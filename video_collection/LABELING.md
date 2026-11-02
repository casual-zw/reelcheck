# Repeated, evidence-grounded video judging

This thorough pipeline started with **22 pilot clips**. To meet the later time/token constraint, it was superseded by the [300-video bulk workflow](BULK_LABELING.md): 14 completed audited pilot records were preserved, and unfinished expensive stages were deferred with their successful requests cached. Outputs are provisional machine annotations. Repeated agreement cannot establish correctness, and these labels must not serve as the sole ground truth for a claim that the harness outperforms its own judge models.

## Method

1. Verify each original video hash. Transcribe the complete audio locally using MLX Whisper large-v3-turbo. Sample frames at 1 FPS; each visual pass gets alternating frames at approximately 0.5 FPS. This is sampled visual analysis, not continuous video understanding.
2. Extract timestamped atomic claims independently with **Kimi K3** and **Qwen3.8 Max** on Fireworks. Preserve speaker stance, attribution and modality. Reconcile their union; every extracted assertion must be retained or explicitly excluded with a reason.
3. Retrieve reviewed evidence URLs from `evidence_sources.json`. Save source text, links, retrieval time and checksums. A fact-check about an apparent fabricated endorsement does not establish whether every associated medical assertion is false. Unavailable sources remain documented failures.
4. Run three separate blinded judgments: Kimi K3, Qwen3.8 Max, Kimi K3. Each gets the same claims and evidence, with complementary frame samples and review emphasis. They are independent requests, not independent human experts; correlated model errors remain possible.
5. Ask Kimi K3 to adjudicate disagreements. Ask **GLM-5.3** to audit evidence entailment, temporal scope and speaker role. The text-only auditor does not inspect the frames.
6. Require a real evidence ID and matching quotation for factual verdicts. Failed citations or audits force abstention. Disagreements, uncertainties, coverage problems and all abstentions require human review.

The six verdicts are `supported`, `refuted`, `misleading_context`, `mixed`, `insufficient_evidence` and `not_checkable`. Claim statuses are `silver_consensus`, `needs_review` and `abstained`; none is gold. Agreement fractions measure votes, **not probabilities of correctness**. A video with any unresolved factual claim conservatively receives `insufficient_evidence`; use individual claims for analysis.

## Run and resume

For mass labeling, use the parallel runner after media preparation and evidence curation:

```sh
.venv/bin/python batch_label.py --workers 8 --max-requests 16
```

Eight videos progress independently. Within each video, both extractors run concurrently, followed by reconciliation; then all three blinded judges run concurrently, followed by adjudication and audit. `--max-requests` bounds actual in-flight API calls **per process**, including nested stages and retries. Raising video workers does not bypass that limit. Rate limits and temporary server/network failures use bounded retries with jitter; numeric `Retry-After` is honored up to 60 seconds.

The same command resumes after interruption. It skips labels that pass provenance and completeness checks, reuses successful API receipts and retries unfinished stages. Per-video filesystem locks prevent two cooperating runner processes from labeling the same clip on the same filesystem. Atomic artifact writes use unique temporary files. Existing legacy `label.py` processes do not participate in these locks: the current pilot handoff uses `--exclude-keys-file data/labeling/legacy_active.json` and `--wait-for-claims` to avoid duplicating their in-flight work.

Live per-video states are in `data/labeling/jobs/`; batch outcomes are in `data/labeling/batch_shard_0_of_1.json`. Missing media becomes `needs_preparation`; missing external sources becomes `needs_evidence`. `--allow-empty-evidence` explicitly permits the latter for a deliberate abstention/control run. This flag does not waive citation or evidence-audit requirements for factual verdicts. Failures remain retryable and cause a nonzero batch exit.

For several workers or machines, use deterministic, disjoint shards with the same manifest and shard count:

```sh
# Run each index 0, 1, 2 and 3 in a separate worker environment.
.venv/bin/python batch_label.py --workers 4 --max-requests 8 --shard-count 4 --shard-index 0
```

Every video key belongs to exactly one shard. Across four processes the aggregate request allowance is 32, so size these limits to the account quota. Machines need their own configured credential and corresponding prepared media and evidence. Merge the per-video labels, claims, evidence snapshots, prepared-media metadata and API receipts/usage afterward into the workspace holding the original videos; then regenerate the consolidated report and run verification. This is deterministic work partitioning, not a distributed storage service.

