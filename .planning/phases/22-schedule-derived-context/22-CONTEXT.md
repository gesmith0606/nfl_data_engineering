# Phase 22: Schedule-Derived Context - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Extract weather, rest/travel, and coaching features from schedules Bronze into a new `game_context` Silver module. Unpivot home/away game rows into per-team per-week rows. All features joinable on `[team, season, week]` to existing Silver data. No new Bronze ingestion — schedules data already has temp, wind, roof, surface, away_rest, home_rest, away_coach, home_coach, stadium_id.

</domain>

<decisions>
## Implementation Decisions

### Weather Handling
- Dome games (`roof` in `['dome', 'closed']`): set temp=72, wind=0 (controlled environment neutral constants)
- `is_dome` flag: True when `roof` in `['dome', 'closed']`
- `is_high_wind` flag: True when wind > 15 mph (NFL broadcast standard threshold)
- `is_cold` flag: True when temp <= 32°F (freezing point — affects fumble rates and passing)
- Outdoor games with missing temp/wind: leave as NaN, do not fill; derived flags become False for NaN values
- Surface type passed through as-is from schedules (`grass`, `fieldturf`, `a_turf`, `sportturf`, etc.)

### Rest & Travel
- Use existing `away_rest`/`home_rest` columns from schedules Bronze directly (pre-computed by nflverse) — unpivot to `rest_days` per team
- Rest days capped at 14 (per success criteria)
- `is_short_rest`: True when rest_days <= 6 (catches TNF at 4 days and Saturday short weeks)
- `is_post_bye`: True when rest_days >= 13 (bye week gives ~13-14 days rest)
- `rest_advantage`: simple difference = team_rest - opponent_rest (positive = more rest)
- Travel distance: haversine miles from team's home stadium to game venue using `STADIUM_COORDINATES` in `config.py`
- Home games: 0 miles travel distance (shared stadiums like MetLife, SoFi handled naturally since STADIUM_COORDINATES maps per-team)
- Time zone differential: absolute difference in hours between team's home timezone and game venue timezone using timezone field in `STADIUM_COORDINATES`
- Week 1 rest: use nflverse value directly, capped at 14

### Coaching
- Head coach per team per week: unpivot `home_coach`/`away_coach` to single `head_coach` column
- Mid-season coaching change: compare coach name week-over-week per team; if coach changes between Week N and N+1, set `coaching_change=True` for Week N+1 onward
- Off-season coaching change: compare Week 1 coach to prior season's final week coach; if different, set `coaching_change=True` for all weeks of new season
- First season of data (2016): `coaching_change=False` for all teams (no prior season to compare)
- `coaching_tenure`: count of consecutive weeks this coach has been with this team; resets on coaching change; Week 1 of a new coach = tenure 1
- No interim vs permanent coach distinction — all coaching changes treated equally (no reliable metadata in schedules data)

### Output & Module Structure
- New module: `src/game_context.py` with `_unpivot_schedules()` helper and individual compute functions
- `_unpivot_schedules()`: stack home + away rows (two rows per game), rename `home_coach`→`head_coach`, `away_rest`→`rest_days`, etc., add `is_home` flag
- Single combined parquet per season under `teams/game_context/season=YYYY/` with all weather, rest, travel, coaching columns
- New standalone script: `scripts/silver_game_context_transformation.py` (separate from PBP-derived transforms)
- Add `game_context` key to `SILVER_TEAM_S3_KEYS` in `config.py`
- All output joinable on `[team, season, week]`

### Claude's Discretion
- Exact column naming conventions (follow existing off_/def_ patterns where applicable)
- How to handle rare edge cases: teams with unusual schedules (e.g., COVID-rescheduled games)
- Whether to add is_home flag as part of game_context or assume it's derived elsewhere
- Haversine implementation (math module vs scipy)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — SCHED-01 through SCHED-05 define all five feature categories
- `.planning/ROADMAP.md` — Phase 22 success criteria (5 items including unpivot helper, weather flags, rest capping, coaching tenure)

### Prior Phase Context
- `.planning/phases/20-infrastructure-and-data-expansion/20-CONTEXT.md` — STADIUM_COORDINATES dict design, timezone field, international venues
- `.planning/phases/21-pbp-derived-team-metrics/21-CONTEXT.md` — Orchestrator pattern, apply_team_rolling(), single combined parquet per season

### Existing Code
- `src/config.py` — `STADIUM_COORDINATES` (line 95), `SILVER_TEAM_S3_KEYS`, `DATA_TYPE_SEASON_RANGES` for schedules (1999+)
- `src/nfl_data_integration.py` — `fetch_game_schedules()` method, schedules validation schema
- `src/team_analytics.py` — `_build_opponent_schedule()` (unpivot reference), `apply_team_rolling()` pattern
- `scripts/silver_team_transformation.py` — Script wiring pattern, `_read_local_pbp()`, `_save_local_silver()`

### Data Model
- `docs/NFL_DATA_DICTIONARY.md` — Schedules column definitions
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — Where game_context features fit in prediction feature vector

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `STADIUM_COORDINATES` in `config.py` — Already has ~35 venues with (lat, lon, timezone, venue_name) per team abbreviation
- `_build_opponent_schedule()` in `team_analytics.py` — Reference for home/away unpivot pattern (creates per-team rows from PBP)
- `download_latest_parquet()` in `utils.py` — Standard Bronze read pattern for schedules data
- `_save_local_silver()` in `silver_team_transformation.py` — Standard Silver write pattern

### Established Patterns
- Orchestrator pattern from Phase 21: single function calls individual computes, merges on `(team, season, week)`
- Local-first storage: `data/silver/` mirrors S3 structure
- Timestamp-suffixed filenames: `dataset_YYYYMMDD_HHMMSS.parquet`
- `apply_team_rolling()` for rolling window features (3-game, 6-game, season-to-date with shift(1) lag)

### Integration Points
- `SILVER_TEAM_S3_KEYS` in `config.py` — add `game_context` entry
- `check_pipeline_health.py` — add `game_context` to Silver path checks
- `tests/` — add `test_game_context.py` for unit tests
- Phase 23 will join game_context with PBP-derived metrics for cross-source features

</code_context>

<specifics>
## Specific Ideas

- Schedules Bronze schema confirmed: `temp` (float, NaN for dome), `wind` (float, NaN for dome), `roof` (outdoors/closed/dome), `surface` (grass/fieldturf/etc), `away_rest`/`home_rest` (int), `away_coach`/`home_coach` (string), `stadium_id`/`stadium` (string)
- 285 rows per season (2024) = ~16-17 games per team including playoffs
- away_rest/home_rest already computed by nflverse — no need to recompute from gameday dates
- Haversine sanity check: NYJ-to-LAR should compute to approximately 2,450 miles (from Phase 20 context)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 22-schedule-derived-context*
*Context gathered: 2026-03-16*
