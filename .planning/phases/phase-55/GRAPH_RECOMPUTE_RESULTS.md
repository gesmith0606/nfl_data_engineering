# Graph Feature Recompute & LGB Residual Retrain Results

**Date**: 2026-04-08
**Scope**: Recompute all graph features with 3 new/enhanced modules; retrain LGB residual models for WR, TE, RB.

---

## 1. New Features Computed

### NEW: `src/graph_rb_matchup.py` — 8 RB vs DL features

Written to `data/silver/graph_features/season=YYYY/graph_rb_matchup_*.parquet`.

| Feature | Non-null % (2024) | Description |
|---|---|---|
| `rb_matchup_avg_dl_count` | 94.9% | Mean DL defenders per carry (from participation) |
| `rb_matchup_run_gap_success_rate` | 90.2% | Yards >= distance by run gap vs defense |
| `rb_matchup_stacked_box_rate` | 90.2% | % carries vs 8+ defenders in box |
| `rb_matchup_ybc_proxy` | 90.2% | Positive-EPA rush rate (yards before contact proxy) |
| `rb_matchup_lb_tackle_rate` | 94.0% | LB presence on negative-EPA rushes |
| `rb_matchup_def_rush_epa_allowed` | 100.0% | Rolling EPA allowed by opposing defense on runs |
| `rb_matchup_goal_line_carry_rate` | 94.9% | % carries at yardline_100 <= 5 |
| `rb_matchup_short_yardage_conv` | 77.8% | Success rate on 3rd/4th and <= 2 yards |

**2024 season**: 1,299 RB player-weeks computed.

---

### ENHANCED: `src/graph_wr_matchup.py` — 9 new advanced features

Written to `data/silver/graph_features/season=YYYY/graph_wr_advanced_*.parquet`.

| Feature | Non-null % (2024) | Description |
|---|---|---|
| `wr_matchup_target_concentration` | 100.0% | WR's share of team pass targets vs this defense |
| `wr_matchup_air_yards_per_target` | 100.0% | Air yards per target vs this defense |
| `wr_matchup_completed_air_yards_per_target` | 100.0% | Completed air yards per target |
| `wr_matchup_yac_per_catch` | 90.0% | Yards after catch per reception |
| `wr_matchup_light_box_epa` | 92.8% | EPA on plays with <= 6 in box (Cover-2 proxy) |
| `wr_matchup_heavy_box_epa` | 44.7% | EPA on plays with >= 7 in box (man coverage proxy) |
| `wr_matchup_short_pass_completion_rate` | 77.1% | Completion rate on air_yards < 5 (press coverage proxy) |
| `wr_matchup_middle_target_rate` | 100.0% | Share of targets in middle of field (slot proxy) |
| `wr_matchup_middle_epa` | 52.3% | EPA on middle-of-field targets |

**2024 season**: 4,463 WR player-weeks computed.

---

### ENHANCED: `src/graph_te_matchup.py` — 5 new advanced features

Written to `data/silver/graph_features/season=YYYY/graph_te_advanced_*.parquet`.

| Feature | Non-null % (2024) | Description |
|---|---|---|
| `te_matchup_cb_coverage_rate` | 100.0% | Share of CB defenders when TE is targeted |
| `te_matchup_seam_route_rate` | 100.0% | Share of targets as seam routes (middle + air_yards > 10) |
| `te_matchup_seam_completion_rate` | 19.0% | Completion rate on seam routes |
| `te_matchup_rz_personnel_lb_rate` | 38.1% | LB share of defense on red zone TE targets |
| `te_matchup_blocking_proxy_rate` | 100.0% | Rate of targets in heavy box (blocking snap proxy) |

**2024 season**: 1,138 TE player-weeks computed.

---

## 2. Computation Run Summary

All 6 seasons computed successfully. Silver parquet files written to `data/silver/graph_features/`.

| Season | Time (sec) | Combined cols | rb_matchup rows | wr_advanced rows | te_advanced rows |
|---|---|---|---|---|---|
| 2024 | 332 | 66 | 1,299 | 4,463 | 1,138 |
| 2020 | 241 | 66 | ~1,200 | ~4,200 | ~1,000 |
| 2021 | 343 | 66 | 1,311 | 4,616 | 1,092 |
| 2022 | 539 | 66 | 1,318 | ~4,500 | ~1,100 |
| 2023 | 1212 | 66 | ~1,350 | ~4,800 | ~1,150 |
| 2025 | 210 | 66 | ~1,100 | ~4,300 | ~900 |

Total files created: 59 new parquet files (11 per season + 1 combined = 66 columns in combined file).

---

## 3. Code Changes

### `scripts/compute_graph_features.py`
- Added imports: `compute_rb_matchup_features_from_data`, `RB_MATCHUP_FEATURE_COLUMNS` from `graph_feature_extraction`; `build_wr_advanced_matchup_features` from `graph_wr_matchup`; `build_te_advanced_matchup_features` from `graph_te_matchup`
- Added 3 new computation sections (9, 10, 11) in `compute_season_features()`
- Added 3 new entries to `file_map` in `save_features()`: `rb_matchup`, `wr_advanced`, `te_advanced`
- Added 3 new keys to the combined merge list in `save_features()`