Check coverage while jobs run with `.venv/bin/python label.py report`. The final gate is `.venv/bin/python verify_labels.py`.

Configure `FIREWORKS_API_KEY` in the ignored local `.env` file or environment. Never commit credentials. Inference sends sampled frames, transcripts and evidence to Fireworks. Audio transcription runs locally because the separate Fireworks audio endpoint did not accept the configured credential. Preparation currently requires Apple Silicon/macOS; inference and evidence retrieval use ordinary Python.

```sh
.venv/bin/python label.py preflight
.venv/bin/python prepare_labels.py
.venv/bin/python label.py extract --workers 3
.venv/bin/python gather_evidence.py
.venv/bin/python batch_label.py --workers 8 --max-requests 16
.venv/bin/python verify_labels.py
.venv/bin/python label.py report
.venv/bin/python -m unittest test_collection test_labeling
```

Use `--key youtube_VIDEO_ID` to prepare, extract or judge one clip. `--limit` selects a prefix of downloaded videos. Successful requests are cached by full request hash and unique run ID; rerunning does not reuse one answer as multiple votes. Changed claims/evidence produce new inference requests. Truncated answers are discarded and retried with progressively larger output allowances, capped at 65,536 tokens. Retry and unsuccessful token usage remains in the usage log. Interrupted calls without a completed receipt may incur costs again on retry.

Review `data/labeling/evidence_requests.jsonl` after extraction, research the actual propositions and add evidence with:

```sh
.venv/bin/python evidence.py --key youtube_VIDEO_ID --url https://example.org/original-source
```

Evidence gathering is **curated**, not an autonomous search agent. For future downloaded videos, add and inspect sources before judging. Claims without adequate retrieved evidence should abstain. Exact directly observable facts can also abstain under the conservative external-citation requirement. No factual verdict is assigned from publisher reputation.

## Outputs

| Path | Contents |
| --- | --- |
| `data/labeling/labels.jsonl` | Consolidated video records with timestamped claim verdicts |
| `data/labeling/labels/*.json` | Per-video labels, votes, citations, uncertainty and audit results |
| `data/labeling/review_queue.jsonl` | Claims requiring human attention |
| `data/labeling/report.json` | Actual coverage and class counts; total recorded API tokens |
| `data/labeling/verification.json` | Artifact integrity/completeness checks; not a truth certificate |
| `data/labeling/claims/*.json` | Reconciled claims and extraction receipt IDs |
| `data/labeling/evidence/*.json` | Retrieved evidence snapshots used by judges |
| `data/labeling/api/*.json` | Successful API receipts, model IDs, request IDs, usage and structured results |
| `data/labeling/api/usage.jsonl` | Append-only metering, including unsuccessful truncated generations |
| `data/labeling/*_failures.json` | Failed video jobs in the corresponding most recent CLI batch |
| `data/labeling/media/` | Automatic transcripts, sampled frames and prepared audio |

API receipts retain structured explanations, not private reasoning traces. The evidence and claim hashes in a label must match current artifacts; `verify_labels.py` rejects stale labels and missing runs. Re-run judging after evidence changes. Failure files describe their last batch, not necessarily the status of every clip; final completeness is established by verification.

## Before benchmarking

Have humans watch the original clips, inspect extraction omissions and adjudicate factual claims using the recorded sources. Review language, event dates and ambiguous identities. Blind reviewers to the model votes where practical. Deduplicate and split by claim/event cluster before training or evaluation; cluster fields remain unset until reviewed. Hold out creators and recent events, and keep evidence/labels outside tested model inputs unless retrieval access is explicitly part of the task.

Compare the baseline and harness under the same inputs, evidence access and cost budget. Report macro-F1, claim coverage, evidence accuracy and abstention separately. A small pilot with machine-generated targets cannot establish frontier-model superiority.

Implementation references: [Fireworks vision inputs](https://docs.fireworks.ai/guides/querying-vision-language-models), [structured responses](https://docs.fireworks.ai/structured-responses/structured-response-formatting), [reasoning budgets](https://docs.fireworks.ai/guides/reasoning), and the model pages for [Kimi K3](https://fireworks.ai/models/fireworks/kimi-k3), [Qwen3.8 Max](https://fireworks.ai/models/fireworks/qwen3p8-max) and [GLM-5.3](https://fireworks.ai/models/fireworks/glm-5p3).
