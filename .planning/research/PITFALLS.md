# Pitfalls Research

**Domain:** ML Game Prediction Models — v2.0 Player-Level Features, Model Ensembles, Feature Selection, Advanced Features
**Researched:** 2026-03-24
**Confidence:** HIGH (leakage, ensemble stacking, feature selection), MEDIUM (player aggregation, regime detection), based on existing codebase inspection, academic literature, and sports analytics community

---

## Background: What Already Happened

Before this research was written, the system caught a real data leakage bug: same-week raw player stats were used as features, producing 90%+ ATS on training data. After the fix, the real baseline is 53.2% ATS overall and 50.0% on the 2024 sealed holdout. The pitfalls below focus on the next phase of mistakes — the ones that happen when adding player-level features, model ensembles, and advanced signal extraction to a system that already passed the first leakage test.

---

## Critical Pitfalls

### Pitfall 1: Player Aggregation Without Per-Position Lag Verification

**What goes wrong:**
Player-level features (QB EPA/QBR rolling, depth chart deltas, injury replacement quality) are aggregated to the game level by joining player data on `[team, season, week]`. If the player data source includes stats from the current game week — even partially — the aggregation inherits leakage. This is distinct from the team-level leakage already caught: player stats (weekly rushing yards, passing EPA) are updated as games complete, and many nfl-data-py pulls include the current week if queried mid-week.

**Why it happens:**
The existing `feature_engineering.py` left-joins Silver team sources on `[team, season, week]`. When player sources are added to this join, developers assume the Silver transformation already applied `shift(1)`. But player Silver paths (`players/usage_metrics`, `players/rolling_avgs`, `players/advanced_profiles`) were built for retrospective fantasy analysis, not forward-looking prediction. The shift(1) guard applied to team sources does not automatically extend to player sources.

**How to avoid:**
1. For every player Silver source added to the feature vector, audit whether the transformation script applies `shift(1)` or equivalent lag before writing to Silver. The pattern is already established in `src/game_context.py` (referee tendencies use expanding-window with shift). Replicate for all player paths.
2. Build a `validate_player_feature_lag(df, week_col='week', stat_cols=[...])` assertion: for any game-week row, the player stats present must have a `source_week <= week - 1`. Run this assertion in test_feature_vector.py.
3. Use `players/rolling_avgs` (already lag-safe by definition if computed through week N-1) rather than `players/usage_metrics` (which may include current-week snaps).
4. For depth chart features, use `shift(1)` on depth chart position because depth charts are published mid-week and the current week's chart may reflect injuries that occur during the game being predicted.

**Warning signs:**
- Adding player features causes a sudden jump in training ATS (from 53% to 60%+) without holdout improvement
- Feature importance shows `qb_epa_week` (unlagged current week) rather than `qb_epa_roll3` (rolling prior 3 weeks)
- Player features for Weeks 1-2 are non-null when they should be missing or imputed

**Phase to address:**
Player-Level Feature Engineering phase — must be the first engineering task, before any model training with player features.

---

### Pitfall 2: Replacement Quality Encoded As a Static Number

**What goes wrong:**
Injury impact is modeled as "starter is out, backup quality = X." But in the NFL, backup quality is dynamic: a backup QB who played 3 games last season has a real skill estimate; a practice squad call-up does not. Encoding backup quality as a single lookup (e.g., ADP rank, career stats average) collapses this distribution into a point estimate. The model sees a clean number where the reality is high uncertainty — and it will overfit to that false precision.

**Why it happens:**
It's tempting to join `depth_charts` Bronze on position + team + week and compute "if starter is questionable/out, fetch backup's career stats." This produces a single number per team per game. The model treats it as signal, but the real signal is uncertainty, not the number itself.

