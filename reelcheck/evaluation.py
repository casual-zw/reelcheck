"""Automated proxies are intentionally distinct from reviewed grounded success."""
import collections
import json
import math
import statistics
from .contract import validate


def score(row, case, gold, review=None):
    output = row.get("output")
    schema_errors = validate(output, case) if row["execution_status"] == "completed" else [row["execution_status"]]
    correct = isinstance(output, dict) and output.get("verdict") == gold["verdict"]
    cited = set()
    if isinstance(output, dict) and isinstance(output.get("citations"), list):
        cited = {c.get("passage_id") for c in output["citations"] if isinstance(c, dict) and isinstance(c.get("passage_id"), str)}
    evidence_match = any(set(ids).issubset(cited) for ids in gold["acceptable_evidence_sets"])
    accepted_reasons = gold.get("acceptable_uncertainty_reasons", [gold["uncertainty_reason"]])
    reason_ok = gold["verdict"] != "insufficient" or (isinstance(output, dict) and output.get("uncertainty_reason") in accepted_reasons)
    proxy = bool(not schema_errors and correct and evidence_match and reason_ok)
    reviewed = None
    if review and all(isinstance(review.get(k), bool) for k in ("label_validated", "material_meaning_ok", "semantic_support_ok", "uncertainty_reason_ok")):
        reviewed = bool(not schema_errors and correct and all(review[k] for k in ("label_validated", "material_meaning_ok", "semantic_support_ok", "uncertainty_reason_ok")))
    verdict = output.get("verdict") if isinstance(output, dict) else None
    decisive = not schema_errors and verdict in ("supported", "contradicted")
    return {"automated_proxy_success": proxy, "reviewed_grounded_success": reviewed,
            "verdict_correct": bool(not schema_errors and correct),
            "uncertainty_reason_accepted": reason_ok,
            "wrong_decisive": bool(decisive and not correct),
            "correct_insufficient": bool(not schema_errors and correct and verdict == "insufficient"),
            "unnecessary_abstention": bool(not schema_errors and verdict == "insufficient" and gold["verdict"] != "insufficient"),
            "answerable": gold["verdict"] != "insufficient", "decisive": bool(decisive),
            "schema_errors": schema_errors}


def summarize(rows, cases, gold, reviews=None):
    reviews = reviews or {}
    groups = collections.defaultdict(list)
    for row in rows:
        key = (row["case_id"], row["system"])
        groups[row["system"]].append((row, score(row, cases[row["case_id"]], gold[row["case_id"]], reviews.get(key))))
    result = {"warning": "Development experiment only. Automated evidence-ID matching is a proxy, not semantic verification. Related source and fixture cases do not support independent-sample statistical claims.", "systems": {}}
    for system, pairs in sorted(groups.items()):
        n = len(pairs)
        scores = [s for _,s in pairs]
        proxy = sum(s["automated_proxy_success"] for s in scores)
        reviewed_count = sum(s["reviewed_grounded_success"] is not None for s in scores)
        success = sum(s["reviewed_grounded_success"] is True for s in scores) if reviewed_count == n else None
        costs = [r.get("cost_usd") for r,_ in pairs]
        total_cost = sum(costs) if all(c is not None for c in costs) else None
        latency = sorted(r["latency_s"] for r,_ in pairs)
        answerable = sum(s["answerable"] for s in scores)
        result["systems"][system] = {
            "cases": n, "completed": sum(r["execution_status"] == "completed" for r,_ in pairs),
            "verdict_correct": sum(s["verdict_correct"] for s in scores),
            "automated_proxy_successes": proxy, "human_reviewed_cases": reviewed_count,
            "reviewed_grounded_successes": success,
            "wrong_decisive_verdicts": sum(s["wrong_decisive"] for s in scores),
            "correct_insufficient": sum(s["correct_insufficient"] for s in scores),
            "unnecessary_abstentions": sum(s["unnecessary_abstention"] for s in scores),
            "answerable_cases": answerable,
            "decisive_coverage_on_answerable": sum(s["answerable"] and s["decisive"] for s in scores)/answerable if answerable else None,
            "p50_latency_s": statistics.median(latency), "p95_latency_s": latency[max(0, math.ceil(.95*n)-1)],
            "estimated_total_cost_usd": total_cost, "unknown_cost_cases": sum(c is None for c in costs),
            "estimated_cost_per_proxy_success": total_cost/proxy if total_cost is not None and proxy else None,
            "estimated_cost_per_reviewed_grounded_success": total_cost/success if total_cost is not None and success else None,
            "paired_reuse_note": "Same C response and usage; not an additional paid call." if system == "C_no_gate" else None,
        }
    # Paired case-level differences, without pretending source-correlated rows are independent.
    by_key = {(r["case_id"],r["system"]): s for pairs in groups.values() for r,s in pairs}
    result["paired_proxy_counts"] = {}
    for other in ("A", "B", "D", "C_no_gate"):
        shared = [cid for cid in cases if (cid,"C") in by_key and (cid,other) in by_key]
        result["paired_proxy_counts"][f"C_vs_{other}"] = {
            "paired_cases":len(shared),
            "C_only_success":sum(by_key[(c,"C")]["automated_proxy_success"] and not by_key[(c,other)]["automated_proxy_success"] for c in shared),
            "other_only_success":sum(not by_key[(c,"C")]["automated_proxy_success"] and by_key[(c,other)]["automated_proxy_success"] for c in shared)}
    return result


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]
