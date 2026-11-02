#!/usr/bin/env python3
"""Evidence-grounded, repeated Fireworks judging for the downloaded collection."""
import argparse
import base64
import collections
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collect import ROOT, DATA, now, read_jsonl, write_jsonl
from fireworks_client import Fireworks, digest, save, load
from judge_schemas import (BASE, EXTRACTION, MERGE, JUDGMENT, AUDIT, EXTRACT_PROMPT,
                          MERGE_PROMPT, JUDGE_PROMPT, AUDIT_PROMPT)

KIMI = 'accounts/fireworks/models/kimi-k3'
QWEN = 'accounts/fireworks/models/qwen3p8-max'
AUDITOR = 'accounts/fireworks/models/glm-5p3'
LABEL_ROOT = DATA / 'labeling'
PROTOCOL = 'video-judge-v1'


def rows_for(args):
    rows = read_jsonl(DATA / 'downloaded_manifest.jsonl')
    if args.key:
        rows = [r for r in rows if r['key'] == args.key]
    return rows[:args.limit]


def media_context(row, offset):
    root = LABEL_ROOT / 'media' / row['key']
    media, transcript = load(root / 'prepared.json'), load(root / 'transcript.json')
    if media['video_sha256'] != row['sha256'] or digest(transcript) != media['transcript_sha256']:
        raise ValueError('Prepared media is stale or changed')
    frames = media['frames'][offset::2]
    content = [{'type': 'text', 'text': json.dumps({
        'duration_seconds': row['duration'], 'upload_date': row.get('upload_date'),
        'evaluation_date': '2026-11-02', 'transcript': transcript,
        'sampling_note': media['frame_sampling_note'], 'resolution_note': media['source_resolution']})}]
    total = 0
    for frame in frames:
        data = base64.b64encode((ROOT / frame['path']).read_bytes()).decode()
        total += len(data)
        content += [{'type': 'text', 'text': f"Frame near {frame['seconds']} seconds"},
                    {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + data}}]
    if len(frames) > 120 or total >= 10_000_000:
        raise ValueError('Frame payload exceeds Fireworks image limits')
    return content, media, transcript


def validate_times(claims, duration):
    for claim in claims:
        if not 0 <= claim['start_seconds'] <= claim['end_seconds'] <= duration + 1:
            raise ValueError('Claim timestamp is outside the video')
        if not claim['claim_text'].strip():
            raise ValueError('Empty claim')


def validate_ids(result, ids):
    got = [c['claim_id'] for c in result['claims']]
    if len(got) != len(set(got)) or set(got) != set(ids):
        raise ValueError('Judge omitted, duplicated or invented a claim ID')


def validate_merge(merged, origins):
    used = [i for c in merged['claims'] for i in c['origin_ids']] + [c['origin_id'] for c in merged['excluded']]
    if set(used) != set(origins) or len(used) != len(set(used)):
        raise ValueError('Claim reconciliation lost or duplicated an extraction origin')
    if any(not c['origin_ids'] for c in merged['claims']):
        raise ValueError('Merged claim has no extraction origin')


def normalize(text):
    return ' '.join(text.split()).casefold()


def citation_errors(verdict, sources):
    errors = []
    source_map = {s['evidence_id']: s for s in sources}
    needs_evidence = verdict['label'] in {'supported', 'refuted', 'misleading_context', 'mixed'}
    if needs_evidence and not verdict['citations']:
        errors.append('Verdict has no retrieved evidence')
    for citation in verdict['citations']:
        source = source_map.get(citation['evidence_id'])
        if source is None:
            errors.append('Invented evidence ID')
        elif len(citation['quote'].strip()) < 12 or normalize(citation['quote']) not in normalize(source['text']):
            errors.append('Quoted passage is missing from retrieved evidence')
    return errors


def aggregate_video(claims):
    labels = {c['label'] for c in claims} - {'not_checkable'}
    if not labels:
        return 'not_checkable'
    if 'insufficient_evidence' in labels:
        return 'insufficient_evidence'
    if len(labels) == 1:
        return next(iter(labels))
    return 'mixed'


