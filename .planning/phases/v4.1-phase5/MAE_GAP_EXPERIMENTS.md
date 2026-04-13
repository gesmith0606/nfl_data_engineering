# MAE Gap Experiments — v4.1 Phase 5

**Date**: 2026-04-13
**Goal**: Close 0.25 MAE gap between Ridge 60f+graph residuals (5.05 MAE) and v3.2 baseline (4.80 MAE)
**Evaluation**: Production backtest 2022-2024, weeks 3-18, half-PPR

## Baseline

```
Experiment: baseline_2022_2024 (seasons 2022,2023,2024)
Overall MAE:  5.31  (actual, higher than stated 5.05 — reflects full 48-week eval)
Overall Bias: +0.12

Per-Position MAE:
  QB: 7.03 (bias +0.05)  — XGBoost SHIP
  RB: 5.25 (bias -0.02)  — LGB SHIP (override)
  WR: 5.36 (bias +0.26)  — Ridge HYBRID (override)
  TE: 4.17 (bias +0.07)  — Ridge HYBRID (override)

By Projection Source:
  hybrid: 4.96
  ml: 5.88
```

## Pre-Experiment Diagnostics

Before running the 4 suspects, a heuristic-only baseline was measured:

```
Experiment: baseline_no_ml (--no-ml flag)
Overall MAE:  4.87
Overall Bias: -0.73

Per-Position:
  QB: 6.58 (bias -2.47)
  RB: 5.00 (bias -0.50)
  WR: 4.78 (bias -0.38)
  TE: 3.74 (bias -0.71)
```

**Critical finding**: The ML/residual layer is DEGRADING performance by +0.44 MAE.
The heuristic-only baseline (4.87) is better than the ML-augmented (5.31).

Root cause analysis revealed that WR/TE Ridge residual models produce mean corrections
of +0.80 and +0.66 respectively, while the actual heuristic bias is only -0.38 (WR)
and -0.71 (TE). The models systematically over-correct — trained residuals averaged
only +0.185 (WR) and +0.203 (TE) but inference corrections are 3-4x larger.

The training residuals are small because the heuristic is accurate on average in
training data. But at inference, the model applies feature-based corrections that are
not dampened by the small average residual.

---

## Experiment 1: Wider Alpha Grid

**Hypothesis**: RidgeCV alphas=logspace(-3, 3, 50) misses optimal alpha for WR/TE.

**Change**: Updated `_create_residual_pipeline()` in `src/hybrid_projection.py` to use
`np.logspace(-5, 5, 100)` (wider range, denser grid).

**Result**:
- WR alpha: 3.556 → 4.535 (found slightly higher optimal)
- TE alpha: 0.373 → 0.443
- Production MAE: 5.31 → 5.30 (Δ -0.01) — **NO MEANINGFUL IMPACT**

**Verdict**: SKIP. Alpha was already near-optimal in original range.
Models restored from backup. Alpha grid reverted to logspace(-3, 3, 50) for
production but factory function preserved as `_create_residual_pipeline(alphas=None)`.

---

## Experiment 2: Training Window

**Hypothesis**: 2016-2017 seasons are too old/noisy; tighter window improves generalization.

**Sub-experiment 2a** (2018-2024):
- WR alpha: 3.556 (same), TE alpha: 0.281 (lower — less data)
- WR MAE: 5.36 → 5.34 (Δ -0.01), TE MAE: 4.17 → 4.18 (Δ +0.01)
- Overall: 5.31 → 5.30 — **MARGINAL, NOT MEANINGFUL**

**Sub-experiment 2b** (2020-2024):
- WR MAE: 5.36 → 5.37 (+0.01 WORSE), TE MAE: 4.17 → 4.27 (+0.10 WORSE)
- Overall: 5.31 → 5.33 — **WORSE**

**Verdict**: SKIP. More training data is better for Ridge. Models restored from backup.
`training_seasons` parameter added to `train_and_save_residual_models()` and CLI
for future experimentation.

---

## Experiment 3: RECENCY_WEIGHTS Audit

**Hypothesis**: RECENCY_WEIGHTS changed from v3.2 values, causing heuristic drift.

**Findings**:
- `src/projection_engine.py` RECENCY_WEIGHTS confirmed as roll3=0.30, roll6=0.15, std=0.55
  — exactly matching CLAUDE.md memory (Phase 54 tuned values). No drift.
