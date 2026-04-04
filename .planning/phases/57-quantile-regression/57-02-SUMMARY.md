# Phase 57-02: Graph Feature Impact on Fantasy MAE

## Objective

Compute 18 new graph-derived features (QB-WR chemistry, game script, red zone) for all training seasons (2016-2025), retrain hybrid residual models, and measure MAE impact.

## New Features (18 total)

### QB-WR Chemistry (5 features)
- `qb_wr_chemistry_epa_roll3` — rolling 3-game pair EPA
- `qb_wr_pair_comp_rate_roll3` — rolling 3-game pair completion rate
- `qb_wr_pair_target_share` — WR's share of QB's targets (rolling 3)
- `qb_wr_pair_games_together` — cumulative games as a pair
- `qb_wr_pair_td_rate` — rolling 6-game TD rate for the pair

### Game Script (6 features)
- `usage_when_trailing_roll3` — target+carry share when trailing
- `usage_when_leading_roll3` — target+carry share when leading
- `garbage_time_share_roll3` — yard share in trailing_big zone
- `clock_killer_share_roll3` — carry share when leading_big
- `script_volatility` — std dev of usage across 5 script zones
- `predicted_script_boost` — multiplier from Vegas spread

### Red Zone (7 features)
- `rz_target_share_roll3` — rolling 3-game RZ target share
- `rz_carry_share_roll3` — rolling 3-game RZ carry share
- `rz_td_rate_roll3` — rolling 3-game RZ TD rate
- `rz_usage_vs_general` — RZ target share / overall target share
- `team_rz_trips_roll3` — team's rolling 3-game RZ trips
- `rz_td_regression` — player RZ TD rate vs position expected
- `opp_rz_td_rate_allowed_roll3` — opponent defense RZ TD rate

## What Was Done

1. **Fixed compute_graph_features.py** — added missing game_script computation (step 8), import, file_map entry, and combined file inclusion.
2. **Computed features for 10 seasons** (2016-2025) — 85 parquet files, 5.7 MB total, 2810 seconds.
3. **Retrained residual models** — WR and TE Ridge models now trained on 483 features (up from ~42 in previous iterations).
4. **Ran backtest** in two modes:
   - `--ml` (42 Silver features at inference): MAE 4.78
   - `--ml --full-features` (483 features at inference): MAE 4.98

## Results

### Mode 1: `--ml` (no full features, 42 features at inference)

| Position | Before | After | Change |
|----------|--------|-------|--------|
| QB       | 6.58   | 6.58  | 0.00   |
| RB       | 5.00   | 5.00  | 0.00   |
| WR       | 4.63   | 4.65  | +0.02  |
| TE       | 3.58   | 3.58  | 0.00   |
| Overall  | 4.77   | 4.78  | +0.01  |

### Mode 2: `--ml --full-features` (483 features at inference)

| Position | Before | After | Change |
|----------|--------|-------|--------|
| QB       | 6.58   | 6.58  | 0.00   |
| RB       | 5.00   | 5.00  | 0.00   |
| WR       | 4.63   | 4.98  | +0.35  |
| TE       | 3.58   | 3.93  | +0.35  |
| Overall  | 4.77   | 4.98  | +0.21  |

## Diagnosis

**The 18 new graph features do not improve point-estimate MAE.**

### Why Mode 1 shows no change
The `--ml` backtest path builds Silver features from `build_silver_features()` which only computes basic usage metrics and rolling averages (42 features). Graph features are not included in this path. The residual model was trained on 483 features but at inference 441 are imputed to training medians — making all new feature coefficients contribute a constant offset. The model's effective behavior is unchanged.

### Why Mode 2 is worse
With `--full-features`, all 483 features reach the model at inference. However, Ridge regression with 483 features overfits: the training regularization (alpha=8.286 for WR, alpha=0.494 for TE) is insufficient to prevent the model from fitting noise in the 441 features beyond the original 42. The log confirms "WR: 42/483 features available from Silver; 441 imputed" in Mode 1.

### Architectural gap
There is a fundamental mismatch between the residual training path (which uses `assemble_multiyear_player_features()` with all graph features) and the inference path (which uses `build_silver_features()` with only basic rolling stats). For the new features to help, either:
1. The backtest `build_silver_features()` needs to join cached graph parquets at inference time, or
2. Feature selection must restrict the residual model to features available at inference

## Recommendation

1. **Do NOT commit the retrained models** — they are worse or neutral. Revert to the previous residual models.
2. **The features themselves are sound** — all use shift(1) temporal safety, have good coverage (75-94% per position), and pass temporal integrity checks.
3. **Next step: wire graph features into inference path** — modify `build_silver_features()` in `backtest_projections.py` to join cached graph feature parquets, so the 18 new features are available at inference without requiring full 483-feature assembly.
4. **These features may still help quantile regression** — floor/ceiling models could benefit from game script volatility, red zone specialization, and chemistry signals even if point estimates don't improve.

## Tests

1053 passed, 1 skipped (all pre-existing tests pass).
