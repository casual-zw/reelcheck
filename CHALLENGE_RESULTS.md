# ReelCheck direction decision — November 2, 2026

**Recommendation: retain direct GLM with output validation. Explore fallback for invalid outputs; do not automatically override valid uncertainty. The evidence map has not earned its extra cost.**

We added 40 development cases to the original 16 (56 total), made 160 paid calls with two concurrent workers, and retained 240 comparison records including reused ablations/routing. Estimated spend for this run: **$0.30044936**. It excludes previous experiments. No external-provider API keys were used.

## Source-backed diagnostic results

32 new AI-authored claims reuse four previously verified source families. Eight fictional fixtures are reported separately. This separation was specified before the run; these are neither independent facts nor held-out real-video examples.

| Approach | Automated proxy passes | Wrong decisive verdicts | Median seconds | Estimated cost for 32 cases |
|---|---:|---:|---:|---:|
| Kimi reference | 31/32 | 1 | 4.71 | $0.188871 |
| GLM direct | 31/32 | 0 | 2.33 | $0.007665 |
| GLM checklist | 31/32 | 1 | 2.55 | $0.008563 |
| GLM evidence map + gate | 31/32 | 1 | 4.19 | $0.015865 |
| Escalate uncertain/invalid (predeclared replay) | 31/32 | 1 | 2.49 | $0.077427 |
| Invalid-output fallback (**post-hoc replay**) | 32/32 | 0 | 2.34 | $0.013158 |

Replay costs include both stages when routed; replay latency is the sum of component service times and excludes live orchestration overhead. Neither replay consumes extra API calls. The invalid-only policy was selected after observing failures: its 32/32 is a hypothesis-generating result, not validated superiority.

## What changed our thinking

1. **More expensive did not mean more grounded.** On case 19, an average lunar distance was treated by Kimi and mapped/checklist GLM as proof that a constant distance was false. An average alone cannot resolve constancy. Direct GLM correctly said insufficient under the packet-only contract. Human adjudication is still required for public claims.
2. **Direct GLM had an operational failure.** Case 21 had the right uncertainty judgment but a malformed citations field. Validation caught it. A fallback for invalid output fixes this case in replay without overriding case 19.
3. **Escalating all uncertainty had a downside.** The predeclared policy escalated 14/40 cases, fixed the malformed output, but also replaced the correct case 19 uncertainty with a wrong decisive answer. The exploratory invalid-only policy escalated 1/40.
4. **The gate does not establish entailment.** C and C_no_gate had identical passes. The mapped schema accepted an unsupported inference because it only validates declared relations and quotations.

## Fixture ambiguity and frozen results

Across all 40 cases, frozen proxy scores are A 39, B 38, C 38, D 38, predeclared routing 39. Exploratory invalid-only replay scores 39. The one-point difference on fictional case 39 is ambiguous: GLM refuses fictional text as real-world proof, while Kimi reasons within the hypothetical fixture. All ignore the hostile instruction. This is not evidence of a GLM prompt-injection vulnerability. No gold labels or prompts were changed after results to improve the scores. The full 40 scores remain provisional pending resolution of this framing issue and human review.

## Next important decision

Choose direct GLM + strict output validation as the implementation candidate, and test invalid-only fallback on fresh cases. Stop investing in evidence-map generation unless new data reveals a measurable benefit. Do not yet claim model equivalence or deploy the exploratory routing result as proven.
The next evaluation needs new real-clip claims, independently checked labels, frozen source packets, and a separate held-out set (aim 100+ where feasible). Source retrieval and transcript extraction have not been tested. The product claim should be evidence-bounded verification unless we explicitly expand into finding evidence; an absent passage does not mean a real-world claim is false.

## Implementation and verification

- Parallel capped runner: `scripts/compare_approaches.py`; 160 calls, atomically persisted shard logs, pre-run hashes and routing policy.
- Routing policies and accounting: `reelcheck/strategies.py`; invalid-only follow-up via `scripts/replay_schema_only.py`.
- 36 tests pass, including preventing gold leakage, failure accounting, routing regressions, quotation checks, and reason-category alternatives.
- All human-reviewed grounded-success fields remain null. AI audit is not human labeling.
- Original run source/config/input snapshots are in `results/challenge-01/source_snapshot/`; no credentials are included.
- Raw run traces and source snapshots stay local and are excluded from the public code upload.

Local-only frozen comparison: `results/challenge-01/REPORT.md`. Included artifacts: [pre/post-run audit](EVALUATION_AUDIT.md), [label worksheet](CHALLENGE_REVIEW.md), [setup and reproduction](README.md).
