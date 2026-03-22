# Phase 25: Feature Assembly and Model Training - Research

**Researched:** 2026-03-20
**Domain:** XGBoost ML model training, game-level differential feature engineering, walk-forward CV
**Confidence:** HIGH

## Summary

This phase assembles game-level differential features from 8 Silver team sources and trains XGBoost spread/total prediction models with walk-forward cross-validation and Optuna hyperparameter tuning. The existing Silver infrastructure (337-column feature vector, 8 team sources, 2016-2025 data) provides a solid foundation -- the key new work is (a) pivoting per-team Silver rows into per-game differential rows by joining home/away team features via schedules, (b) enforcing temporal lag so week N predictions use only week N-1 data, and (c) training regularized XGBoost models on ~2,367 games (2016-2024 regular season).

A critical dependency issue: **XGBoost 3.x requires Python >= 3.10, but this project runs Python 3.9.7.** The solution is to use XGBoost 2.1.4, which is the latest version supporting Python 3.9 (requires >= 3.8). This is a production-stable release and fully supports all features needed (JSON model serialization, feature importance, early stopping, callbacks). Optuna 4.8.0 supports Python 3.9 natively.

**Primary recommendation:** Use XGBoost 2.1.4 + Optuna 4.8.0 + scikit-learn (for metrics only). Assemble game-level differentials by joining Silver team features on schedules Bronze via game_id. Use `model.save_model('model.json')` for portable serialization.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Team-level features only -- no player-level features
- **D-05:** Expanding window strategy -- train on seasons 2016..N, validate on N+1
- **D-06:** Training seasons: 2016-2023. Holdout: 2024 (sealed, never touched during tuning per BACK-02)
- **D-07:** Season-level fold boundaries only -- no intra-season splits to avoid data leakage
- **D-09:** 50 Optuna trials per target for hyperparameter tuning
- **D-10:** Separate XGBoost models for spread and over/under -- independent hyperparameters per target
- **D-11:** Conservative default hyperparameters mandatory: shallow trees, strong regularization, early stopping
- **D-14:** Vegas lines excluded as input features (zero edge by definition)
- **D-15:** Script name: `scripts/train_prediction_model.py`

### Claude's Discretion
- D-02: Module placement for feature assembly code
- D-03: NaN handling for Weeks 1-3 (fill strategy)
- D-04: Differential feature selection (all numeric vs curated subset)
- D-08: Walk-forward fold count
- D-12: Model artifact format
- D-13: Optuna optimization metric
- D-16: CLI flag design beyond --target
- D-17: Model output directory
- D-18: Feature importance report format

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FEAT-01 | Game-level differential features (home - away) from Silver team data | Differential assembly pattern using schedules Bronze as game spine + Silver team features joined per side |
| FEAT-02 | All Silver sources audited to use only week N-1 data for week N | Existing Silver data already stores per-week rolling stats; lag enforcement via `week < target_week` filter |
| FEAT-03 | Feature importance analysis using XGBoost built-in importance and/or SHAP | XGBoost 2.1.4 provides `feature_importances_` (gain-based) and `get_booster().get_score()` for multiple importance types |
| FEAT-04 | Early-season (Weeks 1-3) NaN handling for sparse rolling features | XGBoost handles NaN natively as missing values -- no imputation required for tree models. Fill zeros only for pure count columns |
| MODL-01 | XGBoost spread model with walk-forward CV | XGBRegressor with expanding window (2016..N train, N+1 validate), MAE metric |
| MODL-02 | XGBoost total model with walk-forward CV | Same framework, separate hyperparameters |
| MODL-03 | Walk-forward cross-validation framework | Season-level folds: 5 folds (train 2016-2018/val 2019, ..., train 2016-2022/val 2023). 2024 sealed as holdout |
| MODL-04 | Optuna hyperparameter tuning | 50 trials per target, TPE sampler, pruning via XGBoostPruningCallback |
| MODL-05 | Conservative default hyperparameters | max_depth=4, eta=0.05, min_child_weight=5, subsample=0.8, colsample_bytree=0.7, reg_alpha=1.0, reg_lambda=5.0, n_estimators=500 with early_stopping_rounds=50 |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 2.1.4 | Gradient boosted tree models | Latest version supporting Python 3.9; production-stable |
| optuna | 4.8.0 | Bayesian hyperparameter optimization | TPE sampler, XGBoost pruning callback, Python 3.9 support |
| scikit-learn | 1.6.x | Metrics (MAE, RMSE, R2) | Standard ML metrics library; not used for models |
| pandas | 1.5.3 (existing) | Feature assembly, data manipulation | Already installed |
| numpy | 1.26.4 (existing) | Numerical operations | Already installed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| joblib | (bundled with sklearn) | Parallel Optuna if needed | Only if trial parallelism desired |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| XGBoost 3.2.0 | XGBoost 2.1.4 | 3.x requires Python >= 3.10; 2.1.4 is last Python 3.9 build |
| SHAP | XGBoost built-in importance | SHAP adds heavy dependency; built-in gain/weight importance sufficient for Phase 25 |
| LightGBM | XGBoost | Locked decision: XGBoost only at this scale |

