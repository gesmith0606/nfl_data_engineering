# Phase 46: Backtest Graph Features — Ship/Skip Gate - Context

**Gathered:** 2026-04-02
**Status:** Active

<domain>
## Phase Boundary

Retrain per-position player models with the 18 new graph-derived features (injury cascade, WR matchup, OL/RB, TE coverage) and evaluate against the current heuristic baseline. This is the ship/skip gate for the Neo4j graph approach — each position's graph features must independently improve holdout MAE to ship.

Current baselines to beat:
- Overall MAE: 4.91 (half-PPR)
- QB: 6.58, RB: 5.06, WR: 4.85, TE: 3.77

</domain>

<requirements>
## Requirements

- R-01: Retrain per-position XGBoost models with graph features added to feature vector
- R-02: Walk-forward CV (same folds as Phase 40-41) for fair comparison
- R-03: SHAP feature selection including graph features
- R-04: Per-position ship/skip gate: strict improvement on holdout MAE
- R-05: Graph features that don't improve a position get excluded for that position
- R-06: If any position improves, retrain the ML projection router with updated models
- R-07: Full backtest comparison (MAE/RMSE/bias/correlation) with and without graph features
</requirements>
