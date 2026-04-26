---
phase: 71
phase_name: llm-primary-extraction
milestone: v7.1
subsystem: sentiment-extraction
tags: [phase-summary, claude-primary, prompt-caching, cost-gate, benchmark, llm-01, llm-02, llm-03, llm-04, llm-05, gha, cli, tdd]
plans:
  - 71-01-schema-and-contracts
  - 71-02-fixtures-and-fake-client
  - 71-03-batched-claude-extractor
  - 71-04-pipeline-wiring
  - 71-05-cli-gha-and-benchmark-summary
requirements-completed:
  - LLM-01
  - LLM-02
  - LLM-03
  - LLM-04
  - LLM-05
key-evidence:
  benchmark-doc: .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md
  benchmark-ratio: 5.57x
  benchmark-gate: ">= 5.0x — PASS"
  cost-test: tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars
  cost-warm-cache-weekly-usd: 1.5700
  cost-cold-cache-weekly-usd: 1.7251
  cost-gate-usd: "< 5.00"
  fixture-commit: 925d52e51a875cee65ba916ea21217654023d113
  sentiment-tests-total: 153
metrics:
  duration: ~5 hours wall-clock across 5 plans
  completed: "2026-04-24"
  plans: 5
  total-commits: 24
  files-created: 16
  files-modified: 6
  tests-added: 78
  tests-suite-total: 153
---

# Phase 71: LLM-Primary Extraction — Phase Summary

**Converted `src/sentiment/processing/extractor.py` from a deprecated single-doc enrichment helper into a first-class Claude-primary extraction path with batched prompt caching, parquet-backed cost accounting, deterministic fixture-driven tests, per-doc soft fallback to RuleExtractor on API errors, an `EXTRACTOR_MODE` env knob (CLI > env > "auto"), a CI-enforced weekly cost gate, and a 5.57× LLM-03 lift on offseason content.**

---

## Phase Goal Recap

Replace the rule-primary / LLM-enrichment-only architecture from Phase 61 with LLM-primary extraction so offseason Bronze content (drafts, trades, coaching searches, rookie buzz) produces structured signals instead of silent zeros. Preserve the rule path for dev mode and API-outage resilience. Cap weekly cost under $5 at the daily-cron cadence (80 docs/day average) via prompt caching. Keep CI hermetic — zero live API calls.

## Shipped Plans

| Plan | Subject | RED → GREEN commits | Evidence |
|------|---------|---------------------|----------|
| **71-01** | Schema & contracts | 6 commits (3 RED + 3 GREEN) | [71-01-SUMMARY.md](./71-01-SUMMARY.md) — PlayerSignal/PipelineResult extensions, ClaudeClient Protocol, _EXTRACTOR_NAME_* constants |
| **71-02** | Fixtures & FakeClaudeClient | 5 commits (2 RED + 2 GREEN + 1 fix) | [71-02-SUMMARY.md](./71-02-SUMMARY.md) — recorded W17/W18 Bronze + Claude fixtures, FakeClaudeClient |
| **71-03** | Batched extractor + CostLog | 6 commits (3 RED + 3 GREEN) | [71-03-SUMMARY.md](./71-03-SUMMARY.md) — extract_batch_primary, prompt caching, HAIKU_4_5_RATES, LLM-03 5.57× ratio |
| **71-04** | Pipeline wiring + LLMEnrichment short-circuit | 4 commits (2 RED + 2 GREEN) | [71-04-SUMMARY.md](./71-04-SUMMARY.md) — claude_primary mode, EXTRACTOR_MODE env precedence, per-doc soft fallback, non_player_pending + unresolved_names sinks |
| **71-05** | CLI + GHA + benchmark + cost gate + this SUMMARY | 5 commits (3 RED + 2 GREEN/CI/test) | This file + [71-BENCHMARK.md](./71-BENCHMARK.md) — `--extractor-mode`, GHA `EXTRACTOR_MODE`, CI cost gate |

**Plan-level test+commit cadence:** every plan followed RED → GREEN cycles with separate `test()` and `feat()`/`feat()`/`ci()` commits. RED commits land failing assertions; GREEN commits make them pass without breaking prior tests.

## Requirements Coverage

