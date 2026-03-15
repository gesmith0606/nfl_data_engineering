# NFL Game Prediction Data Model

**Version:** 3.0
**Last Updated:** March 15, 2026
**Purpose:** Comprehensive data model designed for NFL game prediction using machine learning and advanced analytics

## Status Legend

| Badge | Meaning |
|-------|---------|
| **Implemented** | Built and available in the current system |
| **In Progress** | Partially built or being actively developed |
| **Planned** | Designed but not yet implemented |

## Executive Summary

This document presents a comprehensive NFL data model specifically designed for game prediction within a medallion architecture (Bronze -> Silver -> Gold). The model incorporates modern sports analytics best practices, machine learning features, and advanced NFL metrics including Expected Points Added (EPA), Completion Percentage Over Expected (CPOE), and Win Probability.

Based on 2024-2025 research, this model supports prediction methodologies using Random Forest, Neural Networks, and XGBoost algorithms while maintaining compatibility with our existing Bronze layer data from nfl-data-py.

For full column specifications of all Bronze data types, see the [NFL Data Dictionary](NFL_DATA_DICTIONARY.md).

## Architecture Overview

### Medallion Architecture Implementation

```
Raw NFL Data -> Bronze Layer -> Silver Layer -> Gold Layer -> Prediction Models
    |              |             |            |             |
nfl-data-py    Raw Data      Cleaned &    Analytics     ML Features
   API        Storage       Validated     Ready        & Predictions
```

#### Layer Responsibilities

