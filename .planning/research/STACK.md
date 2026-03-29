# Stack Research

**Domain:** ML-based player fantasy point prediction (NFL)
**Researched:** 2026-03-29
**Confidence:** HIGH

## Executive Assessment

The existing stack (XGBoost, LightGBM, CatBoost, scikit-learn, SHAP, Optuna) already covers 90% of what's needed for player-level ML predictions. The same ensemble stacking pattern that works for game-level predictions transfers directly to player-level targets. Only two new libraries are genuinely needed: **statsmodels** for mixed-effects position models during research/EDA, and **MAPIE** for prediction intervals (floor/ceiling estimates). Everything else is already installed or unnecessary complexity.

## What You Already Have (DO NOT ADD)

These are already installed and battle-tested in this codebase. Listing them to prevent redundant additions.

| Technology | Version | Already Used For |
|------------|---------|------------------|
| XGBoost | >=2.1.4 | Game prediction ensemble base model |
| LightGBM | 4.6.0 | Game prediction ensemble base model |
| CatBoost | 1.2.10 | Game prediction ensemble base model; handles categoricals natively |
| scikit-learn | >=1.5 | RidgeCV meta-learner, metrics, preprocessing |
| SHAP | 0.49.1 | Feature selection, importance analysis |
| Optuna | >=4.0 | Hyperparameter tuning |
| pandas | 1.5.3 | All data processing |
| numpy | 1.26.4 | Numerical operations |
| scipy | 1.13.1 | Statistical tests |

## Recommended Stack Additions

### New Libraries (Install These)

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| statsmodels | 0.14.6 | MixedLM for player random effects, position-level variance decomposition | Players are repeated measures within teams/positions; mixed effects quantify player-specific vs team-specific variance. Already supports Python 3.9. Use during research to understand variance structure, not necessarily in production pipeline. |
| MAPIE | 1.3.0 | Conformal prediction intervals for floor/ceiling estimates | Wraps any scikit-learn-compatible regressor (including XGB/LGB/CB). Produces calibrated prediction intervals backed by theory. Replaces the current heuristic `add_floor_ceiling()` with statistically grounded uncertainty. Only deps are numpy>=1.23 and scikit-learn>=1.4, both satisfied. |

### Existing Libraries to Use Differently (No Install Needed)

| Library | New Usage | Why |
|---------|-----------|-----|
| CatBoost | Native categorical encoding for team_id, opponent_id, player position | CatBoost handles categoricals natively without one-hot encoding. Use `cat_features` parameter instead of encoding team/opponent as dummies. This captures team effects without high-cardinality blowup. Already installed. |
| scikit-learn QuantileRegressor | Quantile regression for boom/bust probability | `sklearn.ensemble.GradientBoostingRegressor(loss='quantile', alpha=0.1/0.9)` gives native quantile predictions. No new library needed. |
| scikit-learn TargetEncoder | Encode player_id, team_id as target-encoded features | `sklearn.preprocessing.TargetEncoder` (available since sklearn 1.3) handles high-cardinality categoricals by encoding with smoothed target means. Already installed via scikit-learn>=1.5. |

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| PyTorch / TensorFlow | Neural nets do not outperform gradient boosting on tabular NFL data at this scale (~50K player-weeks). PROJECT.md explicitly scopes out deep learning. | XGB+LGB+CB ensemble (already proven) |
| category_encoders | Redundant; scikit-learn TargetEncoder + CatBoost native categoricals cover all encoding needs | sklearn.preprocessing.TargetEncoder + CatBoost cat_features |
| prophet / neuralprophet | Time-series forecasting libs designed for univariate series with seasonality. NFL player performance is multivariate tabular, not a classic time-series. Weekly features with rolling windows already capture temporal patterns. | Lag features + rolling windows in pandas (already built in player_analytics.py) |
| feature-engine | Adds another dependency for transforms that pandas + scikit-learn already handle | pandas rolling, sklearn pipelines |
| formulaic / patsy | Only needed if building R-style formula interfaces. statsmodels already includes formula support. | statsmodels formula API |
| bambi / PyMC | Full Bayesian modeling is overkill. The ensemble approach with conformal intervals gives uncertainty without MCMC sampling overhead. | MAPIE conformal intervals |
| polars | Migration from pandas mid-project adds risk for no measurable benefit at this data scale (~50K rows) | pandas 1.5.3 (already works) |
| nflfastpy / nflreadr-py | Redundant with nfl-data-py which already provides all needed data | nfl-data-py 0.3.3 (already installed) |

