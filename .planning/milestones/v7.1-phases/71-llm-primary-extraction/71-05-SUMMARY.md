---
phase: 71
plan: 05
subsystem: sentiment-extraction
tags: [cli, gha, ci-gate, cost-projection, benchmark, summary, llm-02, llm-03, llm-04, tdd]
requires:
  - phase: 71-03
    provides: HAIKU_4_5_RATES + compute_cost_usd + BATCH_SIZE + LLM-03 benchmark test producing 5.57× ratio
  - phase: 71-04
    provides: SentimentPipeline.extractor_mode='claude_primary' + EXTRACTOR_MODE env precedence
provides:
  - scripts/process_sentiment.py --extractor-mode / --mode CLI args (mutex group, dest='extractor_mode')
  - .github/workflows/daily-sentiment.yml EXTRACTOR_MODE env on run + health-summary steps
  - tests/sentiment/test_cost_projection.py (CI-enforced LLM-04 weekly cost gate < $5)
  - tests/sentiment/test_process_sentiment_cli.py (CLI parser + main() routing tests)
  - tests/sentiment/test_daily_sentiment_workflow.py (GHA YAML structure tests)
  - 71-BENCHMARK.md (LLM-03 audit trail with ratio + fixture commit hash)
  - 71-SUMMARY.md (phase-level summary with cost projection + files-changed manifest)
affects:
  - daily-sentiment.yml will route to claude_primary on next cron once vars.ENABLE_LLM_ENRICHMENT='true' is flipped
  - Phase 72 (EVT) inherits the cost-gate test as a regression guard for any prompt growth
tech-stack:
  added:
    - "argparse mutex group as the canonical CLI alias pattern (--extractor-mode + --mode share dest)"
  patterns:
    - "Lazy CLI kwarg passthrough — only forward extractor_mode to SentimentPipeline when the operator supplied a CLI override; otherwise let env precedence kick in"
    - "Selective missing-key WARNING — gate the ANTHROPIC_API_KEY warning on modes that actually need it (claude / claude_primary), so rule/auto stay quiet"
    - "GHA expression conditional env: EXTRACTOR_MODE: ${{ (vars.ENABLE_LLM_ENRICHMENT == 'true') && 'claude_primary' || '' }} — empty string falls through to pipeline 'auto' default"
    - "CI cost-projection from imported constants: HAIKU_4_5_RATES + BATCH_SIZE both imported (never hard-coded) so future tuning at source ripples through the test"
    - "TDD RED → GREEN per task with separate test()/feat()/ci() commits"
key-files:
  created:
    - tests/sentiment/test_process_sentiment_cli.py
    - tests/sentiment/test_daily_sentiment_workflow.py
    - tests/sentiment/test_cost_projection.py
    - .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md
    - .planning/phases/71-llm-primary-extraction/71-SUMMARY.md
  modified:
    - scripts/process_sentiment.py
    - .github/workflows/daily-sentiment.yml
    - .planning/phases/71-llm-primary-extraction/deferred-items.md
key-decisions:
  - "CLI default is None (NOT 'auto') so main() can detect 'no override' and skip passing the kwarg. Passing 'auto' would clobber the EXTRACTOR_MODE env precedence Plan 71-04 built — keeping default None preserves the env path."
  - "Missing-key WARNING gated on _MODES_REQUIRING_API_KEY = {'claude', 'claude_primary'}. rule / auto / unset don't need the key — nagging would be noise. The test_rule_mode_does_not_warn test enforces this."
  - "GHA EXTRACTOR_MODE expression returns empty string when LLM enrichment is off. Pipeline's _resolve_extractor_mode treats empty as 'auto', so the off-state is byte-identical to no env var — operationally clean rollback path."
  - "Health-summary step echoes '::notice::Extractor mode: ...' so reviewers see the active path in the Actions UI without diffing repo vars. Defaults to 'auto (rule-primary)' when EXTRACTOR_MODE is empty."
  - "Cost test imports BATCH_SIZE from src.sentiment.processing.extractor — NEVER hard-codes 8 — so a future BATCH_SIZE change at the source ripples through the projection automatically."
  - "Cost test uses W18 warm-cache fixture (cache_read > 0, cache_creation == 0) for the gate; W17 cold-cache is informational only. Cold-cache is the worst case (once per season); warm is steady state."
  - "Cost gate is < $5/week (LLM-04 contract); current projection $1.5700/week leaves 69% budget headroom. A future regression (bigger prompt, smaller batch, rate hike, fixture re-record at higher tokens) trips CI."
