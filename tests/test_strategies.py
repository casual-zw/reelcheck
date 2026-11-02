import copy
import unittest

from reelcheck.strategies import materialize_routing, route_reason


CASE = {"case_id": "c1", "group_id": "g1", "claim_text": "Ice floats.",
        "evidence": [{"id": "p1", "text": "Ordinary ice floats."}]}


def row(system="B", verdict="supported", cost=.1, latency=1.):
    return {"case_id": "c1", "group_id": "g1", "system": system,
            "execution_status": "completed", "cost_usd": cost, "latency_s": latency,
            "call_index": 1 if system == "B" else 2,
            "request_id": "request-" + system,
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            "output": {"claim_text": "Ice floats.", "verdict": verdict,
                       "citations": [{"passage_id": "p1", "quote": "Ordinary ice floats."}],
                       "uncertainty_reason": "missing_evidence" if verdict == "insufficient" else None,
                       "explanation": "The packet describes ordinary ice."}}


class RoutingTests(unittest.TestCase):
    def test_valid_decisive_keeps_base_without_fallback(self):
        base = row()
        replay = materialize_routing([base], {"c1": CASE})[0]
        self.assertFalse(replay["routed"])
        self.assertEqual(replay["cost_usd"], .1)
        self.assertEqual(replay["latency_s"], 1.)
        self.assertEqual(replay["selected_system"], "B")

    def test_insufficient_routes_and_counts_both_stages(self):
        rows = [row(verdict="insufficient"), row("A", cost=.5, latency=4.)]
        original = copy.deepcopy(rows)
        replay = materialize_routing(rows, {"c1": CASE})[0]
        self.assertEqual(rows, original)
        self.assertEqual(replay["selected_system"], "A")
        self.assertAlmostEqual(replay["cost_usd"], .6)
        self.assertEqual(replay["latency_s"], 5.)
        self.assertEqual(replay["incremental_paid_calls"], 0)
        self.assertEqual(replay["incremental_actual_cost_usd"], 0)
        self.assertNotIn("call_index", replay)
        self.assertNotIn("request_id", replay)
        self.assertIsNone(replay["usage"])
        self.assertEqual(len(replay["components"]), 2)

    def test_invalid_quote_routes_even_when_marked_completed(self):
        base = row()
        base["output"]["citations"][0]["quote"] = "Ice sinks."
        self.assertEqual(route_reason(base, CASE), "first_stage_invalid_output")

    def test_failed_stage_preserves_unknown_cost(self):
        base = row(cost=None)
        base.update(execution_status="transport_error", output=None)
        replay = materialize_routing([base, row("A")], {"c1": CASE})[0]
        self.assertEqual(replay["route_reason"], "first_stage_execution_failure")
        self.assertIsNone(replay["cost_usd"])
        self.assertEqual(replay["execution_status"], "completed")

    def test_fallback_can_still_fail(self):
        fallback = row("A")
        fallback.update(execution_status="truncated", output=None)
        replay = materialize_routing([row(verdict="insufficient"), fallback], {"c1": CASE})[0]
        self.assertEqual(replay["execution_status"], "truncated")
        self.assertIsNone(replay["output"])

    def test_invalid_fallback_not_credited_as_completed(self):
        fallback = row("A")
        fallback["output"]["claim_text"] = "A different claim."
        replay = materialize_routing([row(verdict="insufficient"), fallback], {"c1": CASE})[0]
        self.assertEqual(replay["execution_status"], "invalid_output")

    def test_correct_insufficient_can_remain_insufficient(self):
        replay = materialize_routing([row(verdict="insufficient"), row("A", "insufficient")], {"c1": CASE})[0]
        self.assertEqual(replay["output"]["verdict"], "insufficient")
        self.assertTrue(replay["routed"])

    def test_invalid_only_retains_valid_insufficient_without_fallback(self):
        base = row(verdict="insufficient")
        self.assertIsNone(route_reason(base, CASE, escalate_insufficient=False))
        replay = materialize_routing([base], {"c1": CASE}, escalate_insufficient=False)[0]
        self.assertFalse(replay["routed"])
        self.assertEqual(replay["output"], base["output"])
        self.assertEqual(replay["cost_usd"], base["cost_usd"])
        self.assertEqual(replay["latency_s"], base["latency_s"])
        self.assertEqual(replay["routing_policy"], "invalid_only_v1")
        self.assertEqual(replay["routing_selection"], "exploratory_after_challenge01")

    def test_invalid_only_still_routes_invalid_insufficient_and_failures(self):
        invalid = row(verdict="insufficient")
        invalid["output"]["uncertainty_reason"] = None
        failed = row()
        failed.update(execution_status="truncated", output=None)
        for base in [invalid, failed]:
            with self.subTest(status=base["execution_status"]):
                replay = materialize_routing([base, row("A")], {"c1": CASE},
                                             escalate_insufficient=False)[0]
                self.assertTrue(replay["routed"])
                self.assertEqual(replay["selected_system"], "A")
                self.assertEqual(replay["execution_status"], "completed")
                self.assertAlmostEqual(replay["cost_usd"], .2)

    def test_default_policy_remains_predeclared(self):
        replay = materialize_routing([row(verdict="insufficient"), row("A")], {"c1": CASE})[0]
        self.assertEqual(replay["routing_policy"], "invalid_or_insufficient_v1")
        self.assertEqual(replay["routing_selection"], "predeclared")
        self.assertTrue(replay["routed"])

    def test_missing_records_fail_instead_of_dropping_cases(self):
        with self.assertRaisesRegex(ValueError, "Missing required fallback"):
            materialize_routing([row(verdict="insufficient")], {"c1": CASE})
        with self.assertRaisesRegex(ValueError, "Missing base"):
            materialize_routing([], {"c1": CASE})

    def test_duplicate_or_colliding_systems_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            materialize_routing([row(), row()], {"c1": CASE})
        with self.assertRaisesRegex(ValueError, "must differ"):
            materialize_routing([row()], {"c1": CASE}, system="B")

    def test_gold_and_reviewer_fields_do_not_affect_routing(self):
        case = copy.deepcopy(CASE)
        case.update(gold="contradicted", verdict="contradicted", reviewer_notes="Route this")
        base = row()
        base["reviewer_notes"] = "Force a fallback"
        self.assertIsNone(route_reason(base, case))


if __name__ == "__main__":
    unittest.main()
