# Phase 38: Market Feature Ablation - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning

<domain>
## Phase Boundary

A definitive, structurally valid answer on whether market features improve game prediction accuracy, based on 6 seasons of market training data and a fresh 2025 holdout. This is the milestone's real deliverable.

</domain>

<decisions>
## Implementation Decisions

### Ablation execution
- **D-01:** Run `scripts/ablation_market_features.py` which trains P30 baseline (no market features) vs market-augmented ensemble, both on 2016-2024, both evaluated on sealed 2025 holdout
- **D-02:** Use existing ship-or-skip gate: strict `>` on holdout ATS accuracy. Market-augmented model must beat 51.7% ATS (the Phase 37 baseline) to ship
- **D-03:** Both models save to `models/ensemble_ablation/` — this protects the production model in `models/ensemble/`
- **D-04:** No hyperparameter re-tuning for either model — both use P30 ensemble hyperparameters for fair comparison

### SHAP analysis
- **D-05:** Generate SHAP importance report showing relative contribution of `opening_spread` and `opening_total` in the market-augmented model
- **D-06:** SHAP report should distinguish between market features and non-market features to quantify the marginal lift (or lack thereof)

### Verdict and documentation
- **D-07:** Document the verdict in `.planning/phases/38-market-feature-ablation/VERDICT.md` with exact metrics for both models: ATS accuracy, profit, ROI, CLV
- **D-08:** If market features SHIP: update CLAUDE.md and PROJECT.md to reflect that market features are part of the production model
- **D-09:** If market features SKIP: document why (likely: closing-as-opening proxy doesn't carry enough signal), note that pursuing paid opening-line data (The Odds API) would be the next step to revisit
- **D-10:** Regardless of verdict, this ablation is structurally valid (6 seasons of market training data vs v2.1's 1 season) — the conclusion is definitive for available free data

### Claude's Discretion
- Exact VERDICT.md format beyond required metrics
- Whether to include per-season breakdown in the verdict
- Logging verbosity during ablation run
- Whether to run additional diagnostic analysis beyond SHAP

</decisions>

<specifics>
## Specific Ideas

- This is the first structurally valid test: v2.1's ablation had only 1 of 8 training seasons with market data and zero market data in the holdout. Now we have 6/9 training seasons with FinnedAI market data, all 9 with opening lines (via nflverse bridge), and the 2025 holdout has full market coverage
- The baseline to beat is 51.7% ATS (Phase 37) — if market features don't improve on this, the conclusion is clear: free closing-line proxies don't help, and only real opening-line data would be worth pursuing

</specifics>

<canonical_refs>
## Canonical References

### Ablation framework
- `scripts/ablation_market_features.py` — Existing ablation CLI; trains baseline vs market-augmented, SHAP report, ship-or-skip gate
- `src/ensemble_training.py` — Ensemble training with holdout guard
- `src/prediction_backtester.py` — ATS/O-U/CLV evaluation, `LEAKAGE_THRESHOLD=0.58`

### Baseline reference
- `.planning/phases/37-holdout-reset-and-baseline/BASELINE.md` — 2025 holdout baseline: 51.7% ATS, -$3.73 profit

### Prior ablation context
- PROJECT.md Key Decisions: "Ship market features only if holdout ATS improves (strict >)"
- PROJECT.md Key Decisions: "Ablation saves to models/ensemble_ablation/"

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ablation_market_features.py`: Complete CLI — trains both models, evaluates, generates SHAP, renders verdict. Proven in v2.1
- Ship-or-skip gate already implemented in the script
- SHAP importance reporting already built in

### Established Patterns
- Ablation models save to `models/ensemble_ablation/` (not production)
- Same walk-forward CV and holdout guard as production training
- Feature exclusion via column filtering (drops market columns for baseline)

### Integration Points
- Reads feature vectors assembled in Phase 36
- Uses config from Phase 37 (HOLDOUT_SEASON=2025, TRAINING_SEASONS=2016-2024)
- Verdict informs future milestone planning (v3.0+ decision on paid odds API)

</code_context>

<deferred>
## Deferred Ideas

- Paid odds API for real opening lines — only warranted if ablation proves opening-line movement materially improves accuracy
- Per-book line comparison ablation — v4.0+ concern
- Ablation of individual market features (opening_spread alone vs opening_total alone) — interesting but out of scope for v2.2

</deferred>

---

*Phase: 38-market-feature-ablation*
*Context gathered: 2026-03-29*