patterns-established:
  - "Argparse mutex group with shared dest= as the standard CLI alias pattern for this codebase"
  - "GHA env propagation pattern: vars.ENABLE_LLM_ENRICHMENT gates the destination; empty-string fallthrough to pipeline default is operationally cleaner than absent-key shape"
  - "CI gate test for budget contracts: import constants from production code, derive projection, assert with actionable failure message"
requirements-completed:
  - LLM-02 (CLI + env routing now operator-accessible end-to-end)
  - LLM-03 (5.57× ratio captured in 71-BENCHMARK.md with fixture commit hash)
  - LLM-04 (CI-enforced gate via test_weekly_cost_projection_under_5_dollars; warm-cache projection $1.5700/week)
metrics:
  duration: ~1 hour wall-clock
  completed: "2026-04-24"
  tasks: 4
  files_created: 5
  files_modified: 3
  tests_added: 28
  tests_total_suite: 165
---

# Phase 71 Plan 05: CLI + GHA + Benchmark + Cost Gate + Phase Summary

**Exposed `claude_primary` mode to operators via CLI (`--extractor-mode` / `--mode`) and GHA workflow env (`EXTRACTOR_MODE`); promoted the LLM-04 budget contract from documentary to CI-enforced via a pytest assertion; captured the LLM-03 5.57× benchmark to a permanent audit-trail doc; produced the phase-level SUMMARY.md aggregating all 5 plans' evidence.**

## Performance

- **Duration:** ~1 hour wall-clock
- **Tasks:** 4 (Tasks 1-3 each TDD RED → GREEN; Task 4 docs-only)
- **Commits:** 5 atomic (3 RED + 2 GREEN/CI/test for Tasks 1-3, plus this plan-SUMMARY commit)
- **Files created:** 5 (3 test modules + 2 planning docs)
- **Files modified:** 3 (scripts/process_sentiment.py, .github/workflows/daily-sentiment.yml, deferred-items.md)
- **Tests added:** 28 (CLI 16 + GHA 8 + cost projection 4)
- **Sentiment suite total:** 165 passed (up from 137 baseline)

## Accomplishments

### 1. CLI args (Task 1)

`scripts/process_sentiment.py` extended with a `--extractor-mode` / `--mode` mutex group and lazy kwarg routing:

- **Mutex group** in `_build_parser()` — both args share `dest='extractor_mode'`, so passing both raises an argparse error (exit 2). Choices: `auto | rule | claude | claude_primary`.
- **Default `None`** (NOT `"auto"`) — critical so `main()` can detect "no override" and skip passing the kwarg. Preserves the `EXTRACTOR_MODE` env precedence path Plan 71-04 built.
- **`main()` lazy kwarg dict:** `pipeline_kwargs = {}; if extractor_mode is not None: pipeline_kwargs["extractor_mode"] = extractor_mode; pipeline = SentimentPipeline(**pipeline_kwargs)`. Logs INFO line documenting CLI > env precedence when arg is set.
- **Missing-key warning gated to `_MODES_REQUIRING_API_KEY = {"claude", "claude_primary"}`** — rule/auto don't need the key, no nagging.
- **Module docstring** updated with `--extractor-mode claude_primary` / `--mode rule` examples and a precedence section.

Tests added: 16 in `tests/sentiment/test_process_sentiment_cli.py` covering parser-level (parse, alias, mutex error, invalid value, default None, --help mentions claude_primary) and main()-level routing (kwarg presence, alias equivalence, warning gating, INFO log on precedence).

### 2. GHA workflow env (Task 2)

`.github/workflows/daily-sentiment.yml` extended with `EXTRACTOR_MODE` on two steps:

- **"Run daily sentiment pipeline" step env:** `EXTRACTOR_MODE: ${{ (vars.ENABLE_LLM_ENRICHMENT == 'true') && 'claude_primary' || '' }}` — empty string when off, `claude_primary` when on. Pipeline's `_resolve_extractor_mode` treats empty as `"auto"`, so off-state is byte-identical to no env var.
- **"Log pipeline health summary" step:** Same expression in env + `echo "::notice::Extractor mode: ${EXTRACTOR_MODE:-auto (rule-primary)}"` in the run script. Operators see the active path in the Actions UI without diff'ing repo vars.
- **Comment block** in the run-step env documents Phase 71 LLM-02 routing + per-doc soft fallback safety.
- **Preserved:** `permissions.contents=write`, `permissions.issues=write`, `concurrency.group='daily-sentiment'`, `cancel-in-progress=false`, `notify-failure` job, all other steps.

Tests added: 8 in `tests/sentiment/test_daily_sentiment_workflow.py` covering YAML parse, permissions intact, concurrency intact, EXTRACTOR_MODE wired on both steps, env-key preservation, no literal sk-ant- key patterns, notify-failure job preserved.

### 3. CI cost gate (Task 3)

`tests/sentiment/test_cost_projection.py` promotes the LLM-04 budget contract from documentary to CI-enforced:

- **Imports `HAIKU_4_5_RATES` + `compute_cost_usd`** from `src.sentiment.processing.cost_log` (Plan 71-03).
- **Imports `BATCH_SIZE`** from `src.sentiment.processing.extractor` (Plan 71-01) — never hard-coded.
- **Loads W18 warm-cache fixture** at `tests/fixtures/claude_responses/offseason_batch_w18.json` for the per-call token counts.
- **Computes** `weekly_cost = compute_cost_usd(tokens) × (DOCS_PER_DAY=80 / BATCH_SIZE) × DAYS_PER_WEEK=7`.
- **Asserts** `weekly_cost < 5.0` with an actionable failure message that includes per-call cost, batches/day breakdown, and token counts.

Current projections at fixture token counts:
- W18 warm-cache (steady state, gate basis): **$0.022428/call → $1.5700/week**
- W17 cold-cache (worst case, once per season): **$0.024645/call → $1.7251/week**

Both well under the $5/week LLM-04 gate. A future regression — bigger prompts, smaller batch, rate hike, or fixture re-record at higher token counts — fails the test in CI.

Tests added: 4 in `test_cost_projection.py`:
- `test_weekly_cost_projection_under_5_dollars` (the gate)
- `test_cost_projection_uses_warm_cache_fixture` (W18 shape contract — cache_read>0, cache_creation==0)
- `test_cold_cache_week_one_is_documented` (informational, prints cold-cache projection)
- `test_haiku_rates_table_imported_not_hardcoded` (rate-dict shape guard)

### 4. Benchmark + Phase SUMMARY (Task 4)

- **`71-BENCHMARK.md`** captures the LLM-03 evidence: `rule=28 claude=156 ratio=5.57x` against fixture commit `925d52e51a875cee65ba916ea21217654023d113`. Includes reproduction command, determinism contract documentation (`roster_provider=lambda: []`), and cross-reference to the LLM-04 cost gate.
- **`71-SUMMARY.md`** aggregates all 5 plans' evidence: requirements coverage table (LLM-01..05 all DONE), per-plan commit summary, files-changed manifest (16 created + 6 modified), cost projection breakdown with input/output/cache token tables, operational notes (how to enable in production, ad-hoc CLI runs, fixture re-recording, API-outage behavior), Phase-72 deferred items, risks/watchouts.
- **`71-05-SUMMARY.md`** (this file) documents the per-plan deltas.

## Task Commits

| Task | Phase | Commit |
|------|-------|--------|
| 1 RED — CLI test | RED | `74516f1 test(71-05): add failing tests for --extractor-mode/--mode CLI args` |
| 1 GREEN — CLI impl | GREEN | `c009666 feat(71-05): add --extractor-mode/--mode CLI args to process_sentiment.py` |
| 2 RED — GHA test | RED | `861ab49 test(71-05): add failing tests for EXTRACTOR_MODE GHA env wiring` |
| 2 GREEN — GHA impl | GREEN | `530598f ci(71-05): wire EXTRACTOR_MODE env into daily-sentiment.yml` |
| 3 — Cost gate test | GREEN | `f9fb7d5 test(71-05): CI-enforce LLM-04 weekly cost projection < $5` |
| 4 — Benchmark + SUMMARY | docs | (this commit — covers 71-BENCHMARK.md, 71-SUMMARY.md, 71-05-SUMMARY.md, and STATE/ROADMAP/REQUIREMENTS updates) |