**Installation:**
```bash
pip install "xgboost>=2.1.4,<3.0" optuna scikit-learn
```

## Architecture Patterns

### Recommended Project Structure
```
src/
  feature_engineering.py     # NEW: game-level differential feature assembly
  config.py                  # ADD: model config constants (CONSERVATIVE_PARAMS, MODEL_DIR)
scripts/
  train_prediction_model.py  # NEW: training CLI
models/                      # NEW: model artifacts directory
  spread/
    model.json               # XGBoost native JSON
    metadata.json            # Training metadata, feature list, CV scores
  total/
    model.json
    metadata.json
tests/
  test_feature_engineering.py  # NEW: differential assembly + lag tests
  test_model_training.py       # NEW: walk-forward CV + model output tests
```

### Pattern 1: Game-Level Differential Feature Assembly

**What:** Transform per-team-per-week Silver features into per-game differential features (home_metric - away_metric).

**When to use:** For every game prediction -- the core feature engineering step.

**Assembly flow:**
1. Load schedules Bronze for the game spine (game_id, season, week, home_team, away_team, spread_line, total_line, home_score, away_score)
2. For each Silver source, load per-team weekly data
3. Join the assembled Silver feature vector to schedules twice: once for home_team, once for away_team
4. Compute differentials: `diff_col = home_col - away_col` for all numeric features
5. Add non-differential context features: is_dome, div_game, rest_advantage, etc.

**Critical detail:** The Silver data already has per-week granularity with rolling features. The game_context Silver source has `game_id` and `is_home` columns which provides the game-to-team mapping. Use game_context as the bridge:

```python
# Verified from data: game_context has [team, season, week, game_id, is_home]
# Each game_id appears twice (home + away)
# Silver team sources join on [team, season, week]

def assemble_game_features(season: int) -> pd.DataFrame:
    """Assemble game-level differential features for one season."""
    # 1. Load game_context for game spine
    gc = load_silver("game_context", season)

    # 2. Load and join all Silver team sources on [team, season, week]
    features = gc[["team", "season", "week", "game_id", "is_home"]].copy()
    for source_name, source_path in SILVER_TEAM_SOURCES.items():
        src_df = load_silver(source_path, season)
        features = features.merge(src_df, on=["team", "season", "week"], how="left")

    # 3. Split into home and away
    home = features[features["is_home"] == True]
    away = features[features["is_home"] == False]

    # 4. Join on game_id to get both sides per game
    game_df = home.merge(away, on="game_id", suffixes=("_home", "_away"))

    # 5. Compute differentials for numeric columns
    numeric_cols = [c for c in feature_cols if game_df[f"{c}_home"].dtype in [np.float64, np.int64]]
    for col in numeric_cols:
        game_df[f"diff_{col}"] = game_df[f"{col}_home"] - game_df[f"{col}_away"]

    # 6. Add labels from schedules Bronze
    schedules = load_bronze_schedules(season)
    game_df = game_df.merge(schedules[["game_id", "spread_line", "total_line",
                                        "home_score", "away_score"]], on="game_id")
    game_df["actual_margin"] = game_df["home_score"] - game_df["away_score"]
    game_df["actual_total"] = game_df["home_score"] + game_df["away_score"]

    return game_df
```

