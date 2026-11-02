"""Compare configured Fireworks models with bounded concurrency and spend.

This runner never reads gold labels and reports operational measurements only.
All API calls are single attempts. Quality assessment is a separate judge/review step.
"""
import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reelcheck.__main__ import check_data, digest, save_json, save_jsonl, upper_cost
from reelcheck.contract import validate
from reelcheck.evaluation import read_jsonl
from reelcheck.prompts import messages
from reelcheck.providers import call, load_shell_exports
from reelcheck.structured import MODE, MODE_NOTE, structured_messages, request_config, render_citation_ids


def validate_config(config):
    variants = config.get('variants')
    if not isinstance(variants, list) or not variants:
        raise ValueError('Config needs a nonempty variants list')
    ids = set()
    for v in variants:
        vid = v.get('id')
        if not isinstance(vid, str) or not vid or vid in ids:
            raise ValueError('Variant IDs must be nonempty and unique')
        ids.add(vid)
        if v.get('provider') != 'fireworks' or not isinstance(v.get('model'), str) or not v['model']:
            raise ValueError('Every variant needs provider=fireworks and a model ID')
        if v.get('prompt_system', 'B') not in {'A', 'B', 'C', 'D'}:
            raise ValueError('prompt_system must be A, B, C, or D')
        if not 1 <= v.get('max_output_tokens', 0) <= 16384:
            raise ValueError('max_output_tokens must be 1..16384')
        if not 1 <= v.get('timeout_s', 60) <= 60:
            raise ValueError('timeout_s must be 1..60')
        price = v.get('pricing') or {}
        for key in ('input_per_million', 'output_per_million'):
            value = price.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('Verified positive input/output pricing is required')
        if not isinstance(v.get('parameters', {}), dict):
            raise ValueError('parameters must be an object')
        if v.get('output_mode', 'verbatim_quotes') not in {'verbatim_quotes', MODE}:
            raise ValueError('output_mode must be verbatim_quotes or citation_ids')
        if v.get('output_mode') == MODE:
            if v.get('prompt_system', 'B') == 'C':
                raise ValueError('citation_ids mode does not include requirement maps')
            if 'response_format' in v.get('parameters', {}):
                raise ValueError('citation_ids mode owns response_format')
    return variants


def _execute(case, variant, prompt, index):
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc).isoformat()
    structured = variant.get('output_mode') == MODE
    effective = request_config(variant, case) if structured else variant
    try:
        result = call(effective, prompt)
    except Exception:
        # A provider-library failure must not lose an attempted call or echo secrets.
        result = {'execution_status': 'runner_error', 'output': None, 'usage': None,
                  'cost_usd': None, 'latency_s': time.monotonic() - started}
    row = {'case_id': case['case_id'], 'group_id': case.get('group_id', case['case_id']),
           'system': variant['id'], 'provider': variant['provider'],
           'requested_model': variant['model'], 'prompt_system': variant.get('prompt_system', 'B'),
           'prompt_sha256': digest(prompt), 'call_index': index, 'started_at': timestamp, **result}
    if structured:
        row.update(output_mode=MODE, output_mode_note=MODE_NOTE,
                   request_parameters=effective['parameters'], raw_output=result.get('output'))
        if row['execution_status'] == 'completed':
            try:
                row['output'] = render_citation_ids(row['raw_output'], case)
            except ValueError as exc:
                row['execution_status'] = 'invalid_output'
                row['validation_errors'] = [str(exc)]
                row['output'] = None
    if row['execution_status'] == 'completed':
        errors = validate(row.get('output'), case, require_map=variant.get('prompt_system') == 'C')
        if errors:
            row['execution_status'] = 'invalid_output'
            row['validation_errors'] = errors
    return row


def operational_summary(rows, variants, planned_cases):
    systems = {}
    for variant in variants:
        part = [r for r in rows if r['system'] == variant['id']]
        times = sorted(r['latency_s'] for r in part)
        costs = [r.get('cost_usd') for r in part]
        systems[variant['id']] = {
            'planned_cases': planned_cases, 'attempted': len(part),
            'schema_valid_completed': sum(r['execution_status'] == 'completed' for r in part),
            'status_counts': dict(Counter(r['execution_status'] for r in part)),
            'incomplete': len(part) != planned_cases,
            'p50_latency_s': statistics.median(times) if times else None,
            'p95_latency_s': times[math.ceil(.95 * len(times)) - 1] if times else None,
            'estimated_total_cost_usd': sum(costs) if costs and all(c is not None for c in costs) else None,
            'known_cost_subtotal_usd': sum(c for c in costs if c is not None),
            'unknown_cost_calls': sum(c is None for c in costs),
        }
    costs = [r.get('cost_usd') for r in rows]
    return {'warning': 'Operational measurements only. Schema-valid output is not factual correctness; no quality score is computed.',
            'systems': systems, 'paid_calls_attempted': len(rows),
            'estimated_actual_run_cost_usd': sum(costs) if costs and all(c is not None for c in costs) else None,
            'known_cost_subtotal_usd': sum(c for c in costs if c is not None),
            'unknown_cost_calls': sum(c is None for c in costs)}


