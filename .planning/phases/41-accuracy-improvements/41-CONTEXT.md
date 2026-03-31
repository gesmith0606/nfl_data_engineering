# Phase 41: Accuracy Improvements - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Per-position prediction accuracy improves beyond baseline models through derived efficiency features, TD regression, role momentum features, and XGB+LGB ensemble stacking. Targets RB, WR, TE only (QB shipped in Phase 40). Sequential evaluation: features first, ensemble second. Requirements: ACCY-01, ACCY-02, ACCY-03, ACCY-04.

</domain>

<decisions>
## Implementation Decisions

### Target Positions and Success Criteria
- **D-01:** Target all 3 SKIP positions (RB, WR, TE) equally — OOF gaps are similar (-12% to -14%)
- **D-02:** Same ship gate as Phase 40: dual agreement (OOF + holdout both 4%+), per-position fantasy points MAE in half-PPR
- **D-03:** QB left as-is — Phase 40 model (75% holdout improvement) is final, not re-evaluated
- **D-04:** Per-position verdict: ship what passes, heuristic fallback for the rest. Phase succeeds if at least one more position flips from SKIP to SHIP

### Opportunity-Efficiency Decomposition
- **D-05:** Derived feature approach (not two-stage pipeline) — add efficiency metrics as model inputs to existing single-stage models. No error compounding from chained predictions
- **D-06:** Efficiency features with roll3 and roll6 variants (~12 per position):
  - RB: yards_per_carry, yards_per_target, td_rate (rushing_tds/carries), catch_rate (receptions/targets)
  - WR: yards_per_target, yards_per_reception, td_rate (receiving_tds/targets), catch_rate
  - TE: yards_per_target, yards_per_reception, td_rate (receiving_tds/targets), catch_rate
  - All computed from existing Silver usage columns with shift(1) → rolling(window).mean()

