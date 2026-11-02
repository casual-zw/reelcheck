"""Resumable parallel labeling with per-video locks, bounded API concurrency and shards."""
import argparse
import fcntl
import hashlib
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collect import DATA, read_jsonl, now
from fireworks_client import Fireworks, load, save, set_request_limit
from label import LABEL_ROOT, PROTOCOL, extract, judge, report
from verify_labels import verify_one


def shard_for(key, count):
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % count


def current_claims(row):
    try:
        packet = load(LABEL_ROOT / 'claims' / (row['key'] + '.json'))
        media = load(LABEL_ROOT / 'media' / row['key'] / 'prepared.json')
        return (packet['protocol'] == PROTOCOL and packet['video_sha256'] == row['sha256']
                and packet['transcript_sha256'] == media['transcript_sha256']
                and packet['media_config_hash'] == media['config_hash'])
    except (OSError, ValueError, KeyError):
        return False


def current_label(row, rounds):
    try:
        verify_one(row)
        return load(LABEL_ROOT / 'labels' / (row['key'] + '.json'))['rounds'] == rounds
    except (OSError, ValueError, KeyError, AssertionError):
        return False


def process(row, args):
    key = row['key']
    locks = LABEL_ROOT / 'locks'
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / (key + '.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'video_key': key, 'status': 'locked_by_another_worker'}
        started = time.monotonic()
        def status(state, **extra):
            value = {'video_key': key, 'status': state, 'at': now(),
                     'elapsed_seconds': round(time.monotonic() - started, 1), **extra}
            save(LABEL_ROOT / 'jobs' / (key + '.json'), value)
            print(f'{key}: {state}', flush=True)
            return value
        try:
            if current_label(row, args.rounds):
                return status('already_complete')
            if not (LABEL_ROOT / 'media' / key / 'prepared.json').exists():
                return status('needs_preparation')
            if args.wait_for_claims and not current_claims(row):
                status('waiting_for_existing_extraction')
                deadline = time.monotonic() + args.wait_seconds
                while not current_claims(row):
                    if time.monotonic() >= deadline:
                        return status('claims_wait_timeout')
                    time.sleep(2)
            client = Fireworks()
            if not current_claims(row):
                status('extracting')
                extract(row, client)
            evidence_path = LABEL_ROOT / 'evidence' / (key + '.json')
            sources = load(evidence_path)['sources'] if evidence_path.exists() else []
            if not sources and not args.allow_empty_evidence:
                return status('needs_evidence')
            status('judging')
            judge(row, client, args.rounds)
            count = verify_one(row)
            return status('complete', claims=count)
        except Exception as error:
            return status('failed', error=type(error).__name__ + ': ' + str(error))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workers', type=int, default=8, help='Concurrent video pipelines')
    p.add_argument('--max-requests', type=int, default=16, help='Maximum simultaneous API requests in this process')
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--limit', type=int, default=1000)
    p.add_argument('--shard-count', type=int, default=1)
    p.add_argument('--shard-index', type=int, default=0)
    p.add_argument('--exclude-keys-file', help='JSON array of keys handled by an existing legacy process')
    p.add_argument('--include-keys-file', help='Only process keys in this JSON array')
    p.add_argument('--wait-for-claims', action='store_true', help='Wait for existing extraction jobs instead of duplicating them')
    p.add_argument('--wait-seconds', type=int, default=1800)
    p.add_argument('--allow-empty-evidence', action='store_true', help='Explicitly permit judgments with no external evidence; factual claims should abstain')
    args = p.parse_args()
    if not (1 <= args.workers <= 64 and 1 <= args.max_requests <= 128 and args.rounds >= 3
            and args.shard_count >= 1 and 0 <= args.shard_index < args.shard_count):
        p.error('Invalid concurrency, rounds or shard arguments')
    set_request_limit(args.max_requests)
    excluded = set(load(Path(args.exclude_keys_file))) if args.exclude_keys_file else set()
    included = set(load(Path(args.include_keys_file))) if args.include_keys_file else None
    rows = [r for r in read_jsonl(DATA / 'downloaded_manifest.jsonl')[:args.limit]
            if r['key'] not in excluded and (included is None or r['key'] in included)
            and shard_for(r['key'], args.shard_count) == args.shard_index]
    # Schedule ready claims first; waiting tasks cannot starve immediately runnable videos.
    rows.sort(key=lambda r: not current_claims(r))
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(process, row, args) for row in rows]
        for job in as_completed(jobs):
            results.append(job.result())
            print(f'Progress: {len(results)}/{len(rows)} jobs returned', flush=True)
    save(LABEL_ROOT / f'batch_shard_{args.shard_index}_of_{args.shard_count}.json',
         {'at': now(), 'workers': args.workers, 'max_requests': args.max_requests, 'results': results})
    report()
    if any(r['status'] not in {'complete', 'already_complete'} for r in results):
        raise SystemExit('Some jobs remain incomplete; inspect data/labeling/jobs and rerun the same command.')


if __name__ == '__main__':
    main()
