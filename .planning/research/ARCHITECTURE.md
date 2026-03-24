# Architecture Research

**Domain:** v2.0 NFL Game Prediction Improvement — player-level features, model ensembles, feature selection, advanced signals
**Researched:** 2026-03-24
**Confidence:** HIGH (based on direct codebase inspection of all existing prediction modules, Silver data inventory, and ML best practices research)

---

## What Changed in v1.4 (Existing Baseline)

v1.4 shipped a clean, working prediction system. Before describing what v2.0 needs, the existing components must be understood precisely, because v2.0 must integrate without breaking them.

**Existing modules (do not rewrite these):**

| Module | Purpose | Key Interface |
|--------|---------|---------------|
| `src/feature_engineering.py` | Assembles game-level diff features from 8 Silver team sources | `assemble_game_features(season)`, `assemble_multiyear_features()`, `get_feature_columns(game_df)` |
| `src/model_training.py` | Walk-forward CV + XGBoost train/save/load | `walk_forward_cv()`, `train_final_model()`, `load_model()` |
| `src/prediction_backtester.py` | ATS/O-U evaluation + vig-adjusted profit | `evaluate_ats()`, `evaluate_ou()`, `compute_profit()` |
| `scripts/train_prediction_model.py` | End-to-end training CLI with Optuna | CLI entrypoint |
| `scripts/generate_predictions.py` | Weekly predictions with edge detection | CLI entrypoint |
| `src/config.py` | `SILVER_TEAM_LOCAL_DIRS`, `CONSERVATIVE_PARAMS`, `LABEL_COLUMNS`, `MODEL_DIR` | Constants shared by all above |

**The data flow as of v1.4:**

```
Bronze schedules (labels: scores, spread_line, total_line)
    |
    v
Silver (8 team paths joined on [team, season, week])
    |
    v
feature_engineering.py → assemble_game_features(season)
    - game_context as base (has game_id + is_home)
    - left-join pbp_metrics, tendencies, sos, situational, pbp_derived,
      referee_tendencies, playoff_context on [team, season, week]
    - split into home/away; join on game_id
    - compute diff_{col} = home_col - away_col for all rolling/context cols
    - join Bronze schedules for labels
    - get_feature_columns() filters to pre-game knowable only
    → 283 features, ~2,100 training games (2016–2023)
    |
    v
model_training.py → walk_forward_cv() + train_final_model()
    - XGBoost only (spread model + total model)
    - Walk-forward folds: 2019–2023
    - Holdout: 2024 (sealed)
    → models/spread/model.json + models/total/model.json
    |
    v
generate_predictions.py → weekly Gold output
    - data/gold/predictions/season=YYYY/week=WW/*.parquet
```

---

## v2.0 System Overview

Four workstreams, each adding new components that extend (not replace) v1.4.

