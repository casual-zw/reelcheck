import hashlib
import json
import unittest

from scripts.import_video_claims import convert


class ImportVideoClaimsTest(unittest.TestCase):
    def test_unlabeled_claims_and_evidence_integrity(self):
        claims = {'video_key': 'clip', 'claims': [
            {'claim_id': 'c1', 'claim_text': 'A claim', 'speaker_stance': 'asserts',
             'start_seconds': 1, 'end_seconds': 2, 'label': 'supported'},
            {'claim_id': 'c2', 'claim_text': 'A quote', 'speaker_stance': 'quotes'}]}
        text = 'A source passage'
        source = {'evidence_id': 'e1', 'text': text, 'url': 'https://example.org',
                  'text_sha256': hashlib.sha256(json.dumps(text, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
        packet = {'video_key': 'clip', 'sources': [source]}
        rows = convert(claims, packet, '2026-11-02')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['case_id'], 'clip_c1')
        self.assertNotIn('label', rows[0])
        self.assertEqual(rows[0]['evidence'][0]['text'], text)
        source['text'] = 'altered'
        with self.assertRaises(ValueError):
            convert(claims, packet, '2026-11-02')

    def test_rejects_mismatched_video(self):
        with self.assertRaises(ValueError):
            convert({'video_key': 'one'}, {'video_key': 'two'}, '2026-11-02')