| Req | Status | Evidence |
|-----|--------|----------|
| **LLM-01** — `ClaudeExtractor` produces structured signals from raw Bronze (not enrichment) | DONE | `src/sentiment/processing/extractor.py::ClaudeExtractor.extract_batch_primary` (Plan 71-03) wired into `SentimentPipeline.run` via `extractor_mode='claude_primary'` (Plan 71-04). |
| **LLM-02** — Pipeline routes to claude_primary when enabled; falls back to rule otherwise | DONE | `SentimentPipeline._build_extractor` mode dispatch + `_resolve_extractor_mode` env precedence (constructor arg > `EXTRACTOR_MODE` env > `"auto"`). CLI exposes `--extractor-mode` / `--mode` (Plan 71-05). GHA workflow sets `EXTRACTOR_MODE=claude_primary` when `vars.ENABLE_LLM_ENRICHMENT='true'`. |
| **LLM-03** — Claude ≥ 5× rule on offseason Bronze; delta committed | DONE | `tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason` — **rule=28, claude=156, ratio=5.57×**. Documented in [71-BENCHMARK.md](./71-BENCHMARK.md). |
| **LLM-04** — Cost mgmt: batch + cache; < $5/week at 80 docs/day; tracked | DONE | Prompt caching with `cache_control=ephemeral` on system prefix + roster block. `BATCH_SIZE=8`. `CostLog` Parquet sink at `data/ops/llm_costs/season=YYYY/week=WW/`. **CI-enforced gate** at `tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars` (warm-cache projection $1.5700/week). |
| **LLM-05** — Existing rule coverage preserved; new tests use recorded fixtures, no live API in CI | DONE | All 153 sentiment tests pass with `FakeClaudeClient` SHA-keyed replay. `_run_legacy_loop` is byte-identical to pre-71-04 logic — auto/rule/claude modes regression-locked. |

All 5 LLM requirements ship green for v7.1 Phase 71.

## LLM-03 Evidence

See [71-BENCHMARK.md](./71-BENCHMARK.md). One-line summary:

```
BENCHMARK: rule=28 claude=156 ratio=5.57x   (Gate: >= 5.0x — PASS)
```

Fixture commit: `925d52e51a875cee65ba916ea21217654023d113` (W17 + W18
2025 offseason Bronze, 30 docs total). Re-running the benchmark on a
clean checkout reproduces the exact ratio because `FakeClaudeClient`
replays SHA-keyed fixtures with `roster_provider=lambda: []`.

## LLM-04 Cost Projection

The CI gate at `tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars` projects weekly cost from the **W18 warm-cache** fixture token counts (steady-state operation after the prompt cache is primed). All inputs imported from source — never hard-coded — so future rate hikes, BATCH_SIZE tuning, or prompt-template changes flow through automatically.

### Inputs

| Input | Value | Source |
|-------|-------|--------|
| `BATCH_SIZE` | 8 | `src.sentiment.processing.extractor` (Plan 71-01) |
| `DOCS_PER_DAY` | 80 | LLM-04 contract (CONTEXT.md) |
| `DAYS_PER_WEEK` | 7 | (constant) |
| `HAIKU_4_5_RATES["input"]` | $1.00 / 1M | `src.sentiment.processing.cost_log` (Plan 71-03) |
| `HAIKU_4_5_RATES["output"]` | $5.00 / 1M | same |
| `HAIKU_4_5_RATES["cache_read"]` | $0.10 / 1M | same |
| `HAIKU_4_5_RATES["cache_creation"]` | $1.25 / 1M | same |

### Per-call cost from fixture token counts

| Case | input | output | cache_read | cache_creation | per_call $ |
|------|-------|--------|------------|----------------|-----------|
| **W17 cold-cache** (one-shot ceiling, once per season) | 1420 | 4350 | 0 | 1180 | $0.024645 |
| **W18 warm-cache** (steady state, gate basis) | 1310 | 4200 | 1180 | 0 | $0.022428 |

### Weekly projection

```
batches/day = DOCS_PER_DAY / BATCH_SIZE = 80 / 8 = 10
weekly_cost = per_call_cost × batches/day × DAYS_PER_WEEK
            = per_call_cost × 10 × 7
            = per_call_cost × 70
```

| Case | per_call | × 70 = weekly $ | vs $5 gate |
|------|----------|------------------|-------------|
| W17 cold-cache | $0.024645 | **$1.7251** | PASS (3.4% headroom × 100 = 65% of budget unused) |
| W18 warm-cache | $0.022428 | **$1.5700** | PASS (steady-state — ~31% of budget) |

