# Heuristic Consolidation — Phase 59

## Status: COMPLETE (2026-06-12)

## Background

Three heuristic implementations existed (documented in CLAUDE.md Known Issues):
1. `generate_weekly_projections()` in `projection_engine.py` — production inference
2. `generate_heuristic_predictions()` in `player_model_training.py` — WFCV / ship-gate
3. `compute_production_heuristic()` in `unified_evaluation.py` — residual training

`compute_heuristic_baseline()` in `projection_engine.py` was designated the single
source of truth. `compute_production_heuristic` (item 3) was already a thin wrapper
around `compute_heuristic_baseline` before this phase — it was correct.

`generate_heuristic_predictions` (item 2) was the remaining true duplicate.

---

## Divergence Catalog

### Divergence 1: `pred_{stat}` used global RECENCY_WEIGHTS instead of per-position

**Location**: `player_model_training.py:generate_heuristic_predictions`, line ~1099  
**Bug**: `_weighted_baseline(result_df, stat)` called WITHOUT `position` argument  
**Effect**: Used global `RECENCY_WEIGHTS` (roll3=0.30, roll6=0.15, std=0.55) for
ALL positions, ignoring `POSITION_RECENCY_WEIGHTS`:
- WR: global (roll3=0.30) vs correct (std=1.00 pure) — 45% weight mismatch
- QB: global (roll3=0.30) vs correct (std=0.85, roll3=0.10) — diverged
- TE: global (roll3=0.30) vs correct (std=0.85, roll3=0.15) — diverged
- RB: global (roll3=0.30) vs correct (roll3=0.30) — SAME, no divergence

**Measured divergence** on 200-row synthetic sample:
- WR: mean abs delta 1.865 pts, max delta 7.45 pts
- QB: mean abs delta 1.964 pts, max delta 2.72 pts

**Callers affected**:
- `scripts/train_player_models.py`: `compute_position_mae(heuristic_oof)` — ship-gate
  heuristic MAE was inaccurate (too low for WR/QB because rolling averages inflated
  the baseline vs pure-std)
- `src/bayesian_projection.py:_cv_residual_fold`: `compute_fantasy_points_from_preds(heur_df)`
  re-scored pred_{stat} to get heuristic_pts for residual training — training targets
  were systematically wrong by ~1.9 pts mean

**Intentional?** No. `compute_heuristic_baseline` was updated to use
`POSITION_RECENCY_WEIGHTS` in v4.2 (2026-06-10). `generate_heuristic_predictions`
was not updated at the same time, causing drift.

---

### Divergence 2: `pred_{stat}` did not apply `_apply_td_regression`

**Location**: `player_model_training.py:generate_heuristic_predictions`  
**Bug**: `_apply_td_regression` was applied in `compute_heuristic_baseline` but
not in the `pred_{stat}` building loop in `generate_heuristic_predictions`.  
**Effect**: TD stats in `pred_{stat}` used raw rolling averages without blend toward
yardage-implied expectation. For WR (weight=0.75) and QB (weight=0.75), receiving_tds
and passing_tds respectively were over-projected for high-yardage, low-TD players.

**Callers affected**: Same as Divergence 1 (bayesian residual path re-scores pred_{stat}).

**Intentional?** No. `_apply_td_regression` was added to `compute_heuristic_baseline`
in v4.2 without propagating to `generate_heuristic_predictions`.

---

### Divergence 3: `pred_{stat}` does NOT include ceiling shrinkage, bias correction, floor boost

**Location**: `player_model_training.py:generate_heuristic_predictions`  
**Status**: INTENTIONAL-ARCHITECTURAL (not fixed, documented)

`compute_heuristic_baseline` applies:
- `PROJECTION_CEILING_SHRINKAGE` (12/18/23 pt thresholds)
- `POSITION_CEILING_SHRINKAGE` (WR/TE: additional 12% at 12+ pts)
- `POSITION_BIAS_CORRECTION` (QB: +2.3 pts additive)
- `LOW_PROJECTION_FLOOR_BOOST` (position-specific low-projection lift)

These are total-level adjustments, not per-stat adjustments — they cannot be
meaningfully distributed back to individual `pred_{stat}` columns.

**Resolution**: The `heuristic_pts` column in the returned DataFrame (computed via
`compute_heuristic_baseline`) includes all these adjustments. Callers that need
the authoritative total MUST use `heuristic_pts`, not re-score `pred_{stat}`.
The docstring of `generate_heuristic_predictions` was updated to document this.

**Impact of residual divergence on bayesian path**: even after fixing D1+D2, the
bayesian path using `compute_fantasy_points_from_preds(heur_df)` will still differ
from `heuristic_pts` for players above the ceiling shrinkage thresholds. The correct
fix for that caller is to use `heur_df["heuristic_pts"]` directly (a bayesian_projection.py
change outside Phase 59 scope). This remaining divergence is documented in the code.

