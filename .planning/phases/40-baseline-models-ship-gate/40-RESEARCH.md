# Phase 40: Baseline Models and Ship Gate - Research

**Researched:** 2026-03-30
**Domain:** Per-position ML player prediction with walk-forward CV and ship-or-skip evaluation
**Confidence:** HIGH

## Summary

Phase 40 builds per-position, per-stat gradient boosting models that predict raw stat components (yards, TDs, receptions) for QB, RB, WR, and TE. Fantasy points are derived downstream via `scoring_calculator.calculate_fantasy_points_df()` rather than predicted directly. The ship gate compares ML fantasy-point MAE against heuristic baselines (QB: 6.58, RB: 5.06, WR: 4.85, TE: 3.77) with a 4%+ improvement threshold.

The codebase already contains all required building blocks: `player_feature_engineering.py` for feature assembly, `ensemble_training.py` for model factories and walk-forward CV patterns, `feature_selector.py` for SHAP-based feature selection, and `scoring_calculator.py` for stat-to-points conversion. The primary work is adapting the game-level ensemble patterns to player-level granularity with per-position data splitting, per-stat-group feature selection, and a per-position ship gate.

**Primary recommendation:** Start with XGBoost-only baseline models (not the full XGB+LGB+CB ensemble -- that is deferred to Phase 41 per D-03 in deferred ideas). Use `make_xgb_model()` from `ensemble_training.py`, adapt `walk_forward_cv_with_oof()` with custom player-level validation seasons `[2022, 2023, 2024]`, and run SHAP feature selection per stat-type group (4 groups, not 19 individual models).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** One model per stat per position (~19 models total): QB (5), RB (6), WR (4), TE (4)
- **D-02:** Stats per position match `POSITION_STAT_PROFILE` in `projection_engine.py`
- **D-03:** Each stat model gets independent hyperparameters -- TD models need different regularization than yardage models
- **D-04:** SHAP-based feature selection per stat-type group (4 groups: yardage, TD, volume, turnover)
- **D-05:** Same CV-validated SHAP pattern as `feature_selector.py`, adapted per group
- **D-06:** Models within a group share the same selected feature set
- **D-07:** Primary metric: per-position fantasy points MAE (raw stat predictions converted through `scoring_calculator.calculate_fantasy_points_df()` with half-PPR)
- **D-08:** Ship threshold: 4%+ MAE improvement over heuristic baseline per position
- **D-09:** Safety floor: no individual stat model may be >10% worse MAE than heuristic for that stat
- **D-10:** Dual agreement required: walk-forward OOF (2021-2024) AND 2025 holdout must both confirm improvement
- **D-11:** Per-position verdict: positions where both criteria pass are shipped; others fall back to heuristic
- **D-12:** Heuristic baseline re-run on identical player-weeks as ML (same eligibility filter, same rows)
- **D-13:** Half-PPR is primary scoring format for ship verdict; PPR and standard reported alongside
- **D-14:** Weeks 3-18 for ship gate evaluation; weeks 1-2 reported separately as supplementary
- **D-15:** Training seasons: 2020-2024 only (existing player feature assembly coverage)
- **D-16:** 2025 holdout sealed -- never touched during training or feature selection
- **D-17:** Walk-forward folds: minimum 2 training seasons, yielding 3 folds (2020-21->2022, 2020-22->2023, 2020-23->2024)
- **D-18:** Expanding window (all prior seasons per fold), not sliding window
- **D-19:** Fully independent models per position -- no cross-position data sharing

### Claude's Discretion
- Model framework choice (XGBoost-only baseline vs XGB+LGB+CB from the start)
- Hyperparameter defaults and early stopping configuration
- SHAP group cutoff thresholds
- Output directory structure under `models/` and `data/gold/`
- CLI script design and argument structure
- How to structure the comparison report output

