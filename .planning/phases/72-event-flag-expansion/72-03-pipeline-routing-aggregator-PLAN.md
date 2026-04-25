---
phase: 72
plan: 03
type: execute
wave: 3
depends_on: [72-01, 72-02]
files_modified:
  - src/sentiment/processing/extractor.py
  - src/sentiment/processing/pipeline.py
  - src/sentiment/aggregation/weekly.py
  - src/sentiment/aggregation/team_weekly.py
  - tests/sentiment/test_pipeline_claude_primary.py
  - tests/sentiment/test_non_player_routing.py
  - tests/sentiment/test_team_weekly_aggregation.py
autonomous: true
requirements:
  - EVT-02
  - EVT-03
tags: [pipeline, routing, aggregation, non-player, hybrid-attribution, silver-channel]
must_haves:
  truths:
    - "ClaudeExtractor._parse_batch_response captures `subject_type` (default 'player') on every non-player item dict"
    - "SentimentPipeline._route_non_player_items splits non_player_pending records into (a) team-rollup records keyed by team_abbr and (b) reporter records destined for non_player_news"
    - "Subject items with subject_type in {coach, team} write to data/silver/sentiment/non_player_news/season=YYYY/week=WW/non_player_news_{batch}_{ts}.json AND increment counters that flow into team_weekly rollup; subject_type=reporter items write to the SAME non_player_news channel but carry channel='reporter' in the envelope"
    - "WeeklyAggregator.aggregate(season, week) no longer silently drops player_id=null records: result.aggregated_df is unchanged for resolved players, but the aggregator instance attribute aggregator.last_null_player_count == count_of_skipped_records (locked instance-attribute approach)"
    - "TeamWeeklyAggregator output gains coach_news_count + team_news_count + staff_news_count columns (staff_news_count == 0 for Phase 72)"
    - "PipelineResult.non_player_routed_count and PipelineResult.non_player_news_count counters ACCUMULATE correctly across multiple batches in _run_claude_primary_loop (use += not =)"
    - "All new + existing sentiment tests pass under `python -m pytest tests/sentiment/ -v`"
  artifacts:
    - path: "src/sentiment/processing/extractor.py"
      provides: "_parse_batch_response captures subject_type per non_player_item; falls back to 'player' when absent"
    - path: "src/sentiment/processing/pipeline.py"
      provides: "_route_non_player_items helper + _NON_PLAYER_NEWS_DIR constant + PipelineResult.non_player_routed_count + non_player_news_count fields + ACCUMULATING (+=) invocation in _run_claude_primary_loop"
      contains: "_route_non_player_items"
      contains_2: "non_player_news"
    - path: "src/sentiment/aggregation/weekly.py"
      provides: "WeeklyAggregator instance attribute last_null_player_count tracked per aggregate() call; aggregate signature unchanged"
      contains: "last_null_player_count"
    - path: "src/sentiment/aggregation/team_weekly.py"
      provides: "TeamWeeklyAggregator merges coach_news_count + team_news_count from non_player_news Silver channel into per-team rollup"
      contains: "coach_news_count"
      contains_2: "team_news_count"
    - path: "tests/sentiment/test_non_player_routing.py"
      provides: "new test module covering routing branches: subject_type=coach → team rollup, =team → team rollup, =reporter → non_player_news, =player (legacy null) → non_player_pending kept for human review; PLUS multi-batch accumulation contract test"
  key_links:
    - from: "ClaudeExtractor._parse_batch_response"
      to: "non_player_items list"
      via: "each item carries subject_type from Claude (or defaults to 'player' when absent)"
      pattern: "subject_type"
    - from: "SentimentPipeline._run_claude_primary_loop"
      to: "_route_non_player_items"
      via: "after batch_non_player_total accumulation, route by subject_type before _write_envelope; counters use += so multiple batches accumulate"
      pattern: "_route_non_player_items"
    - from: "TeamWeeklyAggregator.aggregate"
      to: "data/silver/sentiment/non_player_news/season=YYYY/week=WW/"
      via: "scan channel='coach' and channel='team' records, group by team_abbr, increment coach_news_count + team_news_count"
      pattern: "non_player_news"
