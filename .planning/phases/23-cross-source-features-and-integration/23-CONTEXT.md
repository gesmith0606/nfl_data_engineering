# Phase 23: Cross-Source Features and Integration - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Compute referee tendency profiles and playoff/elimination context by joining data across Silver modules, validate all Silver sources assemble into a ~130-column prediction feature vector, and add pipeline health monitoring for all new v1.3 Silver paths. No new Bronze ingestion — all source data available from Phases 20-22.

</domain>

<decisions>
## Implementation Decisions

### Referee Tendency Profiles (CROSS-01)
- **Data source:** Use `referee` column from schedules Bronze (head ref name per game) — NOT the full officials Bronze crew data
- **Join approach:** Join schedules referee assignments to existing penalty Silver metrics (`off_penalties`, `def_penalties` from `team_analytics.py`) via `game_id`
- **Granularity:** Season-to-date cumulative (expanding window with `shift(1)` lag) — matches turnover luck pattern from Phase 21
- **Columns produced:** Penalty rate per game by this ref crew (total penalties called per game officiated). Single focused signal, not scoring impact or home bias
- **Name normalization:** Simple `strip()` + `title()` on referee names — no fuzzy matching or manual alias mapping. Should produce 20-25 unique active referees per season
- **Module placement:** New functions in a cross-source module (or extend game_context.py since schedules is the primary source)

### Playoff/Elimination Context (CROSS-02)
- **W-L computation:** Derive from schedules `home_score`/`away_score` columns — compare scores to determine W/L/T per team per week. Cumulative sum with `shift(1)` lag for standings through week N-1
- **Division rank:** Rank teams 1-4 within each division by `win_pct`. Ties broken by total wins (no complex NFL tiebreakers). Uses `TEAM_DIVISIONS` dict already in `config.py`
- **Late season contention:** Binary flag — `win_pct >= 0.400 AND week >= 10`. Simple, interpretable, avoids complex tiebreaker/elimination logic
- **Games behind:** Include `games_behind_division_leader` as continuous column alongside division rank
- **Spot-check validation:** Verify final W-L-T and division rank against official NFL standings for 2023 and 2024 seasons
- **Output columns:** `wins`, `losses`, `ties`, `win_pct`, `division_rank`, `games_behind_division_leader`, `late_season_contention`

### Feature Vector Assembly (Integration Test)
- **Scope:** Test-only validation — no production `assemble_features()` function. The ML phase will build its own feature pipeline
- **Sources joined:** All four Silver source groups on `[team, season, week]`:
  1. PBP metrics (existing v1.2) — EPA, success rate, CPOE, red zone, tendencies, SOS, situational splits
  2. PBP-derived metrics (Phase 21) — penalties, turnovers, ST, 3rd down, explosives, drives, sacks, TOP
  3. Game context (Phase 22) — weather, rest/travel, coaching
  4. Phase 23 outputs — referee tendencies, playoff/elimination context
- **Null policy:** Assert no nulls in core columns (wins, penalties, EPA) for weeks 2+. Allow nulls in Week 1 rolling columns (no prior data) and weather edge cases. Test documents expected null patterns
- **Column count assertion:** ~130 columns total after join (exact count determined during implementation)

### Pipeline Health (INTEG-01)
- Extend `check_pipeline_health.py` to validate all new v1.3 Silver output paths with freshness and file size checks
- Cover: `pbp_derived`, `game_context`, referee tendencies, playoff context outputs

### Claude's Discretion
- Whether referee tendencies go in `game_context.py` (extends schedules-derived module) or a new `cross_source_features.py` module
- Exact column naming for referee penalty rate (e.g., `ref_penalties_per_game`, `ref_penalty_rate`)
- Whether playoff context columns get rolling windows or remain cumulative-only
- How to handle tie games in W-L-T (rare but exist pre-2022 OT rule change)
- Specific null assertions for each source in the integration test

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — CROSS-01 (referee tendencies), CROSS-02 (playoff context), INTEG-01 (pipeline health)
- `.planning/ROADMAP.md` — Phase 23 success criteria (4 items including 20-25 unique refs, spot-check standings, health check, ~130 column vector)

### Prior Phase Context
- `.planning/phases/20-infrastructure-and-data-expansion/20-CONTEXT.md` — Officials Bronze ingestion, PBP column expansion, STADIUM_COORDINATES
- `.planning/phases/21-pbp-derived-team-metrics/21-CONTEXT.md` — Penalty metrics columns, orchestrator pattern, turnover luck expanding window pattern, apply_team_rolling()
- `.planning/phases/22-schedule-derived-context/22-CONTEXT.md` — game_context.py module, _unpivot_schedules(), schedules schema (referee column, home_score/away_score)

### Existing Code
- `src/team_analytics.py` — `compute_pbp_derived_metrics()`, penalty compute functions (`off_penalties`, `def_penalties`), `apply_team_rolling()`
- `src/game_context.py` — `_unpivot_schedules()`, per-team rows with `game_id` and `is_home`
- `src/config.py` — `TEAM_DIVISIONS` (division lookup for rank), `SILVER_TEAM_S3_KEYS`, `STADIUM_COORDINATES`
- `scripts/check_pipeline_health.py` — Existing health check to extend with new Silver paths
- `scripts/silver_team_transformation.py` — Script wiring pattern for new Silver transforms

### Data Model
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — Where referee and playoff features fit in prediction feature vector

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_unpivot_schedules()` in `game_context.py` — Already produces per-team rows with `game_id`; referee column available in schedules Bronze for join
- `apply_team_rolling()` in `team_analytics.py` — Expanding window variant used for turnover luck; same pattern for referee season-to-date
- `TEAM_DIVISIONS` in `config.py` — 32 teams mapped to 8 divisions; needed for division rank computation
- `off_penalties`/`def_penalties` columns in Silver `pbp_derived` output — Join target for referee penalty rate computation
- `download_latest_parquet()` in `utils.py` — Standard read pattern for all Silver sources in integration test

### Established Patterns
- Expanding window with shift(1) lag: used in turnover luck (Phase 21) — same pattern for referee tendencies and standings
- Orchestrator pattern: single function calls individual computes, merges on `(team, season, week)`
- Per-season parquet under `teams/` prefix for Silver output
- Health check: freshness + file size validation per Silver path

### Integration Points
- `SILVER_TEAM_S3_KEYS` in `config.py` — Add entries for referee and playoff Silver outputs
- `check_pipeline_health.py` — Add all new v1.3 Silver paths
- `tests/` — New integration test file for feature vector assembly
- Schedules Bronze `home_score`/`away_score` — Source for W-L computation (already in game_context unpivot)

</code_context>

<specifics>
## Specific Ideas

- Referee penalty rate is the single most predictive ref tendency signal — scoring impact and home bias are noisy with only 17 games per ref per season
- Division rank uses simple win_pct ranking without NFL tiebreaker complexity (explicitly out of scope per REQUIREMENTS.md)
- Late season contention threshold (win_pct >= 0.400 after Week 10) captures "still playing for something" motivation signal
- Integration test should use a single representative season (e.g., 2024) with spot-checks, not all 10 seasons

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 23-cross-source-features-and-integration*
*Context gathered: 2026-03-17*
