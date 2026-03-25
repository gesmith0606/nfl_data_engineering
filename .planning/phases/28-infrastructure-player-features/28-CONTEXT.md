# Phase 28: Infrastructure & Player Features - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Commit the leakage fix, install new dependencies (LightGBM, CatBoost, SHAP), and build player-level features (QB quality, positional quality, injury impact) aggregated to [team, season, week] grain with verified shift(1) lag guards. Feature count grows from 283 to ~310-330.

</domain>

<decisions>
## Implementation Decisions

### QB Quality Metric
- **D-01:** Use `passing_epa` from Bronze weekly stats as the QB quality metric — full coverage 2016-2025, proven signal, simplest option
- **D-02:** Compute roll3 and roll6 rolling windows matching existing team feature pattern
- **D-03:** Starter detection uses BOTH signals: depth chart `depth_team='1'` for pre-game expected starter, actual passing attempts leader for who really played (lagged via shift(1) for next-week use)
- **D-04:** When a different QB starts than depth chart expects, set a `backup_qb_start` boolean flag

### Positional Quality (RB/WR/TE)
- **D-05:** Aggregate using snap-weighted mean EPA — weight each player's EPA by their target_share (WR/TE) or carry_share (RB)
- **D-06:** Compute roll3 and roll6 windows on the aggregated team-level positional EPA
- **D-07:** OL is OUT OF SCOPE for PLAYER-04 — team sack rate and pressure rate already capture OL quality in existing Silver team features
- **D-08:** Top 2 RBs by carries and top 3 WR/TEs by targets per team per week for aggregation

### Injury Impact Scoring
- **D-09:** Graduated severity reusing existing fantasy multipliers: Active=1.0, Questionable=0.85, Doubtful=0.50, Out/IR/PUP=0.0
- **D-10:** Usage-weighted impact: `sum(player_usage_share * (1 - injury_multiplier))` per team per week
- **D-11:** Split into 3 position group scores: QB injury impact, skill position (RB/WR/TE) injury impact, defensive injury impact
- **D-12:** These produce 3 differential features per game (home minus away)

### Architecture
- **D-13:** New Silver path at `data/silver/teams/player_quality/` — follows Medallion pattern, matches existing 8 team sources
- **D-14:** New script `scripts/silver_player_quality_transformation.py` processes Bronze player data → team-level per-week features
- **D-15:** Feature engineering reads the new Silver path via the existing `_assemble_team_features()` join loop — add to SILVER_TEAM_LOCAL_DIRS in config.py
- **D-16:** All player features use shift(1) lag — a test asserts no game's player features reference that same game's stats

### Infrastructure
- **D-17:** Commit leakage fix (get_feature_columns excluding same-week raw stats) — already implemented, just needs commit
- **D-18:** Install LightGBM 4.6.0, CatBoost 1.2.7, SHAP 0.48.0 — all verified Python 3.9 compatible
- **D-19:** Pin versions in requirements.txt

### Claude's Discretion
- Exact column naming conventions for new player features
- How to handle early-season NaN values (week 1-2 have no rolling history)
- Test structure and organization for player feature tests
- Error handling for missing Bronze data (seasons with gaps)

</decisions>

<specifics>
## Specific Ideas

- QB quality differential is the single highest-value feature addition per research (nfelo achieves 53.7% ATS largely via QB signal)
- The "both signals" approach for backup detection gives us a pre-game signal (depth chart) and a lagged post-game truth (who actually threw)
- Injury impact scoring reuses the graduated multipliers already proven in fantasy projections (projection_engine.py `apply_injury_adjustments`)

</specifics>

<canonical_refs>
## Canonical References

### Existing patterns
- `src/feature_engineering.py` — `_assemble_team_features()` join loop, `get_feature_columns()` leakage filter
- `src/config.py` — `SILVER_TEAM_LOCAL_DIRS`, `LABEL_COLUMNS`, `HOLDOUT_SEASON`
- `src/projection_engine.py` — `apply_injury_adjustments()` with graduated multipliers

### Bronze data schemas
- `data/bronze/players/weekly/` — `passing_epa`, `rushing_epa`, `receiving_epa`, `target_share`, `carries` per player per week
- `data/bronze/depth_charts/` — `depth_team` (1/2/3), `position`, `club_code`, `gsis_id` per week
- `data/bronze/players/injuries/` — injury status per player per week

### Silver team sources (integration target)
- `data/silver/teams/game_context/` — existing [team, season, week] pattern to match
- `src/team_analytics.py` — rolling window computation patterns (shift(1) lag established here)

### Research
- `.planning/research/FEATURES.md` — QB signal is #1 gap, snap-weighted aggregation recommended
- `.planning/research/PITFALLS.md` — Player aggregation is a new leakage surface, shift(1) guard critical
- `.planning/research/ARCHITECTURE.md` — Integration via SILVER_TEAM_LOCAL_DIRS in config.py

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apply_injury_adjustments()` in projection_engine.py: graduated injury multipliers (Active/Questionable/Doubtful/Out)
- `_read_latest_local()` in feature_engineering.py: reads latest Silver parquet per season
- Rolling window pattern in team_analytics.py: `.rolling(N, min_periods=1).mean()` with `groupby('team').shift(1)`

### Established Patterns
- Silver team sources join on [team, season, week] via left merge in `_assemble_team_features()`
- Config-driven source registry: `SILVER_TEAM_LOCAL_DIRS` dict maps name → subdirectory
- All rolling features are computed per-team with shift(1) to prevent same-week leakage

### Integration Points
- `config.py`: Add `player_quality` entry to `SILVER_TEAM_LOCAL_DIRS`
- `feature_engineering.py`: No changes needed — new Silver path auto-joins via existing loop
- `get_feature_columns()`: New player features must match rolling naming pattern (`_roll3`, `_roll6`) to pass the leakage filter

</code_context>

<deferred>
## Deferred Ideas

- Regime detection for QB changes (e.g., team's offensive identity shifts after QB swap) — Phase 31
- Snap-count based OL quality proxy from PFR pressure data — dropped, covered by existing Silver team features
- Player-level features for defensive positions (individual pass rusher quality) — future milestone

</deferred>

---

*Phase: 28-infrastructure-player-features*
*Context gathered: 2026-03-24*
