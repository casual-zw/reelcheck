# Evidence-backed video claim cases

50 ReelCheck-compatible claim/evidence cases from 29 downloaded videos and 26 creators. Labels: {'supported': 35, 'insufficient': 11, 'contradicted': 4}. All 50 are AI-drafted references pending independent human review.

## Files

- `inputs.jsonl`: only case identifiers, grouping, assertion date, claim text and retrieved evidence; no reference labels or judge explanations.
- `reference_labels.jsonl`: separate answers, acceptable evidence sets, uncertainty reasons and receipt IDs; pass this as ReelCheck's `--gold` argument.
- `provenance.jsonl`: original claim, explicit narrowing, source video URL/local path/SHA-256, ASR quotation and sampled frame indices.
- `source_snapshots.jsonl`: retrieved source text and hashes. Publication dates remain null when unavailable; retrieval time is not publication time.
- `split_groups.json`: keep each connected video/source group together in future train/test splits. All current cases are development cases, not an untouched test set.
- `human_review_template.jsonl`: incomplete review fields are null, never fabricated approvals.
- Independent Fireworks review receipts are not included in this snapshot; the
  reference labels contain receipt identifiers for audit where the originals exist.

## What is available

3312 discovered URLs; 1000 selected download candidates; **300 actual downloaded clips**, 49 creators, all YouTube. About 363.0 minutes and 582.2 MB of video. Clip lengths: 13–179 seconds (median 60.5). The roughly 3,000-item collection is a URL inventory, not 3,000 downloaded and transcribed videos.

| Sampling category | Downloaded videos | Final claim cases |
|---|---:|---:|
| climate_environment | 30 | 3 |
| finance_economy | 31 | 7 |
| food_fitness | 30 | 5 |
| health_medicine | 31 | 7 |
| history_geography | 30 | 6 |
| politics_society | 30 | 1 |
| science_space | 30 | 3 |
| streamer_viral_commentary | 29 | 3 |
| technology_ai | 29 | 7 |
| world_news | 30 | 8 |

Categories are source sampling buckets, not independently verified topic labels. Counts describe a deliberately selected convenience sample, not misinformation prevalence. The benchmark has 92 retrieved source snapshots across 70 publisher domains; sources and related claims are correlated.

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

This evidence/curation revision used 563 logged API calls, 2,219,598 input tokens and 173,260 output tokens: **approximately $6.81** at standard rates, including experiments and logged retries. This excludes earlier bulk/pilot work and any search connector charges; actual billing may differ.

From the ReelCheck repository root:

```sh
python3 -m reelcheck run --inputs video_collection/benchmark50/inputs.jsonl --out results/benchmark50-dry-run
```

The run command defaults to a free dry run. For an authorized live experiment, keep inputs fixed for every system and use `reference_labels.jsonl` only in the subsequent report step. Do not feed answers or source-review explanations into the baseline or improved verifier.

The integrity results in `verification.json` were produced in the original collection
workspace. Re-running `verify_benchmark.py` requires the original working dataset and
model receipts under `video_collection/data/`; those are not included in this snapshot.
The 300 source videos are available separately under `video_collection/label_snapshots/videos/`
using Git LFS. Obtain your own API key for any additional labeling.
