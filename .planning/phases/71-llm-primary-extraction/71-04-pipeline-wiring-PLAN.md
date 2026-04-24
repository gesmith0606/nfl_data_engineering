---
phase: 71-llm-primary-extraction
plan: 04
type: execute
wave: 4
depends_on:
  - 71-01
  - 71-03
files_modified:
  - src/sentiment/processing/pipeline.py
  - src/sentiment/enrichment/llm_enrichment.py
  - tests/sentiment/test_pipeline_claude_primary.py
  - tests/sentiment/test_enrichment_short_circuit.py
autonomous: true
requirements:
  - LLM-01
  - LLM-02
  - LLM-05
must_haves:
  truths:
    - "`SentimentPipeline._build_extractor('claude_primary')` returns a ClaudeExtractor configured with a CostLog and a roster_provider that reads the latest `data/bronze/players/rosters/season=YYYY/week=WW/*.parquet`"
    - "`SentimentPipeline.__init__(extractor_mode='claude_primary')` sets `result.is_claude_primary = True` on the next `run()` call"
    - "Pipeline.run() processes docs in batches via `extract_batch_primary` when `is_claude_primary`; per-doc soft fallback to RuleExtractor when a batch call raises"
    - "Unresolved player names and non-player items are written to `data/silver/sentiment/unresolved_names/` and `data/silver/sentiment/non_player_pending/` respectively with JSON envelopes"
    - "When `is_claude_primary=True`, `enrich_silver_records()` short-circuits (returns 0 and logs an INFO message) — LLMEnrichment becomes a no-op in this mode"
    - "Existing `auto` and `rule` modes behave IDENTICALLY to pre-Phase-71 (regression locked by existing tests)"
    - "EXTRACTOR_MODE environment variable is read at pipeline construction when `extractor_mode` argument is the default 'auto'; explicit constructor arg wins over env"
  artifacts:
    - path: "src/sentiment/processing/pipeline.py"
      provides: "claude_primary branch in _build_extractor; batched run-loop with per-doc soft fallback; unresolved/non-player sinks; EXTRACTOR_MODE env read"
      contains: "claude_primary"
    - path: "src/sentiment/enrichment/llm_enrichment.py"
      provides: "enrich_silver_records() short-circuits when Silver envelope declares is_claude_primary"
      contains: "is_claude_primary"
    - path: "tests/sentiment/test_pipeline_claude_primary.py"
      provides: "End-to-end tests of claude_primary mode with fake client + fixture docs"
    - path: "tests/sentiment/test_enrichment_short_circuit.py"
      provides: "Tests that LLMEnrichment no-ops when envelope is claude_primary"
  key_links:
    - from: "SentimentPipeline._build_extractor"
      to: "ClaudeExtractor.__init__ (client, roster_provider, cost_log, batch_size)"
      via: "constructor instantiation in claude_primary branch"
      pattern: "ClaudeExtractor\\("
    - from: "SentimentPipeline.run loop"
      to: "ClaudeExtractor.extract_batch_primary"
      via: "batched call with BATCH_SIZE doc chunks"
      pattern: "extract_batch_primary"
    - from: "enrich_silver_records"
      to: "Silver envelope 'is_claude_primary' field"
      via: "early-return when flag set"
      pattern: "is_claude_primary"
    - from: "SentimentPipeline._write_silver_file envelope"
      to: "PipelineResult.is_claude_primary"
      via: "propagates flag into envelope JSON"
      pattern: "\"is_claude_primary\":"
---

<objective>
Wire the batched `ClaudeExtractor.extract_batch_primary` from Plan 71-03 into `SentimentPipeline.run()` via a new `"claude_primary"` extractor mode. Add per-doc soft fallback to RuleExtractor on batch failures. Capture unresolved names and non-player items into dedicated Silver sinks. Short-circuit `LLMEnrichment` when the envelope is flagged `is_claude_primary` (the Claude primary path already did the summarization work). Regress-test that `auto` and `rule` modes are byte-identical to pre-Phase-71.

