# Project Research Summary

**Project:** NFL v2.0 Prediction Model Improvement
**Domain:** ML game prediction — player-level features, model ensembles, feature selection, adaptive signals
**Researched:** 2026-03-24
**Confidence:** HIGH

## Executive Summary

The v1.4 baseline delivers 53.2% ATS accuracy overall but only 50.0% on the 2024 sealed holdout — essentially coin-flip performance. The core problem is that all 283 existing features are team-level aggregates that react slowly to roster changes. The research is unambiguous: the highest-leverage improvement is a direct QB quality differential plus backup detection, following the same approach that gives nfelo its 53.7% ATS accuracy with only ~15 features. Feature selection to reduce the existing 283-feature vector before adding new signals is the mandatory first modeling step, not an afterthought.

The recommended approach is a four-workstream build executed in strict dependency order: (1) player feature engineering to add QB quality index and injury impact at [team, season, week] grain, (2) walk-forward-safe feature selection to reduce the combined feature set from ~310 to 80-120, (3) a three-base-learner stacking ensemble (XGBoost + LightGBM + CatBoost via Ridge meta-learner) trained on the clean feature set, and (4) optional advanced features (EWM windows, momentum scores) added only after the ensemble baseline is validated. The target is 53%+ holdout ATS, achievable with realistic combined improvement of 1.5-4.0 percentage points from all P1 changes.

The dominant risk category is data leakage in new forms. The v1.4 milestone already caught one leakage bug (same-week team stats). v2.0 introduces three new leakage surfaces: player Silver paths not lag-guarded for prediction use, feature selection running before the holdout split, and stacking OOF generated with standard k-fold instead of temporal walk-forward folds. Every one of these burns the sealed 2024 holdout permanently — making the validation strategy invalid for the entire milestone. Strict phase ordering and explicit leakage assertions in tests are the primary mitigations.

## Key Findings

### Recommended Stack

The existing Python 3.9 stack (pandas 1.5.3, XGBoost 2.1.4, scikit-learn 1.6.1, optuna 4.8.0) is unchanged. Four new packages are needed: LightGBM 4.6.0 (second base learner — faster training, leaf-wise splitting finds different patterns than XGBoost depth-wise growth), CatBoost 1.2.10 (third base learner — symmetric trees, ordered boosting, independent error variance), SHAP 0.48.0 (feature importance analysis; 0.49+ requires Python 3.11+, so this specific version is mandatory), and matplotlib 3.9.4 (arrives as a CatBoost transitive dependency, pin explicitly). All needed feature selection tooling is already present in scikit-learn 1.6.1 (`StackingRegressor`, `SelectFromModel`, `VarianceThreshold`, `mutual_info_regression`) and pandas 1.5.3 (`ewm(halflife=N)`). No additional libraries are warranted.

**Core technologies:**
- LightGBM 4.6.0: second ensemble base learner — leaf-wise splitting finds patterns XGBoost depth-wise growth misses; 2-5x faster training on the 283-feature dataset
- CatBoost 1.2.10: third ensemble base learner — symmetric trees + ordered boosting adds orthogonal prediction error; Python 3.9 cp39 wheels confirmed
- SHAP 0.48.0: feature importance analysis — TreeExplainer runs natively on all three base learners; last release compatible with Python 3.9 (mandatory version pin)
- sklearn StackingRegressor + RidgeCV: meta-learner wrapper — use with `cv=TimeSeriesSplit` to prevent future leakage at ensemble level; already in installed 1.6.1
- pandas ewm(): adaptive rolling windows — `halflife=3` recency weighting already available in installed 1.5.3; no new install needed

### Expected Features

The FEATURES.md research identifies a clear priority split. QB features and feature reduction are P1 deliverables that drive the headline improvement. Ensemble and momentum work are also P1 but lower expected return. Advanced features (CatBoost as third learner, 10-game windows, quantile intervals, regime detection, depth chart deltas) are P2/P3 — add only after P1 core shows measurable holdout improvement.

