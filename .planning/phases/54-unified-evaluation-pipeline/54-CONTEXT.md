# Phase 54: Unified Evaluation Pipeline — Context

**Gathered:** 2026-04-03
**Status:** Auto-discussed (--auto mode)

<domain>
## Phase Boundary

Align the residual model training and backtest evaluation to use the identical production heuristic and the full 466-feature set. Currently, residual models are trained against a simplified heuristic (weighted_baseline × usage_mult only) but evaluated against the production heuristic (with ceiling shrinkage, matchup multiplier, Vegas multiplier, injury adjustments). This mismatch limits the residual correction's effectiveness in production. Additionally, the backtest only provides 42 Silver features instead of the full 466-feature vector, degrading model performance.

</domain>

<decisions>
## Implementation Decisions

### Heuristic Alignment
- **D-01:** [auto] Residual models must be trained against the PRODUCTION heuristic — same `_weighted_baseline()`, usage_mult [0.80-1.15], matchup_mult [0.85-1.15], Vegas multiplier (implied_total / 23.0), `_apply_ceiling_shrinkage()` at 12/18/23 thresholds
- **D-02:** [auto] Extract the production heuristic computation into a standalone function callable from both projection_engine.py and hybrid_projection.py — avoid code duplication
- **D-03:** [auto] Injury adjustments are NOT part of the heuristic baseline for residual training — injuries are applied post-projection and vary week-to-week

### Feature Pipeline Alignment
- **D-04:** [auto] The backtest must assemble the full player feature vector (466 columns) using `assemble_player_features()` from `player_feature_engineering.py` — not just the 42 Silver columns currently available
- **D-05:** [auto] Feature assembly happens per-week during backtest, respecting temporal lag (only data available at prediction time)
- **D-06:** [auto] Graph features (steps 11-14) are included in the feature vector during backtest — they are already cached in `data/silver/graph_features/`

### Evaluation Framework
- **D-07:** [auto] Walk-forward CV folds: train on 2016-(N-1), validate on N, for N in [2019, 2020, 2021, 2022, 2023, 2024], holdout = 2025
- **D-08:** [auto] Dual agreement gate remains: both OOF and holdout must improve for a position to SHIP
- **D-09:** [auto] The backtest script (`backtest_projections.py`) gets a `--full-features` flag that assembles the complete feature vector

### Architecture
- **D-10:** [auto] Create `src/unified_evaluation.py` — single module that generates production heuristic projections AND assembles full features for any player-week
- **D-11:** [auto] Residual models retrained and saved to `models/residual/` with full-feature pipelines
- **D-12:** [auto] The backtest uses the same code path as production `generate_projections.py --ml` — no separate evaluation logic

</decisions>

<deferred>
## Deferred Ideas
- Bayesian hierarchical models (Phase 56)
- Quantile regression (Phase 57)
- PFF data integration (v3.3)
</deferred>
