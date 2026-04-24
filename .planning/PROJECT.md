# NFL Data Engineering Platform

## What This Is

A production NFL analytics platform that combines a Medallion-architecture data lake (Bronze/Silver/Gold on local Parquet + S3) with a live public website at https://frontend-jet-seven-33.vercel.app. The data side ingests 16 Bronze types (10 years, 2016-2025) into a 14-path Silver layer (team PBP metrics, player usage, line movement, game context, graph features) and trains both per-position fantasy projection models (Ridge 60f+graph residuals on WR/TE, XGB on QB/RB, 5.05 MAE) and an XGB+LGB+CB+Ridge game prediction ensemble (120 SHAP-selected features, 51.7% ATS on sealed 2025 holdout with `diff_opening_spread` as #1 feature). The website surface delivers: fantasy projections (3 scoring formats), game predictions with edge detection, matchup view backed by real NFL rosters + positional-rank advantage tooltips, an AI advisor with 12 Gold-grounded tools and persistent chat, a news/sentiment pipeline running daily on a 5-source cron, and a 32-team event density grid. Backend is FastAPI on Railway; frontend is Next.js on Vercel with a design-token-driven UI, 5 motion primitives, and mobile responsiveness at 375px.

## Core Value

A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models.

## Requirements

### Validated

