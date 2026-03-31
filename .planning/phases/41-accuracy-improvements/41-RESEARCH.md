# Phase 41: Accuracy Improvements - Research

**Researched:** 2026-03-30
**Domain:** Per-position player fantasy prediction accuracy (feature engineering + ensemble stacking)
**Confidence:** HIGH

## Summary

Phase 41 targets the three SKIP positions (RB, WR, TE) from Phase 40's ship gate, where ML models overfit to holdout but failed OOF dual agreement (OOF regressions of -12% to -14%). The core problem is not model capacity but feature signal — the existing rolling averages do not decompose opportunity from efficiency, TD predictions use raw rolling averages rather than expected TD rates, and there is no role momentum signal.

The implementation follows two sequential stages per CONTEXT.md D-09: (1) add ~17 derived features (efficiency, TD regression, role momentum) to the feature vector and re-run the ship gate, then (2) if positions remain SKIP, add XGB+LGB+Ridge ensemble stacking per stat per position and re-run. Both stages reuse the existing ship gate infrastructure from Phase 40 without modification.

**Primary recommendation:** Add all new features in `player_feature_engineering.py` as post-join derived columns (not in Silver), re-run SHAP feature selection to let the model decide what matters, then evaluate with the existing ship gate. Only proceed to ensemble stacking for positions that remain SKIP after features-only evaluation.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Target all 3 SKIP positions (RB, WR, TE) equally — OOF gaps are similar (-12% to -14%)
- **D-02:** Same ship gate as Phase 40: dual agreement (OOF + holdout both 4%+), per-position fantasy points MAE in half-PPR
- **D-03:** QB left as-is — Phase 40 model (75% holdout improvement) is final, not re-evaluated
- **D-04:** Per-position verdict: ship what passes, heuristic fallback for the rest. Phase succeeds if at least one more position flips from SKIP to SHIP
- **D-05:** Derived feature approach (not two-stage pipeline) — add efficiency metrics as model inputs to existing single-stage models. No error compounding from chained predictions
- **D-06:** Efficiency features with roll3 and roll6 variants (~12 per position)
- **D-07:** Two red zone expected TD features (position-average and player-specific)
- **D-08:** Three subtraction features (snap_pct_delta, target_share_delta, carry_share_delta)
- **D-09:** Sequential approach: features first, then ensemble stacking, with ship gate at each stage
- **D-10:** XGB + LGB + Ridge meta-learner per stat per position (no CatBoost)
- **D-11:** Two-stage ablation report
- **D-12:** Conservative LGB params from config.py, Optuna only as escape hatch

### Claude's Discretion
- How to structure the new feature computation (extend player_feature_engineering.py vs separate module)
- Exact position-average RZ TD rates (compute from historical data)
- SHAP re-selection strategy after adding new features (re-run vs append)
- LGB model factory implementation details
- CLI flags for stage selection (features-only vs features+ensemble)