**How to avoid:**
1. Include a `backup_uncertainty` feature alongside `backup_quality` — e.g., the variance of the backup's prior-season per-game stats or the number of games they have played. A backup with 2 career starts and a backup with 20 carry different signals.
2. Cap the injury impact signal by flagging it as low-confidence when the backup has fewer than 4 prior games. Do not try to extrapolate a 16-game rolling average from 1 game.
3. Use the existing `injuries` Bronze `status` column (Active/Questionable/Doubtful/Out) multiplied by a position-specific impact coefficient rather than trying to estimate exact replacement quality.
4. Consider a simpler binary: "starting QB is active" (1/0). The complexity of estimating backup quality on ~2,100 games will almost certainly overfit.

**Warning signs:**
- `backup_qb_career_epa` appears in the top-5 feature importances but holdout performance does not improve
- Feature importance for injury features is dominated by one extreme outlier game (a backup QBR of 1.2 in a 2020 blowout)
- Model performance for games with no injuries matches games with injuries (the feature adds no discriminative power)

**Phase to address:**
Player-Level Feature Engineering phase — design the injury encoding before implementation.

---

### Pitfall 3: Stacking Ensemble With Temporal Leakage in Meta-Feature Generation

**What goes wrong:**
The standard stacking recipe generates meta-features using out-of-fold (OOF) predictions from base models (XGBoost, LightGBM, CatBoost), then trains a Ridge meta-learner on those OOF predictions. The pitfall is applying this with standard k-fold OOF generation instead of temporally-ordered OOF generation. In standard OOF, the base model trained on 2024 games generates predictions for 2020 games — temporal leakage at the ensemble level, even if the base models themselves are clean.

**Why it happens:**
Scikit-learn's `cross_val_predict` with `StratifiedKFold` or `KFold` is the natural choice for OOF meta-feature generation. It is fast and standard. The temporal ordering requirement is an extra constraint that existing library defaults do not enforce.

**How to avoid:**
1. Generate OOF predictions for the meta-learner using the same walk-forward CV already implemented in `src/model_training.py`. For each fold (train on seasons 2016-N, validate on N+1), generate predictions from the base models and use those as meta-features.
2. The meta-learner (Ridge regression) is then trained only on OOF predictions from past seasons to predict past held-out seasons. Never use OOF predictions where the base model trained on future data.
3. Concretely: the 5-fold walk-forward already in the codebase maps directly to 5 sets of OOF predictions. Stack these temporally.
4. Keep the meta-learner simple: Ridge or Linear Regression. A CatBoost meta-learner on 5 meta-features from 2,100 games is guaranteed to overfit.

**Warning signs:**
- Meta-learner CV performance is 2+ percentage points above base model performance (expected improvement is 0.5-1%)
- Meta-learner feature importances show extreme weights on one base model's OOF predictions
- Removing one base model from the stack improves holdout performance (the stack is learning to compensate for a leaky model)

**Phase to address:**
Model Ensemble phase — the OOF generation protocol must be designed before implementing the stack. Do not adapt standard sklearn stacking examples directly.

---

### Pitfall 4: Feature Selection That Peeks at the Holdout

**What goes wrong:**
Feature selection is run on the full training + validation dataset (2016-2023) using correlation filtering, importance-based pruning, or LASSO. If the selection step implicitly uses 2024 holdout games — for example, by running correlation analysis on the entire assembled feature matrix before splitting — the selected features will be tuned to the holdout distribution. This is a subtle form of holdout contamination that inflates final evaluation by 1-3 ATS percentage points.

**Why it happens:**
Feature selection feels like a preprocessing step, not a modeling step. Developers run it once on "all the data" before the train/test split, reasoning that correlation analysis is unsupervised and shouldn't leak. But if the holdout season's feature distributions differ from training (they do, due to NFL structural changes), then selecting features that minimize correlation or maximize importance on the full matrix is implicitly tuning to the holdout.

**How to avoid:**
1. Split off the 2024 holdout FIRST using the existing `HOLDOUT_SEASON` constant in `src/config.py`. Then run all feature selection only on the 2016-2023 training data.
2. When using importance-based pruning: run the walk-forward CV on training data only, extract feature importances from each fold, average them, prune. The holdout never participates.
3. For correlation filtering: compute the correlation matrix on 2016-2023 only, then apply the resulting feature mask to 2024 holdout rows.
4. Log which features were selected and when — any feature selection that includes 2024 data invalidates the holdout.