### Pattern 2: Walk-Forward Cross-Validation

**What:** Season-expanding training windows with season-level boundaries.

**When to use:** All model training and hyperparameter tuning.

**Fold structure (5 folds):**
| Fold | Train Seasons | Validate Season | Train Games (~) |
|------|--------------|-----------------|-----------------|
| 1 | 2016-2018 | 2019 | ~768 |
| 2 | 2016-2019 | 2020 | ~1,024 |
| 3 | 2016-2020 | 2021 | ~1,280 |
| 4 | 2016-2021 | 2022 | ~1,552 |
| 5 | 2016-2022 | 2023 | ~1,823 |
| Holdout | 2016-2023 | 2024 | ~2,095 (SEALED) |

```python
def walk_forward_cv(all_data: pd.DataFrame, target_col: str):
    """Walk-forward cross-validation with season boundaries."""
    val_seasons = [2019, 2020, 2021, 2022, 2023]
    fold_scores = []

    for val_season in val_seasons:
        train = all_data[all_data["season"] < val_season]
        val = all_data[all_data["season"] == val_season]

        model = xgb.XGBRegressor(**CONSERVATIVE_PARAMS)
        model.fit(
            train[feature_cols], train[target_col],
            eval_set=[(val[feature_cols], val[target_col])],
            verbose=False
        )
        preds = model.predict(val[feature_cols])
        fold_scores.append(mean_absolute_error(val[target_col], preds))

    return np.mean(fold_scores), fold_scores
```

### Pattern 3: Optuna Integration with Walk-Forward CV

**What:** Bayesian hyperparameter search using walk-forward CV as the objective.

```python
import optuna

def objective(trial):
    params = {
        "max_depth": trial.suggest_int("max_depth", 2, 6),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
        "min_child_weight": trial.suggest_int("min_child_weight", 3, 10),
        "subsample": trial.suggest_float("subsample", 0.6, 0.9),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 0.8),
        "reg_alpha": trial.suggest_float("reg_alpha", 0.1, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 20.0, log=True),
        "n_estimators": 500,
        "early_stopping_rounds": 50,
    }
    mean_mae, _ = walk_forward_cv(train_data, target_col, params)
    return mean_mae

study = optuna.create_study(direction="minimize")
study.optimize(objective, n_trials=50)
```

### Pattern 4: Temporal Lag Enforcement

**What:** Guarantee that week N predictions use only data from week N-1 or earlier.

**How the Silver data already handles this:** The Silver team sources store rolling statistics per-week where the rolling window includes data only up to that week. For example, `off_epa_per_play_roll3` at week 5 is the 3-game rolling average of weeks 2-4. The Silver processing already shifts data by one week.

**Verification approach:** For each feature in the assembled dataset, verify that:
1. The Silver source computes rolling stats using `shift(1)` or equivalent
2. The assembled game features for week N only reference Silver data rows at week N (which already represent entering-week-N stats)
3. No label columns (scores, spread results) leak into features

```python
def test_temporal_lag():
    """Verify no future data leakage in features."""
    games = assemble_game_features(2024)

    # For each game at week N, verify feature data comes from <= week N-1
    # The Silver data at week N already represents entering-week-N stats (shifted)
    # So joining Silver at week == game_week is correct

    # Verify no score/result columns in feature set
    feature_cols = get_feature_columns(games)
    forbidden = ["home_score", "away_score", "actual_margin", "actual_total", "result"]
    for col in forbidden:
        assert col not in feature_cols, f"Label column {col} found in features"
```

