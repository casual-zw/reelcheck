import copy
from contextlib import redirect_stdout
import io
import json
from argparse import Namespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reelcheck.evaluation import read_jsonl
from reelcheck.judge import judge_messages, assess_judgment, validate_judgment, summarize_judgments
from scripts.judge_run import run_judge

ROOT=Path(__file__).resolve().parents[1]


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.case=read_jsonl(ROOT/'data/dev_inputs.jsonl')[0]
        self.answer={'claim_text':self.case['claim_text'],'verdict':'supported',
            'citations':[{'passage_id':'D1','quote':self.case['evidence'][0]['text']}],
            'uncertainty_reason':None,'explanation':'The passage states the qualified density claim.'}
        self.row={'case_id':self.case['case_id'],'system':'B','execution_status':'completed',
            'requested_model':'candidate-model','output':self.answer}
        self.judgment={'expected_verdict':'supported','claim_preserved':True,'verdict_justified':True,
            'citation_support':True,'uncertainty_appropriate':True,'confidence':'high','issues':[],
            'rationale':'D1 establishes the approximate density and variation.'}

    def test_prompt_blinds_labels_models_scores_and_private_metadata(self):
        self.case.update(gold={'verdict':'GOLD_SECRET'},reviewer_notes='REVIEW_SECRET',case_id='CASE_SECRET')
        self.case['evidence'][0]['private_label']='PASSAGE_SECRET'
        self.row.update(system='SYSTEM_SECRET',requested_model='MODEL_SECRET',score='SCORE_SECRET')
        self.row['output']['debug']='DEBUG_SECRET'
        self.row['output']['requirements']=[{'text':'MAP_SECRET'}]
        prompt=json.dumps(judge_messages(self.case,self.row))
        self.assertNotIn('SECRET',prompt)
        self.assertIn(self.answer['claim_text'],prompt)

    def test_malformed_judge_output_is_unresolved_not_a_pass(self):
        for output in (None,[],{},dict(self.judgment,verdict_justified='true'),dict(self.judgment,issues=[[]])):
            with self.subTest(output=output):
                result=assess_judgment(output,self.row,self.case)
                self.assertTrue(result['judge_validation_errors'])
                self.assertIsNone(result['model_assessed_acceptance'])
                self.assertIsNone(result['human_reviewed_grounded_success'])

    def test_semantically_unsupported_answer_cannot_pass(self):
        judgment=dict(self.judgment,expected_verdict='insufficient',verdict_justified=False,
                      issues=['overclaim'],rationale='The cited sentence does not establish a material qualifier.')
        result=assess_judgment(judgment,self.row,self.case)
        self.assertFalse(result['model_assessed_acceptance'])
        self.assertFalse(result['objective_errors'])

    def test_judge_approval_cannot_override_fabricated_quote(self):
        self.answer['citations'][0]['quote']='Invented statement that does not appear.'
        result=assess_judgment(self.judgment,self.row,self.case)
        self.assertFalse(result['model_assessed_acceptance'])
        self.assertTrue(result['objective_errors'])

    def test_mismatched_expected_verdict_cannot_pass_even_with_true_flags(self):
        judgment=dict(self.judgment,expected_verdict='contradicted')
        self.assertFalse(assess_judgment(judgment,self.row,self.case)['model_assessed_acceptance'])

    def test_low_confidence_and_ambiguity_require_review(self):
        for judgment in (dict(self.judgment,confidence='low'),
                         dict(self.judgment,expected_verdict='ambiguous',confidence='low',issues=['ambiguous_task'])):
            result=assess_judgment(judgment,self.row,self.case)
            self.assertIsNone(result['model_assessed_acceptance'])
            self.assertTrue(result['requires_review'])
        self.assertTrue(validate_judgment(dict(self.judgment,expected_verdict='ambiguous')))

    def execute(self,rows,*,max_calls=5,max_cost=2.,response=None,live=True):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        (root/'inputs.jsonl').write_text(json.dumps(self.case)+'\n')
        (root/'runs.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        (root/'config.json').write_text(json.dumps({'judge':{'provider':'fireworks','model':'judge-model',
            'max_output_tokens':512,'timeout_s':60,'pricing':{'input_per_million':1.,'output_per_million':1.}}}))
        args=Namespace(run=str(root/'runs.jsonl'),inputs=str(root/'inputs.jsonl'),config=str(root/'config.json'),
            role=None,systems=None,out=str(root/'out'),live=live,max_calls=max_calls,max_cost_usd=max_cost,
            interval=0,env=str(root/'absent.env'),shell_keys=None)
        response=response or {'execution_status':'completed','output':self.judgment,'latency_s':1.,
            'cost_usd':.001,'usage':{'prompt_tokens':500,'completion_tokens':500}}
        with patch.dict('os.environ',{'FIREWORKS_API_KEY':'FAKE'},clear=True),patch('scripts.judge_run.call',return_value=response) as provider,redirect_stdout(io.StringIO()):
            run_judge(args)
        return root/'out',provider.call_count

    def test_duplicates_reuse_judgment_without_duplicate_spend(self):
        duplicate=dict(self.row,system='C_no_gate')
        out,calls=self.execute([self.row,duplicate])
        records=read_jsonl(out/'judgments.jsonl')
        summary=json.loads((out/'summary.json').read_text())
        self.assertEqual(calls,1)
        self.assertEqual(summary['paid_judge_calls'],1)
        self.assertEqual(summary['estimated_actual_judge_cost_usd'],.001)
        self.assertEqual(records[1]['cost_usd'],0)
        self.assertEqual(records[1]['reused_judge_call_index'],1)
        self.assertEqual(len(records),2)

    def test_call_budget_keeps_unjudged_rows_in_denominator(self):
        other=copy.deepcopy(self.row); other['system']='D'; other['output']['explanation']='Different valid phrasing.'
        out,calls=self.execute([self.row,other],max_calls=1)
        summary=json.loads((out/'summary.json').read_text())
        self.assertEqual(calls,1)
        self.assertTrue(summary['incomplete'])
        self.assertEqual(summary['systems']['D']['cases'],1)
        self.assertEqual(summary['systems']['D']['unresolved'],1)

    def test_cost_budget_prevents_call(self):
        out,calls=self.execute([self.row],max_cost=.000001)
        self.assertEqual(calls,0)
        record=read_jsonl(out/'judgments.jsonl')[0]
        self.assertIsNone(record['model_assessed_acceptance'])
        self.assertIn('budget',record['judge_status'])

    def test_objective_failure_is_rejected_without_paid_judge(self):
        self.row['execution_status']='invalid_output'
        out,calls=self.execute([self.row])
        self.assertEqual(calls,0)
        record=read_jsonl(out/'judgments.jsonl')[0]
        self.assertFalse(record['model_assessed_acceptance'])
        self.assertEqual(record['judge_status'],'skipped_objective_failure')

    def test_unknown_failed_call_cost_remains_unknown(self):
        response={'execution_status':'api_error','http_status':429,'cost_usd':None,'latency_s':1.,'output':None}
        other=copy.deepcopy(self.row); other['system']='D'; other['output']['explanation']='Different phrasing.'
        out,calls=self.execute([self.row,other],response=response)
        summary=json.loads((out/'summary.json').read_text())
        self.assertEqual(calls,1)
        self.assertIsNone(summary['estimated_actual_judge_cost_usd'])
        self.assertEqual(summary['unknown_cost_calls'],1)
        self.assertTrue(summary['incomplete'])

    def test_dry_run_makes_no_api_call(self):
        out,calls=self.execute([self.row],live=False)
        self.assertEqual(calls,0)
        self.assertTrue((out/'request_preview.jsonl').exists())
        self.assertFalse((out/'judgments.jsonl').exists())


if __name__=='__main__':
    unittest.main()
