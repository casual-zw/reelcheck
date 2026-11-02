# Grounded 60

The combined evaluation dataset: **60 claim cases from 39 distinct videos**.

| Reference label | Cases |
|---|---:|
| Supported | 41 |
| Contradicted (refuted) | 6 |
| Insufficient evidence | 13 |

Use `inputs.jsonl` for baseline and improved verifiers, and `reference_labels.jsonl` only for scoring. These contain the original grounded 50 plus the 10 recent-news cases labeled by Astra. No old bulk-300 verdicts were imported, and no cases were relabeled. The two parent releases remain unchanged.

`membership.jsonl` identifies each case's parent release. `provenance.jsonl` retains the parent-specific provenance fields. `source_snapshots.jsonl` deduplicates identical source identities; any differing retrieval metadata is retained in `source_snapshot_variants.jsonl`. `split_groups.json` groups related videos and source URLs for future splitting. `release_manifest.json` records both parent release hashes and the merged files' hashes.

All references remain AI drafts pending independent human review. Labeling protocols differ: the grounded 50 used multiple Fireworks models; the news 10 used one in-session Astra reviewer. Original `as_of` dates and development split tags are preserved. Analyze both parent subsets as well as the combined set. This is a fixed-evidence development benchmark, not a human-validated held-out test set or a retrieval benchmark.

From the ReelCheck repository root:

```sh
python3 -m reelcheck run --inputs video_collection/benchmark60/inputs.jsonl --out results/benchmark60-dry-run
```

This defaults to a dry run. Use `video_collection/benchmark60/reference_labels.jsonl` as `--gold` only during reporting.

Publication notes: inputs, references and provenance are byte-for-byte copies of the local merged release. Their internal paths refer to the original collection workspace. The ten Astra annotations and packets are included in `astra_reviews/` and `news10_packets/`; the source release manifests are in `parent_manifests/`. Earlier Fireworks receipt IDs are preserved but the original receipt files are not published. Raw source videos are stored separately in `video_collection/label_snapshots/videos/` via Git LFS, including the four new X clips. Sampled frame files referenced by provenance are not bundled; their source videos and original URLs are available. No credentials are included.