Purpose: LLM-02 requires routing to Claude-primary when `ENABLE_LLM_ENRICHMENT=true` with fallback to rule when false. This plan wires the producer (71-03) into the orchestrator.
Output: Extended `pipeline.py`, short-circuit edit in `llm_enrichment.py`, two dedicated test files.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/71-llm-primary-extraction/71-CONTEXT.md
@.planning/phases/71-llm-primary-extraction/71-01-schema-and-contracts-PLAN.md
@.planning/phases/71-llm-primary-extraction/71-03-batched-claude-extractor-PLAN.md
@src/sentiment/processing/pipeline.py
@src/sentiment/enrichment/llm_enrichment.py
@src/player_name_resolver.py

<interfaces>
<!-- Public pipeline surface after this plan -->

```python
class SentimentPipeline:
    def __init__(
        self,
        extractor: Optional[Any] = None,
        resolver: Optional[PlayerNameResolver] = None,
        extractor_mode: str = "auto",   # Now accepts "claude_primary"
        cost_log: Optional["CostLog"] = None,  # Injected for tests; prod default = CostLog()
        claude_client: Optional["ClaudeClient"] = None,  # DI for tests
    ) -> None:
        # If extractor_mode == "auto" AND os.environ.get("EXTRACTOR_MODE"):
        #   effective_mode = os.environ["EXTRACTOR_MODE"]
        # else: effective_mode = extractor_mode
        # Valid values: "auto", "rule", "claude", "claude_primary"
```

```python
# New private method
def _roster_provider_factory(self, season: int) -> Callable[[], List[str]]:
    """Returns a callable that lazily loads latest rosters for season."""
    # Reads data/bronze/players/rosters/season=YYYY/ and returns player_name list.
    # Fail-open: returns lambda: [] on any error (no raise).
```

```python
# Pipeline.run control flow delta (pseudocode)
if self._is_claude_primary:
    # 1. Collect ALL unprocessed docs from all Bronze files
    # 2. Chunk into batches of BATCH_SIZE
    # 3. For each batch:
    #    try:
    #        by_doc_id, non_player_items = self._extractor.extract_batch_primary(
    #            batch, season=season, week=week or 0
    #        )
    #        for doc in batch:
    #            signals = by_doc_id.get(doc_external_id, [])
    #            records = _build_records(doc, signals)
    #            all_records.extend(records); result.signal_count += len(records)
    #            result.processed_count += 1
    #        result.non_player_items.extend(non_player_items)
    #        result.non_player_count += len(non_player_items)
    #    except Exception as exc:
    #        # Per-doc soft fallback per CONTEXT D-02
    #        result.claude_failed_count += len(batch)
    #        for doc in batch:
    #            signals = self._rule_fallback.extract(doc)  # RuleExtractor
    #            records = _build_records(doc, signals)
    #            all_records.extend(records); result.signal_count += len(records)
    #            result.processed_count += 1
    # 4. After loop: write non_player_items and unresolved_names to their sinks
    # 5. result.is_claude_primary = True
    # 6. result.cost_usd_total = sum from CostLog.running_total_usd
else:
    # Existing per-doc path — UNCHANGED for "auto" / "rule" / "claude"
```

Unresolved-names envelope path: `data/silver/sentiment/unresolved_names/season=YYYY/week=WW/unresolved_{batch_id}_{ts}.json`
Non-player-pending envelope path: `data/silver/sentiment/non_player_pending/season=YYYY/week=WW/non_player_{batch_id}_{ts}.json`

Envelope JSON shape for both:
```json
{
  "batch_id": "abc12345",
  "season": 2025,
  "week": 17,
  "computed_at": "2026-04-24T12:00:00+00:00",
  "record_count": 3,
  "records": [...]
}
```

