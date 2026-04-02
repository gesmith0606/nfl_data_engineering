# Phase 40: Baseline Models and Ship Gate - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Per-position ML models produce stat-level predictions that are objectively measured against the heuristic baseline, with a clear ship-or-skip verdict per position. Separate gradient boosting models for QB, RB, WR, TE predict raw stat components; fantasy points derived via scoring calculator. Walk-forward CV + sealed 2025 holdout evaluation. Requirements: MODL-01, MODL-02, MODL-03, MODL-04, PIPE-01.

</domain>

<decisions>
## Implementation Decisions

### Model Granularity
- **D-01:** One model per stat per position (~19 models total): QB (5), RB (6), WR (4), TE (4)
- **D-02:** Stats per position match `POSITION_STAT_PROFILE` in `projection_engine.py`:
  - QB: passing_yards, passing_tds, interceptions, rushing_yards, rushing_tds
  - RB: rushing_yards, rushing_tds, carries, receptions, receiving_yards, receiving_tds
  - WR: targets, receptions, receiving_yards, receiving_tds
  - TE: targets, receptions, receiving_yards, receiving_tds
- **D-03:** Each stat model gets independent hyperparameters — TD models need different regularization than yardage models

### Feature Selection
- **D-04:** SHAP-based feature selection per stat-type group (4 groups, not 19):
  - Yardage: passing_yards, rushing_yards, receiving_yards
  - TD: passing_tds, rushing_tds, receiving_tds
  - Volume: targets, receptions, carries
  - Turnover: interceptions
- **D-05:** Same CV-validated SHAP pattern as `feature_selector.py` (Phase 29), adapted per group
- **D-06:** Models within a group share the same selected feature set

### Ship Gate Criteria
- **D-07:** Primary metric: per-position fantasy points MAE (raw stat predictions converted through `scoring_calculator.py` with half-PPR)
- **D-08:** Ship threshold: 4%+ MAE improvement over heuristic baseline per position
- **D-09:** Safety floor: no individual stat model may be >10% worse MAE than heuristic for that stat
- **D-10:** Dual agreement required: walk-forward OOF (2021-2024) must show improvement AND 2025 holdout must confirm — either failing = no ship
- **D-11:** Per-position verdict: positions where both criteria pass are shipped; others fall back to heuristic

### Evaluation Method
- **D-12:** Heuristic baseline re-run on identical player-weeks as ML (same eligibility filter, same rows) — not using published 2022-2024 numbers directly
- **D-13:** Half-PPR is the primary scoring format for ship verdict; PPR and standard reported alongside for visibility
- **D-14:** Weeks 3-18 for ship gate evaluation; weeks 1-2 reported separately as supplementary (cold-start performance)

### Training Data and Walk-Forward Design
- **D-15:** Training seasons: 2020-2024 only (existing player feature assembly coverage). No backporting to 2016-2019
- **D-16:** 2025 holdout sealed — never touched during training or feature selection
- **D-17:** Walk-forward folds: minimum 2 training seasons required, yielding 3 folds:
  - Fold 1: Train 2020-2021 -> Validate 2022
  - Fold 2: Train 2020-2022 -> Validate 2023
  - Fold 3: Train 2020-2023 -> Validate 2024
- **D-18:** Expanding window (all prior seasons per fold), not sliding window
- **D-19:** Fully independent models per position — no cross-position data sharing

### Claude's Discretion
- Model framework choice (XGBoost-only baseline vs XGB+LGB+CB from the start)
- Hyperparameter defaults and early stopping configuration
- SHAP group cutoff thresholds
- Output directory structure under `models/` and `data/gold/`
- CLI script design and argument structure
- How to structure the comparison report output

</decisions>

<specifics>
## Specific Ideas

