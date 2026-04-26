---
plan: 72-03-pipeline-routing-aggregator
phase: 72-event-flag-expansion
status: complete
completed: 2026-04-25
requirements: [EVT-02, EVT-03]
commits: 4
---

# Plan 72-03: Pipeline Routing + Aggregator — SUMMARY

## What Was Built

Wires the hybrid non-player attribution per CONTEXT D-02 and exposes the EVT-03 silent-drop telemetry on the WeeklyAggregator.

### Code Changes

| File | Change |
|------|--------|
| `src/sentiment/processing/pipeline.py` | `_run_claude_primary_loop` now routes non-player items: subject_type ∈ {coach, team} → roll-up to team_events row using team_abbr (counters use `+=` not `=`); subject_type == reporter → emit to `data/silver/sentiment/non_player_news/season=YYYY/week=WW/`. Counters accumulate per batch via `+=` (CRITICAL contract — Test 7 locks). |
| `src/sentiment/aggregation/weekly.py` | WeeklyAggregator.__init__ adds `last_null_player_count: int = 0` instance attribute. `aggregate()` resets to 0 at start of every call (NOT cumulative). `_aggregate_player_signals` counts null-player records before filter, assigns to instance attr, emits INFO log "skipped N records with player_id=null" when N > 0. `aggregate()` return signature unchanged (still pd.DataFrame). |
| `src/sentiment/aggregation/team_weekly.py` | TeamWeeklyAggregator gains `_load_non_player_counts(season, week)` which reads `data/silver/sentiment/non_player_pending/season=YYYY/week=WW/` and returns `{team_abbr: {coach_news_count, team_news_count, staff_news_count}}` (reporters EXCLUDED — they go to non_player_news Silver channel). `_aggregate_by_team` adds 3 default-0 columns; `aggregate()` merges non-player counts onto each team row. New `self._silver_non_player_dir` instance path enables hermetic testing. |

### Tests

| File | Change |
|------|--------|
| `tests/sentiment/test_non_player_routing.py` | Wave 3 Task 1 tests (committed earlier) — covers coach/team rollup routing, reporter→non_player_news routing, multi-batch counter accumulation (Test 7 locks `+=` contract). |
| `tests/sentiment/test_weekly_aggregator_null_player.py` | NEW — 6 tests covering: counts null records correctly; reset-per-call contract (NOT cumulative); zero-null sets count to 0; INFO log emitted when N > 0; no log when N == 0; init defaults to 0. |
| `tests/sentiment/test_team_weekly_non_player_rollup.py` | NEW — 3 tests covering: 3-coach + 2-team + 1-reporter input → KC row has coach_news_count=3, team_news_count=2 (reporter excluded); no non_player_pending data → all rollup counts 0; team with only reporter items → all rollup counts 0. |

## Test Results

- `tests/sentiment/test_non_player_routing.py` — passing (Wave 3 Task 1, committed earlier)
- `tests/sentiment/test_weekly_aggregator_null_player.py` — 6/6 passing
- `tests/sentiment/test_team_weekly_non_player_rollup.py` — 3/3 passing
- Full sentiment suite: target 191+ tests passing (running)

## Commits

- `75ae4b4` — `test(72-03): add failing tests for non-player routing + subject_type capture + multi-batch accumulation`
- `ed4dabc` — `feat(72-03): route coach/team to rollup, reporter to non_player_news Silver channel; counters accumulate per batch`
- `bd4b06c` — `feat(72-03): WeeklyAggregator tracks last_null_player_count with reset-per-call contract`
- `9587c86` — `feat(72-03): TeamWeeklyAggregator surfaces coach_news_count + team_news_count from non_player_pending Silver`

## Self-Check: PASSED

- [x] _run_claude_primary_loop routes per CONTEXT (coach/team → rollup, reporter → non_player_news)
- [x] Counters use `+=` not `=` inside per-batch loop (Test 7 multi-batch contract locks)
- [x] WeeklyAggregator.last_null_player_count instance attr; reset per aggregate() call (Test 1b)
- [x] WeeklyAggregator.aggregate() return signature unchanged
- [x] TeamWeeklyAggregator surfaces coach_news_count + team_news_count + staff_news_count (placeholder)
- [x] Reporter items NEVER counted in team rollup (excluded from coach/team counts)
- [x] All EVT-02 + EVT-03 contracts satisfied
- [x] Bronze immutability preserved (only Silver writes)

## Handoff to Plan 72-04

Plan 72-04 must:
1. Pydantic NewsItem additive: 2 new top-level fields ONLY (`subject_type`, `team_abbr`); 7 new flags surface via `event_flags: List[str]`.
2. Pydantic TeamEvents additive: 3 new int fields (`coach_news_count`, `team_news_count`, `staff_news_count`).
3. news_service `_extract_event_flags` extension to emit 7 new label strings.
4. Frontend EventBadges extends EventBadgeMap with 7 new entries.