def extract(row, client):
    key = row['key']
    extracted, receipts = [], []
    def run_extractor(item):
        index, model = item
        content, media, transcript = media_context(row, index)
        result, receipt = client.fork().json(model, EXTRACT_PROMPT, content, EXTRACTION,
            f'{PROTOCOL}:{key}:extract:{index}')
        validate_times(result['claims'], row['duration'])
        for i, claim in enumerate(result['claims']):
            claim['origin_id'] = f'extractor{index}_claim{i}'
        return result, receipt, media, transcript
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result, receipt, media, transcript in pool.map(run_extractor, enumerate([KIMI, QWEN])):
            extracted.append(result)
            receipts.append(receipt)
    origins = [c['origin_id'] for e in extracted for c in e['claims']]
    merged, receipt = client.json(KIMI, MERGE_PROMPT, json.dumps(extracted), MERGE,
                                 f'{PROTOCOL}:{key}:merge', temperature=0.2)
    validate_merge(merged, origins)
    validate_times(merged['claims'], row['duration'])
    for i, claim in enumerate(merged['claims']):
        claim['claim_id'] = f'c{i+1}'
    packet = {'video_key': key, 'protocol': PROTOCOL, 'video_sha256': row['sha256'],
        'media_config_hash': media['config_hash'], 'transcript_sha256': media['transcript_sha256'],
        'claims': merged['claims'], 'excluded': merged['excluded'],
        'extraction_coverage_notes': [note for e in extracted for note in e['coverage_notes']],
        'language': transcript.get('language'), 'language_reviewed': False,
        'receipts': receipts + [receipt], 'at': now()}
    save(LABEL_ROOT / 'claims' / (key + '.json'), packet)
    return packet


