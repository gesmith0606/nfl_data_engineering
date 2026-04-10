# v4.1 Phase 2: v2 Pruned Residual Models — Production Wire

Date: 2026-04-10

## Background

Phase 2 trained new pruned (top-20 SHAP feature) LightGBM residual models after
Phase 1 found that the full-feature v1 models degraded both RB and QB on the 2025
sealed holdout. The v2 models used bias correction and feature pruning to address
the instability.

Training holdout results (2025 sealed, narrow eval slice):
- RB v2: 5.39 → 2.44 MAE (-2.95 vs heuristic) — training declared SHIP
- QB v2: 8.64 → 4.07 MAE (-4.57 vs heuristic) — training declared SHIP

## Implementation

### Files Promoted (Approach A: copy to standard paths)

| Source | Destination |
|--------|-------------|
| `models/residual/rb_residual_lgb_v2.pkl` | `models/residual/rb_residual.joblib` |
| `models/residual/rb_residual_imputer_v2.pkl` | `models/residual/rb_residual_imputer.joblib` |
| `models/residual/rb_residual_meta_v2.json` | `models/residual/rb_residual_meta.json` |
| `models/residual/qb_residual_lgb_v2.pkl` | `models/residual/qb_residual.joblib` |
| `models/residual/qb_residual_imputer_v2.pkl` | `models/residual/qb_residual_imputer.joblib` |
| `models/residual/qb_residual_meta_v2.json` | `models/residual/qb_residual_meta.json` |

V1 files backed up as `*.bak_v1`. V2 source files retained as source of truth.

### Code Changes

**`src/hybrid_projection.py`**:
- `load_residual_model()`: Changed imputer-loading guard from `== "lgb"` to
  `str(...).startswith("lgb")` to support `model_type="lgb_v2"` in v2 metadata.
- `apply_residual_correction()`: Same startswith fix for the prediction dispatch branch.

**`src/ml_projection_router.py`**:
- Module docstring routing table updated to reflect v3 routing.
- `HYBRID_POSITIONS` comment block updated with v4.1 Phase 1 reversal history and
  Phase 2 partial-ship decision.
- `HYBRID_POSITIONS` set: `{"WR", "TE"}` → `{"WR", "TE", "RB"}` (QB excluded, see below).

## Full-Season Backtest Results

### 2025 Sealed Holdout (16 weeks, W3-W18)

| Position | Source | MAE | Bias | Count |
|----------|--------|-----|------|-------|
| QB | heuristic | 8.64 | +1.52 | 560 |
| RB | hybrid (v2) | 6.03 | +1.32 | 1,348 |
| WR | hybrid | 4.73 | +0.66 | 2,008 |
| TE | hybrid | 4.18 | +0.32 | 920 |
| **Overall** | mixed | **5.44** | **+0.88** | **4,836** |

Note: raw counts include backtest join duplicates from player_name matching on
multi-team players (pre-existing bug, not from residual correction). Deduplicated
results: RB 5.42 MAE Bias=+0.06, QB 8.64 MAE.

### 2022-2024 Historical (48 weeks, W1-W18)

| Position | Source | MAE | Bias | Count |
|----------|--------|-----|------|-------|
| QB | heuristic | 6.97 | -0.86 | 1,367 |
| RB | hybrid (v2) | 5.47 | +0.25 | 3,094 |
| WR | hybrid | 5.48 | +0.04 | 4,616 |
| TE | hybrid | 4.40 | -0.13 | 2,106 |
| **Overall** | mixed | **5.46** | **-0.04** | **11,183** |

## Ship Decision

### RB v2 — SHIP

Production RB path: heuristic + LightGBM v2 residual correction (20 features).
- 2025 holdout: 5.42 MAE, Bias=+0.06 (deduplicated) — essentially unbiased
- 2022-2024: 5.47 MAE, Bias=+0.25 — no regression vs previous baseline
- Training holdout 2.44 MAE was on a narrower eval slice; production result is
  approximately parity with heuristic with near-zero bias. Acceptable to ship.

### QB v2 — SKIP

QB v2 was NOT activated in `HYBRID_POSITIONS` despite training declaring SHIP.

Full-season 2025 backtest with QB v2 hybrid showed:
- Mean correction: +11.82 pts per QB (massive upward bias)
- Deduplicated MAE: 12.87 (vs 8.64 heuristic baseline) — catastrophic degradation

Root cause: QB residuals remain non-stationary across seasons. The 20 pruned
features (qb_passing_epa, qbr_epa_total, travel_miles, etc.) still drive unstable
extrapolation when applied out-of-sample. The training holdout (2.44 MAE) evaluated
on a slice where heuristics and QB performance were stable; the full-season
production path sees more diverse conditions.

QB v2 model files are retained at production paths for diagnostic use but QB
stays on heuristic until bias-corrected residuals are developed.

## Final Production Routing

```
QB → heuristic (verdict=SHIP from gate, but HYBRID excluded due to bias)
RB → heuristic + LightGBM v2 residual (HYBRID)
WR → heuristic + LightGBM residual (HYBRID)
TE → heuristic + LightGBM residual (HYBRID)
```

HYBRID_POSITIONS = {"WR", "TE", "RB"}
