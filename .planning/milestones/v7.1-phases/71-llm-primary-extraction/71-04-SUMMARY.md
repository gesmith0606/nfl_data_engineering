---
phase: 71
plan: 04
subsystem: sentiment-extraction
tags: [pipeline-wiring, claude-primary, soft-fallback, env-routing, llm-enrichment-short-circuit, silver-sinks, tdd]
requires:
  - phase: 71-01
    provides: ClaudeClient Protocol + _EXTRACTOR_NAME_CLAUDE_PRIMARY + PipelineResult fields + PlayerSignal extractor field
  - phase: 71-03
    provides: ClaudeExtractor.extract_batch_primary + DI seams (client/cost_log/roster_provider/batch_size) + CostLog Parquet sink
provides:
  - SentimentPipeline.extractor_mode='claude_primary' routing (instance method)
  - SentimentPipeline.cost_log + claude_client constructor kwargs (DI)
  - EXTRACTOR_MODE env var precedence (constructor arg > env > default 'auto')
  - SentimentPipeline._roster_provider_factory(season) — lazy parquet loader
  - SentimentPipeline._run_claude_primary_loop with per-doc soft fallback
  - SentimentPipeline._run_legacy_loop (verbatim extraction of pre-71-04 logic)
  - SentimentPipeline._fallback_per_doc (RuleExtractor pivot on batch failure)
  - SentimentPipeline._build_records_for_signals (resolver + unresolved sink)
  - SentimentPipeline._write_envelope (generic JSON envelope writer)
  - data/silver/sentiment/non_player_pending/ Silver sink (envelope JSON)
  - data/silver/sentiment/unresolved_names/ Silver sink (envelope JSON)
  - Silver signals envelope gains optional 'is_claude_primary': true top-level key
  - LLMEnrichment short-circuits envelopes flagged is_claude_primary=true
affects:
  - 71-05 (release engineering can now exercise EXTRACTOR_MODE=claude_primary end-to-end)
  - 72 (EVT-02 non-player attribution will read from data/silver/sentiment/non_player_pending/)
  - daily-sentiment.yml GHA workflow (EXTRACTOR_MODE env knob is now wired)
tech-stack:
  added:
    - "EXTRACTOR_MODE env var as alternate selection seam (CONTEXT D-02)"
  patterns:
    - "Mode resolution: explicit constructor arg > env var > default 'auto' (single _resolve_extractor_mode helper)"
    - "Per-doc soft fallback to RuleExtractor on batch API failure (D-06 fail-open contract preserved)"
    - "Two split run loops (_run_legacy_loop verbatim + _run_claude_primary_loop new) — zero behaviour drift on auto/rule/claude modes"
    - "Generic _write_envelope helper for parallel sinks (non_player_pending + unresolved_names) with the same partition layout as Silver signals"
    - "Lazy roster parquet loading via Callable[[], List[str]] — fails open to [] on missing dir / column / read error"
    - "@staticmethod → instance method conversion of _build_extractor (back-compat sweep verified: only 1 call site, already inside pipeline.py with self.)"
    - "TDD RED → GREEN per task with separate test() and feat() commits"
key-files:
  created:
    - tests/sentiment/test_pipeline_claude_primary.py
    - tests/sentiment/test_enrichment_short_circuit.py
  modified:
    - src/sentiment/processing/pipeline.py
    - src/sentiment/enrichment/llm_enrichment.py
key-decisions:
  - "EXTRACTOR_MODE env precedence — explicit non-'auto' arg always wins; env only consulted when arg is the default 'auto'. Unknown env values fall through to 'auto' with INFO log (T-71-04-01 mitigation)."
  - "Per-doc soft fallback wraps the entire batch call in try/except; on raise, _rule_fallback (RuleExtractor) processes each doc individually, claude_failed_count += len(batch). Matches D-06 fail-open contract — daily cron must never die from API outage."
  - "_run_legacy_loop is a byte-identical extraction of the prior per-doc loop. Auto/rule/claude modes are regression-locked; only claude_primary mode takes the new path."
  - "Silver envelope gains 'is_claude_primary': true ONLY when set (non-True keys are omitted) so legacy enrichment consumers see the absent-key shape they already handle. enrich_silver_records short-circuits via bool(data.get('is_claude_primary', False))."
  - "Non-player items live in their own envelope at data/silver/sentiment/non_player_pending/season=YYYY/week=WW/non_player_{batch}_{ts}.json — separate from the player-attributed Silver signals so Phase 72 can route them without touching the main signals envelope."
  - "Unresolved names sink at data/silver/sentiment/unresolved_names/season=YYYY/week=WW/unresolved_{batch}_{ts}.json captures Claude-extracted names that PlayerNameResolver couldn't match. Phase 72 will design proper attribution; for now they are logged for human review."
  - "_roster_provider_factory binds the season at construction time (datetime.now().year). Production cron processes the current season; tests inject a fake roster via direct ClaudeExtractor.roster_provider= override after construction."
  - "When claude_primary mode is requested but no client is available (no ANTHROPIC_API_KEY + no DI'd client), the pipeline silently downgrades to RuleExtractor with a WARNING log AND clears self._is_claude_primary so the run loop takes the legacy path. Fail-open per CONTEXT D-02."
