# ReelCheck first development experiment

**Decision: keep the simple verifier as the current baseline; do not claim the evidence gate improves quality.** The direct and checklist GLM configurations passed all 16 automated checks. The mapped verifier passed 15 because one generation exhausted its output budget. The gate-disabled ablation has the same outcome.

All inference used Fireworks, following host guidance relayed by Ray. A is Kimi K3, a stronger open-model reference; this is not a proprietary-model comparison.

## Recorded results

| System | Automated proxy passes | Wrong decisive verdicts | Answerable-case decisive coverage | Median latency | Estimated cost, 16 cases |
| --- | --- | --- | --- | --- | --- |
| Kimi K3 reference | 16/16 | 0 | 100.0% | 4.22 s | $0.077760 |
| GLM direct baseline | 16/16 | 0 | 100.0% | 1.85 s | $0.003392 |
| GLM checklist baseline | 16/16 | 0 | 100.0% | 2.25 s | $0.004236 |
| GLM evidence map + gate | 15/16 | 0 | 91.7% | 2.98 s | $0.008570 |
| Same mapped response, gate disabled | 15/16 | 0 | 91.7% | 2.98 s | $0.008570 |

The scored run made 64 paid API calls and saved 80 records including 16 reused ablation records. Its usage-based estimated cost is **$0.093957**. The ablation reuses C and must not be counted as additional spend. The mapped system cost about **2.70× as much per automated proxy success** as direct GLM on this set.

## What these results establish

- The API adapters, scoring pipeline, direct verifier, mapping gate, logging, and ablation run end to end.
- The four insufficient-evidence cases were correctly handled by all configurations; the three plain/checklist/reference configurations hit the ceiling on this small set.
- The current map adds output and latency without demonstrated quality benefit. Rejection-only gating cannot improve correct-answer counts over the same raw response; any safety benefit must be evaluated at comparable coverage.
- The C failure was dev_15, a gram-versus-kilogram claim. It exhausted the common 4,096-token completion budget; this remains a failed task in the denominator. No failed case was silently retried.

## Important limits

The score is an automated proxy: correct draft verdict, accepted evidence passage IDs, valid quote text, and preserved claim string. It does not independently prove semantic entailment or that every material requirement was extracted. Human-reviewed grounded success remains null. Review HUMAN_REVIEW.md before making a competition claim.

These are 16 AI-drafted development cases across four source families: six supported, six contradicted, four insufficient. They are not held-out final cases, not naturalistic video trials, and not enough for broad equivalence or statistical superiority claims. Several variants share a source or claim. No video ingestion, live search, repair loop, or training is tested.

## Run provenance and failures

- Model IDs: accounts/fireworks/models/glm-5p3-flash and accounts/fireworks/models/kimi-k3.
- Published standard-tier prices were checked in Chrome on November 2, 2026; rates and URLs are in config.fireworks.json.
- results/pilot-02/manifest.json records code/input hashes, provider settings, seed, request spacing, and limits. runs.jsonl contains outputs and usage; summary.json contains aggregates.
- The original 64-call attempt (pilot-01) lost its response trace. It is excluded from scoring and its actual usage cost cannot be reconstructed. Its recorded conservative reservation was $1.416577; it is not a measured bill.
- A four-call diagnostic identified nonbreaking-space quote matching failures. The fix normalizes whitespace only and applies to all systems. The first integration and diagnostic calls are development overhead, not additional scored examples.
- Trace persistence now uses atomic complete snapshots and final readback. Twenty-two local tests passed, including credential-safe loading, malformed outputs, quotation integrity, gold-label isolation, ablation reuse, cost accounting, and trace replacement.

## Next decision

Use direct GLM (or the checklist version if human review favors its explanations) for the minimum verifier. Before investing in a richer gate, use one additional development slice of naturally occurring qualifier, conflicting-evidence, or multi-source failures. Do not manufacture a benchmark to favor the gate. If the cheap baseline still reaches the ceiling, keep the simpler method and focus on faithful claim extraction or a more valuable task.

A real final evaluation must be newly curated, independently labeled, frozen before tuning, and separate from these development cases. At the time of this initial pilot, implementation files and results had not yet been pushed to the public repository.
