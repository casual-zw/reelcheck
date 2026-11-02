import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from argparse import Namespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('run_model_matrix',ROOT/'scripts/run_model_matrix.py')
matrix=importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


class MatrixTests(unittest.TestCase):
    def setUp(self):
        text='The reading is 18 degrees Celsius.'
        self.case={'case_id':'c1','group_id':'g1','as_of':'2026-11-02','claim_text':text,
                   'evidence':[{'id':'p1','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}],
                   'gold':'HIDDEN_GOLD','reviewer_notes':'HIDDEN_REVIEW'}
        self.variant={'id':'v1','prompt_system':'B','provider':'fireworks','model':'test',
                      'max_output_tokens':128,'timeout_s':5,'pricing':{'input_per_million':1.,'output_per_million':1.}}
        self.result={'execution_status':'completed','output':{'claim_text':text,'verdict':'supported',
                    'citations':[{'passage_id':'p1','quote':text}],'uncertainty_reason':None,'explanation':'The packet gives the same reading.'},
                    'cost_usd':.0001,'latency_s':.01,'usage':{'prompt_tokens':10,'completion_tokens':10}}

    def setup_files(self,tmp,*,max_calls=100,max_cost=1.,live=True,workers=2,cases=2):
        path=Path(tmp)
        variants=[self.variant,{**self.variant,'id':'v2'}]
        (path/'config.json').write_text(json.dumps({'variants':variants}))
        inputs=[{**self.case,'case_id':f'c{i}'} for i in range(cases)]
        (path/'inputs.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in inputs))
        return Namespace(config=str(path/'config.json'),inputs=str(path/'inputs.jsonl'),out=str(path/'out'),
                         workers=workers,max_calls=max_calls,max_cost_usd=max_cost,seed=42,live=live,shell_keys=None)

    def test_call_budget_and_gold_blind_prompts_persist_every_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.setup_files(tmp,max_calls=3)
            with patch.dict('os.environ',{'FIREWORKS_API_KEY':'FAKE'}),patch.object(matrix,'call',return_value=self.result) as post:
                result=matrix.run_matrix(args)
            self.assertEqual(post.call_count,3)
            self.assertNotIn('HIDDEN',json.dumps(post.call_args_list,default=str))
            rows=matrix.read_jsonl(Path(args.out)/'runs.jsonl')
            self.assertEqual(len(rows),3)
            self.assertEqual([r['call_index'] for r in rows],[1,2,3])
            self.assertEqual(result['completion']['stop_reason'],'call_or_cost_budget_reached')
            self.assertTrue(any(s['incomplete'] for s in result['systems'].values()))

    def test_cost_reservation_blocks_dispatch_without_invented_free_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.setup_files(tmp,max_cost=.000001)
            with patch.dict('os.environ',{'FIREWORKS_API_KEY':'FAKE'}),patch.object(matrix,'call') as post:
                result=matrix.run_matrix(args)
            post.assert_not_called()
            self.assertEqual(result['paid_calls_attempted'],0)
            self.assertIsNone(result['estimated_actual_run_cost_usd'])

    def test_access_failure_stops_new_work_and_drains_other_inflight_request(self):
        lock=threading.Lock()
        active=0
        maximum=0
        calls=0
        def provider(*_):
            nonlocal active,maximum,calls
            with lock:
                calls+=1
                index=calls
                active+=1
                maximum=max(maximum,active)
            time.sleep(.01 if index==1 else .04)
            with lock: active-=1
            if index==1:
                return {'execution_status':'api_error','http_status':429,'output':None,'cost_usd':None,'latency_s':.01}
            return self.result
        with tempfile.TemporaryDirectory() as tmp:
            args=self.setup_files(tmp,cases=5)
            with patch.dict('os.environ',{'FIREWORKS_API_KEY':'FAKE'}),patch.object(matrix,'call',side_effect=provider):
                result=matrix.run_matrix(args)
            self.assertEqual(calls,2)
            self.assertEqual(maximum,2)
            self.assertEqual(result['completion']['saved_records'],2)
            self.assertIsNone(result['estimated_actual_run_cost_usd'])
            self.assertEqual(result['unknown_cost_calls'],1)

    def test_dry_run_has_no_model_results_and_no_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.setup_files(tmp,live=False)
            with patch.object(matrix,'call') as post:
                matrix.run_matrix(args)
            post.assert_not_called()
            self.assertFalse((Path(args.out)/'runs.jsonl').exists())
            self.assertNotIn('HIDDEN',(Path(args.out)/'request_preview.jsonl').read_text())
            self.assertTrue((Path(args.out)/'source_snapshot/reelcheck/prompts.py').exists())

    def test_malformed_output_is_failure_not_quality_success(self):
        result=copy.deepcopy(self.result)
        result['output']['citations'][0]['quote']='fabricated'
        with patch.object(matrix,'call',return_value=result):
            row=matrix._execute(self.case,self.variant,[],1)
        self.assertEqual(row['execution_status'],'invalid_output')
        summary=matrix.operational_summary([row],[self.variant],1)
        self.assertEqual(summary['systems']['v1']['schema_valid_completed'],0)
        self.assertNotIn('accuracy',summary['systems']['v1'])


if __name__=='__main__':
    unittest.main()
