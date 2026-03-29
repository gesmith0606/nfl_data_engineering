# Phase 37 Baseline -- Sealed 2025 Holdout

## Prior Baseline (2024 Holdout -- v2.0)
- ATS Accuracy: 53.0%
- Profit: +$3.09
- ROI: +1.2%

## New Baseline (2025 Holdout -- v2.2)
- Training: 2016-2024 (9 seasons)
- Holdout: 2025 (sealed)
- Model: P30 Ensemble (XGB+LGB+CB+Ridge)
- Hyperparameters: Unchanged from v2.0 (no --tune)
- Features: 321 (SELECTED_FEATURES=None; all assembled features used)

### Results
- ATS Accuracy: 51.7%
- Record: 140-131-1 (W-L-P)
- Total Profit: -$3.73 units (flat $100 bets)
- ROI: -1.38%
- Mean CLV: +0.14 points
- Median CLV: +0.06 points
- Pct Beating Close: 50.4%

### CLV by Confidence Tier
| Tier   | Games | Mean CLV | Median CLV | Pct Beat Close |
|--------|-------|----------|------------|----------------|
| low    | 129   | +0.07    | +0.09      | 51.2%          |
| medium | 94    | -0.18    | -1.58      | 44.7%          |
| high   | 49    | +0.92    | +3.32      | 59.2%          |

### Cross-Validation Performance
- Spread CV MAE: XGB=10.1050, LGB=10.0752, CB=10.0770
- Total CV MAE: XGB=10.5995, LGB=10.6021, CB=10.6381
- Ridge alpha: 100.0 (both targets)
- Ridge spread coefficients: XGB=0.0816, LGB=0.5119, CB=0.5859
- Ridge total coefficients: XGB=0.4884, LGB=0.2114, CB=0.4488

### Notes
- 2025 injuries data absent (Phase 35 finding) -- affects injury-related features
- 2024 now included in training (was previously sealed) -- 1 extra training season
- Market features: NaN for 2022-2025 games (FinnedAI covers 2016-2021 only)
- SELECTED_FEATURES=None means all 321 assembled features used (no SHAP filtering)
- 51.7% ATS is below break-even (52.38%) but above 50% -- model has directional signal

## Reference
This baseline is the comparison target for Phase 38 market feature ablation.
The ship-or-skip gate requires strict > on holdout ATS accuracy.