**Warning signs:**
- Feature selection is run in a script that loads all seasons including 2024 before splitting
- The selected feature set changes significantly (>20% overlap difference) when 2024 is excluded
- Any line of code that assembles `assemble_multiyear_features([..., 2024])` before the holdout split

**Phase to address:**
Feature Selection phase — implement holdout exclusion as a hard guard before any selection code runs. The existing `HOLDOUT_SEASON` constant should be enforced by an assertion at the top of every feature selection script.

---

### Pitfall 5: Feature Count Explosion When Adding Player Sources

**What goes wrong:**
The current vector has 283 features from team-level Silver sources. Adding player-level features (QB rolling EPA, QBR, NGS separation rate, PFR pressure rate, depth chart deltas for WR/TE/RB, injury status per position) can easily double the feature count to 500+. With ~2,100 training games, a 500-feature model has a feature-to-sample ratio of 1:4 — well into memorization territory. The model appears to improve on training CV but degrades on holdout.

**Why it happens:**
Player features are genuinely useful signals. Each one individually improves training metrics. Developers add them incrementally without stopping to measure the net effect on the feature-to-sample ratio. XGBoost's built-in regularization is not sufficient to overcome a 1:4 ratio — it requires explicit feature reduction.

**How to avoid:**
1. Set a hard ceiling of 120-150 features for the final model. This is achievable if player features replace some redundant team-level features rather than being added on top.
2. Before adding player features: run correlation clustering on the existing 283 features. Groups with r > 0.80 between members (e.g., epa_3g vs epa_6g vs epa_season) should contribute ONE representative, not all variants.
3. Use the walk-forward CV MAE as a gate: add a new feature group only if it reduces mean validation MAE by at least 0.2 points on the held-out validation seasons. Do not add features that improve training MAE but not validation MAE.
4. After player features are added, run permutation importance on the validation set (not training set). Drop any feature whose permutation importance is below noise threshold (importance < 0.001).

**Warning signs:**
- Feature count exceeds 200 after player features are added (current baseline is already 283; adding player features on top will exceed this immediately)
- Training CV ATS improves but gap between training and validation ATS widens
- The top-10 most important features are all rolling-window variants of the same underlying metric (epa_3g, epa_6g, epa_season all in top 10 = redundancy, not signal)

**Phase to address:**
Feature Selection phase (must run before, during, and after player feature addition). This is not a one-time step — run the feature budget check after each player feature group is added.

---

### Pitfall 6: Momentum Features That Capture Opponent Quality, Not Momentum

**What goes wrong:**
A 3-game winning streak is strongly correlated with opponent quality. A team that won 3 in a row probably beat weak opponents. Using raw "games won in last 3" as a momentum feature conflates team strength with schedule difficulty. The feature appears predictive in training (teams on winning streaks often continue winning) but in holdout it adds noise because the causal mechanism is opponent quality, not momentum.

**Why it happens:**
Momentum features are simple to compute: `df.groupby('team')['result'].rolling(3).sum()`. They show up as important in feature importance plots because wins correlate with future wins in general. But the correlation is mediated by team quality, which is already captured by EPA differential features. Adding momentum features doubles down on team strength without adding new signal.

**Why it happens (the deeper reason):**
Academic literature on NFL momentum is skeptical. Searching for Momentum in the NFL (ResearchGate) found weak evidence for momentum effects after controlling for team quality. What looks like momentum in naive analysis is mostly schedule difficulty regression.

**How to avoid:**
1. If building momentum features, use opponent-adjusted form: "how did the team perform vs. expected EPA given opponent quality in the last 3 games" rather than raw win/loss counts.
2. Test each momentum feature in isolation: does adding it to a baseline model with EPA differentials and home/away improve validation MAE by at least 0.2? If not, discard it.
3. Never include both raw form features (last 3 wins) and EPA-based form features (last 3 EPA) simultaneously. One will dominate and the other adds noise.