### TD Regression Features
- **D-07:** Two red zone expected TD features (both as separate model inputs):
  - Position-average: `rz_target_share_roll3 × POSITION_AVG_RZ_TD_RATE` (static constant per position)
  - Player-specific: `rz_target_share_roll3 × player_rz_td_rate_roll6` (player's own conversion rate)

### Role Momentum Features
- **D-08:** Three subtraction features computed from existing rolling columns (no new rolling computation):
  - `snap_pct_delta = snap_pct_roll3 - snap_pct_roll6` (breakout/demotion signal)
  - `target_share_delta = target_share_roll3 - target_share_roll6` (usage trend)
  - `carry_share_delta = carry_share_roll3 - carry_share_roll6` (RB-specific workload trend)

### Ensemble Strategy
- **D-09:** Sequential approach: add new features → re-run ship gate → add ensemble stacking → re-run ship gate. Measures contribution of each stage independently
- **D-10:** XGB + LGB + Ridge meta-learner per stat per position (drop CatBoost — no categorical features to justify it). ~38 base models for 3 positions + 14 Ridge meta-learners
- **D-11:** Two-stage ablation report: ship gate table after features-only, then again after ensemble. Natural pause point — if features alone ship a position, ensemble may be skipped for that position
- **D-12:** Conservative hyperparameters for LGB (same `LGB_CONSERVATIVE_PARAMS` from config.py). Optuna tuning only as escape hatch if all techniques fail to flip OOF

### Claude's Discretion
- How to structure the new feature computation (extend player_feature_engineering.py vs separate module)
- Exact position-average RZ TD rates (compute from historical data)
- SHAP re-selection strategy after adding new features (re-run vs append)
- LGB model factory implementation details
- CLI flags for stage selection (features-only vs features+ensemble)

</decisions>

<specifics>
## Specific Ideas

- Efficiency features use the same `shift(1) → rolling(window).mean()` pattern as existing Silver usage metrics
- Delta features (D-08) are pure arithmetic on existing _roll3 and _roll6 columns — zero risk of leakage
- The sequential evaluation (D-09) reuses the ship gate from Phase 40 (`ship_gate_verdict()`, `compute_position_mae()`, `print_ship_gate_table()`) — no new evaluation infrastructure needed
- LGB model factory follows `make_lgb_model()` pattern already in `ensemble_training.py`
- Ridge meta-learner follows `train_ridge_meta()` pattern from game-level ensemble

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 40 output (baseline to improve)
- `src/player_model_training.py` — `train_position_models()`, `player_walk_forward_cv()`, `run_player_feature_selection()`, `predict_player_stats()`, `ship_gate_verdict()`, `compute_position_mae()`, `generate_heuristic_predictions()`, `print_ship_gate_table()`
- `scripts/train_player_models.py` — CLI for training and ship gate evaluation
- `models/player/ship_gate_report.json` — Phase 40 results (QB SHIP, RB/WR/TE SKIP with OOF gaps)

### Feature assembly (where new features are added)
- `src/player_feature_engineering.py` — `assemble_player_features()`, `get_player_feature_columns()`, rolling feature patterns
- `src/player_analytics.py` — `compute_rolling_averages()` shift(1) → rolling pattern, `compute_usage_metrics()` for rz_target_share

### Ensemble patterns to adapt
- `src/ensemble_training.py` — `make_lgb_model()`, `train_ridge_meta()`, `assemble_oof_matrix()` — game-level ensemble patterns
- `src/config.py` — `LGB_CONSERVATIVE_PARAMS`, `HOLDOUT_SEASON`, `PLAYER_DATA_SEASONS`

### Evaluation
- `src/scoring_calculator.py` — `calculate_fantasy_points_df()` for MAE comparison
- `src/projection_engine.py` — `POSITION_STAT_PROFILE` defines stats per position

### Prior phase context
- `.planning/phases/40-baseline-models-ship-gate/40-CONTEXT.md` — Ship gate design, walk-forward CV, evaluation method decisions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `player_model_training.ship_gate_verdict()`: Dual agreement check with safety floor — reuse directly for both evaluation stages
- `player_model_training.train_position_models()`: Per-position per-stat XGB training — extend to accept LGB models too
- `player_model_training.run_player_feature_selection()`: SHAP per stat-type group — re-run after adding new features
- `ensemble_training.make_lgb_model()`: LGB factory with conservative params — reuse directly
- `ensemble_training.train_ridge_meta()`: Ridge meta-learner on OOF matrix — adapt for player-level stacking
- `player_feature_engineering.get_player_feature_columns()`: Auto-discovers numeric feature columns — new features included automatically if numeric

### Established Patterns
- **Rolling features**: shift(1) → rolling(window).mean() in `player_analytics.py` — same pattern for efficiency metrics
- **Delta features**: Simple subtraction of existing _roll3 and _roll6 columns — no new rolling computation
- **Ship gate re-run**: `train_player_models.py --holdout-eval` already runs the full pipeline — add flag for features-only vs ensemble mode
- **Model serialization**: JSON export with metadata — extend for LGB models

### Integration Points
- **New features added in**: `player_feature_engineering.assemble_player_features()` or a new feature computation step
- **Training pipeline**: `train_position_models()` extended to support LGB + Ridge stacking
- **Evaluation**: Same `ship_gate_verdict()` and `print_ship_gate_table()` — no changes needed
- **Output**: Models saved to `models/player/{position}/` alongside Phase 40 models

### Key Metrics to Beat (Phase 40 OOF)
- RB OOF: ML 5.218 vs Heuristic 4.633 (need ML < 4.448 for 4%+ improvement)
- WR OOF: ML 4.915 vs Heuristic 4.304 (need ML < 4.132)
- TE OOF: ML 3.666 vs Heuristic 3.283 (need ML < 3.152)

</code_context>

<deferred>
## Deferred Ideas

- Optuna hyperparameter tuning per position — escape hatch if conservative defaults fail
- CatBoost as third base model — add back if XGB+LGB ensemble diversity is insufficient
- Extending training data to 2016-2019 — if more data needed for OOF stability
- Sliding window experiment — if older seasons (2020) hurt OOF performance
- Team-total constraint enforcement — Phase 42
- Preseason mode — Phase 42
- MAPIE confidence intervals — Phase 42

</deferred>

---

*Phase: 41-accuracy-improvements*
*Context gathered: 2026-03-31*
