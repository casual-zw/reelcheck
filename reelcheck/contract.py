"""Structural checks only: quotation validity is not semantic entailment."""
from copy import deepcopy

VERDICTS = {"supported", "contradicted", "insufficient"}
RELATIONS = {"supports", "contradicts", "missing", "conflicting"}
REASONS = {"missing_evidence", "conflicting_evidence", "missing_context", "stale_evidence"}


def canonical_whitespace(text):
    """Ignore rendering-only whitespace; never normalize words, numbers or symbols."""
    return " ".join(text.split())


def citations_errors(citations, evidence):
    errors = []
    if not isinstance(citations, list):
        return ["citations must be a list"]
    for c in citations:
        if not isinstance(c, dict):
            errors.append("citation must be an object")
            continue
        pid, quote = c.get("passage_id"), c.get("quote")
        if not isinstance(pid, str) or pid not in evidence:
            errors.append("unknown passage ID")
        elif not isinstance(quote, str) or not quote.strip() or canonical_whitespace(quote) not in canonical_whitespace(evidence[pid]):
            errors.append(f"invalid exact quote for {pid}")
    return errors


def validate(output, case, require_map=False):
    errors = []
    if not isinstance(output, dict):
        return ["output must be an object"]
    evidence = {p["id"]: p["text"] for p in case["evidence"]}
    if output.get("claim_text") != case["claim_text"]:
        errors.append("claim text changed or missing")
    verdict = output.get("verdict")
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        errors.append("invalid verdict")
    if not isinstance(output.get("explanation"), str) or not output["explanation"].strip():
        errors.append("missing explanation")
    errors += citations_errors(output.get("citations"), evidence)
    if verdict in ("supported", "contradicted") and not output.get("citations"):
        errors.append("decisive verdict has no citation")
    reason = output.get("uncertainty_reason")
    if verdict == "insufficient" and (not isinstance(reason, str) or reason not in REASONS):
        errors.append("insufficient verdict requires a specific reason")
    if verdict in ("supported", "contradicted") and output.get("uncertainty_reason") is not None:
        errors.append("decisive verdict must not have an uncertainty reason")
    if not require_map:
        return errors
    requirements = output.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        return errors + ["missing requirement map"]
    ids, mapped_citations, relations = set(), set(), []
    for r in requirements:
        if not isinstance(r, dict):
            errors.append("requirement must be an object")
            continue
        rid = r.get("id")
        if not isinstance(rid, str) or not rid or rid in ids:
            errors.append("invalid or duplicate requirement ID")
        else:
            ids.add(rid)
        if not isinstance(r.get("text"), str) or not r["text"].strip():
            errors.append("empty requirement")
        relation = r.get("relation")
        if not isinstance(relation, str) or relation not in RELATIONS:
            errors.append("invalid requirement relation")
        relations.append(relation)
        refs = r.get("citations")
        errors += citations_errors(refs, evidence)
        if relation in ("supports", "contradicts", "conflicting") and not refs:
            errors.append("claimed evidence relation lacks citations")
        if relation == "missing" and refs:
            errors.append("missing requirement must not claim evidence")
        if isinstance(refs, list):
            mapped_citations.update(c["passage_id"] for c in refs if isinstance(c, dict) and isinstance(c.get("passage_id"), str))
    if verdict == "supported" and any(r != "supports" for r in relations):
        errors.append("support requires coverage of every declared requirement")
    if verdict == "contradicted" and "contradicts" not in relations:
        errors.append("contradiction requires a mapped counterexample")
    if verdict == "insufficient" and all(r == "supports" for r in relations):
        errors.append("insufficiency conflicts with fully supported map")
    top_refs = output.get("citations")
    if isinstance(top_refs, list):
        top_ids = {c.get("passage_id") for c in top_refs if isinstance(c, dict) and isinstance(c.get("passage_id"), str)}
        if not mapped_citations.issubset(top_ids):
            errors.append("mapped citations missing from verdict citations")
    return errors


def apply_gate(output, case):
    errors = validate(output, case, require_map=True)
    # Invalid structure is an execution failure, not epistemic uncertainty.
    return {"execution_status": "invalid_output" if errors else "completed",
            "output": deepcopy(output) if not errors else None,
            "gate_errors": errors}