### Deferred Ideas (OUT OF SCOPE)
- Optuna hyperparameter tuning per position
- CatBoost as third base model
- Extending training data to 2016-2019
- Sliding window experiment
- Team-total constraint enforcement (Phase 42)
- Preseason mode (Phase 42)
- MAPIE confidence intervals (Phase 42)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ACCY-01 | Opportunity-efficiency decomposition predicting shares/volume then per-touch efficiency | D-05/D-06: Derived feature approach — efficiency metrics (yards_per_carry, yards_per_target, td_rate, catch_rate) with roll3/roll6 variants added as model inputs. Computed in player_feature_engineering.py using shift(1)->rolling pattern. |
| ACCY-02 | TD regression features using red zone opportunity share x historical conversion rates | D-07: Two features — position-average and player-specific expected TDs from rz_target_share. Requires adding rz_target_share to ROLLING_STAT_COLS or computing rolling in feature assembly. |
| ACCY-03 | Role momentum features (snap share trajectory as breakout/demotion signal) | D-08: Three delta features from existing _roll3 minus _roll6 columns. Pure arithmetic, zero leakage risk. |
| ACCY-04 | Ensemble stacking (XGB+LGB+Ridge) per position if single model leaves accuracy on the table | D-10/D-11: Second stage only if features alone don't flip positions. Adapts existing ensemble patterns from ensemble_training.py (make_lgb_model, train_ridge_meta). |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 2.1.4 (installed) | Base model for per-stat training | Already used in Phase 40 player models |
| lightgbm | 4.5.0 (installed) | Second base model for ensemble diversity | Already used in game-level ensemble, LGB_CONSERVATIVE_PARAMS in config.py |
| scikit-learn | 1.6.1 (installed) | RidgeCV meta-learner for stacking | Already used in ensemble_training.py train_ridge_meta() |
| shap | 0.46.0 (installed) | Feature selection after adding new features | Already used in run_player_feature_selection() |
| pandas | 2.2.3 (installed) | Feature computation and data manipulation | Project standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 1.26.4 (installed) | Numeric operations for efficiency ratios | Division with np.where for safe zero-handling |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| XGB+LGB stacking | XGB+LGB+CB stacking | CatBoost adds training time with no categorical features to exploit; D-10 explicitly excludes it |
| RidgeCV meta-learner | Simple averaging | Ridge learns optimal base model weights per stat; near-zero training cost |
| Derived features in assembly | Two-stage pipeline | D-05 locks this: derived features avoid error compounding from chained predictions |

**Installation:** No new packages required. All dependencies already installed.

## Architecture Patterns

### Recommended Project Structure
```
src/
  player_feature_engineering.py   # Add compute_efficiency_features(), compute_td_regression_features(), compute_momentum_features()
  player_model_training.py        # Extend train_position_models() to accept model_type param (xgb/lgb), add player_ensemble_stacking()
  config.py                       # Add POSITION_AVG_RZ_TD_RATE constants
scripts/
  train_player_models.py          # Add --stage features-only|ensemble CLI flag
models/
  player/
    {position}/                   # Existing XGB models + new LGB models + Ridge meta
    ship_gate_report.json         # Updated with two-stage verdicts
    feature_selection/            # Re-run SHAP selections
```

### Pattern 1: Derived Feature Computation in Assembly
**What:** Compute efficiency/TD regression/momentum features from existing rolling columns during feature assembly, not in Silver.
**When to use:** When new features are pure arithmetic on existing columns and do not need their own persistence layer.
**Example:**
```python
# In player_feature_engineering.py — after all Silver joins complete
def compute_efficiency_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add efficiency ratio features using existing rolling columns.

    Uses shift(1)->rolling pattern columns already in the DataFrame.
    Safe division with np.where to handle zero denominators.
    """
    result = df.copy()

    for window in ["roll3", "roll6"]:
        carries_col = f"carries_{window}"
        rush_yd_col = f"rushing_yards_{window}"
        targets_col = f"targets_{window}"
        rec_yd_col = f"receiving_yards_{window}"
        receptions_col = f"receptions_{window}"
        rush_td_col = f"rushing_tds_{window}"
        rec_td_col = f"receiving_tds_{window}"

        # Yards per carry (RB)
        if carries_col in result.columns and rush_yd_col in result.columns:
            result[f"yards_per_carry_{window}"] = np.where(
                result[carries_col] > 0,
                result[rush_yd_col] / result[carries_col],
                np.nan,
            )

        # Yards per target (WR/TE/RB receiving)
        if targets_col in result.columns and rec_yd_col in result.columns:
            result[f"yards_per_target_{window}"] = np.where(
                result[targets_col] > 0,
                result[rec_yd_col] / result[targets_col],
                np.nan,
            )

        # Yards per reception
        if receptions_col in result.columns and rec_yd_col in result.columns:
            result[f"yards_per_reception_{window}"] = np.where(
                result[receptions_col] > 0,
                result[rec_yd_col] / result[receptions_col],
                np.nan,
            )

        # Catch rate
        if targets_col in result.columns and receptions_col in result.columns:
            result[f"catch_rate_{window}"] = np.where(
                result[targets_col] > 0,
                result[receptions_col] / result[targets_col],
                np.nan,
            )

        # TD rate (rushing TDs per carry)
        if carries_col in result.columns and rush_td_col in result.columns:
            result[f"rush_td_rate_{window}"] = np.where(
                result[carries_col] > 0,
                result[rush_td_col] / result[carries_col],
                np.nan,
            )

        # TD rate (receiving TDs per target)
        if targets_col in result.columns and rec_td_col in result.columns:
            result[f"rec_td_rate_{window}"] = np.where(
                result[targets_col] > 0,
                result[rec_td_col] / result[targets_col],
                np.nan,
            )

    return result
```