def judge(row, client, rounds):
    if rounds < 3:
        raise ValueError('At least three independent judge runs are required')
    key = row['key']
    packet = load(LABEL_ROOT / 'claims' / (key + '.json'))
    _, media, _ = media_context(row, 0)
    if packet['video_sha256'] != row['sha256'] or packet['transcript_sha256'] != media['transcript_sha256']:
        raise ValueError('Claim packet is stale; rerun extraction')
    if packet['media_config_hash'] != media['config_hash'] or packet['protocol'] != PROTOCOL:
        raise ValueError('Claim protocol/media configuration changed; rerun extraction')
    evidence_path = LABEL_ROOT / 'evidence' / (key + '.json')
    sources = load(evidence_path)['sources'] if evidence_path.exists() else []
    for source in sources:
        if source['text_sha256'] != digest(source['text']):
            raise ValueError('Evidence snapshot checksum mismatch')
    claims = packet['claims']
    ids = [c['claim_id'] for c in claims]
    variants = ['Check all assertions impartially.',
                'Pay particular attention to scope, contradictory evidence and missing context.',
                'Pay particular attention to dates, quantities, attribution and the speaker stance.']
    judgments, receipts = [], []
    def run_judge(index):
        model = [KIMI, QWEN, KIMI][index % 3]
        content, _, _ = media_context(row, index % 2)
        # Provenance/source reputation and other judges' answers are intentionally omitted.
        content.append({'type': 'text', 'text': json.dumps({'claims': claims, 'retrieved_evidence': sources})})
        result, receipt = client.fork().json(model, JUDGE_PROMPT + '\n' + variants[index % 3],
            content, JUDGMENT, f'{PROTOCOL}:{key}:judge:{index}', temperature=0.6)
        validate_ids(result, ids)
        print(f'{key}: judge {index+1}/{rounds} complete', flush=True)
        return {'run': index, 'model': model, 'result': result, 'receipt': receipt}
    with ThreadPoolExecutor(max_workers=min(rounds, 8)) as pool:
        judgments = list(pool.map(run_judge, range(rounds)))
    receipts = [j['receipt'] for j in judgments]
    proposed, disagreements = [], []
    for claim in claims:
        votes = [next(v for v in j['result']['claims'] if v['claim_id'] == claim['claim_id']) for j in judgments]
        counts = collections.Counter(v['label'] for v in votes)
        if len(counts) > 1:
            disagreements.append(claim['claim_id'])
        # A tie resolves to abstention before adjudication, never to the first answer.
        label, count = counts.most_common(1)[0]
        if count <= rounds / 2:
            label = 'insufficient_evidence'
        representative = next((v for v in votes if v['label'] == label), votes[0])
        proposed.append(dict(representative, label=label))
    adjudication = None
    if disagreements:
        content, _, _ = media_context(row, 0)
        content.append({'type': 'text', 'text': json.dumps({'claims': claims,
            'retrieved_evidence': sources, 'independent_judgments': judgments})})
        adjudication, receipt = client.json(KIMI, JUDGE_PROMPT +
            '\nYou are now adjudicating disagreement. Independently inspect evidence; majority vote is not proof.',
            content, JUDGMENT, f'{PROTOCOL}:{key}:adjudicate', temperature=0.2)
        validate_ids(adjudication, ids)
        proposed = [next(v for v in adjudication['claims'] if v['claim_id'] == c['claim_id'])
                    if c['claim_id'] in disagreements else p for c, p in zip(claims, proposed)]
        receipts.append(receipt)
    audit, receipt = client.json(AUDITOR, AUDIT_PROMPT, json.dumps({
        'claims': claims, 'proposed_verdicts': proposed, 'retrieved_evidence': sources,
        'upload_date': row.get('upload_date'), 'evaluation_date': '2026-11-02'}),
        AUDIT, f'{PROTOCOL}:{key}:audit', temperature=0.2)
    validate_ids(audit, ids)
    receipts.append(receipt)
    final_claims = []
    for claim, verdict in zip(claims, proposed):
        cid = claim['claim_id']
        votes = [next(v for v in j['result']['claims'] if v['claim_id'] == cid) for j in judgments]
        check = next(c for c in audit['claims'] if c['claim_id'] == cid)
        errors = citation_errors(verdict, sources)
        if not all(check[f] for f in ['evidence_entails_verdict', 'temporal_scope_valid', 'source_role_valid']):
            errors.append('Independent evidence audit failed: ' + check['reason'])
        final_label = verdict['label'] if not errors else 'insufficient_evidence'
        vote_errors = [e for v in votes for e in citation_errors(v, sources)]
        review = bool(final_label == 'insufficient_evidence' or verdict['uncertainties']
                      or errors or vote_errors or cid in disagreements or verdict['requires_human_review']
                      or any(v['requires_human_review'] for v in votes) or claim['uncertainties']
                      or packet['excluded'] or claim['source_role'] == 'unclear'
                      or any(j['result']['coverage_concerns'] for j in judgments))
        status = 'abstained' if final_label == 'insufficient_evidence' else ('needs_review' if review else 'silver_consensus')
        citations = [{**citation, **{k: next(s for s in sources if s['evidence_id'] == citation['evidence_id'])[k]
                      for k in ['url', 'publisher', 'published_at', 'retrieved_at', 'text_sha256']}}
                     for citation in verdict['citations'] if any(s['evidence_id'] == citation['evidence_id'] for s in sources)]
        final_claims.append({**claim, 'label': final_label, 'proposed_label': verdict['label'],
            'adjudicated_label': verdict['label'] if cid in disagreements else None,
            'rationale': verdict['rationale'], 'evidence': citations,
            'reviewer_1': judgments[0]['model'], 'reviewer_2': judgments[1]['model'],
            'vote_counts': dict(collections.Counter(v['label'] for v in votes)),
            'agreement_fraction': max(collections.Counter(v['label'] for v in votes).values()) / rounds,
            'independent_runs': rounds, 'status': status, 'requires_human_review': review,
            'validation_errors': errors, 'judge_citation_errors': vote_errors,
            'evidence_audit': check, 'uncertainties': list(dict.fromkeys(claim['uncertainties'] + verdict['uncertainties']))})
    result = {'video_key': key, 'protocol': PROTOCOL, 'video_sha256': row['sha256'],
        'claim_packet_sha256': digest(packet), 'evidence_packet_sha256': digest(sources),
        'label_origin': 'fireworks_llm_judges', 'human_verified': False, 'postprocess_version': 2,
        'language': packet['language'], 'language_reviewed': False,
        'category': row['sampling_category'], 'event_cluster_id': None, 'duplicate_cluster_id': None,
        'claims': final_claims, 'video_label': aggregate_video(final_claims),
        'independent_judges': [{'model': j['model'], 'receipt': j['receipt']} for j in judgments],
        'rounds': rounds, 'disagreement_claim_ids': disagreements, 'api_receipts': receipts,
        'review_required': any(c['requires_human_review'] for c in final_claims) or not final_claims,
        'notes': ['Machine labels are provisional; consensus is not correctness.',
                  'Shared ASR and evidence can cause correlated errors. Frames are sampled, not full-motion video.'],
        'at': now()}
    save(LABEL_ROOT / 'labels' / (key + '.json'), result)
    return result


