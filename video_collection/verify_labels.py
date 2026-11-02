"""Verify completeness and provenance of actual labeling artifacts, without API calls."""
import collections
import hashlib
import json
from label import (LABEL_ROOT, PROTOCOL, AUDITOR, KIMI, QWEN, aggregate_video, citation_errors,
                   validate_ids, validate_times, validate_merge)
from collect import DATA, ROOT, read_jsonl, now
from fireworks_client import load, digest, save


def verify_one(row):
    key = row['key']
    result = load(LABEL_ROOT / 'labels' / (key + '.json'))
    packet = load(LABEL_ROOT / 'claims' / (key + '.json'))
    media = load(LABEL_ROOT / 'media' / key / 'prepared.json')
    transcript = load(LABEL_ROOT / 'media' / key / 'transcript.json')
    assert packet['video_sha256'] == media['video_sha256'] == row['sha256']
    assert packet['media_config_hash'] == media['config_hash'], 'Stale media configuration'
    assert packet['transcript_sha256'] == media['transcript_sha256'] == digest(transcript), 'Stale transcript'
    assert media['frames'] and all((ROOT / f['path']).is_file() for f in media['frames']), 'Missing frames'
    assert len(packet['receipts']) == 3, 'Missing extraction/reconciliation receipts'
    extraction_receipts = [load(LABEL_ROOT / 'api' / (r + '.json')) for r in packet['receipts']]
    origins = []
    for index, model in enumerate([KIMI, QWEN]):
        receipt = extraction_receipts[index]
        assert receipt['requested_model'] == model
        assert receipt['run_id'] == f'{PROTOCOL}:{key}:extract:{index}'
        origins.extend(f'extractor{index}_claim{i}' for i in range(len(receipt['result']['claims'])))
    assert extraction_receipts[2]['run_id'] == f'{PROTOCOL}:{key}:merge'
    validate_merge(packet, origins)
    path = LABEL_ROOT / 'evidence' / (key + '.json')
    sources = load(path)['sources'] if path.exists() else []
    with (ROOT / row['path']).open('rb') as video:
        assert hashlib.file_digest(video, 'sha256').hexdigest() == row['sha256'], 'Changed video file'
    for source in sources:
        assert digest(source['text']) == source['text_sha256'], 'Changed evidence text'
    assert result['protocol'] == PROTOCOL
    assert result.get('postprocess_version') == 2, 'Stale postprocessing'
    assert result['video_sha256'] == row['sha256']
    assert result['claim_packet_sha256'] == digest(packet), 'Stale claims'
    assert result['evidence_packet_sha256'] == digest(sources), 'Stale evidence'
    assert result['human_verified'] is False
    assert result['rounds'] >= 3
    ids = [c['claim_id'] for c in packet['claims']]
    validate_ids(result, ids)
    validate_times(result['claims'], row['duration'])
    judges = result['independent_judges']
    assert len(judges) == result['rounds']
    assert len({j['model'] for j in judges}) >= 2
    assert len({j['receipt'] for j in judges}) == len(judges)
    votes, request_ids = [], []
    for index, judge in enumerate(judges):
        receipt = load(LABEL_ROOT / 'api' / (judge['receipt'] + '.json'))
        assert receipt['requested_model'] == judge['model']
        assert receipt['run_id'] == f'{PROTOCOL}:{key}:judge:{index}'
        request_ids.append(receipt['request_id'])
        validate_ids(receipt['result'], ids)
        votes.append(receipt['result']['claims'])
    assert all(request_ids) and len(set(request_ids)) == len(judges), 'Judge requests are not distinct'
    receipts = [load(LABEL_ROOT / 'api' / (r + '.json')) for r in result['api_receipts']]
    audits = [r for r in receipts if r['run_id'] == f'{PROTOCOL}:{key}:audit']
    assert len(audits) == 1 and audits[0]['requested_model'] == AUDITOR
    audit_map = {c['claim_id']: c for c in audits[0]['result']['claims']}
    for claim in result['claims']:
        counts = collections.Counter(next(c for c in v if c['claim_id'] == claim['claim_id'])['label'] for v in votes)
        assert dict(counts) == claim['vote_counts']
        assert max(counts.values()) / result['rounds'] == claim['agreement_fraction']
        assert claim['evidence_audit'] == audit_map[claim['claim_id']]
        if claim['label'] in {'supported', 'refuted', 'mixed', 'misleading_context'}:
            assert not citation_errors({'label': claim['label'], 'citations': claim['evidence']}, sources)
            assert all(claim['evidence_audit'][f] for f in
                       ['evidence_entails_verdict', 'temporal_scope_valid', 'source_role_valid'])
        if claim['label'] == 'insufficient_evidence' or len(counts) > 1:
            assert claim['requires_human_review']
        if claim['status'] == 'silver_consensus':
            assert len(counts) == 1 and not claim['requires_human_review']
    assert result['video_label'] == aggregate_video(result['claims'])
    assert result['review_required'] == (any(c['requires_human_review'] for c in result['claims']) or not result['claims'])
    return len(result['claims'])


def main():
    failures, total = [], 0
    rows = read_jsonl(DATA / 'downloaded_manifest.jsonl')
    for row in rows:
        try:
            total += verify_one(row)
        except Exception as error:
            failures.append({'video_key': row['key'], 'error': type(error).__name__ + ': ' + str(error)})
    output = {'at': now(), 'videos_expected': len(rows), 'videos_verified': len(rows) - len(failures),
              'claims_verified': total, 'failures': failures, 'passed': not failures,
              'scope': 'Structural, provenance and citation checks; this does not certify factual correctness.'}
    save(LABEL_ROOT / 'verification.json', output)
    print(json.dumps(output, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
