# Architecture Patterns

**Domain:** NFL prediction data foundation features (weather, coaching, special teams, penalties, rest/travel, turnover luck, referee tendencies, playoff context, red zone trips)
**Researched:** 2026-03-15
**Confidence:** HIGH (based on direct inspection of all Bronze files, Silver schemas, existing src/ modules, and PBP column inventory)

## Recommended Architecture

### Key Insight: Most "New" Features Require No New Bronze Ingestion

The schedules Bronze data already contains: `temp`, `wind`, `roof`, `surface`, `away_rest`, `home_rest`, `away_coach`, `home_coach`, `referee`, `stadium`, `div_game`. The PBP Bronze data already contains: `penalty`, `fumble`, `fumble_lost`, `interception`, `touchdown`, `yardline_100`, `drive`, `series`, `series_result`, plus all EPA/WPA columns.

The only genuinely new external data that might be needed is a weather API for detailed forecasts (precipitation, humidity), but the schedules-based temp/wind is sufficient for historical analysis. A weather API is a Gold-layer concern for future game forecasting, not a Silver-layer requirement.

**Architecture: 1 new Silver module (game_context.py) + extend existing team_analytics.py + config/path updates + 1 new transformation script.**

```
EXISTING BRONZE DATA                    SILVER MODULES
===================                    ==================

schedules/season=YYYY/     ------>     src/game_context.py (NEW)
  temp, wind, roof, surface               compute_weather_features()
  away_rest, home_rest                     compute_rest_travel()
  away_coach, home_coach                   compute_coaching_changes()
  referee                                  compute_referee_tendencies()
  home_score, away_score                   compute_playoff_context()

pbp/season=YYYY/           ------>     src/team_analytics.py (EXTEND)
  penalty, fumble, fumble_lost             compute_penalty_metrics()
  interception, touchdown                  compute_turnover_luck()
  yardline_100, drive                      compute_red_zone_trips()
  play_type (punt, field_goal)             compute_special_teams_metrics()
  field_goal_result, kick_distance
  extra_point_result, punt_blocked
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `src/game_context.py` (NEW) | Schedule-derived game context: weather, rest/travel, coaching, referee, playoff standings | Reads Bronze schedules; writes Silver `teams/game_context/` |
| `src/team_analytics.py` (EXTEND) | PBP-derived team metrics: penalties, turnover luck, special teams, red zone trips | Reads Bronze PBP; writes to new Silver team paths |
| `src/config.py` (MODIFY) | New Silver key templates, PBP_COLUMNS expansion, stadium coordinate data | Referenced by transformation scripts |
| `scripts/silver_team_transformation.py` (MODIFY) | Orchestrate new team_analytics functions alongside existing ones | Calls team_analytics new functions, writes Silver |
| `scripts/silver_game_context_transformation.py` (NEW) | Orchestrate game_context functions | Calls game_context, writes Silver |

### Data Flow

```
Bronze Schedules (existing, 2016-2025)
    |
    v
src/game_context.py (NEW MODULE)
    |
    |--- compute_weather_features(schedules_df)
    |       Input:  temp, wind, roof, surface from schedules
    |       Output: is_dome, is_cold(<32F), is_hot(>85F), is_windy(>15mph),
    |               weather_impact_score, temp_bucket, wind_bucket
    |       Grain:  one row per team-week
    |
    |--- compute_rest_travel(schedules_df)
    |       Input:  home_rest, away_rest, stadium from schedules
    |       Output: days_rest, is_short_rest(<6), is_long_rest(>8),
    |               rest_advantage, travel_distance_miles,
    |               timezone_change, is_cross_country
    |       Grain:  one row per team-week
    |       Note:   STADIUM_COORDINATES dict in config.py (32 stadiums, static)
    |
    |--- compute_coaching_changes(schedules_df)
    |       Input:  home_coach, away_coach from schedules
    |       Output: head_coach, coach_tenure_games (cumulative),
    |               is_new_coach (tenure < 17 games),
    |               coach_win_pct_rolling (6-game window)
    |       Grain:  one row per team-week
    |       Note:   Coach changes detected by comparing coach name week-to-week
    |
    |--- compute_referee_tendencies(schedules_df, penalties_df)
    |       Input:  referee from schedules + penalty counts from team_analytics
    |       Output: ref_penalties_per_game_roll6, ref_home_penalty_bias,
    |               ref_scoring_impact_avg
    |       Grain:  one row per team-week (keyed by referee for that game)
    |       Note:   Requires penalty metrics from team_analytics as input
    |
    |--- compute_playoff_context(schedules_df)
    |       Input:  home_score, away_score, home_team, away_team, div_game
    |       Output: wins, losses, win_pct, division_rank (1-4),
    |               conference_rank (1-16), games_back,
    |               is_eliminated (simplified), playoff_leverage_score
    |       Grain:  one row per team-week (cumulative within season)
    |
    v