## Architecture Decisions for Player-Level ML

### 1. Reuse the Ensemble Pattern

The existing `ensemble_training.py` pattern (XGB+LGB+CB base models + Ridge meta-learner) should be replicated per-position. Key adaptations:

- **Per-position models**: Train separate ensembles for QB, RB, WR, TE. Positions have fundamentally different stat distributions and feature importance.
- **Walk-forward CV**: Same temporal split logic from game predictions. Train on seasons 1..N, validate on N+1. Holdout 2025 sealed.
- **Target variable**: Half-PPR fantasy points (primary), with PPR/Standard as scoring transformations post-prediction.

### 2. Feature Engineering Approach (No New Libraries)

Player features should decompose into **opportunity** and **efficiency** using existing pandas operations:

```
Fantasy Points = Opportunity x Efficiency x Context
  - Opportunity: snap_pct, target_share, carry_share, route_participation
  - Efficiency: yards_per_target, yards_per_carry, TD_rate, catch_rate
  - Context: opponent_rank, vegas_implied_total, game_script_proxy
```

All these features already exist in Silver layer (`players/usage`, `players/advanced`, `defense/positional`, `teams/pbp_metrics`). The feature assembly module (`feature_engineering.py`) pattern should be replicated for player-level vectors.

### 3. Player Identity Encoding

Use **target encoding** (sklearn TargetEncoder) for player_id rather than player embeddings. Rationale:
- Player embeddings require neural networks (out of scope)
- One-hot encoding of ~2000 players causes dimensionality explosion
- Target encoding captures player skill level as a smoothed scalar
- CatBoost can also handle player_id natively via `cat_features`
- Combine with positional encoding: position is a categorical, not a feature hierarchy

### 4. Temporal Features (No New Libraries)

Player performance has strong temporal patterns. Capture with pandas rolling operations (already built):
- **Recency windows**: roll3, roll6, season-to-date (already in projection_engine.py)
- **Lag features**: Previous week stats (shift(1)), 2-week lag
- **Expanding career means**: Career average as regression target for rookies/role changes
- **Exponential weighted means**: `pandas.DataFrame.ewm(halflife=3)` for momentum

### 5. Prediction Intervals with MAPIE

Replace the current heuristic floor/ceiling (`PROJECTION_CEILING_SHRINKAGE` dict) with conformal prediction:

```python
from mapie.regression import MapieRegressor
mapie = MapieRegressor(estimator=xgb_model, method="plus", cv=5)
mapie.fit(X_train, y_train)
y_pred, y_intervals = mapie.predict(X_test, alpha=0.1)  # 90% interval
# y_intervals[:, 0, 0] = floor, y_intervals[:, 1, 0] = ceiling
```

This gives per-player, per-week calibrated uncertainty -- much better than position-level variance percentages.

## Installation

```bash
# New dependencies only
pip install statsmodels==0.14.6
pip install mapie==1.3.0

# That's it. Everything else is already installed.
```

## Version Compatibility

| New Package | Compatible With | Notes |
|-------------|-----------------|-------|
| statsmodels 0.14.6 | Python 3.9, numpy 1.26.4, scipy 1.13.1 | Verified: supports Python 3.9-3.14. numpy/scipy versions within range. |
| MAPIE 1.3.0 | Python 3.9, scikit-learn>=1.5, numpy 1.26.4 | Verified: requires Python>=3.9, numpy>=1.23, scikit-learn>=1.4. All satisfied. |
| statsmodels 0.14.6 | pandas 1.5.3 | Verified: statsmodels supports pandas 1.x and 2.x |
| MAPIE 1.3.0 | XGBoost, LightGBM, CatBoost | MAPIE wraps any sklearn-compatible estimator. All three boosting libs implement the sklearn API. |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Per-position XGB+LGB+CB ensemble | Single all-position model with position as feature | If data volume per position is too small (<5K samples). QB has the fewest player-weeks. Monitor per-position sample sizes. |
| Target encoding for player_id | CatBoost native categoricals | When using CatBoost as sole model (not in ensemble). In the stacking ensemble, target encoding is needed for XGB/LGB which lack native categorical support. |
| MAPIE conformal intervals | Quantile regression (sklearn GBR) | If you need the full conditional distribution, not just intervals. Quantile regression at alpha=0.1, 0.5, 0.9 gives floor/median/ceiling without conformal wrapper. Downside: no formal coverage guarantee. |
| statsmodels MixedLM | bambi (PyMC-backed) | If you need full posterior distributions and Bayesian credible intervals. Overkill for variance decomposition during research phase. |
| Predict fantasy points directly | Predict stats then score | If you need stat-level projections for lineup optimization (e.g., "how many receptions?"). Predicting points directly is simpler and avoids error propagation across stat predictions. Start with direct points prediction; add stat decomposition later if needed. |

