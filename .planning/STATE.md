---
gsd_state_version: 1.0
milestone: v3.2
milestone_name: Model Perfection
status: Ready for Phase 56 (Bayesian) + parallel workstreams
last_updated: "2026-04-09T01:46:49.856Z"
last_activity: 2026-04-07
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 2
  completed_plans: 3
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
- Phase 56: NEXT — Bayesian hierarchical models
- Phase 57: PENDING — Quantile regression + final validation

### 2. Website — v4.0 Production Launch

- Phase W1-W2: COMPLETE — FastAPI + Next.js frontend
- Phase W3: COMPLETE — Game predictions page (was already built)
- Frontend deployed: https://frontend-jet-seven-33.vercel.app
- Phase W4: NEXT — Player detail + accuracy page
- Phase W5: PENDING — Database (Supabase) + backend deployment

### 3. Graph Features — Enhancement Track

- RB matchup module: COMPLETE — new graph_rb_matchup.py (8 features, 43 tests)
- WR matchup enhanced: COMPLETE — 9 new advanced features (air yards, YAC, coverage shell)
- TE matchup enhanced: COMPLETE — 5 new advanced features (seam routes, CB coverage rate)
- Graph→Residual wiring: COMPLETE — --use-graph-features flag, 39 features available
- NEXT: Recompute graph features with new modules, retrain LGB residuals with enhanced features

### 4. Sentiment Pipeline — v5.0 (Planning)

- Architecture: COMPLETE — .planning/unstructured-data/ARCHITECTURE.md
- Phase S1: NEXT — Supabase pgvector schema + RSS/Sleeper ingestion
- Phase S2: PENDING — Claude extraction pipeline
- Phase S3: PENDING — Projection engine integration

## Current Position

Phase: 55 (LGB+SHAP Residuals) — COMPLETE
Status: Ready for Phase 56 (Bayesian) + parallel workstreams
Last activity: 2026-04-07

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
- [Phase 56]: Use sklearn BayesianRidge for posterior intervals (JAX/NumPyro incompatible with Rosetta)
- [Phase 56]: Ship Bayesian for calibrated floor/ceiling intervals; keep LGB for point estimates

### Research Flags

- Bayesian models may provide better uncertainty than XGBoost (Phase 56)
- PFF data ($300-500) would upgrade proxy matchup features to real coverage data
- Enhanced graph features (22 new) need recomputation + integration into LGB residuals
- Production backtest shows degradation with residuals (train-on-all limitation) — walk-forward is trustworthy

### Blockers/Concerns

- Backend not deployed — frontend shows empty states
- Graph features need recomputation with new RB/WR/TE modules before integration testing

---
*Last updated: 2026-04-07 — Phase 55 complete, 4 workstreams active*
