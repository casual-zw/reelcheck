# Grounded60 evidence-reference revision

This is a development revision of grounded60, not a new collection. All 60 inputs,
claims, videos and verdicts are unchanged: 41 supported, 6 contradicted, 13
insufficient. The frozen parent remains at `../benchmark60`.

## What changed

Twelve reference records now accept additional, individually sufficient evidence
sets. The earlier references often combined independent corroborating passages
into one mandatory conjunction. `evidence_audit.jsonl` records every before/after
set, the actual reviewed passages, and the semantic reason for each addition.
This was a Codex parent-agent review of cached passages, not human verification.
The other 48 reference records have not received this additional audit.

The altered records no longer attribute the new alternatives to the original
judges' receipt IDs. Original reviews remain available in the parent release.
No verdict, input, output schema, or scoring implementation changed.

## Saved baseline check

Rescoring the same 60 DeepSeek outputs gives 40/60 automated proxy successes,
versus 35/60 with the original references. Exact verdict matches remain 56/60.
See `baseline_rescore_details.jsonl` and `validation.json`.

This is a reference correction, not improved model performance. The audit was
motivated by a development baseline, so this release is not an untouched held-out
evaluation. Remaining proxy failures may include other incomplete evidence
alternatives; do not interpret them all as factual errors. Evidence-ID matching
also cannot prove a model's explanation is semantically sound.

## Use

Pass this directory's `inputs.jsonl` to the existing ReelCheck runner and
`reference_labels.jsonl` to the existing reporter's `--gold` argument. Re-score
all compared systems with the same revision; never compare one system's old-gold
score to another system's new-gold score. Human verification is still pending.

Rebuild both additions offline from the collection workspace with
`python3 improve_grounded_data.py`. No external inference is performed.

## Published layout

This directory is a portable input/reference release. Paths inside provenance
refer to the original collection workspace; source text is bundled in
source_snapshots.jsonl. Existing source videos remain in label_snapshots/videos
via Git LFS. No additional videos are needed.

The offline build scripts in video_collection accept the original collection
workspace as their first positional argument. Rebuilding requires that workspace's
`data/grounded60`, `data/latest_news10`, media, and saved baseline source snapshot;
those intermediate caches are not all bundled in this PR. Evaluation of the
published inputs does not require rebuilding or access to those caches.