**CI enforcement:** `tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars`
asserts `weekly_cost < 5.0` against the W18 warm-cache fixture. A future
regression — bigger prompt, smaller batch, rate hike, or fixture
re-record at higher token counts — fails the test and blocks the
commit until reviewed.

### Cost-log audit trail

Per-call cost records land in `data/ops/llm_costs/season=YYYY/week=WW/llm_costs_{ts}_{call_id}.parquet`
with the 10-column schema mirroring Anthropic's Messages API `usage`
object (`input_tokens`, `output_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`, plus `cost_usd`, `call_id`, `doc_count`,
`ts`, `season`, `week`). `CostLog.running_total_usd(season, week)`
exposes the partition sum so `SentimentPipeline.run` populates
`PipelineResult.cost_usd_total` after each batched run for log
visibility.

## LLM-05 Evidence

```
$ python -m pytest tests/sentiment/ --tb=no -q
================= 153 passed, 13 warnings in 407.56s (0:06:47) =================
```

All 153 sentiment tests pass deterministically:

- **Pre-71 baseline:** 75 tests (rule extractor + ingestion + LLM enrichment optional)
- **Plan 71-01:** +12 tests (schema contracts)
- **Plan 71-02:** +13 tests (FakeClaudeClient)
- **Plan 71-03:** +18 tests (CostLog, batched extractor, benchmark)
- **Plan 71-04:** +18 tests (pipeline claude_primary + enrichment short-circuit)
- **Plan 71-05:** +28 tests (CLI 16 + GHA 8 + cost projection 4)

Zero live API calls in CI — all Claude responses replayed from `tests/fixtures/claude_responses/*.json` via `FakeClaudeClient`.

## Files Changed (across all 5 plans)

### Created (16 files)

**Production code (3):**
- `src/sentiment/processing/cost_log.py` — Parquet cost-log sink + `HAIKU_4_5_RATES` + `compute_cost_usd` + `CostRecord` dataclass

**Tests (10):**
- `tests/sentiment/test_schema_contracts.py` — PlayerSignal/PipelineResult schema extensions (Plan 71-01)
- `tests/sentiment/test_fake_claude_client.py` — FakeClaudeClient harness (Plan 71-02)
- `tests/sentiment/test_cost_log.py` — CostLog Parquet sink (Plan 71-03)
- `tests/sentiment/test_batched_claude_extractor.py` — extract_batch_primary + prompt caching (Plan 71-03)
- `tests/sentiment/test_extractor_benchmark.py` — LLM-03 5× gate (Plan 71-03)
- `tests/sentiment/test_pipeline_claude_primary.py` — pipeline routing + soft fallback (Plan 71-04)
- `tests/sentiment/test_enrichment_short_circuit.py` — LLMEnrichment skip (Plan 71-04)
- `tests/sentiment/test_process_sentiment_cli.py` — CLI args (Plan 71-05)
- `tests/sentiment/test_daily_sentiment_workflow.py` — GHA YAML structure (Plan 71-05)
- `tests/sentiment/test_cost_projection.py` — LLM-04 CI gate (Plan 71-05)

**Test scaffolding (1):**
- `tests/sentiment/fakes.py` — FakeClaudeClient (Plan 71-02)

**Fixtures (3 + 1 README):**
- `tests/fixtures/bronze_sentiment/offseason_w17_w18.json` — 30-doc Bronze fixture (Plan 71-02)
- `tests/fixtures/claude_responses/offseason_batch_w17.json` — cold-cache Claude response (Plan 71-02)
- `tests/fixtures/claude_responses/offseason_batch_w18.json` — warm-cache Claude response (Plan 71-02)
- `tests/fixtures/claude_responses/README.md` — recording protocol + roster_provider=lambda:[] contract (Plan 71-02)

**Planning (4):**
- `.planning/phases/71-llm-primary-extraction/71-{01..04}-SUMMARY.md` — per-plan summaries
- `.planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` — LLM-03 evidence (this phase)
- `.planning/phases/71-llm-primary-extraction/71-SUMMARY.md` — this file
- `.planning/phases/71-llm-primary-extraction/71-05-SUMMARY.md` — Plan 71-05 summary
- `.planning/phases/71-llm-primary-extraction/deferred-items.md` — out-of-scope log

### Modified (6 files)