### Pattern 2: Player-Level Ensemble Stacking
**What:** XGB + LGB base models per stat, with Ridge meta-learner trained on OOF predictions.
**When to use:** Second stage, only for positions still SKIP after features-only evaluation.
**Example:**
```python
# Adapt player_walk_forward_cv to accept LGB models
def _player_lgb_fit_kwargs(X_train, y_train, X_val, y_val) -> dict:
    """LightGBM fit kwargs: eval_set + early_stopping callback."""
    import lightgbm as lgb
    return {
        "eval_set": [(X_val, y_val)],
        "callbacks": [lgb.early_stopping(50, verbose=False)],
    }

# Build OOF matrix per stat, then Ridge on top
def player_ensemble_stacking(
    pos_data, position, feature_cols_by_group, output_dir
):
    """Train XGB + LGB per stat, stack with Ridge meta-learner."""
    for stat in POSITION_STAT_PROFILE[position]:
        stat_type = get_stat_type(stat)
        feat_cols = feature_cols_by_group[stat_type]

        # XGB walk-forward CV -> OOF predictions
        xgb_wf, xgb_oof = player_walk_forward_cv(
            pos_data, feat_cols, stat,
            lambda: make_xgb_model(get_player_model_params(stat)),
            fit_kwargs_fn=_player_xgb_fit_kwargs,
        )

        # LGB walk-forward CV -> OOF predictions
        lgb_params = _get_lgb_params_for_stat(stat)
        lgb_wf, lgb_oof = player_walk_forward_cv(
            pos_data, feat_cols, stat,
            lambda p=lgb_params: make_lgb_model(p),
            fit_kwargs_fn=_player_lgb_fit_kwargs,
        )

        # Assemble 2-column OOF matrix + Ridge
        oof_matrix = _assemble_player_oof_matrix(xgb_oof, lgb_oof, pos_data, stat)
        ridge = train_player_ridge_meta(oof_matrix)
```

### Pattern 3: Delta Features (Momentum)
**What:** Subtract roll6 from roll3 to get short-term trend signal.
**When to use:** Role momentum detection.
**Example:**
```python
def compute_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add momentum delta features: roll3 - roll6 = recent trend."""
    result = df.copy()
    deltas = {
        "snap_pct_delta": ("snap_pct_roll3", "snap_pct_roll6"),
        "target_share_delta": ("target_share_roll3", "target_share_roll6"),
        "carry_share_delta": ("carry_share_roll3", "carry_share_roll6"),
    }
    for name, (r3, r6) in deltas.items():
        if r3 in result.columns and r6 in result.columns:
            result[name] = result[r3] - result[r6]
    return result
```

### Anti-Patterns to Avoid
- **Two-stage prediction pipeline:** Do NOT predict volume then predict efficiency then multiply. D-05 explicitly locks the derived-feature approach to avoid error compounding.
- **Using rz_target_share directly as a feature:** It is in `_SAME_WEEK_RAW_STATS` (leakage). Only the rolled versions (with shift(1)) are safe.
- **Skipping SHAP re-selection:** New features should go through SHAP to let the model decide relevance. Appending without selection risks adding noise.
- **Training LGB with verbose output:** LGB_CONSERVATIVE_PARAMS already has `verbose: -1`, but fit kwargs must also use `lgb.early_stopping(50, verbose=False)` to suppress callback output.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Walk-forward CV for LGB | New CV function | Existing `player_walk_forward_cv()` with `model_factory` and `fit_kwargs_fn` params | Already accepts any model factory callable |
| Ridge meta-learner | Custom meta-learner | Adapt `train_ridge_meta()` from ensemble_training.py | RidgeCV with automatic alpha selection |
| LGB model creation | Manual LGBMRegressor setup | `make_lgb_model()` from ensemble_training.py | Already handles param dict correctly |
| OOF prediction assembly | Manual DataFrame merging | Adapt `assemble_oof_matrix()` pattern (use idx instead of game_id) | Handles inner-join and target attachment |
| Ship gate evaluation | New evaluation logic | Existing `ship_gate_verdict()`, `compute_position_mae()`, `print_ship_gate_table()` | Phase 40 infrastructure works as-is |
| Feature column discovery | Manual column listing | Existing `get_player_feature_columns()` | Auto-discovers numeric columns excluding identifiers/labels |

