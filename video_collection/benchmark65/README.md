# Grounded65: five additional claims from recent-news videos

65 claim cases from 39 distinct videos: 45 supported, 6 contradicted, 14
insufficient. This expands grounded60_v2, including its 12 evidence-reference
repairs. The first 60 input and reference records are unchanged from that parent.
The original grounded60 and the separate evidence_challenge18 remain intact.

## Additions

| Case | Video | Claim | Verdict |
|---|---|---|---|
| news10_apple_neural | CNET Apple update | M6 has a dual 16-core Neural Engine | supported |
| news10_apple_wireless | CNET Apple update | M6 MacBook Pro supports Wi-Fi 7 and Bluetooth 6 | supported |
| news10_patterson_victims | BBC Patterson appeal | Three relatives were killed by a meal containing death cap mushrooms | supported |
| news10_patterson_grounds | BBC Patterson appeal | The appeal challenged evidence rulings, cross-examination, and jury accommodation | supported |
| news10_stevens_never_met | Al Jazeera Trump remarks | Trump had never met Haley Stevens before these remarks | insufficient |

The Trump case checks the underlying assertion, not whether he said it. His
statement appears in the clip, but the external evidence does not independently
establish a complete history of their meetings. Reporting of a phone call does
not establish an in-person meeting. Insufficient is relative to the supplied
packet, not a claim that the fact is impossible to verify.

## Provenance and review

Every addition has an exact automatic-transcript quote, transcript character
position and hash, source passage offsets, original packet hash, and video hash
in provenance.jsonl. Source passages match the cached source snapshots exactly.
The ASR phrase "death cat mushrooms" is normalized to "death cap mushrooms",
supported by the source report; this is recorded in the review. ASR was not
independently checked against audio during this expansion.

The five labels were reviewed by the Codex parent agent against cached sources.
They are AI drafts pending independent human review, not new Astra or Fireworks
judgments. No new paid inference was used. addition_reviews.jsonl records the
rationale and input hash. There are four supported additions and one insufficient
addition; no false claim was invented to force class balance.

All claims from the same parent video remain in the same split cluster. These
five additions are correlated with existing cases, not five independent videos.
The recent-news subset now has 15 claims across its original 10 videos: three
claims each for Apple and Patterson, two for Stevens, and one each for the other
seven videos. The 18 derived evidence diagnostics are not included in this count.

## Use and verification

Use inputs.jsonl and reference_labels.jsonl with the existing ReelCheck runner
and reporter. added_inputs.jsonl and added_reference_labels.jsonl contain only
the new five cases for a cheaper incremental evaluation. The model contract is
unchanged. Do not send references, reviews or provenance to the model as inputs.

Rebuild offline from the collection workspace with `python3 expand_grounded65.py`.
The generator verifies passage/source matches, evidence hashes, video hashes,
unique case IDs, parent preservation, and reference-output schema compatibility.
A full ReelCheck dry run prepared 260 requests across A/B/C/D without model calls.
No live evaluation or performance gain is claimed for the new cases.

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