```
Bronze (unchanged)
    |
    v
Silver — team paths (unchanged)
    |     + players/usage (existing, not yet used in prediction)
    |     + players/advanced (existing NGS/PFR/QBR, not yet used)
    |     + Bronze: player_weekly, depth_charts, injuries (direct reads)
    |
    v
NEW: src/player_feature_engineering.py  ← Workstream 1
    - QB quality index per team per week (EPA/QBR rolling)
    - Starter vs backup detection (depth_charts + injuries)
    - Key injury impact score per team per week
    - Output grain: [team, season, week] — same as Silver team sources
    |
    v
MODIFIED: src/feature_engineering.py    ← Workstream 1 integration point
    - _assemble_team_features(): add player feature source to join loop
    - get_feature_columns(): player feature cols follow same rolling/pre-game rules
    → feature count grows from 283 to ~310–330
    |
    v
NEW: src/feature_selector.py            ← Workstream 2
    - importance-based pruning (XGBoost native importance)
    - correlation filtering (drop one of any pair with r > 0.90)
    - walk-forward-safe selection (fit on train folds only)
    - Output: FeatureSelectionResult with selected_features list
    → feature count reduces from ~310 to ~80–120
    |
    v
MODIFIED: src/model_training.py         ← Workstream 3 integration point
    - walk_forward_cv(): accept model_class param (default: XGBoost)
    - train_final_model(): accept model_class param
    - Both remain backward-compatible (default = current XGBoost path)
    |
    v
NEW: src/ensemble_model.py              ← Workstream 3
    - GradientBoostingEnsemble: XGBoost + LightGBM + CatBoost base learners
    - Ridge meta-learner (sklearn Ridge, not another gradient booster)
    - walk_forward_stacking_cv(): OOF predictions for meta-learner training
    - train_ensemble(): train all base models + meta-learner, save artifacts
    - predict_ensemble(): run all base models, feed to meta-learner
    - Output: same interface as model_training.py (model artifacts in models/)
    |
    v
NEW: src/advanced_features.py           ← Workstream 4
    - adaptive_rolling_windows(): weight recent games more (exponential decay)
    - momentum_score(): trend over last 3/5 games vs season mean
    - regime_detection(): clustering-based era classifier (pre/post rule change)
    - All outputs at [team, season, week] grain for feature_engineering join
    |
    v
MODIFIED: scripts/train_prediction_model.py  ← CLI extension
    - Add --ensemble flag (uses ensemble_model.py path)
    - Add --feature-selection flag (uses feature_selector.py)
    - Add --advanced-features flag (uses advanced_features.py)
    - Default: current XGBoost-only path (no regression)
    |
    v
MODIFIED: scripts/generate_predictions.py   ← CLI extension
    - Auto-detect model type from metadata.json (ensemble vs single)
    - Use predict_ensemble() or load_model() accordingly
    - No change to output format or Gold Parquet schema
    |
    v
Gold predictions (same schema as v1.4)
    data/gold/predictions/season=YYYY/week=WW/*.parquet
```

---

## Component Boundaries

### New Components

| Component | File | Responsibility | Input | Output |
|-----------|------|---------------|-------|--------|
| Player Feature Engineering | `src/player_feature_engineering.py` | QB quality index, injury replacement quality, starter/backup detection | Bronze player_weekly, depth_charts, injuries; Silver players/advanced | DataFrame at [team, season, week] grain |
| Feature Selector | `src/feature_selector.py` | Importance + correlation pruning; walk-forward-safe | `game_df` from `assemble_game_features()`, target column | `FeatureSelectionResult` with selected feature list + metadata |
| Ensemble Model | `src/ensemble_model.py` | Three base learners + Ridge meta-learner; OOF training; save/load | Game-level feature DataFrame, target column | Trained ensemble artifacts in `models/ensemble/` |
| Advanced Features | `src/advanced_features.py` | Adaptive rolling windows, momentum scores, regime flags | Silver team DataFrames at [team, season, week] | Additional feature columns at [team, season, week] grain |

### Modified Components (Minimal Surgery)

| Component | File | Change | Why Minimal |
|-----------|------|--------|-------------|
| Team feature assembly | `src/feature_engineering.py` | Add player features source to `_assemble_team_features()` join loop; update `get_feature_columns()` to accept new rolling columns | The join loop already handles arbitrary sources from `SILVER_TEAM_LOCAL_DIRS`-style iteration |
| Model training | `src/model_training.py` | Add optional `model_class` param to `walk_forward_cv()` and `train_final_model()`; default keeps XGBoost | Existing callers (scripts, tests) pass no `model_class` → unchanged behavior |
| Training CLI | `scripts/train_prediction_model.py` | Add `--ensemble`, `--feature-selection`, `--advanced-features` flags; each flag routes to corresponding new module | Flags are additive; default path is identical to v1.4 |
| Prediction CLI | `scripts/generate_predictions.py` | Read `metadata.json["model_type"]` to dispatch to single-model or ensemble inference | Existing model artifacts have no `model_type` key → defaults to current single-model path |
| Config | `src/config.py` | Add `SILVER_PLAYER_LOCAL_DIRS` for new player feature paths; add `ENSEMBLE_MODEL_DIR`; add `FEATURE_SELECTION_PARAMS` | Additive constants; nothing removed |

### Unchanged Components (Must Not Be Modified)

| Component | Reason to Leave Alone |
|-----------|----------------------|
| `src/prediction_backtester.py` | Operates on prediction DataFrames only; model type is irrelevant |
| `scripts/backtest_predictions.py` | CLI wrapper for backtester; no model-type dependency |
| All Silver transformation modules | Silver layer is general-purpose; ML-specific transforms stay in Gold |
| Bronze ingestion scripts | No new data types needed; player_weekly, depth_charts, injuries already ingested |
| Fantasy projection pipeline | Entirely separate Gold path; shares Bronze/Silver but nothing in prediction stack |