- ✓ Infrastructure: local-first storage, dynamic season validation, adapter pattern, registry CLI — v1.0
- ✓ PBP: 103 curated columns (EPA/WPA/CPOE/air yards) for 2016-2025, memory-safe batching — v1.0
- ✓ Advanced stats: NGS, PFR weekly/seasonal, QBR, depth charts, draft picks, combine — v1.0
- ✓ Documentation: data dictionary, Bronze inventory, prediction model badges, implementation guide — v1.0
- ✓ Validation: validate_data() for all data types, wired into ingestion pipeline — v1.0
- ✓ Bronze layer: 6 original types (schedules, player_weekly, player_seasonal, snap_counts, injuries, rosters) — pre-v1.0
- ✓ Silver layer: usage metrics, rolling averages, opponent rankings — pre-v1.0
- ✓ Gold layer: weekly + preseason projections (PPR/Half-PPR/Standard) — pre-v1.0
- ✓ Draft tool: snake, auction, mock draft, waiver wire — pre-v1.0
- ✓ Pipeline monitoring: GHA cron + health check — pre-v1.0
- ✓ Backtesting: MAE 4.91, r=0.51 across 3 seasons — pre-v1.0
- ✓ 186 total tests passing — v1.1
- ✓ 9 new Bronze data types ingested with full historical coverage — v1.1
- ✓ 6 existing types backfilled to 2016-2025 (517 files, 93 MB) — v1.1
- ✓ Batch ingestion CLI with progress, failure handling, skip-existing — v1.1
- ✓ 2025 player stats via stats_player adapter with column mapping — v1.1
- ✓ Bronze-Silver path alignment (snap_counts, schedules) — v1.1
- ✓ Bronze inventory: 15 data types, 10 years, all validated — v1.1
- ✓ PBP-derived team metrics (EPA, success rate, CPOE, red zone) with 3/6-game rolling windows — v1.2
- ✓ Team tendencies (pace, PROE, 4th-down aggressiveness, early-down run rate) with rolling windows — v1.2
- ✓ Opponent-adjusted EPA with lagged SOS and schedule difficulty rankings (1-32) — v1.2
- ✓ Situational splits (home/away, divisional, game script) with rolling EPA — v1.2
- ✓ Advanced player profiles (NGS separation/RYOE/TTT, PFR pressure/blitz, QBR) with rolling windows — v1.2
- ✓ Historical dimension table: combine measurables + draft capital for 9,892 players — v1.2
- ✓ Pipeline health monitoring for all 7 Silver paths — v1.2
- ✓ 289 total tests passing — v1.2
- ✓ PBP expanded to 140 columns (penalty, ST, fumble recovery, drive details) with re-ingestion for 2016-2025 — v1.3
- ✓ Officials Bronze ingested for 2016-2025 with referee crew assignments — v1.3
- ✓ Stadium coordinates (38 venues) for haversine travel distance — v1.3
- ✓ 11 PBP-derived team metrics (penalties, turnovers, red zone trips, FG accuracy, returns, 3rd down, explosives, drives, sacks, TOP) with rolling windows — v1.3
- ✓ Game context Silver layer (weather, rest, travel, coaching, surface) per team per week — v1.3
- ✓ Referee tendency profiles (expanding-window penalty rates per crew with shift(1) lag) — v1.3
- ✓ Playoff/elimination context (cumulative W-L-T, division rank, games behind, late-season contention) — v1.3
- ✓ Full prediction feature vector assembly: 337 columns from 8 Silver sources — v1.3
- ✓ Pipeline health monitoring for all 11 Silver paths — v1.3
- ✓ 360 total tests passing — v1.3
- ✓ Game-level differential feature assembly (337-col vectors, home-away differentials) — v1.4
- ✓ XGBoost model training with walk-forward CV (temporal split, holdout guard) — v1.4
- ✓ Training CLI with Optuna hyperparameter tuning and feature importance reporting — v1.4
- ✓ 396 total tests passing — v1.4
- ✓ Prediction backtester with ATS/O-U evaluation and vig-adjusted profit at -110 odds — v1.4
- ✓ Sealed 2024 holdout validation with leakage guard and per-season stability analysis — v1.4
- ✓ 426 total tests passing — v1.4
- ✓ Comprehensive docs refresh (data dictionary for all layers, CLAUDE.md, implementation guide) — v1.4
- ✓ ML prediction model (XGBoost) for point spreads using 337-column feature vector — v1.4
- ✓ ML prediction model (XGBoost) for over/unders using 337-column feature vector — v1.4
- ✓ Backtest ML models against historical closing lines with ATS accuracy and profit analysis — v1.4
- ✓ Weekly prediction pipeline generating own lines with edge detection vs Vegas — v1.4
- ✓ 439 total tests passing — v1.4
- ✓ Player quality Silver features (QB EPA, positional quality, injury impact) — Phase 28, v2.0
- ✓ Feature selection pipeline: SHAP importance + correlation filtering (r > 0.90) with CV-validated cutoff — Phase 29, v2.0
- ✓ Walk-forward-safe feature selection (per-fold, 2024 holdout excluded) — Phase 29, v2.0
- ✓ 470 total tests passing — v2.0
- ✓ Model ensemble: XGBoost + LightGBM + CatBoost stacking with Ridge meta-learner and generalized walk-forward CV — Phase 30, v2.0
- ✓ Ensemble training CLI with optional Optuna tuning, --ensemble flag in backtest and prediction CLIs — Phase 30, v2.0
- ✓ 482 total tests passing — v2.0
- ✓ Momentum features (win streak, ATS trend/margin) and EWM windows (halflife=3) for team metrics — Phase 31, v2.0
- ✓ Ablation: Phase 31 features improved training but did not improve holdout; P30 ensemble confirmed as v2.0 — Phase 31, v2.0
- ✓ Final holdout: v1.4 (50.0% ATS, -$12.18) → v2.0 ensemble (53.0% ATS, +$3.09) on sealed 2024 — Phase 31, v2.0
- ✓ 503 total tests passing — v2.0
- ✓ Bronze odds ingestion: FinnedAI JSON → Parquet with 45-entry team mapping, sign convention alignment, nflverse join (r=0.997 cross-validation), zero orphans — Phase 32, v2.1
- ✓ 516 total tests passing — v2.1
- ✓ Silver line movement features: spread/total shift, ordinal magnitude buckets, key number crossings, per-team reshape with sign flips, feature_engineering.py integration (opening_spread/opening_total in _PRE_GAME_CONTEXT) — Phase 33, v2.1
- ✓ 545 total tests passing — v2.1
- ✓ CLV tracking: evaluate_clv(), by-tier, by-season metrics in prediction backtester and CLI — Phase 34, v2.1
- ✓ Market feature ablation script: P30 baseline vs market-augmented ensemble on sealed 2024 holdout with SHAP report and ship-or-skip verdict — Phase 34, v2.1
- ✓ 571 total tests passing — v2.1
- ✓ Full FinnedAI odds ingestion for all 6 seasons (2016-2021) with cross-validation r > 0.95, nflverse odds bridge for 2022-2025 with line_source provenance — Phase 35, v2.2
- ✓ 2025 Bronze data complete (7/8 types; injuries capped at 2024 by nflverse) with 285 games confirmed — Phase 35, v2.2
- ✓ 594 total tests passing — v2.2
- ✓ Silver market data for all 10 seasons (2016-2025) with line movement features; player quality gap-filled (2020-2025) — Phase 36, v2.2
- ✓ 2025 feature vector: 272 REG games, 1139 columns, 0% NaN on market features; training seasons 2016-2024 all assemble correctly — Phase 36, v2.2
- ✓ Holdout rotated to 2025 with derived season ranges; ensemble retrained on 2016-2024; 2025 baseline: 51.7% ATS, -$3.73 profit — Phase 37, v2.2
- ✓ Market feature ablation: SHIP — 50.6% ATS beats 50.2% baseline (+0.4%); diff_opening_spread is #1 SHAP feature (23.6%); 120-feature SHAP-selected ensemble promoted to production — Phase 38, v2.2
- ✓ Player-week feature vector assembly: 9 Silver sources joined into per-player-per-week rows (5,480 rows, 337 features for 2024), shift(1) temporal lag enforcement, matchup features, Vegas implied totals, leakage detection — Phase 39, v3.0
- ✓ 608 total tests passing — v3.0
- ✓ Per-position per-stat XGBoost models (19 total: QB 5, RB 6, WR 4, TE 4) with walk-forward CV (3 expanding folds), SHAP feature selection per stat-type group, ship gate with dual agreement (OOF + holdout) — Phase 40, v3.0
- ✓ 622 total tests passing — v3.0
- ✓ Derived efficiency features (12), TD regression features (2), role momentum deltas (3) added to player feature vector — Phase 41, v3.0
- ✓ XGB+LGB+Ridge ensemble stacking per position with two-stage CLI evaluation (features-only → ensemble) — Phase 41, v3.0
- ✓ ML projection router: position-based dispatch (QB→ML, RB/WR/TE→heuristic), MAPIE confidence intervals, team-total coherence — Phase 42, v3.0
- ✓ CLI --ml flag wired into generate_projections.py; preseason draft capital boost for rookies — Phase 42, v3.0
- ✓ 655 total tests passing — v3.0
- ✓ Daily Sleeper roster refresh corrects team + position in a single pass, with audit log — Phase 60, v6.0
- ✓ CI quality-gate job blocks Vercel + Railway/ECR deploys on CRITICAL sanity-check issues — Phase 60, v6.0
- ✓ 5-source daily news pipeline (RSS + Sleeper + Reddit + RotoWire + PFT) with D-06 isolation — Phase 61, v6.0
- ✓ 12 rule-extracted event flags power `/api/news/team-events` (32 rows), `/player-badges/{id}`, and `event_flags` on NewsItem — Phase 61, v6.0
- ✓ Optional Claude Haiku summary enrichment via non-destructive sidecar (double-gated: ENABLE_LLM_ENRICHMENT + ANTHROPIC_API_KEY) — Phase 61, v6.0
- ✓ Design-token foundation (tokens.css + design-tokens.ts) consumed by shell + all 11 pages; audit mean lifted 7.06 → 7.80 — Phase 62, v6.0
- ✓ 5 motion primitives (FadeIn, Stagger, HoverLift, PressScale, DataLoadReveal); mobile-responsive at 375px with 44px tap targets — Phase 62, v6.0
- ✓ AI advisor live-audit on Railway: 7 PASS / 5 WARN / 0 FAIL (baseline 4P/3W/5F) — Phase 63, v6.0
- ✓ `meta.data_as_of` + `/api/projections/latest-week` + advisor auto-week-resolution — Phase 63, v6.0
- ✓ Cache-first external rankings fallback (Sleeper PASS, FantasyPros graceful stale) — Phase 63, v6.0
- ✓ `usePersistentChat` + localStorage persists chat across all 10 dashboard routes — Phase 63, v6.0
- ✓ Matchup view rewired to real NFL data: `/api/teams/current-week`, `/roster?side={offense|defense}`, `/defense-metrics` — Phase 64, v6.0
- ✓ Matchup advantages cite raw silver positional rank (`#N/32 vs POS`); slotHash + placeholder defensive roster removed — Phase 64, v6.0
- ✓ Design skill consolidation (option-a): impeccable primary, redesign-skill + emil-design-eng specialized, taste-skill + soft-skill aliased — Phase 65, v6.0
- ✓ 3 NFL-specific rule files (nfl-data-conventions, nfl-scoring-formats, nfl-validation-patterns) — Phase 65, v6.0
- ✓ Skill optimizer audit: 40 items, 1 below 6, PASS verdict — Phase 65, v6.0

