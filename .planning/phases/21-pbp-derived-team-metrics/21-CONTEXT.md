# Phase 21: PBP-Derived Team Metrics - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Compute eleven new team-level metric categories from PBP data with rolling windows and write as Silver parquet. Metrics cover: penalties, opponent-drawn penalties, turnover luck, red zone trip volume, special teams FG/punt/return, 3rd down rates, explosive plays, drive efficiency, sack rates, and time of possession. No new Bronze ingestion — all source data available from Phase 20.

</domain>

<decisions>
## Implementation Decisions

### Module Organization
- Single new orchestrator function `compute_pbp_derived_metrics(pbp_df)` in `team_analytics.py` — mirrors existing `compute_pbp_metrics()` pattern
- Calls 11 individual `compute_*` functions, merges all on `(team, season, week)`, applies `apply_team_rolling()` at the end
- Orchestrator calls `_filter_valid_plays()` once and passes filtered plays to most functions
- ST and penalty functions receive **raw PBP** and apply their own filters (like `compute_fourth_down_aggressiveness()` pattern)
- Red zone trip volume: extend existing `compute_red_zone_metrics()` to add `off_rz_trips` and `def_rz_trips` columns (drive-level `nunique` already computed there)

### Penalty Metrics
- Use `penalty == 1` flag to identify penalty plays (not `play_type == 'penalty'`)
- Split offensive vs defensive penalties using `penalty_team` column: compare `penalty_team == posteam` (offensive) vs `penalty_team == defteam` (defensive)
- Opponent-drawn penalties: same logic from opponent's perspective (penalties the team draws from opponents)

### Special Teams Filtering
- New `_filter_st_plays(pbp_df)` helper — filters to `special_teams_play == 1` or `play_type in ('field_goal', 'punt', 'kickoff', 'extra_point')`
- Each ST compute function further narrows from ST-filtered plays (e.g., `field_goal_attempt == 1`)
- FG accuracy buckets: NFL standard 4-bucket split — <30 / 30-39 / 40-49 / 50+ yards using `kick_distance`
- Punt/kick return metrics: touchbacks excluded from return yard average; touchback rate is its own column (`touchbacks / attempts`)
- ST metrics split by kicking team vs returning team (natural ST framing), not offense/defense

### Turnover Luck
- Definition: fumble recovery rate vs 50% league-average baseline
- Own fumble recovery rate = own fumbles recovered / total own fumbles; deviation from 50% = luck indicator
- Also track opponent fumble recovery rate
- Granularity: season-to-date cumulative (expanding window with `shift(1)` lag), not rolling windows
- Flag when rate is >60% or <40% as lucky/unlucky
- Include raw counts alongside luck indicator: `fumbles_lost`, `fumbles_forced`, `fumble_recovery_rate`, `is_turnover_lucky` flag
- Uses `fumble_recovery_1_team` column added in Phase 20

### Output Paths & Script
- Single combined parquet file per season under `teams/pbp_derived/season=YYYY/` containing all 11 metric categories merged on `(team, season, week)`
- Extend existing `silver_team_transformation.py` — add `compute_pbp_derived_metrics` import and call alongside the existing 4 compute calls
- Add `pbp_derived` key to `SILVER_TEAM_S3_KEYS` in `config.py`
- Add corresponding entry to `check_pipeline_health.py` for freshness/size monitoring

### Claude's Discretion
- Exact column names for the 11 metric categories (follow existing naming conventions: `off_`/`def_` prefix, descriptive suffix)
- Whether `_filter_st_plays()` needs season_type/week filtering or inherits from the orchestrator
- How to handle edge cases: teams with 0 FG attempts in a game, 0 punt returns, etc. (NaN is fine)
- Explosive play yard thresholds confirmation (20+ pass, 10+ rush per PBP-08 requirement)
- Drive efficiency column naming for 3-and-out rate, avg drive plays/yards

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — PBP-01 through PBP-11 define all eleven metric categories; INTEG-02 defines rolling window requirements
- `.planning/ROADMAP.md` — Phase 21 success criteria (5 items including penalty flag usage, ST filter, drive-level red zone)

### Prior Phase Context
- `.planning/phases/20-infrastructure-and-data-expansion/20-CONTEXT.md` — PBP column expansion details, 140-column schema, ST filter note

### Existing Code
- `src/team_analytics.py` — `_filter_valid_plays()`, `apply_team_rolling()`, `compute_pbp_metrics()`, `compute_red_zone_metrics()` patterns
- `scripts/silver_team_transformation.py` — Script wiring pattern, `_read_local_pbp()`, `_save_local_silver()`, `SILVER_TEAM_S3_KEYS` usage
- `src/config.py` — `PBP_COLUMNS` (140 columns including penalty/ST/fumble/drive), `SILVER_TEAM_S3_KEYS`

### Data Model
- `docs/NFL_DATA_DICTIONARY.md` — PBP column definitions for penalty, ST, fumble, drive fields
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — Where these metrics fit in the prediction feature vector

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_filter_valid_plays()` — run/pass filter with season_type/week guards; reuse for most metrics
- `apply_team_rolling()` — handles `_roll3`, `_roll6`, `_std` with `shift(1)` lag; reuse for all new metrics
- `compute_red_zone_metrics()` — already has drive-level grouping via `drive` column `nunique`; extend with trip volume columns
- `_read_local_pbp()` in silver_team_transformation.py — reads latest PBP parquet per season
- `_save_local_silver()` — writes to local Silver directory with proper path creation

### Established Patterns
- Orchestrator pattern: `compute_pbp_metrics()` calls individual functions, merges on `(team, season, week)`, applies rolling
- Off/def split: group by `posteam` for offense, `defteam` for defense
- Fourth-down pattern: function takes raw PBP and applies its own filtering (model for ST/penalty functions)
- Empty DataFrame guard: return empty DF with correct columns when no plays found

### Integration Points
- `silver_team_transformation.py` line 28: import list — add `compute_pbp_derived_metrics`
- `SILVER_TEAM_S3_KEYS` in `config.py` — add `pbp_derived` entry
- `check_pipeline_health.py` — add `pbp_derived` to Silver path checks
- `tests/test_team_analytics.py` — add unit tests for all 11 new compute functions

</code_context>

<specifics>
## Specific Ideas

- Success criteria #3 explicitly requires: penalties use `penalty == 1` flag (not `play_type == 'penalty'`), ST uses dedicated filter (not `_filter_valid_plays()`), red zone trips use drive-level grouping producing 3-5 trips per team per game (not 15+ from play-level counting)
- Turnover luck's 50% fumble recovery baseline is well-established in NFL analytics (Football Outsiders, Sharp Football Stats)
- FG 4-bucket split (<30/30-39/40-49/50+) matches NFL broadcast conventions and gives enough granularity for kicker evaluation

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 21-pbp-derived-team-metrics*
*Context gathered: 2026-03-16*
