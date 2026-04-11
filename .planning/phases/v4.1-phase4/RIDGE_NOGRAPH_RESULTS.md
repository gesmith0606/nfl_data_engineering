# Ridge NO Graph Features — Backtest Results

**Date**: 2026-04-11
**Hypothesis**: The 9 graph features added in Ridge 60f+graph training are adding noise (sparse 2022-2024 coverage), and removing them will recover the v3.2 4.80 MAE baseline.

## Experiment

Trained Ridge with 60 SHAP-selected features but WITHOUT `--use-graph-features` flag.

Note: `qb_wr_chemistry_epa_roll3` still appeared in both WR and TE models (1 feature each) because it is loaded unconditionally from cached Silver parquet files in `player_feature_engineering.py`, not from the `--use-graph-features` graph loading path. This feature is derived from actual PBP data and has better coverage than inference-based graph features.

**Effective graph feature counts:**
- Ridge 60f + graph (shipped): 7 graph features per position
- Ridge 60f NO graph (new): 1 graph feature per position (qb_wr_chemistry_epa_roll3 only)

## Results — 2022-2024 Backtest (11,183 player-weeks, 48 weeks, Half-PPR)

| Config | Overall MAE | WR MAE | TE MAE | Corr |
|--------|------------|--------|--------|------|
| v3.2 Ridge 42f (baseline) | 4.80 | 4.63 | 3.58 | — |
| Ridge 60f + graph (shipped) | 5.05 | 4.89 | 3.83 | — |
| **Ridge 60f NO graph (new)** | **5.13** | **4.99** | **4.00** | 0.495 |

## Decision: DO NOT SHIP — Restore Backup

The no-graph Ridge is **worse** than the Ridge+graph shipped version by 0.08 MAE overall.

- WR: 4.99 vs 4.89 (no-graph is worse by 0.10)
- TE: 4.00 vs 3.83 (no-graph is worse by 0.17)

**Graph features are not the noise source.** Removing them makes things worse, indicating the sparse 2022-2024 graph features still provide net-positive signal through imputed means/zeros during training.

Production Ridge+graph models were restored from backup: `models/residual/ridge_graph_backup_20260411_0009/`.

## Remaining 0.25 MAE Gap to v3.2 Baseline

All three Ridge 60f configurations are 0.25-0.33 MAE worse than the v3.2 Ridge 42f baseline. Since graph features aren't the cause, the regression likely stems from:

1. **Feature distribution shift from the graph inference fix (deab6a6)** — The commit that fixed graph inference may have changed how graph features behave at inference time, even when the same features are in the model. The WS2 branch (code-level revert test) is investigating this angle directly.
2. **60-feature SHAP selection vs 42f** — The expanded feature set (60 vs 42) may be introducing correlated noise that hurts Ridge generalization.
3. **Training data expansion (2016-2025 vs narrower window)** — Earlier seasons may introduce distribution mismatch given rule/scheme changes.

## Next Steps

1. Wait for WS2 results (graph inference fix revert) — if reverting `deab6a6` recovers baseline, that's the root cause.
2. If WS2 is inconclusive: try Ridge with 42 SHAP features (matching v3.2 feature count) to isolate whether 60-feature selection is the issue.
3. If both are inconclusive: bisect training data window (2020-2025 vs 2016-2025) to test for season-count regression.
