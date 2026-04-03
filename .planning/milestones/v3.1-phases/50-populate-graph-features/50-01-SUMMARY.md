# Phase 50-01: Populate Graph Features from PBP Participation Data

## What was done

Created `scripts/compute_graph_features.py` to compute all graph-derived features from PBP participation data and cache them as Silver-layer parquet files. Also fixed a bug in `src/player_feature_engineering.py` where the `_join_graph_features` function used a wildcard glob (`*.parquet`) that incorrectly picked up non-injury-cascade files.

## Script: compute_graph_features.py

**CLI**: `python scripts/compute_graph_features.py --seasons 2020 2021 2022 2023 2024 2025`

Loads 8 Bronze data sources per season (PBP participation, PBP, rosters, depth charts, injuries, player_weekly, PFR defensive, schedules) and computes 5 feature groups:

| Feature Group | Function | Output Columns |
|---------------|----------|----------------|
| WR Matchup | `compute_wr_matchup_features()` | def_pass_epa_allowed, wr_epa_vs_defense_history, cb_cooccurrence_quality, similar_wr_vs_defense |
| OL/RB | `compute_ol_rb_features()` | ol_starters_active, ol_backup_insertions, rb_ypc_with_full_ol, rb_ypc_delta_backup_ol, ol_continuity_score |
| TE | `compute_te_features()` | te_lb_coverage_rate, te_vs_defense_epa_history, te_red_zone_target_share, def_te_fantasy_pts_allowed |
| Scheme | `compute_scheme_features()` | def_front_quality_vs_run, scheme_matchup_score, rb_ypc_by_gap_vs_defense, def_run_epa_allowed |
| Injury Cascade | `compute_graph_features_from_data()` | injury_cascade_target_boost, injury_cascade_carry_boost, teammate_injured_starter, historical_absorption_rate |

Output files per season in `data/silver/graph_features/season=YYYY/`:
- `graph_wr_matchup_TIMESTAMP.parquet`
- `graph_ol_rb_TIMESTAMP.parquet`
- `graph_te_matchup_TIMESTAMP.parquet`
- `graph_scheme_TIMESTAMP.parquet`
- `graph_injury_cascade_TIMESTAMP.parquet`
- `graph_all_features_TIMESTAMP.parquet` (combined player-level)

## Coverage Results (Target: 60%+)

| Season | WR Coverage | RB/OL Coverage | TE Coverage |
|--------|-------------|----------------|-------------|
| 2020 | 73.1% | 90.3% | 95.0% |
| 2021 | 73.4% | 89.8% | 94.7% |
| 2022 | 72.9% | 90.1% | 94.5% |
| 2023 | 73.3% | 90.3% | 95.0% |
| 2024 | 73.2% | 90.4% | 94.5% |
| 2025 | 75.2% | 90.7% | 94.3% |

All positions exceed the 60% target across all 6 seasons.

## Temporal Safety

- Week 1 features are correctly NaN for all rolling features (confirmed: `def_run_epa_allowed`, `def_front_quality_vs_run` both NaN in week 1)
- All feature computations use `shift(1)` or filter to `week < target_week` to prevent data leakage

## Bug Fix: _join_graph_features glob pattern

**File**: `src/player_feature_engineering.py`, line 381

**Problem**: `_join_graph_features` used `glob.glob("*.parquet")` which picked up all files (including `graph_all_features_*`, `graph_wr_matchup_*`, etc.). The last file alphabetically was `graph_wr_matchup_*`, which lacked the expected injury cascade columns, causing a `KeyError`.

**Fix**: Changed glob pattern to `graph_injury_cascade_*.parquet` to match only the correct file type. This fixed 8 test failures in `test_player_feature_engineering.py`.

## Test Results

- **858 passed**, 0 failed, 1 skipped (up from 841 passing; 8 previously-failing tests now fixed)
- All graph infrastructure, phase 2, TE matchup, and scheme tests pass

## Output Summary

- Total files created: 35 (6 per season x 6 seasons, minus 1 empty injury cascade for 2025)
- Total Silver cache size: ~1.3 MB across all seasons
- Computation time: ~16 minutes total for all 6 seasons

## Known Gaps

- `cb_cooccurrence_quality`: Always NaN — requires deeper WR-CB alignment logic from participation data; the current fallback doesn't populate this. Low-priority since other WR features provide coverage.
- `te_red_zone_target_share`: Always NaN — the `rz_target_share` column is not in player_weekly; would need red zone computation from PBP.
- `rb_ypc_delta_backup_ol`: Always NaN — there are no plays where OL count < 5 in the participation data (all plays show 5+ OL). The full OL always appears on field.
- 2025 injury cascade: Empty — injury data not yet available for 2025 season.