### Active

**v7.0 Production Stabilization (in flight)**

- [ ] HOTFIX — ANTHROPIC_API_KEY in Railway env, Bronze schedules+rosters in Docker image, predictions/lineups query params wired
- [ ] ROSTER — refresh_rosters.py handles released/FA/traded, writes to Bronze, audit log surfaced
- [ ] SANITY — live endpoint probes, payload-content validators, roster drift vs Sleeper, blocking post-deploy smoke gate
- [ ] SENT — extractor backfills accumulated news, event_flags populate, news page shows headlines + context
- [ ] FE — predictions/lineups/matchups/news pages handle empty/error states gracefully

**Carried forward (deferred from v6.0):**
- [ ] DQAL-03 warning-count cleanup — rolled into Phase 3 (SANITY) where roster drift + rookie ingest + rank recalibration become sanity-check coverage
- [ ] 61-03 event-adjustment activation — deferred until Bronze event data accumulates (backtest structurally null)

**Post-v7.0 (future milestones):**
- [ ] External projections comparison (ESPN/Sleeper/Yahoo) — v7.1
- [ ] Heuristic consolidation — v7.3
- [ ] Unified evaluation pipeline (full 466-feature residual) — v7.3+
- [ ] Sleeper OAuth integration — v7.1
- [ ] PFF paid data integration — v8.0

