# Roadmap: NFL Data Engineering Platform

## Milestones

- v1.0 Bronze Expansion -- Phases 1-7 (shipped 2026-03-08)
- v1.1 Bronze Backfill -- Phases 8-14 (shipped 2026-03-13)
- v1.2 Silver Expansion -- Phases 15-19 (shipped 2026-03-15)
- v1.3 Prediction Data Foundation -- Phases 20-23 (shipped 2026-03-19)
- v1.4 ML Game Prediction -- Phases 24-27 (shipped 2026-03-22)
- v2.0 Prediction Model Improvement -- Phases 28-31 (shipped 2026-03-27)
- v2.1 Market Data -- Phases 32-34 (shipped 2026-03-28)
- v2.2 Full Odds + Holdout Reset -- Phases 35-38 (shipped 2026-03-29)
- v3.0 Player Fantasy Prediction System -- Phases 39-48 (shipped 2026-04-01)
- v3.1 Graph-Enhanced Fantasy Projections -- Phases 49-53 (shipped 2026-04-03)
- v3.2 Model Perfection -- Phases 54-57 (shipped 2026-04-09)
- *v4.0 Production Launch -- Phases W7-W12 (parallel, see .planning/v4.0-web/)*
- **v5.0 Sentiment v2 -- Phases SV2-01 through SV2-04 (current)**

---

## Phase W7: Sleeper League Integration

**Goal:** Connect users' Sleeper fantasy football leagues to the platform for personalized roster management, start/sit advice, and waiver wire recommendations -- all via Sleeper's free public API (no OAuth needed).

**Plans:** 3 plans

Plans:
- [ ] W7-01-PLAN.md -- Backend Sleeper service + player ID mapping + FastAPI endpoints
- [ ] W7-02-PLAN.md -- Frontend connect flow, My Team page, roster display, waiver wire
- [ ] W7-03-PLAN.md -- AI advisor tools for roster and waiver wire context

**Requirements:** SLP-01 through SLP-13
**Dependencies:** Existing FastAPI backend (W1-W5), AI advisor (built), projection data (Gold layer)
**Success criteria:**
1. User enters Sleeper username and sees their leagues
2. Selecting a league shows roster with projected points and start/sit badges
3. Waiver wire suggestions show top available players in the league
4. AI advisor can access user's roster and give personalized advice
5. League context persists in localStorage across sessions

---

## v5.0 Sentiment v2: Live News Feed + Sentiment-Adjusted Models

**Goal:** Daily news feed with rule-based sentiment extraction, team-level sentiment for game line adjustment, and a dedicated news page on the website -- all without requiring an Anthropic API key.

**Plans:** 4 plans

Plans:
- [ ] SV2-01-PLAN.md -- Reddit scraper + rule-based extraction (no API key needed)
- [ ] SV2-02-PLAN.md -- Team-level sentiment aggregation + game line adjustment
- [ ] SV2-03-PLAN.md -- Website news feed page + team sentiment badges
- [ ] SV2-04-PLAN.md -- Daily automation (pipeline script + GitHub Actions cron)

### Phase SV2-01: Reddit Scraper + Rule-Based Extraction
**Goal:** Build Reddit ingestion and rule-based signal extraction so the sentiment pipeline works without an Anthropic API key.
**Requirements:** SV2-01, SV2-02, SV2-03, SV2-04
**Dependencies:** None (builds on existing S1-S2 infrastructure)
**Success criteria:**
1. Reddit posts from r/fantasyfootball and r/nfl fetched and saved as Bronze JSON
2. Rule-based extractor produces PlayerSignal objects for injury, trade, role, positive/negative patterns
3. Pipeline auto-selects rule extractor when no ANTHROPIC_API_KEY is set
4. All tests pass

### Phase SV2-02: Team Sentiment + Game Line Adjustment
**Goal:** Aggregate player signals into team-level sentiment and apply as post-prediction edge modifier to game lines.
**Requirements:** SV2-05, SV2-06, SV2-07, SV2-08
**Dependencies:** SV2-01 (needs extraction pipeline working)
**Success criteria:**
1. Team sentiment aggregated for all 32 NFL teams per week
2. Team sentiment multiplier bounded to [0.95, 1.05]
3. Game predictions show sentiment-adjusted edges with --use-sentiment flag
4. Edge adjustment is conservative (max +/- 0.15 pts)

### Phase SV2-03: Website News Feed
**Goal:** Build a dedicated news page with filters and team sentiment badges on the predictions page.
**Requirements:** SV2-09, SV2-10, SV2-11, SV2-12, SV2-13
**Dependencies:** SV2-01 (needs data flowing through pipeline)
**Success criteria:**
1. /dashboard/news page shows all recent news, most recent first
2. Filter by All / Player / Team works
3. Team sentiment badges visible on predictions page
4. Player news panel shows last-updated time
5. TypeScript compiles without errors

### Phase SV2-04: Daily Automation
**Goal:** Automated daily pipeline via GitHub Actions that ingests, extracts, and aggregates sentiment data.
**Requirements:** SV2-14, SV2-15, SV2-16
**Dependencies:** SV2-01, SV2-02 (needs full pipeline working)
**Success criteria:**
1. Single script runs full daily pipeline end-to-end
2. GitHub Actions cron fires daily at noon UTC
3. Pipeline is idempotent (safe to re-run)
4. Failure auto-opens GitHub issue

---

## v3.2 Model Perfection

**Goal:** Push fantasy MAE below 4.5 through unified evaluation pipeline and advanced modeling.

**Current baseline:** MAE 4.77 (QB 6.58, RB 5.00, WR 4.63, TE 3.58)