### Deferred Ideas (OUT OF SCOPE)
- Opportunity-efficiency decomposition (two-stage prediction) -- Phase 41
- TD regression from red zone features -- Phase 41
- Role momentum features (snap share trajectory) -- Phase 41
- Ensemble stacking per position (XGB+LGB+CB+Ridge) -- Phase 41
- Team-total constraint enforcement -- Phase 42
- Preseason mode (prior-season aggregates) -- Phase 42
- MAPIE confidence intervals -- Phase 42
- Extending training data to 2016-2019 -- Phase 41 if needed
- Sliding window experiment -- Phase 41 if expanding window shows 2020 hurting
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MODL-01 | Separate gradient boosting models trained per position (QB, RB, WR, TE) | 19 XGBoost models (one per stat per position) using `make_xgb_model()` factory; position data split via `df[df["position"] == pos]` |
| MODL-02 | Walk-forward temporal CV respecting season/week ordering with 2025 holdout sealed | Adapt `walk_forward_cv_with_oof()` with `val_seasons=[2022, 2023, 2024]` and holdout guard from `_assert_no_holdout()` |
| MODL-03 | Per-position MAE/RMSE/correlation evaluation against heuristic baseline | Convert raw stat predictions to fantasy points via `calculate_fantasy_points_df()`; re-run heuristic on identical rows for fair comparison |
| MODL-04 | Ship-or-skip gate requiring 4%+ per-position MAE improvement over heuristic | Dual agreement (OOF + holdout), safety floor (no stat >10% worse), per-position verdict table |
| PIPE-01 | Stat-level predictions (yards, TDs, receptions) with scoring formula applied downstream | 19 stat models output raw predictions; `calculate_fantasy_points_df()` converts to fantasy points post-hoc |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 2.1.4 (installed) | Gradient boosting for all 19 stat models | Already used in game prediction; proven on tabular sports data |
| shap | 0.46.0 (installed) | Feature importance for per-group selection | Same pattern as Phase 29 feature_selector.py |
| scikit-learn | 1.6.1 (installed) | mean_absolute_error, train_test_split, correlation metrics | Standard ML evaluation |
| pandas | 2.2.3 (installed) | DataFrame processing, groupby, merge | Project standard |
| numpy | 2.2.3 (installed) | Array operations | Project standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scipy.stats | (bundled) | pearsonr for correlation metric in evaluation | Reporting correlation alongside MAE/RMSE |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| XGBoost-only | XGB+LGB+CB ensemble | Ensemble is Phase 41; single-model baseline is simpler to debug, faster to iterate, and establishes the ship gate framework |

**Installation:**
No new packages required -- all dependencies already installed.

## Architecture Patterns

### Recommended Project Structure
```
src/
  player_model_training.py     # Core: per-position per-stat model training, walk-forward CV, ship gate
  player_feature_engineering.py # Existing: feature assembly (Phase 39)
  feature_selector.py           # Existing: SHAP selection (reuse per stat-group)
  ensemble_training.py          # Existing: model factories (reuse make_xgb_model)
  scoring_calculator.py         # Existing: raw stats -> fantasy points

scripts/
  train_player_models.py        # CLI: train all 19 models + produce ship gate report
  backtest_player_models.py     # CLI: evaluate on holdout + side-by-side comparison

models/
  player/                       # New directory for player model artifacts
    qb/                         # Per-position subdirectories
      passing_yards.json        # XGBoost model file
      passing_yards_meta.json   # Metadata sidecar
      passing_tds.json
      ...
    rb/
    wr/
    te/
    feature_selection/          # SHAP selection results per stat-group
      yardage_features.json
      td_features.json
      volume_features.json
      turnover_features.json
    ship_gate_report.json       # Machine-readable verdict

data/gold/
  player_predictions/           # Prediction output
    season=YYYY/
      week=WW/
        predictions_YYYYMMDD_HHMMSS.parquet
```

### Pattern 1: Per-Position Data Splitting
**What:** Filter assembled player features by position before training
**When to use:** Every model training and evaluation call
**Example:**
```python
# Source: adapted from existing pattern in projection_engine.py
from config import PLAYER_LABEL_COLUMNS
from projection_engine import POSITION_STAT_PROFILE

def get_position_data(all_data, position):
    """Split assembled features by position, drop NaN targets."""
    pos_data = all_data[all_data["position"] == position].copy()
    stats = POSITION_STAT_PROFILE[position]
    # Drop rows where ALL target stats are NaN
    pos_data = pos_data.dropna(subset=stats, how="all")
    return pos_data
```