patterns-established:
  - "Hermetic Silver writes via monkeypatch on _PROJECT_ROOT + _SILVER_SIGNALS_DIR + _UNRESOLVED_DIR + _NON_PLAYER_DIR + _PROCESSED_IDS_FILE module attrs (mirrors test_llm_enrichment_optional convention)."
  - "FakeClaudeClient via constructor DI (claude_client=) — never monkeypatch _build_client, never read ANTHROPIC_API_KEY in tests."
  - "Mode-resolution helper as @staticmethod for testability without pipeline construction."
requirements-completed:
  - LLM-01 (SentimentPipeline.extractor_mode='claude_primary' active and wired end-to-end)
  - LLM-02 (extractor mode selectable via constructor arg OR EXTRACTOR_MODE env, with arg-wins precedence and fail-open downgrade when no client)
  - LLM-05 (no live API calls in CI — every claude_primary test injects FakeClaudeClient via DI; full sentiment suite passes hermetically)
metrics:
  duration: ~30 min
  completed: "2026-04-24"
  tasks: 3
  files_created: 2
  files_modified: 2
  tests_added: 18
  tests_total_suite: 137
---

# Phase 71 Plan 04: Pipeline Wiring + LLMEnrichment Short-Circuit Summary

**Wired the batched `ClaudeExtractor.extract_batch_primary` from Plan 71-03 into `SentimentPipeline.run()` via a new `claude_primary` extractor mode with EXTRACTOR_MODE env precedence, per-doc soft fallback to RuleExtractor on batch failures, dedicated Silver sinks for non-player items and unresolved Claude-extracted names, and a `LLMEnrichment` short-circuit that prevents double-LLM-cost on Claude-primary envelopes.**

## Performance

- **Duration:** ~30 min
- **Tasks:** 3 (each TDD RED → GREEN)
- **Commits:** 4 atomic (2 RED test() + 2 GREEN feat()); Tasks 1 + 2 share one GREEN commit because both touch pipeline.py
- **Files created:** 2 test modules
- **Files modified:** 2 production modules
- **Tests added:** 18 (13 in test_pipeline_claude_primary.py + 5 in test_enrichment_short_circuit.py)
- **Sentiment suite total:** 137 passed (up from 119; zero regressions)

## Accomplishments

### 1. Mode routing + EXTRACTOR_MODE env + DI seams (Task 1)

`src/sentiment/processing/pipeline.py` extended with:

- **Constructor signature** now accepts `cost_log: Optional[CostLog] = None` and `claude_client: Optional[ClaudeClient] = None` for full DI. Default `cost_log` is `CostLog()` (real partition path); production runs always have cost accounting.
- **`_resolve_extractor_mode(arg_mode)`** — single source of truth for precedence: explicit non-`"auto"` arg > `EXTRACTOR_MODE` env (when arg is the default `"auto"`) > `"auto"` fallback. Unknown env values fall through to `"auto"` with an INFO log (T-71-04-01 mitigation).
- **`_build_extractor` converted from `@staticmethod` to instance method** to access `self._claude_client` and `self._cost_log`. Back-compat sweep: `grep -rn "SentimentPipeline\._build_extractor"` returns zero unbound call sites — the only existing call was already `self._build_extractor(...)` inside `pipeline.py` line 147.
- **`claude_primary` branch** in `_build_extractor`: instantiates `ClaudeExtractor(client=self._claude_client, roster_provider=self._roster_provider_factory(year), cost_log=self._cost_log, batch_size=BATCH_SIZE)`. When `extractor._client is None` (no DI + no env key), logs WARNING, clears `self._is_claude_primary`, returns `RuleExtractor()` (fail-open per CONTEXT D-02).
- **`_roster_provider_factory(season)`** — returns a `Callable[[], List[str]]` that lazily reads the most recent `data/bronze/players/rosters/season=YYYY/*.parquet`, prefers `player_name` then `full_name` columns, caps at 1500 deduped names. Fails open to `[]` on every error (missing dir, missing column, parquet read failure) with a WARNING log.
- **`_rule_fallback`** — a `RuleExtractor` instance constructed only when `_is_claude_primary` is True. Used by Task 2's per-doc soft fallback path.