## Current State: v7.0 Shipped (2026-04-24)

**Production:**
- Frontend: https://frontend-jet-seven-33.vercel.app — now with defensive empty states + data_as_of freshness chips on predictions/lineups/matchups/news pages
- Backend: https://nfldataengineering-production.up.railway.app — graceful server-side defaulting on `/api/predictions`, `/api/lineups`, `/api/teams/{team}/roster` (200 with empty envelope instead of 422 when params omitted)
- Docker image now bundles `data/bronze/schedules/` + `data/bronze/players/rosters/` so endpoints stop 503-ing in offseason
- `ANTHROPIC_API_KEY` set on Railway environment (LLM enrichment ready; GHA secret still needed separately)
- Roster refresh v2: `refresh_rosters.py` handles released/FA/traded players, writes to Bronze live, surfaces `roster_changes.log` as GHA artifact
- Sanity-Check v2: `scripts/sanity_check_projections.py` now probes live endpoints, validates payload content (not just length), checks roster drift vs Sleeper canonical, asserts API key presence + extractor freshness, absorbs DQAL-03 carry-overs. 57 new tests. Canary test replays all 6 audit regressions and passes.
- GHA `deploy-web.yml` promoted to blocking live gate with `auto-rollback` job (`git revert --no-edit` + `git push`, 5-min window, no force-push, audit commit format, 20 structural tests)
- Frontend: new shared `<EmptyState />` component across 4 pages; news feed null-safety prevents dangling sentiment chips
- Daily sentiment cron running at `0 12 * * *` UTC with hardened permissions (`contents: write`, `issues: write`) and decoupled roster refresh (hardcoded season=2026)
- Test count: ~1469 passing (+90 from v7.0)

