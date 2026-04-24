---
phase: 71-llm-primary-extraction
verified: 2026-04-24T23:10:00Z
status: passed
score: 25/25 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps: []
deferred:
  - truth: "Non-player attribution routing (team-rollup vs separate channel decision)"
    addressed_in: "Phase 72"
    evidence: "71-SUMMARY.md Deferred section explicitly tags EVT-02 to Phase 72; Phase 71 captures non_player items into data/silver/sentiment/non_player_pending/ as scaffolding only"
  - truth: "New event flags (is_drafted, is_rumored_destination, is_coaching_change, is_trade_buzz, is_holdout, is_cap_cut, is_rookie_buzz)"
    addressed_in: "Phase 72"
    evidence: "REQUIREMENTS.md EVT-01 assigned to Phase 72; 71-SUMMARY.md notes Claude already emits them inside events dict but surfacing as first-class booleans is deferred"
  - truth: "tests/sentiment/test_ingest_pft.py + test_ingest_rotowire.py live-RSS write isolation"
    addressed_in: "v7.x tech debt (unscheduled)"
    evidence: "deferred-items.md explicitly logs this as pre-existing (not introduced by 71-04/71-05); retrofit candidate documented"
  - truth: "tests/test_daily_pipeline.py::TestFailureIsolation::test_all_fail_returns_exit_code_1 passes"
    addressed_in: "separate ticket"
    evidence: "deferred-items.md verified against baseline commit 18593fd (pre-71-04); failure exists on main before Phase 71 began"
---

# Phase 71: LLM-Primary Extraction Verification Report

**Phase Goal:** Convert `src/sentiment/processing/extractor.py` from rule-primary + LLM-enrichment-only to LLM-primary with rule fallback. Offseason Bronze content (drafts/trades/coaching/rookie buzz) must produce signals instead of silent zeros. Preserve dev-mode zero-cost path.

**Verified:** 2026-04-24T23:10Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ClaudeExtractor exists as a peer to RuleExtractor, producing raw-Bronze signals (not enrichment) | VERIFIED | `src/sentiment/processing/extractor.py` lines 399+ defines `class ClaudeExtractor` with `extract_batch_primary(docs, season, week)` at line 993 returning `(by_doc_id, non_player_items)` — produces `PlayerSignal` instances directly from Bronze docs, not from pre-existing rule signals. Constructor DI: `client`, `roster_provider`, `cost_log`, `batch_size`. |
| 2 | Re-running pipeline on 2025 W17+W18 with claude_primary produces ≥5× more signals than rule-based; measured + committed | VERIFIED | `71-BENCHMARK.md` line 21: rule=28, claude=156, ratio=5.57× (gate ≥ 5.0× — PASS). Fixture commit `925d52e51a875cee65ba916ea21217654023d113`. Test `tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason` PASSED in 0.67s. |
| 3 | Prompt-cache the player list across docs; target <$5/week at 80 docs/day | VERIFIED | `cache_control: {'type': 'ephemeral'}` markers present in `extractor.py` at lines 376 and 384 on system prefix + ACTIVE PLAYERS roster block. CI-enforced gate `tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars` PASSED — warm-cache projection $1.5700/week, cold-cache $1.7251/week. |
| 4 | Deterministic tests via recorded Claude responses — no live API in CI | VERIFIED | `tests/sentiment/fakes.py::FakeClaudeClient` replays SHA-256-keyed responses from `tests/fixtures/claude_responses/offseason_batch_w{17,18}.json`. README.md documents strict no-live-API contract. All 165 sentiment tests pass without ANTHROPIC_API_KEY. |
| 5 | RuleExtractor preserved for dev + API-outage scenarios (ENABLE_LLM_ENRICHMENT=false is zero-cost) | VERIFIED | `SentimentPipeline._resolve_extractor_mode` (pipeline.py line 230) defaults to "auto" when EXTRACTOR_MODE env unset or empty. Legacy loop `_run_legacy_loop` is byte-identical to pre-71 logic per 71-SUMMARY.md. Per-doc soft fallback in `_run_claude_primary_loop` (line 922) catches batch failures and routes to RuleExtractor via `_fallback_per_doc`. |

**Score:** 5/5 truths verified

### Per-Plan Must-Haves Checklist

