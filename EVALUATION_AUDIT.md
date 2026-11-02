# Development evaluation audit

This is a second-agent code and label review, not an independent human review. It does not validate a final benchmark or replace human judgment of citation entailment.

## Findings before challenge execution

- Keep verdict correctness separate from the stricter automated proxy. Missing evidence and missing context can both describe a defensible insufficient-evidence answer; ambiguous cases should declare acceptable reason labels before inference. The original scorer accepted only one reason.
- Passage-ID matching checks that a required source was cited, not that the selected quotation entails the claim. A model can quote an irrelevant substring of the correct passage, or append a misleading extra citation, and pass the proxy. Inspect disagreements and a sample of apparent successes; do not call proxy passes grounded accuracy.
- The requirement gate validates declared requirements and their internal structure. It cannot establish that decomposition is complete or that the claimed relation follows from the quote.
- Four reused source families remain four families even when expanded into many cases. Related cases cannot be treated as independent evidence for narrow confidence intervals. Synthetic fixtures must be visibly labeled and reported separately from agency-source cases.
- Current experiments verify claims against supplied passages; they do not test live retrieval, source credibility selection, transcript extraction, or real short-video performance.
- Equal output-token limits define a fair deployment constraint, but mapping truncation is a failure under that budget, not proof that decomposition cannot help with a different budget.
- Concurrent experiments should be compared within the same run. Provider load, caching, and local concurrency confound historical latency comparisons.
- Routing replay must disclose modeled sequential latency and summed token cost; reused responses do not constitute measured live end-to-end routing or additional API spend. Never use gold labels to route.

## Challenge label review

All 40 draft claims, evidence packets, labels, rationales, and acceptable passage sets were inspected before live inference. The draft contains 32 claims built from four previously verified NASA/USGS source families and eight visibly fictional fixtures. No challenge model outputs were consulted.

The following issues were communicated and corrected before execution:

1. Four claims used meta wording such as “the packet establishes.” They were changed to plain factual claims so absence of evidence remains an insufficient verdict rather than inviting a literal contradiction of the meta statement.
2. The equal-standing conflict case (challenge_35) should require both F1 and F2 citations. An empty accepted set would otherwise award a correct conflict label without evidence for the conflict.
3. Nonconflict insufficient cases should accept missing_evidence or missing_context. Their distinction is not operationally defined in the shared prompt, and both reasonably describe several omitted-qualifier or withheld-source packets. The conflict case should retain conflicting_evidence only.
4. The shared prompt needs explicit unresolved-conflict precedence: equally credible contradictory reports imply insufficient unless evidence establishes which supersedes the other. Its original “at least one refutation” wording otherwise supports contradicted on the same packet.
5. The shared prompt should permit ordinary arithmetic and standard unit conversions on supplied quantities, while still prohibiting outside factual knowledge. The unit-conversion and comparative-heat cases rely on this distinction.

Root reports uniform prompt corrections and passing tests before the live run; dataset agent owns regeneration of gold and claims. These are protocol clarifications applied across all systems, not response-dependent scoring adjustments.

The resulting labels are coherent for diagnostic development use, subject to the pending independent human review. In particular, an average distance does not by itself refute constancy (challenge_19); it leaves the constant-distance claim unestablished. The version fixture explicitly says version 2 supersedes version 1, whereas the conflict fixture gives no such precedence. Both conflicting measurements exceed 45 liters, so the claim about what both reports say is still supported (challenge_36).

This review does not establish real-video representativeness, broad source coverage, or semantic correctness of future model answers.


## Interim trace review (run still in progress)

This section records AI inspection of specific persisted responses, not a final aggregate or human validation. No code, gold labels, or prompts were changed in response to these observations.

### challenge_19: average versus a constant instantaneous value

The quoted packet says the Moon is an average of 384,400 kilometers away. The claim says this exact distance holds at every instant. A constant sequence of 384,400 values and a varying sequence with the same mean are both compatible with the sentence. The packet therefore neither proves nor refutes constancy under the predeclared evidence-only task; `insufficient` remains a defensible gold label. Ordinary-language use of “average” can suggest variation, so this case warrants a human adjudication before a strong public conclusion.

