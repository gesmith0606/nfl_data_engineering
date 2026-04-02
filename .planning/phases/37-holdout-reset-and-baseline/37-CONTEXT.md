# Phase 37: Holdout Reset and Baseline - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

The evaluation framework uses 2025 as the sealed holdout with a documented ensemble baseline, enabling honest model comparison going forward. This phase rotates the holdout config, retrains the ensemble, updates tests, and documents the new baseline metrics.

</domain>

<decisions>
## Implementation Decisions

### Config rotation
- **D-01:** Change `HOLDOUT_SEASON` from 2024 to 2025 in `src/config.py`
- **D-02:** Compute `TRAINING_SEASONS`, `VALIDATION_SEASONS`, and `PREDICTION_SEASONS` automatically from `HOLDOUT_SEASON` — no more hardcoded lists. Formula: `PREDICTION_SEASONS = range(2016, HOLDOUT_SEASON + 1)`, `TRAINING_SEASONS = range(2016, HOLDOUT_SEASON)`, `VALIDATION_SEASONS = [s for s in range(2019, HOLDOUT_SEASON)]`
- **D-03:** Document the current 2024 baseline metrics (53.0% ATS, +$3.09 profit, +1.2% ROI) BEFORE changing config — this is the reference point for Phase 38 ablation comparison
- **D-04:** The config change and retraining must be atomic — never evaluate the old model against the new holdout or vice versa

### Ensemble retraining
- **D-05:** Run `train_ensemble.py` immediately after config change to retrain on 2016-2024 (2025 excluded by holdout guard)
- **D-06:** Training now includes 2024 data (was previously sealed) — this is 1 extra season of training data, which should marginally improve the model
- **D-07:** No hyperparameter re-tuning (`--tune`) in this phase — use existing P30 ensemble hyperparameters. Re-tuning is a separate concern and would muddy the baseline comparison
- **D-08:** Save retrained model to `models/ensemble/` (overwrites v2.1 model — this is intentional)

### Baseline establishment
- **D-09:** Run `backtest_predictions.py --holdout` against sealed 2025 to produce ATS accuracy, profit, ROI, and CLV metrics
- **D-10:** Document the 2025 baseline in a markdown file at `.planning/phases/37-holdout-reset-and-baseline/BASELINE.md` with exact metrics. This is the reference for Phase 38's ship-or-skip decision
- **D-11:** If 2025 holdout ATS < 50% (below random), investigate before proceeding — likely a data issue, not a model issue

### Test updates
- **D-12:** All 20 test files that reference `2024` as holdout must be updated to import `HOLDOUT_SEASON` from config instead of hardcoding. This makes future rotations a one-line change
- **D-13:** Tests that hardcode `TRAINING_SEASONS` or `VALIDATION_SEASONS` lists must also import from config
- **D-14:** Run full test suite after updates — all 594+ tests must pass

### Claude's Discretion
- Exact order of test file updates
- Whether to batch test updates into one commit or per-file
- Baseline document format beyond the required metrics
- Whether to run `--holdout` with `--ensemble` flag or default

</decisions>

<specifics>
## Specific Ideas

- The holdout rotation is the highest-risk operation in v2.2 — contamination (training on 2025 data) would invalidate all future evaluation
- Document 2024 baseline FIRST, then change config — the sequence is critical
- 2025 injuries are absent (Phase 35 finding) — baseline metrics will reflect this gap. It's a fair comparison since ablation in Phase 38 will face the same gap

</specifics>

<canonical_refs>
## Canonical References

### Config and holdout
- `src/config.py` — `HOLDOUT_SEASON=2024`, `TRAINING_SEASONS`, `VALIDATION_SEASONS`, `PREDICTION_SEASONS` (lines 408-413)
- `src/ensemble_training.py` — holdout guard, walk-forward CV, OOF predictions
- `src/model_training.py` — holdout guard
- `src/feature_selector.py` — holdout guard
- `src/prediction_backtester.py` — `LEAKAGE_THRESHOLD=0.58`, holdout evaluation

### Training and evaluation
- `scripts/train_ensemble.py` — Ensemble training CLI
- `scripts/backtest_predictions.py` — `--holdout` flag for sealed evaluation, `--ensemble` for ensemble dispatch

### Research
- `.planning/research/SUMMARY.md` — Pitfall 2 (holdout contamination), Pitfall 3 (stale model), Pitfall 6 (no baseline before ablation)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `HOLDOUT_SEASON` constant propagates to all ML modules via import — single-point change
- `train_ensemble.py`: proven CLI, saves to `models/ensemble/`
- `backtest_predictions.py --holdout`: produces full evaluation metrics

### Established Patterns
- Holdout guard: `if season == HOLDOUT_SEASON: raise` in training modules
- `LEAKAGE_THRESHOLD = 0.58`: auto-detects if ATS exceeds reasonable bounds
- Walk-forward CV: temporal splits respecting season boundaries

### Integration Points
- Config change affects: `ensemble_training.py`, `model_training.py`, `feature_selector.py`, `prediction_backtester.py`, `feature_engineering.py`
- 20 test files reference holdout/2024 — all need updating
- Phase 38 ablation consumes the baseline metrics from this phase

</code_context>

<deferred>
## Deferred Ideas

- Optuna hyperparameter re-tuning on expanded training data — separate concern, would muddy baseline comparison
- Automatic holdout rotation schedule — out of scope per REQUIREMENTS.md

</deferred>

---

*Phase: 37-holdout-reset-and-baseline*
*Context gathered: 2026-03-29*