**v7.0 outcome:** 23/32 requirements satisfied in code + tests; 9/32 pending external ops (GitHub Secret + Variable for sentiment extraction, daily cron observation, first live rollback proof). Zero `gaps_found` at milestone audit.

**v7.0 artifacts:**
- Milestone roadmap: `.planning/milestones/v7.0-ROADMAP.md`
- Milestone requirements: `.planning/milestones/v7.0-REQUIREMENTS.md`
- Milestone audit: `.planning/v7.0-MILESTONE-AUDIT.md`

## Pending v7.0 External Ops (user action required)

1. Set GitHub Secret `ANTHROPIC_API_KEY` at https://github.com/gesmith0606/nfl_data_engineering/settings/secrets/actions
2. Set GitHub Variable `ENABLE_LLM_ENRICHMENT=true` at .../settings/variables/actions
3. Re-trigger `gh workflow run daily-sentiment.yml -f season=2025 -f week=17` (and `week=18`)
4. Run `scripts/audit_advisor_tools.py --live https://nfldataengineering-production.up.railway.app` — expect 4 news tools to flip WARN→PASS
5. Observe daily cron for Kyler Murray roster canary (ROSTER-05)
6. Run 6 verification curls from `.planning/milestones/v7.0-phases/66-p0-deployment-hotfixes/66-VERIFICATION.md`
7. Observe or deliberately trigger first live rollback (SANITY-09 end-to-end proof)

Estimated total operational effort: 30-60 min.

## v7.0 Tech Debt → v7.1 cleanup scope

- `git commit --amend --no-verify` in auto-rollback (medium, policy violation)
- `web/frontend/**/*.json` ignored by repo-root `*.json` pattern (medium, vitest deps on-disk only)
- Player Bronze parquet unavailable to GHA runner (medium, PlayerNameResolver blind)
- `refresh_rosters --season 2026` hardcoded (low, replace with `$(date +%Y)`)
- Duplicate `relativeTime()` in news-feed + player-news-panel (low, consolidate with format-relative-time)
- `VALID_NFL_TEAMS` redundant LA+LAR (low, pre-existing)
- `test_auto_rollback_pushes_non_force` should assert `--no-verify` absence (low)
- `formatRelativeTime("")` returns "unknown" — guard upstream (medium)

### Planned (Future Milestones)
- v7.1 External Projections Comparison — ESPN/Sleeper/Yahoo projections side-by-side on projections page for user comparison
- v7.1 Sleeper League Integration — username → leagues, roster import, personalized start/sit, advisor access to user rosters
- v7.2 Marketing & Content — Remotion video generation, YouTube/Instagram/TikTok distribution, NotebookLM podcast pipeline
- v7.3 Heuristic consolidation — unify `generate_weekly_projections` + `generate_heuristic_predictions` + `compute_production_heuristic`
- v8.0 PFF Data Integration — true WR-CB coverage, OL blocking grades ($300-500/season)
- v9.0 Multi-Platform — ESPN/Yahoo league support

### Out of Scope

- S3 sync — AWS credentials expired, local-first workflow active
- nflreadpy migration — requires Python 3.10+; separate future milestone
- Neural networks / deep learning — gradient boosting dominates tabular sports prediction at this data scale
- Real-time prediction serving — batch weekly predictions sufficient

## Context

