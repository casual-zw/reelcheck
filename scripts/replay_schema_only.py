"""Exploratory follow-up chosen after challenge-01; never new API calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from reelcheck.__main__ import digest, save_json, save_jsonl
from reelcheck.evaluation import read_jsonl, summarize
from reelcheck.strategies import materialize_routing


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--inputs',default=str(ROOT/'data/challenge_inputs.jsonl'))
    p.add_argument('--gold',default=str(ROOT/'data/challenge_gold.jsonl'))
    args=p.parse_args()
    source=Path(args.run)
    out=Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh output directory')
    cases={c['case_id']:c for c in read_jsonl(args.inputs)}
    gold={g['case_id']:g for g in read_jsonl(args.gold)}
    original=json.loads((source/'summary.json').read_text())
    if digest(list(cases.values())) != original['input_sha256'] or digest(list(gold.values())) != original['gold_sha256']:
        raise ValueError('Inputs or labels differ from original scored run')
    rows=read_jsonl(source/'runs.jsonl')
    replay=materialize_routing(rows,cases,system='R_schema',escalate_insufficient=False)
    result=summarize(replay,cases,gold)
    result.update(selection='Exploratory: policy selected after examining challenge-01. Requires fresh evaluation.',
                  extra_paid_calls=0, extra_actual_cost_usd=0, routed_cases=sum(r['routed'] for r in replay),
                  source_run=str(source.resolve()),provenance_groups={})
    for provenance in sorted({c['provenance'] for c in cases.values()}):
        ids={cid for cid,c in cases.items() if c['provenance']==provenance}
        result['provenance_groups'][provenance]=summarize([r for r in replay if r['case_id'] in ids],cases,gold)['systems']
    out.mkdir(parents=True,exist_ok=True)
    save_jsonl(out/'runs.jsonl',replay)
    save_json(out/'summary.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