Task 3 (cost gate) is a single test commit because the test passes against the current fixtures on first run — there's no failing→passing transition since the actual cost is well under the gate. The "RED" semantics in TDD apply when implementing new behavior; here the test is verifying an existing budget property of upstream code.

## Acceptance Criteria

All automated checks from the plan passed:

### Task 1
- [x] `grep -n "\\-\\-extractor-mode" scripts/process_sentiment.py` returns at least 1 hit (10 hits)
- [x] `grep -n "\\-\\-mode" scripts/process_sentiment.py` returns at least 1 hit (10 hits)
- [x] `grep -n "add_mutually_exclusive_group" scripts/process_sentiment.py` returns 1 hit
- [x] `grep -n "claude_primary" scripts/process_sentiment.py` returns at least 2 hits (4 hits)
- [x] `python scripts/process_sentiment.py --help 2>&1 | grep -qE "\\-\\-extractor-mode.*claude_primary"` exits 0
- [x] `python scripts/process_sentiment.py --season 2025 --week 17 --extractor-mode nonsense 2>&1; test $? -eq 2` exits 0
- [x] `python scripts/process_sentiment.py --season 2025 --week 17 --extractor-mode claude_primary --mode rule 2>&1; test $? -eq 2` exits 0 (mutex error)
- [x] `python -m pytest tests/sentiment/test_process_sentiment_cli.py -v` — 16 tests pass

### Task 2
- [x] `grep -n "EXTRACTOR_MODE" .github/workflows/daily-sentiment.yml` returns at least 2 hits (4 hits)
- [x] `grep -n "claude_primary" .github/workflows/daily-sentiment.yml` returns at least 1 hit (3 hits)
- [x] One-liner verification: `python -c "import yaml; ... assert 'EXTRACTOR_MODE' in s['env'] and 'claude_primary' in str(s['env']['EXTRACTOR_MODE'])"` exits 0
- [x] `python -m pytest tests/sentiment/test_daily_sentiment_workflow.py -v` — 8 tests pass
- [x] Permissions preserved (yaml shows `contents: write` and `issues: write`)
- [x] No literal API key patterns in workflow file

### Task 3
- [x] `test -f tests/sentiment/test_cost_projection.py` exits 0
- [x] `grep -n "test_weekly_cost_projection_under_5_dollars" tests/sentiment/test_cost_projection.py` returns 1 hit
- [x] `grep -n "HAIKU_4_5_RATES\|compute_cost_usd" tests/sentiment/test_cost_projection.py` returns at least 1 hit (11 hits)
- [x] `grep -n "from src.sentiment.processing.extractor import BATCH_SIZE" tests/sentiment/test_cost_projection.py` returns 1 hit
- [x] `grep -n "offseason_batch_w18.json" tests/sentiment/test_cost_projection.py` returns 1 hit (2 hits incl. docstring)
- [x] `grep -n "80" tests/sentiment/test_cost_projection.py` returns at least 1 hit (4 hits)
- [x] `python -m pytest tests/sentiment/test_cost_projection.py -v` — 4 tests pass
- [x] `python -m pytest tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars -v` passes in isolation

### Task 4
- [x] `test -f .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` exits 0
- [x] `test -f .planning/phases/71-llm-primary-extraction/71-SUMMARY.md` exits 0
- [x] `grep -E "ratio=[0-9]+\\.[0-9]+x" 71-BENCHMARK.md` returns hit (`ratio=5.57x`)
- [x] `grep -E "PASS|>= 5\\.0x" 71-BENCHMARK.md` returns hit
- [x] `grep -qE "Cost Projection" 71-SUMMARY.md` exits 0
- [x] `grep -qE "71-BENCHMARK\\.md" 71-SUMMARY.md` exits 0
- [x] `grep -qE "ENABLE_LLM_ENRICHMENT|EXTRACTOR_MODE" 71-SUMMARY.md` exits 0
- [x] `grep -qE "test_weekly_cost_projection_under_5_dollars" 71-SUMMARY.md` exits 0
- [x] Benchmark file contains 40-char fixture commit hash: `925d52e51a875cee65ba916ea21217654023d113`
- [x] LLM-05 confirmation: full sentiment suite passes (165 passed)