**Plan 71-01 (Schema & Contracts):**

| # | Must-have | Status | Evidence |
|---|-----------|--------|----------|
| 1 | PlayerSignal carries optional `summary`, `source_excerpt`, `team_abbr`, `extractor` fields; existing fields unchanged | VERIFIED | extractor.py lines 232-235; smoke test confirmed defaults (`""`, `""`, `None`, `"rule"`). |
| 2 | Silver signal records carry optional top-level `extractor` field (rule | claude_primary | claude_legacy), default `rule` | VERIFIED | pipeline.py line 577 `"extractor": signal.extractor` inside `_build_silver_record`; test_schema_contracts.py tests at lines 195, 227. |
| 3 | PipelineResult exposes claude_failed_count, unresolved_player_count, non_player_count, non_player_items, is_claude_primary, cost_usd_total | VERIFIED | All 6 fields present on dataclass (smoke-tested via `dataclasses.fields(PipelineResult)`). Defaults preserve prior behavior. |
| 4 | ClaudeClient Protocol exists in extractor module | VERIFIED | extractor.py line 284 `class ClaudeClient(Protocol)`. Smoke test confirms `_is_protocol=True` and exposes `messages` attribute. |

**Plan 71-02 (Fixtures & Fake Client):**

| # | Must-have | Status | Evidence |
|---|-----------|--------|----------|
| 5 | FakeClaudeClient replays recorded Claude JSON keyed by SHA-256 of prompt | VERIFIED | `tests/sentiment/fakes.py` (16346 bytes) — `FakeClaudeClient`, `FakeMessages`, `FakeMessageResponse`, `from_fixture_dir`, SHA-256 canonicalization. |
| 6 | Recorded 2025 W17+W18 offseason Bronze fixture of ≥30 documents | VERIFIED | `tests/fixtures/bronze_sentiment/offseason_w17_w18.json` (16638 bytes) — 30 docs confirmed per 71-BENCHMARK.md (15 W17 + 15 W18). |
| 7 | Recorded Claude response fixtures exist for each batch | VERIFIED | `offseason_batch_w17.json` (27275 bytes, cold-cache with cache_creation>0), `offseason_batch_w18.json` (26755 bytes, warm-cache with cache_read>0). |
| 8 | Fake client exposes `.messages.create(...)` surface matching anthropic.Anthropic | VERIFIED | Protocol check passes (runtime_checkable). DI works through ClaudeClient Protocol per test_schema_contracts.py::test_claude_client_protocol_runtime_check. |

**Plan 71-03 (Batched Extractor + CostLog):**

| # | Must-have | Status | Evidence |
|---|-----------|--------|----------|
| 9 | ClaudeExtractor.extract_batch_primary produces PlayerSignal from raw Bronze docs (not enrichment) | VERIFIED | extractor.py line 993 `def extract_batch_primary(docs, season, week)`. Signals tagged `extractor="claude_primary"` at line 779. |
| 10 | Batched call uses prompt caching: static system prefix + active-roster list cached via cache_control ephemeral | VERIFIED | extractor.py lines 376 & 384 — both blocks marked `cache_control: {"type": "ephemeral"}`. Benchmark fixture W18 shows `cache_read > 0`, confirming cache hit path. |
| 11 | Per-doc soft fallback: extract_batch_primary raises on batch failure; malformed JSON items logged and dropped | VERIFIED | Lines 825, 834, 855, 894, 1042 show JSON parse error handling, array validation, unmatched item skipping. Plan 71-04 `_run_claude_primary_loop` catches and falls back. |
| 12 | Non-player items (player_name: null) captured separately via return tuple | VERIFIED | extract_batch_primary returns `Tuple[Dict[str, List[PlayerSignal]], List[Dict]]`. Non-player items routed to `data/silver/sentiment/non_player_pending/` (pipeline.py line 71). |
| 13 | Per-call cost computed via HAIKU_4_5_RATES and written to data/ops/llm_costs/season=YYYY/week=WW/ | VERIFIED | cost_log.py: `HAIKU_4_5_RATES` (input $1, output $5, cache_read $0.10, cache_creation $1.25 per 1M tokens), `compute_cost_usd()`, `CostLog.write_record()` writing Parquet with `running_total_usd()` aggregator. |
| 14 | Extractor accepts client: ClaudeClient via constructor DI | VERIFIED | ClaudeExtractor.__init__ signature: `['self', 'model', 'client', 'roster_provider', 'cost_log', 'batch_size']`. |

