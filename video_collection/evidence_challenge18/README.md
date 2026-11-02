# Evidence sensitivity: 18 diagnostic packets

Six existing claims from six videos each appear under three conditions:

| Claim | Original and restored verdict | Missing-evidence trap |
|---|---|---|
| Squat strength difference | supported | Training methods do not establish results |
| Spirulina highest protein of any food | contradicted | A selected-food ranking is not a universal maximum |
| Viral Netanyahu attack footage | contradicted | A historical incident report alone does not identify the viral clip |
| Patterson appeal outcome | supported | An appeal notice does not establish the decision |
| Charles caught in a downpour | supported | A scheduled visit does not establish what happened |
| MacBook Pro CPU and GPU cores | supported | Knowing the CPU count does not establish the GPU count |

`original` retains the whole parent packet. `missing` retains only reviewed,
related context and is insufficient. `restored` adds the decisive passage(s) back
to that same context. Total labels: 8 supported, 4 contradicted, 6 insufficient.
No passage text or factual claim has been fabricated or rewritten. Passage bytes,
URLs and hashes are checked against cached source snapshots. Metadata identifying
the condition and expected verdict stays outside model inputs. Case IDs are opaque.

These are **18 derived claim/evidence cases, not 18 new videos**. This is an
incomplete-retrieval diagnostic, not a claim that the real-world facts became
unknown. A model must restrict its factual verdict to the supplied packet, as
required by the existing ReelCheck task. Missing packets were reviewed in full;
removal did not merely delete the gold-cited IDs and leave duplicate answers.

## Run with the current contract

From a ReelCheck checkout, using absolute paths to this directory:

```sh
python3 -m reelcheck run --inputs /path/to/evidence_challenge18/inputs.jsonl --out /path/to/new_run
python3 -m reelcheck report --run /path/to/new_run --inputs /path/to/evidence_challenge18/inputs.jsonl --gold /path/to/evidence_challenge18/reference_labels.jsonl
```

The default run is a dry run. Use the repository's normal explicit live-run and
budget options for inference. Local verification prepared 72 requests across
A/B/C/D, with no API calls or performance results.

## Report results honestly

Report verdict and proxy accuracy separately for each condition. For each system,
count how many of the six triples have all three correct verdicts, and how often
it gives a decisive verdict on the missing-evidence condition. Compare original
and restored cases to distinguish incomplete retrieval from distraction/length
sensitivity. More abstentions alone are not a win: the model must recover the
correct decisive verdict when evidence returns.

Keep results separate from the 60-case regression set. All variants and sibling
claims must stay with their parent source cluster;
`split_groups_with_parents.json` includes those assignments. These are development
diagnostics selected after inspecting a baseline, not independent held-out cases.
Three conditions have different evidence lengths, so this is not a controlled
measurement of length effects or a balanced benchmark of retrieval difficulty.

Labels are parent-agent drafts, not human verified. Structural reference-output
checks confirm compatibility, not semantic truth. No live model evaluation was
performed for this addition. `provenance.jsonl` explains each missing fact and
records removed and decisive passage IDs; `validation.json` records checks.

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
