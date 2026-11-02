# Real-video development comparison

**These are model assessments, not human-verified accuracy.**

9 original-claim paraphrases from 3 real videos. Seven derive from untimed publisher transcripts; two derive from a Short creator description. No fabricated timestamps, synthetic claim mutations, or automatic speech extraction.

| System | Objective-valid outputs | Accepted by LLM judge | Rejected | Unresolved | Median service seconds | Inference cost |
|---|---:|---:|---:|---:|---:|---:|
| glm_direct | 9/9 | 9/9 | 0 | 0 | 3.74 | $0.005595 |
| glm_checklist | 8/9 | 8/9 | 1 | 0 | 6.06 | $0.007916 |
| deepseek_reference | 9/9 | 8/9 | 1 | 0 | 2.41 | $0.009771 |
| gptoss_reference | 6/9 | 6/9 | 3 | 0 | 1.88 | $0.005251 |
| gptoss_citation_ids | 9/9 | 9/9 | 0 | 0 | 1.84 | $0.004148 |

Generation spend estimate: 0.032682084. Separate judge spend estimate: 0.450114. Judge time/cost is evaluation overhead, excluded from service latency and inference costs above.

## Judge consistency and required review

The blinded judge produced different expected verdicts for 1 identical claim/evidence packets across candidate answers. Such cases need adjudication; aggregate acceptance counts cannot settle model superiority.
- video_gas_01: insufficient, supported

- **video_gas_01 / deepseek_reference** — acceptance False; objective errors [].
  Judge rationale: CO2_1 establishes that atmospheric CO2 is rising mostly because of fossil-fuel burning, while CO2_4 shows that natural sinks remove only about half of those emissions and the rest remains in the atmosphere; CO2_3 confirms that this adds CO2 to the atmosphere. However, none of the supplied passages states that the carbon was long-stored or is being returned, a material part of the claim. The citations therefore support an atmospheric carbon imbalance but not the full claim, making a supported verdict an overclaim.

- **video_gas_01 / gptoss_reference** — acceptance False; objective errors ['candidate_execution_invalid_output'].

- **video_gas_01 / glm_checklist** — acceptance True; objective errors [].
  Judge rationale: CO2_1 establishes that burning fossil fuels raises atmospheric CO2 and CO2_4 shows natural sinks remove only about half of fossil-fuel CO2 with the rest persisting, supporting a disruption of the natural carbon balance. However, no supplied passage states that the carbon in fossil fuels was 'long-stored' before release, and per the rubric no outside knowledge may be used to fill that gap, so a material qualifier of the claim is unestablished. The candidate correctly identified this exact gap, preserved the claim verbatim, cited accurate and relevant quotes from CO2_1 and CO2_4, and appropriately used missing-evidence uncertainty rather than overclaiming support.

- **video_gas_01 / glm_direct** — acceptance True; objective errors [].
  Judge rationale: CO2_1 establishes that rising CO2 is mostly from burning fossil fuels since the Industrial Revolution, and CO2_4 explicitly states CO2 is emitted from fossil fuel burning with natural sinks removing only about half while the rest stays in the atmosphere, which together establish net atmospheric accumulation and thus a disrupted carbon balance. The candidate's quotes are exact and directly relevant, and the identical claim is preserved. The only caveat is that the packet does not literally prove the carbon is 'long-stored'/'returned'; that descriptor is consistent with the fossil-fuel framing rather than independently established, so confidence is medium rather than high, but it is not a material counterexample and does not warrant abstention.

- **video_gas_02 / gptoss_reference** — acceptance False; objective errors ['candidate_execution_invalid_output'].

- **video_sea_02 / gptoss_reference** — acceptance False; objective errors ['candidate_execution_invalid_output'].

- **video_light_01 / glm_checklist** — acceptance False; objective errors ['candidate_execution_truncated'].

- **video_gas_01 / gptoss_citation_ids** — acceptance True; objective errors [].
  Judge rationale: CO2_1 establishes that rising CO2 is mostly from burning fossil fuels, and CO2_4 establishes that natural sinks remove only about half of fossil-fuel CO2 emissions, with the remainder staying in the atmosphere—together supporting both the release of carbon as CO2 and the disruption of the natural carbon balance. The 'long-stored' characterization is inherent to fossil fuels and consistent with the packet. The candidate's quotes are verbatim and semantically relevant, and no uncertainty qualifier is warranted.

