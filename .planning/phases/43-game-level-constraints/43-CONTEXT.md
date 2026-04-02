# Phase 43: Game-Level Constraints - Context

**Gathered:** 2026-04-01
**Status:** Complete

<domain>
## Phase Boundary

Closing out v3.0 player predictions by ensuring player-level fantasy projections sum to reasonable implied team totals. The Phase 42 soft constraint (warn-only) revealed systematic over-projection. This phase builds a real normalization function that adjusts player projections post-hoc so per-team fantasy point totals align with Vegas implied team totals, using empirically calibrated NFL-to-fantasy multipliers.

</domain>

<decisions>
## Implementation Decisions

### Calibration
- **D-01:** Empirically calibrate multipliers mapping implied NFL points to fantasy points per scoring format (half_ppr, ppr, standard) using historical data
- **D-02:** Multipliers derived from actual team fantasy point totals vs NFL scoring totals across 2020-2024 seasons

### Normalization Approach
- **D-03:** Post-projection normalization chosen over top-down allocation — preserves individual projection logic, adjusts shares after the fact
- **D-04:** Dampened scaling with a dead zone — small deviations from team total are tolerated, only large over/under projections trigger adjustment
- **D-05:** `apply_team_constraints()` is the core function, applied after all projections (both ML and heuristic) are assembled

### Pipeline Integration
- **D-06:** Opt-in via `--constrain` flag on `generate_projections.py` — not default, based on backtest results
- **D-07:** Wired into both heuristic and ML paths (projection_engine.py and ml_projection_router.py)
- **D-08:** Does not modify floor/ceiling — only adjusts projected_points and proj_{stat} columns

### Claude's Discretion
- Dead zone threshold (how much deviation to tolerate before scaling)
- Dampening curve (linear vs logarithmic scaling for large deviations)
- Which stat columns to scale (all proj_{stat} or just projected_points)

</decisions>

<specifics>
## Specific Ideas

- Calibrated multipliers: half_ppr 3.36, ppr 3.77, standard 2.86 (fantasy points per NFL point)
- Dead zone: teams within +/- 10% of implied fantasy total are not adjusted
- Dampening: scale factor capped to prevent individual player projections from moving more than 20%
- The `--constrain` flag works with both `--week` and `--preseason` modes

</specifics>

<deferred>
## Deferred Ideas

- Per-position constraint weights (e.g., QB absorbs more adjustment than WR)
- Dynamic multipliers that vary by game script (blowout vs close game)
- Integration with game prediction model's win probability for constraint tuning

</deferred>

---

*Phase: 43-game-level-constraints*
*Context gathered: 2026-04-01*