### Anti-Patterns to Avoid
- **Using spread_line as an input feature:** Zero edge by definition -- the model would just learn to predict the line itself
- **Intra-season CV splits:** Week 10 data to predict week 5 causes temporal leakage
- **Imputing NaN with column means from full dataset:** Information from future leaks into past. XGBoost handles NaN natively -- let it
- **Training on 2024 data during tuning:** 2024 is sealed holdout per BACK-02
- **Using `pickle.dump()` for model persistence:** Not portable across XGBoost versions; use `model.save_model()` with JSON

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hyperparameter search | Grid search or manual tuning | Optuna TPE sampler | Bayesian optimization explores 50 trials far more efficiently than grid |
| Walk-forward CV | sklearn TimeSeriesSplit | Custom season-boundary folds | sklearn's TimeSeriesSplit splits by row index, not by season boundary |
| Feature importance | Manual correlation analysis | `model.feature_importances_` | XGBoost tracks gain-based importance natively during training |
| Model serialization | pickle/joblib | `model.save_model('model.json')` | JSON is forward-compatible across XGBoost versions |
| NaN handling | Custom imputation | XGBoost native missing value handling | XGBoost learns optimal split direction for missing values |
| Regression metrics | Manual MAE/RMSE computation | `sklearn.metrics` | Standard, tested implementations |

**Key insight:** XGBoost handles NaN natively for tree models. For ~2,000 training games with 180+ differential features, the biggest risk is overfitting, not missing data. Let XGBoost route missing values optimally during split decisions rather than injecting artificial signal through imputation.

## Common Pitfalls

### Pitfall 1: Feature Explosion from Differential Computation
**What goes wrong:** Computing home-away differential for all 337 columns creates ~300+ features for ~2,300 games -- a 7:1 sample-to-feature ratio.
**Why it happens:** Blindly differencing all numeric columns without considering relevance.
**How to avoid:** Use a curated subset of ~80-120 differential features. Exclude columns that don't make sense as differentials (week, season, binary flags). Group by category: EPA metrics (12-15), tendencies (8-10), SOS (4-6), situational (10-15), PBP-derived (20-30), game context diffs (5-8).
**Warning signs:** Feature importance shows many features with near-zero contribution.

### Pitfall 2: Spread Line Convention Confusion
**What goes wrong:** Misinterpreting `spread_line` sign convention causes labels and ATS calculations to be inverted.
**Why it happens:** Different sources use different conventions (positive = home favored vs. away favored).
**How to avoid:** Verified from data: `spread_line > 0` means home team is favored (positive spread = home expected to win by that margin). `result` column = `home_score - away_score`. So `actual_margin = home_score - away_score` and model predicts the home team's margin.
**Warning signs:** Model predicts opposite sign consistently; ATS accuracy below 45%.

### Pitfall 3: Early Season Sparsity Crash
**What goes wrong:** Week 1 has no prior data, so all rolling features are NaN; if code filters out NaN rows, Week 1-3 games are entirely dropped.
**Why it happens:** Rolling features require lookback window that doesn't exist in early weeks.
**How to avoid:** XGBoost handles NaN natively -- pass NaN through. The model learns that missing = early season and adjusts. For count-based features (wins, losses), fill with 0. Do NOT drop early-season rows.
**Warning signs:** Test predictions crash for Week 1; model trained on fewer games than expected.

### Pitfall 4: Overfitting on ~2,300 Games
**What goes wrong:** Model achieves 55%+ ATS on training data but ~50% on new data.
**Why it happens:** 2,300 games with 180+ features allows model to memorize noise.
**How to avoid:** Conservative hyperparameters (max_depth=4, strong reg_alpha/lambda), early stopping, limit feature count to ~100. Per STATE.md: if ATS > 58%, investigate leakage.
**Warning signs:** Large gap between train and validation MAE; validation MAE increasing across folds.