Silver: teams/game_context/season=YYYY/game_context_{ts}.parquet
    Join key: [team, season, week]


Bronze PBP (existing, 103+ columns, 2016-2025)
    |
    v
src/team_analytics.py (EXTENDED — 4 new functions + 1 new orchestrator)
    |
    |--- compute_penalty_metrics(pbp_df)
    |       Input:  penalty, penalty_yards columns from PBP
    |       Output: off_penalties_per_game, off_penalty_yards_per_game,
    |               def_penalties_per_game, def_penalty_yards_per_game,
    |               off_penalty_first_downs, opponent_drawn_penalty_rate
    |       Filter: All plays with penalty==1 (including special teams)
    |       Note:   Uses raw pbp_df, NOT _filter_valid_plays() —
    |               penalties occur on all play types
    |
    |--- compute_turnover_luck(valid_plays)
    |       Input:  fumble, fumble_lost, interception from PBP
    |       Output: off_fumbles, off_fumbles_lost, off_fumble_recovery_rate,
    |               off_turnover_luck (actual_recovery - 0.50 expected),
    |               def_fumbles_forced, def_fumbles_recovered,
    |               def_fumble_recovery_rate, def_turnover_luck,
    |               off_interceptions_thrown, def_interceptions_gained
    |       Note:   NFL long-term fumble recovery rate is ~50% — deviation
    |               from 50% is "luck" that regresses to mean
    |
    |--- compute_special_teams_metrics(pbp_df)
    |       Input:  play_type, field_goal_result, extra_point_result,
    |               kick_distance, punt columns from PBP
    |       Output: fg_attempts, fg_made, fg_pct, fg_pct_40plus,
    |               xp_attempts, xp_made, xp_pct,
    |               punt_count, punt_avg_yards, punt_inside_20_pct,
    |               kick_return_avg_yards, punt_return_avg_yards,
    |               blocked_kicks_for, blocked_kicks_against
    |       Filter: play_type in ('field_goal', 'extra_point', 'punt', 'kickoff')
    |       Note:   Uses raw pbp_df — special teams plays are excluded
    |               by _filter_valid_plays()
    |
    |--- compute_red_zone_trips(valid_plays)
    |       Input:  yardline_100, drive, touchdown from PBP
    |       Output: off_rz_trips (unique drives entering RZ),
    |               off_rz_td_count, off_rz_fg_count,
    |               off_rz_scoring_pct (TD+FG / trips),
    |               def_rz_trips, def_rz_td_count, def_rz_fg_count,
    |               def_rz_scoring_pct
    |       Note:   Drive-level counting (nunique on drive),
    |               NOT play-level counting — avoids inflating trips
    |               Complements existing compute_red_zone_metrics() which
    |               provides efficiency RATES; this adds VOLUME counts
    |
    v
Silver: teams/penalties/season=YYYY/penalties_{ts}.parquet
Silver: teams/turnover_luck/season=YYYY/turnover_luck_{ts}.parquet
Silver: teams/special_teams/season=YYYY/special_teams_{ts}.parquet
Silver: teams/rz_trips/season=YYYY/rz_trips_{ts}.parquet
    All join key: [team, season, week]
    All include rolling (_roll3, _roll6, _std) variants via apply_team_rolling()
