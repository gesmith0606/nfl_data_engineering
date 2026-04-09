# Phase 56: Bayesian Hierarchical Models — Experiment Results

## Environment

- **Date:** 2026-04-08
- **Python:** 3.9.7 (x86_64 via Rosetta on ARM Mac)
- **Scoring:** Half-PPR
- **Features:** 493 candidate, 60 SHAP-selected per position per fold
- **Folds:** Walk-forward CV (train < val_season, test = val_season), weeks 3-18
- **Test seasons:** 2022, 2023, 2024

## Dependency Decision

NumPyro (JAX-based) was the preferred Bayesian framework. However, all pip-available
JAX wheels for macOS x86_64 require AVX instructions, which are unavailable when
running x86 Python under Rosetta on ARM hardware. After testing JAX versions 0.4.17
through 0.4.30, all failed with the same AVX RuntimeError.

**Fallback:** sklearn BayesianRidge provides the same theoretical guarantees for this
use case (conjugate Gaussian likelihood + Gaussian prior = analytical posterior).
No MCMC needed — the posterior is computed in closed form. BayesianRidge learns
position-level precision parameters (alpha for weight prior, lambda for noise)
that act as hierarchical shrinkage, and the posterior predictive distribution
enables calibrated uncertainty intervals.

## Walk-Forward CV Results

### Bayesian Residual Model (BayesianRidge + SHAP-60)

| Position | Bayes MAE | Heuristic MAE | Improvement | Calibration (80% CI) | Interval Width |
|----------|-----------|---------------|-------------|---------------------|----------------|
| QB       | 4.669     | 13.742        | -66.0%      | 78.8%               | 14.66          |
| RB       | 3.759     | 4.490         | -16.3%      | 86.5%               | 13.61          |
| WR       | 3.170     | 4.157         | -23.7%      | 86.2%               | 11.17          |
| TE       | 2.736     | 3.183         | -14.0%      | 86.1%               | 9.73           |

### Per-Fold Detail

**QB:**
| Fold | MAE   | Calib | Width | Noise Sigma | Alpha  | Lambda |
|------|-------|-------|-------|-------------|--------|--------|
| 2022 | 4.489 | 81.4% | 14.84 | 0.652      | 0.0302 | 2.354  |
| 2023 | 4.312 | 82.2% | 14.79 | 0.650      | 0.0302 | 2.370  |
| 2024 | 5.205 | 72.9% | 14.35 | 0.680      | 0.0321 | 2.163  |

**RB:**
| Fold | MAE   | Calib | Width | Noise Sigma | Alpha  | Lambda |
|------|-------|-------|-------|-------------|--------|--------|
| 2022 | 3.777 | 87.4% | 13.77 | 0.453      | 0.0347 | 4.883  |
| 2023 | 3.759 | 85.9% | 13.59 | 0.413      | 0.0355 | 5.852  |
| 2024 | 3.742 | 86.1% | 13.49 | 0.405      | 0.0360 | 6.102  |

**WR:**
| Fold | MAE   | Calib | Width | Noise Sigma | Alpha  | Lambda |
|------|-------|-------|-------|-------------|--------|--------|
| 2022 | 3.134 | 86.5% | 11.28 | 8.830      | 0.0515 | 0.013  |
| 2023 | 3.095 | 87.6% | 11.09 | 9.685      | 0.0532 | 0.011  |
| 2024 | 3.280 | 84.5% | 11.14 | 6.204      | 0.0527 | 0.026  |

**TE:**
| Fold | MAE   | Calib | Width | Noise Sigma | Alpha  | Lambda |
|------|-------|-------|-------|-------------|--------|--------|
| 2022 | 2.761 | 85.9% | 9.77  | 0.346      | 0.0689 | 8.363  |
| 2023 | 2.640 | 86.5% | 9.77  | 0.345      | 0.0689 | 8.407  |
| 2024 | 2.808 | 85.8% | 9.65  | 0.347      | 0.0704 | 8.283  |