**Must have (table stakes — P1):**
- SHAP/gain feature importance analysis — current model is a black box; required before adding any new features to understand which of 283 contribute signal
- Correlation redundancy filter — existing 283 features contain highly collinear pairs (r > 0.90); reduce to 80-120 before adding player features or ensemble
- Starting QB quality differential (EPA-based rolling, roll3/roll6) — single highest-impact player feature; nfelo's QB adjustment is their largest signal; expected +0.5-1.5% ATS
- Backup QB detection flag + quality drop — QB injuries cause 8-12 point power ranking shifts; current model is blind for 2-3 weeks post-injury; expected +0.5-1.0% ATS
- LightGBM + Ridge meta-learner stacking (2-model minimum) — OOF stacking with temporally-ordered folds; expected +0.3-0.8% ATS
- Momentum signal (win streak + ATS trend, opponent-adjusted) — simple derived column from existing Bronze schedules; low implementation cost; expected +0.2-0.5% ATS

**Should have (competitive — P2):**
- CatBoost as third base learner — adds independent error variance; only justified after LightGBM stacking shows measurable uplift
- Adaptive 10-game rolling windows — test whether longer window adds signal over 3/6-game variants
- Quantile regression intervals — prediction intervals for edge confidence refinement using XGBoost native quantile objective; no new library needed

**Defer (P3/v2.x+):**
- Regime detection flag — experimental changepoint detection on EPA rolling std; low expected gain, high leakage risk if full-season retroactive labels are used
- Depth chart delta features — requires new Silver path; high complexity; defer until base improvements validated
- WR-CB matchup graph (Neo4j) — requires v3.1 graph infrastructure; not achievable from flat Parquet
- Live in-season model updates — requires production infrastructure (v3.0 milestone)

### Architecture Approach

v2.0 extends v1.4 without replacing it. Four new source files are created (`src/player_feature_engineering.py`, `src/feature_selector.py`, `src/ensemble_model.py`, `src/advanced_features.py`) and five existing files are minimally modified with backward-compatible additions (`src/feature_engineering.py`, `src/model_training.py`, `scripts/train_prediction_model.py`, `scripts/generate_predictions.py`, `src/config.py`). The critical design constraint is that all player features must be aggregated to [team, season, week] grain before joining the feature matrix — no per-player columns enter the training data. The prediction CLI dispatches to the ensemble or single-model path by reading `metadata.json["model_type"]`, preserving v1.4 model artifacts in `models/spread/` as the untouched fallback throughout development. Four new test files bring the target suite to ~470 tests.

**Major components:**
1. `src/player_feature_engineering.py` — QB quality index (EPA rolling + QBR) and injury impact (position-weighted, shift(1)-lagged) at [team, season, week] grain; integrates via left-join in `_assemble_team_features()`
2. `src/feature_selector.py` — walk-forward-safe correlation filter + importance threshold pruning; runs inside each CV fold on training data only; outputs `FeatureSelectionResult` with selected feature list and metadata
3. `src/ensemble_model.py` — XGBoost + LightGBM + CatBoost base learners with Ridge meta-learner trained on temporally-ordered OOF predictions; artifacts saved to `models/ensemble/`; backward-compatible dispatch via metadata.json
4. `src/advanced_features.py` — EWM rolling windows, momentum scores, regime detection; lowest priority, highest experimental uncertainty; implement only after Phases 1-3 are validated

### Critical Pitfalls

1. **Player feature lag not verified** — player Silver paths (`players/usage_metrics`, `players/rolling_avgs`, `players/advanced_profiles`) were built for retrospective fantasy analysis, not forward-looking prediction; the existing team-level `shift(1)` guard in `feature_engineering.py` does not extend to player sources automatically. Add a `validate_player_feature_lag()` assertion in tests; prefer `players/rolling_avgs` (already lag-safe by construction) over `players/usage_metrics` (may include current-week snaps).

2. **Feature selection peeking at holdout** — running correlation filtering or importance pruning on the assembled feature matrix before the train/holdout split contaminates the sealed 2024 evaluation, inflating final ATS by 1-3 percentage points and permanently invalidating the holdout. Add `assert 2024 not in training_seasons` at the top of every selection and training script; split the holdout first, always.

