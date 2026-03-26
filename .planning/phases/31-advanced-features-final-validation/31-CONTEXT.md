# Phase 31: Advanced Features & Final Validation - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Add momentum signals and adaptive EWM windows to the feature vector, measure their marginal value via ablation, and run the final sealed 2024 holdout comparison: v1.4 single-XGBoost vs Phase-30 ensemble vs Phase-31-full ensemble. Ship whichever configuration performs best.

</domain>

<decisions>
## Implementation Decisions

### Momentum Signal Design
- **D-01:** Compute win/loss streak (consecutive W/L count, resets on opposite result) and ATS streak (consecutive covers/non-covers) from Bronze schedules
- **D-02:** Lookback is last 3 games only — season cumulative already captured by existing `win_pct`
- **D-03:** Streaks are raw counts (uncapped) — let tree models decide where to split
- **D-04:** Include both binary ATS cover (rolling sum over last 3) AND continuous ATS margin (actual spread minus closing line) as features
- **D-05:** All momentum features use shift(1) lag — no game references its own result

### Adaptive EWM Windows
- **D-06:** EWM windows supplement (not replace) existing fixed roll3/roll6 — added alongside, then feature selection prunes redundant ones
- **D-07:** Compute EWM at Silver source level in `team_analytics.py` alongside existing rolling columns — consistent with where roll3/roll6 live
- **D-08:** Single halflife = 3 games — matches roll3 in recency emphasis, keeps feature growth manageable
- **D-09:** EWM applied to team-level metrics only: EPA, success rate, CPOE, red zone — not player-level (avoids feature explosion)
- **D-10:** After adding EWM features, re-run Phase 29's feature selection to update SELECTED_FEATURES with the expanded candidate set

### Validation & Ship Decision
- **D-11:** Ship bar is meaningful improvement: at least +1% ATS accuracy OR flipping vig-adjusted profit from negative to positive on 2024 holdout
- **D-12:** Ablation test: run holdout with ensemble + Phase 31 features vs ensemble without Phase 31 features — ship whichever is better
- **D-13:** Final comparison table shows three columns: v1.4 baseline, Phase-30 ensemble, Phase-31-full — on ATS accuracy, O/U accuracy, MAE, profit, plus per-season breakdown
- **D-14:** Extend `backtest_predictions.py` with `--holdout` flag that restricts to 2024 and prints the comparison table — no one-off script

### Claude's Discretion
- Exact EWM column naming convention (e.g., `_ewm3` suffix)
- How to structure the ablation in code (separate config or inline toggle)
- Whether to re-run feature selection as a subprocess or inline call
- Test organization for momentum and EWM features

</decisions>

<specifics>
## Specific Ideas

- ATS margin = `actual_margin - spread_line` (positive means covered) — derive from existing Bronze schedule columns `result` and `spread_line`
- Win streak resets on loss, loss streak resets on win — simple counter with sign (positive = winning streak, negative = losing streak) is an option
- EWM halflife=3 means the weight of a game 3 weeks ago is ~50% of the current weight — pandas `ewm(halflife=3)` handles this natively
- The three-column comparison table (v1.4 / Phase-30 / Phase-31) makes the marginal contribution of each milestone phase visible
- If Phase 31 features hurt, ship Phase 30 ensemble as v2.0 — still a major upgrade over v1.4

</specifics>

<canonical_refs>
## Canonical References

### Feature engineering
- `src/feature_engineering.py` — `assemble_game_features()`, `get_feature_columns()` with leakage guards, `_read_bronze_schedules()` for schedule data access
- `src/team_analytics.py` — existing roll3/roll6 computation pattern, where EWM columns will be added
- `src/player_analytics.py` — existing rolling window pattern (EWM NOT added here per D-09)

### Feature selection
- `src/feature_selector.py` — `FeatureSelectionResult`, `select_features_for_fold()` — must re-run after adding new features (D-10)
- `scripts/run_feature_selection.py` — CLI for updating SELECTED_FEATURES in config.py

### Model infrastructure
- `src/ensemble_training.py` — `train_ensemble()`, `load_ensemble()`, `predict_ensemble()` from Phase 30
- `src/config.py` — `SELECTED_FEATURES`, `HOLDOUT_SEASON=2024`, `VALIDATION_SEASONS`

### Backtesting
- `scripts/backtest_predictions.py` — existing `--ensemble` flag, `run_comparison_backtest()`, evaluation functions — extend with `--holdout` per D-14
- `src/prediction_backtester.py` — `evaluate_ats()`, `evaluate_ou()`, `compute_profit()`, `evaluate_holdout()`

### Bronze data
- Bronze schedules at `data/bronze/schedules/season=YYYY/` — contains `result`, `spread_line`, `total_line` needed for ATS/streak derivation

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_read_bronze_schedules(season)` in feature_engineering.py — already reads schedule data with result/spread_line/total_line columns
- `team_analytics.py` roll3/roll6 pattern — EWM columns follow the same groupby-team, sort-by-week, shift(1) pattern
- `backtest_predictions.py` `run_comparison_backtest()` — already prints side-by-side table, extend for three-way comparison
- `evaluate_holdout()` in prediction_backtester.py — existing holdout evaluation function
- Feature selection pipeline from Phase 29 — re-runnable to incorporate new features

### Established Patterns
- All derived features use shift(1) lag at Silver level — momentum features must follow this
- Feature columns filtered by `get_feature_columns()` leakage guard — new features must pass the guard
- Bronze schedules joined in `assemble_game_features()` step 6 — momentum features should be computed before this join

### Integration Points
- `feature_engineering.py`: Add momentum feature computation in `assemble_game_features()` before schedule join
- `team_analytics.py`: Add EWM columns alongside existing roll3/roll6
- `config.py`: SELECTED_FEATURES updated after re-running feature selection
- `backtest_predictions.py`: Add `--holdout` flag and three-way comparison table

</code_context>

<deferred>
## Deferred Ideas

- Bayesian stacking (replace Ridge with Bayesian Ridge) — future enhancement
- Regime detection (pre/post bye, playoff mode) — could be its own phase
- Pace-adjusted stats — requires additional data modeling
- In-season model retraining — v3.0 production infra

</deferred>

---

*Phase: 31-advanced-features-final-validation*
*Context gathered: 2026-03-25*