**Key insight:** The existing `player_walk_forward_cv()` is already parameterized with `model_factory` and `fit_kwargs_fn`, making it trivially reusable for LGB models. The ensemble stacking at the player level is structurally identical to the game-level ensemble in `ensemble_training.py`, just keyed on row index instead of game_id and per-stat instead of per-target.

## Common Pitfalls

### Pitfall 1: Red Zone Target Share Not in Rolling Columns
**What goes wrong:** D-07 requires `rz_target_share_roll3` for TD regression features, but `rz_target_share` is NOT in `ROLLING_STAT_COLS` in player_analytics.py. Attempting to use it will find NaN/missing columns.
**Why it happens:** `rz_target_share` was added as a usage metric but never added to the rolling average computation list.
**How to avoid:** Either (a) add `rz_target_share` to `ROLLING_STAT_COLS` in player_analytics.py and re-run Silver transformation, or (b) compute the rolling in `player_feature_engineering.py` post-join using the shift(1)->rolling pattern directly. Option (b) is preferred to avoid Silver reprocessing.
**Warning signs:** `rz_target_share_roll3` column not found in assembled features.

### Pitfall 2: Division by Zero in Efficiency Ratios
**What goes wrong:** Computing `yards_per_carry_roll3` when `carries_roll3` is zero or NaN produces inf or NaN that propagates through the model.
**Why it happens:** Players with zero carries/targets in a rolling window (bye weeks, injuries, position changes).
**How to avoid:** Always use `np.where(denominator > 0, numerator / denominator, np.nan)`. XGBoost and LightGBM both handle NaN natively as missing values.
**Warning signs:** Inf values in feature columns, model training warnings about infinite values.

### Pitfall 3: OOF Matrix Key Mismatch (idx vs game_id)
**What goes wrong:** The game-level `assemble_oof_matrix()` joins on `game_id`. Player-level OOF DataFrames use `idx` (row index). Using game_id will fail with empty joins.
**Why it happens:** Player models are row-level (one row per player-week), not game-level.
**How to avoid:** The player-level OOF assembly must join on `idx` column, not `game_id`. Write a dedicated `assemble_player_oof_matrix()` function.
**Warning signs:** Empty OOF matrix after assembly, Ridge meta-learner fitting on zero rows.

### Pitfall 4: Feature Selection Must Be Re-Run
**What goes wrong:** Adding ~17 new features without re-running SHAP selection means: (a) new features are not selected, or (b) feature count bloats and model overfits.
**Why it happens:** `get_player_feature_columns()` auto-discovers all numeric columns, so new features enter the candidate set. But the saved feature_selection JSON files from Phase 40 don't include them.
**How to avoid:** Re-run `run_player_feature_selection()` with the new features in the candidate pool. This is already the behavior of `train_player_models.py` when `--skip-feature-selection` is NOT passed.
**Warning signs:** New feature columns present in data but absent from selected features list.

### Pitfall 5: LGB Early Stopping API Differs from XGBoost
**What goes wrong:** Passing `early_stopping_rounds` as a constructor param to LGBMRegressor does not work the same as XGBoost. LGB uses a callback pattern.
**Why it happens:** API differences between frameworks.
**How to avoid:** Use `_lgb_fit_kwargs()` from ensemble_training.py which passes `callbacks=[lgb.early_stopping(50, verbose=False)]` in fit kwargs. The existing `player_walk_forward_cv()` supports custom `fit_kwargs_fn`.
**Warning signs:** LGB training warnings, LGB training without early stopping (overfitting).