## Stack Patterns by Use Case

**For position-specific model training:**
- Use CatBoost with `cat_features=['team', 'opponent']` for native categorical handling
- Use XGB+LGB as additional base models with target-encoded categoricals
- Stack with Ridge meta-learner (same pattern as game predictions)

**For understanding player variance structure (research phase):**
- Use statsmodels MixedLM: `fantasy_points ~ fixed_features + (1|player_id) + (1|team)`
- This tells you how much variance is player-specific vs team-specific vs matchup-specific
- Informs whether player identity features are worth including in the production model

**For prediction intervals (production):**
- Use MAPIE MapieRegressor wrapping the final ensemble
- Conformal method = "plus" (Jackknife+) for efficiency with walk-forward CV
- Output floor (10th percentile) and ceiling (90th percentile) alongside point prediction

**For rookie/unknown player projections:**
- Use career-stage grouping: Rookie (year 1), Sophomore (year 2), Veteran (3+)
- Target-encode career_stage to provide prior for unknown players
- Fall back to positional baselines (already in projection_engine.py) when insufficient data

## Integration Points with Existing Code

| Existing Module | How New Code Connects |
|-----------------|----------------------|
| `src/player_analytics.py` | Source of usage metrics (target_share, carry_share, snap_pct). Feed directly into player feature vector. |
| `src/player_advanced_analytics.py` | Source of NGS/PFR/QBR features. Rolling windows already computed. Join by player_gsis_id + season + week. |
| `src/projection_engine.py` | **Replace** heuristic projection with ML model output. Keep scoring calculator, bye week logic, injury adjustments. |
| `src/ensemble_training.py` | **Replicate** pattern for player models. Same walk_forward_cv_with_oof, same Ridge stacking. New target variable (fantasy points instead of margin/total). |
| `src/feature_engineering.py` | **New parallel module** for player feature assembly. Different grain (player-week vs game-level), different sources (player Silver + team Silver + defense Silver). |
| `src/feature_selector.py` | **Reuse** SHAP-based feature selection. Same per-fold isolation, same correlation filtering. |
| `src/scoring_calculator.py` | Downstream consumer. ML predicts fantasy points directly (or predicts stats, then scores). |
| `src/config.py` | Add player model config: PLAYER_MODEL_DIR, PLAYER_HOLDOUT_SEASON, per-position hyperparameters. |

## Sources

- [MAPIE PyPI](https://pypi.org/project/MAPIE/) -- version 1.3.0, Python>=3.9, confirmed Feb 2026 (HIGH confidence)
- [MAPIE Documentation](https://mapie.readthedocs.io/en/latest/) -- conformal prediction intervals for regression (HIGH confidence)
- [statsmodels PyPI](https://pypi.org/project/statsmodels/) -- version 0.14.6, Python>=3.9, confirmed Dec 2025 (HIGH confidence)
- [statsmodels MixedLM docs](https://www.statsmodels.org/stable/examples/notebooks/generated/mixed_lm_example.html) -- mixed-effects model examples (HIGH confidence)
- [scikit-learn TargetEncoder](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.TargetEncoder.html) -- available since sklearn 1.3 (HIGH confidence)
- [scikit-learn quantile regression](https://scikit-learn.org/stable/auto_examples/ensemble/plot_gradient_boosting_quantile.html) -- GBR with quantile loss (HIGH confidence)
- [Bayesian Hierarchical Modeling for Fantasy Football](https://srome.github.io/Bayesian-Hierarchical-Modeling-Applied-to-Fantasy-Football-Projections-for-Increased-Insight-and-Confidence/) -- research context (LOW confidence, blog post)
- [Linear Mixed Effect Modeling for Fantasy Football](https://www.dennisgong.com/blog/fantasy_football/) -- practical mixed-effects application (LOW confidence, blog post)

---
*Stack research for: ML-based player fantasy point prediction system (v3.0)*
*Researched: 2026-03-29*
