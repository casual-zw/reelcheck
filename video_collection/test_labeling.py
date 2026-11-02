import unittest
from unittest.mock import patch, Mock
from tempfile import TemporaryDirectory
from pathlib import Path
from fireworks_client import Fireworks
import socket
import threading
from types import SimpleNamespace
from fireworks_client import save
from label import judge, PROTOCOL
from batch_label import shard_for, process
from bulk_label import decide
from label import citation_errors, validate_ids, validate_merge, validate_times, aggregate_video
from evidence import public_https


class LabelingTests(unittest.TestCase):
    def test_bulk_disagreement_abstains_instead_of_selecting_a_winner(self):
        votes = [{'result': {'label': 'supported'}}, {'result': {'label': 'refuted'}}]
        self.assertEqual(decide(votes), 'insufficient_evidence')
        votes[1]['result']['label'] = 'supported'
        self.assertEqual(decide(votes), 'supported')

    def test_judge_rounds_run_concurrently_and_keep_stable_vote_order(self):
        barrier = threading.Barrier(3, timeout=3)
        claim = {'claim_id': 'c1', 'claim_text': 'Test assertion', 'start_seconds': 0,
                 'end_seconds': 1, 'source_role': 'original_claim', 'uncertainties': []}
        class Client:
            def fork(self):
                return self
            def json(self, model, system, content, schema, run_id, **kwargs):
                if ':judge:' in run_id:
                    barrier.wait()
                    return {'claims': [{'claim_id': 'c1', 'label': 'insufficient_evidence',
                        'rationale': 'No evidence', 'citations': [], 'uncertainties': [],
                        'requires_human_review': False}], 'coverage_concerns': []}, run_id
                return {'claims': [{'claim_id': 'c1', 'evidence_entails_verdict': True,
                    'temporal_scope_valid': True, 'source_role_valid': True, 'reason': 'Abstention fits'}]}, run_id
        with TemporaryDirectory() as directory:
            root = Path(directory)
            packet = {'protocol': PROTOCOL, 'video_sha256': 'v', 'transcript_sha256': 't',
                      'media_config_hash': 'm', 'claims': [claim], 'excluded': [], 'language': 'en'}
            save(root / 'claims' / 'test.json', packet)
            media = {'config_hash': 'm', 'transcript_sha256': 't'}
            with patch('label.LABEL_ROOT', root), patch('label.media_context', return_value=([], media, {})):
                result = judge({'key': 'test', 'sha256': 'v', 'sampling_category': 'test'}, Client(), 3)
            self.assertEqual([j['receipt'].rsplit(':', 1)[1] for j in result['independent_judges']], ['0', '1', '2'])
            self.assertEqual(result['claims'][0]['vote_counts'], {'insufficient_evidence': 3})
            self.assertTrue(result['review_required'])

    def test_shards_are_disjoint_and_cover_every_key(self):
        keys = {f'video_{i}' for i in range(100)}
        shards = [{key for key in keys if shard_for(key, 4) == i} for i in range(4)]
        self.assertEqual(set.union(*shards), keys)
        self.assertEqual(sum(map(len, shards)), len(keys))

    def test_locked_video_is_not_submitted_twice(self):
        import fcntl
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'locks').mkdir()
            with (root / 'locks' / 'test.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch('batch_label.LABEL_ROOT', root), patch('batch_label.Fireworks') as client:
                    self.assertEqual(process({'key': 'test'}, SimpleNamespace())['status'], 'locked_by_another_worker')
                    client.assert_not_called()

    def test_truncated_response_is_retried_and_never_cached_as_a_label(self):
        schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}
        def response(reason, content):
            result = Mock(status_code=200)
            result.json.return_value = {'id': 'test', 'usage': {},
                'choices': [{'finish_reason': reason, 'message': {'content': content}}]}
            return result
        with TemporaryDirectory() as directory:
            client = object.__new__(Fireworks)
            client.root = Path(directory)
            client.session = Mock()
            client.session.post.side_effect = [response('length', '{"ok":'), response('stop', '{"ok":true}')]
            result, receipt = client.json('test-model', 'system', 'content', schema, 'round-1')
            self.assertEqual(result, {'ok': True})
            self.assertEqual(client.session.post.call_count, 2)
            self.assertEqual(client.session.post.call_args.kwargs['json']['max_tokens'], 32768)
            self.assertEqual(client.json('test-model', 'system', 'content', schema, 'round-1')[1], receipt)
            self.assertEqual(client.session.post.call_count, 2)
            client.session.post.side_effect = [response('stop', '{"ok":true}')]
            self.assertNotEqual(client.json('test-model', 'system', 'content', schema, 'round-2')[1], receipt)
            self.assertEqual(client.session.post.call_count, 3)

    def test_true_false_cannot_pass_without_retrieved_evidence(self):
        for label in ['supported', 'refuted', 'mixed', 'misleading_context']:
            self.assertTrue(citation_errors({'label': label, 'citations': []}, []))
        self.assertFalse(citation_errors({'label': 'insufficient_evidence', 'citations': []}, []))

    def test_real_url_does_not_validate_fabricated_quote(self):
        source = {'evidence_id': 'e1', 'text': 'The study did not establish a causal relationship.'}
        verdict = {'label': 'refuted', 'citations': [{'evidence_id': 'e1', 'quote': 'The study proved causation.'}]}
        self.assertTrue(citation_errors(verdict, [source]))
        verdict['citations'][0]['quote'] = 'did not establish a causal relationship'
        self.assertFalse(citation_errors(verdict, [source]))
        verdict['citations'][0]['evidence_id'] = 'invented'
        self.assertTrue(citation_errors(verdict, [source]))

    def test_every_judge_must_cover_every_claim_exactly_once(self):
        for ids in [['c1'], ['c1', 'c1'], ['c1', 'c3']]:
            with self.assertRaises(ValueError):
                validate_ids({'claims': [{'claim_id': i} for i in ids]}, ['c1', 'c2'])
        validate_ids({'claims': [{'claim_id': 'c2'}, {'claim_id': 'c1'}]}, ['c1', 'c2'])

    def test_merger_cannot_silently_drop_rare_claims(self):
        with self.assertRaises(ValueError):
            validate_merge({'claims': [{'origin_ids': ['a']}], 'excluded': []}, ['a', 'b'])
        validate_merge({'claims': [{'origin_ids': ['a', 'b']}], 'excluded': []}, ['a', 'b'])

    def test_timestamps_and_abstention(self):
        with self.assertRaises(ValueError):
            validate_times([{'start_seconds': 20, 'end_seconds': 10, 'claim_text': 'X'}], 30)
        self.assertEqual(aggregate_video([{'label': 'supported'}, {'label': 'insufficient_evidence'}]), 'insufficient_evidence')
        self.assertEqual(aggregate_video([{'label': 'supported'}, {'label': 'refuted'}]), 'mixed')
        self.assertEqual(aggregate_video([{'label': 'not_checkable'}]), 'not_checkable')

    def test_evidence_fetch_rejects_internal_and_credential_urls(self):
        for url in ['http://example.com', 'https://user:secret@example.com', 'file:///etc/passwd', 'https://example.com:8080']:
            with self.assertRaises(ValueError):
                public_https(url)
        for ip in ['127.0.0.1', '169.254.169.254', '10.1.2.3', '::1']:
            with patch('evidence.socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))]):
                with self.assertRaises(ValueError):
                    public_https('https://example.com')


if __name__ == '__main__':
    unittest.main()
