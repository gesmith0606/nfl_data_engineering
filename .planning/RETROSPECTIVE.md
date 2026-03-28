# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v2.1 — Market Data

**Shipped:** 2026-03-28
**Phases:** 3 | **Plans:** 6 | **Sessions:** ~2

### What Was Built
- Bronze odds ingestion: FinnedAI JSON → Parquet with 45-entry team mapping, nflverse join (r=0.997), zero orphans
- Silver line movement features: spread/total shift, ordinal magnitude buckets, key number crossings, per-team reshape with sign flips
- Feature engineering integration: opening_spread/opening_total in pre-game context filter with retrospective feature exclusion
- CLV tracking: evaluate_clv(), by-tier, by-season metrics in prediction backtester and CLI
- Market feature ablation script: P30 baseline vs market-augmented ensemble on sealed holdout with SHAP and ship-or-skip verdict
- 571 tests passing (68 new across 3 new test files)

### What Worked
- Cleanest milestone yet: zero gap-closure phases, audit passed on first cycle with 10/10 requirements satisfied
- 2-day execution (fastest per-phase rate) — well-scoped 3-phase milestone with clear dependencies (32→33→34)
- Ablation framework from v2.0 was directly reusable — ablation_market_features.py followed the same pattern
- Pre-game/retrospective feature classification caught potential leakage early (closing-line features excluded)
- CLV tracking ships independently of ablation outcome — good separation of concerns
- FinnedAI JSON was simpler than expected SBRO XLSX — pivot during research saved complexity

### What Was Inefficient
- Phase 32 SUMMARY frontmatter missing `requirements_completed` for ODDS-01/02/03 — documentation gap carried through to audit
- FinnedAI odds only cover 2016-2021 — market features are NaN for 2022-2024 training window, limiting ablation effectiveness
- Steam move flag is NaN for all rows (no timestamp data) — designed as forward-compatible but currently provides zero signal

### Patterns Established
- Market data pattern: Bronze odds → Silver per-team features → feature_engineering.py auto-discovery via SILVER_TEAM_LOCAL_DIRS
- Pre-game vs retrospective classification: _PRE_GAME_CONTEXT whitelist controls which market features enter the model
- CLV evaluation: `evaluate_clv()`, `compute_clv_by_tier()`, `compute_clv_by_season()` — reusable for any model evaluation
- Ablation isolation: `models/ensemble_ablation/` directory protects production model during comparison
- Ship-or-skip gate: strict `>` comparison on holdout ATS accuracy

### Key Lessons
1. Data coverage gaps matter for ablation — FinnedAI's 2016-2021 window limits market feature testing when training on 2022+
2. CLV is the gold standard for model evaluation — should have been added earlier (v1.4 or v2.0)
3. Forward-compatible schema columns (is_steam_move) are low-cost insurance but add NaN noise in the interim
4. Research phase pivot (SBRO XLSX → FinnedAI JSON) was the right call — simpler is better when data quality is equivalent
5. Small milestones (3 phases) execute faster per-phase than large ones — less context overhead

### Cost Observations
- Model mix: ~60% opus (execution), ~40% sonnet (verification/integration check)
- Sessions: ~2
- Notable: Fastest milestone by wall-clock (2 days for 3 phases); milestone audit was clean on first pass

---

## Milestone: v2.0 — Prediction Model Improvement

**Shipped:** 2026-03-27
**Phases:** 4 | **Plans:** 8 | **Sessions:** ~3

### What Was Built
- Leakage-safe feature pipeline (337→283 features) and LightGBM/CatBoost/SHAP installed for ensemble modeling
- Player quality Silver features (QB EPA, positional quality, injury impact) with shift(1) lag guards
- SHAP-based feature selection with walk-forward-safe per-fold isolation (310→100 features)
- XGB+LGB+CB stacking ensemble with Ridge meta-learner and generalized walk-forward CV with OOF predictions
- Ensemble training CLI with Optuna tuning, --ensemble flag in backtest and prediction CLIs
- Momentum/EWM features with honest ablation (improved training but not holdout)
- Three-way sealed holdout comparison: v1.4 (50.0% ATS, -$12.18) → v2.0 (53.0% ATS, +$3.09)
- 503 tests passing (64 new across 3 new test files)

### What Worked
- Phase 30 ensemble was the clear value driver — +3% ATS and profit flip from negative to positive on sealed holdout
- Honest ablation in Phase 31 saved from shipping a worse model — momentum features overfit to training data
- Feature selection pipeline (Phase 29) was reusable for Phase 31's expanded feature set — re-ran cleanly
- Walk-forward CV generalization (from XGBoost-specific to model-agnostic) enabled all three base learners with one function
- Zero gap-closure phases — all 19 requirements complete on first pass across 4 phases