3. **Stacking OOF with standard k-fold** — using `sklearn.cross_val_predict` with `KFold` allows the base model trained on 2024 data to generate predictions for 2020 games, producing temporal leakage at the ensemble level even if base models are individually clean. Write a new `generate_oof_predictions()` function that uses the existing walk-forward CV fold structure; never adapt standard sklearn stacking examples directly.

4. **Feature count explosion** — the current baseline is 283 features; adding player features on top (not replacing) pushes to 500+ with a 1:4 feature-to-sample ratio on ~2,100 games. Hard ceiling: 150 features in the final model. Gate: add a player feature group only if it reduces validation MAE by at least 0.2. Run the feature budget check after each player feature group is added, not just once.

5. **LightGBM/CatBoost hyperparameter search space reuse** — the existing Optuna search space is calibrated for XGBoost. LightGBM's leaf-wise growth requires `min_data_in_leaf >= 20`, `num_leaves <= 31` on small datasets. CatBoost requires `depth=4-6`, `l2_leaf_reg=3-10`. Create separate Optuna studies per model type with a `validation_gap_penalty` to steer away from overfitting configurations.

## Implications for Roadmap

Based on the architecture's explicit build-order dependency analysis and the pitfall-to-phase mapping, four phases are recommended in strict dependency order.

### Phase 1: Player Feature Engineering

**Rationale:** More signal before pruning is more productive than less signal before pruning. QB quality differential is the single highest-impact change (expected +0.5-1.5% ATS) and all required Bronze sources are already ingested. This phase is also the highest leakage risk — getting the lag guard right here prevents cascading contamination in all later phases.
**Delivers:** `src/player_feature_engineering.py` with QB quality index and position-weighted injury impact at [team, season, week] grain; integration into `feature_engineering.py`; feature count grows from 283 to ~310-330; tests including player lag assertions
**Addresses:** Starting QB quality differential (P1 table stakes), backup QB detection flag (P1 table stakes), position-weighted injury impact
**Avoids:** Player aggregation without lag verification (Pitfall 1); QB-centric features missing O-line signal (Pitfall 9)
**Uses:** Existing Bronze player_weekly, depth_charts, injuries; Silver players/advanced (2020-2025 confirmed available)

### Phase 2: Feature Selection

**Rationale:** Clean input improves all three ensemble models equally. Adding ensemble complexity to 310+ noisy features compounds overfitting. Feature selection must be walk-forward-safe and must exclude the 2024 holdout — implementing this constraint correctly before the ensemble is built prevents the most expensive recovery scenario (burned holdout).
**Delivers:** `src/feature_selector.py` with correlation filter + importance threshold + `FeatureSelectionResult`; feature count reduced from ~310 to 80-120; integration into `model_training.py` walk-forward CV; holdout exclusion assertion enforced project-wide
**Addresses:** Correlation/redundancy filter (P1 table stakes), SHAP-based feature selection (P1 table stakes), feature count gate enforcement
**Avoids:** Feature selection peeking at holdout (Pitfall 4); feature count explosion (Pitfall 5)
**Dependency:** Phase 1 complete (need full candidate feature set to select from)

### Phase 3: Model Ensemble

**Rationale:** Stacking requires stable, clean features to avoid overfitting the meta-learner. The ensemble is the most architecturally complex change — building it on a reduced, validated feature set from Phase 2 reduces risk substantially. LightGBM alone with Ridge stacking (2-model) is the P1 deliverable; CatBoost as the third learner is P2 after validating uplift.
**Delivers:** `src/ensemble_model.py` with GradientBoostingEnsemble (XGB + LGB + CAT), `walk_forward_stacking_cv()`, `train_ensemble()`, `predict_ensemble()`; model artifacts in `models/ensemble/`; CLI extensions to `train_prediction_model.py` (--ensemble flag) and `generate_predictions.py` (metadata dispatch); 2024 holdout evaluation
**Implements:** Ensemble model architecture component; backward-compatible metadata.json dispatch preserving v1.4 artifacts
**Avoids:** Stacking OOF temporal leakage (Pitfall 3); LightGBM/CatBoost hyperparameter search space reuse (Pitfall 8)
**Dependency:** Phase 2 complete (feature selection must be stable before ensemble training)