def report():
    labels = [load(p) for p in sorted((LABEL_ROOT / 'labels').glob('*.json'))]
    available = read_jsonl(DATA / 'downloaded_manifest.jsonl')
    claims = [c for l in labels for c in l['claims']]
    summary = {'at': now(), 'available_videos': len(available), 'labeled_videos': len(labels),
        'missing_video_keys': sorted({r['key'] for r in available} - {l['video_key'] for l in labels}),
        'claims': len(claims), 'claim_labels': dict(collections.Counter(c['label'] for c in claims)),
        'claim_status': dict(collections.Counter(c['status'] for c in claims)),
        'videos_needing_review': sum(l['review_required'] for l in labels),
        'human_verified_videos': sum(l['human_verified'] for l in labels),
        'disputed_claims': sum(len(l['disagreement_claim_ids']) for l in labels),
        'unanimous_claims': sum(c['agreement_fraction'] == 1 for c in claims),
        'mean_vote_agreement': round(sum(c['agreement_fraction'] for c in claims) / len(claims), 4) if claims else None,
        'audit_rejections': sum(any(e.startswith('Independent evidence audit failed:')
                                   for e in c['validation_errors']) for c in claims),
        'citation_rejections': sum(any(not e.startswith('Independent evidence audit failed:')
                                      for e in c['validation_errors']) for c in claims),
        'models': sorted({j['model'] for l in labels for j in l['independent_judges']}),
        'audit_model': AUDITOR}
    usage = read_jsonl(LABEL_ROOT / 'api' / 'usage.jsonl')
    summary['api_requests'] = len(usage)
    summary['prompt_tokens'] = sum(r['usage'].get('prompt_tokens', 0) for r in usage)
    summary['completion_tokens'] = sum(r['usage'].get('completion_tokens', 0) for r in usage)
    rates = {KIMI: (3.0, 15.0), QWEN: (2.0, 6.0), AUDITOR: (1.4, 4.4)}
    summary['estimated_standard_price_usd'] = round(sum(
        (r['usage'].get('prompt_tokens', 0) * rates[r['model']][0] +
         r['usage'].get('completion_tokens', 0) * rates[r['model']][1]) / 1_000_000
        for r in usage if r['model'] in rates), 4)
    summary['cost_note'] = ('Estimate using published standard token rates checked 2026-11-02; '
                            'includes logged failed generations and smoke tests, ignores cache discounts. '
                            'Not an invoice; interrupted requests without usage receipts may be absent.')
    save(LABEL_ROOT / 'report.json', summary)
    write_jsonl(LABEL_ROOT / 'labels.jsonl', labels)
    write_jsonl(LABEL_ROOT / 'review_queue.jsonl', [dict(c, video_key=l['video_key'])
        for l in labels for c in l['claims'] if c['requires_human_review'] or c['status'] == 'abstained'])
    print(json.dumps(summary, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['extract', 'judge', 'report', 'preflight'])
    p.add_argument('--key')
    p.add_argument('--limit', type=int, default=1000)
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--workers', type=int, default=1)
    args = p.parse_args()
    if args.command == 'report':
        report()
        return
    client = Fireworks()
    if args.command == 'preflight':
        catalog = {m['id']: m for m in client.models()['data']}
        for model in [KIMI, QWEN, AUDITOR]:
            if model not in catalog:
                raise RuntimeError('Required model not available: ' + model)
            if model != AUDITOR and not catalog[model].get('supports_image_input'):
                raise RuntimeError('Image support missing: ' + model)
            print(model + ': available')
        return
    rows = rows_for(args)
    def process(row):
        print(f"{args.command} {row['key']}", flush=True)
        worker_client = Fireworks()
        if args.command == 'extract':
            extract(row, worker_client)
        else:
            judge(row, worker_client, args.rounds)
        return row['key']
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
        jobs = {pool.submit(process, row): row['key'] for row in rows}
        for job in as_completed(jobs):
            try:
                print('Completed: ' + job.result(), flush=True)
            except Exception as error:
                failures.append({'video_key': jobs[job], 'error': str(error), 'at': now()})
                print(f"Failed {jobs[job]}: {error}", flush=True)
    if args.command == 'extract':
        packets = [load(p) for p in sorted((LABEL_ROOT / 'claims').glob('*.json'))]
        write_jsonl(LABEL_ROOT / 'evidence_requests.jsonl', [{'video_key': p['video_key'],
            'claims': [{'claim_id': c['claim_id'], 'claim_text': c['claim_text'], 'queries': c['search_queries']} for c in p['claims']]}
            for p in packets])
    else:
        report()
    if failures:
        save(LABEL_ROOT / (args.command + '_failures.json'), failures)
        raise SystemExit(f'{len(failures)} jobs failed; successful requests are cached for resumption.')
    save(LABEL_ROOT / (args.command + '_failures.json'), [])


if __name__ == '__main__':
    main()