### Pitfall 6: Sequential Stage Evaluation Requires Identical Data Splits
**What goes wrong:** If features-only and ensemble stages use different data splits or different holdout subsets, the two-stage comparison is invalid.
**Why it happens:** Subtle differences in row filtering, NaN dropping, or holdout season handling between runs.
**How to avoid:** Both stages must use the same `PLAYER_VALIDATION_SEASONS` and `HOLDOUT_SEASON`. The ship gate function already enforces this.
**Warning signs:** Different row counts between stages, different fold sizes in walk-forward CV.

## Code Examples

### Efficiency Feature Computation
```python
# Source: derived from existing player_analytics.py rolling pattern
# Compute in player_feature_engineering.py after all Silver joins

def compute_efficiency_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive per-touch efficiency features from existing rolling averages.

    Per D-06: ~12 features per position with roll3 and roll6 variants.
    Uses safe division (np.where) to handle zero denominators.
    All source columns already have shift(1) applied in Silver.
    """
    result = df.copy()

    for suffix in ["roll3", "roll6"]:
        # Yards per carry
        c, y = f"carries_{suffix}", f"rushing_yards_{suffix}"
        if c in result.columns and y in result.columns:
            result[f"yards_per_carry_{suffix}"] = np.where(
                result[c] > 0, result[y] / result[c], np.nan
            )

        # Yards per target
        t, ry = f"targets_{suffix}", f"receiving_yards_{suffix}"
        if t in result.columns and ry in result.columns:
            result[f"yards_per_target_{suffix}"] = np.where(
                result[t] > 0, result[ry] / result[t], np.nan
            )

        # Yards per reception
        r, ry = f"receptions_{suffix}", f"receiving_yards_{suffix}"
        if r in result.columns and ry in result.columns:
            result[f"yards_per_reception_{suffix}"] = np.where(
                result[r] > 0, result[ry] / result[r], np.nan
            )

        # Catch rate
        t, r = f"targets_{suffix}", f"receptions_{suffix}"
        if t in result.columns and r in result.columns:
            result[f"catch_rate_{suffix}"] = np.where(
                result[t] > 0, result[r] / result[t], np.nan
            )

        # Rush TD rate
        c, td = f"carries_{suffix}", f"rushing_tds_{suffix}"
        if c in result.columns and td in result.columns:
            result[f"rush_td_rate_{suffix}"] = np.where(
                result[c] > 0, result[td] / result[c], np.nan
            )

        # Receiving TD rate
        t, td = f"targets_{suffix}", f"receiving_tds_{suffix}"
        if t in result.columns and td in result.columns:
            result[f"rec_td_rate_{suffix}"] = np.where(
                result[t] > 0, result[td] / result[t], np.nan
            )

    return result
```

### TD Regression Features
```python
# Source: D-07 design from CONTEXT.md

# Position-average red zone TD conversion rates (compute from historical data)
POSITION_AVG_RZ_TD_RATE = {
    "RB": 0.08,   # ~8% of red zone targets convert to TDs (historical average)
    "WR": 0.12,   # ~12% for WRs (higher per-target TD rate in red zone)
    "TE": 0.14,   # ~14% for TEs (highest per-target TD rate in red zone)
}

def compute_td_regression_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add expected TD features from red zone opportunity share.

    Per D-07: Two features per position:
    1. Position-average: rz_share * POSITION_AVG_RZ_TD_RATE
    2. Player-specific: rz_share * player's own RZ TD conversion rate (roll6)
    """
    result = df.copy()

    # Need rz_target_share rolling - compute if not present
    if "rz_target_share_roll3" not in result.columns:
        if "rz_target_share" in result.columns:
            result["rz_target_share_roll3"] = (
                result.groupby(["player_id", "season"])["rz_target_share"]
                .transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
            )

    if "rz_target_share_roll3" in result.columns:
        # Position-average expected TDs
        result["expected_td_pos_avg"] = result.apply(
            lambda row: row["rz_target_share_roll3"] * POSITION_AVG_RZ_TD_RATE.get(
                row.get("position", ""), 0.10
            ),
            axis=1,
        )

        # Player-specific: use rec_td_rate_roll6 (computed by efficiency features)
        if "rec_td_rate_roll6" in result.columns:
            result["expected_td_player"] = (
                result["rz_target_share_roll3"] * result["rec_td_rate_roll6"]
            )

    return result
```