**Plan 71-04 (Pipeline Wiring):**

| # | Must-have | Status | Evidence |
|---|-----------|--------|----------|
| 15 | _build_extractor('claude_primary') returns ClaudeExtractor configured with CostLog + roster_provider reading latest bronze rosters | VERIFIED | pipeline.py lines 275-318 and `_roster_provider_factory` at line 320+ reading `data/bronze/players/rosters/season=YYYY/` per SUMMARY. |
| 16 | __init__(extractor_mode='claude_primary') sets result.is_claude_primary=True | VERIFIED | pipeline.py line 205 `self._is_claude_primary = ...`, line 782 `result.is_claude_primary = self._is_claude_primary`. |
| 17 | Pipeline.run() batches docs via extract_batch_primary when claude_primary; per-doc soft fallback on batch raise | VERIFIED | `_run_claude_primary_loop` at line 922, batch try/except at 984-998 increments `claude_failed_count += len(batch)` then calls `_fallback_per_doc`. |
| 18 | Unresolved names + non-player items written to data/silver/sentiment/{unresolved_names,non_player_pending}/ | VERIFIED | pipeline.py lines 68 + 71 define both sinks. Tests at test_pipeline_claude_primary.py exercise the sinks. |
| 19 | enrich_silver_records() short-circuits when is_claude_primary=true (no-op) | VERIFIED | `src/sentiment/enrichment/llm_enrichment.py` lines 391-400 explicit short-circuit: `if bool(data.get("is_claude_primary", False)): ... return 0`. |
| 20 | Existing auto + rule modes byte-identical to pre-71 (regression locked) | VERIFIED | 165-test suite passes including pre-71 75-test baseline. `_run_legacy_loop` preserves per-doc extraction logic. |
| 21 | EXTRACTOR_MODE env var read when extractor_mode arg is default 'auto'; explicit arg wins | VERIFIED | `_resolve_extractor_mode` at line 230: arg-mode != 'auto' short-circuits env read (constructor arg wins); `EXTRACTOR_MODE` env read only when arg mode is 'auto'. |

**Plan 71-05 (CLI + GHA + Benchmark):**

| # | Must-have | Status | Evidence |
|---|-----------|--------|----------|
| 22 | `process_sentiment.py --extractor-mode claude_primary` routes through claude_primary | VERIFIED | scripts/process_sentiment.py lines 148 (`--extractor-mode`) + 159 (`--mode` alias, dest=extractor_mode). Line 233 passes to `pipeline_kwargs["extractor_mode"]`. |
| 23 | --mode alias accepted | VERIFIED | Line 159-163 argparse with `dest="extractor_mode"` + help "Short alias for --extractor-mode." |
| 24 | CLI arg wins over EXTRACTOR_MODE env; INFO log documents precedence | VERIFIED | Lines 208-236 show CLI arg check + log message "CLI arg --extractor-mode=%s wins over EXTRACTOR_MODE env". |
| 25 | daily-sentiment.yml sets EXTRACTOR_MODE=claude_primary when ENABLE_LLM_ENRICHMENT=true | VERIFIED | `.github/workflows/daily-sentiment.yml` lines 105 & 124: `EXTRACTOR_MODE: ${{ (vars.ENABLE_LLM_ENRICHMENT == 'true') && 'claude_primary' || '' }}`. |
| 26 | LLM-04 cost gate CI-enforced via test_cost_projection.py | VERIFIED | Test PASSED in isolated run. Uses `HAIKU_4_5_RATES` + fixture token counts. All 4 cost tests green. |
| 27 | 71-BENCHMARK.md records claude/rule ratio ≥5x | VERIFIED | File exists, ratio 5.57x, gate PASS. |
| 28 | 71-SUMMARY.md captures fixture commit hash, cost projection, full file list | VERIFIED | Complete SUMMARY with commit 925d52e, $1.5700/week warm-cache, 16 created + 6 modified files, all 5 requirements table. |