## Decisions Made

- **CLI default is `None`, not `"auto"`** — critical so the operator's choice flows through correctly. With `default="auto"`, the kwarg would always be passed to `SentimentPipeline.__init__` and clobber the `EXTRACTOR_MODE` env precedence Plan 71-04 designed. Keeping default `None` lets `main()` detect "no override" and skip the kwarg entirely, preserving env-driven routing for the daily cron.
- **Missing-key warning gated on mode** — rule/auto/unset don't need ANTHROPIC_API_KEY; only claude/claude_primary do. `_MODES_REQUIRING_API_KEY = {"claude", "claude_primary"}` is the allow-list. Tests verify both directions: rule mode is silent, claude_primary mode warns.
- **GHA expression returns empty string when off** — operationally cleaner than absent-key shape. Pipeline's `_resolve_extractor_mode` treats empty/missing as `"auto"`, so the off-state is byte-identical to a workflow that never set the env var. Easy rollback: flip `vars.ENABLE_LLM_ENRICHMENT` to `'false'` and the empty-string env collapses harmlessly.
- **Cost test imports BATCH_SIZE, never hard-codes 8** — tracks the source of truth. A future BATCH_SIZE tune (say to 10 or 6) automatically ripples through the cost projection. Test message includes the live BATCH_SIZE in failure output for actionable debugging.
- **Cost test uses W18 warm-cache** — represents steady-state weekly operation. W17 cold-cache is the once-per-season worst case (informational only). Using W17 as the gate would over-project and create false alarms on prompt-template tweaks.
- **Task 3 ships as a single test commit** (not RED→GREEN) because the test verifies an *existing* budget property of upstream code. The pipeline's actual cost is well under the gate; there's no failing→passing transition. RED→GREEN is the right shape when implementing new behavior, not when documenting / asserting an existing property.

## Deviations from Plan

### Auto-fixed Issues

None. Each task's RED commit failed exactly the assertions targeted (Task 1: 13 failures; Task 2: 2 failures); each GREEN commit made them pass without breaking prior tests. Task 3's test passed on first run because the cost projection is well under gate.

### Out-of-scope discoveries (deferred)