### 2. Batched run loop + per-doc soft fallback + new sinks (Task 2)

Same file extended with:

- **Module constants** for two new Silver sinks: `_UNRESOLVED_DIR` and `_NON_PLAYER_DIR` (parallel layout to `_SILVER_SIGNALS_DIR`).
- **`run()` refactored** into two branches: `_run_legacy_loop` (byte-identical extraction of pre-71-04 logic — auto/rule/claude modes regression-locked) and `_run_claude_primary_loop` (new batched path).
- **`_run_claude_primary_loop`** — collects all unprocessed docs across every Bronze file, slices into `BATCH_SIZE` chunks, calls `extract_batch_primary` per batch. On success: per-doc signals routed through `_build_records_for_signals` (resolver + unresolved-names sink); non-player items accumulated. On API failure: `claude_failed_count += len(batch)`, every doc in the batch handed to `_fallback_per_doc` which runs `RuleExtractor.extract` (fallback signals carry `extractor="rule"` per PlayerSignal default).
- **`_build_records_for_signals`** — resolves player names; when resolver returns `None`, increments `unresolved_player_count` and appends a JSON-friendly dict (`doc_id`, `player_name`, `team_abbr`, `category`, `summary`, `source_excerpt`, `extractor`) to the `unresolved_records` list passed in by reference. The Silver record is still built (name preserved with `player_id=None`).
- **`_fallback_per_doc`** — defensive RuleExtractor reconstruction (should never trigger because `_is_claude_primary` implies `_rule_fallback` is set in `__init__`); wraps the rule extract call in try/except so a rule-side bug never kills the run.
- **`_write_silver_file` extended** with optional `is_claude_primary: bool = False`. When True, the envelope JSON gains a top-level `"is_claude_primary": true` key. Legacy callers (auto/rule/claude modes) pass the default `False` and the key stays absent — non-breaking for prior consumers.
- **`_write_envelope`** — generic helper for the two new sinks. Same partition layout as `_write_silver_file` (`{base_dir}/season=YYYY/week=WW/{prefix}_{batch_id}_{ts}.json`).
- **`run()` post-processing** — when `is_claude_primary` and `week is not None`, populates `result.cost_usd_total` from `self._cost_log.running_total_usd(season, week)`. Wrapped in try/except so cost accounting can never crash the run.

### 3. LLMEnrichment short-circuit (Task 3)

`src/sentiment/enrichment/llm_enrichment.py` — minimal surgical edit:

- Inside `enrich_silver_records()`, after `_load_silver_envelope(envelope_path)` succeeds, a new `if bool(data.get("is_claude_primary", False)):` branch logs INFO and `continue`s to the next envelope. The check is positioned BEFORE `source_records = data.get("records") or []` so the entire envelope is skipped, not individual records.
- Pre-existing rule envelopes (no `is_claude_primary` key) are unaffected — `data.get("is_claude_primary", False)` returns `False`, skipping the branch entirely.

The module's existing fail-open shape (`is_available`, env/SDK guard, exception swallowing in `enrich`) is preserved.

## Task Commits

| Task | RED commit | GREEN commit |
|------|------------|--------------|
| 1 + 2: Pipeline routing + run loop + sinks | `210d521` test(71-04) | `b25759c` feat(71-04) |
| 3: LLMEnrichment short-circuit | `5a55566` test(71-04) | `284772f` feat(71-04) |

Tasks 1 and 2 share one GREEN commit because both modify `pipeline.py` and the run-loop changes depend on the routing changes; splitting them would have left `pipeline.py` in an inconsistent intermediate state. RED commits cover the full task surface; GREEN commits land the implementation in one passing slice. This matches the Plan 71-03 atomic-test-commit pattern.

## Acceptance Criteria

All automated checks from the plan passed:

### Task 1
- [x] `grep -n "claude_primary" src/sentiment/processing/pipeline.py` returns ≥ 4 hits (29 hits)
- [x] `grep -n "_roster_provider_factory" src/sentiment/processing/pipeline.py` returns ≥ 2 hits (2 hits — def + call)
- [x] `grep -n "EXTRACTOR_MODE" src/sentiment/processing/pipeline.py` returns ≥ 1 hit (5 hits)
- [x] `grep -n "self._rule_fallback\|_rule_fallback" src/sentiment/processing/pipeline.py` returns ≥ 1 hit (5 hits)
- [x] `python -c "from src.sentiment.processing.pipeline import SentimentPipeline; from tests.sentiment.fakes import FakeClaudeClient; p=SentimentPipeline(extractor_mode='claude_primary', claude_client=FakeClaudeClient()); assert p._is_claude_primary is True"` exits 0
- [x] `EXTRACTOR_MODE=claude_primary python -c "...assert p._is_claude_primary is True"` exits 0
- [x] `EXTRACTOR_MODE=rule python -c "...assert type(p._extractor).__name__=='RuleExtractor'"` exits 0
- [x] Legacy auto: `python -c "...assert type(p._extractor).__name__=='RuleExtractor'"` exits 0
- [x] Back-compat sweep: `grep -rn "SentimentPipeline\._build_extractor" src/ scripts/ tests/` returns ZERO unbound call sites; the only call (`self._build_extractor(effective_mode)`) is inside `pipeline.py` with `self.` prefix
- [x] `pytest tests/sentiment/test_pipeline_claude_primary.py tests/sentiment/test_daily_pipeline_resilience.py -v` — 49 passed (13 + 7 + 26 from test_rule_extractor_events.py also run; all green)

### Task 2
- [x] `grep -n "_run_claude_primary_loop\|_run_legacy_loop" src/sentiment/processing/pipeline.py` returns ≥ 4 hits (5 hits — 2 defs + 3 references)
- [x] `grep -n "_UNRESOLVED_DIR\|_NON_PLAYER_DIR" src/sentiment/processing/pipeline.py` returns ≥ 4 hits (5 hits — 2 defs + 3 uses)
- [x] `grep -n "claude_failed_count\s*+=" src/sentiment/processing/pipeline.py` returns ≥ 1 hit (1 hit at line 998)
- [x] `grep -n "non_player_items.extend\|non_player_items.append" src/sentiment/processing/pipeline.py` returns ≥ 1 hit (1 hit at line 1028)
- [x] `grep -n "cost_usd_total\s*=" src/sentiment/processing/pipeline.py` returns ≥ 1 hit (3 hits — dataclass default + run() assignment + docstring)
- [x] Envelope `is_claude_primary` key emitted: line 629 `envelope["is_claude_primary"] = True` (assignment style; verified via test that reads back the JSON envelope)
- [x] `pytest tests/sentiment/test_pipeline_claude_primary.py -v` — 13 tests passed
- [x] Full sentiment suite: 137 passed

### Task 3
- [x] `grep -n "is_claude_primary" src/sentiment/enrichment/llm_enrichment.py` returns ≥ 1 hit (2 hits — check + log message)
- [x] `grep -nE 'data\.get\("is_claude_primary"' src/sentiment/enrichment/llm_enrichment.py` returns 1 hit (line 397)
- [x] `pytest tests/sentiment/test_enrichment_short_circuit.py -v` — 5 tests passed
- [x] `pytest tests/sentiment/test_llm_enrichment_optional.py -v` — 6 existing tests still pass
- [x] Full sentiment suite: 137 passed

## Decisions Made

- **Tasks 1 + 2 ship in one GREEN commit because both touch `pipeline.py` and the run-loop in Task 2 depends on the routing changes in Task 1.** Splitting would have left an inconsistent intermediate state. RED commits split correctly per task scope. Matches the Plan 71-03 atomic-commit-where-meaningful pattern.
- **`_resolve_extractor_mode` factored as a `@staticmethod`** so unit tests can verify precedence semantics without instantiating the full pipeline (no resolver, no extractor, no I/O). Single source of truth for the env-vs-arg rule.
- **`_run_legacy_loop` is a verbatim extraction of the pre-71-04 per-doc loop.** Zero behaviour drift on auto/rule/claude modes — `test_daily_pipeline_resilience.py` and `test_rule_extractor_events.py` continue to pass without modification.
- **Per-doc soft fallback loops `for doc, src in batch:`** so each doc carries its inferred source string forward into the Silver record. This preserves the per-source attribution that `WeeklyAggregator` and `news_service` consume.
- **`_write_silver_file(is_claude_primary=False)` defaults to False** so the envelope key is absent on auto/rule/claude runs (preserves the pre-71-04 envelope shape byte-for-byte for legacy consumers). The key only appears when explicitly True. This is intentionally non-symmetric to keep enrichment back-compat trivial.
- **`enrich_silver_records` short-circuit uses `bool(data.get("is_claude_primary", False))`** — the explicit bool() coercion is defensive against envelopes that ship the key as a non-bool (e.g. string `"true"`). Pre-Phase-71 envelopes never have the key, so the default `False` returns immediately.
- **Roster-provider season binding at construction time** (`datetime.now().year`) — production runs the daily cron during the current NFL season. Tests inject a fake roster after construction by directly setting `pipeline._extractor.roster_provider = lambda: []` (the SHA-determinism contract from Plan 71-02).
- **Generic `_write_envelope` helper, not bespoke writers per sink.** Both new sinks (`unresolved_names`, `non_player_pending`) share the same partition layout as Silver signals; one helper keeps the envelope shape consistent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] One test asserted log message text using "fallback" but the actual log message reads "Falling back to RuleExtractor"**