---

<objective>
Wire the hybrid non-player attribution decision (CONTEXT D-02) end-to-end in the pipeline + aggregators. The Claude extractor now emits `subject_type` per item; the pipeline routes non-player items into either the team rollup (coach/team) or the new `non_player_news` Silver channel (reporter). The weekly aggregator stops silently dropping `player_id=null` records — they either become per-team counters or live in the new channel. The team aggregator surfaces `coach_news_count` + `team_news_count` columns so the Wave 4 API can project them into TeamEvents.

Purpose: Closes EVT-02 (non-player attribution decision implemented) and EVT-03 (no silent drops of player_id=null). Without this plan, the Phase 71 `non_player_pending` Silver sink would just accumulate dead data; this plan makes it a routable input that flows all the way to the team rollup metrics that Wave 4 surfaces in `/api/news/team-events`.

Output: Hybrid routing helper, new `non_player_news` Silver channel, two-aggregator extension producing 4 new column-counters, ~22 new tests covering routing branches + null-player tracking + team rollup merge + multi-batch accumulation.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/72-event-flag-expansion/72-CONTEXT.md
@.planning/phases/72-event-flag-expansion/72-01-SUMMARY.md
@.planning/phases/72-event-flag-expansion/72-02-SUMMARY.md
@.planning/phases/71-llm-primary-extraction/71-04-SUMMARY.md
@CLAUDE.md
@.claude/rules/coding-style.md
@.claude/rules/nfl-data-conventions.md
@.claude/rules/testing.md

<interfaces>
<!-- LOCKED contracts from Phases 71 + Plans 72-01, 72-02. -->

From src/sentiment/processing/extractor.py (post-72-01):

```python
class ClaudeExtractor:
    def _parse_batch_response(
        self, raw: str, batch_docs: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, List[PlayerSignal]], List[Dict[str, Any]]]:
        """Returns (by_doc_id, non_player_items). non_player_items is List[dict] with:
            {doc_id, external_id, team_abbr, summary, sentiment, confidence, category, source_excerpt}
        AFTER 72-03: must also carry 'subject_type' (default 'player' when absent)."""

    def extract_batch_primary(
        self, docs: List[Dict[str, Any]], season: int, week: int
    ) -> Tuple[Dict[str, List[PlayerSignal]], List[Dict[str, Any]]]:
        """Returns (by_doc_id, non_player_items)."""
```

From src/sentiment/processing/pipeline.py (Phase 71 final):

```python
_NON_PLAYER_DIR = _PROJECT_ROOT / "data" / "silver" / "sentiment" / "non_player_pending"
_UNRESOLVED_DIR = _PROJECT_ROOT / "data" / "silver" / "sentiment" / "unresolved_names"
# AFTER 72-03: add _NON_PLAYER_NEWS_DIR = .../non_player_news (sibling of above)

@dataclass
class PipelineResult:
    # Existing Phase 71 fields:
    non_player_count: int = 0
    non_player_items: List[Dict[str, Any]] = field(default_factory=list)
    # AFTER 72-03 add:
    non_player_routed_count: int = 0   # team-rollup destinations (coach + team)
    non_player_news_count: int = 0      # non_player_news channel destinations (coach + team + reporter)
    null_player_count: int = 0          # player_id=null records the aggregator now tracks (EVT-03)

def _run_claude_primary_loop(...) -> Tuple[List[Dict], List[Dict]]:
    # After batch_non_player_total accumulation (around line 1025):
    # 1. Call _route_non_player_items(batch_non_player_total) -> (rollup_items, news_items, leftover_items)
    # 2. Write rollup_items to _NON_PLAYER_DIR (existing channel — keeps the partition)
    # 3. Write news_items to _NON_PLAYER_NEWS_DIR (new channel)
    # 4. ACCUMULATE counters: result.non_player_routed_count += len(rollup_items)
    #                          result.non_player_news_count += len(news_items)
    #    NEVER use plain `=` here — _run_claude_primary_loop runs this block per batch.

def _write_envelope(records, base_dir, prefix, season, week, batch_id) -> Optional[Path]:
    """Generic JSON envelope writer; reuse for non_player_news with prefix='non_player_news'."""
```