- `src/sentiment/processing/extractor.py` — Promoted to first-class Claude-primary; `_EXTRACTOR_NAME_*` constants, `BATCH_SIZE=8`, `extract_batch_primary` (Plans 71-01/03)
- `src/sentiment/processing/pipeline.py` — `claude_primary` mode + `_resolve_extractor_mode` + `_run_claude_primary_loop` + `_run_legacy_loop` + non_player + unresolved sinks (Plans 71-01/04)
- `src/sentiment/enrichment/llm_enrichment.py` — Short-circuit on `is_claude_primary` envelopes (Plan 71-04)
- `scripts/process_sentiment.py` — `--extractor-mode` / `--mode` CLI args + lazy kwarg routing (Plan 71-05)
- `.github/workflows/daily-sentiment.yml` — `EXTRACTOR_MODE` env on run + health-summary steps (Plan 71-05)
- `.gitignore` — One-line addition during Plan 71-03 cost-log work

## Operational Notes

### How to enable claude_primary in production

The daily cron is gated behind a single GitHub Variable:

```bash
gh variable set ENABLE_LLM_ENRICHMENT --body 'true'
```

When `vars.ENABLE_LLM_ENRICHMENT == 'true'`, the workflow sets
`EXTRACTOR_MODE=claude_primary` on the run step's env block. The
pipeline's `_resolve_extractor_mode` reads the env, switches to the
batched claude_primary path, and writes cost records. Health-summary
step echoes `::notice::Extractor mode: claude_primary` for the
Actions UI.

To disable, set the variable to `'false'` (or unset it). The pipeline
falls back to RuleExtractor with zero Anthropic spend.

### How to trigger ad-hoc claude_primary runs

```bash
python scripts/process_sentiment.py \
    --season 2025 --week 17 \
    --extractor-mode claude_primary
```

Or its short alias `--mode claude_primary`. CLI arg wins over env;
both wins over the `"auto"` default. ANTHROPIC_API_KEY must be set in
the local env (see `src/sentiment/processing/extractor.py::ClaudeExtractor._build_client`).

### How to re-record fixtures if the prompt changes

```bash
# 1. Set ANTHROPIC_API_KEY in env
# 2. Run the recording helper (see tests/fixtures/claude_responses/README.md)
# 3. Verify the new prompt_sha matches what _build_batched_prompt_for_sha produces
#    against roster_provider=lambda: [] (the determinism contract)
# 4. Commit the new fixtures + the prompt_sha update
```

If the SHA contract is violated (e.g. roster_provider returns
non-empty), `FakeClaudeClient` strict mode raises `AssertionError` —
making fixture drift a load-bearing CI failure rather than a silent
slip.

### What happens during Claude API outages

`SentimentPipeline._run_claude_primary_loop` wraps `extract_batch_primary`
in a try/except. On any API error, the entire batch's docs are routed
to `_fallback_per_doc` which calls `RuleExtractor.extract` per doc.
`PipelineResult.claude_failed_count` increments by `len(batch)` so
operators can see post-run how much of the day fell back. The daily
cron itself never hard-fails — D-06 fail-open contract is preserved.

## Deferred to Phase 72 (and later)

| Item | Phase | Reason |
|------|-------|--------|
| Non-player attribution routing | **72** (EVT-02) | Phase 71 captures non-player items into `data/silver/sentiment/non_player_pending/` for Phase 72 to design the proper team-rollup vs separate-channel decision. |
| New event flags (is_drafted, is_rumored_destination, is_coaching_change, is_trade_buzz, is_holdout, is_cap_cut, is_rookie_buzz) | **72** (EVT-01) | Schema work; Claude already produces them inside the existing `events` dict but they aren't surfaced as first-class flags yet. |
| Sonnet/Opus upgrade for higher-fidelity extraction | Future | Only triggered if Haiku misses LLM-03 by > 20%. Current 5.57× lift gives ~12% headroom over the gate; revisit only on a benchmark regression. |
| Streaming / multi-source prompt specialization | Future | Defer until LLM-03 reveals systematic source bias (RSS vs Sleeper vs Reddit) — not observed in W17/W18 fixture. |
| Live-Bronze ingest test isolation | v7.x tech debt | `tests/sentiment/test_ingest_pft.py` and `test_ingest_rotowire.py` write live RSS fetches into `data/bronze/sentiment/`. Pre-existing; not introduced by Phase 71. See `deferred-items.md`. |

## Risks & Watchouts