### Pattern 2: Adapted Walk-Forward CV for Player Data
**What:** Walk-forward CV with player-specific validation seasons (3 folds, not 6)
**When to use:** All model training and feature selection
**Example:**
```python
# Source: adapted from ensemble_training.walk_forward_cv_with_oof
PLAYER_VALIDATION_SEASONS = [2022, 2023, 2024]  # D-17: min 2 training seasons

def player_walk_forward_cv(pos_data, feature_cols, target_col, model_factory,
                           fit_kwargs_fn=None):
    """Walk-forward CV for player models with 3 folds."""
    # Reuse walk_forward_cv_with_oof with custom val_seasons
    # Key difference: join key is player_id (not game_id)
    return walk_forward_cv_with_oof(
        pos_data, feature_cols, target_col,
        model_factory=model_factory,
        fit_kwargs_fn=fit_kwargs_fn,
        val_seasons=PLAYER_VALIDATION_SEASONS,
    )
```

**Critical adaptation needed:** The existing `walk_forward_cv_with_oof()` collects OOF predictions keyed by `game_id`. For player models, the OOF key must be `player_id` + `season` + `week` (or a row index). This requires either modifying the existing function to accept a configurable key column, or writing a new player-specific walk-forward function.

### Pattern 3: Stat-Group Feature Selection
**What:** Run SHAP feature selection once per stat-type group, shared across models in that group
**When to use:** Before training, to reduce features
**Example:**
```python
# Source: adapted from feature_selector.select_features_for_fold
STAT_GROUPS = {
    "yardage": ["passing_yards", "rushing_yards", "receiving_yards"],
    "td": ["passing_tds", "rushing_tds", "receiving_tds"],
    "volume": ["targets", "receptions", "carries"],
    "turnover": ["interceptions"],
}

# For each group, pick a representative target and run selection
# e.g., yardage group uses rushing_yards as the SHAP target
```

### Pattern 4: Heuristic Baseline Re-Run
**What:** Generate heuristic predictions on identical player-week rows as ML
**When to use:** For fair MAE comparison (D-12)
**Example:**
```python
# Source: adapted from projection_engine._weighted_baseline
from projection_engine import (
    _weighted_baseline, _usage_multiplier, _matchup_factor,
    POSITION_STAT_PROFILE, RECENCY_WEIGHTS,
)
from scoring_calculator import calculate_fantasy_points_df

def generate_heuristic_predictions(pos_data, position, scoring="half_ppr"):
    """Re-run heuristic on the same rows ML will predict."""
    pred_df = pos_data.copy()
    for stat in POSITION_STAT_PROFILE[position]:
        pred_df[f"pred_{stat}"] = _weighted_baseline(pred_df, stat)
    # Apply usage and matchup adjustments
    mult = _usage_multiplier(pred_df, position)
    for stat in POSITION_STAT_PROFILE[position]:
        pred_df[f"pred_{stat}"] *= mult
    # Convert to fantasy points
    # Rename pred_ columns to match scoring calculator expectations
    return calculate_fantasy_points_df(pred_df, scoring_format=scoring)
```

### Pattern 5: Ship Gate Verdict
**What:** Compare ML vs heuristic MAE with dual agreement requirement
**When to use:** Final evaluation step
**Example:**
```python
# Source: adapted from scripts/ablation_market_features.py ship-or-skip pattern
def ship_gate_verdict(ml_mae, heuristic_mae, oof_ml_mae, oof_heuristic_mae):
    """Per-position ship-or-skip with dual agreement (D-10)."""
    holdout_improvement = (heuristic_mae - ml_mae) / heuristic_mae
    oof_improvement = (oof_heuristic_mae - oof_ml_mae) / oof_heuristic_mae
    ship = holdout_improvement >= 0.04 and oof_improvement >= 0.04
    return {
        "holdout_improvement_pct": holdout_improvement * 100,
        "oof_improvement_pct": oof_improvement * 100,
        "verdict": "SHIP" if ship else "SKIP",
    }
```