**Warning signs:**
- Momentum features are in the top-10 but permutation importance on the validation set is near zero
- Removing momentum features from a model that already has EPA rolling features does not change validation ATS
- Form features fire strongly in games with large pre-game spread (already captured by the team quality signal)

**Phase to address:**
Advanced Features phase — design each advanced feature with an explicit hypothesis about what causal mechanism it captures that is not already in the 283-feature baseline.

---

### Pitfall 7: Regime Detection Introducing Future Information

**What goes wrong:**
Regime detection (identifying "high-tempo", "run-heavy", "rebuild mode" states) uses clustering or HMM on team season sequences. A regime label assigned to a team in 2024 Week 6 based on their 2024 season data is safe. But if the regime assignment uses the full 2024 season to cluster and then labels each week, it introduces future information: the Week 6 regime label reflects what happens in Weeks 7-17. This is the same bug as the original same-week leakage, applied at the season level.

**Why it happens:**
Clustering and HMM fitting naturally use all available data for the model. Developers fit on the full season and then extract week-by-week states, forgetting that Week N's label depended on Weeks N+1 through 17.

**How to avoid:**
1. Regime detection must be purely online (expanding window from Week 1 to the current week). Never fit a clustering or HMM model on the full season and then label past weeks.
2. Simpler alternative: use the rolling EPA percentile rank within the season (expanding window). A team in the 80th percentile of EPA after Week 6 is "high-performing regime" without requiring clustering. This avoids the future-lookback problem entirely.
3. If using HMM or K-means, fit only on completed seasons prior to the current season. Apply the fitted model to the current season week-by-week. Do not refit on the current season.

**Warning signs:**
- Regime labels for Week 1 are non-null in a season (Week 1 cannot have a stable regime estimate)
- Regime clustering uses `season` data that includes the prediction week
- Regime changes in the training data precisely align with game outcomes (the regime learned the results, not the process)

**Phase to address:**
Advanced Features phase — any regime or momentum detection feature must pass a "could this value be known at prediction time?" gate before inclusion.

---

### Pitfall 8: LightGBM and CatBoost Behaving Differently From XGBoost on Small NFL Samples

**What goes wrong:**
LightGBM uses leaf-wise tree growth (splits the leaf with highest gain first) rather than XGBoost's level-wise growth. On ~2,100 games, leaf-wise growth aggressively overfits unless `min_data_in_leaf` is set conservatively (20+). CatBoost handles categoricals natively but uses ordered boosting, which has a different regularization profile. Using the same hyperparameter budget (Optuna trials) for all three models without accounting for these differences produces models with very different overfitting profiles.

**Why it happens:**
The existing Optuna tuning in `scripts/train_prediction_model.py` is calibrated for XGBoost. Reusing the same search space (max_depth, learning_rate, n_estimators) for LightGBM and CatBoost produces models that look similar but have different implicit regularization.

**How to avoid:**
1. For LightGBM, set `min_data_in_leaf` floor at 20 and `num_leaves` ceiling at 31 for ~2,100 game datasets. These are not arbitrary — they follow the conservative path for small tabular data.
2. For CatBoost, use `depth=4-6` and `l2_leaf_reg=3-10`. CatBoost's ordered boosting already helps but does not eliminate the need for depth control.
3. Run each model's Optuna search with a `validation_gap_penalty`: if training ATS exceeds validation ATS by more than 5 percentage points, penalize the trial heavily. This steers Optuna away from overfitting configurations regardless of which model it's tuning.
4. Treat LightGBM and CatBoost as ensembles of their own (multiple seeds, slightly different subsets) rather than single models. Averaging 5 LightGBM runs with different `bagging_seed` values is more robust than one heavily-tuned run.