- Key event: commit df26127 (2026-04-12) consolidated 3 duplicate heuristic
  implementations into single `compute_heuristic_baseline()`. Pre-consolidation,
  residual training used a different heuristic than production.
- Post-consolidation retrain: WR/TE Ridge retrained with unified heuristic.
  Result: 5.31 → 5.31 (no change) — models converge to same alphas and features.
- Training residuals: WR mean=+0.185, TE mean=+0.203 (very small).

**Verdict**: SKIP as MAE lever. RECENCY_WEIGHTS correct. Retrain doesn't help because
the over-correction is a feature-prediction problem, not a mean-offset problem.

---

## Experiment 4: Routing Override Audit (ROOT CAUSE FIX)

**Hypothesis**: HYBRID_POSITIONS override in `ml_projection_router.py` forces WR/TE
into residual correction even when ship gate votes SKIP, and residual models
over-correct since mean inference corrections (+0.80, +0.66) exceed actual heuristic
bias (-0.38, -0.71).

**Root cause**: `_load_ship_gate()` contained two stale overrides:
1. Lines 127-138: WR/TE forced to HYBRID whenever `*_residual.joblib` exists
2. Lines 120-125: RB forced to SHIP whenever XGB models exist on disk
Both overrides pre-date the heuristic consolidation; the ship gate's SKIP verdicts
for WR/TE/RB were correct but being silently ignored.

**Sub-experiment 4 (WR/TE HYBRID disabled)**:
- WR: 5.36 → 4.78 (Δ -0.58, SHIPS gate ≥0.05)
- TE: 4.17 → 3.74 (Δ -0.43)
- Overall: 5.31 → 4.99, Bias: +0.12 → -0.29

**Sub-experiment 4b (WR/TE + RB overrides disabled)**:
- RB: 5.25 → 5.00 (Δ -0.25, SHIPS gate)
- Overall: 5.31 → 4.92, Bias: -0.42 ✓ (within ≤0.5 threshold)

**Sub-experiment 4c (all heuristic including QB)**:
- QB: 7.03 → 6.58 (Δ -0.45) but bias: -0.42 → -0.73 (FAILS bias gate)
- Overall: 4.87 but bias -0.73 exceeds ≤0.5 threshold — REJECTED

**SHIPPED: Exp4b configuration**:
- QB: XGBoost SHIP (bias control — heuristic QB has -2.47 bias)
- RB: Heuristic (SKIP) — MAE 5.00 vs XGB 5.25
- WR: Heuristic (SKIP) — MAE 4.78 vs Ridge 5.36
- TE: Heuristic (SKIP) — MAE 3.74 vs Ridge 4.17

**Final result**:
```
Overall MAE:  4.92  (was 5.31, improvement of -0.39 pts)
Overall Bias: -0.42 (within ≤0.5 threshold ✓)

Per-Position:
  QB: 7.03 (bias +0.05) — XGBoost SHIP (bias control)
  RB: 5.00 (bias -0.50) — Heuristic SKIP ✓
  WR: 4.78 (bias -0.38) — Heuristic SKIP ✓
  TE: 3.74 (bias -0.71) — Heuristic SKIP ✓
```

---

## Files Changed

| File | Change |
|------|--------|
| `src/ml_projection_router.py` | Disabled WR/TE HYBRID override (lines 127-138) and RB SHIP override (lines 120-125) |
| `src/hybrid_projection.py` | Added `training_seasons` param to `train_and_save_residual_models()`; refactored `_create_residual_pipeline()` to accept custom `alphas` |
| `scripts/train_residual_models.py` | Added `--training-seasons` CLI flag |
| `models/player/ship_gate_report.json` | Updated QB entry with current MAE values and bias-control rationale; updated summary |

## Remaining Gap

After Exp4b ships, the gap vs heuristic-only is:
- Exp4b: 4.92 vs Heuristic-only: 4.87 → 0.05 MAE gap
- Entirely from QB XGBoost (+0.45 MAE penalty) needed for bias control
- If QB bias is fixed via a better model, full heuristic (4.87 MAE) becomes viable

## Next Steps

1. Investigate QB XGBoost over-correction: why does the heuristic have -2.47 bias?
   Could be a systematic issue with QB stat prediction in the projection engine.
2. If QB heuristic bias is fixed, removing QB XGBoost would recover the last 0.05 MAE.
3. Long-term: retrain WR/TE residual models with a validation-set calibration step
   to prevent over-correction at inference time.
