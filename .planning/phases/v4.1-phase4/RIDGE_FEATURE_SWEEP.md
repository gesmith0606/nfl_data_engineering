# Ridge WR/TE Feature Count Sweep
**Date**: 2026-04-11
**Hypothesis**: 60 SHAP features is too many for Ridge WR/TE residual models; smaller counts may reduce overfitting.

## Setup
- Evaluation window: 2024-only (weeks 1–16, 3,754 player-weeks)
- Scoring: half_ppr
- Flags: `--ml --full-features` (full 466-col feature vector, graph features enabled)
- Backup created: `models/residual/ridge_60f_backup_20260411_1007/`

## Results — 2024-Only Backtest

| Features | Overall MAE | WR MAE | TE MAE | WR Corr | TE Corr |
|----------|-------------|--------|--------|---------|---------|
| 30       | 5.33        | 5.32   | 4.21   | 0.390   | 0.340   |
| 40       | 5.33        | 5.33   | 4.18   | 0.388   | 0.341   |
| 42       | 5.33        | 5.32   | 4.19   | 0.388   | 0.338   |
| 50       | 5.33        | 5.32   | 4.19   | 0.386   | 0.341   |
| **60 (prod)** | **5.33** | **5.33** | **4.15** | 0.386 | 0.355 |

## Finding
**Hypothesis disproven.** Overall MAE is flat at 5.33 across all feature counts (30–60). The production 60f model is marginally best on TE (4.15 vs 4.18–4.21) and has the highest TE correlation (0.355). No smaller feature count improves on the current configuration.

## Ship Decision
**No change.** 60f backup restored to `models/residual/`. No commit made.

## MAE Recovery Summary (Session Start → Now)
| Checkpoint | Overall MAE (2022–2024) |
|-----------|------------------------|
| Session start | 5.40 |
| WS1: Ridge wins over LGB (shipped) | 5.05 |
| WS5: Graph features confirmed (no change) | 5.05 |
| WS2: Code revert (no impact) | 5.05 |
| **Feature count sweep (no improvement)** | **5.05** |

**Remaining gap to v3.2 baseline (4.80)**: 0.25 MAE

## Next Investigation Suggestions
1. **Alpha tuning for Ridge**: The WR alpha (4.715) and TE alpha (0.494) differ substantially. Try forcing a wider search range in `RidgeCV(alphas=...)` to explore lower-regularization regimes for WR.
2. **Feature engineering quality**: The flat MAE across feature counts suggests the marginal features aren't noise — they just aren't helpful. Inspect which 30 features are consistently selected and whether engineering new interaction features (e.g., `target_share × snap_pct`, `air_yards × matchup_rank`) would help.
3. **Heuristic weight tuning**: WR/TE use hybrid (heuristic + residual). The heuristic component may be the bottleneck. Try re-tuning `RECENCY_WEIGHTS` specifically for WR/TE separately from QB/RB.
4. **Separate WR tier models**: WR1 (starter ≥12 ppg) vs WR2/WR3 behavior differs. Tier-specific models could reduce cross-tier variance.
5. **TE position split**: TE has lower alpha (more regularization = fewer effective features). Investigate if blocking TEs are pulling MAE up vs receiving TEs.
6. **Training window expansion**: Current training uses 2016–2024. Verify all seasons actually have graph features populated — sparse graph coverage in early years may add noise to the residual target.
