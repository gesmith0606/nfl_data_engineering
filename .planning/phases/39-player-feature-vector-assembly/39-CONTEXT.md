# Phase 39: Player Feature Vector Assembly - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Build player-week feature vectors from existing Silver sources with temporal lag enforcement and leakage prevention. Produces a validated per-player-per-week DataFrame joining usage, advanced, historical, opponent, team context, player quality, and market data. Requirements: FEAT-01, FEAT-02, FEAT-03, FEAT-04.

</domain>

<decisions>
## Implementation Decisions

### Player Eligibility
- **D-01:** Include skill position players (QB, RB, WR, TE) with snap_pct >= 20% in any of their prior 3 games
- **D-02:** Eligibility uses Silver usage `snap_pct_roll3` (already computed with shift(1) lag)
- **D-03:** ~60% of player-weeks pass this filter, removing noise from special-teamers, garbage-time snaps, and practice squad callups

### Target Variable Design
- **D-04:** Include raw stat target columns per position for Phase 40 model training:
  - QB: passing_yards, passing_tds, interceptions, rushing_yards, rushing_tds (5 stats)
  - RB: rushing_yards, rushing_tds, carries, receptions, receiving_yards, receiving_tds (6 stats)
  - WR: targets, receptions, receiving_yards, receiving_tds (4 stats)
  - TE: targets, receptions, receiving_yards, receiving_tds (4 stats)
- **D-05:** Fantasy points derived downstream via `scoring_calculator.py` — not a model target
- **D-06:** Target columns are actual same-week stats (not lagged) — these are labels, not features

### Missing Data Handling
- **D-07:** Rookies: rolling features are NaN (XGBoost/LGB/CB handle NaN natively). Add draft_round, draft_pick, draft_value, speed_score, burst_score from Silver historical table as cold-start features
- **D-08:** Traded players: `recent_team` in weekly data already reflects current team; matchup/team-quality features join on current team naturally
- **D-09:** Bye weeks: excluded from training data (known zeros, not predictions). Rolling features naturally skip bye gap via shift(1)

### Claude's Discretion
- Module structure: new `player_feature_engineering.py` vs extending existing `feature_engineering.py`
- Exact column naming convention for the player feature vector
- Deduplication strategy for overlapping columns across Silver sources
- Leakage validator implementation details
- Output partitioning scheme (by season, by season+week, etc.)

</decisions>

<specifics>
## Specific Ideas

- Follow the same multi-source left-join pattern as `feature_engineering.py` `_assemble_team_features()`
- The feature vector should serve all 4 positions — position-specific filtering happens at Phase 40 training time
- Implied team total formula: `(total_line / 2) - (spread_line / 2)`, clipped [5.0, 45.0] — same as `compute_implied_team_totals()` in player_analytics.py
- Matchup features: join opponent defense-vs-position rank on `[opponent_team, position, season, week-1]` from Silver `defense/positional/`

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Feature assembly pattern
- `src/feature_engineering.py` — Game-level feature assembly; `_assemble_team_features()`, `assemble_game_features()`, `get_feature_columns()` patterns to adapt for player-level
- `src/config.py` — `PLAYER_DATA_SEASONS`, `SILVER_TEAM_LOCAL_DIRS`, `HOLDOUT_SEASON`

### Silver player data
- `src/player_analytics.py` — `compute_usage_metrics()`, `compute_rolling_averages()` (shift(1) lag pattern), `compute_opponent_rankings()`, `compute_implied_team_totals()`
- `src/player_advanced_analytics.py` — Advanced player profiles (NGS/PFR/QBR merge)
- `src/historical_profiles.py` — Combine + draft capital dimension table

### Team-level context sources
- `src/game_context.py` — Game context features (weather, rest, travel)
- `src/market_analytics.py` — Line movement features; `_PRE_GAME_CONTEXT` filter for pre-game knowable columns

### Projection engine (current heuristic)
- `src/projection_engine.py` — `POSITION_STAT_PROFILE` dict, `RECENCY_WEIGHTS`, `_usage_multiplier()`, `_matchup_factor()` — defines what stats each position predicts

### Read patterns
- `src/utils.py` — `download_latest_parquet()` for S3; local reads use glob + `sorted(files)[-1]` pattern

### Research
- `.planning/research/ARCHITECTURE.md` — Player feature vector design, join keys, ~160-col estimate
- `.planning/research/PITFALLS.md` — Same-game leakage risks, shift(1) enforcement, QB sample size concerns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `player_analytics.compute_usage_metrics()`: target_share, carry_share, snap_pct, air_yards_share, rz_target_share — all available as Silver pre-computed
- `player_analytics.compute_rolling_averages()`: shift(1) → rolling(window).mean() pattern — already battle-tested, produces _roll3, _roll6, _std columns
- `player_analytics.compute_opponent_rankings()`: defense-vs-position rank (1-32) per team per week — Silver `defense/positional/`
- `player_analytics.compute_implied_team_totals()`: Vegas implied total formula — used in current heuristic
- `feature_engineering._read_latest_local()`: reads latest Parquet from local Silver directory — reuse for player sources

### Established Patterns
- **Multi-source left join**: Base table + left join per source on shared keys, with suffix dedup — from `feature_engineering.py`
- **Temporal lag**: All rolling features use `shift(1)` before rolling window to prevent same-game leakage — from `player_analytics.py`
- **Pre-game filter**: `_PRE_GAME_CONTEXT` set in `feature_engineering.py` excludes retrospective features — adapt for player-level
- **Season-partitioned output**: One Parquet per season with timestamp suffix — standard pattern

### Integration Points
- **Silver sources to join** (9 total):
  1. `players/usage/` — player_id, recent_team, position, season, week, rolling usage metrics (113 cols)
  2. `players/advanced/` — player_gsis_id, NGS/PFR/QBR rolling metrics (119 cols)
  3. `players/historical/` — gsis_id, combine measurables, draft capital (static, no week)
  4. `defense/positional/` — team, position, week, avg_pts_allowed, rank
  5. `teams/player_quality/` — team, week, qb_passing_epa, injury impact (28 cols)
  6. `teams/game_context/` — team, week, is_home, rest_days, travel, weather (22 cols)
  7. `teams/market_data/` — team, week, opening_spread, opening_total
  8. `teams/pbp_metrics/` — team, week, team EPA, success rate, CPOE
  9. `teams/tendencies/` — team, week, pace, PROE, early-down run rate
- **Join keys**: `[player_id, season, week]` for player tables; `[recent_team, season, week]` for team tables; `[opponent_team, position, season, week]` for defense
- **Opponent mapping**: Derived from schedules Bronze — each player-week needs an `opponent_team` column

### Key Identifiers
- Player ID: `player_id` / `player_gsis_id` / `gsis_id` — all same GSIS format (`00-XXXXXXX`)
- Team: `recent_team` in player data; `team` in team-level data — same 2/3-letter abbreviations
- Position: `position` in player data; `position` in defense/positional — QB/RB/WR/TE

</code_context>

<deferred>
## Deferred Ideas

- Opportunity-efficiency decomposition (two-stage prediction) — Phase 41
- TD regression from red zone features — Phase 41
- Role momentum features (snap share trajectory) — Phase 41
- Ensemble stacking per position — Phase 41
- Team-total constraint enforcement — Phase 42
- Preseason mode (prior-season aggregates) — Phase 42
- MAPIE confidence intervals — Phase 42

</deferred>

---

*Phase: 39-player-feature-vector-assembly*
*Context gathered: 2026-03-29*
