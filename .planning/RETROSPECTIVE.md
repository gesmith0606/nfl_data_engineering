# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~5 | 7 | First GSD milestone; 3 audit cycles to pass |

### Cumulative Quality

| Milestone | Tests | Coverage | Key Metric |
|-----------|-------|----------|------------|
| v1.0 | 141 | — | 23/23 requirements satisfied, 9/9 integrations connected |

### Top Lessons (Verified Across Milestones)

1. Milestone audits catch real gaps — invest in audit-first before marking complete
2. Wire validation into pipelines during initial implementation, not as gap closure
