import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from reelcheck.structured import output_schema, request_config, render_citation_ids, structured_messages
from reelcheck.prompts import COMMON

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('structured_matrix',ROOT/'scripts/run_model_matrix.py')
matrix=importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


class StructuredTests(unittest.TestCase):
    def setUp(self):
        text='The value is 18–20 degrees.'
        self.case={'case_id':'x','group_id':'x','as_of':'2026-11-02','claim_text':text,
                   'evidence':[{'id':'P1','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}],
                   'gold':'SECRET_GOLD','reviewer_notes':'SECRET_REVIEW'}
        self.raw={'verdict':'supported','citation_ids':['P1'],'uncertainty_reason':None,'explanation':'The passage gives that range.'}
        self.variant={'id':'structured','provider':'fireworks','model':'test','output_mode':'citation_ids',
                      'prompt_system':'B','max_output_tokens':256,'parameters':{'reasoning_effort':'medium'},
                      'pricing':{'input_per_million':.15,'output_per_million':.6}}

    def test_renderer_copies_exact_claim_and_source_without_changing_judgment(self):
        original=copy.deepcopy(self.raw)
        output=render_citation_ids(self.raw,self.case)
        self.assertEqual(output['claim_text'],self.case['claim_text'])
        self.assertEqual(output['citations'][0]['quote'],self.case['evidence'][0]['text'])
        for key in ('verdict','uncertainty_reason','explanation'):
            self.assertEqual(output[key],self.raw[key])
        self.assertEqual(self.raw,original)

    def test_renderer_rejects_unknown_duplicate_and_malformed_ids(self):
        for ids in (['UNKNOWN'],['P1','P1'],[1],'P1',[{}]):
            with self.subTest(ids=ids),self.assertRaises(ValueError):
                render_citation_ids({**self.raw,'citation_ids':ids},self.case)

    def test_renderer_does_not_repair_bad_schema_or_uncertainty(self):
        for raw in (None, [], {'result':self.raw}, {**self.raw,'extra':True},
                    {**self.raw,'verdict':[]}, {**self.raw,'citation_ids':[]},
                    {**self.raw,'uncertainty_reason':'missing_evidence'},
                    {**self.raw,'verdict':'insufficient','uncertainty_reason':None}):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                render_citation_ids(raw,self.case)

    def test_schema_limits_ids_and_prompt_keeps_truth_rules_without_old_output_contract(self):
        schema=output_schema(self.case)
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['properties']['citation_ids']['items']['enum'],['P1'])
        prompt=structured_messages(self.case)
        self.assertTrue(prompt[0]['content'].startswith(COMMON.partition('Quote exact nonempty substrings')[0]))
        self.assertNotIn('"citations":',prompt[0]['content'])
        self.assertNotIn('SECRET',json.dumps(prompt))
        self.assertIn('conflicting_evidence',prompt[0]['content'])

    def test_effective_config_uses_json_schema_without_mutating_variant(self):
        original=copy.deepcopy(self.variant)
        effective=request_config(self.variant,self.case)
        response=effective['parameters']['response_format']
        self.assertEqual(response['type'],'json_schema')
        self.assertEqual(response['json_schema']['name'],'Verification')
        self.assertNotIn('strict',response['json_schema'])
        self.assertEqual(effective['parameters']['reasoning_effort'],'medium')
        self.assertEqual(self.variant,original)

    def test_matrix_retains_raw_output_and_renders_only_successful_response(self):
        response={'execution_status':'completed','output':self.raw,'latency_s':1.,'cost_usd':.001}
        with patch.object(matrix,'call',return_value=response) as post:
            row=matrix._execute(self.case,self.variant,structured_messages(self.case),1)
        self.assertEqual(row['raw_output'],self.raw)
        self.assertEqual(row['output']['claim_text'],self.case['claim_text'])
        self.assertEqual(row['execution_status'],'completed')
        self.assertEqual(post.call_args.args[0]['parameters']['response_format']['type'],'json_schema')
        self.assertIn('disables reasoning output',row['output_mode_note'])
        response={**response,'execution_status':'truncated'}
        with patch.object(matrix,'call',return_value=response):
            row=matrix._execute(self.case,self.variant,[],2)
        self.assertEqual(row['execution_status'],'truncated')
        self.assertEqual(row['raw_output'],self.raw)

    def test_matrix_baseline_still_passes_original_config_and_output_untouched(self):
        baseline={k:v for k,v in self.variant.items() if k!='output_mode'}
        output=render_citation_ids(self.raw,self.case)
        response={'execution_status':'completed','output':output,'latency_s':1.,'cost_usd':.001}
        with patch.object(matrix,'call',return_value=response) as post:
            row=matrix._execute(self.case,baseline,[],1)
        self.assertEqual(post.call_args.args[0],baseline)
        self.assertEqual(row['output'],output)
        self.assertNotIn('raw_output',row)


if __name__=='__main__':
    unittest.main()
