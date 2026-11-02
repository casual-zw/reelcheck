"""Combine measured service metrics with explicitly fallible model assessments."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from reelcheck.__main__ import digest,save_json
from reelcheck.evaluation import read_jsonl


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',action='append',required=True)
    p.add_argument('--judge',action='append',required=True)
    p.add_argument('--inputs',default=str(ROOT/'data/real_video_inputs.jsonl'))
    p.add_argument('--out',required=True)
    args=p.parse_args()
    if len(args.run)!=len(args.judge):raise ValueError('Pair each run with one judge directory')
    cases=read_jsonl(args.inputs)
    data_hash=digest(cases)
    runs=[]; judgments=[]; systems={}; generation_cost=0;judge_cost=0
    for run_path,judge_path in zip(args.run,args.judge):
        run=Path(run_path);judge=Path(judge_path)
        manifest=json.loads((run/'manifest.json').read_text())
        jm=json.loads((judge/'manifest.json').read_text())
        if manifest['inputs_sha256']!=data_hash or jm['inputs_sha256']!=data_hash:
            raise ValueError('Input hashes differ')
        rows=read_jsonl(run/'runs.jsonl'); jr=read_jsonl(judge/'judgments.jsonl')
        if digest(rows)!=jm['candidate_rows_sha256']:raise ValueError('Judge assessed different candidate rows')
        if {(r['case_id'],r['system']) for r in rows}!={(r['case_id'],r['system']) for r in jr}:
            raise ValueError('Incomplete judge coverage')
        rs=json.loads((run/'summary.json').read_text());js=json.loads((judge/'summary.json').read_text())
        for name,metrics in rs['systems'].items():
            if name in systems:raise ValueError('System names must be unique across runs')
            systems[name]={**metrics,**js['systems'][name],
                'verdict_distribution':dict(Counter((r.get('output') or {}).get('verdict','no_valid_verdict') for r in rows if r['system']==name))}
        cost=rs['estimated_actual_run_cost_usd'];jc=js['estimated_actual_judge_cost_usd']
        generation_cost=generation_cost+cost if generation_cost is not None and cost is not None else None
        judge_cost=judge_cost+jc if judge_cost is not None and jc is not None else None
        runs+=rows;judgments+=jr
    if any(m['incomplete'] for m in systems.values()):raise ValueError('Incomplete generation cannot support full comparison')
    expected=defaultdict(set)
    for r in judgments:
        output=(r.get('judge_response') or {}).get('output') or {}
        if output.get('expected_verdict'):expected[r['case_id']].add(output['expected_verdict'])
    inconsistent={cid:sorted(v) for cid,v in expected.items() if len(v)>1}
    artifact={'status':'Development only; LLM assessments are not human-verified accuracy.',
        'systems':systems,'case_count':len(cases),'clip_groups':len({c['group_id'] for c in cases}),
        'generation_cost_usd':generation_cost,'judge_cost_usd':judge_cost,
        'judge_expected_verdict_disagreements':inconsistent,
        'requires_review':[{'case_id':r['case_id'],'system':r['system'],
            'acceptance':r.get('model_assessed_acceptance'),'judge':(r.get('judge_response') or {}).get('output'),
            'objective_errors':r.get('objective_errors')} for r in judgments if r.get('model_assessed_acceptance') is not True or r['case_id'] in inconsistent]}
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    save_json(out/'summary.json',artifact)
    lines=['# Real-video development comparison','','**These are model assessments, not human-verified accuracy.**', '',
        f"{len(cases)} original-claim paraphrases from {artifact['clip_groups']} real videos. Seven derive from untimed publisher transcripts; two derive from a Short creator description. No fabricated timestamps, synthetic claim mutations, or automatic speech extraction.", '',
        '| System | Objective-valid outputs | Accepted by LLM judge | Rejected | Unresolved | Median service seconds | Inference cost |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name,s in systems.items():
        cost='unknown' if s['estimated_total_cost_usd'] is None else f"${s['estimated_total_cost_usd']:.6f}"
        lines.append(f"| {name} | {s['schema_valid_completed']}/{s['attempted']} | {s['accepted_by_model_assessment']}/{s['cases']} | {s['rejected_by_model_assessment_or_objective_checks']} | {s['unresolved']} | {s['p50_latency_s']:.2f} | {cost} |")
    lines += ['',f'Generation spend estimate: {generation_cost}. Separate judge spend estimate: {judge_cost}. Judge time/cost is evaluation overhead, excluded from service latency and inference costs above.', '',
        '## Judge consistency and required review','',
        f'The blinded judge produced different expected verdicts for {len(inconsistent)} identical claim/evidence packets across candidate answers. Such cases need adjudication; aggregate acceptance counts cannot settle model superiority.']
    for cid,verdicts in inconsistent.items():lines.append(f'- {cid}: '+', '.join(verdicts))
    for r in artifact['requires_review']:
        lines += ['',f"- **{r['case_id']} / {r['system']}** — acceptance {r['acceptance']}; objective errors {r['objective_errors']}."]
        if r['judge']:lines.append('  Judge rationale: '+r['judge'].get('rationale',''))
    lines += ['', '## Interpretation', '',
        'The matrix uses identical manually assembled source packets, a 4096-token output budget, two workers, and no retries. DeepSeek and GPT-OSS use default reasoning. Kimi is an independent-family, identity-blinded judge with explicit high reasoning. The judge was sanity-checked on six controlled examples (five model calls plus one objective rejection); this is not broad judge validation.', '',
        'The citation-ID follow-up, if included, was selected after observing baseline wrapper and quote errors. It constrains the response schema and attaches source quotations in code. Verdicts/explanations remain model-generated and can be wrong. Schema mode has a documented reasoning-output caveat. Same-case improvements are development evidence and must be tested on fresh clips.', '',
        'Primary evidence contains exact NOAA excerpts and, for the light-path clip, short Caltech quotations plus explicitly marked editorial summaries. Interpretive questions and incomplete packets remain. No human labels, representative population sample, retrieval benchmark, or full-video understanding is established. Strong open-model reference candidates are not confirmed hackathon frontier-baseline eligibility.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'report':str(out/'REPORT.md'),'systems':systems,'judge_disagreement_cases':inconsistent},indent=2))


if __name__=='__main__':main()
