"""Gold-blind routing replay; this does not make API calls.

The policy sends invalid/failed or insufficient first-stage responses to an
independent stronger-model response. A confident but wrong first-stage answer
will not be caught. Replay estimates a sequential deployment's token cost and
service latency; it does not measure live routing overhead, cache effects, or
request contention. Never sum these rows into the experiment's actual spend:
their component calls have already been paid for in the original run.

The default invalid-or-insufficient policy was predeclared. The optional
invalid-only variant was selected after challenge01 results: it is exploratory,
not a predeclared confirmatory comparison, and needs fresh evaluation.
"""
from copy import deepcopy

from .contract import validate


POLICY_VERSION = "invalid_or_insufficient_v1"


def route_reason(row, case, *, escalate_insufficient=True):
    """Return a deterministic escalation reason, or None, without reading gold."""
    if row["execution_status"] != "completed":
        return "first_stage_execution_failure"
    if validate(row.get("output"), case):
        return "first_stage_invalid_output"
    if escalate_insufficient and row["output"]["verdict"] == "insufficient":
        return "first_stage_insufficient"
    return None


def _sum_known(values):
    return sum(values) if all(value is not None for value in values) else None


def materialize_routing(rows, cases, *, base_system="B", fallback_system="A", system="R",
                        escalate_insufficient=True):
    """Create evaluator-compatible replay rows from paired first/reference calls.

    `cases` is the case_id -> input dictionary used by evaluation.summarize.
    Exactly one base row per case is required. A fallback row is required only
    when the policy escalates. Missing or duplicate records fail explicitly;
    incomplete inputs are not silently excluded. The fallback receives the same
    original evidence packet, not the first-stage response. Optional alternate
    base systems (e.g. D) must be declared before examining their outcomes.

    `cost_usd` includes BOTH stages when routed. `latency_s` is their sequential
    sum, a replay estimate rather than a live end-to-end measurement. Additional
    paid calls and additional actual API spend for materialization are zero.
    `escalate_insufficient=False` retains valid insufficient answers and routes
    failures only. This variant was selected after challenge01 results and is
    exploratory; its apparent improvement must be tested on fresh cases.
    """
    if len({base_system, fallback_system, system}) != 3:
        raise ValueError("Base, fallback, and replay system names must differ")
    indexed = {}
    for row in rows:
        key = (row["case_id"], row["system"])
        if key in indexed:
            raise ValueError(f"Duplicate run record: {key}")
        indexed[key] = row
    results = []
    for case_id, case in cases.items():
        base = indexed.get((case_id, base_system))
        if base is None:
            raise ValueError(f"Missing base record for {case_id}")
        reason = route_reason(base, case, escalate_insufficient=escalate_insufficient)
        components = [base]
        selected = base
        if reason:
            selected = indexed.get((case_id, fallback_system))
            if selected is None:
                raise ValueError(f"Missing required fallback record for {case_id}")
            components.append(selected)
        result = deepcopy(selected)
        result.update({
            "system": system,
            "started_at": base.get("started_at"),
            "cost_usd": _sum_known([row.get("cost_usd") for row in components]),
            "latency_s": _sum_known([row.get("latency_s") for row in components]),
            "usage": None,  # Per-component usage cannot describe the whole pipeline.
            "routing_policy": POLICY_VERSION if escalate_insufficient else "invalid_only_v1",
            "routing_selection": "predeclared" if escalate_insufficient else "exploratory_after_challenge01",
            "route_reason": reason,
            "routed": bool(reason),
            "selected_system": selected["system"],
            "replay_only": True,
            "incremental_paid_calls": 0,
            "incremental_actual_cost_usd": 0.0,
            "cost_basis": "hypothetical sequential cost of reused component calls",
            "latency_basis": "sum of recorded service latencies; excludes live routing overhead",
            "components": [{
                "system": row["system"],
                "call_index": row.get("call_index"),
                "request_id": row.get("request_id"),
                "requested_model": row.get("requested_model"),
                "execution_status": row["execution_status"],
                "cost_usd": row.get("cost_usd"),
                "latency_s": row.get("latency_s"),
                "usage": deepcopy(row.get("usage")),
            } for row in components],
        })
        # A reused request is not a new paid call index or a single provider request.
        for key in ("call_index", "request_id", "reused_call_index"):
            result.pop(key, None)
        if result["execution_status"] == "completed":
            errors = validate(result.get("output"), case)
            if errors:
                result["execution_status"] = "invalid_output"
                result["validation_errors"] = errors
        results.append(result)
    return results