---

## Data Flow: Workstream 1 (Player Features)

This is the highest-value workstream with the cleanest integration path.

```
INPUT SOURCES (all already ingested in Bronze)
    Bronze: player_weekly → data/bronze/player_weekly/season=YYYY/week=WW/
    Bronze: depth_charts  → data/bronze/depth_charts/season=YYYY/week=WW/
    Bronze: injuries      → data/bronze/injuries/season=YYYY/week=WW/
    Silver: players/advanced → data/silver/players/advanced/season=YYYY/

PLAYER FEATURE ENGINEERING (new module)
    player_feature_engineering.py::build_qb_quality_index(season, week)
        1. Read player_weekly: filter to QB position, current season
        2. Compute rolling EPA per dropback (roll3, roll6 using shift(1) lag)
        3. Join Silver players/advanced for QBR rolling windows
        4. Aggregate to [team, season, week]: starter QB metrics only
           (starter = highest snap count QB per team per week)
        5. Output: qb_epa_roll3, qb_epa_roll6, qb_qbr_roll3 per team-week

    player_feature_engineering.py::build_injury_impact(season, week)
        1. Read injuries: filter to Q/D/Out/IR status this week
        2. Read depth_charts: position rank for each player
        3. Join player_weekly: snap_pct for injured players (from prior week)
        4. Weight injury impact by position importance × snap share
           (QB: weight 3.0, RB: 1.0, WR: 0.8, OL: 1.5, DL/LB/DB: 0.6)
        5. Aggregate to [team, season, week]: injury_impact_offense, injury_impact_defense
        6. Apply shift(1) lag: week N game uses week N-1 injury report

OUTPUT GRAIN: [team, season, week] — identical to existing Silver team sources

INTEGRATION POINT IN feature_engineering.py:
    _assemble_team_features(season):
        for name, subdir in SILVER_TEAM_SOURCES.items():
            ...  # existing joins

        # NEW: add player features as additional source
        player_features = build_game_week_player_features(season)
        if not player_features.empty:
            base = base.merge(player_features, on=["team", "season", "week"], how="left")
```

**Key constraint:** All player features must be at [team, season, week] grain. No per-player columns flow into the game-level feature matrix. The QB quality index collapses the QB's week-N-1 EPA/QBR into a single team-level scalar. This avoids combinatorial explosion and keeps the existing diff_ differential pipeline working without modification.

---

## Data Flow: Workstream 2 (Feature Selection)

Feature selection must be walk-forward-safe: the selected feature set must be determined using only training data from each fold.

```
CURRENT STATE: 283 features (post-leakage fix)
AFTER PLAYER FEATURES: ~310–330 features
TARGET AFTER SELECTION: 80–120 features

FEATURE SELECTION PIPELINE (src/feature_selector.py)

Step 1: Correlation filter (cheap, model-agnostic)
    - Build correlation matrix on training set only
    - For any pair with |r| > 0.90:
        keep the feature with higher XGBoost importance
        (importance computed on training set with fast fit)
    - Eliminates highly redundant diff_ pairs
      (e.g., diff_off_epa_roll3 and diff_off_epa_roll6 are often r > 0.85)

Step 2: Importance threshold (XGBoost gain importance)
    - Train a lightweight XGBoost (n_estimators=100, fast) on training set
    - Keep features with gain importance > threshold
      (threshold = importance_cutoff_pct * max_importance, default 0.5%)
    - Eliminates near-zero-importance features

Step 3: Permutation importance validation (optional, expensive)
    - Run permutation importance on validation fold
    - Drop features where permutation drop < noise threshold
    - Recommended for final model only, not in CV loop

OUTPUT: FeatureSelectionResult
    - selected_features: List[str]
    - removed_by_correlation: List[str]
    - removed_by_importance: List[str]
    - importance_scores: Dict[str, float]
    - selection_season: int (which training period was used)

WALK-FORWARD INTEGRATION:
    - Feature selection runs inside each walk_forward_cv fold
    - Selection uses train data only; validation fold uses selected features
    - Final model: selection on all training seasons (2016–2023)
    - Holdout (2024): features fixed at selection from training period

CRITICAL: Do not reuse the same FeatureSelectionResult across folds.
Each fold selects independently on its own training window.
(Slight feature set variation across folds is acceptable and honest.)
```