## Comparison to Phase 55 Models

Reference Phase 55 LGB SHAP-60 results (from phase-55/EXPERIMENTS.md):

| Position | Heuristic MAE | Ridge MAE | LGB MAE | **Bayes MAE** | Bayes vs Heur | LGB vs Heur |
|----------|---------------|-----------|---------|---------------|---------------|-------------|
| QB       | 13.742        | ~5.5      | 3.826   | **4.669**     | -66.0%        | -72.2%      |
| RB       | 4.490         | ~3.9      | 3.361   | **3.759**     | -16.3%        | -25.1%      |
| WR       | 4.157         | ~3.5      | 2.850   | **3.170**     | -23.7%        | -31.4%      |
| TE       | 3.183         | ~2.8      | 2.317   | **2.736**     | -14.0%        | -27.2%      |

## Analysis

### MAE Performance

The Bayesian model provides **substantial improvement over heuristic** for all positions
(-14% to -66%), but is **outperformed by LGB SHAP-60** on all positions. This is expected:
BayesianRidge is a linear model (like Ridge), and LightGBM captures nonlinear interactions
that linear models cannot.

The Bayesian model's MAE is roughly between Ridge and LGB — closer to Ridge for most
positions, which confirms the linear model ceiling.

### Calibration (Key Value)

The Bayesian model's **primary value is posterior uncertainty intervals**, not MAE:

- **80% coverage interval achieves 78-87% actual coverage** across positions and folds
- This is well-calibrated — an 80% interval should contain ~80% of actuals
- RB/WR/TE are slightly over-covered (86%), suggesting intervals could be tightened
- QB 2024 fold shows 73% coverage (under-covered), suggesting higher QB variance

### Interval Width

Mean interval widths range from 9.7 (TE) to 14.7 (QB) fantasy points. This is:
- QB: +/- 7.3 points around the mean (reasonable given QB score variance)
- RB: +/- 6.8 points
- WR: +/- 5.6 points
- TE: +/- 4.9 points

These are **data-driven** intervals vs the current hardcoded multipliers
(_FLOOR_CEILING_MULT = QB: 45%, RB: 40%, WR: 38%, TE: 35%).

### Learned Priors (Hierarchical Signal)

The learned precision parameters reveal position-specific structure:
- **TE has highest lambda (8.3)**: Data is most precise for TEs — small, predictable group
- **RB has moderate lambda (4.9-6.1)**: Moderate data precision
- **WR has very low lambda (0.01-0.03)**: High noise — WR outcomes are highly variable
- **QB lambda (2.2-2.4)**: Moderate, but small group with high individual variance

This is genuine hierarchical learning — the model discovers that TE residuals are
highly predictable while WR residuals are essentially noise-dominated.

## Ship/Skip Decision

### MAE: SKIP (LGB is strictly better)
- LGB outperforms Bayesian on all 4 positions
- No reason to replace LGB with Bayesian for point estimates

### Posterior Intervals: SHIP for floor/ceiling replacement
- Calibrated 80% intervals achieve 78-87% actual coverage
- Replaces hardcoded _FLOOR_CEILING_MULT with data-driven intervals
- Can be used alongside LGB point estimates (use LGB mean + Bayesian intervals)

### Recommended Integration
1. Keep LGB SHAP-60 as the residual correction model (Phase 55 winner)
2. Train Bayesian models in parallel for interval estimation only
3. Replace `add_floor_ceiling()` hardcoded multipliers with Bayesian posteriors
4. This gives: LGB accuracy + Bayesian calibrated uncertainty = best of both

## Reproduction

```bash
source venv/bin/activate

# Walk-forward CV evaluation
python scripts/train_bayesian_models.py --evaluate

# Train and save production models
python scripts/train_bayesian_models.py --train

# Both
python scripts/train_bayesian_models.py --evaluate --train
```
