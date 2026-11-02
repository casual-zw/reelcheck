import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import time
from datetime import datetime, timezone

from .contract import apply_gate, validate
from .evaluation import read_jsonl, summarize
from .prompts import messages, public_input
from .providers import call, load_env, load_shell_exports, ENDPOINTS

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def configuration(path):
    config = json.loads(Path(path).read_text())
    for role in ("open", "frontier"):
        entry = config[role]
        if entry["provider"] not in ENDPOINTS:
            raise ValueError("Unsupported provider")
        override = os.environ.get(role.upper()+"_MODEL")
        if not override and (role == "open" or entry["provider"] != config["open"]["provider"]):
            override = os.environ.get(entry["provider"].upper()+"_MODEL")
        if override:
            entry["model"] = override
        if not entry.get("model"):
            raise ValueError(f"Set {role} model ID")
        if not 1 <= entry["max_output_tokens"] <= 16384:
            raise ValueError("max_output_tokens must be between 1 and 16384")
        if not 1 <= entry.get("timeout_s", 60) <= 60:
            raise ValueError("timeout_s must be between 1 and 60")
        price = entry.get("pricing")
        if price is not None and any(not isinstance(price.get(k), (float, int)) or price[k] <= 0 for k in ("input_per_million", "output_per_million")):
            raise ValueError("Pricing must contain positive input_per_million and output_per_million rates")
    return config


def check_data(cases):
    ids = set()
    for c in cases:
        if c["case_id"] in ids:
            raise ValueError("Duplicate case ID")
        ids.add(c["case_id"])
        pids = set()
        for p in c["evidence"]:
            if p["id"] in pids:
                raise ValueError("Duplicate passage ID")
            pids.add(p["id"])
            if hashlib.sha256(p["text"].encode()).hexdigest() != p["sha256"]:
                raise ValueError("Evidence hash mismatch")


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+"\n")


def save_jsonl(path, rows):
    # Replace the complete snapshot atomically; never keep an append handle open
    # across long API calls or external workspace synchronization.
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)


def upper_cost(entry, prompt):
    price = entry.get("pricing")
    if not price:
        raise ValueError("Set verified pricing in config before a budgeted live run; null is deliberately not treated as free")
    # Conservative byte-count approximation plus overhead. Not a billing guarantee.
    input_bound = len(json.dumps(prompt,ensure_ascii=False).encode())+4096
    return (input_bound*price["input_per_million"] + entry["max_output_tokens"]*price["output_per_million"])/1e6


def run(args):
    config = configuration(args.config)
    cases = read_jsonl(args.inputs)
    check_data(cases)
    if args.limit:
        cases = cases[:args.limit]
    systems = args.systems.split(",")
    if not systems or len(set(systems)) != len(systems) or not set(systems) <= {"A","B","C","D"}:
        raise ValueError("Use unique system names from A,B,C,D")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Output directory must be empty; existing measurements will not be overwritten")
    rng = random.Random(args.seed)
    tasks = []
    for case in cases:
        order = systems.copy()
        rng.shuffle(order)
        tasks.extend((case,s) for s in order)
    manifest = {"mode":"live" if args.live else "dry_run_NO_MODEL_RESULTS", "created_at": datetime.now(timezone.utc).isoformat(),
                "config":config, "inputs_sha256":digest(cases), "source_files_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/"reelcheck").glob("*.py"))},
                "case_count":len(cases), "source_group_count":len({c["group_id"] for c in cases}),
                "systems":systems, "seed":args.seed, "max_calls":args.max_calls,
                "max_cost_usd":args.max_cost_usd, "min_interval_s":args.interval,
                "cost_note":"Token-price estimates; cached rates applied when configured, otherwise conservative uncached rates. Unknown costs remain null. Budget reservations use byte-count bounds.",
                "protocol":"One call per system; no repair or retry. D is the fixed-packet checklist baseline. C_no_gate reuses C output and cost. No gold file is read by run."}
    save_json(out/"manifest.json",manifest)
    if not args.live:
        with (out/"request_preview.jsonl").open("w") as f:
            for case,system in tasks:
                f.write(json.dumps({"case_id":case["case_id"],"system":system,"messages":messages(case,system)},ensure_ascii=False)+"\n")
        print(f"Dry run: {len(tasks)} requests prepared; no model calls or performance results. {out}")
        return
    for role in {"frontier" if s == "A" else "open" for s in systems}:
        entry=config[role]
        if not os.environ.get(ENDPOINTS[entry["provider"]][1]):
            raise ValueError(f"Missing credential for {role}; set it in .env")
        upper_cost(entry, [])
    reserved, calls, last_started = 0., 0, 0.
    stop_reason = "completed"
    records = []
    for case,system in tasks:
        entry=config["frontier" if system == "A" else "open"]
        prompt=messages(case,system)
        bound=upper_cost(entry,prompt)
        if calls >= args.max_calls or reserved+bound > args.max_cost_usd:
            stop_reason="call_or_cost_budget_reached"
            break
        delay=args.interval-(time.monotonic()-last_started)
        if delay>0:
            time.sleep(delay)
        last_started=time.monotonic()
        reserved+=bound  # Never release unknown/failed request reservations.
        calls+=1
        started_at=datetime.now(timezone.utc).isoformat()
        result=call(entry,prompt)
        base={"case_id":case["case_id"],"group_id":case["group_id"],"system":system,
              "provider":entry["provider"],"requested_model":entry["model"],"prompt_sha256":digest(prompt),
              "started_at":started_at,"call_index":calls,**result}
        if system == "C":
            ablated=copy.deepcopy(base)
            ablated["system"]="C_no_gate"
            ablated["reused_call_index"]=calls
            records.append(ablated)
            if result["execution_status"] == "completed":
                start=time.monotonic()
                gated=apply_gate(result["output"],case)
                base.update(gated)
                base["latency_s"]+=time.monotonic()-start
        elif result["execution_status"] == "completed":
            errors=validate(result["output"],case)
            if errors:
                base["execution_status"]="invalid_output"
                base["validation_errors"]=errors
        records.append(base)
        save_jsonl(out/"runs.jsonl", records)
        print(f"{case['case_id']} {system}: {base['execution_status']}",flush=True)
        if result.get("http_status") in {401,403,404,429} or result["execution_status"] == "transport_error":
            stop_reason="provider_access_rate_or_transport_error"
            break
    save_jsonl(out/"runs.jsonl", records)
    save_json(out/"completion.json",{"stop_reason":stop_reason,"paid_calls_attempted":calls,"reserved_cost_upper_estimate":reserved,"planned_calls":len(tasks)})