### Phase 4: Advanced Features (Optional Workstream)

**Rationale:** Lowest expected gain, highest experimental uncertainty. Momentum signals require opponent-adjustment to avoid conflating schedule difficulty with form. Regime detection requires online-only computation to avoid future-data leakage. Implemented last because both add complexity without de-risking the core delivery — and measuring marginal gain against a validated ensemble baseline is more reliable than measuring against a single XGBoost model.
**Delivers:** `src/advanced_features.py` with EWM rolling windows, opponent-adjusted momentum score, optional regime flags; integration into `feature_engineering.py`
**Addresses:** Adaptive rolling windows (P2), momentum signal (P1 — opponent-adjusted form only), regime detection (P3)
**Avoids:** Momentum features conflating opponent quality (Pitfall 6); regime detection using future data (Pitfall 7)
**Dependency:** Phase 3 validated — advanced features should show incremental lift over the ensemble baseline, not just over the v1.4 XGBoost single model

### Phase Ordering Rationale

- Player features before selection: ensures the selection pipeline sees the full candidate set, including features that may replace existing redundant team-level columns rather than being added on top
- Selection before ensemble: the Ridge meta-learner in a stacking ensemble is sensitive to its training set; noisy base-model OOF predictions corrupt the meta-regression
- Ensemble before advanced features: momentum and regime features have uncertain signal value; measuring marginal gain against a validated ensemble baseline is more reliable than measuring against single-model XGBoost
- Advanced features are explicitly optional: if Phases 1-3 push holdout ATS to 53%+, Phase 4 is incremental optimization, not milestone-critical
- Each phase gate includes a 2024 holdout ATS evaluation before proceeding — this enforces honest measurement at each transition

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Verify which player Silver transformation scripts apply `shift(1)` for prediction use (grep `.shift(1)` in `silver_player_transformation.py` and related scripts — this must be a first task, not an assumption); confirm nfl-data-py depth chart weekly update cadence to determine correct lag strategy for depth chart features
- **Phase 3:** OOF stacking with temporal walk-forward is not the default sklearn pattern — plan step requires explicit OOF generation protocol design before implementation to avoid accidentally building a standard k-fold loop

Phases with standard patterns (skip research-phase):
- **Phase 2:** Correlation filter + `SelectFromModel` feature selection is well-documented sklearn pattern; implementation is straightforward given the existing walk-forward CV structure in `model_training.py`
- **Phase 4:** EWM windows are trivial pandas additions (`ewm(halflife=3)`); momentum formulas are domain-specific but simple; only regime detection would warrant research if elevated to P2 priority

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All package versions verified against PyPI JSON API and confirmed against Python 3.9 constraint; pip list confirms existing installed versions; SHAP 0.48.0 version pin is critical and must not be changed |
| Features | MEDIUM-HIGH | QB adjustment value validated by nfelo's published 53.7% ATS result (HIGH confidence); ensemble gains are MEDIUM confidence (tabular sports data is domain-specific; general 6.3% accuracy lift claims are from non-sports benchmarks); momentum signal is LOW confidence but low implementation cost justifies inclusion |
| Architecture | HIGH | Based on direct codebase inspection of all existing prediction modules and Silver data inventory; build order is dependency-driven with clear rationale; backward compatibility verified against existing module interfaces |
| Pitfalls | HIGH | Leakage pitfalls are HIGH confidence based on prior v1.4 experience (real bug caught) and academic literature; LightGBM/CatBoost overfitting profiles are HIGH confidence from established ML community guidance; regime detection leakage is HIGH confidence from first-principles temporal analysis |

**Overall confidence:** HIGH

### Gaps to Address