## Interpretation

The matrix uses identical manually assembled source packets, a 4096-token output budget, two workers, and no retries. DeepSeek and GPT-OSS use default reasoning. Kimi is an independent-family, identity-blinded judge with explicit high reasoning. The judge was sanity-checked on six controlled examples (five model calls plus one objective rejection); this is not broad judge validation.

The citation-ID follow-up, if included, was selected after observing baseline wrapper and quote errors. It constrains the response schema and attaches source quotations in code. Verdicts/explanations remain model-generated and can be wrong. Schema mode has a documented reasoning-output caveat. Same-case improvements are development evidence and must be tested on fresh clips.

Primary evidence contains exact NOAA excerpts and, for the light-path clip, short Caltech quotations plus explicitly marked editorial summaries. Interpretive questions and incomplete packets remain. No human labels, representative population sample, retrieval benchmark, or full-video understanding is established. Strong open-model reference candidates are not confirmed hackathon frontier-baseline eligibility.

## Decision from this pilot

Use DeepSeek V4.1 Flash as the cheaper strong open-model reference candidate, and carry GPT-OSS with constrained citation IDs forward as an implementation candidate. Keep direct GLM as a control. On these same nine development cases the GPT-OSS change increased objective-valid outputs from 6/9 to 9/9, with inference cost $0.005251 to $0.004148 and median service latency 1.88s to 1.84s. The latency difference is too small and unreplicated to claim a speed improvement. This does not establish semantic superiority or general reliability.

The independent-family judge accepted all nine improved outputs, but disagreed with itself on the expected verdict of gas_01 across candidates. Thus no model has demonstrated perfect factual accuracy. Exclude this case from definitive quality ranking until adjudicated, while retaining its recorded scores. Other interpretive questions concern metaphors, average temperatures, and evidence gaps.

This turn's estimated API spend was $0.518098134 including both inference runs, both judge runs, six judge sanity checks (five calls), and one schema compatibility call. These are usage-based estimates, not the account balance or provider invoice.

## Videos and primary evidence

- [NASA Earth Minute: Gas Problem](https://www.jpl.nasa.gov/edu/resources/video/nasas-earth-minute-gas-problem/) — official untimed transcript; 102-second video.
- [NASA Earth Minute: Sea Level Rise](https://www.jpl.nasa.gov/edu/resources/video/nasas-earth-minute-sea-level-rise/) — official untimed transcript; 90-second video; forecast context remains 2015.
- [Light Takes Every Path—At Once](https://www.youtube.com/shorts/eNOwQtfWSWg) — 34-second Short uploaded by Quantums; claims here come from its creator description, not verified spoken captions.
- [NOAA carbon dioxide](https://www.climate.gov/news-features/understanding-climate/climate-change-atmospheric-carbon-dioxide), [NOAA sea level](https://oceanservice.noaa.gov/facts/sealevel.html), and [Caltech/Feynman optics](https://www.feynmanlectures.caltech.edu/I_26.html).

## Model and API references

- [DeepSeek V4.1 Flash1017](https://app.fireworks.ai/models/fireworks/deepseek-v4p1-flash-1017): $0.30 input / $1.20 output per million tokens (standard tier). Kimi reference was $3/$15, so DeepSeek's token rates are substantially lower. Actual response costs depend on usage.
- [GPT-OSS120B](https://app.fireworks.ai/models/fireworks/gpt-oss-120b): $0.15 input / $0.60 output per million tokens. Uses the Fireworks key, not an OpenAI API key.
- [Structured outputs documentation](https://docs.fireworks.ai/structured-responses/structured-response-formatting) and [reasoning parameters](https://docs.fireworks.ai/api-reference/post-chatcompletions). All verified in Chrome on November2,2026.

## Implementation status

60 local tests pass. The new code includes the generic budgeted two-worker model matrix, blinded semantic judge, per-case judge-consistency reporting, real-video provenance builder, and constrained citation-ID renderer. Human-reviewed accuracy remains unset. The next useful validation is fresh clips with independently checked evidence and an evidence-only reference assessment frozen before candidate grading.