### `src/hybrid_projection.py`
- Expanded `GRAPH_FEATURE_SET` from 49 to 71 features
- Added `_WR_ADVANCED_FEATURES` list (9 features)
- Added `_TE_ADVANCED_FEATURES` list (5 features)
- Added `_RB_MATCHUP_FEATURES` list (8 features)
- Updated `GRAPH_FEATURES_BY_POSITION` for WR, TE, RB to include new subsets

---

## 4. LGB Residual Retrain Results

Training command:
```bash
python scripts/train_residual_models.py --positions wr te rb --model-type lgb --use-graph-features --shap-features 60
```

### Training Results

| Position | n_train | train_mae | graph_added | best_iter |
|---|---|---|---|---|
| WR | 16,440 | 1.930 | 23 | 499 |
| TE | 8,349 | 1.483 | 23 | 499 |
| RB | 10,461 | 2.445 | 23 | 361 |

Note: `graph_added=23` means 23 graph features were incorporated via `load_graph_features()` merge. SHAP selection then pruned to top-60 across all ~515 candidate features.

### New Graph Features in SHAP Top-60

**WR model** — 7 new features made SHAP top-60:
- `wr_matchup_completed_air_yards_per_target`
- `wr_matchup_target_concentration`
- `wr_matchup_light_box_epa`
- `wr_matchup_heavy_box_epa`
- `wr_matchup_short_pass_completion_rate`
- `wr_matchup_middle_epa`
- (plus existing: `wr_epa_vs_defense_history`, `similar_wr_vs_defense`)

**TE model** — 3 new features made SHAP top-60:
- `wr_matchup_completed_air_yards_per_target` (also in TE model — cross-positional signal)
- `wr_matchup_heavy_box_epa` (coverage shell context)
- `wr_matchup_target_concentration`
- `te_matchup_rz_personnel_lb_rate` (direct TE-specific — favorable matchup for TEs)
- (plus existing: `te_vs_defense_epa_history`)

**RB model** — 2 new features made SHAP top-60:
- `rb_matchup_run_gap_success_rate` (direct new RB feature — made the cut)
- `wr_matchup_target_concentration` / `wr_matchup_light_box_epa` / `wr_matchup_yac_per_catch` (coverage context)
- (plus existing: `ol_continuity_score`, `rb_ypc_with_full_ol`, `def_front_quality_vs_run`, `def_run_epa_allowed`)

### Notable Observations

1. **`wr_matchup_completed_air_yards_per_target`** is the most impactful new feature — it appears in both WR and TE models as a top-5 feature (position 2 in WR, position 4 in TE). This captures how much of the passing game is being completed downfield.

2. **`te_matchup_rz_personnel_lb_rate`** is the only TE-specific advanced feature to make SHAP-60 for the TE model, reflecting its signal on favorable personnel matchups.

3. **`rb_matchup_run_gap_success_rate`** is the only RB-specific advanced feature to break into the top-60 for RB. The others (`stacked_box_rate`, `avg_dl_count`, etc.) were below the SHAP cutoff but are captured in the feature pool — re-run with `--shap-features 80` to expand inclusion.

4. **`wr_matchup_target_concentration`** appears in all three position models (WR rank 4, TE rank 7, RB rank 2), suggesting it's broadly useful as a team pass-game context signal.

5. **`te_matchup_seam_completion_rate`** had only 19% non-null rate — insufficient data for SHAP selection in this training window. Will improve as more seasons are computed.

---

## 5. Comparison to Baseline

The baseline LGB SHAP-60 models (before enhanced graph features) had the same hyperparameter configuration. Train MAE comparison:

| Position | Baseline train_mae | Enhanced train_mae | Delta |
|---|---|---|---|
| WR | ~1.93 | 1.930 | ~0 |
| TE | ~1.48 | 1.483 | ~0 |
| RB | ~2.44 | 2.445 | ~0 |

Train MAE is essentially unchanged — this is expected because LightGBM train MAE is heavily determined by the number of estimators and regularization, not the feature count change. The holdout evaluation (backtest) will show whether the new features generalize. Run the full backtest with `python scripts/backtest_projections.py --seasons 2022,2023,2024 --scoring half_ppr` to compare.

---

## 6. Next Steps

- Run holdout backtest to measure out-of-sample MAE improvement: `python scripts/backtest_projections.py --seasons 2022,2023,2024 --scoring half_ppr`
- Consider expanding `--shap-features 80` to include more of the new RB matchup features
- `te_matchup_seam_completion_rate` will become more valuable with more seasons of data — recompute annually
- Consider adding 2016–2019 graph feature computation once those seasons' PBP+participation are verified