### Pitfall 5: Python 3.9 / XGBoost Version Mismatch
**What goes wrong:** `pip install xgboost` installs 3.2.0 which fails on Python 3.9.
**Why it happens:** XGBoost 3.x dropped Python 3.9 support.
**How to avoid:** Pin version: `pip install "xgboost>=2.1.4,<3.0"`.
**Warning signs:** ImportError or installation failure mentioning Python version.

## Code Examples

### Conservative XGBoost Default Parameters
```python
# Source: XGBoost docs + STATE.md overfitting concern
CONSERVATIVE_PARAMS = {
    "objective": "reg:squarederror",
    "max_depth": 4,              # Shallow trees -- critical for small dataset
    "learning_rate": 0.05,       # Low learning rate
    "n_estimators": 500,         # Many weak learners, rely on early stopping
    "min_child_weight": 5,       # Minimum samples in leaf
    "subsample": 0.8,            # Row sampling
    "colsample_bytree": 0.7,     # Column sampling per tree
    "reg_alpha": 1.0,            # L1 regularization
    "reg_lambda": 5.0,           # L2 regularization (strong)
    "early_stopping_rounds": 50, # Stop if no improvement for 50 rounds
    "random_state": 42,
    "verbosity": 0,
}
```

### Model Serialization (JSON Native)
```python
# Source: XGBoost Model IO docs
import json
import xgboost as xgb

# Save model
model.save_model("models/spread/model.json")

# Save metadata alongside
metadata = {
    "target": "spread",
    "training_seasons": [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023],
    "n_features": len(feature_cols),
    "feature_names": feature_cols,
    "cv_scores": {"mean_mae": mean_mae, "fold_maes": fold_maes},
    "best_params": best_params,
    "trained_at": datetime.now().isoformat(),
}
with open("models/spread/metadata.json", "w") as f:
    json.dump(metadata, f, indent=2)

# Load model
loaded = xgb.XGBRegressor()
loaded.load_model("models/spread/model.json")
```

### Feature Importance Report
```python
# Source: XGBoost feature_importances_ API
import xgboost as xgb

# After training
importance = model.feature_importances_  # gain-based by default
feat_imp = pd.DataFrame({
    "feature": feature_cols,
    "importance": importance,
}).sort_values("importance", ascending=False)

# Top 20 report
print("\nTop 20 Features by Gain:")
print(feat_imp.head(20).to_string(index=False))

# Save to file
feat_imp.to_csv("models/spread/feature_importance.csv", index=False)
```