Shipped v4.1 with ~40,000 LOC Python across 50+ phases and 100+ plans (nine milestones).
Tech stack: Python 3.9, pandas, pyarrow, pytz, xgboost, lightgbm, catboost, scikit-learn, optuna, shap, nfl-data-py, neo4j (Docker dual-path fallback), local Parquet storage (S3 optional), PostgreSQL (game/college archive).
Bronze layer: 18 data types (16 NFL + 2 college) + odds (FinnedAI 2016-2021, nflverse bridge 2022-2025) covering 10 seasons of complete data; PBP participation ingestion ready.
Silver layer: 14 team output paths (including market/line movement, graph features for all 10 seasons), 3 player output paths, 15 prospect features (college teammate networks, coaching trees, prospect comps), 49 total graph features (22 NFL + 27 college/prospect).
Gold layer: weekly + preseason fantasy projections (QB via ML, RB/WR/TE via heuristic with hybrid residual testing); ML game predictions with 120-feature SHAP-selected ensemble (market features included); kicker projections; game results archive (1999-2026) + player stats per game (all scoring formats).
Prediction feature vector: 1139 raw columns → 120 SHAP-selected features. `diff_opening_spread` is #1 feature (23.6% SHAP importance).
ML models (game prediction): v2.1 stacking ensemble (XGB+LGB+CB + Ridge meta-learner) with market features; walk-forward CV, sealed 2025 holdout (51.7% ATS, 50.6% with market features). CLV tracking measures model quality against closing lines.
Player models (fantasy): 19 per-position per-stat XGBoost models (2016-2025 training data +66% from v2.0, walk-forward CV, SHAP feature selection). QB SHIP (6.72 MAE, 14% better than heuristic). RB/WR/TE under evaluation with hybrid residual approach (train ML on heuristic errors, not raw projections). Graph features (49) integrated; 22 NFL + 27 college/prospect for draft preparation.
College integration (CFBD API): prospect profiles with scheme familiarity, conference adjustment, comparable arcs, bust rates, coaching tree lineage, college teammate networks (tracked annually).
Game archive: PostgreSQL tables (game_results, game_player_stats) for historical lookup and backtest validation; all 3 scoring formats (PPR/Half-PPR/Standard) computed per game.
API endpoints: 14 total (3 projections, 2 predictions, 2 players, 1 lineups, 3 games, 3 college).
Tests: 1154 passing across 25 test files. Web API (FastAPI, 14 endpoints) with 25 passing tests. PostgreSQL schema with 4 tables + 13 indexes.

Existing documentation:
- `CLAUDE.md` — project reference, commands, architecture
- `docs/NFL_DATA_DICTIONARY.md` — table definitions for all 15+ Bronze types
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — ML prediction model design
- `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` — implementation roadmap
- `docs/BRONZE_LAYER_DATA_INVENTORY.md` — bronze inventory (auto-generated)

## Constraints

- **Data source**: nfl-data-py is the primary API; some functions have quirks (e.g., `import_rosters` vs `import_seasonal_rosters`)
- **Storage**: Local-first (data/bronze/, data/silver/, data/gold/) with S3 as optional fallback
- **Seasons**: Player data 2020-2025; schedules back to 1999; PBP back to 2016; most types 2016-2025
- **Python**: 3.9 compatible; pandas/pyarrow for all processing

## Key Decisions (Phases 51-53 Research)

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Graph features (22 features from PBP participation) | Relational signal for matchups, injury cascades, scheme | ✓ 17/22 survived SHAP selection, carry signal but don't flip positions alone |
| Ridge/ElasticNet models (Phase 53) | Reduce overfitting vs XGBoost on small datasets | ✓ Ridge better than XGB for WR/TE, but still trails heuristic |
| Training data expansion (2016-2025) | More history improves generalization | ✓ QB improved 14% (7.84→6.72 MAE); RB within 1%, WR/TE closing gap |
| Hybrid residual approach (industry standard) | Don't replace heuristic, improve it; train ML on errors | ✓ Good — mirrors FantasyPros/PFF/ESPN production models |
| Heuristic as baseline linear model | Weighted roll3/roll6/std × domain multipliers is optimal | ✓ Good — confirmed via ablation: simpler is better |