### Anti-Patterns to Avoid
- **Predicting fantasy points directly:** D-07 and PIPE-01 require predicting raw stats, then converting. Direct fantasy point prediction hides stat-level errors.
- **Using game-level VALIDATION_SEASONS for player models:** Config has `[2019, 2020, 2021, 2022, 2023, 2024]` but player data only covers 2020-2025. Must use `[2022, 2023, 2024]` per D-17.
- **Sharing features across positions:** D-19 requires fully independent models. No cross-position feature sharing.
- **Touching 2025 holdout during feature selection:** SHAP selection must exclude holdout. Use `_assert_no_holdout()` guard.
- **Using published heuristic baselines directly:** D-12 requires re-running heuristic on the exact same rows. The published numbers (6.58, 5.06, etc.) were on different player-week populations.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| XGBoost model creation | Custom model init | `ensemble_training.make_xgb_model()` | Handles early_stopping_rounds extraction correctly |
| Walk-forward fold logic | Custom fold splitting | Adapt `walk_forward_cv_with_oof()` or replicate its fold logic | Holdout guard, OOF collection, fold detail tracking already handled |
| SHAP feature importance | Custom importance scoring | `feature_selector.select_features_for_fold()` | Correlation filtering, SHAP subsample, holdout guard included |
| Fantasy point conversion | Manual stat weighting | `scoring_calculator.calculate_fantasy_points_df()` | Handles all scoring formats, column mapping, NaN filling |
| Stat profiles per position | Hardcoded stat lists | `projection_engine.POSITION_STAT_PROFILE` | Single source of truth for which stats each position predicts |
| Heuristic baseline | New baseline implementation | `projection_engine._weighted_baseline()` + `_usage_multiplier()` + `_matchup_factor()` | Must match existing heuristic exactly for fair comparison |

**Key insight:** The entire model training pipeline is a composition of existing building blocks. The novelty is the per-position/per-stat decomposition and the ship gate framework -- not the ML infrastructure.

## Common Pitfalls

### Pitfall 1: OOF Key Column Mismatch
**What goes wrong:** `walk_forward_cv_with_oof()` hardcodes `game_id` as the OOF key. Player data does not have `game_id`.
**Why it happens:** The function was built for game-level prediction where each row is a game.
**How to avoid:** Either (a) add `game_id` to player data by joining from schedules, or (b) write a player-specific walk-forward function that uses `(player_id, season, week)` as the key. Option (b) is cleaner.
**Warning signs:** KeyError on `game_id` during OOF collection.

### Pitfall 2: NaN Targets for Position-Irrelevant Stats
**What goes wrong:** QB rows will have NaN for `receiving_yards`; attempting to train a receiving_yards model on QB data produces garbage.
**Why it happens:** PLAYER_LABEL_COLUMNS includes all stats for all positions.
**How to avoid:** Only train stat models that match `POSITION_STAT_PROFILE[position]`. Never train a stat model on a position that does not produce that stat.
**Warning signs:** Models with 0.0 importance on all features, or extremely high MAE.

### Pitfall 3: Heuristic Comparison on Different Populations
**What goes wrong:** ML is trained/evaluated on eligible players (snap_pct_roll3 >= 0.20) but heuristic baselines from backtest used all players. MAE not comparable.
**Why it happens:** The eligibility filter in `assemble_player_features()` removes low-snap players.
**How to avoid:** D-12 explicitly requires re-running heuristic on identical rows. Generate heuristic predictions on the exact same player-week DataFrame that ML predicts on.
**Warning signs:** ML MAE looks artificially good because low-snap outliers were removed.

### Pitfall 4: Week 1-2 Cold Start Inflating Error
**What goes wrong:** Weeks 1-2 have no rolling averages (all NaN or zeros), inflating MAE.
**Why it happens:** Rolling features require 3+ prior games.
**How to avoid:** D-14 specifies weeks 3-18 for ship gate evaluation. Report weeks 1-2 separately.
**Warning signs:** Unusually high MAE that drops substantially after week 3.

### Pitfall 5: TD Model Overfitting
**What goes wrong:** TD counts are sparse integers (0 or 1 per game), making MAE noisy and models prone to overfitting.
**Why it happens:** Binary-ish targets with gradient boosting require stronger regularization.
**How to avoid:** D-03 specifies independent hyperparameters per stat. TD models should use higher min_child_weight, lower learning_rate, fewer estimators. Consider max_depth=3 for TD models vs 4 for yardage.
**Warning signs:** Training MAE much lower than validation MAE for TD models.

### Pitfall 6: Feature Selection Target Choice for Groups
**What goes wrong:** Stat-group feature selection (D-04) requires choosing a representative target. Poor choice leads to irrelevant features.
**Why it happens:** The group concept is new -- the existing feature_selector always used a single target.
**How to avoid:** For each group, use the highest-volume stat as the selection target: yardage -> rushing_yards (most variance), TD -> rushing_tds, volume -> receptions, turnover -> interceptions. Alternatively, average SHAP across all group members.
**Warning signs:** Selected features have low predictive power for some stats in the group.

