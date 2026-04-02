# Session Report: April 1-2, 2026

## Executive Summary

Two intensive sessions spanning v3.1 Graph-Enhanced Fantasy Projections and v4.0 Web Platform MVP. Starting from v3.0 (phases 39-42, 655 tests, MAE 4.91), the project advanced through 11 phases (43-53) and 6 web phases (W1-W6) to reach 900 tests and MAE 4.79 with a complete website prototype.

**Key outcomes:**
- Fantasy MAE improved 4.91 to 4.79 (-2.4%) via hybrid residual approach
- Neo4j graph infrastructure with 22 player features built and evaluated
- Kicker projections added as new position (MAE 4.14)
- Full web platform: FastAPI backend (7 endpoints) + Next.js frontend (3 pages)
- 132 new project files created across 9 commits

---

## v3.1 Graph-Enhanced Fantasy Projections

### Phase 43: Game-Level Constraints
- Team-level projection constraints (total must match implied team total)
- Decision: SKIP for default pipeline, available via `--constrain` opt-in flag
- Files: `src/projection_engine.py` (modified), `tests/test_team_constraints.py` (new)

### Phase 44: Neo4j Phase 1 -- Injury Cascade
- Graph database infrastructure (`src/graph_db.py`)
- Injury cascade features: 4 graph-derived features
- Ingestion pipeline: `scripts/graph_ingestion.py`
- Files: `src/graph_db.py`, `src/graph_injury_cascade.py`, `src/graph_participation.py`

### Phase 45: Neo4j Phase 2 -- WR/TE/OL Matchup Features
- WR-CB matchup graph features (`src/graph_wr_matchup.py`)
- TE coverage features (`src/graph_te_matchup.py`)
- OL lineup stability (`src/graph_ol_lineup.py`)
- Total: 14 additional features (18 cumulative graph features)
- Tests: `tests/test_graph_phase2.py`, `tests/test_graph_te_matchup.py`

### Phase 46: Ship/Skip Gate -- Graph Features
- Evaluated 22 graph features through ship gate
- Finding: 17/22 features show SHAP importance, but none flip RB/WR/TE from SKIP to SHIP
- Graph features add signal but insufficient alone to beat production heuristic

### Phase 47: Scheme Classification + Defensive Front
- 4 RB-specific features: scheme type, defensive front alignment
- File: `src/graph_scheme.py`, `tests/test_graph_scheme.py`

### Phase 48: Kicker Projections
- New position support (K) in projection engine and draft tool
- `src/kicker_analytics.py`: field goal %, distance, game-script modeling
- `src/kicker_projection.py`: projection engine for kickers
- Modified: `src/config.py`, `src/scoring_calculator.py`, `src/draft_optimizer.py`

### Phase 49: PBP Participation Ingestion (no separate phase dir -- folded into commit)
- 295K plays ingested (2020-2025) via expanded `bronze_ingestion_simple.py`
- Training data expanded from 2020-2025 to 2016-2025 (51,758 player-weeks, +66%)

### Phase 50: Populate Graph Features
- Feature extraction pipeline: `scripts/compute_graph_features.py`
- Coverage: 73-95% across feature types
- File: `src/graph_feature_extraction.py`

### Phase 51: Ship/Skip Gate with All Features
- Full evaluation with 22 graph + expanded data
- Result: still SKIP for RB/WR/TE -- OOF overfitting persists across model types

### Phase 52: Kicker Backtesting
- `scripts/backtest_kicker_projections.py`
- MAE 4.14 -- near random for kickers, which is expected (high variance position)

### Phase 53: Model Architecture Improvements (5 sub-phases)

**53-01: Ridge/ElasticNet as primary model**
- Added `create_ridge_pipeline()`, `create_elasticnet_pipeline()` to `src/player_model_training.py`
- Added interaction features (7 stats x 3 context = 21 features) to `src/player_feature_engineering.py`
- CLI: `--model-type {xgb, ridge, elasticnet}` in `scripts/train_player_models.py`
- Finding: Ridge reduces overfitting vs XGB but still trails production heuristic for RB/WR/TE

