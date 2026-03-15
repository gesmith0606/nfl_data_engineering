# Phase 15: PBP Team Metrics and Tendencies - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Compute team-level performance metrics (EPA, success rate, CPOE, red zone efficiency) and tendency metrics (pace, PROE, 4th down aggressiveness, early-down run rate) from Bronze PBP data with rolling windows. Expose via a new Silver team CLI (`silver_team_transformation.py`). Register new Silver output paths in config.py. Fix the existing rolling window season-leak bug in player_analytics.py. Update data dictionary with new table schemas.

</domain>

<decisions>
## Implementation Decisions

### Rolling Windows
- Lagged: use `shift(1)` so week N's rolling value uses only prior weeks (no data leakage for prediction models)
- min_periods=1 for both roll3 and roll6 — values start appearing at Week 2; Week 1 is always NaN
- Include season-to-date (STD) expanding average alongside roll3 and roll6
- Groupby must use (entity, season) not entity alone — prevents cross-season contamination
- Fix existing bug in `player_analytics.py:compute_rolling_averages()` in-place: change `groupby('player_id')` to `groupby(['player_id', 'season'])`

### PROE Calculation
- Use nflfastR's `xpass` column from Bronze PBP data: PROE = actual_pass_rate - mean(xpass)
- Include all non-special plays (play_type in ['pass', 'run'] — exclude punts, kickoffs, spikes, kneels, penalties)
- Early-down run rate uses 1st and 2nd down (down <= 2)

### 4th Down Aggressiveness
- Two columns: go rate (% of 4th downs where team went for it vs punt/FG) and success rate (conversion rate when going for it)
- Both get rolling windows (roll3, roll6, std)

### Red Zone Metrics
- Red zone = yardline_100 <= 20 (no separate goal-to-go tier)
- Four metrics: TD rate, success rate, pass/rush split, EPA/play
- Both offense AND defense sides — prefix columns with off_ and def_
- TD rate denominator is drive-based: TDs / unique drives entering the red zone (use PBP `drive` column)

### Output Structure
- Two separate Parquet files per team-week:
  - `data/silver/teams/pbp_metrics/season=YYYY/` — EPA/play, success rate, CPOE, red zone metrics
  - `data/silver/teams/tendencies/season=YYYY/` — pace, PROE, 4th down aggressiveness, early-down run rate
- One row per (team, season, week) with offense and defense as column prefixes (off_, def_)
- Include both raw weekly values AND rolling columns (raw + _roll3 + _roll6 + _std per metric)
- Column naming convention: `metric_rollN` suffix (e.g., off_epa_per_play_roll3, pace_roll6) — matches existing player_analytics.py convention

### Documentation
- Update `docs/NFL_DATA_DICTIONARY.md` with schemas for both new Silver team tables (pbp_metrics and tendencies)

### Claude's Discretion
- Exact play filtering logic for edge cases (e.g., two-point conversions, overtime)
- How to handle teams with zero red zone trips in a week (NaN vs 0)
- Pace calculation details (plays per game vs plays per 60 minutes)
- CPOE aggregation method (mean of play-level CPOE vs team-level calculation)

</decisions>

<specifics>
## Specific Ideas

- xpass from nflfastR is the standard expected pass probability model used across NFL analytics — no need to build a custom one
- Red zone TD rate should mirror NFL.com's convention: drive-based denominator using PBP `drive` column to count unique red zone trips
- Existing player rolling pattern (`shift(1).rolling(window, min_periods=1).mean()`) is the template — team version uses same logic with `groupby(['team', 'season'])`

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `player_analytics.py:compute_rolling_averages()` — pattern for rolling windows (shift+rolling+groupby), needs season fix
- `config.py:SILVER_PLAYER_S3_KEYS` — registration pattern for new Silver team keys
- `config.py:PBP_COLUMNS` — all 103 PBP columns including epa, success, cpoe, xpass, yardline_100, drive, down, play_type
- `silver_player_transformation.py` — CLI pattern (argparse, local Bronze read, transform, local Silver write, optional S3)
- `utils.py:download_latest_parquet()` — read convention for timestamped files

### Established Patterns
- Local-first storage with S3 as optional fallback
- Timestamped filenames: `metric_YYYYMMDD_HHMMSS.parquet`
- Season/week partitioned directories
- `_read_local_bronze()` helper for reading latest Bronze parquet

### Integration Points
- Bronze PBP data at `data/bronze/pbp/season=YYYY/` — source for all team metrics
- `config.py` — register new `SILVER_TEAM_S3_KEYS` dict
- `docs/NFL_DATA_DICTIONARY.md` — add new Silver table schemas
- Future Phase 16 (SOS) consumes team EPA outputs from this phase

</code_context>

<deferred>
## Deferred Ideas

- Comprehensive Silver data dictionary update across all layers — could be a standalone doc task after v1.2 completes
- Exponentially-weighted moving averages (EWM) as alternative to fixed windows — tracked as EWM-01 in REQUIREMENTS.md for v1.3+

</deferred>

---

*Phase: 15-pbp-team-metrics-and-tendencies*
*Context gathered: 2026-03-13*
