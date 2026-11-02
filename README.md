# ReelCheck

Check the claim. See the evidence.

This is the **first fixed-evidence verifier experiment** for Fireworks Deploy 2026.
It is a working local experiment harness, not a completed video app. Live access
has been verified for GLM 5.3 Flash and Kimi K3 on Fireworks. The public repository is
https://github.com/raylin435/reelcheck.

## Run locally

Python 3.11+; no third-party packages are needed for the first experiment.
Run commands from this directory:

```sh
python3 -m unittest discover -s tests -v
python3 -m reelcheck doctor
python3 -m reelcheck run --out results/preview
```

The last command is a **dry run**. It prepares 64 requests for 16 cases and makes no
network calls. It writes input/prompt/config/code hashes and request previews, never
fake model outputs or benchmark scores. Choose a fresh output directory each run.

## Credentials and smoke checks

Copy `.env.example` to `.env` and populate it locally. Never put keys in chat or git.
Fireworks keys: https://app.fireworks.ai/settings/users/api-keys

```sh
cp .env.example .env
# Edit .env in your editor, then:
python3 -m reelcheck doctor
python3 -m reelcheck smoke --config config.fireworks.json --role open
python3 -m reelcheck smoke --config config.fireworks.json --role frontier
```

If the file is in the parent workspace, use `python3 -m reelcheck --env ../.env ...`.
If keys were saved in `~/.zshrc`, use `python3 -m reelcheck --shell-keys ~/.zshrc ...`.
This reads only direct exports for the three supported API keys without executing
the shell configuration or copying credentials into the project.
The smoke commands each make one small paid API request. They print status, model,
usage, and latency, not credentials. They do not test verification quality.

The default experiment uses **Fireworks only**, following host guidance relayed by Ray.
Both roles use the same Fireworks key and hackathon credit. A is Kimi K3, the stronger
open-model reference; B/C/D use GLM 5.3 Flash. This is not a comparison with a proprietary
frontier API. Internal role name `frontier` is retained for configuration compatibility.
The adapters also support other providers, but no additional provider key is needed.

## Cost-bounded pilot

Copy `config.example.json` to `config.local.json`. Enter verified per-million-token
rates under each model's `pricing`, for example the **shape**
`{"input_per_million": 1.0, "output_per_million": 2.0}`; these example numbers are
not prices. Record the pricing source and date alongside your experiment.

```sh
python3 -m reelcheck --shell-keys ~/.zshrc run --config config.fireworks.json --live \
  --out results/pilot-02 --max-calls 64 --max-cost-usd 2
python3 -m reelcheck report --run results/pilot-02
```

The runner uses one call per case/system, interleaves system order deterministically,
and spaces requests 6.1 seconds apart by default. No retry or repair is implemented
in this first version. It stops on access/rate/transport errors. A 64-call run takes
at least about 6.5 minutes, plus slow inference. `--limit 2 --max-calls 8` is useful
for the first live integration check. Cost guards reserve conservative input byte-count
and maximum-output estimates; these are not provider-enforced spending limits. Unknown
usage/cost remains unknown and failures remain in denominators. Cached input uses
`cached_input_per_million` when configured, otherwise the conservative uncached rate;
final financial claims require reconciling actual billing. `config.fireworks.json`
contains GLM standard-tier rates checked on its official model page on November 2.

## Systems

| ID | Experiment |
| --- | --- |
| A | Kimi K3 on Fireworks, with explicit evidence and uncertainty instructions |
| B | GLM 5.3 Flash on Fireworks, with the same core instructions |
| C | GLM emits requirements and evidence mapping; executable gate validates it |
| D | GLM with an explicit material-qualifier and citation checklist |
| C_no_gate | Same raw response and usage as C, before the gate; zero additional API calls |

This is a fixed-packet component experiment. D does not implement live retrieval.
C has no repair loop yet. Invalid maps are execution failures, not automatically
converted into correct-looking insufficient-evidence answers. Every system has the
same evidence and output-token ceiling by default. Record model-specific reasoning
settings and tune fair baselines on development data before freezing a final protocol.
Because the gate only rejects answers in this version, it cannot increase the number
of correct answers relative to its own ungated response. Any reduction in wrong
decisive answers must be examined alongside reduced coverage. C versus B/D tests
the full mapping approach; the gate ablation tests enforcement alone.