### Momentum Delta Features
```python
# Source: D-08 design from CONTEXT.md

def compute_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add role momentum deltas: roll3 - roll6 = short-term trend.

    Positive = breakout (increasing role), negative = demotion (decreasing role).
    Pure arithmetic on existing lagged columns — zero leakage risk.
    """
    result = df.copy()
    deltas = {
        "snap_pct_delta": ("snap_pct_roll3", "snap_pct_roll6"),
        "target_share_delta": ("target_share_roll3", "target_share_roll6"),
        "carry_share_delta": ("carry_share_roll3", "carry_share_roll6"),
    }
    for name, (r3, r6) in deltas.items():
        if r3 in result.columns and r6 in result.columns:
            result[name] = result[r3] - result[r6]
    return result
```

### LGB Adaptation for Player Models
```python
# Source: adapted from ensemble_training.py _lgb_fit_kwargs + make_lgb_model

from config import LGB_CONSERVATIVE_PARAMS

def _player_lgb_fit_kwargs(X_train, y_train, X_val, y_val) -> dict:
    """LightGBM fit kwargs for player walk-forward CV."""
    import lightgbm as lgb
    return {
        "eval_set": [(X_val, y_val)],
        "callbacks": [lgb.early_stopping(50, verbose=False)],
    }

def _get_lgb_params_for_stat(stat: str) -> dict:
    """Map stat type to LGB hyperparameters (analogous to get_player_model_params)."""
    stat_type = get_stat_type(stat)
    base = LGB_CONSERVATIVE_PARAMS.copy()
    if stat_type == "td":
        base["max_depth"] = 3
        base["min_child_samples"] = 30
        base["n_estimators"] = 300
    elif stat_type == "turnover":
        base["max_depth"] = 3
        base["min_child_samples"] = 30
        base["n_estimators"] = 300
    return base
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw rolling averages for TDs | Expected TD from RZ opportunity x conversion rate | Phase 41 | TD regression reduces noise from random TD variance |
| Single model (XGBoost) per stat | XGB + LGB stacking with Ridge meta | Phase 41 | Model diversity reduces overfitting (same benefit as game-level ensemble in v2.0) |
| No efficiency decomposition | Yards/carry, yards/target, catch rate, TD rate features | Phase 41 | Separates volume signal from efficiency signal |
| No role momentum | Delta features (roll3 - roll6) | Phase 41 | Detects breakout/demotion trends in 3-game window |

**Critical numeric targets (from Phase 40 ship gate):**
| Position | OOF ML MAE | OOF Heuristic MAE | Target ML OOF (4%+ improvement) |
|----------|------------|-------------------|----------------------------------|
| RB | 5.218 | 4.633 | < 4.448 |
| WR | 4.915 | 4.304 | < 4.132 |
| TE | 3.666 | 3.283 | < 3.152 |

These are aggressive targets. The ML models need to improve by 15-19% on OOF to pass the ship gate. The new features and ensemble should help but success is not guaranteed for all three positions.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 |
| Config file | tests/ directory with existing test infrastructure |
| Quick run command | `python -m pytest tests/test_player_model_training.py tests/test_player_ship_gate.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACCY-01 | Efficiency features computed correctly with safe division | unit | `python -m pytest tests/test_player_feature_engineering.py -x -v -k efficiency` | Wave 0 |
| ACCY-02 | TD regression features produce expected values, handle NaN | unit | `python -m pytest tests/test_player_feature_engineering.py -x -v -k td_regression` | Wave 0 |
| ACCY-03 | Momentum deltas equal roll3 - roll6 | unit | `python -m pytest tests/test_player_feature_engineering.py -x -v -k momentum` | Wave 0 |
| ACCY-04 | LGB walk-forward CV produces OOF, Ridge meta fits on OOF matrix | unit | `python -m pytest tests/test_player_model_training.py -x -v -k ensemble` | Wave 0 |
| ACCY-01-04 | Ship gate re-run with new features (integration) | integration | `python scripts/train_player_models.py --positions RB WR TE --holdout-eval` | Existing |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_player_feature_engineering.py tests/test_player_model_training.py tests/test_player_ship_gate.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_player_feature_engineering.py` — add tests for `compute_efficiency_features()`, `compute_td_regression_features()`, `compute_momentum_features()` (file exists, needs new test methods)
- [ ] `tests/test_player_model_training.py` — add tests for LGB model factory, `_player_lgb_fit_kwargs`, `player_ensemble_stacking()`, `assemble_player_oof_matrix()` (file exists, needs new test methods)

## Open Questions

1. **Exact position-average RZ TD rates**
   - What we know: These should be computed from historical data (2020-2024 training seasons).
   - What's unclear: Exact values depend on running the computation. The CONTEXT.md says to compute from historical data.
   - Recommendation: Compute from Silver usage data during implementation. Start with reasonable estimates (RB ~8%, WR ~12%, TE ~14%) and refine.

2. **SHAP re-selection vs append strategy**
   - What we know: New features need to be evaluated. `get_player_feature_columns()` auto-discovers them. The question is whether to re-run full SHAP selection or just add new features to existing selected sets.
   - What's unclear: Whether re-running might drop previously useful features.
   - Recommendation: Re-run full SHAP selection. The existing flow in `train_player_models.py` does this by default when `--skip-feature-selection` is not passed. SHAP will retain what matters.

3. **Whether features alone will be sufficient**
   - What we know: The OOF gap is 15-19% — substantial. Features alone may not close this.
   - What's unclear: How much signal the new features add vs how much is an inherent modeling limitation.
   - Recommendation: D-09 addresses this with sequential evaluation. Features first, ensemble second. The two-stage ablation report (D-11) will quantify each contribution.

4. **LGB hyperparameter tuning for player stats vs game stats**
   - What we know: `LGB_CONSERVATIVE_PARAMS` in config.py was tuned for game-level targets (margin, total). Player stats have different distributions.
   - What's unclear: Whether the same params work well for player-level stats.
   - Recommendation: Start with conservative params (D-12). Per-stat-type variations (TD vs yardage vs volume) should mirror the XGBoost pattern: shallower trees for TDs/turnovers, deeper for yardage/volume. Optuna is explicitly deferred.

## Sources

### Primary (HIGH confidence)
- `src/player_model_training.py` — Existing walk-forward CV, ship gate, feature selection infrastructure
- `src/player_feature_engineering.py` — Feature assembly patterns, identifier/label column lists
- `src/player_analytics.py` — Rolling average computation (shift(1)->rolling), ROLLING_STAT_COLS
- `src/ensemble_training.py` — make_lgb_model(), train_ridge_meta(), assemble_oof_matrix(), _lgb_fit_kwargs()
- `src/config.py` — LGB_CONSERVATIVE_PARAMS, CONSERVATIVE_PARAMS, HOLDOUT_SEASON
- `models/player/ship_gate_report.json` — Phase 40 baselines (RB/WR/TE OOF gaps)
- `src/projection_engine.py` — POSITION_STAT_PROFILE (defines per-position stats)

### Secondary (MEDIUM confidence)
- Position-average RZ TD rates (estimates based on NFL data knowledge; should be computed from data)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed and proven in codebase
- Architecture: HIGH - extending existing patterns with minimal new abstractions
- Pitfalls: HIGH - based on direct code reading of existing implementations
- Feature design: HIGH - locked in CONTEXT.md with specific column names
- Numeric targets: HIGH - directly from Phase 40 ship gate report

**Research date:** 2026-03-30
**Valid until:** 2026-04-15 (stable domain, no external dependency changes expected)
