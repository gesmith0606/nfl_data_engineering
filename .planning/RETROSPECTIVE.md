# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

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

### Cumulative Quality

| Milestone | Tests | Coverage | Key Metric |
|-----------|-------|----------|------------|
| v1.0 | 141 | — | 23/23 requirements satisfied, 9/9 integrations connected |
| v1.1 | 186 | — | 22/22 requirements satisfied, 7/7 integrations wired, 2/2 E2E flows |
| v1.2 | 289 | — | 25/25 requirements satisfied, 22/25 integrations wired, 3/4 E2E flows |

### Top Lessons (Verified Across Milestones)

1. Milestone audits catch real gaps — invest in audit-first before marking complete
2. Wire validation/health checks into pipelines during initial implementation, not as gap closure
3. Plan for integration testing within feature phases, not as separate gap-closure work
4. Registry/adapter patterns pay dividends — adding new types and modules is config-only
5. nflverse API instability (tag renames, schema changes) requires defensive adapter routing
6. Established conventions (rolling windows, join patterns) compound — v1.2 was 2x faster than v1.0