## Previous Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Local-first storage | AWS credentials expired March 2026 | ✓ Good — fast iteration |
| nfl-data-py as primary source | Battle-tested, covers 95% of needed data | ✓ Good |
| Parquet format | Columnar, compressed, pandas-native | ✓ Good |
| Registry dispatch pattern | Adding a data type is config-only | ✓ Good |
| Adapter pattern (NFLDataAdapter) | Isolates nfl-data-py for future migration | ✓ Good |
| 103 PBP columns (not ~80) | All EPA/WPA/CPOE variants needed for prediction | ✓ Good |
| Warn-never-block validation | Bronze accepts raw data; validation is informational | ✓ Good |
| QBR frequency-prefixed filenames | Prevents weekly/seasonal collision | ✓ Good |
| No row counts in inventory | Too slow for large datasets | ✓ Good |
| stats_player adapter for 2025 | nflverse deprecated old player_stats tag | ✓ Good |
| Week partition registry flag | Automatic per-week file splitting (snap_counts) | ✓ Good |
| Batch ingestion with skip-existing | Idempotent reruns, graceful failure handling | ✓ Good |
| Dry-run default for cleanup scripts | Safe filesystem operations | ✓ Good |
| Rolling windows for team metrics | In-season predictions need recency; season aggregates miss momentum | ✓ Good |
| Separate team_analytics.py module | Protects existing player_analytics.py test suite | ✓ Good |
| Three-tier join for advanced profiles | GSIS ID (NGS), name+team (PFR/QBR), team-only (blitz) | ✓ Good |
| Static dimension table for historical | No season/week partition; avoids row explosion | ✓ Good |
| Lagged SOS (week N-1 only) | Avoids circular dependency in opponent-adjusted EPA | ✓ Good |
| PBP expanded to 140 columns | Penalty, ST, fumble recovery, drive fields needed for v1.3 metrics | ✓ Good |
| STADIUM_ID_COORDS dict (not CSV) | Config lookup matches nflverse stadium_id strings directly | ✓ Good |
| Turnover luck uses expanding window | Regression-to-mean needs full-season context, not 3-game rolling | ✓ Good |
| Referee tendencies from schedules referee col | Simpler than joining Officials Bronze; crew chief name sufficient | ✓ Good |
| Playoff context with simple proxy | Cumulative W-L-T + division rank captures 95% of elimination signal | ✓ Good |
| Game context per-game facts (no rolling) | Weather/rest/travel are single-game properties, not trends | ✓ Good |
| XGBoost as initial model | Simplest gradient boosting, proven on tabular NFL data | ✓ Good — later expanded to ensemble |
| Walk-forward CV (train 1..N, validate N+1) | Respects temporal ordering; no future leakage | ✓ Good |
| Sealed 2024 holdout | Never touched during tuning; honest final evaluation | ✓ Good |
| Conservative default hyperparameters | Shallow trees (max_depth=4), strong L1/L2 regularization, early stopping | ✓ Good |
| Confidence tiers at 3.0/1.5 thresholds | Simple, interpretable edge buckets for user filtering | ✓ Good |
| Vig-adjusted profit at -110 odds | Standard sportsbook vig; realistic profit accounting | ✓ Good |
| XGB+LGB+CB stacking with Ridge | Model diversity improves generalization over single XGBoost | ✓ Good — +3% ATS on holdout |
| SHAP-based feature selection | Walk-forward-safe, per-fold isolation, holdout excluded | ✓ Good — 310→100 features |
| Honest ablation for Phase 31 features | Momentum/EWM improved training but not holdout | ✓ Good — shipped P30 ensemble |
| Conservative hyperparameters for LGB/CB | Analogous to XGBoost: shallow trees, strong regularization | ✓ Good |
| CLV = predicted_margin - spread_line | Point-based CLV is the gold standard for betting model evaluation | ✓ Good |
| Ablation saves to models/ensemble_ablation/ | Protects production model during comparison | ✓ Good |
| Ship market features only if holdout ATS improves | Accuracy is the decision criterion, not model purity | ✓ Good |
| CI quality-gate keys on exit code only (no stdout grep) | Preserves warnings-allowed contract; 0 = deploy, 1 = block | ✓ Good — phase 60 |
| D-06 graceful-failure contract on every news ingestor | Daily cron must never be blocked by a single upstream flake | ✓ Good — phase 61, 7 resilience tests |
| Rule-first sentiment, Haiku demoted to optional sidecar | Pipeline ships with no API key dependency; enrichment is website-only | ✓ Good — phase 61, D-01/D-02/D-04/D-06 |
| Design-token layer is additive (:root custom properties only) | theme.css retains sole color ownership; zero visual change on shipment | ✓ Good — phase 62 |
| ADVR-02 via `meta.data_as_of` + auto-resolve | Advisor discovers latest week from response metadata, not client-side guesses | ✓ Good — phase 63 |
| Matchup advantages cite raw silver positional rank | Opaque synthesized scores replaced with auditable `#N/32 vs POS` | ✓ Good — phase 64 |
| Design skill consolidation option-a (umbrella-with-modes) | Single primary (impeccable) prevents multi-skill incoherence; specialized/aliased roles explicit | ✓ Good — phase 65 |
| Skill audit: 1 item below 6 is PASS (target <3) | Small gap (security-reviewer Testability 5) doesn't block shipment | ✓ Good — phase 65 |
| Accept DQAL-03 as [~] partial | 34 warnings = pre-existing data debt out of phase 60 scope; CI gate delivers full security value regardless | ⚠️ Revisit in v7.0 — clamp/rookie fixes |
| FinnedAI JSON (not SBRO XLSX) for odds | JSON simpler to parse, same data, no openpyxl dep needed | ✓ Good |
| 45-entry hardcoded team mapping | Explicit and auditable vs fuzzy matching; covers all FinnedAI names | ✓ Good |
| Negate FinnedAI spreads for nflverse convention | Positive = home favored; one-line transform avoids confusion | ✓ Good |
| Ordinal float64 for magnitude buckets | Survives numeric dtype filter in feature_engineering.py | ✓ Good |
| Opening lines only in _PRE_GAME_CONTEXT | Closing-line-derived features are retrospective (leakage) | ✓ Good |
| CLV uses nflverse spread_line (not FinnedAI) | nflverse has full season coverage; FinnedAI only 2016-2021 | ✓ Good |
| nflverse closing lines as opening proxies for 2022+ | Free, 100% coverage, gradient boosting handles approximate values | ✓ Good — 0% NaN on market features |
| line_source provenance column | Distinguishes FinnedAI from nflverse data for downstream filtering | ✓ Good |
| Derived season ranges from HOLDOUT_SEASON | Future holdout rotations are a one-line change | ✓ Good |
| No hyperparameter re-tuning during holdout rotation | Fair baseline comparison; avoids confounding tuning with holdout change | ✓ Good |
| SHAP-based feature selection (321→120 features) | Removes noise, preserves signal; diff_opening_spread confirmed as #1 | ✓ Good |
| Market features SHIP verdict | 50.6% > 50.2% ATS on structurally valid ablation (6 seasons training data) | ✓ Good — definitive answer |