- **`tests/sentiment/test_ingest_pft.py` + `test_ingest_rotowire.py` write live RSS data into `data/bronze/sentiment/`** during the full sentiment suite run. Pre-existing — not introduced by Plan 71-05. Logged in `deferred-items.md` for future retrofit (`monkeypatch.setattr(module, "_BRONZE_DIR", tmp_path)` mirrors Plan 71-04's pipeline test convention).

## Issues Encountered

None. TDD flow was clean across Tasks 1-2; Task 3 passed on first run as expected.

## User Setup Required

To activate `claude_primary` in production after Phase 71 ships:

1. Confirm `ANTHROPIC_API_KEY` GitHub Secret is set (already done per v7.0 carry-forward).
2. Set the GitHub Variable: `gh variable set ENABLE_LLM_ENRICHMENT --body 'true'`.
3. Wait for the next daily cron at `0 12 * * *` UTC. Health-summary step will log `::notice::Extractor mode: claude_primary`.
4. Verify cost-log Parquet files appear under `data/ops/llm_costs/season=2026/week=NN/` after the run.

To roll back: `gh variable set ENABLE_LLM_ENRICHMENT --body 'false'`. The next cron runs with `EXTRACTOR_MODE=''` (empty), pipeline falls through to `"auto"` (rule-primary), zero Anthropic spend.

## Next Phase Readiness

**Phase 72 (Event Flag Expansion + Non-Player Attribution) is unblocked.**

Phase 72 inherits:
- The `claude_primary` extraction path (Plan 71-04) producing structured signals from offseason content.
- The `non_player_pending/` Silver sink (Plan 71-04) where Claude already routes coach/reporter/team subjects.
- The `unresolved_names/` Silver sink (Plan 71-04) where unresolvable Claude-extracted names accumulate for human review.
- The cost-projection CI gate (this plan) that catches any prompt regression introduced by event-flag expansion.
- The LLM-03 benchmark test (Plan 71-03) as a regression guard for prompt drift.

**Blockers:** None.

## TDD Gate Compliance

Per-task RED → GREEN sequence verified for Tasks 1 and 2:

| Task | RED commit | GREEN commit |
|------|------------|--------------|
| 1 — CLI args | `74516f1 test(71-05)` (13 failing) | `c009666 feat(71-05)` (16 passing) |
| 2 — GHA env | `861ab49 test(71-05)` (2 failing) | `530598f ci(71-05)` (8 passing) |
| 3 — Cost gate | n/a — single test commit | `f9fb7d5 test(71-05)` (4 passing) |

Task 3 ships as a single test commit because it verifies an existing budget property. The plan's `tdd="true"` semantics apply when implementing new behavior, not when asserting a property of upstream code.

## Threat Model Compliance

All STRIDE threats from the plan addressed:

- **T-71-05-01** (Tampering — invalid `--extractor-mode` value) — mitigated; argparse `choices=` enforcement; exit 2 on bad value; verified by `test_extractor_mode_invalid_value_exits_2`.
- **T-71-05-02** (Information disclosure — workflow leaking API key) — mitigated; `test_no_anthropic_api_key_in_plain_text` greps for sk-ant-... patterns and asserts only the `secrets.ANTHROPIC_API_KEY` reference.
- **T-71-05-03** (DoS — cost overrun in production) — mitigated; CostLog WARNING at >$5/week (Plan 71-03) + CI-enforced gate `test_weekly_cost_projection_under_5_dollars` blocks commits that raise projected cost above $5.
- **T-71-05-04** (Repudiation — LLM-03 gate not documented) — mitigated; `71-BENCHMARK.md` captures ratio + fixture commit hash + pytest output as a permanent audit trail.
- **T-71-05-05** (Repudiation — LLM-04 gate not enforced) — mitigated; `test_weekly_cost_projection_under_5_dollars` promotes the gate from narrative to CI-enforced assertion.

## Known Stubs

None. All added code is first-class production surface. The CLI args, GHA env, and cost-projection test are all production-grade.

## Threat Flags

None. Plan 71-05 is configuration + tests; no new data flows or trust boundaries.

## Self-Check: PASSED

Verified post-write at 2026-04-24:

**Files exist:**
- `scripts/process_sentiment.py` — modified (+84 lines for CLI args + main() routing)
- `.github/workflows/daily-sentiment.yml` — modified (+12 lines for EXTRACTOR_MODE env on 2 steps)
- `tests/sentiment/test_process_sentiment_cli.py` — created (294 lines, 16 tests)
- `tests/sentiment/test_daily_sentiment_workflow.py` — created (144 lines, 8 tests)
- `tests/sentiment/test_cost_projection.py` — created (170 lines, 4 tests)
- `.planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` — created
- `.planning/phases/71-llm-primary-extraction/71-SUMMARY.md` — created (phase-level)
- `.planning/phases/71-llm-primary-extraction/71-05-SUMMARY.md` — this file

**Commits in git log:**
- `74516f1 test(71-05)` — FOUND
- `c009666 feat(71-05)` — FOUND
- `861ab49 test(71-05)` — FOUND
- `530598f ci(71-05)` — FOUND
- `f9fb7d5 test(71-05)` — FOUND

**Test runs:**
- `pytest tests/sentiment/test_process_sentiment_cli.py` — 16 passed
- `pytest tests/sentiment/test_daily_sentiment_workflow.py` — 8 passed
- `pytest tests/sentiment/test_cost_projection.py` — 4 passed
- LLM-03 benchmark: rule=28 claude=156 ratio=5.57x — PASS
- Full sentiment suite: 165 passed (137 baseline + 16 + 8 + 4 = 165 — exact)

---
*Phase: 71-llm-primary-extraction*
*Plan: 05 (final plan in phase)*
*Completed: 2026-04-24*