**Score:** 25/25 plan-level must-haves verified (exceeds roadmap 5/5; granular breakdown above).

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|--------------|----------|
| 1 | Non-player attribution routing (team rollup vs separate channel) | Phase 72 (EVT-02) | 71-SUMMARY.md Deferred table + REQUIREMENTS.md EVT-02 explicitly assigned to Phase 72. Phase 71 captures non-player items into `data/silver/sentiment/non_player_pending/` as raw scaffolding for Phase 72 to design routing. |
| 2 | New event flags (is_drafted, is_rumored_destination, is_coaching_change, is_trade_buzz, is_holdout, is_cap_cut, is_rookie_buzz) | Phase 72 (EVT-01) | REQUIREMENTS.md EVT-01 assigned to Phase 72. 71-SUMMARY.md notes Claude already emits them inside `events` dict — only the schema promotion to first-class booleans is deferred. |
| 3 | Live-Bronze write isolation in test_ingest_{pft,rotowire}.py | v7.x tech debt | deferred-items.md verifies these tests hit live RSS feeds pre-71 and are pre-existing. Retrofit pattern documented (monkeypatch `_BRONZE_DIR` to tmp_path). |
| 4 | test_daily_pipeline.py::test_all_fail_returns_exit_code_1 | separate ticket | deferred-items.md verifies failure pre-dates Phase 71 via baseline commit 18593fd. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/sentiment/processing/extractor.py` | ClaudeExtractor, extract_batch_primary, ClaudeClient Protocol, BATCH_SIZE, _EXTRACTOR_NAME_* | VERIFIED | 43790 bytes; all symbols confirmed via grep + import smoke test. |
| `src/sentiment/processing/pipeline.py` | claude_primary branch, EXTRACTOR_MODE env read, _run_claude_primary_loop, PipelineResult extensions | VERIFIED | 45754 bytes; all 11 PipelineResult fields present; _resolve_extractor_mode at line 230. |
| `src/sentiment/processing/cost_log.py` | CostLog, CostRecord, HAIKU_4_5_RATES, compute_cost_usd, write_record, running_total_usd | VERIFIED | 11209 bytes; exports all at lines 301-304. |
| `src/sentiment/processing/rule_extractor.py` | Preserved for fallback | VERIFIED | 18052 bytes; untouched since April 17. |
| `src/sentiment/enrichment/llm_enrichment.py` | Short-circuit when is_claude_primary=true | VERIFIED | 16607 bytes; short-circuit at line 391-400. |
| `scripts/process_sentiment.py` | --extractor-mode + --mode CLI args | VERIFIED | Lines 148, 159 argparse; 233 passes to pipeline. |
| `.github/workflows/daily-sentiment.yml` | EXTRACTOR_MODE env conditional on ENABLE_LLM_ENRICHMENT | VERIFIED | Lines 105, 124; gated on vars.ENABLE_LLM_ENRICHMENT='true'. |
| `tests/sentiment/fakes.py` | FakeClaudeClient with SHA-256 keying, token counts, retry hooks | VERIFIED | 16346 bytes. |
| `tests/sentiment/test_extractor_benchmark.py` | 5x claude/rule gate test | VERIFIED | 3909 bytes; test PASSED 0.67s with rule=28 claude=156. |
| `tests/sentiment/test_cost_projection.py` | Weekly cost projection < $5 gate | VERIFIED | 6997 bytes; 4 tests PASSED. |
| `tests/fixtures/claude_responses/README.md` | Re-recording protocol + SHA keying docs | VERIFIED | 5991 bytes; documents LLM-05 contract, lambda:[] roster contract. |
| `tests/fixtures/claude_responses/offseason_batch_w17.json` | W17 recorded Claude response | VERIFIED | 27275 bytes; cold-cache fixture. |
| `tests/fixtures/claude_responses/offseason_batch_w18.json` | W18 recorded Claude response | VERIFIED | 26755 bytes; warm-cache fixture. |
| `tests/fixtures/bronze_sentiment/offseason_w17_w18.json` | 30-doc Bronze fixture | VERIFIED | 16638 bytes. |
| `.planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` | 5x ratio evidence | VERIFIED | 3319 bytes; ratio 5.57x, fixture commit 925d52e. |
| `.planning/phases/71-llm-primary-extraction/71-SUMMARY.md` | Phase summary with cost + ratio + fixtures | VERIFIED | 19347 bytes; all 5 requirements covered + full changelog. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tests/sentiment/test_schema_contracts.py` | `extractor.py` PlayerSignal/ClaudeClient | `from src.sentiment.processing.extractor import` | WIRED | test_schema_contracts.py::test_claude_client_protocol_importable passes. |
| `pipeline.py::_build_silver_record` | `PlayerSignal.extractor` | `"extractor": signal.extractor` serialization | WIRED | Line 577 + 1088. |
| `tests/sentiment/fakes.py::FakeClaudeClient` | `ClaudeClient` Protocol | Structural duck-typing via `.messages.create(...)` | WIRED | runtime_checkable Protocol verified. |
| `fakes.py` | `tests/fixtures/claude_responses/*.json` | `hashlib.sha256` key lookup | WIRED | `from_fixture_dir` loader exercised by all 165 tests. |
| `ClaudeExtractor.__init__` | `ClaudeClient` Protocol | Constructor DI param `client: Optional[ClaudeClient]` | WIRED | Signature confirmed via inspect. |
| `ClaudeExtractor.extract_batch_primary` | `data/ops/llm_costs/season=YYYY/week=WW/` | `cost_log.write_record(CostRecord(...))` | WIRED | Line 1102; CostLog writes Parquet partition. |
| `test_batched_claude_extractor.py` | `offseason_batch_w17.json` | `FakeClaudeClient.from_fixture_dir` | WIRED | Test file 16475 bytes exercises fixture replay. |
| `SentimentPipeline._build_extractor` | `ClaudeExtractor.__init__` | Instantiation in claude_primary branch | WIRED | pipeline.py lines 275-318. |
| `SentimentPipeline.run` | `ClaudeExtractor.extract_batch_primary` | BATCH_SIZE chunks | WIRED | `_run_claude_primary_loop` line 922-1029. |
| `enrich_silver_records` | envelope `is_claude_primary` field | Early-return when flag set | WIRED | llm_enrichment.py lines 391-400. |
| `SentimentPipeline._write_silver_file` | `PipelineResult.is_claude_primary` | Propagates into envelope JSON | WIRED | pipeline.py lines 587, 628-629. |
| `scripts/process_sentiment.py::main` | `SentimentPipeline(extractor_mode=...)` | `pipeline_kwargs["extractor_mode"]` | WIRED | Lines 232-236. |
| `daily-sentiment.yml` | `EXTRACTOR_MODE` env | Workflow env: block on pipeline step | WIRED | Lines 105, 124. |
| `71-BENCHMARK.md` | `test_extractor_benchmark.py` output | Ratio captured from pytest -s | WIRED | "ratio=5.57x" matches regex; test output block in doc. |
| `test_cost_projection.py` | `cost_log.py HAIKU_4_5_RATES` + W18 fixture | Imports + computes weekly projection | WIRED | Test file 6997 bytes; 4 tests green. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `extract_batch_primary` | PlayerSignal list | Claude API response (prod) / FakeClaudeClient recorded fixture (CI) | Yes — benchmark confirms 156 signals on 30 docs | FLOWING |
| `CostLog.write_record` | CostRecord dataclass | Anthropic response.usage (prod) / FakeMessageResponse.usage (CI) | Yes — Parquet file written per call | FLOWING |
| `_run_claude_primary_loop` | all_records + unresolved_records | Batched Claude path with per-doc fallback | Yes — 165 tests pass including test_pipeline_claude_primary | FLOWING |
| `enrich_silver_records` | skip count | Silver envelope flag | Short-circuit confirmed on is_claude_primary=true | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Sentiment suite green (165 tests) | `python -m pytest tests/sentiment/ --tb=short -q` | `165 passed, 13 warnings in 400.47s` | PASS |
| LLM-03 5x gate | `python -m pytest tests/sentiment/test_extractor_benchmark.py -v` | `test_claude_5x_rule_on_offseason PASSED` | PASS |
| LLM-04 cost gate | `python -m pytest tests/sentiment/test_cost_projection.py -v` | 4 tests PASSED (warm-cache $1.5700/week, cold-cache $1.7251/week, rates-imported-not-hardcoded) | PASS |
| PlayerSignal schema extensions | Python import + dataclass inspection | All 4 new fields present with correct defaults | PASS |
| PipelineResult schema extensions | `dataclasses.fields(PipelineResult)` | All 6 new fields present with correct defaults | PASS |
| ClaudeClient Protocol importable | `from src.sentiment.processing.extractor import ClaudeClient` | runtime_checkable Protocol, has `messages` attr | PASS |
| BATCH_SIZE constant | import + read | `BATCH_SIZE = 8` | PASS |
| HAIKU_4_5_RATES constant | import + read | `{input: 1.0, output: 5.0, cache_read: 0.1, cache_creation: 1.25}` | PASS |
| Extractor name constants | import + read | `rule`, `claude_primary`, `claude_legacy` | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| **LLM-01** | 71-01, 71-03 | ClaudeExtractor as peer to RuleExtractor; produces structured signals from raw Bronze | SATISFIED | `extract_batch_primary` at extractor.py line 993; PlayerSignal carries `summary`, `events` dict, `extractor="claude_primary"`. Signals produced directly from Bronze docs (not enrichment of rules). |
| **LLM-02** | 71-04, 71-05 | Routes to claude_primary when ENABLE_LLM_ENRICHMENT=true; falls back to rule | SATISFIED | `_build_extractor` mode dispatch + `_resolve_extractor_mode` precedence; `--extractor-mode` + `--mode` CLI args; GHA `EXTRACTOR_MODE` env gated on `vars.ENABLE_LLM_ENRICHMENT=='true'`. Per-doc soft fallback on batch failure confirmed (D-06 fail-open). |
| **LLM-03** | 71-03, 71-05 | ≥5x more signals than rule on offseason Bronze; delta committed | SATISFIED | `tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason` — rule=28, claude=156, ratio=5.57x. 71-BENCHMARK.md published with fixture commit `925d52e`. |
| **LLM-04** | 71-03, 71-05 | Batch 5-10 docs; prompt-cache; target <$5/week at 80 docs/day; tracked | SATISFIED | BATCH_SIZE=8; `cache_control=ephemeral` on system prefix + ACTIVE PLAYERS; CostLog Parquet sink at `data/ops/llm_costs/`. CI gate `test_weekly_cost_projection_under_5_dollars` PASS (warm-cache $1.5700/week). |
| **LLM-05** | 71-02, all plans | Rule coverage preserved; Claude tests use recorded fixtures; no live API in CI | SATISFIED | FakeClaudeClient SHA-256 replay; zero ANTHROPIC_API_KEY in CI; all 165 tests pass offline. `_run_legacy_loop` preserves pre-71 rule path. |

