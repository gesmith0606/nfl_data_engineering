# Phase 16: Strength of Schedule and Situational Splits - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Compute opponent-adjusted EPA rankings and schedule difficulty (SOS) plus situational performance splits (home/away, divisional, game script) with rolling windows. All derived from PBP data in the existing Silver team pipeline. Expose via the existing `silver_team_transformation.py` CLI. Register new Silver output paths in config.py.

</domain>

<decisions>
## Implementation Decisions

### SOS Methodology
- Simple average: opponent-adjusted EPA = raw EPA minus mean of opponents' EPA faced (through week N-1 only — lagged, no circular dependency)
- Additive adjustment: adj_off_epa = raw_off_epa - mean(opponents_def_epa); adj_def_epa = raw_def_epa - mean(opponents_off_epa)
- Offense and defense SOS computed separately (off_sos = mean of opponents' DEF EPA; def_sos = mean of opponents' OFF EPA)
- Week 1 opponent-adjusted EPA equals raw EPA for all teams (no opponent history available)
- Output includes both rank (1-32) AND numeric SOS score per team-week

### Situational Tagging
- Home/away determined from PBP columns: posteam == home_team (no schedule join needed)
- Divisional games detected via static `TEAM_DIVISIONS` dict in config.py (teams don't change divisions)
- Game script uses PBP `score_differential` column (pre-snap, positive = posteam leading)
- Binary game script threshold: leading by 7+ and trailing by 7+; plays within 6 points are neutral and excluded from game script splits

### Output Structure
- Two separate Parquet datasets:
  - `data/silver/teams/sos/season=YYYY/` — opponent-adjusted EPA, SOS numeric score, SOS rank (1-32), per team-week
  - `data/silver/teams/situational/season=YYYY/` — home/away EPA, divisional/non-divisional EPA, leading/trailing EPA, per team-week
- Wide format: one row per (team, season, week) with situation-specific columns (home_epa, away_epa, div_epa, nondiv_epa, leading_epa, trailing_epa)
- NaN for non-applicable situations (e.g., home_epa = NaN for away weeks; div_epa = NaN for non-divisional weeks)
- Rolling windows (roll3, roll6, std) applied to ALL split columns — min_periods=1 so values appear after first applicable game

### CLI Integration
- Extend existing `silver_team_transformation.py` — no new script
- Always compute all 4 datasets per run (pbp_metrics, tendencies, sos, situational)
- Full season processing only (SOS needs cumulative opponent history; no single-week mode)
- PBP data is the sole input — no schedule Bronze dependency
- New SOS/situational functions added to `team_analytics.py` alongside existing PBP metric functions

### Claude's Discretion
- Exact column naming for adjusted EPA variants (e.g., adj_off_epa_per_play vs sos_adj_off_epa)
- How to handle bye weeks in SOS computation (team didn't play — skip that week's SOS row or carry forward)
- Whether to include success rate splits alongside EPA splits for situational data
- TEAM_DIVISIONS dict format and placement within config.py

</decisions>

<specifics>
## Specific Ideas

- SOS ranking convention: rank 1 = hardest schedule (highest mean opponent EPA faced), rank 32 = easiest — consistent with NFL.com's convention
- Game script splits should capture "garbage time vs competitive" dynamics — the 7-point threshold is a common NFL analytics standard
- Rolling windows on situational columns will naturally have more NaN early in the season since a team might not have played at home or in a divisional game yet — this is expected and correct behavior with min_periods=1

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `team_analytics.py:apply_team_rolling()` — rolling window logic with shift(1), groupby(['team', 'season']), min_periods=1; reuse directly for SOS and situational columns
- `team_analytics.py:_filter_valid_plays()` — play filtering (REG, week ≤ 18, pass/run, non-null EPA); reuse for situational split computation
- `team_analytics.py:compute_team_epa()` — team EPA per week; SOS consumes this output as input for opponent adjustment
- `config.py:SILVER_TEAM_S3_KEYS` — registration pattern for new Silver team datasets (add 'sos' and 'situational' entries)
- `silver_team_transformation.py:_read_local_pbp()` — Bronze PBP reader; already handles latest-file resolution
- `silver_team_transformation.py:_save_local_silver()` — Silver writer with timestamped filenames

### Established Patterns
- Wide format with off_/def_ column prefixes (from Phase 15 PBP metrics)
- Column naming: `{metric}_roll{N}` suffix for rolling windows (e.g., off_epa_per_play_roll3)
- Local-first storage with optional S3 upload
- Timestamped filenames: `{dataset}_{YYYYMMDD_HHMMSS}.parquet`

### Integration Points
- `team_analytics.py:compute_pbp_metrics()` output → input for SOS computation (need team EPA per week)
- `config.py` — register SILVER_TEAM_S3_KEYS entries for 'sos' and 'situational'
- `silver_team_transformation.py` — add SOS and situational compute calls after existing pbp_metrics and tendencies
- PBP columns used: posteam, defteam, home_team, away_team, epa, score_differential, game_id

</code_context>

<deferred>
## Deferred Ideas

- Forward-looking SOS (remaining schedule difficulty) — tracked as SOS-03 in REQUIREMENTS.md for v1.3+
- Weather/indoor splits as additional situational dimension — future phase
- Quarter-by-quarter game script analysis (not just overall game state) — future enhancement

</deferred>

---

*Phase: 16-strength-of-schedule-and-situational-splits*
*Context gathered: 2026-03-14*