### Phase 54: Unified Evaluation Pipeline
**Goal:** Align training and backtest to use the same production heuristic and full 466-feature set.
**Requirements:** EVAL-01, EVAL-02, EVAL-03, EVAL-04
**Dependencies:** None
**Success criteria:**
1. Backtest generates production heuristic projections with ALL multipliers (usage, matchup, Vegas, ceiling shrinkage)
2. Full 466-feature set assembled and available during backtest evaluation
3. Residual models retrained against production heuristic (not simplified)
4. Per-position MAE comparison: degraded (42 features) vs full (466 features)
5. Tests passing

### Phase 55: Full-Feature Residual Deployment
**Goal:** Deploy residual models with full features for all positions, update router.
**Requirements:** RES-01, RES-02, RES-03, RES-04, RES-05
**Dependencies:** Phase 54 (unified pipeline must exist)
**Success criteria:**
1. WR residual improvement increases from -4.5% to -10%+ with full features
2. TE residual improvement increases from -5.0% to -8%+ with full features
3. QB and RB residual evaluated -- ship if beats standalone
4. ML projection router updated with best approach per position
5. Overall MAE improved (target: < 4.5)

### Phase 56: Bayesian Hierarchical Models
**Goal:** Implement Bayesian player models with partial pooling and posterior uncertainty.
**Requirements:** BAYES-01, BAYES-02, BAYES-03, BAYES-04
**Dependencies:** Phase 54 (needs unified evaluation for fair comparison)
**Success criteria:**
1. PyMC or NumPyro model implemented with position-level priors
2. Walk-forward CV completed with same folds as Ridge/XGB
3. MAE compared to heuristic, Ridge, and XGB per position
4. Posterior predictive intervals provide calibrated floor/ceiling
5. Ship if any position improves; valuable even if MAE is similar (uncertainty)

### Phase 57: Quantile Regression + Final Validation
**Goal:** Replace hardcoded floor/ceiling with data-driven percentiles, run final validation.
**Requirements:** QUANT-01, QUANT-02, QUANT-03, INFRA-01, INFRA-02, INFRA-03
**Dependencies:** Phases 55-56 (final model state must be known)
**Success criteria:**
1. LightGBM quantile models trained for 10th/50th/90th percentiles
2. Calibration: 80% of actuals fall within 10th-90th range
3. Floor/ceiling in projection_engine.py uses quantile bounds
4. Final backtest: overall MAE < 4.5
5. All tests passing, docs updated

---

## Requirement Coverage

| REQ-ID | Phase | Description |
|--------|-------|-------------|
| EVAL-01 | 54 | Identical production heuristic |
| EVAL-02 | 54 | Full 466-feature set |
| EVAL-03 | 54 | Residual trained vs production |
| EVAL-04 | 54 | Per-position MAE comparison |
| RES-01 | 55 | WR full-feature residual |
| RES-02 | 55 | TE full-feature residual |
| RES-03 | 55 | QB residual evaluation |
| RES-04 | 55 | RB residual evaluation |
| RES-05 | 55 | Router update |
| BAYES-01 | 56 | PyMC/NumPyro dependency |
| BAYES-02 | 56 | Bayesian model implementation |
| BAYES-03 | 56 | Walk-forward CV evaluation |
| BAYES-04 | 56 | Posterior predictive intervals |
| QUANT-01 | 57 | Quantile regression models |
| QUANT-02 | 57 | Calibration evaluation |
| QUANT-03 | 57 | Replace hardcoded floor/ceiling |
| INFRA-01 | all | Tests passing |
| INFRA-02 | all | MAE < 4.5 |
| INFRA-03 | all | No position regression |
| SV2-01 | SV2-01 | Reddit scraper (r/fantasyfootball, r/nfl) |
| SV2-02 | SV2-01 | Rule-based signal extraction (no API key) |
| SV2-03 | SV2-01 | Pipeline auto-selects extractor |
| SV2-04 | SV2-01 | Reddit + rule extractor tests |
| SV2-05 | SV2-02 | Team-level sentiment aggregation |
| SV2-06 | SV2-02 | Team sentiment multiplier [0.95, 1.05] |
| SV2-07 | SV2-02 | Game prediction edge adjustment |
| SV2-08 | SV2-02 | Pipeline CLI runs player + team aggregation |
| SV2-09 | SV2-03 | /dashboard/news page with feed |
| SV2-10 | SV2-03 | News feed filters (All/Player/Team) |
| SV2-11 | SV2-03 | Team sentiment badges on predictions page |
| SV2-12 | SV2-03 | Enhanced player news panel (last updated) |
| SV2-13 | SV2-03 | New API endpoints (feed, team-sentiment) |
| SV2-14 | SV2-04 | Daily pipeline orchestrator script |
| SV2-15 | SV2-04 | GitHub Actions daily cron |
| SV2-16 | SV2-04 | Idempotent pipeline (no duplicate data) |
| SLP-01 | W7 | Sleeper user lookup by username |
| SLP-02 | W7 | League listing for user |
| SLP-03 | W7 | Roster retrieval with player ID mapping |
| SLP-04 | W7 | Matchup data for current week |
| SLP-05 | W7 | Waiver wire (free agent) discovery |
| SLP-06 | W7 | Frontend connect flow (username + league select) |
| SLP-07 | W7 | My Team page with roster display |
| SLP-08 | W7 | Start/sit recommendation badges |
| SLP-09 | W7 | Waiver wire suggestions UI |
| SLP-10 | W7 | localStorage persistence for league context |
| SLP-11 | W7 | AI advisor getMyRoster tool |
| SLP-12 | W7 | AI advisor getWaiverWire tool |
| SLP-13 | W7 | Sleeper context passed to AI advisor |

**Coverage: 48/48 requirements mapped (100%)**