- **Bronze Layer (s3://nfl-raw)** -- **Implemented**: Raw data ingestion from nfl-data-py with minimal transformation
- **Silver Layer (s3://nfl-refined)** -- **Partially Implemented**: Fantasy analytics (usage, rolling avgs, opp rankings), team PBP metrics, team tendencies, strength of schedule, situational splits, and advanced player profiles implemented; game prediction features (matchup features, enhanced games/plays/player_stats tables) planned
- **Gold Layer (s3://nfl-trusted)** -- **Partially Implemented**: Fantasy projections implemented; game outcome predictions planned
- **Platinum Layer** -- **Planned**: Real-time prediction serving and model inference (future extension)

## Conceptual Data Model

### Core Entities and Relationships

```
+--------------+     +--------------+     +--------------+
|   SEASONS    |---->|    TEAMS     |<----|   PLAYERS    |
+--------------+     +--------------+     +--------------+
       |                     |                  |
       v                     v                  v
+--------------+     +--------------+     +--------------+
|    GAMES     |<----|   ROSTERS    |---->|   COACHING   |
+--------------+     +--------------+     +--------------+
       |                     |                  |
       v                     v                  v
+--------------+     +--------------+     +--------------+
|    PLAYS     |---->| PLAY_ACTORS  |---->|  INJURIES    |
+--------------+     +--------------+     +--------------+
       |                     |                  |
       v                     v                  v
+--------------+     +--------------+     +--------------+
|  ANALYTICS   |---->| SITUATIONAL  |---->|  WEATHER     |
+--------------+     +--------------+     +--------------+
```

### Predictive Feature Categories

1. **Team Performance Metrics**: Historical win rates, scoring efficiency, defensive strength
2. **Player Performance**: QB ratings, key player stats, injury status
3. **Situational Factors**: Home/away, division games, rest days, weather
4. **Advanced Analytics**: EPA, CPOE, success rates, explosive play rates
5. **Temporal Patterns**: Season progression, momentum, recent form
6. **Head-to-Head**: Historical matchups, coaching matchups, scheme advantages

---

## Bronze Layer Schema -- Implemented

All Bronze tables below are ingested and stored in `data/bronze/` (local) and `s3://nfl-raw/` (when AWS credentials are active). For full column specs, see the [NFL Data Dictionary](NFL_DATA_DICTIONARY.md).

### Core Game Data

#### Games/Schedules -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_schedules()`
- **Storage:** `s3://nfl-raw/schedules/season=YYYY/`
- **Seasons:** 1999-2025
- **Key columns:** game_id, season, week, home_team, away_team, home_score, away_score, spread_line, total_line, roof, div_game
- **Full column specs:** See [NFL Data Dictionary -- Schedules](NFL_DATA_DICTIONARY.md#schedules-games)

#### Play-by-Play (PBP) -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_pbp()`
- **Storage:** `s3://nfl-raw/pbp/season=YYYY/`
- **Seasons:** 2010-2025
- **Key columns:** 103 curated columns including epa, wpa, cpoe, air_yards, success, yards_gained, down, ydstogo, play_type
- **Full column specs:** See [NFL Data Dictionary -- Play-by-Play](NFL_DATA_DICTIONARY.md#play-by-play-pbp)

### Player Data

#### Player Weekly Stats -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_player_weekly()`
- **Storage:** `s3://nfl-raw/player_weekly/season=YYYY/`
- **Seasons:** 1999-2025
- **Key columns:** player_id, player_name, position, recent_team, completions, attempts, passing_yards, rushing_yards, receptions, receiving_yards, targets, fantasy_points
- **Full column specs:** See [NFL Data Dictionary -- Player Weekly](NFL_DATA_DICTIONARY.md#player-weekly-stats)

#### Player Seasonal Stats -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_player_seasonal()`
- **Storage:** `s3://nfl-raw/player_seasonal/season=YYYY/`
- **Seasons:** 1999-2025
- **Full column specs:** See [NFL Data Dictionary -- Player Seasonal](NFL_DATA_DICTIONARY.md#player-seasonal-stats)

#### Rosters -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_rosters()`
- **Storage:** `s3://nfl-raw/rosters/season=YYYY/`
- **Seasons:** 2002-2025
- **Key columns:** player_id, player_name, position, team, jersey_number, height, weight, years_exp, college
- **Full column specs:** See [NFL Data Dictionary -- Rosters](NFL_DATA_DICTIONARY.md#rosters)

### Team and Context Data

#### Teams -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_teams()`
- **Storage:** `s3://nfl-raw/teams/`
- **Key columns:** team_abbr, team_name, team_division, team_conference, team_logo
- **Full column specs:** See [NFL Data Dictionary -- Teams](NFL_DATA_DICTIONARY.md#teams)

#### Snap Counts -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_snap_counts()`
- **Storage:** `s3://nfl-raw/snap_counts/season=YYYY/week=WW/`
- **Seasons:** 2012-2025
- **Key columns:** player, team, position, offense_snaps, offense_pct, defense_snaps, defense_pct
- **Full column specs:** See [NFL Data Dictionary -- Snap Counts](NFL_DATA_DICTIONARY.md#snap-counts)

#### Injuries -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_injuries()`
- **Storage:** `s3://nfl-raw/injuries/season=YYYY/week=WW/`
- **Seasons:** 2009-2025
- **Key columns:** gsis_id, season, week, team, report_status, practice_status
- **Full column specs:** See [NFL Data Dictionary -- Injuries](NFL_DATA_DICTIONARY.md#injuries)

### Advanced Stats

#### NGS Data (Passing, Rushing, Receiving) -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_ngs()`
- **Storage:** `s3://nfl-raw/ngs/{stat_type}/season=YYYY/`
- **Seasons:** 2016-2025
- **Sub-types:** passing (completion probability, air distance), rushing (efficiency, time behind line), receiving (separation, catch probability)
- **Full column specs:** See [NFL Data Dictionary -- NGS](NFL_DATA_DICTIONARY.md#ngs-passing)

#### PFR Stats (Weekly + Seasonal) -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_pfr_weekly()` and `fetch_pfr_seasonal()`
- **Storage:** `s3://nfl-raw/pfr/{stat_type}/season=YYYY/`
- **Seasons:** 2018-2025
- **Sub-types:** pass, rush, rec, def (weekly and seasonal variants)
- **Full column specs:** See [NFL Data Dictionary -- PFR](NFL_DATA_DICTIONARY.md#pfr-weekly-passing)

#### QBR -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_qbr()`
- **Storage:** `s3://nfl-raw/qbr/season=YYYY/`
- **Seasons:** 2006-2025
- **Sub-types:** weekly and seasonal
- **Full column specs:** See [NFL Data Dictionary -- QBR](NFL_DATA_DICTIONARY.md#qbr-weekly)

### Context Data

#### Depth Charts -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_depth_charts()`
- **Storage:** `s3://nfl-raw/depth_charts/season=YYYY/`
- **Seasons:** 2020-2025
- **Full column specs:** See [NFL Data Dictionary -- Depth Charts](NFL_DATA_DICTIONARY.md#depth-charts)

#### Draft Picks -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_draft_picks()`
- **Storage:** `s3://nfl-raw/draft_picks/season=YYYY/`
- **Seasons:** 2000-2025
- **Full column specs:** See [NFL Data Dictionary -- Draft Picks](NFL_DATA_DICTIONARY.md#draft-picks)

#### Combine -- Implemented

- **Source:** `nfl-data-py` via `NFLDataAdapter.fetch_combine()`
- **Storage:** `s3://nfl-raw/combine/season=YYYY/`
- **Seasons:** 2000-2025
- **Full column specs:** See [NFL Data Dictionary -- Combine](NFL_DATA_DICTIONARY.md#combine)

### Not Ingested (Out of Scope)

| Data Source | Reason |
|-------------|--------|
| Weather API | PBP already includes temp/wind; separate pipeline adds ~2pp for high complexity |
| Officials/referee | Minimal game prediction value per research |
| FTN charting | Only 3 seasons of history, insufficient for ML training |
| Win totals | Source flagged as "in flux" by nflverse; unreliable |

---

## Silver Layer Schema

### Fantasy Analytics -- Implemented

The existing Silver layer supports fantasy football projections. These tables are built by `scripts/silver_player_transformation.py`.

#### Player Usage Metrics (Silver) -- Implemented

```
Storage: s3://nfl-refined/player_usage/season=YYYY/
```

Aggregates player usage metrics from weekly stats: target share, carry share, snap percentage, air yards share, red zone opportunities. Used as input to the projection engine.

See [NFL Data Dictionary -- Player Usage Metrics](NFL_DATA_DICTIONARY.md#3-player-usage-metrics-silver) for full column specs.

#### Opponent Rankings (Silver) -- Implemented

```
Storage: s3://nfl-refined/opp_rankings/season=YYYY/
```

Ranks all 32 teams (1-32) for points allowed to each position (QB, RB, WR, TE). Used as matchup multiplier in projections.

See [NFL Data Dictionary -- Opponent Rankings](NFL_DATA_DICTIONARY.md#4-opponent-rankings-silver) for full column specs.

#### Rolling Averages (Silver) -- Implemented

```
Storage: s3://nfl-refined/rolling_stats/season=YYYY/
```

3-game and 6-game rolling averages for key stats (passing yards, rushing yards, receiving yards, fantasy points). Weighted by recency in projections (roll3: 45%, roll6: 30%, std: 25%).

See [NFL Data Dictionary -- Rolling Averages](NFL_DATA_DICTIONARY.md#5-rolling-averages-silver) for full column specs.

### Team PBP Metrics (Silver) -- Implemented

Built by `scripts/silver_team_transformation.py`, computed by `src/team_analytics.py` (Phase 15).

#### Team EPA Aggregates (Silver) -- Implemented

```
Storage: data/silver/teams/pbp_metrics/season=YYYY/
```

Team-level EPA aggregates computed from play-by-play data. Covers offense and defense EPA per play, passing and rushing splits, completion percentage over expected (CPOE), success rate, and red zone efficiency. One row per team per season.

Key columns:
- team, season
- off_epa_per_play, def_epa_per_play
- pass_epa_per_play, rush_epa_per_play
- cpoe, success_rate
- red_zone_success_rate

### Team Tendencies (Silver) -- Implemented

Built by `scripts/silver_team_transformation.py` (Phase 16).

```
Storage: data/silver/teams/tendencies/season=YYYY/
```

Offensive and defensive scheme tendencies derived from play-by-play data. Captures pace, pass rate preferences, and fourth-down aggressiveness signals.

Key columns:
- team, season
- plays_per_game (pace)
- pass_rate_over_expected (PROE)
- fourth_down_go_rate (aggressiveness)
- early_down_run_rate

### Strength of Schedule (Silver) -- Implemented

Built by `scripts/silver_team_transformation.py` (Phase 16).

```
Storage: data/silver/teams/sos/season=YYYY/
```

Opponent-adjusted EPA rankings for each team's offense and defense schedule. Ranks all 32 teams on the quality of opponents faced, used to contextualize raw EPA metrics.

Key columns:
- team, season
- off_sos_rank (1-32, opponent defensive EPA rank)
- def_sos_rank (1-32, opponent offensive EPA rank)

### Situational Splits (Silver) -- Implemented

Built by `scripts/silver_team_transformation.py` (Phase 16).

```
Storage: data/silver/teams/situational/season=YYYY/
```

Team performance segmented by game context: home vs. away, divisional vs. non-divisional, and game script (leading, trailing, close games). Supports situational feature construction for the game prediction pipeline.

Key columns:
- team, season, split_type (home/away/divisional/non_divisional/leading/trailing/close)
- epa_per_play, success_rate, pass_rate, win_rate

### Advanced Player Profiles (Silver) -- Implemented

Built by `scripts/silver_advanced_transformation.py`, computed by `src/player_advanced_analytics.py` (Phase 17).

```
Storage: data/silver/players/advanced/season=YYYY/
```

Player-level advanced metrics aggregated from NGS, PFR, and QBR sources. Covers all three position groups (QB, RB, WR/TE) with tracking-based and pressure-based signals.

Key columns:
- player_id, player_name, position, team, season
- **Receiving (NGS):** avg_separation, catch_probability, avg_intended_air_yards
- **Passing (NGS):** avg_time_to_throw, aggressiveness, completion_percentage_above_expectation (CPAE)
- **Rushing (NGS):** rush_yards_over_expected (RYOE), efficiency
- **Pressure (PFR):** times_pressured, sack_rate, hurry_rate, team_blitz_rate
- **QBR:** qbr_total, qbr_points_added

### Game Prediction Features -- Planned

The following Silver tables are designed for the game prediction pipeline (v2 requirements SLV-01 to SLV-03).

#### Rolling Team EPA (Silver) -- Planned

```
Storage: s3://nfl-refined/team_epa/season=YYYY/week=WW/
```

Week-scoped rolling offensive and defensive EPA per play, extending the implemented season-level PBP metrics table with exponentially weighted rolling windows. Will support requirements SLV-01 (team EPA aggregates) and SLV-02 (exponentially weighted rolling metrics).

Key planned columns:
- team_id, season, week
- off_epa_per_play, def_epa_per_play (rolling 3/6 game windows)
- pass_epa_per_play, rush_epa_per_play
- success_rate, explosive_play_rate
- Schedule-adjusted metrics combining team_epa + sos tables

#### Matchup Features (Silver) -- Planned

```
Storage: s3://nfl-refined/matchup_features/season=YYYY/week=WW/
```

Team A offense vs Team B defense feature combinations for each game. Will support requirement SLV-03 (matchup feature generation).

Key planned columns:
- game_id, home_team, away_team
- off_vs_def_epa_diff (home offense EPA minus away defense EPA)
- pass_matchup_advantage, rush_matchup_advantage
- Recent form differentials, rest advantage

#### Games (Silver) -- Planned

```
Storage: s3://nfl-refined/games/season=YYYY/
```

Enhanced game-level data with standardized fields, derived flags (prime time, dome, division game), and betting results. See the conceptual schema below.

Key planned columns:
- game_id, season, week, game_date
- home_team_id, away_team_id, home_score, away_score
- game_result, total_points, overtime_flag
- spread, total_line, spread_cover_result, total_result
- division_game_flag, playoff_flag, prime_time_flag
- rest_differential, data_quality_score

#### Teams (Silver) -- Planned

```
Storage: s3://nfl-refined/teams/
```

Standardized team reference data with geographic info, stadium details, and conference/division mapping.

#### Plays (Silver) -- Planned

```
Storage: s3://nfl-refined/plays/season=YYYY/week=WW/
```

Cleaned play-by-play with enhanced categorization: drive identifiers, game state tracking, standardized player IDs, and success flags.

#### Player Stats (Silver) -- Planned

```
Storage: s3://nfl-refined/player_stats/season=YYYY/week=WW/
```

Position-partitioned player statistics combining weekly stats, snap counts, and advanced metrics into a single unified view per player-week.

---

## Gold Layer Schema

### Fantasy Projections -- Implemented

The existing Gold layer produces fantasy football projections. Built by `scripts/generate_projections.py`.

#### Weekly Projections (Gold) -- Implemented

```
Storage: s3://nfl-trusted/projections/season=YYYY/week=WW/
```

Per-player weekly fantasy point projections with floor/ceiling ranges. Incorporates rolling averages, usage metrics, opponent rankings, injury adjustments, and Vegas implied team totals.

See [NFL Data Dictionary -- Weekly Projections](NFL_DATA_DICTIONARY.md#1-weekly-projections-gold) for full column specs.

#### Preseason Projections (Gold) -- Implemented

```
Storage: s3://nfl-trusted/preseason_projections/season=YYYY/
```

Full-season fantasy point projections for draft preparation. Includes rookie fallback baselines and position-specific regression shrinkage.

See [NFL Data Dictionary -- Preseason Projections](NFL_DATA_DICTIONARY.md#2-preseason-projections-gold) for full column specs.

### Game Prediction Analytics -- Planned

The following Gold tables are designed for the game outcome prediction pipeline (v2 requirements ML-01 to ML-03).

#### Team Performance Metrics (Gold) -- Planned

```
Storage: s3://nfl-trusted/team_performance/season=YYYY/
```

Team-level aggregated performance metrics for offense, defense, and special teams. Includes EPA-based advanced metrics, situational performance, and strength of schedule adjustments.

Key planned columns:
- team_id, season, metric_type (offense/defense/special_teams), week_number
- epa_per_play, success_rate, explosive_play_rate
- Passing and rushing splits (epa, success rate)
- Situational metrics (early down, late down, red zone, two-minute)
- Strength of schedule adjustments

#### Game Prediction Features (Gold) -- Planned

```
Storage: s3://nfl-trusted/prediction_features/season=YYYY/week=WW/
```

Pre-computed ML features for each game, combining team performance, player impact, situational factors, and betting market data into a single feature vector per game.

Key planned columns:
- game_id, season, week, prediction_date
- Team strength metrics (Elo, EPA differentials, recent form)
- QB performance features (EPA, CPOE, pressure rate)
- Injury impact scores, rest advantage
- Head-to-head history, coaching matchup stats
- Weather impact, betting market indicators
- Target variables: actual_home_score, actual_margin, home_win_flag

#### Player Impact Ratings (Gold) -- Planned

```
Storage: s3://nfl-trusted/player_impact/season=YYYY/
```

Individual player impact on team performance, including usage/opportunity metrics, position-specific performance ratings, and replacement value calculations.

Key planned columns:
- player_id, season, week_number, team_id, position
- Snap percentage, target share, carry share
- EPA per play, success rate, explosiveness rate
- Position-specific: QB (CPOE, time to throw), WR (separation, catch rate), RB (YBC, broken tackles)
- Team EPA with/without player, win shares, replacement value

---

## Advanced Analytics Schema -- Planned

### Expected Points and Win Probability Models -- Planned

#### Expected Points Model (Gold) -- Planned

```
Storage: s3://nfl-trusted/expected_points/
```

Situational expected points lookup table: given down, distance, yard line, quarter, and score differential, provides expected points and outcome probabilities (TD, FG, safety, turnover, punt).

Note: EPA values from nfl-data-py PBP data are already available in Bronze. This table would provide a custom model trained on our data.

#### Win Probability Model (Gold) -- Planned

```
Storage: s3://nfl-trusted/win_probability/
```

Play-by-play win probability tracking with WPA (Win Probability Added) calculations, leverage index, and clutch situation identification.

Note: WPA values from nfl-data-py PBP data are already available in Bronze. This table would provide enhanced tracking and model serving.

#### Game Flow Analytics (Gold) -- Planned

```
Storage: s3://nfl-trusted/game_flow/
```

Play-by-play momentum tracking, game script analysis, and pace-of-play metrics. Designed for in-game prediction model updates.

---

## Temporal Data Structures -- Planned

### Season Progression Tracking

#### Team Performance Trends (Gold) -- Planned

```
Storage: s3://nfl-trusted/performance_trends/
```

Week-over-week team performance evolution: rolling PPG, EPA trends, strength of schedule changes, playoff probability updates, and injury severity tracking.

#### Player Development Tracking (Gold) -- Planned

```
Storage: s3://nfl-trusted/player_development/
```

Individual player performance progression: rolling efficiency metrics, rookie progression curves, veteran decline tracking, scheme fit ratings, and clutch performance ratings.

---

## Machine Learning Integration -- Planned

### Feature Engineering Pipeline -- Planned

The ML pipeline will produce 200+ features per game (requirement ML-01), including:

1. **Team features:** EPA-based offense/defense ratings, success rates, explosive play rates, turnover margins
2. **Player features:** QB EPA, CPOE, pressure handling; key skill player usage and efficiency
3. **Situational features:** Rest days, travel distance, prime time, division rivalry, weather impact
4. **Temporal features:** Rolling averages (3/6/10 game windows), season progression, momentum indicators
5. **Market features:** Spread, total, line movement, public betting percentage
6. **Historical features:** Head-to-head records, coaching matchup history

### Model Architecture -- Planned

| Model | Role | Target |
|-------|------|--------|
| Random Forest | Primary classifier | Win/loss prediction |
| XGBoost | Ensemble component | Spread prediction, point total |
| Neural Network | Secondary model | Complex interaction features |

**Target performance (ML-03):** 65%+ accuracy, <3.5 point spread MAE.

**Validation approach (ML-02):** Leave-one-season-out cross-validation to prevent temporal leakage.

### Model Evaluation Framework -- Planned

Key metrics:
- **Classification:** Accuracy, AUC-ROC, precision/recall for upset detection
- **Regression:** MAE, RMSE for spread and total predictions
- **Calibration:** Predicted probability vs actual outcome frequency
- **Against market:** Performance vs closing spread (profitable if >52.4% ATS)

---

## Implementation Guidelines

### S3 Storage Strategy

#### Partitioning Schema
```
s3://{bucket}/{table}/
  season=2024/
    week=01/
      data_20240909_143022.parquet
    week=02/
    ...
  season=2023/
    week=01/
    ...
```

#### File Naming Convention
```
{table_name}_{YYYYMMDD}_{HHMMSS}.parquet
```

#### Format and Compression
- **Format**: Apache Parquet
- **Compression**: Snappy (balance of speed and size)
- **Read convention**: Always use `download_latest_parquet()` from `src/utils.py`

### Data Quality Framework -- Implemented

Validation is handled by `NFLDataFetcher.validate_data()` at Bronze ingestion time. Required column checks are defined per data type in the adapter layer.

See `src/nfl_data_integration.py` for the validation implementation.

---

## Data Governance

### Security and Access Control -- Implemented

- AWS credentials managed via `.env` file (never committed)
- Pre-commit hook blocks credential patterns (AKIA*, github_pat_*, private keys)
- IAM permissions scoped to S3 buckets (nfl-raw, nfl-refined, nfl-trusted)

### Monitoring -- Implemented

- GitHub Actions weekly pipeline (Tuesdays 9am UTC)
- `scripts/check_pipeline_health.py` for S3 freshness and file size checks
- Auto-opens GitHub issue on pipeline failure

---

## Migration Strategy

### Completed Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | Infrastructure Prerequisites | **Implemented** |
| 2 | Core PBP Ingestion | **Implemented** |
| 3 | Advanced Stats & Context Data | **Implemented** |
| 4 | Documentation Update | **Implemented** |
| 5–14 | Fantasy Analytics Pipeline (Bronze → Silver → Gold → Draft) | **Implemented** |
| 15 | Silver Team PBP Metrics | **Implemented** |
| 16 | Silver Team Tendencies, SOS, Situational Splits | **Implemented** |
| 17 | Silver Advanced Player Profiles (NGS, PFR, QBR) | **Implemented** |

### Upcoming Phases (v2)

| Phase | Name | Requirements | Status |
|-------|------|-------------|--------|
| 18 | Rolling Team EPA (week-scoped) | SLV-01, SLV-02 | **Planned** |
| 19 | Matchup Features | SLV-03 | **Planned** |
| 20 | ML Pipeline | ML-01, ML-02, ML-03 | **Planned** |
| 21 | nflreadpy Migration | MIG-01 | **Planned** |

See [NFL Data Model Implementation Guide](NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md) for detailed phase descriptions.

---

## Conclusion

This data model provides a comprehensive foundation for NFL game prediction. The Bronze layer is fully implemented with 15+ data types covering games, players, advanced stats, and context data. The Silver layer now includes five implemented subsections beyond the original fantasy analytics pipeline: team PBP metrics (EPA, CPOE, success rate, red zone), team tendencies (pace, PROE, 4th-down aggressiveness), strength of schedule rankings, situational splits (home/away, divisional, game script), and advanced player profiles aggregating NGS tracking, PFR pressure data, and QBR. The Gold layer has working fantasy projections, with game outcome predictions planned as v2 work. The ML integration layer is designed to produce 200+ features targeting 65%+ prediction accuracy.

---
*Version 3.0 -- Updated March 15, 2026 to document Silver layer expansion through Phase 17 (team metrics, tendencies, SOS, situational splits, advanced player profiles)*
