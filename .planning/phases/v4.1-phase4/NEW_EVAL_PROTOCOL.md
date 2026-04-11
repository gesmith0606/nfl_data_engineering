# Production-Faithful Evaluation (PFE) Protocol

**Phase:** v4.1-p4
**Status:** Design complete, implementation pending
**Author:** Architect agent, 2026-04-10

## 1. Root Cause Analysis — Why WFCV Lies

WFCV and production use **two completely different heuristic baselines** built on **two completely different feature assemblies**. The residual models are trained against baseline A, evaluated in CV against baseline A, but deployed against baseline B. CV MAE has no causal relationship to production MAE.

### The three pipelines in play

| Pipeline | Feature source | Heuristic function | `_usage_multiplier` receives |
|---|---|---|---|
| **Production backtest** (`scripts/backtest_projections.py`) | `build_silver_features()` → `compute_usage_metrics(hist)` called **without `snap_df`** | `generate_weekly_projections()` (`src/projection_engine.py`) | `silver_df` has NO `snap_pct` column → line 160 `if usage_col not in df.columns: return 1.0` (neutral) |
| **WFCV in `train_residual_model`** (`src/hybrid_projection.py:555`) | `assemble_multiyear_player_features()` | `generate_heuristic_predictions()` (`src/player_model_training.py:1051`) | Column present but blanked by `_SAME_WEEK_RAW_STATS`. Post-Phase 3 fix (line 1087) returns neutral 1.0 when all-NaN, but this path doesn't apply `_matchup_factor` or ceiling shrinkage at all |
| **Training in `train_and_save_residual_models`** (`src/hybrid_projection.py:794`) | `assemble_multiyear_player_features()` | `compute_production_heuristic()` (`src/unified_evaluation.py:55`) | Same blanked `snap_pct`; pre-Phase 3 fix produced 0.03 pts for QB; post-fix still not equal to production path |

### Hypotheses verdicts

- **H1 CONFIRMED (primary)**: Heuristic baselines differ between WFCV and production. The Phase 3 fix only patches the call site in `player_model_training.py:1087`, not `projection_engine.py:150` at the function level. Three call paths, only one guard.
- **H2 CONFIRMED (secondary)**: `assemble_multiyear_player_features` carries same-week stats blanked/lagged differently than `build_silver_features` computes them. Feature distributions differ even for identically-named columns.
- **H3 CONFIRMED**: WFCV metric uses one heuristic baseline, production metric uses a different one. Same residual model = different bases = different MAE.
- **H4 CONFIRMED (secondary)**: WFCV val folds (2022-2024) are in-sample for production models training on 2016-2024. 2025 has no `qbr_*` data (100% NaN for QB), different injury timing, different Vegas coverage.

### Concrete file/line references

- `src/projection_engine.py:150-167` — `_usage_multiplier`, still unguarded in the function itself
- `src/player_feature_engineering.py:63-69` — `_SAME_WEEK_RAW_STATS` blanking rule
- `src/player_analytics.py:89` — `snap_pct` only populated when `snap_df` is passed
- `src/player_model_training.py:1087` — Phase 3 guard (WFCV path only)
- `src/unified_evaluation.py:55` — training-time heuristic, NOT identical to production
- `src/hybrid_projection.py:595` — WFCV calls `generate_heuristic_predictions`
- `src/hybrid_projection.py:913` — Training calls `compute_production_heuristic` — different function
- `scripts/backtest_projections.py:242` — production assembles via `compute_usage_metrics(hist)` and passes only `silver_df` to `apply_residual_correction`

**The bug class is not "a hyperparameter issue". It is: three different feature assemblies × three different heuristic implementations, with no contract between them. Every experiment validated on WFCV is validating a strictly different model than the one shipped.**

## 2. Protocol Specification — Production-Faithful Eval (PFE)

**Principle**: the only evaluation that can predict production MAE is one that calls `run_backtest()` from `scripts/backtest_projections.py` with `use_ml=True`. Everything else is a proxy whose correlation to production has been empirically refuted.

### The protocol

| Item | Specification |
|---|---|
| **Feature assembly** | `build_silver_features()` for `silver_df` AND `assemble_player_features(season)` for `feature_df` — the exact pair that `run_backtest(full_features=True, use_ml=True)` uses |
| **Heuristic** | `generate_weekly_projections()` — NO other heuristic permitted |
| **Residual application** | `apply_residual_correction()` via `ml_projection_router.generate_ml_projections()` |
| **Dataset** | 2024 full season (weeks 3-18) as **iteration set** (fast, in-distribution). 2025 full season as **sealed ship gate** (touched at most once per experiment) |
| **Metric** | Position MAE and bias, overall MAE and bias, split by `projection_source` |
| **Ship gate** | Ship new residual model **only if ALL four hold**: (1) 2024 iter position MAE improves by ≥ 0.10 vs current prod, (2) 2024 bias magnitude ≤ 0.5 pts, (3) 2025 sealed-holdout position MAE improves by ≥ 0.10 AND overall MAE doesn't regress, (4) 2025 bias magnitude ≤ 1.0 pts |
| **Forbidden** | Any eval whose heuristic is not `generate_weekly_projections`. Any eval whose features are not assembled via `build_silver_features`/`assemble_player_features`. WFCV numbers may be reported as diagnostics only, never as a ship criterion |