- Reuse `ensemble_training.py` patterns (model factories, walk-forward CV with OOF) — adapt from game-level to player-level
- Reuse `feature_selector.py` SHAP + correlation filtering — run per stat-type group instead of per target
- Fantasy points conversion: predict raw stats -> feed through `scoring_calculator.calculate_fantasy_points_df()` -> compare MAE
- Ship gate report should be a clear table: position | heuristic MAE | ML MAE | delta % | verdict (SHIP/SKIP)
- Per-stat breakdown table underneath for transparency

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Player feature assembly (Phase 39 output)
- `src/player_feature_engineering.py` — `assemble_player_features()`, `get_player_feature_columns()`, `detect_leakage()`, `validate_temporal_integrity()`
- `src/config.py` — `PLAYER_DATA_SEASONS`, `PLAYER_LABEL_COLUMNS`, `HOLDOUT_SEASON`, `VALIDATION_SEASONS`

### Existing ML patterns to adapt
- `src/ensemble_training.py` — `make_xgb_model()`, `walk_forward_cv_with_oof()`, `train_ridge_meta()`, `train_ensemble()` — game-level ensemble patterns
- `src/model_training.py` — `WalkForwardResult` dataclass, `walk_forward_cv()` with season-boundary folds, `train_final_model()`
- `src/feature_selector.py` — SHAP importance + correlation filtering, CV-validated cutoff

### Heuristic baseline (comparison target)
- `src/projection_engine.py` — `POSITION_STAT_PROFILE`, `RECENCY_WEIGHTS`, `_weighted_baseline()`, `_rookie_baseline()`, `_usage_multiplier()`, `_matchup_factor()`
- `scripts/backtest_projections.py` — Existing backtest framework for heuristic; adapt for side-by-side comparison

### Scoring conversion
- `src/scoring_calculator.py` — `calculate_fantasy_points_df()` for converting raw stat predictions to fantasy points

### Prior phase context
- `.planning/phases/39-player-feature-vector-assembly/39-CONTEXT.md` — Feature vector design, join keys, eligibility filter, target columns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ensemble_training.make_xgb_model()`: XGBRegressor factory with early stopping — reuse directly
- `ensemble_training.walk_forward_cv_with_oof()`: Generalized walk-forward CV producing OOF predictions — adapt fold boundaries for player data (2020-2024, min 2 training seasons)
- `feature_selector.py`: SHAP importance + correlation filtering pipeline — run per stat-type group
- `scoring_calculator.calculate_fantasy_points_df()`: Vectorized raw stats -> fantasy points — use for MAE comparison
- `projection_engine.POSITION_STAT_PROFILE`: Canonical stat list per position — drives model count
- `player_feature_engineering.get_player_feature_columns()`: Returns valid feature column names (excludes identifiers, labels, same-week raw stats)

### Established Patterns
- **Walk-forward CV**: Season-boundary folds, holdout exclusion, OOF predictions — from `model_training.py` and `ensemble_training.py`
- **Model serialization**: JSON export with metadata sidecar — from `model_training.train_final_model()`
- **Ship-or-skip gate**: Strict > comparison on holdout metric — from `scripts/ablation_market_features.py` (Phase 34/38)
- **Feature selection**: Per-fold SHAP with holdout excluded — from `feature_selector.py`

### Integration Points
- **Input**: `player_feature_engineering.assemble_player_features(season)` returns player-week DataFrame with features + labels
- **Output**: Trained models saved to `models/player/` (new directory); predictions to `data/gold/player_predictions/`
- **Comparison**: Both ML and heuristic predictions generated on identical player-week rows, converted to fantasy points, MAE computed per position

</code_context>

<deferred>
## Deferred Ideas

- Opportunity-efficiency decomposition (two-stage prediction) -- Phase 41
- TD regression from red zone features -- Phase 41
- Role momentum features (snap share trajectory) -- Phase 41
- Ensemble stacking per position (XGB+LGB+CB+Ridge) -- Phase 41
- Team-total constraint enforcement -- Phase 42
- Preseason mode (prior-season aggregates) -- Phase 42
- MAPIE confidence intervals -- Phase 42
- Extending training data to 2016-2019 -- Phase 41 if needed
- Sliding window experiment -- Phase 41 if expanding window shows 2020 hurting

</deferred>

---

*Phase: 40-baseline-models-ship-gate*
*Context gathered: 2026-03-30*
