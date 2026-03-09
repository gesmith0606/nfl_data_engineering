# Requirements: NFL Data Engineering

**Defined:** 2026-03-08
**Core Value:** A rich NFL data lake powering both fantasy football projections and game outcome predictions

## v1.1 Requirements

Requirements for Bronze Backfill milestone. Each maps to roadmap phases.

### Setup

- [ ] **SETUP-01**: Config caps injury season range at 2024 (data source discontinued)
- [ ] **SETUP-02**: GITHUB_TOKEN configured for nfl-data-py downloads to avoid rate limiting
- [ ] **SETUP-03**: nfl-data-py version pinned in requirements to prevent breaking changes

### New Data Types

- [ ] **INGEST-01**: Teams reference data ingested for 2016-2025
- [ ] **INGEST-02**: Draft picks data ingested for 2016-2025
- [ ] **INGEST-03**: Combine data ingested for 2016-2025
- [ ] **INGEST-04**: Depth charts ingested for 2016-2025 (handle 2025 schema change)
- [ ] **INGEST-05**: QBR weekly + seasonal ingested for 2016-2025
- [ ] **INGEST-06**: NGS passing, rushing, receiving ingested for 2016-2025
- [ ] **INGEST-07**: PFR weekly (pass/rush/rec/def) ingested for 2018-2025
- [ ] **INGEST-08**: PFR seasonal (pass/rush/rec/def) ingested for 2018-2025
- [ ] **INGEST-09**: PBP ingested for 2016-2025 (103 curated columns)

### Existing Type Backfill

- [ ] **BACKFILL-01**: Schedules extended to 2016-2025
- [ ] **BACKFILL-02**: Player weekly extended to 2016-2025
- [ ] **BACKFILL-03**: Player seasonal extended to 2016-2025
- [ ] **BACKFILL-04**: Snap counts extended to 2016-2025 (handle week-level iteration)
- [ ] **BACKFILL-05**: Injuries extended to 2016-2024 (source discontinued after 2024)
- [ ] **BACKFILL-06**: Rosters extended to 2016-2025

### Orchestration

- [ ] **ORCH-01**: Batch ingestion script runs all data types in sequence with progress reporting
- [ ] **ORCH-02**: Script handles failures gracefully (skip failed type, continue, report at end)

### Validation

- [ ] **VALID-01**: All ingested data passes Bronze validate_data() checks
- [ ] **VALID-02**: Bronze inventory regenerated reflecting full 10-year dataset

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Silver/Gold Expansion

- **SILVER-01**: Silver layer expanded to leverage PBP, NGS, PFR data
- **GOLD-01**: Gold projections upgraded with advanced stats features
- **ML-01**: ML models (RF/XGBoost) replace weighted-average baseline

## Out of Scope

| Feature | Reason |
|---------|--------|
| S3 sync | AWS credentials expired, local-first workflow active |
| Neo4j graph DB | Deferred until prediction model is validated |
| nflreadpy migration | Requires Python 3.10+; separate future milestone |
| Cross-year schema comparison | Nice-to-have, not core to backfill |
| Live Sleeper integration | Deferred to draft season |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SETUP-01 | Phase 8 | Pending |
| SETUP-02 | Phase 8 | Pending |
| SETUP-03 | Phase 8 | Pending |
| INGEST-01 | Phase 9 | Pending |
| INGEST-02 | Phase 9 | Pending |
| INGEST-03 | Phase 9 | Pending |
| INGEST-04 | Phase 9 | Pending |
| INGEST-05 | Phase 9 | Pending |
| INGEST-06 | Phase 9 | Pending |
| INGEST-07 | Phase 9 | Pending |
| INGEST-08 | Phase 9 | Pending |
| INGEST-09 | Phase 9 | Pending |
| BACKFILL-01 | Phase 10 | Pending |
| BACKFILL-02 | Phase 10 | Pending |
| BACKFILL-03 | Phase 10 | Pending |
| BACKFILL-04 | Phase 10 | Pending |
| BACKFILL-05 | Phase 10 | Pending |
| BACKFILL-06 | Phase 10 | Pending |
| ORCH-01 | Phase 11 | Pending |
| ORCH-02 | Phase 11 | Pending |
| VALID-01 | Phase 11 | Pending |
| VALID-02 | Phase 11 | Pending |

**Coverage:**
- v1.1 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-03-08*
*Last updated: 2026-03-08 after v1.1 roadmap creation*