## Code Examples

### Assembling Multi-Year Player Features
```python
# Source: src/player_feature_engineering.py
from player_feature_engineering import (
    assemble_multiyear_player_features,
    get_player_feature_columns,
    detect_leakage,
)

# Load all training seasons (2020-2024) + holdout (2025)
all_data = assemble_multiyear_player_features(seasons=[2020, 2021, 2022, 2023, 2024, 2025])
feature_cols = get_player_feature_columns(all_data)

# Leakage check before training
leaks = detect_leakage(all_data, feature_cols, PLAYER_LABEL_COLUMNS)
if leaks:
    raise ValueError(f"Leakage detected: {leaks}")
```

### Converting Raw Stat Predictions to Fantasy Points
```python
# Source: src/scoring_calculator.py
from scoring_calculator import calculate_fantasy_points_df

# After predicting raw stats, rename prediction columns to match scorer expectations
pred_df = pred_df.rename(columns={
    "pred_passing_yards": "passing_yards",
    "pred_passing_tds": "passing_tds",
    "pred_interceptions": "interceptions",
    "pred_rushing_yards": "rushing_yards",
    "pred_rushing_tds": "rushing_tds",
    "pred_receiving_yards": "receiving_yards",
    "pred_receiving_tds": "receiving_tds",
    "pred_receptions": "receptions",
})
pred_df = calculate_fantasy_points_df(pred_df, scoring_format="half_ppr",
                                       output_col="ml_fantasy_points")
```

### Ship Gate Report Table Format
```python
# Per the CONTEXT.md specific ideas
report = """
| Position | Heuristic MAE | ML MAE | Delta % | OOF Delta % | Verdict |
|----------|--------------|--------|---------|-------------|---------|
| QB       | 6.58         | {qb}   | {qb_d}% | {qb_oof}%  | {qb_v} |
| RB       | 5.06         | {rb}   | {rb_d}% | {rb_oof}%  | {rb_v} |
| WR       | 4.85         | {wr}   | {wr_d}% | {wr_oof}%  | {wr_v} |
| TE       | 3.77         | {te}   | {te_d}% | {te_oof}%  | {te_v} |
"""
```

## Discretion Recommendations

### Model Framework: XGBoost-Only
**Recommendation:** Use XGBoost only for this baseline phase.
**Rationale:** D-03 in deferred ideas explicitly lists ensemble stacking (XGB+LGB+CB+Ridge) as a Phase 41 concern. This phase establishes the training framework and ship gate; adding ensemble complexity now delays validation of the core architecture. XGBoost alone is the simplest model to debug and iterate on.

### Hyperparameter Defaults
**Recommendation:** Use `CONSERVATIVE_PARAMS` from config.py as the starting point, with stat-type adjustments:
- **Yardage models:** max_depth=4, min_child_weight=5, n_estimators=500 (same as game models)
- **TD models:** max_depth=3, min_child_weight=10, n_estimators=300 (higher regularization for sparse targets)
- **Volume models:** max_depth=4, min_child_weight=5, n_estimators=500
- **Turnover (INT) model:** max_depth=3, min_child_weight=10, n_estimators=300

### SHAP Group Cutoff Thresholds
**Recommendation:** Target 80 features per group (correlation threshold 0.90), consistent with the game prediction pipeline which settled on 120 features from 321. Player features have ~337 columns; 80 per group after correlation filtering should capture key signals without noise.

### Output Directory Structure
**Recommendation:** `models/player/{position}/{stat}.json` with `models/player/feature_selection/{group}_features.json` and `models/player/ship_gate_report.json`. This mirrors the `models/ensemble/` pattern.

### CLI Design
**Recommendation:** Single script `scripts/train_player_models.py` with flags:
- `--positions QB RB WR TE` (default: all four)
- `--dry-run` (feature selection only, no training)
- `--skip-feature-selection` (reuse saved features)
- `--holdout-eval` (run 2025 holdout evaluation after training)