---

### Divergence 4: `run_production_residual_experiment.py` has stale local copy

**Location**: `scripts/run_production_residual_experiment.py:compute_production_heuristic_points`  
**Status**: DOCUMENTED, not fixed (experiment/one-off script outside production path)

This script (Phase 54 experiment) contains its own inline heuristic that predates
both `POSITION_RECENCY_WEIGHTS` (v4.2) and `_apply_td_regression`. It is NOT called
by any production code path. It is archived experiment infrastructure.

---

### Divergence 5: `unified_evaluation.py` module docstring listed stale RECENCY_WEIGHTS

**Status**: FIXED — docstring updated to reflect POSITION_RECENCY_WEIGHTS and full
step list (TD regression, POSITION_CEILING_SHRINKAGE, POSITION_BIAS_CORRECTION,
LOW_PROJECTION_FLOOR_BOOST).

---

## Changes Made

### `src/player_model_training.py` — `generate_heuristic_predictions`

1. Added `_apply_td_regression` to the import block.
2. Changed `_weighted_baseline(result_df, stat)` → `_weighted_baseline(result_df, stat, position)` so per-position weights are used.
3. Restructured the `pred_{stat}` build loop to collect a dict first, then apply `_apply_td_regression` via a `proj_`/`pred_` prefix rekey, then assign.
4. Updated docstring to document the ceiling shrinkage gap in `pred_{stat}` and direct callers to use `heuristic_pts` for the authoritative total.

### `src/unified_evaluation.py`

1. Updated module docstring step list to reflect full pipeline (9 steps including TD regression and post-scoring adjustments).
2. Updated `compute_production_heuristic` docstring to defer to `compute_heuristic_baseline` for the step list.

### `tests/test_heuristic_contract.py`

Added `TestGenerateHeuristicPredictionsDelegation` class (4 new tests):
1. `test_heuristic_pts_equals_canonical_wr` — heuristic_pts == compute_heuristic_baseline to 1e-9 for WR
2. `test_heuristic_pts_equals_canonical_qb` — same for QB
3. `test_delegation_via_monkeypatch` — monkeypatches compute_heuristic_baseline, verifies it is called
4. `test_pred_stat_uses_position_recency_weights_wr` — pred_receiving_yards equals pure-std baseline for WR

---

## Equivalence Proof

### `heuristic_pts` (Divergences 1 and 2 fixed — ceiling shrinkage gap intentional)

| Metric | Before | After |
|--------|--------|-------|
| heuristic_pts == canonical (WR) | max_diff = 0.00e+00 | max_diff = 0.00e+00 |
| heuristic_pts == canonical (QB) | max_diff = 0.00e+00 | max_diff = 0.00e+00 |

`heuristic_pts` was already correct before Phase 59 — it delegated to
`compute_heuristic_baseline` before this phase. The fix ensures the `pred_{stat}`
columns (used by WFCV/ship-gate re-scoring) are also internally consistent.

### `pred_{stat}` re-score divergence (residual gap: ceiling shrinkage etc. not applied)

| Metric | Before fix | After fix |
|--------|-----------|-----------|
| WR pred_stat re-score max_diff vs canonical | 7.45 pts | 4.22 pts |
| WR pred_stat re-score mean_diff vs canonical | 1.86 pts | 0.60 pts |
| QB pred_stat re-score max_diff vs canonical | 2.72 pts | 2.72 pts |
| QB pred_stat re-score mean_diff vs canonical | 1.96 pts | 0.97 pts |

After fix, remaining divergence (0.60 pts mean WR, 0.97 pts mean QB) is entirely
due to ceiling shrinkage/bias correction/floor boost which are total-level adjustments
that cannot be split across stats (Divergence 3, intentional).

---

## Test Results

- `tests/test_heuristic_contract.py`: 17 passed (was 13, +4 new Phase 59 tests)
- Full suite: 2487 passed, 1 skipped (0 new failures introduced)

---

## Remaining Known Issues (not in Phase 59 scope)

1. `bayesian_projection.py`: calls `compute_fantasy_points_from_preds(heur_df)` instead of
   `heur_df["heuristic_pts"]` — will compute residuals without ceiling shrinkage.
   Fix: replace with `heur_df["heuristic_pts"]` in that caller. (Scope: bayesian_projection.py)

2. `scripts/run_production_residual_experiment.py`: stale inline heuristic (Phase 54
   experiment, not production). Replace if ever re-run.

3. THREE duplicate heuristic functions: now reduced to TWO effective implementations
   after this phase (compute_heuristic_baseline = canonical; compute_production_heuristic
   = thin wrapper; generate_weekly_projections = production with Vegas/bye/injury;
   generate_heuristic_predictions = WFCV wrapper now correctly delegating for the total).
   The "known issues" entry in CLAUDE.md can be updated to reflect resolution.