**Warning signs:**
- LightGBM converges in 20 trees (learning_rate too high, not enough regularization)
- CatBoost training takes 10x longer than XGBoost with no meaningful ATS improvement
- Validation gap (training ATS minus validation ATS) is wider for LightGBM or CatBoost than for XGBoost

**Phase to address:**
Model Ensemble phase — each base learner needs its own tuning protocol. Do not copy-paste the XGBoost hyperparameter search space.

---

### Pitfall 9: QB-Centric Feature Engineering Missing the "Rest of the Lineup" Signal

**What goes wrong:**
QB metrics (EPA, QBR, NGS time-to-throw, PFR pressure rate) are the richest player-level signals. It is tempting to build the entire player feature layer around QB quality and ignore the offensive line, WR1 availability, and RB depth chart. The resulting model has strong QB features but misses the structural factors that determine whether the QB's quality translates to game outcomes. A great QB behind a bad O-line does not produce the same prediction as a great QB behind a great O-line.

**Why it happens:**
QB data is the most complete: nfl-data-py has QBR, NGS, PFR stats, and per-game EPA all keyed to the same player. WR, RB, and O-line data is sparser, harder to aggregate to game level, and more dependent on snap count thresholds. Developers build what's easy first.

**How to avoid:**
1. Build the QB feature layer first, but immediately measure its marginal impact: does adding QB features to the 283-feature baseline improve validation MAE? If yes (expected: yes), then add complementary features for the O-line (pressure rate allowed by offensive line, from PFR) and WR1 target share differential.
2. Use snap counts as a guard: only include player features from players with >= 30% snap share. Below that, the stats are noisy and sample-size limited.
3. Keep player features symmetric between home and away. If you build `home_qb_epa_roll3`, you must build `away_qb_epa_roll3` and compute the differential. The existing differential feature assembly in `feature_engineering.py` handles this if the player sources follow the same `[team, season, week]` structure.

**Warning signs:**
- Feature vector has 5+ QB metrics but 0 O-line metrics (asymmetric coverage)
- QB feature importance is extremely high but the model still fails on games where QB changed at halftime
- The model is systematically wrong for games with depleted O-lines (identifiable from PFR sack rates)

**Phase to address:**
Player-Level Feature Engineering phase — design the full player feature schema before implementation, not incrementally.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Adding all player features on top of existing 283 | Fast to implement | Feature count explodes to 500+; overfitting guaranteed | Never — replace redundant team features |
| Using standard OOF for meta-learner generation | Familiar sklearn API | Temporal leakage at ensemble level | Never — use walk-forward OOF |
| Encoding backup quality as a single career-average number | Simple join on depth_charts | False precision on high-uncertainty backup assessments | Only if also including a backup uncertainty flag |
| Running feature selection before holdout split | Convenient | Holdout contamination; invalidates final evaluation | Never |
| Copying XGBoost Optuna search space for LightGBM/CatBoost | Fast to code | Each model has different overfitting regime; search space is wrong | OK for exploration; must be corrected before final model |
| Using raw win/loss momentum features alongside EPA features | Easy to compute | Redundant with team quality already captured by EPA | Never — use opponent-adjusted form only |
| Single-seed ensemble members | Fast training | Ensemble correlation is too high; diversity benefit is lost | Never for final ensemble — use 3-5 seeds per model |

---

## Integration Gotchas