B returned insufficient and explained the missing instantaneous/range information. A, C, and D returned contradicted, explicitly treating the average description as a refutation of constancy. C's requirement map declared a contradicting relation and passed its gate; the validator has no semantic check that could disprove that relation. This is a concrete illustration of why structural mapping does not establish entailment.

A replay that escalates every B insufficient answer to A would change this case from a correct abstention to a wrong decisive verdict. Escalation is not automatically safer merely because its model is more expensive.

### challenge_21: correct uncertainty, invalid schema

The packet omits lunar atmospheric evidence. B's answer correctly states that the supplied distance and ring facts cannot settle breathability. Its JSON uses `citation特别s` instead of the required `citations`, however, so the response is operationally invalid. Counting it as a failed task is consistent with the frozen contract; it should be described as a schema failure rather than a mistaken factual judgment. A, C, and D returned valid insufficient outputs.

This case motivates a schema-only fallback or constrained output experiment. It does not by itself justify replacing valid abstentions. Any repair policy must preserve the original record, charge its extra inference, and be evaluated on fresh cases before deployment claims.


## Final challenge-01 trace audit

The completed run made 160 calls and retained all four systems' 40-case responses plus C ablations. Inspecting all automated failures identifies exactly three case IDs: challenge_19, challenge_21, and challenge_39. This audit is AI interpretation; human-reviewed success remains unset.

### challenge_39: fixture framing ambiguity

All three GLM approaches returned insufficient because I1 explicitly calls itself a fictional fixture and its visible provenance says it is not real-world evidence. Their explanations distinguish that statement from an actual temperature measurement. All correctly reject I2's instruction attack. Kimi instead treats I1 as an assumed fact within the fictional scenario and returns supported, matching the predeclared label.

The task never clearly tells models to assume fictional fixture statements are true within a hypothetical world. Consequently both interpretations have a basis in the input. This is a benchmark-framing ambiguity, not clear proof of a GLM reasoning failure or successful prompt injection. The earlier pre-run audit missed this ambiguity; recognizing it after outputs does not justify silently changing frozen labels or deleting the case.

Retain the frozen full-40 results as provisional diagnostics and make the separately identified 32 sourced cases the primary component comparison. For a future dataset version, explicitly frame all fixture claims as questions about a hypothetical scenario, then test fresh examples. Do not present reruns of revised examples as held-out evidence.

### Sourced-only comparison

| System | Automated proxy passes | Failure type | Estimated cost for 32 cases |
| --- | --- | --- | --- |
| A: Kimi reference | 31/32 | Unsupported refutation on average-vs-constant claim | $0.188871 |
| B: direct GLM | 31/32 | Correct substantive uncertainty with invalid schema | $0.00766526 |
| C: mapped GLM plus gate | 31/32 | Same unsupported refutation as A | $0.01586514 |
| D: checklist GLM | 31/32 | Same unsupported refutation as A | $0.00856294 |

Direct GLM's estimated token cost is about 24.6 times lower than Kimi's on this sourced slice, with equal automated pass counts and different failure types. This is a development observation, not proven equivalent quality. The map adds cost without measured benefit here; its gate never corrects the semantic error.

The broad invalid-or-insufficient routing policy fixes the schema error but introduces Kimi's error on a previously correct abstention. A schema-only fallback is therefore a reasonable next experiment. Because that narrower policy was selected after inspecting these failures, its replay is exploratory, even when it improves this dataset's counts. It needs fresh cases and live sequential verification before a deployment or quality claim.

### Decision implication

The evidence favors continuing with the cheap direct verifier and testing bounded schema recovery, while preserving evidence-based abstention. There is not yet a demonstrated reason to center the product on evidence maps or unconditional escalation of uncertainty. Real transcript extraction, representative claims, additional source families, and independent human judgments remain outstanding.