---

## Data Flow: Workstream 3 (Ensemble)

The ensemble extends model_training.py without replacing it. The key architectural decision is **out-of-fold (OOF) stacking**, not simple averaging.

```
ENSEMBLE ARCHITECTURE (src/ensemble_model.py)

Base learners (layer 1):
    - XGBoost 2.1.4 (existing, already tuned)
    - LightGBM 4.6.0 (faster, handles categorical differently)
    - CatBoost 1.2.7 (handles missing values natively, less tuning needed)
    Note: All three use the same feature set from feature_selector.py

Meta-learner (layer 2):
    - sklearn Ridge (alpha=1.0)
    - Input: [xgb_pred, lgb_pred, cat_pred] (3 features)
    - Output: final spread or total prediction
    - Ridge is correct here: no nonlinear combination needed at meta-level;
      overfitting risk is high with only ~2,100 training games

OOF STACKING PROCEDURE (walk_forward_stacking_cv):
    For each walk-forward fold (train_seasons, val_season):
        1. Train XGB, LGB, CAT on train_seasons
        2. Predict on val_season → [xgb_oof, lgb_oof, cat_oof]
        3. Stack OOF predictions as meta-features
    After all folds:
        Train Ridge meta-learner on stacked OOF predictions
        (target: actual_margin or actual_total)

FINAL ENSEMBLE TRAINING (train_ensemble):
    1. Run OOF stacking to train meta-learner
    2. Retrain XGB, LGB, CAT on all training data (2016–2023)
    3. Save artifacts:
        models/ensemble/
            xgb/model.json + metadata.json
            lgb/model.txt + metadata.json
            cat/model.cbm + metadata.json
            meta/ridge_meta.joblib + metadata.json
            ensemble_metadata.json (lists component models + versions)

PREDICTION (predict_ensemble):
    1. Load all 4 model artifacts
    2. Run each base model: xgb_pred, lgb_pred, cat_pred
    3. Stack: meta_input = [[xgb_pred, lgb_pred, cat_pred], ...]
    4. Ridge.predict(meta_input) → final prediction
    5. Return predictions in same format as single-model predict()

BACKWARD COMPATIBILITY:
    - generate_predictions.py reads metadata.json["model_type"]
    - "xgboost" → existing load_model() path (unchanged)
    - "ensemble" → new predict_ensemble() path
    - Existing model artifacts have no "model_type" key → default "xgboost"
```

---

## Data Flow: Workstream 4 (Advanced Features)

Advanced features are additional columns produced at [team, season, week] grain and injected into the feature_engineering.py join loop alongside player features.

```
ADVANCED FEATURES (src/advanced_features.py)

Feature 1: Exponential decay rolling windows
    - Alternative to uniform roll3/roll6 with recency weighting
    - half_life = 3 weeks → games from 3 weeks ago count at 50%
    - Output columns: {metric}_ewm3, {metric}_ewm6
    - Source: Silver team DataFrames (same as existing roll3/roll6)
    - Note: Do not replace roll3/roll6; add as additional features.
      Feature selector will determine which is more predictive.

Feature 2: Momentum score
    - Captures "team trending up/down" beyond recent averages
    - momentum_{metric} = (roll3_{metric} - roll8_{metric}) / std_{metric}
    - Positive = performing above season average recently
    - Output at [team, season, week] grain

Feature 3: Regime detection (LOW priority, implement last)
    - Cluster seasons into "eras" based on league-wide offensive pace
    - One-hot encode which era a game belongs to
    - Allows model to learn that 2018 passing volume differs from 2024
    - Implementation: KMeans on league-wide EPA/play per season
    - Output: regime_id (integer) per season (not week-varying)

INTEGRATION: Same pattern as player features
    advanced_df = build_advanced_features(season)
    base = base.merge(advanced_df, on=["team", "season", "week"], how="left")
```

---

## Build Order (Dependency-Driven)

The four workstreams have dependencies. This order minimizes rework.