Specific to adding player-level features and ensembles to the existing pipeline:

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `_assemble_team_features()` in feature_engineering.py | Adding player Silver sources to the same left-join without verifying lag | Add a separate `_assemble_player_features()` function with explicit `shift(1)` guards before joining to team features |
| `players/rolling_avgs` Silver path | Reading `rolling_avgs` for season N, week W as if it contains only W-1 data | Verify: does the transformation script compute rolling stats through W or through W-1? Grep for `.shift(1)` in `silver_player_transformation.py` |
| `depth_charts` Bronze | Joining depth chart on `[team, season, week]` and treating the chart as "pre-game" | nfl-data-py depth charts are often updated mid-week reflecting injury designations. Use `shift(1)` to get the prior week's chart, then use injury status to apply the actual game-week adjustment |
| `walk_forward_cv()` in model_training.py | Extending it to generate OOF predictions for stacking by adding a return value | The current function only returns MAE metrics. OOF predictions require storing per-fold predictions and concatenating — write a new `generate_oof_predictions()` function rather than modifying the existing one |
| `HOLDOUT_SEASON` in config.py | Forgetting that `assemble_multiyear_features()` accepts any season list | Add an assertion at the top of every training and feature selection script: `assert 2024 not in training_seasons` when running during model development |
| Optuna study for ensemble | Reusing the same `optuna.create_study()` for all three models | Create separate studies per model type; hyperparameter spaces are not interchangeable |
| Feature differencing in `assemble_game_features()` | Player features that are team-level aggregates (QB EPA differential) vs. individual player features (QB QBR) | Player features should be computed as differentials (home_qb_epa_roll3 - away_qb_epa_roll3) using the same differential logic already applied to team features. Do not add raw per-team player features |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Re-joining player Silver sources on every training run | Training takes 10+ minutes; each Optuna trial is slow | Pre-assemble a single `training_features_v2.parquet` that includes player columns, with an explicit version timestamp | After the first Optuna run with player features |
| Computing injury aggregation on the fly | Each model.fit() call triggers a full injury join across 6 seasons | Pre-compute `injury_impact_features.parquet` per season/week and join once during feature assembly | After 3+ Optuna runs |
| Storing 5 base model OOF arrays in memory during stacking | Memory spike during walk-forward fold generation (each model x each fold) | Write OOF predictions to disk per fold per model; load at meta-learner training time | With 3 models x 5 folds x ~300 games each |
| Running CatBoost with default iterations | CatBoost defaults to 1000 iterations; each Optuna trial takes 5x longer than XGBoost | Set `iterations=300` as Optuna starting point; use early stopping on the validation fold | First CatBoost Optuna trial |

---

## "Looks Done But Isn't" Checklist

- [ ] **Player feature lag:** Verify `shift(1)` is applied in every player Silver transformation that feeds the prediction feature vector — do not assume it inherits the team-level lag guard
- [ ] **Holdout exclusion in feature selection:** Verify that `HOLDOUT_SEASON` (2024) is excluded before any correlation filtering, importance ranking, or LASSO runs
- [ ] **Ensemble OOF temporal ordering:** Verify that meta-features for the Ridge learner were generated by walk-forward folds, not standard k-fold OOF
- [ ] **Feature count gate:** Verify final feature count is under 150 and document which team-level features were replaced (not just augmented) by player features
- [ ] **LightGBM/CatBoost tuning space:** Verify Optuna search space for each model uses model-appropriate hyperparameter bounds — not the XGBoost space
- [ ] **Backup quality uncertainty flag:** Verify every "injury replacement quality" feature is accompanied by a "games_played_by_backup" feature or equivalent uncertainty signal
- [ ] **Momentum feature adjustment:** Verify any form/streak features are opponent-adjusted — not raw win/loss counts
- [ ] **Player feature differential assembly:** Verify player features enter the model as home-minus-away differentials using the existing `assemble_game_features()` differential logic, not as raw per-team values
- [ ] **Regime detection online-only:** Verify any regime/momentum detection code uses only data available at prediction time (expanding window from Week 1, no full-season clustering and retroactive labeling)

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Player feature leakage discovered after model trained | MEDIUM | Audit each player Silver source for shift(1), rebuild `_assemble_player_features()` with explicit lags, retrain. The modular structure of feature_engineering.py makes this a targeted fix. |
| Holdout contaminated by feature selection | HIGH | Cannot recover — the 2024 holdout is burned for this experiment. Accept the caveat, wait for 2025 season data, or use a 2023 pseudo-holdout for final evaluation. |
| Ensemble meta-learner using standard OOF | MEDIUM | Rewrite OOF generation to use walk-forward; retrain meta-learner only. Base models do not need retraining. |
| Feature count exceeded (500+ features) | MEDIUM | Run correlation clustering on full feature matrix, identify redundant groups, drop all but representative, retrain. Expect 2-3 day delay. |
| CatBoost/LightGBM massively overfit | LOW | Increase `min_data_in_leaf` and `num_leaves` constraints, rerun Optuna with penalized validation gap, retrain. Usually fixable in one Optuna run. |
| Regime features using full-season retroactive labels | HIGH | Redesign as expanding-window features; requires changes to the Silver transformation generating the feature. This is a pipeline change, not just a training change. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Player aggregation without lag verification | Player-Level Feature Engineering | `test_feature_vector.py` includes player lag assertions; no player feature for Week N includes Week N data |
| Backup quality as static number | Player-Level Feature Engineering | Every injury feature has a paired uncertainty/games-played feature |
| Stacking with temporal leakage in OOF | Model Ensemble | OOF generation uses walk-forward folds; `generate_oof_predictions()` documented to require temporal ordering |
| Feature selection peeking at holdout | Feature Selection | `HOLDOUT_SEASON` excluded before any selection script; assertion at top of all selection scripts |
| Feature count explosion | Feature Selection | Final feature count logged; gate checks that player features replace redundant team features |
| Momentum features conflating opponent quality | Advanced Features | Each momentum feature paired with a marginal validation MAE test; opponent-adjusted form used |
| Regime detection using future data | Advanced Features | Regime/HMM fitting uses only completed prior seasons; expanding-window for in-season labels |
| LightGBM/CatBoost overfitting | Model Ensemble | Validation gap < 5 ATS percentage points per model; model-specific Optuna search spaces |
| QB-centric player features missing O-line | Player-Level Feature Engineering | Feature schema documented before implementation; O-line/WR features included alongside QB features |