### Optuna Hyperparameter Search Ranges
```python
# Source: XGBoost tuning docs + NFL prediction domain knowledge
def suggest_params(trial):
    return {
        "max_depth": trial.suggest_int("max_depth", 2, 6),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
        "min_child_weight": trial.suggest_int("min_child_weight", 3, 10),
        "subsample": trial.suggest_float("subsample", 0.6, 0.9),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 0.8),
        "reg_alpha": trial.suggest_float("reg_alpha", 0.1, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 20.0, log=True),
        "gamma": trial.suggest_float("gamma", 0.0, 5.0),
        "n_estimators": 500,
        "early_stopping_rounds": 50,
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| XGBoost pickle serialization | JSON native `save_model` | XGBoost 1.0+ | Forward-compatible model files |
| Manual grid search | Optuna TPE Bayesian optimization | Optuna 2.0+ | 3-5x more efficient exploration |
| Feature imputation for trees | Native NaN handling | XGBoost 1.0+ | Better performance, less code |
| XGBoost 3.x | XGBoost 2.1.4 | 2026 (3.x dropped Python 3.9) | Must pin <3.0 for this project |

**Deprecated/outdated:**
- `xgb.DMatrix` is still supported but `XGBRegressor` sklearn API is simpler for this use case
- `pickle.dump(model)` for XGBoost models -- officially discouraged; use `save_model()`

## Data Inventory (Verified)

### Silver Team Sources (8 paths, all with 2016-2025 data)
| Source | Rows/Season | Columns | Key Features |
|--------|------------|---------|--------------|
| pbp_metrics | 544 (32x17) | 63 | EPA, CPOE, success rate, red zone (incl. roll3/roll6) |
| tendencies | 544 | 23 | Pace, PROE, 4th-down rate, early-down run rate |
| sos | 544 | 21 | Offensive/defensive SOS ranks |
| situational | 544 | 51 | Home/away/div/leading/trailing splits |
| pbp_derived | 544 | 164 | Penalties, turnovers, FG, drives, explosives |
| game_context | 570 | 22 | Weather, rest, travel, coaching (has game_id, is_home) |
| referee_tendencies | 570 | 4 | Ref penalty rates |
| playoff_context | 544 | 10 | Wins, losses, win_pct, standings |

### Bronze Schedules (Labels)
| Field | Coverage | Convention |
|-------|----------|------------|
| spread_line | 100% non-null for 2016-2024 | Positive = home favored |
| total_line | 100% non-null | Expected total points |
| home_score | 100% non-null | Final score |
| away_score | 100% non-null | Final score |
| result | 100% non-null | home_score - away_score |
| game_type | REG + playoffs | Filter to REG only for training |

### Training Data Size
| Seasons | Games (REG) |
|---------|-------------|
| 2016-2018 | 768 |
| 2016-2019 | 1,024 |
| 2016-2020 | 1,280 |
| 2016-2021 | 1,552 |
| 2016-2022 | 1,823 |
| 2016-2023 | 2,095 |
| 2024 (holdout) | 272 |
| Total | 2,367 |

## Discretion Recommendations

For areas marked as Claude's discretion, these are the research-backed recommendations:

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| D-02: Module placement | New `src/feature_engineering.py` | Separate concern from existing analytics; follows project pattern of one module per domain |
| D-03: NaN handling | Let XGBoost handle NaN natively; fill only wins/losses with 0 | XGBoost learns optimal split direction for missing values; avoids injecting artificial signal |
| D-04: Feature selection | Curated ~100-120 differential features (not all 300+) | 7:1 sample-to-feature ratio with all features; ~20:1 with curated set reduces overfitting |
| D-08: Fold count | 5 folds (validate 2019-2023) | Balances minimum training size (~768 games in fold 1) with enough validation signal |
| D-12: Model format | JSON native (`model.save_model('model.json')`) | Forward-compatible, human-readable, officially recommended over pickle |
| D-13: Optuna metric | MAE (minimize) | More robust to outliers than RMSE; aligns with spread prediction where a few blowouts shouldn't dominate |
| D-16: CLI flags | `--target spread\|total`, `--trials 50`, `--no-tune` (skip Optuna, use defaults), `--seasons` | Minimum viable CLI with escape hatch for quick runs |
| D-17: Model directory | `models/` at project root | Separate from data/ (models are code artifacts, not data); add to .gitignore |
| D-18: Feature importance | Console output + CSV file in model directory | Dual output: immediate visibility + downstream use |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.1 |
| Config file | None (uses defaults, existing pattern) |
| Quick run command | `python -m pytest tests/test_feature_engineering.py tests/test_model_training.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FEAT-01 | Differential features computed correctly | unit | `pytest tests/test_feature_engineering.py::test_differential_features -x` | Wave 0 |
| FEAT-02 | Temporal lag verified (no future data) | unit | `pytest tests/test_feature_engineering.py::test_temporal_lag -x` | Wave 0 |
| FEAT-03 | Feature importance report generated | integration | `pytest tests/test_model_training.py::test_feature_importance -x` | Wave 0 |
| FEAT-04 | Early-season NaN handling | unit | `pytest tests/test_feature_engineering.py::test_early_season_nan -x` | Wave 0 |
| MODL-01 | Spread model trains and produces predictions | integration | `pytest tests/test_model_training.py::test_spread_model -x` | Wave 0 |
| MODL-02 | Total model trains and produces predictions | integration | `pytest tests/test_model_training.py::test_total_model -x` | Wave 0 |
| MODL-03 | Walk-forward CV produces fold-level scores | unit | `pytest tests/test_model_training.py::test_walk_forward_cv -x` | Wave 0 |
| MODL-04 | Optuna tuning runs and returns best params | integration | `pytest tests/test_model_training.py::test_optuna_tuning -x` | Wave 0 |
| MODL-05 | Conservative defaults produce valid model | unit | `pytest tests/test_model_training.py::test_conservative_defaults -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_feature_engineering.py tests/test_model_training.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_feature_engineering.py` -- covers FEAT-01, FEAT-02, FEAT-04
- [ ] `tests/test_model_training.py` -- covers MODL-01 through MODL-05, FEAT-03
- [ ] Package installation: `pip install "xgboost>=2.1.4,<3.0" optuna scikit-learn`
- [ ] `models/` directory creation
- [ ] Add `models/` to `.gitignore`

