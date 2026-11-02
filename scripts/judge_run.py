"""Optional pointwise LLM judge. Dry run by default; model scores are not labels."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reelcheck.__main__ import check_data, digest, save_json, save_jsonl, upper_cost
from reelcheck.evaluation import read_jsonl
from reelcheck.judge import (RUBRIC_VERSION, assess_judgment, judge_messages,
                            objective_errors, summarize_judgments)
from reelcheck.providers import call, load_env, load_shell_exports


def judge_config(path, role):
    config = json.loads(Path(path).read_text())
    selected = role or ("judge" if "judge" in config else "frontier")
    entry = config[selected]
    if entry.get("provider") != "fireworks":
        raise ValueError("This judge runner uses Fireworks only")
    if not isinstance(entry.get("model"), str) or not entry["model"]:
        raise ValueError("Judge model must be explicitly configured")
    if not 1 <= entry.get("max_output_tokens", 0) <= 16384 or not 1 <= entry.get("timeout_s",60) <= 60:
        raise ValueError("Invalid judge output limit or timeout")
    price = entry.get("pricing")
    if not price or any(type(price.get(k)) not in (float,int) or price[k] <= 0 for k in ("input_per_million", "output_per_million")):
        raise ValueError("Verified positive pricing is required for judge cost accounting")
    return entry, selected


def run_judge(args):
    if args.max_calls < 1 or args.max_cost_usd <= 0 or args.interval < 0:
        raise ValueError("Positive limits and a nonnegative interval are required")
    entry, role = judge_config(args.config, args.role)
    cases_list = read_jsonl(args.inputs)
    check_data(cases_list)
    cases = {c["case_id"]: c for c in cases_list}
    source = Path(args.run)
    rows = read_jsonl(source/"runs.jsonl" if source.is_dir() else source)
    verified_inputs = False
    if source.is_dir() and (source/'manifest.json').exists():
        source_manifest = json.loads((source/'manifest.json').read_text())
        expected_hash = source_manifest.get('inputs_sha256')
        count = source_manifest.get('case_count',len(cases_list))
        if expected_hash:
            if digest(cases_list[:count]) != expected_hash:
                raise ValueError('Judge inputs differ from the candidate run manifest')
            verified_inputs = True
    elif source.is_dir() and (source/'summary.json').exists():
        source_summary = json.loads((source/'summary.json').read_text())
        expected_hash = source_summary.get('input_sha256')
        if expected_hash:
            if digest(cases_list) != expected_hash:
                raise ValueError('Judge inputs differ from the candidate run summary')
            verified_inputs = True
    if args.systems:
        wanted = set(args.systems.split(","))
        rows = [r for r in rows if r["system"] in wanted]
        if wanted - {r["system"] for r in rows}:
            raise ValueError("Requested systems missing from run")
    if not rows or len({(r["case_id"],r["system"]) for r in rows}) != len(rows):
        raise ValueError("Input run must have nonempty unique case/system records")
    if any(r["case_id"] not in cases for r in rows):
        raise ValueError("Run references a case absent from inputs")
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use an empty output directory; judge results are never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"mode": "live" if args.live else "dry_run_NO_JUDGE_RESULTS", "created_at": datetime.now(timezone.utc).isoformat(),
        "rubric_version": RUBRIC_VERSION, "judge_config": entry, "config_role": role,
        "inputs_sha256": digest(cases_list), "candidate_rows_sha256": digest(rows), "candidate_count": len(rows),
        "inputs_verified_against_candidate_run": verified_inputs,
        "source_files_sha256": {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/"reelcheck/judge.py",Path(__file__))},
        "max_calls": args.max_calls, "max_cost_usd": args.max_cost_usd, "interval_s": args.interval,
        "protocol": "Blinded pointwise assessment; no gold labels; one call per unique valid candidate payload; no retry. Exact duplicate payloads reuse judgment and incur zero additional cost. Objective failures are rejected without a judge call. All candidate rows remain in denominators."}
    save_json(out/"manifest.json",manifest)
    if not args.live:
        seen = set()
        previews = []
        for row in rows:
            errors = objective_errors(row,cases[row["case_id"]])
            prompt = judge_messages(cases[row["case_id"]],row)
            key = digest(prompt)
            previews.append({"case_id":row["case_id"],"system":row["system"],"objective_errors":errors,
                "would_reuse":key in seen and not errors,"would_call":not errors and key not in seen,"messages":prompt})
            if not errors:
                seen.add(key)
        save_jsonl(out/"request_preview.jsonl",previews)
        print(f"Dry run: {len(rows)} candidate rows; {len(seen)} unique eligible judge requests. No API calls.")
        return
    load_env(args.env)
    if args.shell_keys:
        load_shell_exports(args.shell_keys)
    if not os.environ.get("FIREWORKS_API_KEY"):
        raise ValueError("FIREWORKS_API_KEY is required; do not paste it in chat")
    records, cache = [], {}
    paid_calls, reserved, last_started = 0, 0., 0.
    stop_reason = None
    for row in rows:
        case = cases[row["case_id"]]
        errors = objective_errors(row,case)
        prompt = judge_messages(case,row)
        key = digest(prompt)
        record = {"case_id":row["case_id"],"system":row["system"],"rubric_version":RUBRIC_VERSION,
            "judge_model":entry["model"],"candidate_model":row.get("requested_model"),
            "same_model_as_candidate":entry["model"] == row.get("requested_model"),
            "prompt_sha256":key,"objective_errors":errors,"paid_judge_call":False,
            "cost_usd":0.,"model_assessed_acceptance":None,"requires_review":True,
            "human_reviewed_grounded_success":None}
        if errors:
            record.update(judge_status="skipped_objective_failure",model_assessed_acceptance=False)
        elif key in cache:
            previous = cache[key]
            record.update(copy.deepcopy(previous))
            record.update(case_id=row["case_id"],system=row["system"],candidate_model=row.get("requested_model"),
                same_model_as_candidate=entry["model"] == row.get("requested_model"),
                paid_judge_call=False,cost_usd=0.,reused_judge_call_index=previous["judge_call_index"],
                reused_judge_cost_usd=previous.get("cost_usd"),reused_judge_status=previous["judge_status"])
            record["judge_status"] = "reused"
            record.pop("judge_call_index",None)
        else:
            bound = upper_cost(entry,prompt)
            if stop_reason or paid_calls >= args.max_calls or reserved+bound > args.max_cost_usd:
                stop_reason = stop_reason or "call_or_cost_budget_reached"
                record["judge_status"] = "not_judged_"+stop_reason
            else:
                delay = args.interval-(time.monotonic()-last_started)
                if delay > 0:
                    time.sleep(delay)
                last_started = time.monotonic()
                paid_calls += 1
                reserved += bound
                started_at = datetime.now(timezone.utc).isoformat()
                try:
                    result = call(entry,prompt)
                except (ValueError, TypeError, KeyError):
                    # Retain the attempted call and its unknown cost. Never log an
                    # untrusted exception which may contain echoed response data.
                    result = {"execution_status":"protocol_error","output":None,
                              "latency_s":time.monotonic()-last_started,"usage":None,"cost_usd":None}
                record.update(judge_call_index=paid_calls,paid_judge_call=True,judge_response=result,
                    cost_usd=result.get("cost_usd"),latency_s=result.get("latency_s"),usage=result.get("usage"),
                    started_at=started_at)
                record["judge_status"] = result["execution_status"]
                if result["execution_status"] == "completed":
                    record.update(assess_judgment(result.get("output"),row,case))
                    if record["judge_validation_errors"]:
                        record["judge_status"] = "invalid_judge_output"
                if result.get("http_status") in {401,403,404,429} or result["execution_status"] == "transport_error":
                    stop_reason = "provider_access_rate_or_transport_error"
                cache[key] = copy.deepcopy(record)
        records.append(record)
        save_jsonl(out/"judgments.jsonl",records)
        print(f"{row['case_id']} {row['system']}: {record['judge_status']}",flush=True)
    summary = summarize_judgments(records)
    summary.update(stop_reason=stop_reason or "completed", reserved_cost_upper_estimate=reserved,
                   planned_candidate_rows=len(rows), incomplete=any(r["judge_status"].startswith("not_judged_") for r in records))
    save_json(out/"summary.json",summary)
    print(json.dumps(summary,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True,help='Run directory containing runs.jsonl, or a JSONL file')
    p.add_argument('--inputs',required=True)
    p.add_argument('--config',default=str(ROOT/'config.fireworks.json'))
    p.add_argument('--role',help='Config role; defaults to judge when present, otherwise frontier')
    p.add_argument('--systems',help='Optional comma-separated systems')
    p.add_argument('--out',required=True)
    p.add_argument('--live',action='store_true')
    p.add_argument('--max-calls',type=int,default=40)
    p.add_argument('--max-cost-usd',type=float,default=2.)
    p.add_argument('--interval',type=float,default=1.)
    p.add_argument('--env',default=str(ROOT/'.env'))
    p.add_argument('--shell-keys',help='Read direct key exports from this file without executing it')
    args=p.parse_args()
    try:
        run_judge(args)
    except (ValueError,KeyError,OSError,json.JSONDecodeError) as exc:
        p.exit(2,f'Error: {exc}\n')


if __name__=='__main__':
    main()