- **Found during:** Task 1 first GREEN run
- **Issue:** `test_claude_primary_without_di_or_env_falls_back_to_rule_with_warning` checked `"fallback" in rec.message.lower()` but the production log message is `"Falling back to RuleExtractor for this run."` — the substring "fallback" never appears (only "Falling back" / "ruleextractor").
- **Fix:** Changed the assertion to check for `"ruleextractor"` (lowercase) which is unambiguously present in the message. The intent of the test (verify ops can see WHY the downgrade happened) is preserved — the "RuleExtractor" identifier is the actionable signal.
- **Files modified:** `tests/sentiment/test_pipeline_claude_primary.py`
- **Committed in:** `b25759c` (Task 1+2 GREEN — together with the production code that emits the WARNING)

**Total deviations:** 1 auto-fixed (Rule 1 - Bug, test-side only).
**Impact on plan:** None. Production code and contract were correct on first attempt; the fix was a test-assertion correction.

### Out-of-scope discoveries (deferred)

- **`tests/test_daily_pipeline.py::TestFailureIsolation::test_all_fail_returns_exit_code_1`** — pre-existing failure verified against the baseline commit `18593fd` (pre-71-04). The test patches certain ingestion functions but RotoWire/PFT/LLM Enrichment run for real and return success. Not introduced by Plan 71-04. Logged in `.planning/phases/71-llm-primary-extraction/deferred-items.md` for separate triage.

## Issues Encountered

None beyond the single deviation above. TDD flow was clean: each RED commit failed exactly the assertions targeted; each GREEN commit made them pass without breaking prior tests. The only iteration loop was the log-message assertion fix described in Deviation #1.

## User Setup Required

None for this plan itself. Production activation requires (handled in Plan 71-05):

1. Set `ENABLE_LLM_ENRICHMENT=true` and `EXTRACTOR_MODE=claude_primary` in the daily-sentiment.yml GHA workflow env.
2. Confirm `ANTHROPIC_API_KEY` GitHub Secret is present (already set per v7.0 carry-forward).
3. Verify the `data/bronze/players/rosters/season=2026/` parquet is present (committed 2026-04-24 per recent ROSTER fix).

When the daily cron runs with both env vars set:
- New writes will appear under `data/silver/sentiment/non_player_pending/season=2026/week=NN/` and `data/silver/sentiment/unresolved_names/season=2026/week=NN/`.
- Cost records will appear under `data/ops/llm_costs/season=2026/week=NN/llm_costs_*.parquet`.
- The Silver signals envelope will gain `"is_claude_primary": true` and downstream `enrich_silver_records()` will skip those envelopes (saving the second LLM call).

## Next Phase Readiness

**Ready for Plan 71-05 (release engineering).** Plan 71-05 will:

1. Update `scripts/process_sentiment.py` CLI with `--extractor-mode` / `--mode` arg (matches existing CLI conventions per CONTEXT D-02).
2. Update `.github/workflows/daily-sentiment.yml` to set `EXTRACTOR_MODE=claude_primary` env when `ENABLE_LLM_ENRICHMENT=true`.
3. Harvest the LLM-03 5.57x ratio + Plan 71-04 cost stub into `71-SUMMARY.md`.
4. Update `nfl-data-engineering/CLAUDE.md` Status block to reflect Phase 71 ship.

**Critical invariants Plan 71-05 must preserve:**

