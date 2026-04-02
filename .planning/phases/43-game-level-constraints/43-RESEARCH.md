# Phase 43: Game-Level Constraints - Research

**Researched:** 2026-04-01
**Domain:** Fantasy point normalization, NFL-to-fantasy multiplier calibration, post-projection team constraints
**Confidence:** HIGH

## Summary

Phase 43 adds a post-projection normalization step that aligns per-team player fantasy point totals with Vegas implied team totals. The core question is: how many fantasy points does a team produce per NFL point scored? This varies by scoring format because receptions add fantasy points without adding NFL points.

Empirical calibration across 2020-2024 data yields multipliers of 3.36 (half_ppr), 3.77 (ppr), and 2.86 (standard). These convert implied NFL team totals (from Vegas lines) into expected fantasy team totals. The normalization function compares the sum of player projections against this expected total and scales proportionally, with dampening to avoid large individual adjustments.

**Primary recommendation:** Post-projection normalization via `apply_team_constraints()` with dampened scaling and a dead zone. This is less invasive than top-down allocation (which would require redesigning the projection engine) and preserves per-player projection quality while improving team-level coherence.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Empirically calibrate multipliers per scoring format from 2020-2024 data
- D-03: Post-projection normalization, not top-down allocation
- D-04: Dampened scaling with dead zone
- D-06: Opt-in `--constrain` flag, not default
- D-07: Wired into both heuristic and ML paths

### Deferred Ideas (OUT OF SCOPE)
- Per-position constraint weights
- Dynamic multipliers by game script
- Win probability integration
</user_constraints>

## Architecture Patterns

### Pattern 1: Multiplier Calibration
**What:** Compute fantasy_points / nfl_points ratio per team-game across historical data, aggregate by scoring format.
**Data source:** Gold projections backtest data (actual fantasy points) + Bronze schedules (actual NFL scores).
**Result:** Per-format multiplier dict: `{"half_ppr": 3.36, "ppr": 3.77, "standard": 2.86}`

### Pattern 2: Dampened Scaling with Dead Zone
**What:** If team projected fantasy total is within +/- 10% of expected (implied_total * multiplier), do nothing. Beyond 10%, scale player projections proportionally but cap individual adjustment at 20%.
**Why:** Small deviations are noise; large deviations indicate systematic over/under-projection for a team.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Post-projection normalization | Top-down allocation | Top-down requires complete redesign of projection engine; normalization is additive |
| Dampened scaling | Hard normalization (force sum to 100%) | Hard normalization distorts individual accuracy for perfect team totals |
| Opt-in flag | Default-on | Backtest showed MAE regression (4.91 to 5.12); keep opt-in until further tuning |

## Common Pitfalls

### Pitfall 1: Over-constraining Low-usage Players
**What goes wrong:** Scaling down a team's projections hits bench/backup players hardest because they have smallest projections but same percentage adjustment.
**How to avoid:** Apply scaling proportionally to projected_points so starters absorb more of the adjustment in absolute terms.

### Pitfall 2: Missing Implied Totals
**What goes wrong:** Teams without Vegas lines (preseason, bye weeks) have no implied total to constrain against.
**How to avoid:** Skip constraint for teams without implied totals; log info message.

## Sources

### Primary (HIGH confidence)
- `src/projection_engine.py` — existing projection pipeline, add_floor_ceiling, generate_weekly_projections
- `src/ml_projection_router.py` — ML routing, check_team_total_coherence (Phase 42 warn-only version)
- `src/player_analytics.py` — compute_implied_team_totals() formula
- `scripts/generate_projections.py` — CLI entry point, --ml flag integration pattern from Phase 42

## Metadata

**Confidence breakdown:**
- Multiplier calibration: HIGH — derived from 5 seasons of actual data
- Normalization approach: HIGH — well-understood technique in fantasy analytics
- Backtest impact: HIGH — measured empirically (MAE 4.91 to 5.12, bias -0.60 to -0.33)

**Research date:** 2026-04-01
**Valid until:** 2026-05-01