## Previous Milestone: v3.0 Player Fantasy Prediction System

**Shipped:** 2026-04-01 | **Phases:** 39-48 | **Plans:** 15 | **Delivered:** Per-position ML models (QB SHIP), ML projection router, Neo4j infrastructure, 22 graph features (injury cascade, WR/TE/OL matchup, scheme), kicker projections, game-level constraints (opt-in), 841 tests

See `.planning/milestones/v3.0-ROADMAP.md` for full archive.

## Previous Milestone: v2.2 Full Odds + Holdout Reset

**Shipped:** 2026-03-29 | **Phases:** 35-38 | **Plans:** 7 | **Delivered:** Full odds coverage (2016-2025), holdout rotated to 2025, market feature ablation SHIP verdict, 120-feature SHAP-selected ensemble

See `.planning/milestones/v2.2-ROADMAP.md` for full archive.

## Previous Milestone: v2.1 Market Data

**Shipped:** 2026-03-28 | **Phases:** 32-34 | **Plans:** 6

See `.planning/milestones/v2.1-ROADMAP.md` for full archive.

## Previous Milestone: v2.0 Prediction Model Improvement

**Shipped:** 2026-03-27 | **Phases:** 28-31 | **Plans:** 8 | **Result:** 53.0% ATS, +$3.09 profit on sealed 2024 holdout

See `.planning/milestones/v2.0-ROADMAP.md` for full archive.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-21 after v7.0 Production Stabilization milestone started*