```
Phase 1: Player Feature Engineering
    NEW: src/player_feature_engineering.py
        - build_qb_quality_index(season) → [team, season, week] DataFrame
        - build_injury_impact(season) → [team, season, week] DataFrame
        - build_game_week_player_features(season) → merged DataFrame
    MODIFY: src/feature_engineering.py
        - _assemble_team_features(): add player features join
        - get_feature_columns(): accept new rolling player columns
    MODIFY: src/config.py
        - PLAYER_FEATURE_LOCAL_DIR = "teams/player_features"
    NEW: tests/test_player_feature_engineering.py
    Rationale: Foundational — more features before selection/ensemble.
    Risk: Leakage in injury data (same-week injuries must be excluded).

Phase 2: Feature Selection
    NEW: src/feature_selector.py
        - FeatureSelectionResult dataclass
        - select_features(game_df, target_col, train_seasons) → FeatureSelectionResult
        - correlation_filter(df, feature_cols, threshold=0.90) → List[str]
        - importance_filter(df, feature_cols, target_col, cutoff=0.005) → List[str]
    MODIFY: src/model_training.py
        - walk_forward_cv(): optional feature_selector param
        - train_final_model(): optional feature_selector param
    NEW: tests/test_feature_selector.py
    Rationale: Reduce noise before ensemble — base learners should train on clean features.
    Dependency: Phase 1 (need full feature set to select from).

Phase 3: Model Ensemble
    NEW: src/ensemble_model.py
        - GradientBoostingEnsemble class
        - walk_forward_stacking_cv() → OOF predictions + meta-learner
        - train_ensemble() → save all artifacts
        - predict_ensemble() → Ridge(XGB, LGB, CAT predictions)
    MODIFY: src/model_training.py
        - walk_forward_cv(): accept optional model_class param
        - train_final_model(): accept optional model_class param
    MODIFY: scripts/train_prediction_model.py
        - Add --ensemble flag
    MODIFY: scripts/generate_predictions.py
        - Add model_type dispatch from metadata.json
    MODIFY: src/config.py
        - ENSEMBLE_MODEL_DIR
        - LIGHTGBM_PARAMS (conservative defaults)
        - CATBOOST_PARAMS (conservative defaults)
    NEW: tests/test_ensemble_model.py
    Rationale: Only add ensemble complexity after feature set is clean.
    Dependency: Phase 2 (feature selection must be stable before ensemble training).

Phase 4: Advanced Features (Optional Workstream)
    NEW: src/advanced_features.py
        - build_ewm_features(team_df) → EWM rolling columns
        - build_momentum_features(team_df) → momentum score columns
        - build_regime_features(all_seasons_df) → regime_id column
    MODIFY: src/feature_engineering.py
        - _assemble_team_features(): add advanced features join
    NEW: tests/test_advanced_features.py
    Rationale: Lower expected gain than Phases 1–3; implement after validating ensemble.
    Dependency: Phase 3 (want clean ensemble baseline before adding more features).
```

**Phase ordering rationale:**
- Player features first: more signal before pruning is more productive than less signal before pruning.
- Feature selection second: clean input improves all three ensemble models equally.
- Ensemble third: stacking requires stable features to avoid overfitting the meta-learner.
- Advanced features last: highest uncertainty, lowest dependency, most experimental.

---

## Integration Points: Explicit New vs Modified

### New Files

| File | What It Does |
|------|-------------|
| `src/player_feature_engineering.py` | QB quality index + injury impact at [team, season, week] grain |
| `src/feature_selector.py` | Walk-forward-safe importance + correlation feature pruning |
| `src/ensemble_model.py` | XGB + LGB + CatBoost base learners + Ridge meta-learner |
| `src/advanced_features.py` | EWM rolling windows, momentum scores, regime flags |
| `tests/test_player_feature_engineering.py` | Unit tests for player feature module |
| `tests/test_feature_selector.py` | Unit tests for feature selection |
| `tests/test_ensemble_model.py` | Unit tests for ensemble (synthetic data) |
| `tests/test_advanced_features.py` | Unit tests for advanced features |

### Modified Files (with specific change description)

