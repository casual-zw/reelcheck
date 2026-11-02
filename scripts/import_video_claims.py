"""Convert local claim and evidence packets into unlabeled verifier inputs."""
import argparse
import hashlib
import json
from pathlib import Path


def convert(claims, packet, as_of):
    if claims['video_key'] != packet['video_key']:
        raise ValueError('Claim and evidence packets refer to different videos')
    evidence = []
    seen = set()
    for source in packet['sources']:
        text, source_id = source['text'], source['evidence_id']
        if not text or source_id in seen:
            raise ValueError('Empty evidence or duplicate evidence ID')
        encoded = json.dumps(text, sort_keys=True, ensure_ascii=False).encode()
        if hashlib.sha256(encoded).hexdigest() != source['text_sha256']:
            raise ValueError('Evidence text hash mismatch')
        seen.add(source_id)
        evidence.append({'id': source_id, 'text': text, 'url': source['url'],
                         'sha256': hashlib.sha256(text.encode()).hexdigest(),
                         'collection_text_sha256': source['text_sha256']})
    rows = []
    for claim in claims['claims']:
        if claim.get('speaker_stance') != 'asserts':
            continue
        rows.append({'case_id': claims['video_key'] + '_' + claim['claim_id'],
                     'group_id': claims['video_key'], 'split': 'development_unreviewed',
                     'as_of': as_of, 'claim_text': claim['claim_text'], 'evidence': evidence,
                     'timestamp': {'start_seconds': claim.get('start_seconds'),
                                   'end_seconds': claim.get('end_seconds')},
                     'human_label_status': 'pending'})
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--claims', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--as-of', required=True, help='Evidence cutoff date (YYYY-MM-DD)')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    from datetime import date
    date.fromisoformat(args.as_of)
    rows = convert(json.loads(args.claims.read_text()), json.loads(args.evidence.read_text()), args.as_of)
    with args.out.open('x') as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(f'Wrote {len(rows)} unlabeled development claims to {args.out}')


if __name__ == '__main__':
    main()