def run_matrix(args):
    if not 1 <= args.workers <= 2 or args.max_calls < 1 or not math.isfinite(args.max_cost_usd) or args.max_cost_usd <= 0:
        raise ValueError('Use 1..2 workers, positive max_calls, and a finite positive cost cap')
    config = json.loads(Path(args.config).read_text())
    variants = validate_config(config)
    cases = read_jsonl(args.inputs)
    if not cases:
        raise ValueError('Inputs must contain at least one case')
    check_data(cases)
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty')
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    tasks = []
    for case in cases:
        order = list(variants)
        rng.shuffle(order)
        for variant in order:
            if variant.get('output_mode') == MODE:
                prompt = structured_messages(case, variant.get('prompt_system', 'B'))
                effective = request_config(variant, case)
                # Account conservatively for the schema's input bytes as well.
                budget_prompt = prompt + [{'role':'system', 'content':json.dumps(effective['parameters']['response_format'])}]
            else:
                prompt = messages(case, variant.get('prompt_system', 'B'))
                budget_prompt = prompt
            tasks.append((case, variant, prompt, upper_cost(variant, budget_prompt)))
    code = [*sorted((ROOT/'reelcheck').glob('*.py')), Path(__file__).resolve()]
    snapshot = out/'source_snapshot'
    snapshot.mkdir()
    hashes = {}
    for path in code:
        relative = path.relative_to(ROOT)
        target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        target.write_bytes(raw)
        hashes[str(relative)] = hashlib.sha256(raw).hexdigest()
    save_json(snapshot/'config.json', config)
    save_jsonl(snapshot/'inputs.jsonl', cases)
    manifest = {'mode': 'live' if args.live else 'dry_run_NO_MODEL_RESULTS',
                'created_at': datetime.now(timezone.utc).isoformat(), 'config': config,
                'inputs_sha256': digest(cases), 'source_files_sha256': hashes,
                'case_count': len(cases), 'systems': [v['id'] for v in variants],
                'seed': args.seed, 'workers': args.workers, 'max_calls': args.max_calls,
                'max_cost_usd': args.max_cost_usd, 'planned_calls': len(tasks),
                'planned_cost_upper_estimate': sum(task[3] for task in tasks),
                'protocol': 'Same input packets; shuffled variant order per case; at most two in flight; no retry or repair; no gold or judge is consulted.',
                'output_mode_notes': {v['id']:MODE_NOTE for v in variants if v.get('output_mode') == MODE},
                'cost_note': 'Conservative byte-count reservations are estimates, not billing guarantees. Reservations are never released. Unknown failed-call costs remain unknown.'}
    save_json(out/'manifest.json', manifest)
    if not args.live:
        save_jsonl(out/'request_preview.jsonl', [{'case_id':c['case_id'], 'system':v['id'], 'messages':p,
            'request_parameters':request_config(v,c)['parameters'] if v.get('output_mode') == MODE else v.get('parameters',{})} for c,v,p,_ in tasks])
        print(f'Dry run: {len(tasks)} requests prepared; no API calls. {out}', flush=True)
        return manifest
    if args.shell_keys:
        load_shell_exports(args.shell_keys)
    if not os.environ.get('FIREWORKS_API_KEY'):
        raise ValueError('FIREWORKS_API_KEY is missing')
    records, pending = [], {}
    next_task, dispatched, reserved = 0, 0, 0.
    stop_reason = 'completed'
    halted = False
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while pending or (next_task < len(tasks) and not halted):
            while not halted and len(pending) < args.workers and next_task < len(tasks):
                case, variant, prompt, bound = tasks[next_task]
                if dispatched >= args.max_calls or reserved + bound > args.max_cost_usd:
                    halted, stop_reason = True, 'call_or_cost_budget_reached'
                    break
                reserved += bound
                dispatched += 1
                next_task += 1
                future = pool.submit(_execute, case, variant, prompt, dispatched)
                pending[future] = dispatched
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            # Inspect the entire completed batch before dispatching another request.
            for future in sorted(done, key=lambda f: pending[f]):
                row = future.result()
                del pending[future]
                records.append(row)
                save_jsonl(out/'runs.jsonl', sorted(records, key=lambda r:r['call_index']))
                print(f"{row['case_id']} {row['system']}: {row['execution_status']}", flush=True)
                if row.get('http_status') in {401,403,404,429} or row['execution_status'] in {'transport_error','runner_error'}:
                    halted, stop_reason = True, 'provider_access_rate_or_transport_error'
    records.sort(key=lambda r:r['call_index'])
    save_jsonl(out/'runs.jsonl', records)
    completion = {'stop_reason': stop_reason, 'paid_calls_attempted': dispatched,
                  'saved_records': len(records), 'planned_calls': len(tasks),
                  'reserved_cost_upper_estimate': reserved}
    save_json(out/'completion.json', completion)
    summary = operational_summary(records, variants, len(cases))
    summary['completion'] = completion
    save_json(out/'summary.json', summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('--inputs', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--live', action='store_true')
    p.add_argument('--max-cost-usd', type=float, default=3.)
    p.add_argument('--max-calls', type=int, default=100)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--seed', type=int, default=20261102)
    p.add_argument('--shell-keys', default=str(Path.home()/'.zshrc'))
    args = p.parse_args()
    try:
        run_matrix(args)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        p.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