1. **CLI arg wins over env** — explicit `--extractor-mode` on the command line takes precedence over `EXTRACTOR_MODE` env. Pipeline already enforces this at construction; the CLI just needs to pass the value through.
2. **Daily cron env var is conditional on ENABLE_LLM_ENRICHMENT** — when the flag is `false`, the cron must NOT set `EXTRACTOR_MODE=claude_primary` (so RuleExtractor stays primary). The GHA expression `if: env.ENABLE_LLM_ENRICHMENT == 'true'` should gate the env propagation.
3. **No live API calls in CI** (LLM-05) — Plan 71-05 must not introduce network-dependent assertions in any test it adds.

**Blockers:** None.

## TDD Gate Compliance

Plan type is `execute`, not top-level `tdd`, but each individual task carried `tdd="true"`. RED → GREEN sequence verified:

| Task | RED commit (test) | GREEN commit (feat) |
|------|-------------------|---------------------|
| 1 + 2 (pipeline routing + run loop) | `210d521` | `b25759c` |
| 3 (enrichment short-circuit) | `5a55566` | `284772f` |

All four commits land in the canonical order. RED commits have at least one failing assertion at commit time (verified during plan execution). GREEN commits make those assertions pass without breaking any prior tests in the sentiment suite.

## Threat Model Compliance

All STRIDE threats from the plan addressed:

- **T-71-04-01** (Tampering — invalid EXTRACTOR_MODE) — mitigated; `_resolve_extractor_mode` falls through to `"auto"` with INFO log on unknown env values; `_VALID_MODES` frozenset is the allow-list.
- **T-71-04-02** (DoS — batch failure halts pipeline) — mitigated; `_run_claude_primary_loop` wraps `extract_batch_primary` in try/except and pivots to `_rule_fallback` per doc; daily cron always completes.
- **T-71-04-03** (Repudiation — cost without surfaced total) — mitigated; `result.cost_usd_total` populated from `CostLog.running_total_usd`; visible in run logs and (Plan 71-05) the SUMMARY weekly cost line.
- **T-71-04-04** (Info disclosure — unresolved-names sink) — accepted per CONTEXT; names are public NFL figures.
- **T-71-04-05** (Elevation of privilege — double LLM cost) — mitigated; `enrich_silver_records` short-circuits envelopes with `is_claude_primary=true`; the entire envelope is skipped before record enumeration.

## Known Stubs

None. All added code is first-class production surface. The `_rule_fallback` defensive reconstruction inside `_fallback_per_doc` is not a stub — it's a belt-and-braces guard for a defensive path that should never trigger (`_is_claude_primary` implies `_rule_fallback` was set in `__init__`).

## Threat Flags

None. The new Silver sinks (`non_player_pending/`, `unresolved_names/`) are partition-mirroring the existing Silver layout, hold only data Claude already produced (which itself derives from public Bronze content), and are not network-exposed. The LLMEnrichment short-circuit reduces attack surface (one fewer Anthropic call per claude_primary envelope) — strictly defensive.

## Self-Check: PASSED

Verified post-write:

**Files exist:**
- `src/sentiment/processing/pipeline.py` — FOUND (1146 lines; +600 net additions vs pre-71-04)
- `src/sentiment/enrichment/llm_enrichment.py` — FOUND (455 lines; +14 net additions for short-circuit)
- `tests/sentiment/test_pipeline_claude_primary.py` — FOUND (650 lines; 13 tests)
- `tests/sentiment/test_enrichment_short_circuit.py` — FOUND (368 lines; 5 tests)

**Commits in git log:**
- `210d521 test(71-04): add failing tests for claude_primary pipeline wiring` — FOUND
- `b25759c feat(71-04): wire claude_primary mode into SentimentPipeline` — FOUND
- `5a55566 test(71-04): add failing tests for LLMEnrichment claude_primary short-circuit` — FOUND
- `284772f feat(71-04): short-circuit LLMEnrichment on claude_primary envelopes` — FOUND

**Test runs:**
- `pytest tests/sentiment/test_pipeline_claude_primary.py` — 13 passed
- `pytest tests/sentiment/test_enrichment_short_circuit.py` — 5 passed
- `pytest tests/sentiment/test_llm_enrichment_optional.py` — 6 passed (regression)
- `pytest tests/sentiment/test_daily_pipeline_resilience.py` — 7 passed (regression)
- `pytest tests/sentiment/test_rule_extractor_events.py` — 26 passed (regression)
- Full sentiment suite: **137 passed** (up from 119; zero regressions)

---
*Phase: 71-llm-primary-extraction*
*Completed: 2026-04-24*