From src/sentiment/aggregation/weekly.py (Phase 61 final):

```python
class WeeklyAggregator:
    def __init__(self, ...):
        # AFTER 72-03 add:
        self.last_null_player_count: int = 0

    def _aggregate_player_signals(
        self, records: List[Dict[str, Any]], reference_time: datetime
    ) -> Dict[str, Dict[str, Any]]:
        """Currently SKIPS records where rec.get('player_id') is falsy.
        AFTER 72-03: count records where player_id is None BEFORE the existing skip,
        return the count to the caller via the locked instance-attribute pattern."""

    def aggregate(self, season, week, dry_run=False, reference_time=None) -> pd.DataFrame:
        """Currently returns DataFrame.
        AFTER 72-03: still returns DataFrame (back-compat). Resets self.last_null_player_count = 0
        at the start of each call; sets it to the null count before returning. Logs INFO."""
```

From src/sentiment/aggregation/team_weekly.py (Phase 61 final):

```python
class TeamWeeklyAggregator:
    def _aggregate_by_team(self, player_df: pd.DataFrame) -> pd.DataFrame:
        """Currently emits columns: team, team_sentiment_score, team_sentiment_multiplier,
        player_signal_count, positive_count, negative_count, net_sentiment.
        AFTER 72-03: ALSO emit coach_news_count, team_news_count, staff_news_count
        derived from data/silver/sentiment/non_player_news/season=YYYY/week=WW/."""
```

From src/sentiment/processing/cost_log.py:

```python
class CostLog:
    def write_record(self, record: CostRecord) -> None: ...
    def running_total_usd(self, season: int, week: int) -> float: ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Capture subject_type in extractor + add _route_non_player_items + non_player_news Silver sink (RED→GREEN)</name>
  <read_first>
    - src/sentiment/processing/extractor.py lines 700-907 (_parse_batch_response and _item_to_claude_signal — must understand the non_player_items dict shape)
    - src/sentiment/processing/pipeline.py lines 60-80 (_NON_PLAYER_DIR + _UNRESOLVED_DIR constants), lines 88-130 (PipelineResult dataclass), lines 922-1042 (_run_claude_primary_loop — note this loop runs PER BATCH, so accumulation must use +=), lines 634-687 (_write_envelope)
    - tests/sentiment/test_pipeline_claude_primary.py (full file — see how _NON_PLAYER_DIR is monkeypatched and how PipelineResult assertions are structured; mirror exactly)
  </read_first>
  <files>src/sentiment/processing/extractor.py, src/sentiment/processing/pipeline.py, tests/sentiment/test_non_player_routing.py</files>
  <behavior>
    - Test 1: ClaudeExtractor._parse_batch_response on a fixture item with `"subject_type": "coach"` returns a non_player_item dict containing `subject_type: "coach"`
    - Test 2: Same as above with `"subject_type": "reporter"` — captured verbatim
    - Test 3: Item without subject_type → captured as `subject_type: "player"` (back-compat default)
    - Test 4: Item with `subject_type: "garbage"` → coerced to `"player"` (defensive against prompt drift)
    - Test 5: SentimentPipeline._route_non_player_items([{subject_type:"coach", team_abbr:"KC", ...}, {subject_type:"reporter", team_abbr:"PHI", ...}, {subject_type:"team", team_abbr:"BUF", ...}, {subject_type:"player", team_abbr:None, ...}]) returns (rollup_items, news_items, leftover_items) where:
        - rollup_items contains the coach + team items (2 entries)
        - news_items contains all 3 attributable items (coach + team + reporter)
        - leftover_items contains the player-typed null items (1 entry, kept for human review under non_player_pending)
    - Test 6: SentimentPipeline.run() with a FakeClaudeClient injecting a batch where the response contains 2 coach items (KC, PHI) and 1 reporter item (DAL):
        - non_player_news_{batch}_{ts}.json file exists under tmp _NON_PLAYER_NEWS_DIR/season=2025/week=17/ with 3 records (coach, coach, reporter)
        - non_player_{batch}_{ts}.json file under _NON_PLAYER_DIR contains the leftover non-player items (subject_type='player' or unknown)
        - PipelineResult.non_player_routed_count == 2 (coach + team count for team rollup)
        - PipelineResult.non_player_news_count == 3 (all three coach + team + reporter routed to news channel)
    - Test 7 (multi-batch accumulation contract — locks the += vs = distinction): SentimentPipeline.run() processing 2 batches where batch 1 yields 3 rollup items + 3 news items and batch 2 yields 2 rollup items + 2 news items:
        - Final PipelineResult.non_player_routed_count == 5 (3 + 2; NOT 2 from the last batch only)
        - Final PipelineResult.non_player_news_count == 5 (3 + 2; NOT 2 from the last batch only)
        - This test fails LOUDLY if the implementation uses `=` instead of `+=`. Construct the test by injecting a FakeClaudeClient that returns two distinct prompt_sha responses (one per batch), or by calling _run_claude_primary_loop twice with cumulative result tracking — whichever matches the existing test_pipeline_claude_primary.py multi-batch pattern.
  </behavior>
  <action>
    Per CONTEXT D-02 (locked hybrid routing):

    1. Edit `src/sentiment/processing/extractor.py::_parse_batch_response`:
       - In the `non_player_items.append({...})` block (around line 875), add a new key `"subject_type": _coerce_subject_type(item.get("subject_type"))`.
       - Add module-level helper `_VALID_SUBJECT_TYPES = frozenset({"player", "coach", "team", "reporter"})` near the other frozensets.
       - Add module-level function `def _coerce_subject_type(value: Any) -> str: """Returns value when in _VALID_SUBJECT_TYPES else "player". Logs debug on coerce."""`
       - In `_item_to_claude_signal`, also stamp `sig.subject_type = _coerce_subject_type(item.get("subject_type"))` so player items carry it too (Plan 72-01 made `subject_type` a PlayerSignal field).

    2. Edit `src/sentiment/processing/pipeline.py`:
       - Add new module constant after `_NON_PLAYER_DIR`:
         `_NON_PLAYER_NEWS_DIR = _PROJECT_ROOT / "data" / "silver" / "sentiment" / "non_player_news"`
       - Extend `PipelineResult` dataclass with three new fields below `non_player_items`:
         ```
         non_player_routed_count: int = 0
         non_player_news_count: int = 0
         null_player_count: int = 0
         ```
       - Add module-level constant `_TEAM_ROLLUP_SUBJECT_TYPES = frozenset({"coach", "team"})` and `_NEWS_CHANNEL_SUBJECT_TYPES = frozenset({"coach", "team", "reporter"})`.
       - Add new instance method `_route_non_player_items(self, items: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict], List[Dict]]`:
         ```
         """Hybrid attribution per CONTEXT D-02.
         Returns (rollup_items, news_items, leftover_items) where:
           - rollup_items: subject_type in {coach, team} AND team_abbr is set
                          (these contribute to coach_news_count + team_news_count
                          surfaced via team_weekly aggregator)
           - news_items: subject_type in {coach, team, reporter} AND team_abbr is set
                        (written to non_player_news Silver channel; reporter-only
                        items skip the team rollup because reporters cover multiple teams)
           - leftover_items: subject_type == "player" or team_abbr missing
                            (kept in non_player_pending for human review)
         """
         ```
         Implementation: iterate `items`, for each: extract `subject_type` (default `"player"`) and `team_abbr`. If `team_abbr` is None or empty string, append to leftover. Else if `subject_type` in `_TEAM_ROLLUP_SUBJECT_TYPES`, append to BOTH rollup_items and news_items. Else if `subject_type == "reporter"`, append to news_items ONLY. Else (`"player"` with team set), append to leftover.
       - In `_run_claude_primary_loop`, after the existing `result.non_player_items.extend(batch_non_player_total)` line and before the existing `_write_envelope(batch_non_player_total, _NON_PLAYER_DIR, ...)` block, insert:
         ```
         rollup_items, news_items, leftover_items = self._route_non_player_items(batch_non_player_total)
         result.non_player_routed_count += len(rollup_items)   # ACCUMULATE: this loop runs per batch
         result.non_player_news_count += len(news_items)        # ACCUMULATE: same
         ```
         **CRITICAL: use `+=` not `=`. This loop body executes once per batch, so plain assignment would overwrite earlier batches' counts with the last batch's count alone (bug Test 7 catches).**
         Replace the existing `_write_envelope(batch_non_player_total, _NON_PLAYER_DIR, prefix="non_player", ...)` call with TWO writes:
         - `if not dry_run and leftover_items: self._write_envelope(leftover_items, _NON_PLAYER_DIR, prefix="non_player", season=season, week=week, batch_id=batch_id)`
         - `if not dry_run and news_items: self._write_envelope(news_items, _NON_PLAYER_NEWS_DIR, prefix="non_player_news", season=season, week=week, batch_id=batch_id)`

    3. Create new test module `tests/sentiment/test_non_player_routing.py`:
       - Mirror the imports + monkeypatch + fixture-loading pattern from `test_pipeline_claude_primary.py` (use `tmp_path` to redirect `_PROJECT_ROOT`, `_SILVER_SIGNALS_DIR`, `_PROCESSED_IDS_FILE`, `_NON_PLAYER_DIR`, `_UNRESOLVED_DIR`, `_NON_PLAYER_NEWS_DIR`).
       - Implement Tests 1-7 from the behavior block. Test 7 is the critical multi-batch accumulation contract — make it explicit in the test name: `test_routing_counters_accumulate_across_batches` or similar.
       - Use `FakeClaudeClient.from_fixture_dir(Path("tests/fixtures/claude_responses"))` for the SentimentPipeline.run() integration test (Test 6); the W17/W18 fixtures already include coach/team/reporter subject_type items per Plan 72-02.
       - For Test 7, construct a tiny synthetic two-batch scenario by either: (a) feeding a FakeClaudeClient with two distinct fixture entries that the pipeline batches sequentially, or (b) stubbing `_run_claude_primary_loop`'s batch iteration to drive two iterations directly. Whichever matches the existing test patterns.

    4. RED: write tests first; confirm they fail with sensible messages. Test 7 in particular must fail with a clear "expected 5, got 2" diagnostic when the bug is present.
    5. GREEN: implement extractor + pipeline edits; confirm tests pass.

    6. Commit:
       - `test(72-03): add failing tests for non-player routing + subject_type capture + multi-batch accumulation`
       - `feat(72-03): route coach/team to rollup, reporter to non_player_news Silver channel; counters accumulate per batch`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/sentiment/test_non_player_routing.py tests/sentiment/test_pipeline_claude_primary.py -v</automated>
  </verify>
  <done>
    All routing tests pass + existing pipeline_claude_primary tests still pass. Test 7 (multi-batch accumulation) explicitly proves the += contract. _NON_PLAYER_NEWS_DIR constant exists. PipelineResult has 3 new counter fields. _route_non_player_items helper exists and produces the expected 3-tuple split. Two commits land in git log.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: WeeklyAggregator tracks last_null_player_count via instance attribute + TeamWeeklyAggregator merges non_player_news columns (RED→GREEN)</name>
  <read_first>
    - src/sentiment/aggregation/weekly.py (full file — _aggregate_player_signals at line 244, aggregate at line 454, __init__)
    - src/sentiment/aggregation/team_weekly.py (full file — _aggregate_by_team at line 276, aggregate at line 363)
    - tests/sentiment/ (any existing tests for these aggregators — extend or create as needed)
  </read_first>
  <files>src/sentiment/aggregation/weekly.py, src/sentiment/aggregation/team_weekly.py, tests/sentiment/test_team_weekly_aggregation.py</files>
  <behavior>
    - Test 1: WeeklyAggregator with 5 silver records (3 with player_id, 2 with player_id=null) → aggregate() returns 3-row DataFrame; aggregator instance attribute `aggregator.last_null_player_count == 2`; INFO log emitted matching `"WeeklyAggregator: 2 records had null player_id (tracked for EVT-03)"`. (Locked: instance-attribute approach — test asserts directly against `aggregator.last_null_player_count`, not a tuple-return signature.)
    - Test 1b (reset contract): Calling `aggregator.aggregate(season, week)` twice with different inputs (first 2 nulls, then 0 nulls) → second call's `last_null_player_count == 0` (reset at the start of each call, NOT cumulative).
    - Test 2: TeamWeeklyAggregator with player Gold data for KC + a non_player_news file containing 2 coach items (KC, KC) + 1 team item (BUF) + 1 reporter item (DAL) → output DataFrame contains:
        - row team=KC: coach_news_count=2, team_news_count=0, staff_news_count=0
        - row team=BUF: coach_news_count=0, team_news_count=1, staff_news_count=0
        - row team=DAL: NOT present (reporters route to news channel only, not the team rollup table) — UNLESS DAL has player gold data; in that case DAL row exists with coach_news_count=0, team_news_count=0
    - Test 3: TeamWeeklyAggregator on empty non_player_news directory → all rows have coach_news_count=0, team_news_count=0, staff_news_count=0 (back-compat — Phase 61 callers see only zeros)
    - Test 4: TeamWeeklyAggregator with mixed-channel non_player_news (subject_type='coach' for KC + subject_type='reporter' for KC) → KC row coach_news_count == 1 (reporter excluded from rollup), staff_news_count == 0
  </behavior>
  <action>
    Per CONTEXT "Aggregator no longer silent-drops player_id: null records":

    1. Edit `src/sentiment/aggregation/weekly.py` (LOCKED: instance-attribute approach — matches Test 1 contract `aggregator.last_null_player_count == 2`):
       - **Add `self.last_null_player_count: int = 0` attribute to `WeeklyAggregator.__init__`** (place near the other instance attrs).
       - **Inside `_aggregate_player_signals`, before the existing `player_id` filter,** count records where `player_id is None` (or falsy):
         `null_count = sum(1 for rec in records if not rec.get("player_id"))`
         Return the count to the caller via the same return type the helper already uses, OR set it on the aggregator instance directly via a tightly-scoped pattern. Pick the approach that needs the smallest call-site diff (search call sites first). The chosen mechanism is internal — the EXTERNAL contract is `aggregator.last_null_player_count` after `aggregate()` returns.
       - **At the start of every `aggregate(season, week, ...)` call, reset `self.last_null_player_count = 0`.** This is the contract Test 1b locks: each call is independent, never cumulative.
       - **Before returning from `aggregate()`,** assign `self.last_null_player_count = null_count` and `logger.info("WeeklyAggregator: %d records had null player_id (tracked for EVT-03)", null_count)`.
       - Do NOT modify the `aggregate()` return signature — it still returns `pd.DataFrame` for back-compat.

    2. Edit `src/sentiment/aggregation/team_weekly.py`:
       - Add module constant: `_NON_PLAYER_NEWS_DIR = _PROJECT_ROOT / "data" / "silver" / "sentiment" / "non_player_news"`
       - Add new method `_load_non_player_news(season: int, week: int) -> List[Dict[str, Any]]`:
         ```
         """Load all non_player_news envelope JSON records for season/week.
         Falls back to [] when directory absent (D-06 fail-open)."""
         ```
         Implementation: glob `{_NON_PLAYER_NEWS_DIR}/season={season}/week={week:02d}/*.json`, parse envelope, return flat list of records.
       - Add new method `_team_news_counts(records: List[Dict]) -> Dict[str, Dict[str, int]]`:
         ```
         """Group non_player_news records by team_abbr. Returns dict mapping team_abbr to
         {coach_news_count, team_news_count, staff_news_count} sub-dict. staff_news_count
         is always 0 in Phase 72 (placeholder for future GM/exec items per CONTEXT)."""
         ```
       - Modify `_aggregate_by_team(...)` to accept an optional `team_news_lookup: Optional[Dict[str, Dict[str, int]]] = None` parameter. For each team in the per-row construction, if `team_news_lookup` has the team, merge the 3 counts into the row dict; else default 0.
       - Modify `aggregate(...)` to call `self._load_non_player_news(season, week)` then `self._team_news_counts(records)`, then pass the result as `team_news_lookup` to `_aggregate_by_team`.
       - Ensure the column order in the output DataFrame includes `coach_news_count`, `team_news_count`, `staff_news_count` after `net_sentiment`. Update any column-order list in the aggregator.

    3. Create new test module `tests/sentiment/test_team_weekly_aggregation.py`:
       - Use a `tmp_path` fixture to monkeypatch `_PROJECT_ROOT` (or instantiate `TeamWeeklyAggregator(project_root=tmp_path)` since the existing init accepts an override).
       - Write a tiny Gold parquet under `tmp_path/data/gold/sentiment/season=2025/week=17/` with 2-3 KC + BUF + DAL player rows.
       - Write a small non_player_news envelope JSON under `tmp_path/data/silver/sentiment/non_player_news/season=2025/week=17/` with the records described in Test 2.
       - Implement Tests 2-4 from the behavior block. Tests 1 + 1b belong in a small `test_weekly_aggregation_null_tracking.py` module (or extend an existing test_weekly module if one exists — check first).

    4. Run the targeted tests:
       `python -m pytest tests/sentiment/test_team_weekly_aggregation.py -v`

    5. Commit:
       - `test(72-03): add failing tests for null_player tracking + team news rollup`
       - `feat(72-03): WeeklyAggregator + TeamWeeklyAggregator surface non_player_news counts`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/sentiment/test_team_weekly_aggregation.py tests/sentiment/test_non_player_routing.py -v</automated>
  </verify>
  <done>
    WeeklyAggregator.last_null_player_count instance attribute exists, populated per call, reset at the start of each call. TeamWeeklyAggregator output DataFrame includes coach_news_count + team_news_count + staff_news_count columns. New test module has all behaviour tests passing. Two commits land.
  </done>
</task>

<task type="auto">
  <name>Task 3: Run full sentiment + aggregation suite + write SUMMARY</name>
  <read_first>
    - .planning/phases/71-llm-primary-extraction/71-04-SUMMARY.md (mirror for Plan 72-03)
  </read_first>
  <files>.planning/phases/72-event-flag-expansion/72-03-SUMMARY.md</files>
  <action>
    1. Run the full sentiment suite + the new aggregation tests:
       `source venv/bin/activate && python -m pytest tests/sentiment/ --tb=short -q`

       Expected: 179 (post-72-02) + ~22 new from this plan = >= 201 passed, 0 failed.

    2. Spot-check the routing logic with a manual smoke run against the fixture-driven pipeline:
       `python -c "
       from pathlib import Path
       from tests.sentiment.fakes import FakeClaudeClient
       from src.sentiment.processing.pipeline import SentimentPipeline
       fake = FakeClaudeClient.from_fixture_dir(Path('tests/fixtures/claude_responses'))
       p = SentimentPipeline(extractor_mode='claude_primary', claude_client=fake)
       res = p.run(season=2025, week=17, dry_run=True)
       print(f'non_player_count={res.non_player_count} routed={res.non_player_routed_count} news={res.non_player_news_count}')
       "`
       Expect non_player_count >= 30 (from W17 fixture) AND routed >= 5 AND news >= 5.

    3. Write `.planning/phases/72-event-flag-expansion/72-03-SUMMARY.md` mirroring `71-04-SUMMARY.md` structure. Include:
       - `requirements-completed: [EVT-02, EVT-03]`
       - Total sentiment test count + breakdown of new tests (call out the multi-batch accumulation test by name)
       - Wire diagram in ASCII showing: `Bronze → ClaudeExtractor → non_player_items → _route_non_player_items → {rollup_items, news_items, leftover_items} → {_NON_PLAYER_DIR (review queue), _NON_PLAYER_NEWS_DIR (Silver channel)}` AND `non_player_news → TeamWeeklyAggregator._team_news_counts → coach_news_count + team_news_count + staff_news_count columns`
       - Note that data/bronze/ remains untouched (Bronze immutability)
       - Risks: routing decisions are LOCKED via CONTEXT D-02; Phase 73+ may revisit if reporter-only items become high-volume

    4. Commit: `docs(72-03): plan summary — non-player routing + aggregator extensions`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/sentiment/ --tb=no -q | tail -3 && test -f .planning/phases/72-event-flag-expansion/72-03-SUMMARY.md</automated>
  </verify>
  <done>
    Full sentiment suite green (>= 201 passed). Smoke-run output prints positive routed + news counts. SUMMARY file written. Single docs commit lands. EVT-02 + EVT-03 marked complete in the plan summary frontmatter.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Claude API output → SentimentPipeline | Claude's `subject_type` field is untrusted text; tampered prompts could emit arbitrary values |
| non_player_news Silver channel → API/frontend | New Silver path consumed by Wave 4; downstream consumers must handle empty/missing partitions |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-72-03-01 | Tampering | subject_type from Claude | mitigate | `_coerce_subject_type` (in extractor.py) validates against frozenset({"player","coach","team","reporter"}); invalid values fall back to "player" with debug log. Prevents prompt-injection from causing arbitrary routing destinations. |
| T-72-03-02 | Information Disclosure | non_player_news Silver channel | accept | Same data Claude already produced; new channel just splits the existing non_player_pending sink. No new sensitive fields. |
| T-72-03-03 | Denial of Service | _load_non_player_news in TeamWeeklyAggregator | mitigate | Glob + JSON parse wrapped in try/except returning [] on any failure (D-06 fail-open). Aggregator's `aggregate()` never raises from non-player loading. |
| T-72-03-04 | Repudiation | Routing decisions per item | mitigate | Each routed item carries its `subject_type` + `team_abbr` + `doc_id` in the Silver envelope so the routing decision is auditable post-hoc. |
| T-72-03-05 | Spoofing | team_abbr from Claude | accept | Claude already emits team_abbr per Phase 71; this plan does not introduce a new validation gate. Wave 4 API gracefully handles unknown team codes via existing NFL_TEAM_ABBRS allowlist. |
| T-72-03-06 | Tampering | Per-batch counter accumulation | mitigate | Test 7 (multi-batch accumulation) locks the `+=` contract; a regression to `=` would drop counts from earlier batches and Test 7 would fail loudly. |
</threat_model>

<verification>
- `python -m pytest tests/sentiment/ --tb=no -q` → 201+ passed, 0 failed
- `grep -c "_NON_PLAYER_NEWS_DIR\|_route_non_player_items\|non_player_news_count\|null_player_count" src/sentiment/processing/pipeline.py` returns >= 8
- `grep -nE "non_player_routed_count\s*\+=\|non_player_news_count\s*\+=" src/sentiment/processing/pipeline.py` returns >= 2 (proves += contract — must NOT find `=` form)
- `grep -c "coach_news_count\|team_news_count\|staff_news_count\|_load_non_player_news" src/sentiment/aggregation/team_weekly.py` returns >= 6
- `grep "subject_type" src/sentiment/processing/extractor.py | wc -l` returns >= 5 (constant + _coerce + 2 capture sites + assertion)
- `grep "last_null_player_count" src/sentiment/aggregation/weekly.py | wc -l` returns >= 3 (init + reset + assignment before return)
- Smoke run from Task 3 prints `non_player_routed_count >= 5` AND `non_player_news_count >= 5`
- `ls data/silver/sentiment/non_player_news/season=2025/week=17/ 2>/dev/null` is acceptable to be empty (real backfill happens in Plan 72-05 against actual ingested Bronze)
</verification>

<success_criteria>
- ClaudeExtractor captures subject_type per non_player item with safe coercion
- SentimentPipeline._route_non_player_items splits items into 3-tuple per CONTEXT D-02
- New non_player_news Silver sink lives at data/silver/sentiment/non_player_news/season=YYYY/week=WW/
- PipelineResult exposes non_player_routed_count + non_player_news_count + null_player_count, accumulating correctly across multiple batches via `+=`
- WeeklyAggregator no longer silently drops null player_ids — count surfaces on instance attribute + log; reset per call
- TeamWeeklyAggregator output gains 3 new count columns
- 22+ new tests pass (including the multi-batch accumulation contract test); existing 179+ stay green
- SUMMARY captures EVT-02 + EVT-03 closure
</success_criteria>

<output>
After completion, create `.planning/phases/72-event-flag-expansion/72-03-SUMMARY.md` mirroring `71-04-SUMMARY.md`.
</output>
</content>
</invoke>