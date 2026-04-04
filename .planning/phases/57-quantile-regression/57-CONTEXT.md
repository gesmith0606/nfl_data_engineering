# Phase 57: Quantile Regression — Context

**Gathered:** 2026-04-03
**Status:** Ready

<domain>
## Phase Boundary

Replace hardcoded floor/ceiling (position-specific variance multipliers) with data-driven quantile predictions. LightGBM quantile mode produces 10th/50th/90th percentile estimates per player per week. The 50th percentile (median) may also be a more robust point estimate than the mean. This has high product value — users care about "safe floor play" vs "boom-or-bust" more than point estimate accuracy.

</domain>

<decisions>
## Implementation Decisions

- **D-01:** Use LightGBM quantile mode (`objective='quantile'`, `alpha=0.1/0.5/0.9`)
- **D-02:** Train 3 models per position (10th, 50th, 90th percentile) — NOT per-stat, per-position total fantasy points
- **D-03:** Use the 42-feature Silver set (proven to work, not the full 466 which overfits)
- **D-04:** Walk-forward CV with same folds as existing models (2019-2024 validation, 2025 holdout)
- **D-05:** Calibration target: 80% of actuals fall within 10th-90th range
- **D-06:** Replace `add_floor_ceiling()` in projection_engine.py with quantile-based bounds
- **D-07:** If median (50th percentile) beats heuristic MAE, consider as alternative point estimate
- **D-08:** Integrate with the web API — floor/ceiling in PlayerProjection response
</decisions>