| File | Change | Backward Compatible? |
|------|--------|---------------------|
| `src/feature_engineering.py` | `_assemble_team_features()`: call `build_game_week_player_features()` and merge on [team, season, week] if module available; `get_feature_columns()`: no change needed (existing `_is_rolling()` check already accepts new rolling columns) | Yes — player features are left-joined (NaN fill if absent) |
| `src/model_training.py` | `walk_forward_cv(model_class=None)`: if None, use XGBRegressor as before; `train_final_model(model_class=None)`: same | Yes — default None preserves existing behavior |
| `scripts/train_prediction_model.py` | Add `--ensemble` flag (routes to `train_ensemble()`), `--feature-selection` flag (runs `select_features()` before train), `--advanced-features` flag (builds advanced features before assembly) | Yes — no flags = current v1.4 behavior |
| `scripts/generate_predictions.py` | After `load_model()`, check `metadata["model_type"]`; dispatch to `predict_ensemble()` if "ensemble"; else existing predict path | Yes — existing model.json has no "model_type" key → falls through to current path |
| `src/config.py` | Add `PLAYER_FEATURE_LOCAL_DIR`, `ENSEMBLE_MODEL_DIR`, `LIGHTGBM_PARAMS`, `CATBOOST_PARAMS`, `FEATURE_SELECTION_PARAMS` | Yes — additive constants only |

### Unchanged Files

| File | Why Unchanged |
|------|--------------|
| `src/prediction_backtester.py` | Takes prediction DataFrames as input; model type is invisible to it |
| `scripts/backtest_predictions.py` | CLI wrapper for backtester; no model dependency |
| All Silver transformation modules | Silver is general-purpose; stays decoupled from ML pipeline |
| Fantasy projection pipeline | Entirely separate Gold output path |
| Bronze ingestion scripts | All needed data types already ingested |

---

## Leakage Rules for New Features

The v1.4 leakage fix committed a specific rule in `get_feature_columns()`: only rolling stats and pre-game context are allowed as features. New components must follow the same rule.