**53-02: Data expansion retrain**
- Expanded PLAYER_VALIDATION_SEASONS to [2019-2024]
- 51,758 player-weeks (+66% from 31,116)
- QB improved 14%, RB within 1%, WR/TE still SKIP

**53-03: Hybrid residual experiment**
- Blend approach (alpha grid search): ruled out -- heuristic provides no complementary signal
- Residual approach (RidgeCV on actual - heuristic): WR -11%, TE -8% vs standalone ML
- Key insight: heuristic's rolling averages capture "player identity" while ML captures "situation"

**53-04: Production residual experiment**
- Tested residual correction against PRODUCTION heuristic (with ceiling shrinkage + matchup)
- WR: 4.026 -> 3.124 MAE (-22.4%) -- SHIP
- TE: 3.122 -> 2.509 MAE (-19.6%) -- SHIP
- Consistent across all 3 walk-forward folds

**53-05: Wire hybrid into production pipeline**
- New: `scripts/train_residual_models.py`, `src/hybrid_projection.py`
- Saved models: `models/residual/wr_residual.joblib`, `models/residual/te_residual.joblib`
- Router updated: QB -> XGB ML, RB -> XGB ML, WR -> Heuristic + Residual, TE -> Heuristic + Residual
- **Final backtest: MAE 4.91 -> 4.79 (-2.4%)**

Per-position breakdown:
| Position | Old MAE | New MAE | Change |
|----------|---------|---------|--------|
| QB       | 6.58    | 6.58    |  0.0%  |
| RB       | 5.06    | 5.06    |  0.0%  |
| WR       | 4.85    | 4.63    | -4.5%  |
| TE       | 3.77    | 3.58    | -5.0%  |
| Overall  | 4.91    | 4.79    | -2.4%  |

---

## v4.0 Web Platform

Single commit (`669e13d`) containing 60 new files across 6 logical phases:

### W1: FastAPI Backend
- 7 endpoints: projections, predictions, player search, player detail, health, metadata
- Dual data source: Parquet files (default) + PostgreSQL (optional)
- Files: `web/api/main.py`, `web/api/routers/{projections,predictions,players}.py`
- Services: `web/api/services/{projection_service,prediction_service}.py`
- Pydantic schemas: `web/api/models/schemas.py`

### W2: Next.js Projections Table
- Sortable columns, position filter, scoring toggle (PPR/Half-PPR/Standard)
- Components: `ProjectionTable.tsx`, `PositionFilter.tsx`, `ScoringToggle.tsx`

### W3: Game Predictions Page
- Matchup cards with spread/total/confidence
- Confidence tier filter (high/medium/low)
- Components: `PredictionCard.tsx`, `PredictionsView.tsx`, `ConfidenceFilter.tsx`

### W4: Player Detail Page
- Dynamic route: `/players/[id]`
- Projection breakdown, stat grid, matchup context
- Components: `PlayerHeader.tsx`, `ProjectionBreakdown.tsx`, `PlayerDetailView.tsx`, `MatchupContext.tsx`

### W5: Database + Deployment
- PostgreSQL schema and connection: `web/api/db.py`
- Docker: `web/Dockerfile`, `docker-compose.yml` (also serves Neo4j)
- AWS SAM serverless: `web/api/serverless/{handler.py,template.yaml}`
- CI/CD: `.github/workflows/deploy-web.yml`
- Vercel frontend config

### W6: Polish
- Dark mode via `ThemeProvider.tsx`
- SEO metadata in `layout.tsx`
- API key auth middleware
- Loading skeletons, search bar, footer
- Components: `Header.tsx`, `Footer.tsx`, `SearchBar.tsx`, `ThemeProvider.tsx`

### Frontend Stack
- Next.js 14+ with App Router, TypeScript, Tailwind CSS
- 4 pages: home, projections, predictions, player detail
- 15 components in `web/frontend/src/components/`
- API client: `web/frontend/src/lib/api.ts`
- Type definitions: `web/frontend/src/lib/types.ts`
- Team color palette: `web/frontend/src/lib/teamColors.ts`

### Tests
- `tests/test_web_api.py`: API endpoint tests with TestClient

