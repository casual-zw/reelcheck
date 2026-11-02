"""Export separate ReelCheck references, review records and collection statistics."""
import collections
import hashlib
import json
import statistics
from urllib.parse import urlsplit
from curate_cases import B, G, PROTOCOL, validate_vote
from collect import DATA, ROOT, now, read_jsonl, write_jsonl
from fireworks_client import load, save, digest
from label import KIMI, QWEN, AUDITOR


def finalize():
    cases=read_jsonl(B/'inputs.jsonl')
    provenance={r['case_id']:r for r in read_jsonl(B/'provenance.jsonl')}
    refs=[]
    for c in cases:
        r=load(B/'reviews'/(c['case_id']+'.json'))
        assert r['case_sha256']==digest(c),'Stale claim review: '+c['case_id']
        assert r['provenance_sha256']==digest(provenance[c['case_id']]),'Stale provenance review'
        votes=[v['result'] for v in r['votes']]
        a=r['reconciliation']
        final=a['result'] if a else votes[0]
        validate_vote(final,c)
        assert a or (all(v['contract_valid'] for v in r['votes']) and votes[0]['verdict']==votes[1]['verdict'])
        candidates=[final]+[v for v in votes if v['verdict']==final['verdict']]
        evidence_sets=[]
        for v in candidates:
            try:validate_vote(v,c)
            except AssertionError:continue
            ids=sorted(set(v['passage_ids']))
            if ids and ids not in evidence_sets:evidence_sets.append(ids)
        if final['verdict']=='insufficient':evidence_sets=[[]]
        assert evidence_sets
        p=provenance[c['case_id']]
        refs.append({'case_id':c['case_id'],'verdict':final['verdict'],
            'acceptable_evidence_sets':evidence_sets,'uncertainty_reason':final['uncertainty_reason'],
            'slice':p['video']['sampling_category'],'label_status':'AI_draft_pending_independent_human_review',
            'human_verified':False,'reason':final['reason'],
            'agreement_status':'reconciled' if a and len({v['verdict'] for v in votes})>1 else 'unanimous',
            'additional_audit':bool(a),'review_receipts':[v['receipt'] for v in r['votes']]+([a['receipt']] if a else []),
            'input_sha256':digest(c)})
    write_jsonl(B/'reference_labels.jsonl',refs)
    write_jsonl(B/'human_review_template.jsonl',[{'case_id':c['case_id'],
        'label_validated':None,'material_meaning_ok':None,'semantic_support_ok':None,
        'uncertainty_reason_ok':None,'reviewer':None,'notes':''} for c in cases])

    # Cases sharing a video or exact normalized source URL belong in one split.
    parent={c['case_id']:c['case_id'] for c in cases}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def join(a,b):parent[find(a)]=find(b)
    seen={}
    for c in cases:
        keys=['video:'+c['group_id']]+['source:'+urlsplit(p['url'])._replace(query='',fragment='').geturl() for p in c['evidence']]
        for k in keys:
            if k in seen:join(c['case_id'],seen[k])
            else:seen[k]=c['case_id']
    components=collections.defaultdict(list)
    for cid in parent:components[find(cid)].append(cid)
    clusters=[{'leakage_group_id':'cluster_'+digest(sorted(ids))[:12],'case_ids':sorted(ids)} for ids in components.values()]
    save(B/'split_groups.json',clusters)
    downloaded=read_jsonl(DATA/'downloaded_manifest.jsonl')
    cats=collections.Counter(r['sampling_category'] for r in downloaded)
    casecats=collections.Counter(p['video']['sampling_category'] for p in provenance.values())
    selected={p['video_key']:p['video'] for p in provenance.values()}
    labels=collections.Counter(r['verdict'] for r in refs)
    usage=[r for r in read_jsonl(DATA/'labeling/api/usage.jsonl') if r['run_id'].startswith(('grounded-v1:','curated50-v1:','curated50-v2:'))]
    rates={KIMI:(3,15),QWEN:(2,6),AUDITOR:(1.4,4.4)}
    cost=sum((r['usage'].get('prompt_tokens',0)*rates[r['model']][0]+r['usage'].get('completion_tokens',0)*rates[r['model']][1])/1e6 for r in usage)
    overview={'at':now(),'discovered_candidates':len(read_jsonl(DATA/'candidates.jsonl')),
        'selected_download_candidates':len(read_jsonl(DATA/'selected.jsonl')),
        'downloaded_videos':len(downloaded),'downloaded_creators':len({r.get('channel_id') or r['source_handle'] for r in downloaded}),
        'platforms':dict(collections.Counter(r['platform'] for r in downloaded)),
        'duration_seconds':{'min':min(r['duration'] for r in downloaded),'median':statistics.median(r['duration'] for r in downloaded),'max':max(r['duration'] for r in downloaded),'total':sum(r['duration'] for r in downloaded)},
        'download_bytes':sum(r['bytes'] for r in downloaded),'downloaded_categories':dict(cats),
        'benchmark_cases':len(cases),'benchmark_videos':len(selected),
        'benchmark_creators':len({r.get('channel_id') or r['source_handle'] for r in selected.values()}),
        'benchmark_labels':dict(labels),'benchmark_case_categories':dict(casecats),
        'benchmark_video_categories':dict(collections.Counter(r['sampling_category'] for r in selected.values())),
        'benchmark_source_snapshots':len(read_jsonl(B/'source_snapshots.jsonl')),
        'benchmark_publisher_domains':len({urlsplit(p['url']).netloc for c in cases for p in c['evidence']}),
        'leakage_groups':len(clusters),'human_verified':0,
        'reconciled_cases':sum(r['agreement_status']=='reconciled' for r in refs),
        'additional_audits':sum(r['additional_audit'] for r in refs),
        'revision_api_calls':len(usage),'revision_input_tokens':sum(r['usage'].get('prompt_tokens',0) for r in usage),
        'revision_output_tokens':sum(r['usage'].get('completion_tokens',0) for r in usage),
        'estimated_revision_cost_usd':round(cost,4),
        'cost_scope':'Evidence-grounded and curated-50 revisions, including logged experiments and retries. Standard rates; not an invoice. Excludes earlier bulk/pilot runs and any connector search charges.'}
    save(B/'overview.json',overview)
    save(B/'release_manifest.json',{'protocol':PROTOCOL,'at':now(),
        'files_sha256':{name:hashlib.sha256((B/name).read_bytes()).hexdigest() for name in ['inputs.jsonl','reference_labels.jsonl','provenance.jsonl','source_snapshots.jsonl','split_groups.json']},
        'human_verified':False,'reference_status':'AI draft, development use only'})
    table='\n'.join(f"| {cat} | {cats[cat]} | {casecats[cat]} |" for cat in sorted(cats))
    text=f'''# Evidence-backed video claim cases

50 ReelCheck-compatible claim/evidence cases from {len(selected)} downloaded videos and {overview['benchmark_creators']} creators. Labels: {dict(labels)}. All 50 are AI-drafted references pending independent human review.

## Files

- `inputs.jsonl`: only case identifiers, grouping, assertion date, claim text and retrieved evidence; no reference labels or judge explanations.
- `reference_labels.jsonl`: separate answers, acceptable evidence sets, uncertainty reasons and receipt IDs; pass this as ReelCheck's `--gold` argument.
- `provenance.jsonl`: original claim, explicit narrowing, source video URL/local path/SHA-256, ASR quotation and sampled frame indices.
- `source_snapshots.jsonl`: retrieved source text and hashes. Publication dates remain null when unavailable; retrieval time is not publication time.
- `split_groups.json`: keep each connected video/source group together in future train/test splits. All current cases are development cases, not an untouched test set.
- `human_review_template.jsonl`: incomplete review fields are null, never fabricated approvals.
- `reviews/`: independent Fireworks decisions and conditional reconciliation, linked to API receipts.

## What is available

{overview['discovered_candidates']} discovered URLs; {overview['selected_download_candidates']} selected download candidates; **{len(downloaded)} actual downloaded clips**, {overview['downloaded_creators']} creators, all YouTube. About {overview['duration_seconds']['total']/60:.1f} minutes and {overview['download_bytes']/1e6:.1f} MB of video. Clip lengths: {overview['duration_seconds']['min']}–{overview['duration_seconds']['max']} seconds (median {overview['duration_seconds']['median']}). The roughly 3,000-item collection is a URL inventory, not 3,000 downloaded and transcribed videos.

| Sampling category | Downloaded videos | Final claim cases |
|---|---:|---:|
{table}

Categories are source sampling buckets, not independently verified topic labels. Counts describe a deliberately selected convenience sample, not misinformation prevalence. The benchmark has {overview['benchmark_source_snapshots']} retrieved source snapshots across {overview['benchmark_publisher_domains']} publisher domains; sources and related claims are correlated.

## Labeling workflow

1. Local speech transcription plus six sampled video frames establish the assertions. Frames capture text that speech misses. ASR and visual grounding remain provisional; this does not audit every frame.
2. Select atomic assertions, retaining the original extraction and recording any narrowing. No fabricated counterfactual claims were added. A supported subclaim does not make the entire video true.
3. Retrieve external sources and cache attributable passages with source hashes and character offsets. Search results are discovery leads; full retrieved text or explicitly marked page excerpts form the evidence. One USDA JSON nutrient record is rendered deterministically with its raw record retained.
4. Kimi K3 and Qwen 3.8 Max independently judge the same fixed claim and evidence. The final verifier input contains **no source-video transcript**; repeated video assertions cannot serve as corroboration. GLM 5.3 reviews disagreements, invalid responses and selected risk cases. Original votes are preserved.
5. Inspect scope and provenance, verify files and hashes, export labels separately, and dry-run ReelCheck without paid evaluation calls.

The earlier broad screen had 186/300 insufficient-evidence video labels and should not be used as evaluation truth. Earlier 150-claim results are retained in `data/grounded/labels/` for audit; use this directory's frozen 50-case files for the new experiment. The earlier curated attempt supplied transcripts to factual judges and is retained separately for audit, not released as the reference.

## Meaning and limits

`supported` and `contradicted` mean the supplied evidence establishes or refutes the exact claim. `insufficient` means the fixed packet cannot decide; it is not a false label, and it does not imply no evidence exists anywhere. Every insufficient case includes retrieved context and a reason. Personal anecdotes and product-benefit claims are not corroborated simply because a narrator says them.

The ambiguous “last erupted in 2012” assertion about Mount Cameroon was excluded: the Smithsonian lists 2000 while also reporting a 2012 explosion. This case instead tests the video's explicit assertion that it is an active volcano. Unfounded negative labels based on lake-size wording, average body-water percentages and composite collagen claims were also excluded.

These are **AI-drafted development references**, not human-validated gold. Models used to create labels overlap with models that may be evaluated, creating possible model-family bias. Evidence-ID matches are scoring proxies; acceptable evidence sets may not enumerate every valid alternative. Independent human review and a new held-out source-grouped test set are needed before claiming broad performance or frontier-model superiority. The small contradicted class and repeated claims per video limit class-level comparisons. This experiment evaluates fixed-evidence verification, not retrieval quality or end-to-end video fact checking.

## Cost and use

This evidence/curation revision used {len(usage)} logged API calls, {overview['revision_input_tokens']:,} input tokens and {overview['revision_output_tokens']:,} output tokens: **approximately ${cost:.2f}** at standard rates, including experiments and logged retries. This excludes earlier bulk/pilot work and any search connector charges; actual billing may differ.

From the project root:

```sh
.venv/bin/python verify_benchmark.py
cd Reelcheck
../.venv/bin/python -m reelcheck run --inputs ../data/grounded/benchmark/inputs.jsonl --out ../data/grounded/benchmark/new_dry_run
```

The run command defaults to a free dry run. For an authorized live experiment, keep inputs fixed for every system and use `reference_labels.jsonl` only in the subsequent report step. Do not feed answers or source-review explanations into the baseline or improved verifier.
'''
    (B/'README.md').write_text(text)
    print(json.dumps(overview,indent=2))


if __name__=='__main__':finalize()
