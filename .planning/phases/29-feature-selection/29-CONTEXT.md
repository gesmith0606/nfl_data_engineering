# Phase 29: Feature Selection - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Reduce ~303 features to an optimal subset (targeting 80-120) via correlation filtering and SHAP importance pruning. Selection runs inside walk-forward CV folds and never touches the 2024 holdout. Retrain XGBoost on the reduced set and backtest to measure improvement over v1.4 baseline (53.2% ATS).

</domain>

<decisions>
## Implementation Decisions

### Selection Pipeline
- **D-01:** Pipeline order: quick SHAP pre-rank → correlation filter (r > 0.90, keep higher-SHAP-ranked of each pair) → final SHAP pruning to target count
- **D-02:** Correlation threshold: r > 0.90 Pearson correlation triggers pair removal
- **D-03:** When dropping one from a correlated pair, keep the feature with higher SHAP importance (pre-ranked before correlation step)
- **D-04:** All selection steps run inside each walk-forward CV fold using only that fold's training data — no full-dataset selection

### Target Feature Count
- **D-05:** Use CV-validated cutoff — try multiple counts (60, 80, 100, 120, 150) and pick the one with best walk-forward CV MAE
- **D-06:** Feature budget ceiling remains 150 (from STATE.md)
- **D-07:** The optimal count is determined empirically, not fixed — could land anywhere in the tested range

### Holdout Protection
- **D-08:** 2024 season data is excluded from all feature selection operations — a test asserts this
- **D-09:** Selection metadata records which seasons were used for each fold's selection

### Retrain and Backtest
- **D-10:** After finding optimal feature count, retrain XGBoost spread + total models on the reduced feature set
- **D-11:** Run full backtest comparing reduced-feature XGBoost vs v1.4 baseline (303-feature XGBoost)
- **D-12:** Report ATS accuracy, O/U accuracy, and vig-adjusted profit at -110 for both configurations
- **D-13:** If reduced features don't improve or match baseline, investigate before proceeding to Phase 30

### Output Format
- **D-14:** Persist `SELECTED_FEATURES` list in `src/config.py` for Phase 30 to import
- **D-15:** Save detailed metadata to `models/feature_selection/metadata.json` with: selected features, drop reasons (correlation vs low importance), SHAP scores, correlated pairs, optimal cutoff, CV MAE at each cutoff
- **D-16:** `get_feature_columns()` in feature_engineering.py unchanged — the selection is applied downstream in model training, not at assembly time (assembly still produces all 303 features)

### Claude's Discretion
- SHAP computation method (TreeExplainer vs KernelExplainer)
- Exact implementation of CV-validated cutoff loop
- Test structure and organization
- How to handle features with zero variance in some CV folds
- Visualization of SHAP importance / correlation heatmap (optional CLI output)

</decisions>

<specifics>
## Specific Ideas

- The correlation step will primarily catch roll3/roll6 pairs (e.g., `diff_off_epa_per_play_roll3` and `diff_off_epa_per_play_roll6` are typically r > 0.90)
- The _std features may also correlate with their rolling counterparts
- SHAP TreeExplainer is the natural choice since we're using XGBoost (exact, not approximate)
- CV-validated cutoff should use the same walk-forward folds as model_training.py to ensure consistency

</specifics>

<canonical_refs>
## Canonical References

### Existing patterns
- `src/model_training.py` — `walk_forward_cv()` with 5 season-boundary folds, `HOLDOUT_SEASON` guard
- `src/feature_engineering.py` — `get_feature_columns()` returns 303 features, `assemble_multiyear_features()`
- `src/config.py` — `PREDICTION_SEASONS`, `HOLDOUT_SEASON=2024`, `TRAINING_SEASONS`, `CONSERVATIVE_PARAMS`

### Phase 28 outputs (inputs to this phase)
- `scripts/silver_player_quality_transformation.py` — produces player quality Silver data
- `data/silver/teams/player_quality/` — QB EPA, positional quality, injury impact per team per week
- 303 features total (283 original + 20 player features)

### Research
- `.planning/research/FEATURES.md` — correlation filter + SHAP recommended, r > 0.90 threshold
- `.planning/research/PITFALLS.md` — feature selection before holdout split burns the holdout; selection inside CV folds mandatory
- `.planning/research/ARCHITECTURE.md` — feature selection module details

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `walk_forward_cv()` in model_training.py: produces fold indices for 5 season-boundary splits — reuse for CV-validated cutoff
- `assemble_multiyear_features()` in feature_engineering.py: produces the full 303-feature matrix
- `get_feature_columns()`: returns feature column names (used to identify candidates)
- SHAP 0.49.1 installed in Phase 28 (TreeExplainer available)

### Established Patterns
- Walk-forward CV with `HOLDOUT_SEASON` exclusion (model_training.py)
- Config-driven feature/model settings (config.py)
- Model save/load with JSON + metadata sidecar (model_training.py)

### Integration Points
- `config.py`: Add `SELECTED_FEATURES` list
- `model_training.py`: Optionally filter features before training using `SELECTED_FEATURES`
- `scripts/backtest_predictions.py`: Retrain + backtest uses existing CLI

</code_context>

<deferred>
## Deferred Ideas

- Recursive feature elimination (RFE) — more expensive, overkill at this scale
- Boruta / BorutaSHAP — sophisticated but adds dependency and complexity
- Feature interaction detection — interesting but belongs in Phase 31 (advanced features)

</deferred>

---

*Phase: 29-feature-selection*
*Context gathered: 2026-03-25*
