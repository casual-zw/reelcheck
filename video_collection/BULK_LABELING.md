# 300-video, low-token run

This is the fast, provisional workflow selected for the 30-minute hackathon window. It is separate from the exhaustive claim-level pilot in `data/labeling/`.

Completed on 2026-11-02: **300 videos, ten categories, 49 creators**, with no unresolved preparation/inference failures. The run reused 14 audited pilot records and produced 286 two-model screens. Verdicts: 77 supported, 13 mixed, one refuted, one misleading-context, 22 not-checkable and 186 insufficient-evidence. There were 108 disagreements between the two bulk judges; these abstain. This is not a balanced true/false benchmark.

The bulk calls consumed 965,466 input tokens and 129,596 output tokens across 572 API requests. Estimated standard-rate cost: **$3.7817**, excluding prior pilot costs and cache discounts. These are usage-based estimates, not an invoice. The labels and source videos passed `verify_bulk.py --expected 300`; 13 implementation tests passed.

Run downloads and labeling in separate terminals; labels stream from completed downloads:

```sh
.venv/bin/python download_mass.py --count 300 --workers 6
.venv/bin/python bulk_label.py --count 300 --workers 16 --max-requests 24 --minutes 25
```

The downloader replenishes failed candidates from the category/creator-diverse selection queue. It checks duration (10–180 seconds), decodes every accepted file and hashes the original bytes. The bulk preparer transcribes complete audio locally and selects six frames across each clip. No title-only classifications are used.

Each new video gets two independent calls: Kimi K3 and Qwen3.8 Max on Fireworks, with reasoning disabled, a 1,024-token output allowance and at most one length retry to 2,048 tokens. Each call receives six frames and the automatic transcript, capped at 12,000 characters with an explicit truncation flag. It returns the main assertion, one video-level label, a short rationale and limitations. There are no separate extraction, reconciliation, adjudication or evidence-audit calls in this fast path. The models are not shown each other's answers. A disagreement yields `insufficient_evidence` and high review priority.

**These are weak/provisional labels, not independently verified facts or gold benchmark answers.** No external evidence is retrieved for the fast path. Models must abstain on unverified events, identity, attribution and medical efficacy. Agreement can still reflect shared errors, omitted claims or ASR mistakes. Before measuring harness accuracy, have humans adjudicate a held-out sample. Never use agreement rate as an accuracy estimate.

Completed audited pilot labels are reused to save tokens, with `label_tier=audited_claim_aggregate`; newly screened videos have `label_tier=provisional_video_screen`. Keep these tiers distinct in analysis: the first aggregates an exhaustive claim inventory, while the second covers the main assertion(s). Neither tier is human-verified.

Outputs:

- `data/bulk/dataset.jsonl`: ready-to-load video paths, URLs, durations, categories and annotation links. Keep label fields out of evaluated model inputs.
- `data/bulk/labels.jsonl`: consolidated labels, source URLs, category, provenance and judge results.
- `data/bulk/labels/`: resumable per-video results.
- `data/bulk/review_queue.jsonl`: disagreement and insufficient-evidence records for follow-up; no additional model calls are launched automatically.
- `data/bulk/report.json`: actual counts, categories, disagreements and label tiers.
- `data/bulk/failures.json`: preparation or inference failures from the completed run.
- `data/bulk/verification.json`: coverage/provenance checks after verification.
- `data/bulk/media/`: six-frame samples and automatic transcripts.
- `data/labeling/api/`: shared successful API receipts and token usage, filtered by `bulk-video-v1:` run IDs for bulk cost accounting.
- `data/mass_download.log` and `data/bulk_run.log`: logs for this live run.

The preparation deadline stops scheduling new clips; already-submitted inference requests drain afterward. A count is a target, not proof of completion. After the processes finish:

```sh
.venv/bin/python bulk_label.py --report
.venv/bin/python verify_bulk.py --expected 300
```

Rerunning reuses successful labels and cached API responses. Failed clips can be retried; final coverage is determined by verification, not by the scheduler's submitted count. Do not run multiple `bulk_label.py` processes against the same output directory simultaneously; use the locking/sharded claim pipeline for multi-process orchestration. Preparation requires Apple Silicon/macOS with the installed MLX Whisper dependency.