## Data and evaluation

`data/dev_inputs.jsonl` contains 16 original claims: six supported, six contradicted,
four insufficient. Short passages were verified against four USGS/NASA pages in
Chrome on November 2, 2026. `data/sources.jsonl` records URLs and snapshot hashes.
Only the supplied packet determines the disposition; a true real-world claim can
be insufficient when its decisive passage is deliberately withheld.

`data/dev_gold.jsonl` is separate from inputs and never read by the inference runner.
**Labels are AI-drafted and await independent human review.** These are development
cases, not a held-out final benchmark. The four source families and related variants
are too narrow for broad statistical claims. No video or caption extraction is tested.

The report separates:

- Verdict accuracy and an **automated evidence-ID/quote proxy**.
- Wrong decisive answers, correct insufficiency, and unnecessary abstention.
- Decisive coverage on answerable cases and execution failures.
- Observed latency, usage, estimated cost, and unknown-cost cases.
- Human-reviewed grounded success, which stays **null** until all required reviews exist.

To review, copy `review_template.jsonl` to a different file, inspect each answer
against the actual claim and evidence, and fill all four Boolean review fields.
Keep any alternative acceptable evidence decisions documented in the gold labels.
Then run `report --reviews path/to/reviews.jsonl`. Partial runs are explicitly flagged.
The reviewer should not be the same assistant used to tune the harness.

The gate cannot prove semantic entailment, detect all missing model-generated
requirements, or establish source authority. A valid quote is not proof of support.
Quotation matching normalizes whitespace only, including nonbreaking spaces; wording,
numbers, punctuation and units still must match. Source text and hashes remain original.
Human review is necessary; apparent proxy improvements are not measured grounded gains.

Trace files use atomic complete snapshots rather than long-lived append handles.
The first 64-call attempt (`pilot-01`) lost its response file and is **not valid evidence**.
Its API costs cannot be reconstructed from the missing usage records. A subsequent
four-call diagnostic confirmed a nonbreaking-space validation bug, corrected uniformly
for all systems before the fresh `pilot-02` run. Do not merge those diagnostic results
into the reported pilot or present them as independent held-out evidence.

## Parallel approach comparison

See [CHALLENGE_RESULTS.md](CHALLENGE_RESULTS.md) for the completed comparison,
its failure audit, and the architecture recommendation. The first routing policy
was declared before inference; the invalid-only variant was chosen afterward and
is explicitly exploratory.

The expanded development set contains 40 additional cases: 32 AI-authored claims
using the existing verified passages and 8 clearly fictional diagnostic fixtures.
These reuse source families; they are not 40 new independent facts or real clips.
`CHALLENGE_REVIEW.md` contains provenance and draft-label rationale, and
`EVALUATION_AUDIT.md` records the pre-run AI audit. Human review remains pending.

```bash
python3 scripts/compare_approaches.py --out results/my-preview
python3 scripts/compare_approaches.py --out results/my-live-run --live --max-cost-usd 5
python3 scripts/replay_schema_only.py --run results/my-live-run --out results/my-schema-replay
```

The checked-in JSONL datasets are ready to use. Dataset builder scripts require the
original local page snapshots in `data/source_snapshots/`, which are not distributed;
use the source URLs and hashes in `data/sources.jsonl` to inspect provenance.

Use a fresh output directory each time. The live command reads only direct key
exports from `~/.zshrc` without executing the shell file. Two concurrent workers
compare Kimi/direct GLM and mapped/checklist GLM on identical inputs. Each shard
retains its own atomic traces and completion status. The cost cap uses conservative
token reservations; reported spend uses returned usage. Failed calls can have
unknown cost and are never treated as free. There are no automatic retries.

The predeclared routing policy replays GLM first, escalating invalid, failed, or
insufficient outputs to the already recorded Kimi response. It cannot detect a
confidently wrong GLM answer. Replay includes both stages' costs and sums their
latencies, but is not a measured live routing pipeline. Its rows and the gate
ablation do not add paid calls or actual experiment spend.

