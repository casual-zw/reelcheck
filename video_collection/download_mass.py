"""Bounded parallel downloads; retain the existing download provenance format."""
import argparse
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collect import DATA, ROOT, read_jsonl, append, base_command, ffmpeg, media_file, validate_video, now


def fetch(row):
    key = row['platform'] + '_' + row['video_id']
    command = base_command() + ['--no-playlist', '--write-info-json', '--match-filters',
        'duration >= 10 & duration <= 180 & !is_live', '-f', 'bv*[height<=480]+ba/b[height<=480]/b',
        '--merge-output-format', 'mp4', '--ffmpeg-location', ffmpeg(),
        '-o', str(DATA / 'videos' / (key + '.%(ext)s')), row['url']]
    record = dict(row, key=key, collected_at=now(), status='failed')
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=150)
        path = media_file(key)
        info_path = DATA / 'videos' / (key + '.info.json')
        info = json.loads(info_path.read_text()) if info_path.exists() else {}
        valid, error = validate_video(path) if path else (False, 'No media file')
        if result.returncode or not valid or not 10 <= (info.get('duration') or 0) <= 180:
            record['error'] = (result.stderr + error)[-1500:]
            return record
        with path.open('rb') as media:
            sha = hashlib.file_digest(media, 'sha256').hexdigest()
        record.update(status='downloaded', path=str(path.relative_to(ROOT)), sha256=sha,
            bytes=path.stat().st_size, duration=info['duration'], upload_date=info.get('upload_date'),
            title=info.get('title') or row.get('title'), license=info.get('license'),
            language=info.get('language'), language_reviewed=False, returncode=0,
            channel_id=info.get('channel_id') or row.get('channel_id'),
            source_name=info.get('uploader') or row.get('source_name'),
            source_handle=info.get('uploader_id') or row.get('source_handle'))
    except Exception as error:
        record['error'] = type(error).__name__ + ': ' + str(error)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--count', type=int, default=300)
    p.add_argument('--workers', type=int, default=6)
    args = p.parse_args()
    good = {r['key']: r for r in read_jsonl(DATA / 'downloads.jsonl')
            if r['status'] == 'downloaded' and media_file(r['key'])}
    candidates = iter(r for r in read_jsonl(DATA / 'selected.jsonl')
                      if r['platform'] + '_' + r['video_id'] not in good)
    failures = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {}
        def fill():
            while len(pending) < args.workers and len(good) + len(pending) < args.count and failures < 12:
                row = next(candidates, None)
                if row is None:
                    break
                pending[pool.submit(fetch, row)] = row
        fill()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for job in done:
                pending.pop(job)
                record = job.result()
                append(DATA / 'downloads.jsonl', record)
                if record['status'] == 'downloaded':
                    good[record['key']] = record
                    failures = 0
                else:
                    failures += 1
                print(f"{len(good)}/{args.count} {record['key']}: {record['status']}", flush=True)
            fill()
    from collect import report
    report(None)
    if len(good) < args.count:
        raise SystemExit('Download target not reached; inspect failures before retrying.')


if __name__ == '__main__':
    main()
