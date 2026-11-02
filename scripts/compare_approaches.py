"""Run two independent, budgeted experiment shards concurrently, then compare.

All outputs are local. Source calls are preserved separately from routing replay.
Run from project root: python3 scripts/compare_approaches.py --out results/challenge-01 --live
"""
import argparse
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reelcheck.__main__ import check_data, configuration, digest, run, save_json, save_jsonl, upper_cost
from reelcheck.evaluation import read_jsonl, score, summarize
from reelcheck.prompts import messages
from reelcheck.providers import load_shell_exports
from reelcheck.strategies import materialize_routing, POLICY_VERSION


def combine(out, inputs, gold_path):
    cases = {c['case_id']: c for c in read_jsonl(inputs)}
    gold = {g['case_id']: g for g in read_jsonl(gold_path)}
    rows = []
    for shard in ('reference_direct', 'map_checklist'):
        part = read_jsonl(out / shard / 'runs.jsonl')
        for row in part:
            row['shard'] = shard
        rows.extend(part)
    if len({(r['case_id'], r['system']) for r in rows}) != len(rows):
        raise ValueError('Duplicate measurements')
    planned = {(cid, s) for cid in cases for s in ('A','B','C','C_no_gate','D')}
    if {(r['case_id'],r['system']) for r in rows} != planned:
        save_json(out/'incomplete.json', {'message':'Partial run: inspect shard completion files. No full comparison produced.'})
        raise ValueError('Incomplete run; retained partial measurements, do not compare as complete')
    replay = materialize_routing(rows, cases)
    combined = rows + replay
    save_jsonl(out/'runs.jsonl', combined)
    result = summarize(combined, cases, gold)
    paid = [r for r in rows if r['system'] != 'C_no_gate']
    result['paid_calls_attempted'] = len(paid)
    result['estimated_actual_run_cost_usd'] = sum(r['cost_usd'] for r in paid) if all(r.get('cost_usd') is not None for r in paid) else None
    result['routing'] = {'policy':POLICY_VERSION, 'routed_cases':sum(r['routed'] for r in replay), 'note':'Replay only; component latency summed, no extra paid calls.'}
    result['input_sha256'] = digest(list(cases.values()))
    result['gold_sha256'] = digest(list(gold.values()))
    result['slices'] = {}
    result['provenance_groups'] = {}
    for provenance in sorted({c.get('provenance','unspecified') for c in cases.values()}):
        ids = {cid for cid,c in cases.items() if c.get('provenance','unspecified') == provenance}
        result['provenance_groups'][provenance] = summarize([r for r in combined if r['case_id'] in ids], cases, gold)['systems']
    for category in sorted({g.get('slice', 'unspecified') for g in gold.values()}):
        ids = {cid for cid,g in gold.items() if g.get('slice','unspecified') == category}
        result['slices'][category] = summarize([r for r in combined if r['case_id'] in ids], cases, gold)['systems']
    result['disagreements'] = []
    for cid in cases:
        case_rows = [r for r in combined if r['case_id'] == cid]
        scores = {r['system']:score(r,cases[cid],gold[cid]) for r in case_rows}
        if any(not s['automated_proxy_success'] for s in scores.values()):
            result['disagreements'].append({'case_id':cid, 'claim':cases[cid]['claim_text'], 'gold':gold[cid],
                'systems':{r['system']:{'status':r['execution_status'], 'verdict':(r.get('output') or {}).get('verdict'),
                     'reason':(r.get('output') or {}).get('uncertainty_reason'), 'score':scores[r['system']]} for r in case_rows}})
    save_json(out/'summary.json',result)
    save_jsonl(out/'review_template.jsonl', [{'case_id':r['case_id'],'system':r['system'],
         'label_validated':None,'material_meaning_ok':None,'semantic_support_ok':None,'uncertainty_reason_ok':None,'notes':''} for r in combined])
    names = {'A':'Kimi reference','B':'GLM direct','C':'GLM evidence map + gate','C_no_gate':'Same map, gate disabled','D':'GLM checklist','R':'GLM → Kimi routing (replay)'}
    lines = ['# ReelCheck parallel development comparison', '',
       '**AI-drafted development cases, not independently labeled held-out results.**', '',
       '| Approach | Valid correct verdicts | Automated proxy passes | Wrong decisive | Median seconds | Estimated cost |',
       '|---|---:|---:|---:|---:|---:|']
    for system in ('A','B','D','C','C_no_gate','R'):
        s=result['systems'][system]
        cost = 'unknown' if s['estimated_total_cost_usd'] is None else f"${s['estimated_total_cost_usd']:.6f}"
        lines.append(f"| {names[system]} | {s['verdict_correct']}/{s['cases']} | {s['automated_proxy_successes']}/{s['cases']} | {s['wrong_decisive_verdicts']} | {s['p50_latency_s']:.2f} | {cost} |")
    lines += ['', '## Source and fixture breakdown', '', '| Provenance | Kimi | Direct | Checklist | Map + gate | Routing replay |', '|---|---:|---:|---:|---:|---:|']
    for provenance, groups in result['provenance_groups'].items():
        lines.append('| '+provenance+' | '+' | '.join(f"{groups[s]['automated_proxy_successes']}/{groups[s]['cases']}" for s in ('A','B','D','C','R'))+' |')
    lines += ['', f"Paid calls: {len(paid)}. Estimated actual run spend: {result['estimated_actual_run_cost_usd']}. Reused ablation and routing rows are excluded from actual spend.",
        f"Routing escalated {result['routing']['routed_cases']}/{len(cases)} cases under the predeclared policy. Its latency and cost are replay estimates, not measured live pipeline performance.", '',
        'All approaches use the same evidence, common output-token limit, no repair/retry, and Fireworks. Two concurrent workers can affect latency; compare within this run, not historical timings. The evidence gate checks structure and quotations, not entailment.', '',
        '## Cases requiring review', '']
    for d in result['disagreements']:
        lines += [f"- **{d['case_id']}**: {d['claim']} Draft label: {d['gold']['verdict']}. " + '; '.join(f"{s}: {v['verdict'] or v['status']} ({'pass' if v['score']['automated_proxy_success'] else 'needs review'})" for s,v in d['systems'].items())]
    lines += ['', '## Interpretation limits', '',
        'Original sourced facts and explicitly synthetic fixtures are diagnostic material. Related examples are not independent. No real clip ingestion, retrieval quality, or human semantic review is established. See CHALLENGE_REVIEW.md for case provenance and label rationale. Use this run to decide what to test next, not to claim competition superiority.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'report':str(out/'REPORT.md'), 'systems':result['systems'], 'routing':result['routing'], 'actual_cost':result['estimated_actual_run_cost_usd']},indent=2),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',required=True)
    p.add_argument('--live',action='store_true')
    p.add_argument('--inputs',default=str(ROOT/'data/challenge_inputs.jsonl'))
    p.add_argument('--gold',default=str(ROOT/'data/challenge_gold.jsonl'))
    p.add_argument('--max-cost-usd',type=float,default=5.)
    p.add_argument('--shell-keys',default=str(Path.home()/'.zshrc'))
    args=p.parse_args()
    out=Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Choose a fresh output directory')
    cases=read_jsonl(args.inputs)
    check_data(cases)
    config=configuration(ROOT/'config.fireworks.json')
    shards=[('reference_direct','A,B'),('map_checklist','C,D')]
    bounds={name:sum(upper_cost(config['frontier' if s=='A' else 'open'],messages(c,s)) for c in cases for s in systems.split(',')) for name,systems in shards}
    if sum(bounds.values()) > args.max_cost_usd:
        raise ValueError(f"Conservative reservation {sum(bounds.values()):.3f} exceeds cap {args.max_cost_usd}")
    out.mkdir(parents=True,exist_ok=True)
    save_json(out/'plan.json',{'mode':'live' if args.live else 'dry_run','cases':len(cases),'paid_calls_planned':len(cases)*4,
        'concurrency':2,'shards':shards,'budget_cap_usd':args.max_cost_usd,'conservative_reservations':bounds,
        'input_sha256':digest(cases),'gold_file_sha256_before_run':hashlib.sha256(Path(args.gold).read_bytes()).hexdigest(),
        'routing_policy':POLICY_VERSION,'replay_note':'Predeclared B → A; invalid or insufficient only. No gold consulted by policy.'})
    if args.live:
        load_shell_exports(args.shell_keys)
    def shard_run(name,systems):
        run(Namespace(config=str(ROOT/'config.fireworks.json'),inputs=args.inputs,limit=None,systems=systems,
            out=str(out/name),seed=20261103,live=args.live,max_calls=len(cases)*2,max_cost_usd=bounds[name]+1e-9,interval=1.))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(shard_run,name,systems) for name,systems in shards]
        for f in futures:
            f.result()
    if args.live:
        combine(out,args.inputs,args.gold)


if __name__=='__main__':
    main()