---

## Sources

- Direct inspection of `/Users/georgesmith/repos/nfl_data_engineering/src/feature_engineering.py`, `src/model_training.py`, `src/player_analytics.py`, `src/player_advanced_analytics.py` — codebase state as of 2026-03-24
- [ParlaySavant: How to Build Sports Prediction Models 2026](https://www.parlaysavant.com/insights/sports-prediction-models-2026) — player feature leakage, rolling window pitfalls
- [ResearchGate: Searching for Momentum in the NFL](https://www.researchgate.net/publication/227378935_Searching_for_Momentum_in_the_NFL) — academic evidence that raw momentum features conflate opponent quality
- [Towards Data Science: How to properly validate a model when stacking](https://towardsdatascience.com/how-to-properly-validate-a-model-when-stacking-ad2ee1b2b9c/) — OOF temporal ordering requirement for stacking
- [ResearchGate: Stacking Ensemble Learning combining XGBoost, LightGBM, CatBoost](https://www.researchgate.net/publication/397047638_Stacking_Ensemble_Learning_Combining_XGBoost_LightGBM_CatBoost_and_AdaBoost_with_Random_Forest_Meta_Model) — per-model overfitting profiles on small datasets
- [ScienceDirect: Importance of proper validation strategy for avoiding overfitting](https://www.sciencedirect.com/article/pii/S0003267025012322) — feature selection before holdout split as contamination
- [Frontiers in Sports and Active Living: Advancing NFL Win Prediction with ML](https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2025.1638446/full) — feature dimensionality vs sample size tradeoffs
- [Open Source Football: XGBoost Win Probability Model](https://opensourcefootball.com/posts/2021-04-13-creating-a-model-from-scratch-using-xgboost-in-r/) — practical pitfalls with NFL tabular data
- Previous PITFALLS.md (researched 2026-03-19) — Pitfalls 1-9 from v1.4 milestone remain valid and are not duplicated here

---

*Pitfalls research for: v2.0 Prediction Model Improvement — Player Features, Ensembles, Feature Selection, Advanced Features*
*Researched: 2026-03-24*