## Open Questions

1. **Spread line: closing vs opening?**
   - What we know: `spread_line` is populated for all games, positive = home favored
   - What's unclear: Whether nfl-data-py provides closing lines or opening lines (STATE.md blocker)
   - Recommendation: Proceed with available data; verify during backtesting (Phase 26). nfl-data-py typically provides closing lines from nflverse.

2. **Optimal feature count for ~2,300 games**
   - What we know: 337 Silver columns produce ~180 differentials after removing non-numeric. Literature suggests 10-20:1 sample-to-feature ratio for tree models.
   - What's unclear: Exact optimal count for NFL spread prediction.
   - Recommendation: Start with ~100-120 curated features. Use XGBoost feature importance from fold 5 to identify top features. Can iterate in Phase 26.

3. **Situational splits as features**
   - What we know: Situational Silver has 51 columns with split_type (home/away/divisional/etc.) making it a wide format per team.
   - What's unclear: Whether to include all splits or just the contextually relevant one (e.g., home split for home team).
   - Recommendation: Include only the overall and home/away splits to keep feature count manageable.

## Sources

### Primary (HIGH confidence)
- Local data exploration -- verified all 8 Silver sources, schedules Bronze schema, game counts, spread_line convention
- [XGBoost 2.1.4 PyPI](https://pypi.org/project/xgboost/2.1.4/) -- Python >= 3.8 requirement confirmed
- [Optuna 4.8.0 PyPI](https://pypi.org/project/optuna/) -- Python >= 3.9 requirement confirmed
- [XGBoost Model IO docs](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html) -- JSON serialization recommendation
- [XGBoost parameter tuning docs](https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html) -- Conservative hyperparameter guidance

### Secondary (MEDIUM confidence)
- [NFL prediction with XGBoost achieving 64.8% accuracy](https://medium.com/@dgentile_10367/predicting-nfl-game-outcomes-with-machine-learning-c3889d305f5c) -- Comparable project, similar feature engineering approach
- [XGBoost parameters docs](https://xgboost.readthedocs.io/en/stable/parameter.html) -- Regularization parameter reference
- [Optuna XGBoost integration](https://forecastegy.com/posts/xgboost-hyperparameter-tuning-with-optuna/) -- TPE sampler and pruning callback patterns

### Tertiary (LOW confidence)
- Spread line closing vs opening convention -- assumed closing based on nflverse standard practice, needs verification in Phase 26

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- verified versions, Python 3.9 compatibility confirmed from PyPI
- Architecture: HIGH -- data schema verified from actual parquet files on disk
- Pitfalls: HIGH -- data-driven (game counts, column counts, spread convention all verified)
- Discretion recommendations: MEDIUM -- based on domain knowledge + data characteristics

**Research date:** 2026-03-20
**Valid until:** 2026-04-20 (stable libraries, local data)
