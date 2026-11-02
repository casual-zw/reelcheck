import copy
import json
from pathlib import Path
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch

from reelcheck.contract import apply_gate, validate
from reelcheck.evaluation import read_jsonl, score, summarize
from reelcheck.prompts import messages
from reelcheck.providers import estimate_cost, load_env, load_shell_exports, call
from reelcheck.__main__ import check_data, upper_cost, run, save_jsonl

ROOT=Path(__file__).resolve().parents[1]


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.case=read_jsonl(ROOT/"data/dev_inputs.jsonl")[0]
        self.gold=read_jsonl(ROOT/"data/dev_gold.jsonl")[0]
        citation={"passage_id":"D1","quote":self.case["evidence"][0]["text"]}
        self.output={"claim_text":self.case["claim_text"],"verdict":"supported",
                     "citations":[citation],"uncertainty_reason":None,"explanation":"The passage states both the approximate density and its variation.",
                     "requirements":[{"id":"R1","text":"Approximate density and variation with temperature and dissolved substances",
                                      "relation":"supports","citations":[citation]}]}

    def test_valid_evidence_map(self):
        self.assertEqual(apply_gate(self.output,self.case)["execution_status"],"completed")

    def test_fabricated_quote_fails_even_with_real_id(self):
        self.output["citations"][0]["quote"]="Water always has exactly the same density."
        self.assertEqual(apply_gate(self.output,self.case)["execution_status"],"invalid_output")

    def test_whitespace_quote_rejected(self):
        self.output["citations"][0]["quote"]=" "
        self.assertTrue(validate(self.output,self.case))

    def test_rendering_whitespace_is_accepted_but_changed_words_are_not(self):
        from reelcheck.contract import citations_errors
        evidence={"P":"Condensation\u00a0is water vapor turning into liquid water."}
        self.assertEqual(citations_errors([{"passage_id":"P","quote":"Condensation is water vapor turning into liquid water."}],evidence),[])
        self.assertTrue(citations_errors([{"passage_id":"P","quote":"Condensation is liquid water turning into water vapor."}],evidence))

    def test_atomic_trace_snapshot_survives_external_path_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"runs.jsonl"
            records=[{"call_index":1}]
            save_jsonl(path,records)
            replacement=Path(tmp)/"external-copy"
            replacement.write_text("")
            replacement.replace(path)
            records.append({"call_index":2})
            save_jsonl(path,records)
            self.assertEqual(read_jsonl(path),records)

    def test_missing_requirement_blocks_support_without_inventing_abstention(self):
        self.output["requirements"].append({"id":"R2","text":"A material qualifier","relation":"missing","citations":[]})
        result=apply_gate(self.output,self.case)
        self.assertEqual(result["execution_status"],"invalid_output")
        self.assertIsNone(result["output"])
        self.assertEqual(self.output["verdict"],"supported")

    def test_contradiction_does_not_require_every_part_be_refuted(self):
        self.output["verdict"]="contradicted"
        self.output["requirements"][0]["relation"]="contradicts"
        self.output["requirements"].append({"id":"R2","text":"Other unestablished part","relation":"missing","citations":[]})
        self.assertEqual(apply_gate(self.output,self.case)["execution_status"],"completed")

    def test_changed_claim_is_invalid(self):
        self.output["claim_text"]="Water is dense."
        self.assertIn("claim text changed or missing",validate(self.output,self.case))

    def test_untrusted_json_shapes_fail_closed(self):
        for broken in [None,[],"supported",{"verdict":[]}, {"verdict":"insufficient","uncertainty_reason":[]}]:
            with self.subTest(broken=broken):
                self.assertTrue(validate(broken,self.case,require_map=True))

    def test_duplicate_requirement_is_invalid(self):
        self.output["requirements"]*=2
        self.assertTrue(validate(self.output,self.case,require_map=True))

    def test_prompt_whitelist_excludes_gold_and_private_metadata(self):
        self.case["gold"]={"verdict":"SECRET_LABEL"}
        self.case["reviewer_notes"]="SECRET_NOTES"
        prompt=json.dumps(messages(self.case,"C"))
        self.assertNotIn("SECRET",prompt)
        self.assertNotIn("group_id",prompt)

    def test_proxy_is_never_presented_as_human_grounded_success(self):
        row={"execution_status":"completed","output":self.output}
        s=score(row,self.case,self.gold)
        self.assertTrue(s["automated_proxy_success"])
        self.assertIsNone(s["reviewed_grounded_success"])
        review={"label_validated":True,"material_meaning_ok":True,"semantic_support_ok":False,"uncertainty_reason_ok":True}
        self.assertFalse(score(row,self.case,self.gold,review)["reviewed_grounded_success"])

    def test_abstaining_on_answerable_case_cannot_win(self):
        self.output.update(verdict="insufficient",uncertainty_reason="missing_evidence",citations=[])
        s=score({"execution_status":"completed","output":self.output},self.case,self.gold)
        self.assertFalse(s["automated_proxy_success"])
        self.assertTrue(s["unnecessary_abstention"])

    def test_predeclared_reason_alternatives_do_not_relax_verdict(self):
        self.gold.update(verdict="insufficient", uncertainty_reason="missing_evidence",
                         acceptable_uncertainty_reasons=["missing_evidence", "missing_context"],
                         acceptable_evidence_sets=[[]])
        self.output.update(verdict="insufficient", uncertainty_reason="missing_context", citations=[])
        row={"execution_status":"completed", "output":self.output}
        self.assertTrue(score(row,self.case,self.gold)["automated_proxy_success"])
        self.output["uncertainty_reason"]="conflicting_evidence"
        self.assertFalse(score(row,self.case,self.gold)["automated_proxy_success"])
        self.assertTrue(score(row,self.case,self.gold)["verdict_correct"])

    def test_failed_requests_remain_in_denominator_and_cost_not_free(self):
        rows=[{"case_id":self.case["case_id"],"system":"B","execution_status":"api_error","output":None,"latency_s":5.,"cost_usd":None}]
        summary=summarize(rows,{self.case["case_id"]:self.case},{self.gold["case_id"]:self.gold})["systems"]["B"]
        self.assertEqual(summary["cases"],1)
        self.assertEqual(summary["automated_proxy_successes"],0)
        self.assertIsNone(summary["estimated_total_cost_usd"])

    def test_reasoning_tokens_not_double_counted(self):
        usage={"prompt_tokens":1000,"completion_tokens":200,"completion_tokens_details":{"reasoning_tokens":150}}
        self.assertAlmostEqual(estimate_cost(usage,"fireworks",{"input_per_million":1,"output_per_million":2}),.0014)

    def test_missing_prices_cannot_mean_zero_cost(self):
        self.assertIsNone(estimate_cost({"prompt_tokens":5},"fireworks",None))
        with self.assertRaises(ValueError):
            upper_cost({"pricing":None},[])

    def test_cached_input_discount_and_reasoning_total(self):
        usage={"prompt_tokens":1000,"completion_tokens":200,"prompt_tokens_details":{"cached_tokens":800}}
        self.assertAlmostEqual(estimate_cost(usage,"fireworks",{"input_per_million":1,"cached_input_per_million":.1,"output_per_million":2}),.00068)

    def test_shell_key_loader_does_not_execute_or_import_other_variables(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict("os.environ",{},clear=True):
            path=Path(tmp)/".zshrc"
            path.write_text("export FIREWORKS_API_KEY=test-key\nexport UNRELATED=not-imported\necho do-not-execute\n")
            load_shell_exports(path)
            import os
            self.assertEqual(os.environ["FIREWORKS_API_KEY"],"test-key")
            self.assertNotIn("UNRELATED",os.environ)

    def test_end_to_end_runner_reuses_C_call_for_ablation(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=Namespace(config=str(ROOT/"config.fireworks.json"),inputs=str(ROOT/"data/dev_inputs.jsonl"),
                           limit=1,systems="B,C,D",out=str(Path(tmp)/"run"),seed=42,live=True,
                           max_calls=3,max_cost_usd=.1,interval=0)
            response={"execution_status":"completed","output":self.output,"raw_text":json.dumps(self.output),
                      "usage":{"prompt_tokens":100,"completion_tokens":100},"latency_s":.5,"cost_usd":.0001}
            with patch.dict("os.environ",{"FIREWORKS_API_KEY":"FAKE"}),patch("reelcheck.__main__.call",return_value=response) as provider:
                run(args)
            rows=read_jsonl(Path(args.out)/"runs.jsonl")
            self.assertEqual(provider.call_count,3)
            self.assertEqual(len(rows),4)
            gated=next(r for r in rows if r["system"]=="C")
            ungated=next(r for r in rows if r["system"]=="C_no_gate")
            self.assertEqual(gated["call_index"],ungated["reused_call_index"])
            self.assertEqual(gated["cost_usd"],ungated["cost_usd"])
            self.assertNotIn("gold",json.dumps(provider.call_args_list))

    def test_all_passages_integrity_and_expected_label_mix(self):
        cases=read_jsonl(ROOT/"data/dev_inputs.jsonl")
        labels=read_jsonl(ROOT/"data/dev_gold.jsonl")
        check_data(cases)
        self.assertEqual(len(cases),16)
        self.assertEqual([sum(g["verdict"]==v for g in labels) for v in ["supported","contradicted","insufficient"]],[6,6,4])
        self.assertEqual(len({c["group_id"] for c in cases}),4)
        changed=copy.deepcopy(cases)
        changed[0]["evidence"][0]["text"]+="changed"
        with self.assertRaises(ValueError):
            check_data(changed)

    def test_env_is_data_not_executable_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/".env"
            path.write_text("REELCHECK_TEST_VALUE='$(touch /tmp/should-not-run)'\n")
            with patch.dict("os.environ",{},clear=True):
                load_env(path)
                import os
                self.assertEqual(os.environ["REELCHECK_TEST_VALUE"],"$(touch /tmp/should-not-run)")

    def test_provider_parses_response_and_never_persists_authorization(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return json.dumps({"choices":[{"message":{"content":'{"ok":true}'},"finish_reason":"stop"}],"usage":{"prompt_tokens":12,"completion_tokens":4}}).encode()
        with patch.dict("os.environ",{"FIREWORKS_API_KEY":"TEST-SECRET"}),patch("urllib.request.urlopen",return_value=FakeResponse()) as post:
            result=call({"provider":"fireworks","model":"test","max_output_tokens":32},messages(self.case,"B"))
            self.assertEqual(result["output"],{"ok":True})
            self.assertNotIn("TEST-SECRET",json.dumps(result))
            self.assertEqual(post.call_args.args[0].full_url,"https://api.fireworks.ai/inference/v1/chat/completions")


if __name__=="__main__":
    unittest.main()