### What Was Inefficient
- Phase 31 features (momentum/EWM) didn't improve holdout despite improving training — could have been predicted from the small training set (~2K games)
- EWM features were fully pruned by feature selection (0 selected) — the halflife=3 EWM is too correlated with existing roll3 columns
- Feature selection re-run in Phase 31 took significant execution time for a result that reverted to Phase 30's model

### Patterns Established
- Model factory pattern: `make_xgb_model()`, `make_lgb_model()`, `make_cb_model()` — any sklearn-compatible model
- OOF prediction matrix: temporal out-of-fold predictions for Ridge meta-learner training
- Ablation protocol: backup P30 artifacts → retrain P31 → compare → ship winner
- `--ensemble` / `--holdout` CLI flags for side-by-side comparison without breaking existing workflows
- Leakage guard update: `_PRE_GAME_CUMULATIVE` set + `_is_rolling()` regex for new feature suffixes

### Key Lessons
1. Ensemble stacking is the highest-ROI improvement for tabular sports prediction — model diversity > feature engineering at this data scale
2. Honest ablation is essential — ship what works on holdout, not what looks good on training
3. EWM with similar halflife to existing rolling windows adds redundant signal — use only if halflife differs significantly
4. Feature selection pipeline should be designed for re-runability from day one (Phase 29's was)
5. Small-sample domains (~270 holdout games) amplify overfitting risk — simpler models generalize better

### Cost Observations
- Model mix: ~60% opus (execution), ~40% sonnet (verification)
- Sessions: ~3
- Notable: Phase 31's checkpoint pattern worked well for the ship decision — human-in-the-loop at the right moment

---

## Milestone: v1.4 — ML Game Prediction

**Shipped:** 2026-03-22
**Phases:** 4 | **Plans:** 8 | **Sessions:** ~3

### What Was Built
- Complete Silver and Gold data dictionary (12 tables, 734 columns documented from Parquet)
- Game-level differential feature assembly (337 features from 8 Silver sources, home-away differentials)
- XGBoost spread and over/under models with walk-forward CV (5 season-boundary folds) and 2024 sealed holdout
- Training CLI with Optuna TPE tuning (50 trials), conservative defaults, and gain-based feature importance
- Backtesting framework with ATS accuracy and vig-adjusted profit accounting at -110 odds
- Weekly prediction pipeline with edge detection vs Vegas lines, confidence tiers, and Gold Parquet output
- 439 tests passing (79 new tests across 3 new test files)

### What Worked
- TDD approach for prediction pipeline (Phase 27) — tests written first, implementation followed cleanly
- Walk-forward CV framework reusable across spread and total models — same code, different target
- Sealed holdout guard (raises error if 2024 in training set) prevents accidental data leakage
- Single-plan Phase 27 was right-sized — prediction pipeline was a focused, well-scoped deliverable
- No gap-closure phases needed — all 20/20 requirements complete on first pass

### What Was Inefficient
- Documentation phase (24) required reading all existing docs to audit staleness — could benefit from automated doc drift detection
- Feature assembly (Phase 25) had the most complex plan (3 plans) but could potentially have been 2 with tighter scoping

### Patterns Established
- Walk-forward CV: `WalkForwardCV(min_train_seasons=3)` with temporal split and holdout guard
- Model persistence: XGBoost JSON format with metadata dict for reproducibility
- Edge detection: `model_line - vegas_line` with tier thresholds (>=3.0 high, >=1.5 medium, else low)
- Backtesting evaluation: ATS accuracy + vig-adjusted profit at standard -110 odds
- Confidence tiers: independent per-metric (spread_tier != total_tier for same game)

### Key Lessons
1. Zero gap-closure phases is achievable when requirements are well-defined upfront and scoped tightly
2. XGBoost + walk-forward CV is the right baseline for tabular sports prediction — simple, interpretable, fast
3. Sealed holdout with a guard clause is essential — prevents accidental leakage during iterative development
4. Confidence tiers should be independent per metric — a game can have high spread edge but low total edge
5. TDD for ML pipelines works well when the interface is well-defined (inputs/outputs clear before training)

### Cost Observations
- Model mix: ~60% opus (execution), ~40% sonnet (verification)
- Sessions: ~3
- Notable: Fastest 4-phase milestone (2 days) — established ML patterns from research phase accelerated execution

---

## Milestone: v1.3 — Prediction Data Foundation

**Shipped:** 2026-03-19
**Phases:** 4 | **Plans:** 9 | **Sessions:** ~4

### What Was Built
- Expanded PBP Bronze to 140 columns and ingested officials data for 2016-2025
- 11 PBP-derived team metrics (penalties, turnovers, red zone trips, FG accuracy, returns, 3rd down, explosives, drives, sacks, TOP) with rolling windows in Silver
- Game context Silver module: weather, rest/travel distance, timezone differential, coaching tenure
- Referee tendency profiles with expanding-window penalty rates and playoff/elimination context
- 337-column prediction feature vector assembled from 8 Silver sources
- Pipeline health monitoring for all 11 Silver paths; 360 tests passing (71 new)

### What Worked
- Parallel execution of Phases 21 and 22 (both depended only on Phase 20) compressed timeline
- Health check wiring done in-phase (learned from v1.2 lesson) — no gap-closure phase needed
- Audit passed on first cycle (tech_debt only, 0 requirement gaps) — best audit result yet
- game_context.py as a new module kept team_analytics.py stable during heavy expansion
- Feature vector integration test (test_feature_vector.py) caught join issues early

### What Was Inefficient
- Officials Bronze ingested (INFRA-02) but never consumed by any Silver pipeline — referee tendencies use schedules `referee` column instead. Infrastructure work with no downstream consumer.
- Duplicate `_filter_st_plays` in team_analytics.py (lines 136 and 1248) from out-of-order plan execution — same issue as v1.1 duplicate patterns
- STADIUM_ID_COORDS has 42 entries but no dedicated unit test (only STADIUM_COORDINATES tested)
- Nyquist validation left in draft state for 3 of 4 phases — validation step was consistently skipped

### Patterns Established
- Expanding window for regression metrics: `shift(1).expanding().mean()` for turnover luck, referee tendency
- Per-game facts pattern: weather/rest/travel output raw values (no rolling) — they're single-game properties
- Cross-source join: unpivot schedules → merge with Silver metrics for derived features
- Cumulative standings: W-L-T with shift(1) lag for playoff/elimination context
- Feature vector assembly: left joins on [team, season, week] across all Silver sources

### Key Lessons
1. Audit on first cycle is achievable when gap-closure patterns from prior milestones are internalized
2. Don't ingest data without a confirmed downstream consumer — Officials Bronze is wasted infrastructure
3. Expanding windows (not rolling) are correct for regression-to-mean and cumulative metrics
4. Feature vector integration test should be written early (Phase 23) — validates entire Silver pipeline
5. Parallel phase execution works well when dependency graph is clean (21‖22 after 20)

### Cost Observations
- Model mix: ~60% opus, ~40% sonnet (more sonnet for parallel execution phases)
- Sessions: ~4
- Notable: 4 days for 4 phases — sustained pace from v1.2; parallel execution of Phases 21+22 was the key accelerator

---

## Milestone: v1.1 — Bronze Backfill

**Shipped:** 2026-03-13
**Phases:** 7 | **Plans:** 12 | **Sessions:** ~6

### What Was Built
- 9 new Bronze data types ingested with full historical coverage (PBP 2016-2025, NGS, PFR, QBR, depth charts, draft picks, combine, teams)
- 6 existing types backfilled from 2020-2024 to 2016-2025 range
- Batch ingestion CLI with progress reporting, failure handling, skip-existing deduplication
- stats_player adapter for 2025 data from nflverse's new release tag with column mapping
- Bronze-Silver path alignment fixes for snap_counts and schedules
- Complete Bronze inventory: 517 files, 93 MB across 15 data types, all validated
- Filesystem cleanup: normalized week=0/ paths, deduplicated draft_picks

### What Worked
- Milestone audit identified real gaps early (snap_counts/schedules path mismatches, validate_data false negative) — resolved via gap-closure Phases 13-14
- stats_player adapter discovery (Phase 12) unblocked 2025 data that was 404'ing on the old tag
- Registry-driven architecture from v1.0 made adding 9 new data types config-only
- Week partition registry flag generalized snap_counts special case for future types
- Dry-run-by-default pattern for cleanup scripts prevented accidental data loss

### What Was Inefficient
- Initial 4-phase roadmap (8-11) expanded to 7 phases (8-14) — gap closure phases added late
- ROADMAP.md plan checkboxes not updated during execution (6 left unchecked despite completion)
- Multiple audit cycles still needed (first audit found integration gaps, second confirmed fixes)
- PBP backfill was a no-op (v1.0 code already handled 2016-2025) — could have been validated without a separate plan

### Patterns Established
- stats_player adapter: conditional routing based on STATS_PLAYER_MIN_SEASON for nflverse tag migration
- Week partition: registry flag `week_partition: True` for automatic per-week file splitting
- Batch ingestion: skip-existing with glob pattern, Result tuple tracking (type, variant, season, status, detail)
- Cleanup scripts: dry-run default with `--execute` flag for filesystem operations
- Column mapping: passing_cpoe -> dakota for backward compatibility across nflverse schema changes

### Key Lessons
1. Plan for gap-closure phases upfront — a 4-phase roadmap becoming 7 is avoidable if integration testing is part of initial scope
2. Keep ROADMAP.md checkboxes synchronized — stale checkboxes create false audit failures
3. nflverse tag changes (player_stats -> stats_player) require monitoring; build adapters with version routing
4. Bronze-Silver path alignment should be verified as part of ingestion phases, not as a separate phase
5. Batch ingestion with skip-existing is essential for large backfills — saves hours on reruns

### Cost Observations
- Model mix: ~80% opus, ~20% sonnet
- Sessions: ~6
- Notable: Gap-closure phases (13, 14) were small and fast; bulk work was in Phases 9-11

---

## Milestone: v1.0 — Bronze Expansion

**Shipped:** 2026-03-08
**Phases:** 7 | **Plans:** 11 | **Sessions:** ~5

### What Was Built
- Registry-driven Bronze CLI supporting 15+ data types with config-only dispatch
- Full PBP ingestion (103 columns, EPA/WPA/CPOE) for 2010-2025
- Advanced stats: NGS, PFR weekly/seasonal, QBR, depth charts, draft picks, combine
- Complete documentation overhaul: data dictionary, inventory script, prediction model badges
- Bronze validation pipeline wired into ingestion (warn-never-block)
- 70 milestone-specific tests (infrastructure, PBP, advanced, inventory, validation)

### What Worked
- GSD workflow enforced structure: discuss -> plan -> execute -> verify cycle kept scope tight
- Milestone audit caught real gaps (missing VERIFICATION.md, validate_data() not wired, hardcoded season bounds) — all resolved before shipping
- Adapter pattern isolation made adding 9 new data types straightforward
- Parametrized tests for sub-typed data sources (NGS/PFR) reduced test boilerplate

### What Was Inefficient
- Three audit cycles needed (gaps_found -> tech_debt -> passed) — could have caught more in first pass
- Phase 5 (verification backfill) was pure documentation — a stricter initial workflow would have avoided it
- Phase 7 tech debt items were small fixes that could have been caught during Phase 2/6 code review

### Patterns Established
- Registry dispatch: DATA_TYPE_REGISTRY dict for CLI data types — config-only to add new types
- Adapter pattern: NFLDataAdapter wraps all nfl-data-py calls — single migration point
- Warn-never-block validation: Bronze accepts raw data, logs warnings, never fails save
- Frequency-prefixed filenames for multi-mode data (QBR weekly vs seasonal)
- Local-first with S3 optional: data/bronze/ is primary, --s3 flag for upload

### Key Lessons
1. Run milestone audit early — the first audit found 5 requirement gaps and 2 integration gaps that required 2 additional phases
2. Enforce VERIFICATION.md creation during phase execution, not as a backfill step
3. validate_data() should be wired into the ingestion flow from day one, not added as a gap-closure phase
4. Hardcoded bounds (season years, etc.) are a recurring tech debt source — use config helpers consistently

### Cost Observations
- Model mix: ~80% opus, ~20% sonnet
- Sessions: ~5
- Notable: Yolo mode + coarse granularity kept overhead low; most time spent on actual code vs process

---

## Milestone: v1.2 — Silver Expansion

**Shipped:** 2026-03-15
**Phases:** 5 | **Plans:** 10 | **Sessions:** ~4

### What Was Built
- PBP-derived team performance metrics (EPA, success rate, CPOE, red zone efficiency) and tendencies (pace, PROE, 4th-down aggressiveness) with 3/6-game rolling windows
- Opponent-adjusted EPA with lagged schedule difficulty rankings and situational splits (home/away, divisional, game script)
- Advanced player profiles from NGS/PFR/QBR data with three-tier join strategy across 47K+ player-weeks
- Historical dimension table with combine measurables and Jimmy Johnson draft chart values for 9,892 players
- Pipeline health monitoring for all 7 Silver paths; tech debt cleanup closing all audit gaps
- 103 new tests (289 total)

### What Worked
- Single tech debt cleanup phase (19) efficiently closed all 4 audit gaps in one plan
- Audit-then-fix pattern from v1.0/v1.1 now well-established — only 1 gap-closure phase needed (vs 2-3 in prior milestones)
- Separate modules (team_analytics.py, player_advanced_analytics.py, historical_profiles.py) kept existing test suite stable
- Three-tier join strategy (GSIS ID, name+team, team-only) solved the cross-source player matching problem cleanly
- Rolling window convention (entity, season groupby with shift(1)) was established once in Phase 15 and reused in all subsequent phases

### What Was Inefficient
- Phase 19 was only needed because health check wiring and config imports weren't done during Phases 15-17 — should be part of initial implementation checklist
- ROADMAP.md plan checkboxes still not auto-updated (same issue as v1.1)
- Phase 19 row in progress table had formatting error (missing milestone column)

### Patterns Established
- Team rolling: `apply_team_rolling(df, cols, [team, season])` with min_periods=1
- Player rolling: `apply_player_rolling(df, cols, [player_id, season])` with min_periods=3
- Static dimension table: no season/week partition, flat Parquet file (historical profiles)
- Three-tier player join: GSIS ID (primary) → name+team (secondary) → team-only (tertiary)
- Lagged SOS: opponent strength uses week N-1 data only to avoid circular dependency
- Synthetic player IDs: name+team hash when GSIS ID unavailable (PFR/QBR sources)

### Key Lessons
1. Wire health check monitoring as part of each feature phase, not as a cleanup step
2. Config constant imports (not hard-coded paths) should be a code review checklist item
3. Three-tier join pattern is robust for cross-source player matching — reuse in future modules
4. Rolling window convention must include groupby columns to prevent cross-season contamination
5. Static dimension tables are the right pattern for rarely-changing reference data (combine, draft)

### Cost Observations
- Model mix: ~70% opus, ~30% sonnet (more sonnet for execution phases)
- Sessions: ~4
- Notable: Fastest milestone yet (3 days) — established patterns from v1.0/v1.1 accelerated execution significantly

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~5 | 7 | First GSD milestone; 3 audit cycles to pass |
| v1.1 | ~6 | 7 | Gap-closure phases (13-14) added from audit; 2 audit cycles |
| v1.2 | ~4 | 5 | Single gap-closure phase (19); fastest milestone (3 days) |
| v1.3 | ~4 | 4 | Clean audit on first cycle (0 requirement gaps); parallel phase execution |
| v1.4 | ~3 | 4 | Zero gap-closure phases; fastest milestone (2 days); ML pipeline complete |
| v2.0 | ~3 | 4 | Ensemble stacking +3% ATS; honest ablation; zero gap-closure; 3 days |
| v2.1 | ~2 | 3 | Smallest milestone; cleanest audit (10/10 first pass); CLV tracking shipped; 2 days |

### Cumulative Quality

| Milestone | Tests | Coverage | Key Metric |
|-----------|-------|----------|------------|
| v1.0 | 141 | — | 23/23 requirements satisfied, 9/9 integrations connected |
| v1.1 | 186 | — | 22/22 requirements satisfied, 7/7 integrations wired, 2/2 E2E flows |
| v1.2 | 289 | — | 25/25 requirements satisfied, 22/25 integrations wired, 3/4 E2E flows |
| v1.3 | 360 | — | 23/23 requirements satisfied, 22/23 integrations wired, 4/4 E2E flows |
| v1.4 | 439 | — | 20/20 requirements satisfied, 0 gap-closure phases needed |
| v2.0 | 503 | — | 19/19 requirements satisfied, 0 gap-closure phases, 53.0% ATS on sealed holdout |
| v2.1 | 571 | — | 10/10 requirements satisfied, 8/8 integrations wired, 1/1 E2E flow, CLV tracking |

### Top Lessons (Verified Across Milestones)

1. Milestone audits catch real gaps — invest in audit-first before marking complete
2. Wire validation/health checks into pipelines during initial implementation, not as gap closure
3. Plan for integration testing within feature phases, not as separate gap-closure work
4. Registry/adapter patterns pay dividends — adding new types and modules is config-only
5. nflverse API instability (tag renames, schema changes) requires defensive adapter routing
6. Established conventions (rolling windows, join patterns) compound — v1.2 was 2x faster than v1.0
7. Don't ingest data without a confirmed downstream consumer — avoid orphaned infrastructure
8. Feature vector integration tests validate entire Silver pipeline early and catch join issues
9. Zero gap-closure is achievable with tight upfront requirements and well-scoped phases
10. TDD works for ML pipelines when interfaces are well-defined before implementation
