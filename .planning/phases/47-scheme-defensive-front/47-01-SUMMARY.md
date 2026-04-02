# Phase 47-01 Summary: Scheme Classification + Defensive Front Proxy Features

## Status: COMPLETE

## What was built

### Step 1: Scheme Classification (`src/graph_scheme.py`)
- `classify_run_scheme(pbp_df, season)` — classifies each team's offensive run scheme per season
  - Computes run_gap distribution (end/tackle/guard rates), run_location distribution, shotgun_rate, no_huddle_rate
  - Classification: zone (end_rate > 0.35 or balanced location), gap_power (guard+tackle > 0.50), spread (shotgun > 0.60), balanced (default)
- `build_scheme_nodes(graph_db, schemes_df)` — creates (:Scheme) nodes and (:Team)-[:RUNS_SCHEME]->(:Scheme) edges

### Step 2: Defensive Front Profiling (`src/graph_scheme.py`)
- `compute_defensive_front_quality(pfr_def_df, rosters_df)` — front-7 composite per team-week
  - Filters to DL/LB positions via roster join, or uses sack/pressure heuristic when no roster data
  - Composite: 0.3*sacks + 0.3*pressures + 0.2*hurries + 0.2*tackles
  - Rolling 3-game average with shift(1) for temporal safety
- `build_defends_run_edges(graph_db, def_front_df)` — creates [:DEFENDS_RUN] edges

### Step 3: Scheme Matchup Features (`src/graph_feature_extraction.py`)
- `compute_scheme_features(pbp_df, pfr_def_df, rosters_df, schedules_df)` — 4 features:
  - `def_front_quality_vs_run`: opposing team's front7_quality (rolling 3, shift(1))
  - `scheme_matchup_score`: historical YPC of same scheme type vs opponent front7 tier
  - `rb_ypc_by_gap_vs_defense`: team YPC vs this specific opponent (prior meetings only)
  - `def_run_epa_allowed`: opposing defense EPA on run plays (rolling 3, shift(1))
- `SCHEME_FEATURE_COLUMNS` constant exported

### Step 4: Integration (`src/player_feature_engineering.py`)
- `_join_scheme_features()` added as step 14 in `assemble_player_features()`
- Pattern: try cached Silver parquet, fallback to Bronze computation, fallback to NaN columns
- RB-only: non-RB positions get NaN for all scheme features

### Step 5: Tests (`tests/test_graph_scheme.py`)
- 28 tests covering:
  - Scheme classification (zone/gap_power/spread/balanced) with synthetic PBP
  - Defensive front composite calculation and temporal lag
  - Scheme matchup feature computation
  - Empty/missing data handling
  - Neo4j integration (mocked)
  - Player feature engineering integration (RB-only enforcement)

## Test Results
- **28 new tests**: all passing
- **797 total tests**: all passing (up from 769)
- No regressions

## Files Changed
| File | Change |
|------|--------|
| `src/graph_scheme.py` | NEW — scheme classification + defensive front profiling |
| `src/graph_feature_extraction.py` | Added SCHEME_FEATURE_COLUMNS + compute_scheme_features() |
| `src/player_feature_engineering.py` | Added _join_scheme_features() as step 14 |
| `tests/test_graph_scheme.py` | NEW — 28 tests |

## Data Sources
- PBP: `data/bronze/pbp/season=YYYY/` — run_gap, run_location, shotgun, no_huddle confirmed
- PFR defensive: `data/bronze/pfr/weekly/def/season=YYYY/` — def_sacks, def_pressures, def_times_hurried, def_tackles_combined
- Schedules: `data/bronze/schedules/season=YYYY/` or derived from PBP posteam/defteam