def report(args):
    run_dir=Path(args.run)
    manifest=json.loads((run_dir/"manifest.json").read_text())
    if manifest["mode"] != "live":
        raise ValueError("Dry runs contain no model results and cannot be scored")
    rows=read_jsonl(run_dir/"runs.jsonl")
    cases={c["case_id"]:c for c in read_jsonl(args.inputs)}
    gold={c["case_id"]:c for c in read_jsonl(args.gold)}
    if len(rows) != len({(r["case_id"],r["system"]) for r in rows}):
        raise ValueError("Duplicate run records")
    selected=[c for c in cases.values() if c["case_id"] in {r["case_id"] for r in rows}]
    # Full run input hash is authoritative; partial runs are reported explicitly below.
    all_inputs=list(cases.values())[:manifest["case_count"]]
    if digest(all_inputs) != manifest["inputs_sha256"]:
        raise ValueError("Input file differs from the run manifest")
    reviews={}
    if args.reviews:
        for r in read_jsonl(args.reviews):
            key=(r["case_id"],r["system"])
            if key in reviews:
                raise ValueError("Duplicate review")
            reviews[key]=r
    summary=summarize(rows,cases,gold,reviews)
    summary["planned_cases_per_system"]=manifest["case_count"]
    summary["incomplete_run"]=any(summary["systems"].get(s,{}).get("cases",0) != manifest["case_count"] for s in manifest["systems"])
    summary["gold_sha256"]=digest(gold)
    summary["label_statuses"]=sorted({g.get("label_status","unknown") for g in gold.values()})
    save_json(run_dir/"summary.json",summary)
    with (run_dir/"review_template.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps({"case_id":r["case_id"],"system":r["system"],"label_validated":None,"material_meaning_ok":None,"semantic_support_ok":None,"uncertainty_reason_ok":None,"notes":""})+"\n")
    print(json.dumps(summary,indent=2))


def main():
    p=argparse.ArgumentParser(description="ReelCheck development experiment")
    p.add_argument("--env",default=str(ROOT/".env"))
    p.add_argument("--shell-keys",help="Read only direct credential exports from a named shell config, without executing it")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor")
    smoke=sub.add_parser("smoke")
    smoke.add_argument("--config",default=str(ROOT/"config.example.json"))
    smoke.add_argument("--role",choices=["open","frontier"],required=True)
    runner=sub.add_parser("run")
    runner.add_argument("--config",default=str(ROOT/"config.example.json"))
    runner.add_argument("--inputs",default=str(ROOT/"data/dev_inputs.jsonl"))
    runner.add_argument("--systems",default="A,B,C,D")
    runner.add_argument("--out",required=True)
    runner.add_argument("--live",action="store_true")
    runner.add_argument("--limit",type=int)
    runner.add_argument("--max-calls",type=int,default=64)
    runner.add_argument("--max-cost-usd",type=float,default=1.)
    runner.add_argument("--interval",type=float,default=6.1)
    runner.add_argument("--seed",type=int,default=20261102)
    scorer=sub.add_parser("report")
    scorer.add_argument("--run",required=True)
    scorer.add_argument("--inputs",default=str(ROOT/"data/dev_inputs.jsonl"))
    scorer.add_argument("--gold",default=str(ROOT/"data/dev_gold.jsonl"))
    scorer.add_argument("--reviews")
    args=p.parse_args()
    try:
        load_env(args.env)
        if args.shell_keys:
            load_shell_exports(args.shell_keys)
        if args.command=="doctor":
            print("Python standard library only; no package install required.")
            for _,name in ENDPOINTS.values():
                print(f"{name}: {'present' if os.environ.get(name) else 'not set'}")
            check_data(read_jsonl(ROOT/"data/dev_inputs.jsonl"))
            print("Development inputs: hashes valid; independent human label review pending.")
        elif args.command=="smoke":
            cfg=configuration(args.config)[args.role]
            cfg["max_output_tokens"]=512
            response=call(cfg,[{"role":"system","content":"Return only JSON."},{"role":"user","content":'Return {"ok":true}.'}])
            # Usage and status only, no credential or untrusted response echo.
            print(json.dumps({k:v for k,v in response.items() if k not in {"raw_text","output"}},indent=2))
            if response["execution_status"]!="completed" or response.get("output")!={"ok":True}:
                raise ValueError("Smoke response did not complete with the requested JSON")
        elif args.command=="run":
            if args.max_calls<1 or args.max_cost_usd<=0 or args.interval<0 or (args.limit is not None and args.limit<1):
                raise ValueError("Limits must be positive and interval nonnegative")
            run(args)
        else:
            report(args)
    except (ValueError,KeyError,OSError,json.JSONDecodeError) as e:
        p.exit(2,f"Error: {e}\n")


if __name__=="__main__":
    main()
