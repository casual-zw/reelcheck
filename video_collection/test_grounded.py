import unittest
from grounded_labels import check_ids, citation_valid, passages
from fireworks_client import digest


class GroundedTests(unittest.TestCase):
    def test_identical_duplicates_can_be_normalized_but_conflicts_cannot(self):
        claim={'claim_id':'c1'}
        vote={'claim_id':'c1','label':'supported'}
        result={'claims':[vote,dict(vote)]}
        check_ids(result,[claim]);self.assertEqual(len(result['claims']),1)
        with self.assertRaises(ValueError):
            check_ids({'claims':[vote,dict(vote,label='refuted')]},[claim])
        with self.assertRaises(ValueError):
            check_ids({'claims':[]},[claim])

    def test_definitive_verdict_requires_real_passage(self):
        evidence=[{'passage_id':'p_real'}]
        self.assertFalse(citation_valid({'label':'supported','passage_ids':[]},evidence))
        self.assertFalse(citation_valid({'label':'supported','passage_ids':['made_up']},evidence))
        self.assertTrue(citation_valid({'label':'supported','passage_ids':['p_real']},evidence))

    def test_passages_reproduce_exact_source_spans(self):
        text='The clinical trial enrolled sixty adults. '*80
        source={'text':text,'evidence_id':'e1','url':'https://example.org/study','title':'Trial',
                'publisher':'example.org','published_at':'2024-01-01','retrieved_at':'2026-11-02',
                'text_sha256':digest(text),'retrieval_method':'direct_https'}
        snippets=passages(source,[{'text':'The trial enrolled sixty adults','search_query':'clinical trial sixty adults','kind':'factual'}])
        self.assertTrue(snippets)
        for p in snippets:self.assertEqual(p['text'],text[p['start']:p['end']])


if __name__=='__main__':unittest.main()