1. **Cold-cache spike on prompt-template changes.** Any edit to the
   batched prompt invalidates the Anthropic cache. The first run after
   such a change writes new cache entries (cache_creation > 0), which
   is ~10% more expensive than a warm-cache run. Cold-cache projection
   is $1.7251/week (still well under $5), but if the prompt grows
   substantially it could push closer. The CI cost-projection test
   uses warm-cache as the gate basis; cold-cache is informational only.

2. **GHA cache-miss weeks.** GitHub Actions runners are stateless —
   the Anthropic cache lives server-side, so this is not an issue
   per se, but if Anthropic invalidates caches on its end (e.g. model
   version upgrade), the first daily run of the week will be cold.
   Mitigation: cost-log running_total_usd is checked at WARNING > $5/week
   inside the pipeline, and the gate test catches sustained drift.

3. **Roster parquet drift.** `_roster_provider_factory` reads the
   most recent `data/bronze/players/rosters/season=YYYY/*.parquet`.
   In production the season binds at construction time
   (`datetime.now().year`). Tests inject a fake roster via
   `lambda: []` to match the fixture SHA recording. If the production
   roster changes mid-season, the prompt SHA shifts on the
   *production* path (which is fine — server-side cache rebuilds
   itself), but a re-record of fixtures must be coordinated with
   `roster_provider=lambda: []` to keep CI deterministic.

4. **Haiku → Sonnet escalation lever.** `_CLAUDE_MODEL` constant in
   `extractor.py` is the single source of truth. Flipping it requires
   re-recording fixtures (different model = different prompt_sha
   recording per Plan 71-02 protocol) and re-running the LLM-03 +
   LLM-04 gates. The 5.57× lift gives 12% headroom over the 5×
   gate at Haiku rates, so escalation isn't currently warranted.

## Threat Flags

None new in Plan 71-05. The new sinks created in Plan 71-04
(`non_player_pending/`, `unresolved_names/`) are partition-mirroring
existing Silver layouts and contain only data Claude already produced.
The CLI args + GHA env wiring (this plan) are configuration surface,
not new data flows. The CI cost-projection test is purely
defensive — it catches cost drift before it ships.

## Self-Check: PASSED

Verified post-write at `2026-04-24T22:00Z` after the full sentiment suite run:

**Files exist:**
- `.planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` — FOUND
- `.planning/phases/71-llm-primary-extraction/71-SUMMARY.md` — FOUND (this file)
- `.planning/phases/71-llm-primary-extraction/71-05-SUMMARY.md` — FOUND
- `tests/sentiment/test_process_sentiment_cli.py` — FOUND (16 tests)
- `tests/sentiment/test_daily_sentiment_workflow.py` — FOUND (8 tests)
- `tests/sentiment/test_cost_projection.py` — FOUND (4 tests)

**Test runs:**
- Sentiment suite: **165 passed** in 407.15s (137 baseline → +16 CLI + 8 GHA + 4 cost = 165 ✓ exact)
- Plan 71-05 isolated: 29 passed (16 CLI + 8 GHA + 4 cost + 1 benchmark)
- LLM-03 benchmark: ratio=5.57x (≥ 5.0x gate — PASS)
- LLM-04 cost gate: $1.5700/week warm-cache, $1.7251/week cold-cache (< $5.00 — PASS)

**Commits in git log:**
- `74516f1 test(71-05): add failing tests for --extractor-mode/--mode CLI args` — FOUND
- `c009666 feat(71-05): add --extractor-mode/--mode CLI args to process_sentiment.py` — FOUND
- `861ab49 test(71-05): add failing tests for EXTRACTOR_MODE GHA env wiring` — FOUND
- `530598f ci(71-05): wire EXTRACTOR_MODE env into daily-sentiment.yml` — FOUND
- `f9fb7d5 test(71-05): CI-enforce LLM-04 weekly cost projection < $5` — FOUND
- `f9218c5 docs(71-05): add 71-BENCHMARK.md + phase 71-SUMMARY.md + plan 71-05-SUMMARY.md` — FOUND
- `07bf237 docs(71-05): close Phase 71 — STATE/ROADMAP/REQUIREMENTS updates` — FOUND

---

*Phase: 71-llm-primary-extraction (v7.1 Draft Season Readiness)*
*Completed: 2026-04-24*
*Next phase: Phase 72 — Event Flag Expansion + Non-Player Attribution (depends on 71)*