**Player features (must follow):**
- QB quality index uses roll3/roll6 with shift(1): week N game uses week N-1 rolling QB EPA. Correct.
- Injury impact uses week N-1 injury report (pre-game information available before kickoff). Correct.
- Do NOT use same-week player_weekly stats (e.g., this game's QB EPA). This is leakage.
- Depth chart position must use the depth chart filed BEFORE the game week, not the updated post-week depth chart.

**Advanced features (must follow):**
- EWM windows use the same shift(1) pattern as existing roll3/roll6. Correct.
- Regime IDs are season-level (no week variation). Correct.
- Momentum scores use only prior-week data. Correct.

**Feature selection (must follow):**
- Correlation filter and importance filter must run on training data only within each fold.
- The selected feature list must never be informed by validation fold data.

---

## Model Artifact Storage

```
models/
    spread/                           ← existing v1.4 XGBoost
        model.json
        metadata.json                 ← add "model_type": "xgboost"
    total/                            ← existing v1.4 XGBoost
        model.json
        metadata.json
    ensemble/                         ← NEW v2.0
        spread/
            xgb/model.json
            lgb/model.txt
            cat/model.cbm
            meta/ridge_meta.joblib
            ensemble_metadata.json    ← lists component models, model_type: "ensemble"
        total/
            xgb/model.json
            lgb/model.txt
            cat/model.cbm
            meta/ridge_meta.joblib
            ensemble_metadata.json
```

The `ensemble_metadata.json` sidecar contains: `model_type`, `component_models`, `feature_names`, `training_seasons`, `cv_scores`, `trained_at`. The prediction CLI reads `model_type` from this file to dispatch correctly.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Per-Player Columns in the Feature Matrix

**What:** Adding individual player stats as separate columns (e.g., `mahomes_epa`, `kelce_targets`).
**Why bad:** Creates column explosion (53 roster spots × 2 teams), extreme sparsity, and requires dynamic column naming that breaks the fixed feature schema between training and inference.
**Instead:** Aggregate to team-week scalars only. QB quality index = one float per team per week. Injury impact = one float per team per week. The feature matrix schema must be fixed at training time.

### Anti-Pattern 2: Fitting Feature Selection on the Full Dataset

**What:** Running `select_features()` on all seasons, then using the result in walk-forward CV.
**Why bad:** The feature selector has seen validation and holdout data, creating indirect leakage. Even importance scores computed on 2024 data influence which features the 2020-fold model uses.
**Instead:** Feature selection must run inside each walk-forward fold, using only the training seasons for that fold. The final model's feature selection uses only the training period (2016–2023).

### Anti-Pattern 3: Simple Averaging as the Meta-Learner

**What:** `final_pred = (xgb_pred + lgb_pred + cat_pred) / 3`.
**Why bad:** Equal weighting ignores that models may have different accuracy on different game types. Ridge regression learned from OOF predictions will find the correct weights automatically and suppress a base model that adds no value.
**Instead:** Ridge meta-learner trained on out-of-fold predictions. Ridge is preferred over another gradient booster at the meta level because the meta-input has only 3 features and 2,100 samples — a linear model is correct here.

### Anti-Pattern 4: Replacing XGBoost v1.4 Model Artifacts

**What:** Retraining and overwriting `models/spread/model.json` with new code during v2.0 development.
**Why bad:** The v1.4 model is the validated baseline. If v2.0 training has a bug, the production model is gone.
**Instead:** Ensemble artifacts go in `models/ensemble/`; single-model retrains with new features go in `models/spread_v2/`. Keep v1.4 artifacts in `models/spread/` as the fallback until v2.0 is validated against the holdout.

### Anti-Pattern 5: Adding CatBoost Without Pinning Its Version

**What:** `pip install catboost` without specifying a version.
**Why bad:** CatBoost's Python API has changed across versions. CatBoost 1.2.x supports Python 3.9; CatBoost 1.3+ requires 3.10+.
**Instead:** Pin `catboost==1.2.7` in requirements.txt (last release in the 1.2.x line, Python 3.9 compatible).

### Anti-Pattern 6: Running Feature Selection Inside assemble_game_features()

**What:** Filtering feature columns inside `feature_engineering.py` based on importance.
**Why bad:** Feature assembly is a data pipeline function; feature selection is a modeling decision. Mixing them means you cannot run the assembly pipeline without a trained model, and you cannot re-run feature selection without re-running assembly.
**Instead:** `assemble_game_features()` returns all features. `select_features()` is called separately in the training script. The selected feature list is passed to `walk_forward_cv()` and `train_final_model()`.

---

## Scalability Considerations

| Concern | v1.4 Baseline | v2.0 (player features + ensemble) | Notes |
|---------|--------------|----------------------------------|-------|
| Feature assembly time | <5 sec/season | +2–5 sec/season (player feature joins) | Still fast; Bronze parquet reads are cheap |
| Training time (single model) | ~30 sec | ~30 sec + feature selection ~10 sec | Feature selection adds modest overhead |
| Training time (ensemble) | N/A | ~90 sec (3 base models × 30 sec) | All three train in sequence; could parallelize later |
| Memory peak | <500 MB | <700 MB (additional Bronze reads) | Still well within single-machine limits |
| Walk-forward CV time | ~2 min (5 folds × 30 sec) | ~8 min with ensemble (5 folds × 3 models × 30 sec) | Acceptable for offline training |
| Inference time (weekly) | <1 sec | <2 sec (3 base models + Ridge) | Trivial |
| Test suite | 439 tests | Target: +30–40 tests | 4 new test files |

---

## Sources

- Direct inspection of `src/feature_engineering.py`, `src/model_training.py`, `src/prediction_backtester.py`, `scripts/generate_predictions.py`, `src/config.py`
- `.planning/PROJECT.md` — v2.0 milestone goals, baseline metrics, target metrics
- [Stacking Ensembles: XGBoost + LightGBM + CatBoost (Medium)](https://medium.com/@stevechesa/stacking-ensembles-combining-xgboost-lightgbm-and-catboost-to-improve-model-performance-d4247d092c2e) — OOF stacking architecture
- [scikit-learn StackingRegressor docs](https://scikit-learn.org/stable/modules/ensemble.html) — meta-learner patterns
- [Permutation Importance (scikit-learn)](https://scikit-learn.org/stable/modules/permutation_importance.html) — correlated feature handling caveats
- [Feature Importance in Gradient Boosting Trees with CV Feature Selection (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9140774/) — walk-forward-safe selection pattern
- [NFL Advanced Metrics (Covers.com)](https://www.covers.com/nfl/key-advanced-metrics-betting-tips) — EPA/CPOE as core QB quality signals
- `data/silver/` directory inspection — confirmed players/usage and players/advanced data available 2020–2025; teams/* available 2016–2025

---
*Architecture research for: v2.0 NFL Game Prediction Model Improvement*
*Researched: 2026-03-24*