Silver signals envelope gains the `is_claude_primary` flag at the top level (NON-BREAKING — enrichment path consumes it):
```json
{
  "batch_id": "...",
  "season": 2025,
  "week": 17,
  "is_claude_primary": true,    // NEW
  "computed_at": "...",
  "signal_count": 42,
  "records": [...]
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add claude_primary branch + EXTRACTOR_MODE env + roster_provider factory</name>
  <files>src/sentiment/processing/pipeline.py, tests/sentiment/test_pipeline_claude_primary.py</files>
  <read_first>
    - src/sentiment/processing/pipeline.py (full file already read in planning)
    - src/sentiment/processing/extractor.py (extract_batch_primary from Plan 71-03)
    - src/sentiment/processing/cost_log.py (from Plan 71-03)
    - tests/sentiment/fakes.py (FakeClaudeClient from Plan 71-02)
    - src/config.py lines 743-785 (SENTIMENT_LOCAL_DIRS — confirm roster path convention)
    - data/bronze/players/rosters/season=2025/ (confirm real parquet files exist)
  </read_first>
  <behavior>
    - `SentimentPipeline(extractor_mode="claude_primary", claude_client=fake)` instantiates without raising when ANTHROPIC_API_KEY is unset (because we DI'd the client)
    - `SentimentPipeline(extractor_mode="claude_primary")` without a DI'd client and without ANTHROPIC_API_KEY falls back to `RuleExtractor` and logs a WARNING (per CONTEXT D-02 fail-open)
    - `os.environ["EXTRACTOR_MODE"] = "claude_primary"` causes `SentimentPipeline()` (with default `extractor_mode="auto"`) to use claude_primary — env wins when arg is the default
    - Explicit arg wins over env: `SentimentPipeline(extractor_mode="rule")` with `os.environ["EXTRACTOR_MODE"]="claude_primary"` uses rule
    - `_roster_provider_factory(2025)` returns a callable; calling it returns a non-empty list of player names if the real rosters parquet exists; returns `[]` if no rosters file exists (no exception)
    - `_build_extractor("claude_primary")` instantiates `ClaudeExtractor(client=self._claude_client, roster_provider=..., cost_log=self._cost_log, batch_size=BATCH_SIZE)` correctly
    - When claude_primary mode is active, `self._rule_fallback` is also instantiated (for per-doc soft fallback in Task 2)
    - Back-compat: `SentimentPipeline(extractor_mode="auto")` still returns a RuleExtractor and `result.is_claude_primary is False` — no behavior change
    - Back-compat: converting `_build_extractor` from @staticmethod to an instance method must not silently break any pre-existing unbound call site (e.g. `SentimentPipeline._build_extractor(mode)`). All pre-existing call sites must either be inside `pipeline.py` using `self.` prefix, or — if any legacy unbound call exists in src/, tests/, or scripts/ — they MUST be updated in this task to instance-bound calls.
  </behavior>
  <action>
    1. Open `src/sentiment/processing/pipeline.py`. Import at top: `os`, `Callable` from typing. Import `ClaudeExtractor, BATCH_SIZE, _EXTRACTOR_NAME_CLAUDE_PRIMARY` and `ClaudeClient` from `src.sentiment.processing.extractor`. Import `CostLog` from `src.sentiment.processing.cost_log`.
    2. Extend `SentimentPipeline.__init__` signature to match the `<interfaces>` block: add `cost_log: Optional[CostLog] = None` and `claude_client: Optional[ClaudeClient] = None` kwargs.
    3. Inside `__init__`:
       - Read `os.environ.get("EXTRACTOR_MODE")`. If `extractor_mode == "auto"` (the default) AND env var is set to one of the valid values, use env var value. Otherwise use the arg value. Log at INFO which source won.
       - Store `self._claude_client = claude_client`, `self._cost_log = cost_log or CostLog()`.
       - Set `self._is_claude_primary = (effective_mode == _EXTRACTOR_NAME_CLAUDE_PRIMARY)`.
       - Call `self._build_extractor(effective_mode)` and store in `self._extractor`.
       - If `self._is_claude_primary`, also construct `self._rule_fallback = RuleExtractor()` for per-doc soft fallback (Task 2 consumes this).
    4. Rewrite `_build_extractor` from a `@staticmethod` to an instance method (needed for access to `self._claude_client`, `self._cost_log`). Add the new branch:
       ```python
       elif mode == _EXTRACTOR_NAME_CLAUDE_PRIMARY:
           roster_provider = self._roster_provider_factory(season=datetime.now().year)
           extractor = ClaudeExtractor(
               client=self._claude_client,
               roster_provider=roster_provider,
               cost_log=self._cost_log,
               batch_size=BATCH_SIZE,
           )
           if extractor._client is None:
               logger.warning(
                   "claude_primary requested but no client available "
                   "(no ANTHROPIC_API_KEY and no DI'd client). "
                   "Falling back to RuleExtractor for this run."
               )
               self._is_claude_primary = False
               return RuleExtractor()
           logger.info("Using claude_primary extractor (batched, cached)")
           return extractor
       ```
       Preserve the existing `"auto"`, `"rule"`, `"claude"` branches byte-identical — regression is a zero-diff commitment.
    5. **Back-compat sweep for @staticmethod → instance method conversion:** before declaring done, run `grep -rn "SentimentPipeline\._build_extractor" src/ scripts/ tests/`. For every match found: if it is inside `pipeline.py` itself using `self.` prefix, leave it. If it is an unbound call (e.g. `SentimentPipeline._build_extractor("rule")`) anywhere in `src/`, `scripts/`, or `tests/`, update the call site to instantiate the pipeline first or use an instance-bound equivalent. Document each changed call site in `71-04-SUMMARY.md`.
    6. Add method `_roster_provider_factory(self, season: int) -> Callable[[], List[str]]`:
       ```python
       def _roster_provider_factory(self, season: int) -> Callable[[], List[str]]:
           rosters_dir = _PROJECT_ROOT / "data" / "bronze" / "players" / "rosters" / f"season={season}"
           def _load() -> List[str]:
               try:
                   if not rosters_dir.exists():
                       logger.warning("Roster dir not found: %s; claude_primary will run without player hints", rosters_dir)
                       return []
                   files = sorted(rosters_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime, reverse=True)
                   if not files:
                       return []
                   import pandas as pd
                   df = pd.read_parquet(files[0])
                   col = "player_name" if "player_name" in df.columns else ("full_name" if "full_name" in df.columns else None)
                   if col is None:
                       logger.warning("Roster parquet has no player_name/full_name column; returning []")
                       return []
                   return sorted(df[col].dropna().astype(str).unique().tolist())[:1500]
               except Exception as exc:
                   logger.warning("roster_provider: failed to load rosters (%s); returning []", exc)
                   return []
           return _load
       ```
    7. Create `tests/sentiment/test_pipeline_claude_primary.py` with 8+ tests covering the behaviour bullets. Use `monkeypatch` for env-var tests; use `FakeClaudeClient` via DI everywhere; use `tmp_path` for cost_log base dir.
    Why: CONTEXT.md D-01 ("New extractor_mode added to SentimentPipeline._build_extractor"), D-02 ("--extractor-mode … and EXTRACTOR_MODE env var … CLI arg wins when both are set"), and "Downstream Integration" (roster_provider from rosters parquet). The staticmethod→instance-method conversion is required because we now need access to `self._claude_client` and `self._cost_log`.
  </action>
  <acceptance_criteria>
    - `grep -n "claude_primary" src/sentiment/processing/pipeline.py` returns at least 4 hits
    - `grep -n "_roster_provider_factory" src/sentiment/processing/pipeline.py` returns at least 2 hits (def + call)
    - `grep -n "EXTRACTOR_MODE" src/sentiment/processing/pipeline.py` returns at least 1 hit
    - `grep -n "self._rule_fallback" src/sentiment/processing/pipeline.py` returns at least 1 hit
    - `python -c "from src.sentiment.processing.pipeline import SentimentPipeline; from tests.sentiment.fakes import FakeClaudeClient; p=SentimentPipeline(extractor_mode='claude_primary', claude_client=FakeClaudeClient()); assert p._is_claude_primary is True"` exits 0
    - Env-var detection: `EXTRACTOR_MODE=claude_primary python -c "from src.sentiment.processing.pipeline import SentimentPipeline; from tests.sentiment.fakes import FakeClaudeClient; p=SentimentPipeline(claude_client=FakeClaudeClient()); assert p._is_claude_primary is True"` exits 0
    - Regression: `EXTRACTOR_MODE=rule python -c "from src.sentiment.processing.pipeline import SentimentPipeline; p=SentimentPipeline(); assert type(p._extractor).__name__=='RuleExtractor'"` exits 0
    - Legacy auto mode unchanged: `python -c "from src.sentiment.processing.pipeline import SentimentPipeline; p=SentimentPipeline(); assert type(p._extractor).__name__=='RuleExtractor'"` exits 0
    - **Back-compat sweep for @staticmethod→instance conversion:** `grep -rn "SentimentPipeline\._build_extractor" src/ scripts/ tests/` — every match is either inside `pipeline.py` using `self.` prefix, or (if a legacy unbound call is found) the task must update the call site to use an instance-bound call (and list the updates in `71-04-SUMMARY.md`).
    - `python -m pytest tests/sentiment/test_pipeline_claude_primary.py tests/sentiment/test_daily_pipeline_resilience.py -v` all pass
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_pipeline_claude_primary.py tests/sentiment/test_daily_pipeline_resilience.py tests/sentiment/test_rule_extractor_events.py -v</automated>
  </verify>
  <done>`SentimentPipeline` accepts `claude_primary` mode via arg or EXTRACTOR_MODE env; DI'd client flows through; roster_provider factory reads latest parquet; back-compat auto/rule modes unchanged; no legacy unbound `_build_extractor` call sites remain.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement batched run loop with per-doc soft fallback + new sinks</name>
  <files>src/sentiment/processing/pipeline.py, tests/sentiment/test_pipeline_claude_primary.py</files>
  <read_first>
    - src/sentiment/processing/pipeline.py (Task 1 additions applied; `run` method currently processes docs one-by-one)
    - src/sentiment/processing/extractor.py (extract_batch_primary returns (by_doc_id, non_player_items))
    - tests/fixtures/bronze_sentiment/offseason_w17_w18.json (pipeline integration test input)
    - tests/fixtures/claude_responses/offseason_batch_w17.json (registered response)
  </read_first>
  <behavior>
    - When `self._is_claude_primary` is True, `run(season, week)` collects all unprocessed docs first, chunks into `BATCH_SIZE` slices, and calls `extract_batch_primary` for each batch
    - On a batch call that raises (e.g. fake client registered a failure), that batch's docs fall back to RuleExtractor individually; `result.claude_failed_count` increases by batch size
    - On a successful batch, returned signals are merged via the existing `_build_silver_record` path; new `signal.extractor="claude_primary"` surfaces in the Silver record
    - `result.non_player_items` accumulates non-player items from all batches; `result.non_player_count == len(result.non_player_items)` at end
    - Unresolved player names (when resolver.resolve returns None) increment `result.unresolved_player_count` AND are written to `data/silver/sentiment/unresolved_names/season=YYYY/week=WW/unresolved_{batch_id}_{ts}.json`
    - Non-player items are written to `data/silver/sentiment/non_player_pending/season=YYYY/week=WW/non_player_{batch_id}_{ts}.json`
    - The written Silver signals envelope gains `"is_claude_primary": true` at the top level when the run was claude_primary
    - `result.is_claude_primary is True` after a claude_primary run
    - `result.cost_usd_total > 0.0` after a successful claude_primary run (reads from `self._cost_log.running_total_usd(season, week)`)
    - Back-compat: auto/rule mode's per-doc run loop is untouched; existing `test_daily_pipeline_resilience.py` still passes
  </behavior>
  <action>
    1. Open `src/sentiment/processing/pipeline.py`. Add module-level constants for the two new sinks:
       ```python
       _UNRESOLVED_DIR = _PROJECT_ROOT / "data" / "silver" / "sentiment" / "unresolved_names"
       _NON_PLAYER_DIR = _PROJECT_ROOT / "data" / "silver" / "sentiment" / "non_player_pending"
       ```
    2. Refactor `run()` to split behavior by mode WITHOUT changing the legacy branch:
       ```python
       def run(self, season: int, week: Optional[int]=None, dry_run: bool=False) -> PipelineResult:
           result = PipelineResult()
           result.is_claude_primary = self._is_claude_primary
           batch_id = str(uuid.uuid4())[:8]
           all_records: List[Dict[str, Any]] = []

           bronze_files = self._find_bronze_files(season, week)
           logger.info("Found %d Bronze files to scan", len(bronze_files))

           if self._is_claude_primary:
               all_records = self._run_claude_primary_loop(
                   bronze_files, season, week, batch_id, result
               )
           else:
               # Existing per-doc loop — COPY VERBATIM from current implementation;
               # the only change is that it now populates all_records AND result
               all_records = self._run_legacy_loop(
                   bronze_files, season, week, result
               )

           # Post-processing common to both modes
           if not dry_run and all_records:
               output_path = self._write_silver_file(
                   all_records, season, week, batch_id
               )
               if output_path:
                   result.output_files.append(output_path)
               self._save_processed_ids()
           elif dry_run:
               logger.info("Dry run: %d records would be written", len(all_records))

           if self._is_claude_primary and week is not None:
               result.cost_usd_total = self._cost_log.running_total_usd(season, week)

           return result
       ```
    3. Implement `_run_legacy_loop` as a verbatim extraction of the current per-doc loop (zero behavior change). Do NOT modify its behavior.
    4. Implement `_run_claude_primary_loop(self, bronze_files, season, week, batch_id, result) -> List[Dict]`:
       - Collect all unprocessed docs first (flatten across bronze files; filter via `self._processed_ids`; infer source per file).
       - Chunk into `BATCH_SIZE` batches.
       - For each batch, try `self._extractor.extract_batch_primary(batch, season, week or 0)`; on success, iterate docs in the batch and for each `signal` from `by_doc_id.get(doc_external_id, [])`, resolve player_id via `self.resolver.resolve(signal.player_name)`; if None, increment `result.unresolved_player_count` and append the signal dict (+ doc metadata) to a `unresolved_list`; build the Silver record via `_build_silver_record` and accumulate; add doc_id to `self._processed_ids`; increment `result.processed_count`, `result.signal_count`.
       - On batch exception, log error, increment `result.claude_failed_count += len(batch)`, then for each doc in batch call `self._rule_fallback.extract(doc)` and follow the same record-building + ID tracking path as the success case. Doc still gets marked processed.
       - After ALL batches: if `result.non_player_items` non-empty, write the `non_player_pending` envelope (unless dry_run); if `unresolved_list` non-empty, write the `unresolved_names` envelope (unless dry_run).
       - Accumulate `result.non_player_items` by extending from each batch's non_player list.
    5. Extend `_write_silver_file` signature to accept an optional `is_claude_primary: bool = False` param; include that key in the envelope JSON when True. Update both the legacy call site and the new one.
    6. Add helper `_write_envelope(self, records: List[Dict], base_dir: Path, prefix: str, season: int, week: Optional[int], batch_id: str) -> Optional[Path]` that mirrors `_write_silver_file` layout for the unresolved/non_player sinks.
    7. Extend `tests/sentiment/test_pipeline_claude_primary.py` with an end-to-end test:
       - Set up tmp Bronze tree by copying `tests/fixtures/bronze_sentiment/offseason_w17_w18.json` items into actual `{tmp}/data/bronze/sentiment/rss/season=2025/week=17/sample.json` files (use `monkeypatch.setattr` to redirect `_PROJECT_ROOT`).
       - Load `FakeClaudeClient.from_fixture_dir("tests/fixtures/claude_responses")`.
       - Instantiate `SentimentPipeline(extractor_mode="claude_primary", claude_client=fake, resolver=<fake_resolver>)`.
       - Call `run(season=2025, week=17, dry_run=False)`.
       - Assert `result.is_claude_primary is True`, `result.signal_count > 0`, `result.non_player_count >= 2`, a Silver file was written and its JSON has `"is_claude_primary": true`.
       - Assert `non_player_pending` envelope was written under the tmp tree.
    8. Add a failure-injection test: register a failure for the W18 batch's SHA in the fake client; run the pipeline; assert `result.claude_failed_count >= len(w18_batch)` and that those docs' signals came from RuleExtractor (fallback signals have `extractor="rule"` in the Silver record).
    Why: CONTEXT.md D-02 "Per-doc soft fallback … falls back to RuleExtractor for that single doc. Batches never hard-fail (matches Phase 61 D-06 fail-open contract)." Also D-03 "Silver schema gains an optional `extractor` field … PipelineResult emits new metrics" — these all land here.
  </action>
  <acceptance_criteria>
    - `grep -n "_run_claude_primary_loop\|_run_legacy_loop" src/sentiment/processing/pipeline.py` returns at least 4 hits (2 defs + 2 calls)
    - `grep -n "_UNRESOLVED_DIR\|_NON_PLAYER_DIR" src/sentiment/processing/pipeline.py` returns at least 4 hits (2 defs + 2+ uses)
    - `grep -n "claude_failed_count\s*+=" src/sentiment/processing/pipeline.py` returns at least 1 hit
    - `grep -n "non_player_items.extend\|non_player_items.append" src/sentiment/processing/pipeline.py` returns at least 1 hit
    - `grep -n "cost_usd_total\s*=" src/sentiment/processing/pipeline.py` returns at least 1 hit
    - `grep -nE "\"is_claude_primary\":\s*" src/sentiment/processing/pipeline.py` returns at least 1 hit (envelope)
    - `python -m pytest tests/sentiment/test_pipeline_claude_primary.py -v` all pass (10+ tests)
    - Regression: `python -m pytest tests/sentiment/ -v` entire sentiment suite passes
    - No regression in the non-sentiment suite: `python -m pytest tests/ -v --ignore=tests/sentiment -x 2>&1 | tail -20` shows no new failures (if prior failures exist, document them in SUMMARY.md as pre-existing)
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/ -v</automated>
  </verify>
  <done>Claude-primary run loop works end-to-end with per-doc soft fallback; unresolved/non-player sinks write correctly; Silver envelope carries is_claude_primary; cost_usd_total populated; legacy loop untouched.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Short-circuit LLMEnrichment when envelope is claude_primary</name>
  <files>src/sentiment/enrichment/llm_enrichment.py, tests/sentiment/test_enrichment_short_circuit.py</files>
  <read_first>
    - src/sentiment/enrichment/llm_enrichment.py (full file already read; specifically enrich_silver_records)
    - src/sentiment/processing/pipeline.py (Task 2 writes `"is_claude_primary": true` in the envelope)
    - tests/sentiment/test_llm_enrichment_optional.py (existing enrichment tests — MUST still pass)
  </read_first>
  <behavior>
    - When an envelope has `"is_claude_primary": true`, `enrich_silver_records(season, week)` skips that envelope entirely, logs INFO, and contributes 0 to the return count
    - When an envelope has no `is_claude_primary` key OR it is `false`, enrichment runs unchanged (backward compat with all pre-Phase-71 envelopes)
    - If ALL envelopes in a week are `is_claude_primary`, `enrich_silver_records` returns 0 and writes no sidecar files
    - Mixed envelopes (some claude_primary, some rule) are handled per-envelope — only rule envelopes get enriched
    - Existing `test_llm_enrichment_optional.py` tests continue to pass (envelopes without the flag default to old behavior)
  </behavior>
  <action>
    1. Open `src/sentiment/enrichment/llm_enrichment.py`.
    2. Inside `enrich_silver_records`, after loading the envelope dict via `_load_silver_envelope(envelope_path)`, add an early-return check:
       ```python
       if bool(data.get("is_claude_primary", False)):
           logger.info(
               "LLMEnrichment: skipping envelope %s (is_claude_primary=true); "
               "extraction already produced summaries.",
               envelope_path,
           )
           continue  # Next envelope
       ```
    3. This check must come BEFORE the `source_records = data.get("records") or []` extraction so that we skip the whole envelope, not just individual records.
    4. Create `tests/sentiment/test_enrichment_short_circuit.py` with tests:
       - `test_enrichment_skips_claude_primary_envelope`: write a sample envelope with `is_claude_primary=true` to a tmp tree; call `enrich_silver_records`; assert returns 0 and no sidecar file written.
       - `test_enrichment_processes_rule_envelope_unchanged`: write envelope without the flag; assert enrichment runs (mock the `LLMEnrichment` client). Use the same pattern as `test_llm_enrichment_optional.py`.
       - `test_enrichment_mixed_envelopes`: two envelopes in the same week, one with flag one without; assert only the non-claude_primary one gets enriched.
       - `test_enrichment_legacy_envelope_missing_flag`: envelope with no `is_claude_primary` key at all (pre-Phase-71 shape); assert enrichment runs normally (backward compat).
    5. Run full sentiment suite to confirm no regression in existing `test_llm_enrichment_optional.py`.
    Why: CONTEXT.md "LLMEnrichment becomes a no-op when the active extractor is claude_primary. Implementation: pipeline sets `is_claude_primary` bool on envelope and enrich_silver_records early-returns when it sees that flag. Module is preserved (still works in auto / rule modes)."
  </action>
  <acceptance_criteria>
    - `grep -n "is_claude_primary" src/sentiment/enrichment/llm_enrichment.py` returns at least 1 hit
    - `grep -nE "data\.get\(\"is_claude_primary\"" src/sentiment/enrichment/llm_enrichment.py` returns at least 1 hit
    - `python -m pytest tests/sentiment/test_enrichment_short_circuit.py -v` all 4+ tests pass
    - Regression: `python -m pytest tests/sentiment/test_llm_enrichment_optional.py -v` all existing tests still pass
    - Regression: `python -m pytest tests/sentiment/ -v` entire sentiment suite passes
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_enrichment_short_circuit.py tests/sentiment/test_llm_enrichment_optional.py -v</automated>
  </verify>
  <done>`enrich_silver_records` short-circuits claude_primary envelopes; rule envelopes unchanged; four new tests pass; existing enrichment tests unaffected.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| env → pipeline | EXTRACTOR_MODE env variable influences runtime behavior |
| resolver → pipeline | `PlayerNameResolver.resolve()` may return None; pipeline handles both |
| fallback path → extractor | When Claude fails, RuleExtractor takes over — both must produce compatible PlayerSignal |
| envelope → enrichment | is_claude_primary flag prevents double LLM cost |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-71-04-01 | Tampering | EXTRACTOR_MODE env set to invalid value | mitigate | Unknown modes fall through to `"auto"` (the existing default); INFO log emitted |
| T-71-04-02 | Denial of Service | Batch failure halts entire pipeline | mitigate | Per-doc soft fallback via `_rule_fallback` ensures the daily cron always completes |
| T-71-04-03 | Repudiation | Cost accrues without surfaced running total | mitigate | `result.cost_usd_total` populated; visible in logs + SUMMARY |
| T-71-04-04 | Information disclosure | Unresolved-names sink contains Claude-inferred names | accept | Names are public figures from NFL news; no PII risk beyond already-public data |
| T-71-04-05 | Elevation of privilege | Double LLM cost from primary + enrichment | mitigate | enrichment short-circuits on is_claude_primary flag |
</threat_model>

<verification>
- `python -m pytest tests/sentiment/ -v` — entire sentiment suite green
- Claude-primary end-to-end test writes Silver envelope with `"is_claude_primary": true`
- Unresolved-names and non-player-pending envelopes present in tmp Silver tree after test run
- Failure-injection test: `result.claude_failed_count` > 0 and fallback signals have `extractor="rule"`
- `test_llm_enrichment_optional.py` still passes (no regression)
</verification>

<success_criteria>
- `claude_primary` is a first-class mode in `SentimentPipeline._build_extractor`
- EXTRACTOR_MODE env var read with CLI-arg-wins precedence
- Roster provider loads active player names from latest Bronze parquet; fail-open to []
- Batched run loop processes docs via `extract_batch_primary`; per-doc soft fallback to RuleExtractor on batch error
- Unresolved names and non-player items written to dedicated Silver sinks
- Silver envelope carries `is_claude_primary` flag; LLMEnrichment short-circuits on that flag
- `auto` / `rule` modes byte-identical to pre-Phase-71
</success_criteria>

<output>
After completion, create `.planning/phases/71-llm-primary-extraction/71-04-SUMMARY.md`.
</output>