All 5 requirements SATISFIED. No orphaned requirements — REQUIREMENTS.md row 67 cross-confirms: "LLM-01 ✓ / LLM-02 ✓ / LLM-03 ✓ / LLM-04 ✓ / LLM-05 ✓ — all shipped".

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | — | — | Clean — no stubs, TODOs, empty-return-only implementations, or hardcoded-empty-data patterns found in any Phase 71 artifact. |

Grep sweep of Phase 71 modified/created files for `TODO|FIXME|XXX|HACK|PLACEHOLDER|placeholder|coming soon|not yet implemented` — no blocking matches. Only informational uses: `_PENDING_WAVE_2_SHA_*` tokens in fixtures README documenting a two-phase recording workflow (intentional, explained in-doc).

### Human Verification Required

None — all must-haves and success criteria verified programmatically via test suite (165 tests, 100% pass), dataclass introspection, file-existence checks, and grep-based wiring traces. No UI, visual, or real-time-service components in Phase 71 scope.

### Gaps Summary

**No gaps.** Phase 71 achieves its goal: `ClaudeExtractor` is now a first-class peer to `RuleExtractor` producing structured offseason signals (5.57x lift on W17+W18 Bronze), with prompt caching ($1.57/week projected, $5 gate CI-enforced), deterministic fixture-driven tests (165 green), GHA + CLI operator access, and a preserved zero-cost rule fallback path.

Scope that sits beyond Phase 71 is explicitly deferred to Phase 72 (non-player routing, new event flag schemas) or logged as pre-existing tech debt (live-RSS test isolation, unrelated daily-pipeline test failure). None of the deferred items block the roadmap goal.

---

*Verified: 2026-04-24T23:10Z*
*Verifier: Claude (gsd-verifier)*