Each completed run produces `REPORT.md`, `summary.json` (including source/fixture
breakdowns and disagreements), `runs.jsonl`, and a blank human review template.
Prompts explicitly allow arithmetic and explain conflict precedence uniformly.
Predeclared acceptable uncertainty reasons avoid treating synonymous categories
as different factual verdicts. The proxy still cannot establish semantic support.

## Next steps

### Real-video seed and model judge

Run `python3 scripts/build_real_video.py` to generate the inputs and provenance
manifest from the checked-in seed files. [REAL_VIDEO_RESULTS.md](REAL_VIDEO_RESULTS.md)
contains the completed pilot and its limitations.

`data/real_video_manifest.json` records nine original-claim paraphrases from three
real videos: two NASA/JPL explainers with official untimed transcripts and one
Short with a detailed creator description. No timestamps or human truth labels
are invented. These are development seeds, not a representative final benchmark.
The pipeline currently evaluates verification against manually assembled evidence;
it does not test automatic video ingestion or retrieval. Caltech passages include
clearly marked editorial summaries as well as short direct excerpts.

```bash
python3 scripts/build_real_video.py
python3 scripts/run_model_matrix.py --config config.real_video.json \
  --inputs data/real_video_inputs.jsonl --out results/my-video-run \
  --live --max-cost-usd 3 --max-calls 36 --workers 2
python3 scripts/judge_run.py --run results/my-video-run \
  --inputs data/real_video_inputs.jsonl --config config.real_video.json \
  --out results/my-video-judge --live --shell-keys ~/.zshrc \
  --max-cost-usd 5 --max-calls 36 --interval 1
python3 scripts/report_video_run.py --run results/my-video-run \
  --judge results/my-video-judge --out results/my-video-report
```

Omit `--live` for previews. Every output directory must be fresh. The matrix
compares GLM direct/checklist, DeepSeek V4.1 Flash, and GPT-OSS 120B. All use
Fireworks and the same key; GPT-OSS does not require an OpenAI API account.
Published prices and reasoning parameters are recorded in the configuration.
Reference models' eligibility as the event's frontier baseline remains unconfirmed.

Kimi judges anonymized responses, without gold labels or model/system identities.
Objective failures cannot be overridden by a judge. Exact duplicate judge payloads
reuse an assessment without extra cost. Model-assessed acceptance remains separate
from human-verified accuracy. Reports flag when the judge chooses different expected
verdicts for the same packet across candidate answers. Judging cost is evaluation
overhead and is reported separately from service cost and latency.

`config.structured_video.json` is an exploratory follow-up selected after observing
GPT-OSS formatting failures. `output_mode: citation_ids` constrains its JSON schema
and attaches selected source passages in code. The renderer preserves its verdict,
reason, and explanation, rejects unknown IDs, and cannot fix semantic mistakes.
Quote validity becomes a renderer property. Fireworks documents that JSON-schema
mode disables reasoning output; this is a declared generation-mode change, not a
pure prompt ablation. Fresh clips are needed before claiming general improvement.

1. API access, published prices, and the two-case integration check are complete.
2. Have the teammate independently review the 16 labels and evidence sufficiency.
3. Compare the completed pilot and expanded challenge results; inspect disagreements
   before deciding whether mapping or routing earns its cost.
4. Only then add repair, retrieval, or video; curate a separate held-out evaluation.
5. Publish code, reproduction instructions, measured results, and the final commit;
   record the under-120-second demo and update the HackerSquad draft.

The online draft and repository setup were prepared with Codex assistance. This local
implementation and development dataset were also authored with Codex. No benchmark
improvement or independent human validation is claimed.

## Reference documentation

- Fireworks chat API: https://docs.fireworks.ai/api-reference/post-chatcompletions
- Fireworks API key settings: https://app.fireworks.ai/settings/users/api-keys
- Event rules: https://hackersquad.io/events/fireworks-deploy-with-microsoft-nvidia/resources?tab=rules

License: MIT (matching the initialized public repository). Government text excerpts
remain attributed to their agencies; third-party imagery and tables are not included.