```

## Patterns to Follow

### Pattern 1: Schedule Unpivot — Home/Away to Team-Level Rows

The schedules table has one row per game with separate home/away columns. Every game_context function must unpivot into per-team rows.

**What:** Read schedules, create two DataFrames (home perspective, away perspective), concat, producing one row per team-week.

**When:** Every function in `game_context.py`.

**Example:**
```python
def _unpivot_schedules(schedules_df: pd.DataFrame) -> pd.DataFrame:
    """Convert game-level schedules to team-level rows.

    Each game produces two rows: one for the home team, one for the away team.
    Columns specific to home/away perspective are renamed to generic names.
    """
    home = schedules_df.rename(columns={
        "home_team": "team", "away_team": "opponent",
        "home_score": "team_score", "away_score": "opp_score",
        "home_rest": "days_rest", "home_coach": "head_coach",
    })
    home["is_home"] = True

    away = schedules_df.rename(columns={
        "away_team": "team", "home_team": "opponent",
        "away_score": "team_score", "home_score": "opp_score",
        "away_rest": "days_rest", "away_coach": "head_coach",
    })
    away["is_home"] = False

    return pd.concat([home, away], ignore_index=True)
```

### Pattern 2: PBP Extension — Follow Existing team_analytics.py Structure

New PBP-derived functions follow the exact pattern of `compute_team_epa`, `compute_red_zone_metrics`, etc.: groupby posteam/defteam + season + week, aggregate, merge offense + defense, return `[team, season, week, metric_cols...]`.

**What:** Each new metric function takes `valid_plays` (or raw `pbp_df` for special plays/penalties), aggregates by team-week, returns a team-week DataFrame.

**When:** Every new function added to `team_analytics.py`.

**Example:**
```python
def compute_penalty_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute penalty rates per team-week from raw PBP.

    Uses raw pbp_df (not _filter_valid_plays) because penalties
    occur on all play types including special teams.
    """
    df = pbp_df.copy()
    # Regular season filter only
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    pen = df[df["penalty"] == 1]

    off = pen.groupby(["posteam", "season", "week"]).agg(
        off_penalties=("penalty", "count"),
        off_penalty_yards=("penalty_yards", "sum"),
    ).reset_index().rename(columns={"posteam": "team"})

    defense = pen.groupby(["defteam", "season", "week"]).agg(
        def_penalties=("penalty", "count"),
        def_penalty_yards=("penalty_yards", "sum"),
    ).reset_index().rename(columns={"defteam": "team"})

    result = off.merge(defense, on=["team", "season", "week"], how="outer")
    logger.info("Penalty metrics computed for %d team-weeks", len(result))
    return result
```

### Pattern 3: Orchestrator per Output Path

Each new Silver output gets an orchestrator function that chains sub-functions, merges, and applies `apply_team_rolling()`. This mirrors `compute_pbp_metrics()` and `compute_tendency_metrics()`.

**What:** Single entry-point function per Silver output path that computes all sub-metrics, merges on `[team, season, week]`, applies rolling windows.

**When:** Every new Silver output path.

### Pattern 4: Config-Driven Silver Paths

New Silver paths are registered in `config.py` `SILVER_TEAM_S3_KEYS`:

```python
# Additions to SILVER_TEAM_S3_KEYS in config.py
SILVER_TEAM_S3_KEYS = {
    # ... existing entries ...
    "game_context": "teams/game_context/season={season}/game_context_{ts}.parquet",
    "penalties": "teams/penalties/season={season}/penalties_{ts}.parquet",
    "turnover_luck": "teams/turnover_luck/season={season}/turnover_luck_{ts}.parquet",
    "special_teams": "teams/special_teams/season={season}/special_teams_{ts}.parquet",
    "rz_trips": "teams/rz_trips/season={season}/rz_trips_{ts}.parquet",
}
```

### Pattern 5: Cumulative Within-Season Computation (Playoff Context)

Playoff context requires computing running win/loss records — a cumulative within-season calculation that differs from the rolling-window pattern.

**What:** Sort by `[team, season, week]`, compute cumsum of wins/losses, derive standings within division/conference at each week point.

**When:** `compute_playoff_context()` in `game_context.py`.

**Example:**
```python
def compute_playoff_context(team_games_df: pd.DataFrame) -> pd.DataFrame:
    """Compute running standings and playoff leverage per team-week."""
    df = team_games_df.sort_values(["team", "season", "week"])
    df["win"] = (df["team_score"] > df["opp_score"]).astype(int)
    df["loss"] = (df["team_score"] < df["opp_score"]).astype(int)

    # Cumulative wins/losses within season
    df["wins"] = df.groupby(["team", "season"])["win"].cumsum()
    df["losses"] = df.groupby(["team", "season"])["loss"].cumsum()
    df["win_pct"] = df["wins"] / (df["wins"] + df["losses"])

    # Division rank at each week (requires knowing division membership)
    # Use TEAM_DIVISIONS from config.py
    ...
    return df
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Creating New Bronze Data Types for Schedule-Resident Data

**What:** Adding a `weather` Bronze type or `coaching` Bronze type that re-ingests data already present in schedules.
**Why bad:** Duplicates data, adds ingestion complexity, creates sync issues. The schedules table already has temp, wind, roof, surface, home_coach, away_coach, referee, home_rest, away_rest.
**Instead:** Extract features directly from existing Bronze schedules in the Silver layer. Only add a new Bronze source for genuinely external data (e.g., precipitation/humidity from a weather API, which is a future Gold-layer concern).

### Anti-Pattern 2: Merging All New Features into Existing Silver Files

**What:** Adding penalty rates, turnover luck, and weather features into the existing `teams/pbp_metrics/` Silver output.
**Why bad:** Makes individual features hard to test, debug, and recompute independently. Breaks the existing test suite for pbp_metrics. Forces full recomputation when only one feature domain changes.
**Instead:** Separate Silver output paths per feature domain. Gold layer joins them when building prediction feature vectors.

### Anti-Pattern 3: Look-Ahead Bias in Cumulative Features

**What:** For playoff context, computing win_pct using the full season's results and applying it retroactively to early weeks.
**Why bad:** Creates data leakage. Week 5's win_pct should only reflect weeks 1-4.
**Instead:** Use cumsum within the sorted team-season group. For rolling features, use `shift(1)` before rolling (already established in `apply_team_rolling()`).

### Anti-Pattern 4: External Weather API for Historical Data

**What:** Calling a weather API (e.g., OpenWeatherMap) for all games from 2016-2024 when schedules already has game-time temperature and wind speed.
**Why bad:** Expensive API calls, rate-limited, and schedules data already provides actual game-time observations (not forecasts).
**Instead:** Use schedules temp/wind for all historical seasons. Only consider a weather API for future game forecasts in the Gold layer (not Silver).

### Anti-Pattern 5: Using _filter_valid_plays() for Penalty and Special Teams Metrics

**What:** Passing PBP through `_filter_valid_plays()` before computing penalty or special teams metrics.
**Why bad:** `_filter_valid_plays()` removes all non-pass/run plays (punts, field goals, kickoffs) and all penalty-only plays. This would drop the exact plays needed for these features.
**Instead:** Use raw `pbp_df` with only season_type and week filters for penalties and special teams. Use `_filter_valid_plays()` only for turnover luck and red zone trips (which are based on scrimmage plays).

## Join Strategy

All new Silver tables share the universal team-level join key: `[team, season, week]`.

```
Gold Prediction Feature Vector Assembly:
========================================

EXISTING Silver (from v1.2):
  teams/pbp_metrics/      [team, season, week]  -- EPA, success rate, CPOE, RZ efficiency
  teams/tendencies/       [team, season, week]  -- pace, PROE, 4th-down, early-down run rate
  teams/sos/              [team, season, week]  -- opponent-adjusted EPA, schedule difficulty
  teams/situational/      [team, season, week]  -- home/away, divisional, game script splits
  players/usage/          [player_id, season, week]  -- target share, rolling avgs
  players/advanced/       [player_id, season, week]  -- NGS, PFR, QBR profiles

NEW Silver (v1.3):
  teams/game_context/     [team, season, week]  -- weather, rest, coaching, referee, playoff
  teams/penalties/        [team, season, week]  -- penalty rates and yards
  teams/turnover_luck/    [team, season, week]  -- fumble recovery luck, TO differential
  teams/special_teams/    [team, season, week]  -- FG%, punt avg, return yards
  teams/rz_trips/         [team, season, week]  -- RZ trip volume counts (not just rates)

GAME-LEVEL JOIN (for prediction model):
  schedules + home_team features (left join all team Silver tables)
           + away_team features (left join all team Silver tables)
           = one row per game with ~130+ feature columns
```

## Module Responsibility Matrix

| Feature | Source Bronze | Module | Output Silver Path | Key Bronze Columns |
|---------|-------------|--------|-------------------|-------------------|
| Weather | schedules | game_context.py (NEW) | teams/game_context/ | temp, wind, roof, surface |
| Rest/Travel | schedules | game_context.py (NEW) | teams/game_context/ | home_rest, away_rest, stadium |
| Coaching | schedules | game_context.py (NEW) | teams/game_context/ | home_coach, away_coach |
| Referee | schedules + penalties | game_context.py (NEW) | teams/game_context/ | referee + penalty counts |
| Playoff Context | schedules | game_context.py (NEW) | teams/game_context/ | home_score, away_score, div_game |
| Penalties | PBP | team_analytics.py (EXTEND) | teams/penalties/ | penalty, penalty_yards |
| Turnover Luck | PBP | team_analytics.py (EXTEND) | teams/turnover_luck/ | fumble, fumble_lost, interception |
| Special Teams | PBP | team_analytics.py (EXTEND) | teams/special_teams/ | play_type, field_goal_result, kick_distance, punt cols |
| Red Zone Trips | PBP | team_analytics.py (EXTEND) | teams/rz_trips/ | yardline_100, drive, touchdown |

## PBP Column Expansion Required

The existing `PBP_COLUMNS` in config.py (103 columns) includes most needed columns but is MISSING several required for special teams and penalty detail:

| Column | Currently in PBP_COLUMNS? | Needed For | Action |
|--------|--------------------------|-----------|--------|
| penalty | YES | Penalties | None |
| fumble | YES | Turnover luck | None |
| fumble_lost | YES | Turnover luck | None |
| interception | YES | Turnover luck | None |
| touchdown | YES | Red zone trips | None |
| yardline_100 | YES | Red zone trips | None |
| drive | YES | Red zone trips | None |
| `penalty_yards` | NO | Penalty yards | ADD to PBP_COLUMNS |
| `penalty_type` | NO | Penalty type breakdown | ADD (optional, nice-to-have) |
| `field_goal_result` | NO | FG accuracy | ADD to PBP_COLUMNS |
| `extra_point_result` | NO | XP accuracy | ADD to PBP_COLUMNS |
| `kick_distance` | NO | FG/punt distance | ADD to PBP_COLUMNS |
| `punt_blocked` | NO | Blocked kicks | ADD to PBP_COLUMNS |
| `return_yards` | NO | Return averages | ADD to PBP_COLUMNS |
| `kickoff_attempt` | NO | Kickoff identification | ADD to PBP_COLUMNS |

**Action: Expand PBP_COLUMNS by ~8 columns.** This is a config-only change. Existing PBP files will need re-ingestion for affected seasons, OR the special teams function can load raw PBP without the column filter (accepting larger memory footprint for special teams computation only).

**Recommended approach:** Add columns to PBP_COLUMNS, then re-ingest PBP for 2016-2025. This is ~10 minutes of batch ingestion and keeps the architecture clean.

## Build Order (Dependency-Driven)

```
Phase 1: PBP Column Expansion
  config.py: add ~8 columns to PBP_COLUMNS
  bronze_ingestion: re-ingest PBP with expanded columns (optional; or load raw)
  No Silver output yet — just infrastructure

Phase 2: PBP-Derived Team Features (penalties, turnover luck, red zone trips)
  team_analytics.py: add compute_penalty_metrics(), compute_turnover_luck(),
                     compute_red_zone_trips()
  silver_team_transformation.py: call new functions, write new Silver paths
  Tests for each new function
  Dependencies: Phase 1 (PBP columns)

Phase 3: Special Teams Metrics
  team_analytics.py: add compute_special_teams_metrics()
  silver_team_transformation.py: call new function
  Dependencies: Phase 1 (PBP columns — field_goal_result, kick_distance)

Phase 4: Schedule-Derived Features (weather, rest/travel, coaching)
  game_context.py: NEW module with compute_weather_features(),
                   compute_rest_travel(), compute_coaching_changes()
  config.py: add STADIUM_COORDINATES dict
  silver_game_context_transformation.py: NEW script
  Dependencies: None (reads existing schedules Bronze)

Phase 5: Referee Tendencies
  game_context.py: add compute_referee_tendencies()
  Dependencies: Phase 2 (needs penalty counts from Silver) + Phase 4 (game_context module exists)

Phase 6: Playoff Context
  game_context.py: add compute_playoff_context()
  Dependencies: Phase 4 (game_context module exists)
  Note: Most complex computation (cumulative standings, division rankings)

Phase 7: Pipeline Health + Integration Testing
  scripts/check_pipeline_health.py: add checks for new Silver paths
  Integration tests verifying end-to-end Silver output
  Dependencies: All previous phases
```

**Rationale for this order:**
1. PBP column expansion first because it unblocks phases 2-3
2. PBP-derived features next because they extend an existing, well-tested module (team_analytics.py)
3. Special teams after basic PBP features because it needs the same column expansion but is more complex (punt/kick/FG play types)
4. Schedule-derived features after PBP because they require a new module (game_context.py) — more infrastructure
5. Referee tendencies after penalties + game_context because it joins data from both
6. Playoff context last because it's the most complex computation (cumulative standings)

## Scalability Considerations

| Concern | At 10 seasons (current) | At 20 seasons | Notes |
|---------|------------------------|---------------|-------|
| PBP memory per season | ~120 MB raw PBP | Same per season | Per-season loop in transformation script handles this |
| New Silver file count | 5 new paths x 10 seasons = 50 files | 5 x 20 = 100 | Manageable; glob + latest-file pattern |
| Feature vector width | ~80 existing + ~50 new = ~130 features | Same | Pandas handles easily |
| game_context computation | ~500 rows per season (32 teams x ~17 weeks) | Same | Trivially fast |
| Stadium coordinates | 32 stadiums (static dict) | Same | Hardcode in config.py |
| Playoff context | ~500 rows x cumsum | Same per season | Fast; no cross-season computation |

## Sources

- `src/team_analytics.py` -- existing team PBP metrics module (847 lines), established patterns for compute functions, orchestrators, and rolling windows
- `src/player_analytics.py` -- existing player analytics module (418 lines), schedule unpivot patterns in `compute_venue_splits()`
- `src/config.py` -- PBP_COLUMNS (103 columns, lines 156-203), SILVER_TEAM_S3_KEYS (lines 136-141), TEAM_DIVISIONS
- `src/projection_engine.py` -- Gold layer consumption patterns for Silver data
- `docs/NFL_DATA_DICTIONARY.md` -- schedules schema confirms: temp, wind, roof, surface, away_rest, home_rest, away_coach, home_coach, referee, stadium columns
- `scripts/silver_team_transformation.py` -- existing team transformation CLI patterns
- `scripts/bronze_ingestion_simple.py` -- DATA_TYPE_REGISTRY pattern for ingestion
- `.planning/PROJECT.md` -- v1.3 milestone requirements
- Confidence: HIGH -- all recommendations based on direct codebase inspection of existing modules, Bronze schemas, and Silver output patterns
