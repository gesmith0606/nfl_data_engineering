# Production-ML review — 2026-08-15 (full model scan, agent 1 of 4)

Read-only review of both model families. Verdict: **BLOCK** (serve-path integrity
issues confirmed empirically). Companion reports from the same scan:
`BENCHMARK_REFRESH_2026_08_15.md`, `RETRAIN_ON_REPAIRED_FEATURES.md`,
`ENSEMBLE_HEALTH_2026_08_15.md`.

## Ranked findings

1. **[CRITICAL] Quantile floor/ceiling imputer permanently drops 28 now-real
   features at inference** — sklearn `SimpleImputer` (default
   `keep_empty_features=False`) drops any column that was all-NaN at fit time from
   every future `transform()`. Confirmed empirically against
   `models/quantile/imputer.pkl`: the dropped set includes the entire
   `snap_pct*` family (+ its 7 interaction columns) restored by the 83327ecd join
   fix, plus college/scheme features. Served live via `--conformal-bands`
   (`scripts/generate_projections.py:1384`); nothing detects or logs it.
   → Retrain quantile models; assert `imputer.statistics_` has zero NaNs pre-ship.
2. **[HIGH] No data-vintage/provenance pinning on any model artifact** — metas
   record timestamps + season lists, never a data hash/row-counts/code SHA. The
   June artifacts cannot be traced to their training data (which a dev machine
   provably lacked). → Stamp metas with per-source content hash or row counts.
3. **[HIGH] No staleness detection in the ML router** — `_load_ship_gate`
   (`src/ml_projection_router.py:158-188`) only string-matches
   `heuristic_version`; a material Silver schema change (snap_pct 0→96% non-null,
   advanced 0→88-128 cols) triggers nothing. → Add data-vintage gate condition.
4. **[HIGH] Pre-fix models trained on the UNFILTERED population** —
   `_filter_eligible_players` fell back to "position only" when `snap_pct_roll3`
   was all-NaN (always, pre-fix), so every pre-Aug model learned from a different
   population (deep bench included) than inference now serves. Train/serve
   population shift, independent of feature values.
5. **[MED-HIGH] RB role signals still degrade silently on missing snaps/injuries**
   (`src/rb_role_signals.py:755,473,526`) — the original RB_SNAP_COLLAPSE failure
   mode is closed for current data but not structurally. → Coverage assertion.
6. **[MED] Ensemble Ridge meta-learners deserve the same imputer NaN-statistics
   check** (not verified to depth; ensemble otherwise cleared by agent 4).
7. **[MED] Generic mechanism: `imputer.transform()` on frozen artifacts with no
   schema-mismatch check** (`hybrid_projection.py:1472-1487`,
   `quantile_models.py:480-528`). → Startup/CI assertion for every shipped imputer.
8. **[MED] Conformal width factors (~80% coverage claim) calibrated on the pre-fix
   distribution** — do not carry forward after retraining; recompute.
9. **[MED] Join-failure class has one regression test but the name-keyed-join
   pattern elsewhere in Silver is unswept.** → match-rate assertion helper sweep.
10. **[MED] SHAP feature selection (`nan_threshold=0.90`) will silently change the
    selected schema on retrain** — diff pre/post feature lists before shipping.
11. **[MED] No CI gate compares shipped-model imputer/feature profile vs live
    Silver schema** — the systemic gap behind #1/#3/#4/#8. → `check_model_freshness.py`.
12. **[LOW-MED] Preseason consensus-anchor circularity** — document which public
    metrics are pre- vs post-anchor.
13. **[LOW-MED] MAPIE interval path is dead code as wired**
    (`ml_projection_router.py:889-917`) — always heuristic bands; fix or remove
    before re-enabling QB/RB ML (relevant NOW given the flip-to-SHIP verdict).
14. **[LOW] Bayesian artifacts (2026-04-08) stalest in repo, unwired — mark
    research-only or retrain before any reactivation.**
15. **[LOW] Fallback-routing composition changes now the eligibility filter
    actually fires — re-run production backtest before trusting doc'd numbers**
    (done by agent 2 — see BENCHMARK_REFRESH_2026_08_15.md).
