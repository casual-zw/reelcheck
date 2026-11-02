"""Verify bulk-label coverage, media provenance and independent API receipts."""
import argparse
import hashlib
import json
from jsonschema import validate
from collect import DATA, ROOT, read_jsonl, now
from fireworks_client import load, save, digest
from bulk_label import BULK, PROTOCOL, SCHEMA, PROMPT, content_for, decide, report
from label import KIMI, QWEN


def verify(row, result):
    key = row['key']
    assert result['protocol'] == PROTOCOL
    assert result['video_sha256'] == row['sha256']
    with (ROOT / row['path']).open('rb') as f:
        assert hashlib.file_digest(f, 'sha256').hexdigest() == row['sha256']
    assert result['human_verified'] is False
    if result['label_tier'] == 'audited_claim_aggregate':
        from verify_labels import verify_one
        verify_one(row)
        original = load(ROOT / result['audited_label_path'])
        assert result['label'] == original['video_label']
        return
    assert result['label_tier'] == 'provisional_video_screen'
    assert result['externally_verified'] is False
    media = load(BULK / 'media' / key / 'prepared.json')
    assert result['media_sha256'] == digest(media)
    assert media['video_sha256'] == row['sha256']
    assert len(media['frames']) == 6
    assert all((ROOT / f['path']).is_file() for f in media['frames'])
    votes = result['judgments']
    assert len(votes) == 2 and [v['model'] for v in votes] == [KIMI, QWEN]
    request_ids = []
    content = content_for(row, media)
    for index, vote in enumerate(votes):
        receipt = load(DATA / 'labeling' / 'api' / (vote['receipt'] + '.json'))
        assert receipt['requested_model'] == vote['model']
        assert receipt['run_id'] == f'{PROTOCOL}:{key}:{index}'
        assert vote['result'] == receipt['result']
        expected_hashes = set()
        for limit in [1024, 2048]:
            body = {'model': vote['model'], 'messages': [
                {'role': 'system', 'content': PROMPT + '\nJSON schema:\n' + json.dumps(SCHEMA)},
                {'role': 'user', 'content': content}], 'temperature': .2, 'max_tokens': limit,
                'response_format': {'type': 'json_schema', 'json_schema': {'name': 'annotation', 'schema': SCHEMA}},
                'reasoning_effort': 'none'}
            expected_hashes.add(digest(body))
        assert receipt['input_sha256'] in expected_hashes, 'Media, prompt or token budget does not match request'
        validate(vote['result'], SCHEMA)
        request_ids.append(receipt['request_id'])
    assert all(request_ids) and len(set(request_ids)) == 2
    assert result['label'] == decide(votes)
    assert result['agreement'] == (votes[0]['result']['label'] == votes[1]['result']['label'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected', type=int, default=300)
    args = p.parse_args()
    rows = {r['key']: r for r in read_jsonl(DATA / 'downloads.jsonl') if r['status'] == 'downloaded'}
    labels = [load(p) for p in sorted((BULK / 'labels').glob('*.json'))]
    failures = []
    for result in labels:
        try:
            verify(rows[result['video_key']], result)
        except Exception as error:
            failures.append({'video_key': result['video_key'], 'error': type(error).__name__ + ': ' + str(error)})
    output = {'at': now(), 'expected': args.expected, 'labels': len(labels),
        'verified': len(labels)-len(failures), 'failures': failures,
        'passed': len(labels) >= args.expected and not failures,
        'scope': 'Coverage, source hashes, two distinct judging requests (or audited pilot provenance), schemas and aggregation. Not a factual correctness certificate.'}
    save(BULK / 'verification.json', output)
    print(output)
    if not output['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
