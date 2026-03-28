# Phase 34: CLV Tracking + Ablation - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Model quality is measured by CLV, and market features are shipped only if they improve the sealed 2024 holdout. Add CLV metrics to the backtester, run ablation comparing v2.0 baseline vs v2.0+market features, produce SHAP importance report, and make ship-or-skip decision.

</domain>

<decisions>
## Implementation Decisions

### Ablation methodology
- **D-01:** Full ablation: retrain ensemble from scratch with market features as candidates in the feature selection pipeline — do not manually add features to the P30 set. Re-run `run_feature_selection.py` with market_data Silver source included, then retrain ensemble, then compare holdout results
- **D-02:** The ablation trains on 2016-2021 (where market data exists) and evaluates on 2024 holdout (where market data does NOT exist — NaN). This tests whether market-informed feature selection improves the model even when market features are unavailable at prediction time
- **D-03:** If market features are selected by SHAP but NaN for 2022-2024, XGBoost/LightGBM/CatBoost handle NaN natively — no imputation needed. Ridge meta-learner gets NaN-filled to 0 (existing behavior)
- **D-04:** Create a dedicated ablation script `scripts/ablation_market_features.py` that orchestrates: (1) baseline P30 holdout eval, (2) re-run feature selection with market data, (3) retrain ensemble with selected features, (4) holdout eval, (5) comparison report

### CLV computation source
- **D-05:** Use nflverse `spread_line` already present in the assembled game features DataFrame — no new data join required. CLV = `predicted_margin - spread_line` (model's predicted home margin minus closing line)
- **D-06:** CLV is computed in `prediction_backtester.py` as a new function `evaluate_clv()` that takes the same DataFrame used by `evaluate_ats()`
- **D-07:** CLV metrics added to the backtest summary report (both CLI output and any saved JSON/CSV): `mean_clv`, `pct_beating_close`, `clv_by_season`, `clv_by_tier`

### Ship-or-skip implementation
- **D-08:** If market features improve holdout ATS accuracy by any amount (even 0.1%), ship them — accuracy is the priority, and even marginal improvements compound over a season
- **D-09:** If market features do NOT improve holdout ATS: exclude them from the production model by NOT updating `metadata.json` with market-selected features. The P30 ensemble remains production. CLV tracking still ships.
- **D-10:** The ship-or-skip decision is documented in the ablation output report, not encoded as a config flag — it's a one-time decision for v2.1, not a runtime toggle
- **D-11:** If shipped, update `metadata.json` with the new feature set. The ensemble training pipeline reads features from metadata, not config.py (per v2.0 decision)

### Opening spread SHAP dominance
- **D-12:** If `opening_spread` exceeds 30% SHAP importance: still ship it if holdout ATS improves. The goal is maximum accuracy, not model purity. A market-informed model that wins more is better than a "pure performance" model that wins less.
- **D-13:** Log the SHAP importance distribution in the ablation report so the dominance level is transparent and documented for future analysis
- **D-14:** If opening_spread dominates AND holdout does NOT improve: this confirms the model already captures market signal indirectly. Document this finding.

### CLV reporting format
- **D-15:** CLV by confidence tier: reuse existing tier thresholds (high ≥3.0, medium ≥1.5, low <1.5) from the prediction pipeline
- **D-16:** CLV by season: one row per season with mean CLV, pct_beating_close, and game count — same structure as `compute_season_stability()` output
- **D-17:** Positive CLV = model line was closer to the final outcome than the closing line (good). Negative CLV = closing line was closer (bad). Report both mean and median to handle outlier games.

### Claude's Discretion
- Exact ablation script structure and CLI arguments
- SHAP visualization format (text table vs plot)
- How to handle the edge case where feature selection with market data selects fewer features than P30
- Logging and progress reporting during ablation

</decisions>

<specifics>
## Specific Ideas

- Accuracy is the overriding goal — ship market features if they improve holdout by any amount
- The ablation must be honest: train on 2016-2021 (market data available), predict on 2024 (market data NaN). This is the real-world scenario for 2022+ predictions.
- CLV is the gold standard metric for betting model evaluation — even if the model doesn't improve ATS, CLV tracking adds permanent value for model monitoring

</specifics>

<canonical_refs>
## Canonical References

### Existing backtester
- `src/prediction_backtester.py` — `evaluate_ats()`, `evaluate_holdout()`, `compute_season_stability()`, `compute_profit()`, `VIG_WIN/VIG_LOSS` constants
- `scripts/backtest_predictions.py` — Backtest CLI with `--ensemble` flag, summary report output

### Feature selection
- `scripts/run_feature_selection.py` — SHAP-based feature selection with walk-forward CV, per-fold isolation
- `src/feature_engineering.py` — `get_feature_columns()`, `_PRE_GAME_CONTEXT`, Silver source loop

### Ensemble training
- `scripts/train_ensemble.py` — XGB+LGB+CB+Ridge stacking, `--tune` flag for Optuna, metadata.json output
- `src/config.py` — `HOLDOUT_SEASON = 2024`, confidence tier thresholds

### Requirements
- `.planning/REQUIREMENTS.md` §CLV-01, §CLV-02, §CLV-03, §LINE-04 — CLV and ablation requirements

### Prior phase outputs
- `src/market_analytics.py` — Silver market_data transform (Phase 33)
- `scripts/bronze_odds_ingestion.py` — Bronze odds pipeline (Phase 32)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evaluate_ats()` returns DataFrame with `predicted_margin` and `spread_line` — CLV is a one-liner: `df["clv"] = df["predicted_margin"] - df["spread_line"]`
- `compute_season_stability()` pattern: groupby season, compute metrics per group — clone for CLV by season
- `evaluate_holdout()` with leakage guard — reuse for ablation holdout eval
- `compute_profit()` — reuse for ablation profit comparison

### Established Patterns
- Backtest CLI: `scripts/backtest_predictions.py` with `--ensemble` flag, JSON output
- Feature selection: walk-forward CV with SHAP, per-fold isolation, holdout exclusion
- Ensemble metadata: `data/models/ensemble_metadata.json` stores selected features

### Integration Points
- `prediction_backtester.py`: add `evaluate_clv()` function
- `scripts/backtest_predictions.py`: add CLV section to summary output
- `scripts/run_feature_selection.py`: no changes needed — market features are already in Silver, feature selection auto-discovers them
- `data/models/ensemble_metadata.json`: updated only if ablation passes

</code_context>

<deferred>
## Deferred Ideas

- No-vig implied probability CLV — v2.2 Betting Framework
- Automated ablation pipeline (re-run on new data) — v3.0 Production Infra
- CLV-weighted bet sizing — v2.2 Betting Framework
- Rolling CLV monitoring for model drift detection — v3.0

</deferred>

---

*Phase: 34-clv-tracking-ablation*
*Context gathered: 2026-03-28*