---

## Infrastructure Improvements

### Documentation (commit `9362443`)
- 5 D2 architecture diagrams: `docs/diagrams/{system_architecture,data_flow,fantasy_pipeline,ml_architecture,neo4j_planned}.d2`
- Data dictionary: `docs/data_dictionary.csv` (456 rows)
- `docs/ARCHITECTURE.md` updated to v2.1
- 84 files touched (includes cleanup of old phase directories 28-34)

### Tooling
- GSD updated to v1.31.0 (commit `41a5b27`, 85 new agent/workflow files)

---

## Commit History

```
9420fea feat: wire hybrid residual into projection pipeline (WR/TE SHIP)
ecc4c0e feat: WR and TE SHIP with hybrid residual approach
41a5b27 chore: update GSD to v1.31.0
9362443 docs: update architecture, data dictionary, and planning docs
669e13d feat: add web platform (FastAPI + Next.js + PostgreSQL)
b9b5362 feat: add Ridge/ElasticNet models and hybrid residual approach
66d97b1 feat: ingest PBP participation data and expand training to 2016-2025
cefd44e feat: add game-level constraints and kicker projections
1889616 feat: add Neo4j graph infrastructure with 22 player features
```

All commits dated 2026-04-02 on branch `main`.

---

## Key Decisions

1. **Graph features carry signal but don't flip positions**: 17/22 features show SHAP importance, but OOF overfitting prevents ship for standalone ML on RB/WR/TE
2. **Ridge reduces overfitting vs XGBoost**: Lower capacity helps, but still trails the production heuristic for non-QB positions
3. **Heuristic is effectively an optimally tuned linear model**: Rolling averages + usage/matchup multipliers are hard to beat with ML alone
4. **Hybrid residual is the winning approach**: Correct the heuristic's errors with Ridge, don't try to replace it
5. **Blend approach definitively ruled out**: Grid search always converges to alpha=0.1 (pure ML); heuristic provides no complementary signal for blending
6. **PFF data ($300-500/year) identified as highest-ROI paid upgrade**: Would provide snap-level grades, route data, and blocking metrics unavailable in free sources
7. **Kicker projections are inherently near-random**: MAE 4.14 is acceptable given position variance

---

## Metrics Summary

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Tests | 655 | 900 | +245 |
| Fantasy MAE (Half-PPR) | 4.91 | 4.79 | -2.4% |
| Commits | -- | 9 | -- |
| New project files | -- | 132 | -- |
| Planning phases | 42 | 53 | +11 |
| Web phases | 0 | 6 (W1-W6) | +6 |
| src/ modules | ~20 | ~31 | +11 |
| Graph features | 0 | 22 | +22 |
| Positions supported | 4 (QB/RB/WR/TE) | 5 (+K) | +1 |

### New src/ Modules
- `graph_db.py`, `graph_participation.py`, `graph_wr_matchup.py`, `graph_ol_lineup.py`
- `graph_te_matchup.py`, `graph_scheme.py`, `graph_injury_cascade.py`, `graph_feature_extraction.py`
- `kicker_analytics.py`, `kicker_projection.py`, `hybrid_projection.py`

### New Scripts
- `scripts/graph_ingestion.py`, `scripts/compute_graph_features.py`
- `scripts/backtest_kicker_projections.py`, `scripts/train_residual_models.py`
- `scripts/run_hybrid_experiment.py`, `scripts/run_production_residual_experiment.py`

---

## Next Steps

1. **Wire full features into backtest**: Current production uses ~42 features; residual models trained on 466 columns -- expanding feature availability should further improve WR/TE
2. **Tune heuristic multipliers with expanded data**: The 2016-2025 dataset provides more signal for usage/matchup weight optimization
3. **Deploy website**: Vercel (frontend) + AWS Lambda/SAM (API) -- CI/CD pipeline already configured
4. **Bayesian hierarchical models**: Track 2 approach for position-specific priors
5. **PFF data subscription**: When ready for the $300-500/year investment
6. **Neo4j Aura cloud setup**: Production graph database for live queries
7. **Refresh AWS credentials**: Sync local data back to S3
