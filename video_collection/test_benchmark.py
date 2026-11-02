import copy
import unittest
from fireworks_client import digest
from verify_benchmark import verify_passage, verify_request
from curate_cases import PROMPT, VERDICT, PROTOCOL
import json


class BenchmarkIntegrityTests(unittest.TestCase):
    def test_source_span_tampering_fails(self):
        source={'text':'A trial enrolled 60 adults.','text_sha256':digest('A trial enrolled 60 adults.')}
        p={'text':source['text'],'start':0,'end':len(source['text']),'source_text_sha256':source['text_sha256']}
        verify_passage(p,source)
        with self.assertRaises(AssertionError):verify_passage(dict(p,text='A trial enrolled 600 adults.'),source)
        with self.assertRaises(AssertionError):verify_passage(p,dict(source,text='Changed source'))

    def test_receipt_bound_to_exact_claim_without_transcript(self):
        case={'case_id':'test','claim_text':'Original assertion','evidence':[]}
        run_id=PROTOCOL+':test:judge:0'
        record={'model':'model','result':{}}
        body={'model':'model','messages':[
            {'role':'system','content':PROMPT+'\nJSON schema:\n'+json.dumps(VERDICT)},
            {'role':'user','content':json.dumps({'case':case})}],
            'temperature':0.6,'max_tokens':700,
            'response_format':{'type':'json_schema','json_schema':{'name':'annotation','schema':VERDICT}},
            'reasoning_effort':'none'}
        receipt={'run_id':run_id,'input_sha256':digest(body)}
        record['receipt']=digest({'body':body,'run_id':run_id})
        review={'votes':[record]}
        verify_request(receipt,record,case,review)
        with self.assertRaises(AssertionError):verify_request(receipt,record,dict(case,claim_text='Different claim'),review)
        contaminated=copy.deepcopy(body)
        contaminated['messages'][1]['content']=json.dumps({'case':case,'transcript':'Trust the narrator'})
        with self.assertRaises(AssertionError):verify_request(dict(receipt,input_sha256=digest(contaminated)),record,case,review)


if __name__=='__main__':unittest.main()