- **Actual holdout improvement per change:** Expected ATS lifts (+0.5-1.5% for QB features, +0.3-0.8% for stacking) are literature-derived estimates, not measured values. The 2024 sealed holdout is the only reliable measurement. Each phase transition should include a holdout evaluation gate — do not proceed to Phase 3 ensemble work if Phase 1+2 shows zero improvement on validation folds.
- **Player Silver lag status:** It is unconfirmed whether existing player Silver transformation scripts apply `shift(1)` for prediction use. This must be verified at the start of Phase 1 implementation. A grep for `.shift(1)` in `silver_player_transformation.py` and related scripts is the literal first task.
- **Backup quality encoding complexity:** Research recommends starting with a binary "starter active (1/0)" over complex career-average backup quality estimation. Final encoding decision should be validated against held-out folds before adding `backup_uncertainty` complexity features. Do not over-engineer the first version.
- **Regime detection priority:** Research classifies regime detection as LOW priority (high complexity, uncertain gain, leakage risk). It should be explicitly de-prioritized unless Phases 1-3 leave headroom and a clear causal hypothesis can be stated before implementation.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `src/feature_engineering.py`, `src/model_training.py`, `src/prediction_backtester.py`, `scripts/generate_predictions.py`, `src/config.py` — all existing prediction module interfaces verified
- `pip list` in project venv — ground truth for installed package versions
- [LightGBM 4.6.0 PyPI](https://pypi.org/pypi/lightgbm/json) — requires_python>=3.7; latest stable release confirmed
- [CatBoost 1.2.10 PyPI](https://pypi.org/pypi/catboost/1.2.10/json) — cp39 macOS/Linux/Windows wheels confirmed
- [SHAP 0.48.0 PyPI](https://pypi.org/pypi/shap/0.48.0/json) — requires_python>=3.9; 0.49+ requires Python 3.11+; version boundary confirmed
- [scikit-learn StackingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.StackingRegressor.html) — presence confirmed via import test in project venv
- [scikit-learn feature selection](https://scikit-learn.org/stable/modules/feature_selection.html) — SelectFromModel, VarianceThreshold, mutual_info_regression all in 1.6.1
- [nfelo Model Performance](https://www.nfeloapp.com/games/nfl-model-performance/) — 53.7% ATS with QB adjustment; validates QB feature priority
- [nfeloqb GitHub](https://github.com/greerreNFL/nfeloqb) — QB Elo adjustment implementation reference
- [Frontiers in Sports 2025: Advancing NFL Win Prediction](https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2025.1638446/full) — SHAP feature importance, RF vs NN vs traditional; RF outperforms NN on small NFL sample

### Secondary (MEDIUM confidence)
- [Stacking Ensembles XGBoost+LightGBM+CatBoost (2025)](https://johal.in/ensemble-learning-methods-xgboost-and-lightgbm-stacking-for-improved-predictive-accuracy-2025/) — 6.3% accuracy lift over best single model on general tabular data; not sports-specific
- [Stacking Ensemble Research Square 2025](https://www.researchsquare.com/article/rs-7944070/v1) — per-model overfitting profiles on small datasets
- [Towards Data Science: Proper model validation when stacking](https://towardsdatascience.com/how-to-properly-validate-a-model-when-stacking-ad2ee1b2b9c/) — OOF temporal ordering requirement
- [SHAP vs Permutation Importance (Springer 2024)](https://link.springer.com/article/10.1186/s40537-024-00905-w) — SHAP consistency advantage over permutation importance
- [Impact of Injuries on NFL Power Rankings (WalterFootball)](https://walterfootball.com/impactinjuriespowerrankings.php) — QB injury causes 8-12 position drop in power rankings
- [Feature Importance in Gradient Boosting Trees with CV Feature Selection (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9140774/) — walk-forward-safe selection pattern

### Tertiary (LOW confidence)
- [ResearchGate: Searching for Momentum in the NFL](https://www.researchgate.net/publication/227378935_Searching_for_Momentum_in_the_NFL) — weak momentum evidence after controlling for team quality; supports anti-feature classification for raw win/loss streaks
- [Hidden Markov Model Regime Detection (Medium)](https://pyquantlab.medium.com/hidden-markov-model-regime-adaptive-momentum-strategy-with-dynamic-lookbacks-and-trailing-stops-be1aae8b73f1) — HMM regime detection patterns; financial domain, not sports-specific; low applicability

---
*Research completed: 2026-03-24*
*Ready for roadmap: yes*
