---
gsd_state_version: 1.0
milestone: v3.2
milestone_name: Model Perfection
status: complete
last_updated: "2026-04-09T02:30:00.000Z"
last_activity: 2026-04-09
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 4
  completed_plans: 4
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** 4 parallel workstreams — Models, Website, Graph Features, Sentiment Pipeline

## Active Workstreams

### 1. Models — v3.2 Model Perfection

Phases 54-57 | 19 requirements | Target: MAE < 4.5

- Phase 54: COMPLETE — unified evaluation pipeline
- Phase 55: COMPLETE — LightGBM + SHAP-60 residuals (massive improvement)
- Phase 56: COMPLETE — Bayesian posterior intervals (78-87% calibration), LGB keeps point estimates
- Phase 57: COMPLETE — Quantile regression (74.8-81.8% calibration), final validation (MAE 4.80, target 4.5 not met)

### 2. Website — v4.0 Production Launch

- Phase W1-W2: COMPLETE — FastAPI + Next.js frontend
- Phase W3: COMPLETE — Game predictions page (was already built)
- Frontend deployed: https://frontend-jet-seven-33.vercel.app
- Phase W4: COMPLETE — Player detail page, accuracy dashboard, backend fix (Pydantic v2)
- Phase W5: COMPLETE — sync_gold_to_db.py, PostgreSQL fallback, Docker/Railway ready

### 3. Graph Features — Enhancement Track

- RB matchup module: COMPLETE — new graph_rb_matchup.py (8 features, 43 tests)
- WR matchup enhanced: COMPLETE — 9 new advanced features (air yards, YAC, coverage shell)
- TE matchup enhanced: COMPLETE — 5 new advanced features (seam routes, CB coverage rate)
- Graph→Residual wiring: COMPLETE — --use-graph-features flag, 39 features available
- Recompute: COMPLETE — 66 features (was 49), 6 seasons, new features in SHAP top-60
- LGB retrained: COMPLETE — WR/TE/RB with 23 new graph features each
- Backtest validation: COMPLETE — hybrid path 4.72 MAE vs heuristic 5.66 (17% gap); 40% of players fall through to heuristic
- v4.1 Phase 1: COMPLETE — RB/QB routing attempted and reverted (both degrade on 2025 holdout)
  - RB hybrid: +0.59 MAE worse (5.39 -> 5.98) — LGB residual overfits
  - QB hybrid: +7.51 MAE catastrophic failure (8.64 -> 16.15) — residual model extrapolates wildly
  - Fixed 2 bugs: feature file format + duplicate column names in XGB SHIP path
  - 2025 sealed holdout baseline: 5.26 overall, 4.56 hybrid (WR/TE)
  - NEXT: Feature pruning + regularization tuning to retrain models that generalize to holdout

### 4. Sentiment Pipeline — v5.0 (Planning)

- Architecture: COMPLETE — .planning/unstructured-data/ARCHITECTURE.md
- Phase S1: COMPLETE — pgvector schema, RSS ingestion (5 feeds), Sleeper ingestion, player name resolver
- Phase S2: COMPLETE — Claude extraction, processing pipeline, weekly aggregation, 44 tests
- Phase S3: NEXT — Projection engine integration (apply sentiment_multiplier)

## Current Position

Phase: v4.1-p1 (Expand Hybrid Coverage) — COMPLETE
Status: v3.2 shipped; v4.1-p1 investigated routing RB/QB through hybrid; both degraded on 2025 holdout; fixed 2 SHIP path bugs; HYBRID_POSITIONS unchanged {WR, TE}
Last activity: 2026-04-10

## Key Artifacts

| Artifact | Location |
|----------|----------|
| Project | .planning/PROJECT.md |
| Milestones | .planning/MILESTONES.md |
| Roadmap | .planning/ROADMAP.md |
| Requirements | .planning/REQUIREMENTS.md |
| v4.0 Web Planning | .planning/v4.0-web/ |
| Unstructured Data | .planning/unstructured-data/ARCHITECTURE.md |
| Phase 55 Research | .planning/phases/phase-55/55-RESEARCH.md |
| Phase 55 Experiments | .planning/phases/phase-55/EXPERIMENTS.md |

## Accumulated Context

### Decisions

- [v3.1]: Hybrid residual SHIPS for WR/TE — heuristic + Ridge correction beats standalone ML
- [v3.1]: Heuristic is an optimally tuned linear model — don't replace, correct
- [v3.2/P54]: 466 features degrade all positions with Ridge — Ridge cannot regularize noise
- [v3.2/P55]: LightGBM + SHAP-60 SHIPS — massively outperforms Ridge across all positions
- [v3.2/P55]: Walk-forward CV: WR -31.4%, TE -27.2%, RB -25.1%, QB -72.2% MAE improvement
- [v3.2/P55]: LGB beats Ridge by 7-17% per position — tree-based handles high-dim features
- [v3.2/P55]: New graph features built: RB matchup (8), WR advanced (9), TE advanced (5)
- [v4.0]: Website deployed to Vercel (frontend-jet-seven-33.vercel.app), backend not yet live
- [v5.0]: Sentiment pipeline designed — pgvector in Supabase, sentiment_multiplier pattern
- [Phase 56]: BayesianRidge ships for calibrated 80% CI floor/ceiling (78-87% coverage); LGB keeps point estimates
- [WS3]: Graph features expanded 49→66; new WR/TE/RB features in SHAP top-60 (target_concentration, air_yards strongest)
- [WS4/S1]: Sentiment foundation built — pgvector schema, RSS+Sleeper ingestion, player name resolver
- [v3.2/P57]: Quantile regression SHIPS for calibrated floor/ceiling (74.8-81.8% coverage); MAE 4.80 (target 4.5 not met)
- [v3.2/P57]: Graph features do NOT improve point-estimate MAE — train/inference feature mismatch; SKIP retrained models
- [v4.1/P1]: RB hybrid routing SKIP — degrades 2025 holdout MAE +0.59 (5.39 -> 5.98); LGB residual has +0.77 upward bias
- [v4.1/P1]: QB hybrid routing SKIP — catastrophic +7.51 MAE on 2025 holdout (8.64 -> 16.15); residual adds ~15 pts per QB
- [v4.1/P1]: XGB SHIP path architecturally broken — feature_names mismatch (qbr_* cols missing); QB/RB on heuristic since deployment
- [v4.1/P1]: Walk-forward CV does NOT predict production for residual models — WFCV and production diverge on unseen years

### Research Flags

- Bayesian models may provide better uncertainty than XGBoost (Phase 56)
- PFF data ($300-500) would upgrade proxy matchup features to real coverage data
- Enhanced graph features (22 new) need recomputation + integration into LGB residuals
- Walk-forward CV is trustworthy for *relative* model comparison but NOT for absolute production MAE prediction
- RB/QB residual models need stricter regularization + feature pruning before re-attempting hybrid routing
- XGB SHIP path needs QBR feature integration into player_feature_engineering.py

### Blockers/Concerns

- Backend not deployed — frontend shows empty states
- Graph features need recomputation with new RB/WR/TE modules before integration testing

---
*Last updated: 2026-04-09 — v3.2 Model Perfection complete: P57 quantile regression done, MAE 4.80, 18/19 requirements met*