### Report Output
**Recommendation:** Print the ship gate verdict table to stdout with JSON sidecar at `models/player/ship_gate_report.json`. Include per-stat breakdown table underneath the position-level summary. Same pattern as `scripts/ablation_market_features.py`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 |
| Config file | tests/ directory, no pytest.ini (uses defaults) |
| Quick run command | `python -m pytest tests/test_player_model_training.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MODL-01 | Separate models per position per stat | unit | `python -m pytest tests/test_player_model_training.py::test_per_position_model_count -x` | No -- Wave 0 |
| MODL-02 | Walk-forward CV with 3 folds, holdout excluded | unit | `python -m pytest tests/test_player_model_training.py::test_walk_forward_folds -x` | No -- Wave 0 |
| MODL-03 | MAE/RMSE/correlation per position vs heuristic | unit | `python -m pytest tests/test_player_model_training.py::test_evaluation_metrics -x` | No -- Wave 0 |
| MODL-04 | Ship gate with 4% threshold and dual agreement | unit | `python -m pytest tests/test_player_model_training.py::test_ship_gate_verdict -x` | No -- Wave 0 |
| PIPE-01 | Stat-level predictions converted to fantasy points | unit | `python -m pytest tests/test_player_model_training.py::test_stat_to_fantasy_conversion -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_player_model_training.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_player_model_training.py` -- covers MODL-01 through MODL-04, PIPE-01
- [ ] Fixtures: synthetic player-week DataFrames with known stats for deterministic MAE checks

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Predict fantasy points directly | Predict raw stats, convert downstream | v3.0 design (D-01/PIPE-01) | Enables stat-level debugging, position-specific tuning |
| Single heuristic model for all positions | Per-position ML models | v3.0 design (MODL-01) | Different positions have fundamentally different stat distributions |
| Fixed feature set for all targets | Per-stat-group SHAP selection | v3.0 design (D-04) | TD models benefit from different features than yardage models |

## Open Questions

1. **SHAP target for stat groups**
   - What we know: D-04 specifies 4 groups (yardage, TD, volume, turnover) that share features
   - What's unclear: Should SHAP be computed against a single representative stat, or averaged across all stats in the group?
   - Recommendation: Use the highest-variance stat as the representative (rushing_yards for yardage, receiving_tds for TD, receptions for volume, interceptions for turnover). If results are poor, average SHAP as a fallback.

2. **Heuristic re-run mechanics**
   - What we know: Must re-run on identical rows (D-12). The heuristic uses `_weighted_baseline()`, `_usage_multiplier()`, `_matchup_factor()` from projection_engine.py
   - What's unclear: Whether heuristic functions are easily callable on a raw player-week DataFrame, or if they expect Silver-layer column names that differ from the feature assembly output
   - Recommendation: Write a thin wrapper that maps assembled feature columns to heuristic expectations. Test on a small sample before full evaluation.

3. **Walk-forward CV function reuse**
   - What we know: `walk_forward_cv_with_oof()` hardcodes `game_id` as OOF key
   - What's unclear: Whether to modify the existing function (breaking game-level callers) or write a new one
   - Recommendation: Write a new `player_walk_forward_cv()` in `player_model_training.py` that uses the same logic but keys on row index or `(player_id, season, week)`. Do not modify the existing function.

## Sources

### Primary (HIGH confidence)
- `src/ensemble_training.py` -- model factories, walk-forward CV, OOF collection
- `src/feature_selector.py` -- SHAP importance + correlation filtering
- `src/player_feature_engineering.py` -- feature assembly, leakage detection
- `src/projection_engine.py` -- POSITION_STAT_PROFILE, heuristic baseline functions
- `src/scoring_calculator.py` -- calculate_fantasy_points_df()
- `src/config.py` -- HOLDOUT_SEASON=2025, PLAYER_DATA_SEASONS=[2020-2025], CONSERVATIVE_PARAMS, PLAYER_LABEL_COLUMNS
- `src/model_training.py` -- WalkForwardResult dataclass

### Secondary (MEDIUM confidence)
- `scripts/ablation_market_features.py` -- ship-or-skip gate pattern
- `scripts/backtest_projections.py` -- heuristic backtest framework

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and proven in codebase
- Architecture: HIGH -- adapting established patterns, not building new infrastructure
- Pitfalls: HIGH -- directly informed by reading existing code and identifying specific mismatches (game_id key, NaN targets, population filters)

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable -- no external dependency changes expected)