### Runnable commands

```bash
source venv/bin/activate

# Iteration eval (2024, ~3-4 min with cached data)
python scripts/backtest_projections.py \
    --seasons 2024 --weeks 3-18 \
    --scoring half_ppr --ml --full-features \
    --output-dir output/eval/iter_<experiment_name>

# Sealed ship-gate eval (2025, run at most once per candidate model)
python scripts/backtest_projections.py \
    --seasons 2025 --weeks 3-18 \
    --scoring half_ppr --ml --full-features \
    --output-dir output/eval/gate_<experiment_name>
```

## 3. Migration Plan

| Experiment | Current WFCV claim | Re-run on PFE? | Priority |
|---|---|---|---|
| WR LGB-SHAP-60 (current prod) | -37% vs heuristic | **Re-measure** — WFCV number is meaningless | P0 |
| TE LGB-SHAP-60 (current prod) | -33% vs heuristic | **Re-measure** | P0 |
| RB v2 pruned LGB | -25.1% / 2.44 WFCV MAE | Will not pass gate (+0.47 regression) | P1 — document SKIP |
| QB v2 pruned LGB | -72% WFCV, 4.07 "holdout" | Already proven catastrophic (+11.33 bias) | Done — SKIP |
| LGB vs Ridge head-to-head | "LGB wins 7-17%" | **Re-run PFE** — key regression test | **P0** |
| Any Phase 1/Phase 2 ablation | various | Re-validate before further iteration | P2 |

## 4. Tooling Needs

| Tool | Purpose | Implementation | Runtime |
|---|---|---|---|
| `scripts/production_eval.py` | Wrap `run_backtest()` with opinionated defaults, cache features, print delta vs baseline | ~150 lines. Accepts `--baseline <name>`, `--experiment <name>`. Writes `output/eval/<experiment>/summary.json` | < 5 min |
| `scripts/swap_and_eval.py` | Temporarily swap residual model file, run PFE, restore original, report delta | Uses `joblib.load`/`dump`, symlink rename under `models/residual/_sandbox/`. Reverts on error via `try/finally` | inherits |

**Recommended**: `pytest` contract test in `tests/test_eval_contract.py` that asserts `compute_production_heuristic(...)` and `generate_weekly_projections(...)` produce numerically identical outputs on a fixture player-week. This would have caught the Phase 3 QB bug.

## 5. Example Application — "Evaluate LGB vs Ridge for WR residual"

### Old (broken) workflow
1. Run `train_residual_model` WFCV on each, pick lower mean_mae
2. Save best
3. Ship

### New PFE workflow
1. Train both candidates, save to `models/residual/_sandbox/wr_lgb/` and `models/residual/_sandbox/wr_ridge/`
2. Use `swap_and_eval.py` to atomically swap into production path, run `production_eval.py --seasons 2024 --experiment wr_lgb_candidate`, restore
3. Compare `output/eval/iter_wr_lgb_candidate/summary.json` vs `output/eval/iter_baseline/summary.json`. Both must beat baseline on 2024 MAE by ≥ 0.10
4. For survivor, run PFE once on 2025. If it clears ship gate, promote. If not, revert
5. Run `pytest tests/test_eval_contract.py`

**Expected outcome on current evidence**: Ridge wins. The +0.8 MAE regression on WR/TE is the honest measurement; WFCV's "LGB wins 7-17%" is a measurement artifact of the wrong baseline.

## Constraints Broken (to fix)

The codebase has **three heuristic functions claiming to compute "the" production heuristic**. The architectural invariant that must hold: there is ONE heuristic function, called from all paths, and a contract test that catches any divergence.

**Immediate refactor target**: delete `generate_heuristic_predictions` and `compute_production_heuristic`. Make both WFCV and training call `generate_weekly_projections` directly, with whatever adapter is needed for their specific inputs.

## Next Steps

1. **P0 (this session)**: Run PFE on current production WR/TE LGB models vs a fresh Ridge 60f candidate. Settles the Ridge vs LGB question.
2. **P0 (this session)**: If Ridge wins, revert to Ridge and commit.
3. **P1 (next session)**: Build `scripts/production_eval.py` and `scripts/swap_and_eval.py` helpers.
4. **P1**: Write `tests/test_eval_contract.py` for heuristic function equivalence.
5. **P2**: Refactor to single heuristic function (delete duplicates).
6. **P2**: Re-validate all surviving v4.1 experiments through PFE.
