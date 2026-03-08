# Roadmap: NFL Data Platform — Bronze Expansion

**Created:** 2026-03-08
**Phases:** 4
**Requirements covered:** 23/23

## Phase Overview

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | 2/2 | Complete   | 2026-03-08 | 5 |
| 2 | Core PBP Ingestion | Ingest full play-by-play with EPA/WPA/CPOE | PBP-01 to PBP-04 | 4 |
| 3 | Advanced Stats & Context Data | Ingest NGS, PFR, QBR, depth charts, draft, combine | ADV-01 to ADV-05, CTX-01 to CTX-02, VAL-01 to VAL-03 | 10 |
| 4 | Documentation Update | Align all docs with actual data state | DOC-01 to DOC-04 | 4 |

## Phase Details

### Phase 1: Infrastructure Prerequisites

**Goal:** Fix the three blockers preventing new data type ingestion — local-first support, dynamic season validation, and future-proof architecture.

**Requirements:** INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05

**Plans:** 2/2 plans complete

Plans:
- [ ] 01-01-PLAN.md — Config + adapter layer (dynamic seasons, season ranges, nfl-data-py adapter)
- [ ] 01-02-PLAN.md — Registry CLI + local-first storage + test suite

**Success Criteria:**
1. `bronze_ingestion_simple.py` saves to `data/bronze/` locally when no AWS credentials present
2. Season validation accepts 2026 without code changes
3. All `nfl.import_*` calls routed through `src/nfl_data_adapter.py` adapter module
4. CLI uses a DATA_TYPE_REGISTRY dict — adding a new type requires only a config entry
5. Config has per-type season ranges (e.g., NGS: 2016+, PFR: 2018+)

**Dependencies:** None
**Research needed:** No (well-documented refactoring)

---

### Phase 2: Core PBP Ingestion

**Goal:** Ingest full play-by-play data with EPA, WPA, CPOE, and air yards — the foundation for game prediction.

**Requirements:** PBP-01, PBP-02, PBP-03, PBP-04

**Success Criteria:**
1. PBP parquet files exist in `data/bronze/plays/season=YYYY/` for 2020-2025
2. Each file contains ~80 curated columns including epa, wpa, cpoe, air_yards, success
3. Single-season ingestion completes without OOM (peak memory < 2GB)
4. `python scripts/bronze_ingestion_simple.py --data-type pbp --season 2024` works end-to-end

**Dependencies:** Phase 1 (local-first, adapter, registry)
**Research needed:** Yes (column selection benchmarking, memory profiling)

---

### Phase 3: Advanced Stats & Context Data

**Goal:** Ingest all remaining data types — NGS, PFR, QBR, depth charts, draft picks, combine data.

**Requirements:** ADV-01 to ADV-05, CTX-01, CTX-02, VAL-01 to VAL-03

**Success Criteria:**
1. NGS data in `data/bronze/ngs/{stat_type}/season=YYYY/` for passing/rushing/receiving
2. PFR weekly + seasonal data in `data/bronze/pfr/` for pass/rush/rec/def
3. QBR, depth charts, draft picks, combine data each in their own Bronze directories
4. `validate_data()` handles all new types with required column checks
5. At least 1 test per new fetch method (7+ new tests)

**Dependencies:** Phase 1 (adapter, registry, season config)
**Research needed:** No (straightforward fetch-and-store following existing patterns)

---

### Phase 4: Documentation Update

**Goal:** Update all existing docs to reflect the actual data state after ingestion.

**Requirements:** DOC-01 to DOC-04

**Success Criteria:**
1. `NFL_DATA_DICTIONARY.md` has entries for all 15+ Bronze data types with actual column names
2. `NFL_GAME_PREDICTION_DATA_MODEL.md` marks implemented tables vs planned
3. `BRONZE_LAYER_DATA_INVENTORY.md` reflects actual file counts, sizes, and seasons
4. `NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` updated with realistic phase status

**Dependencies:** Phases 2 and 3 (need actual data to document)
**Research needed:** No

---

## Phase Ordering Rationale

- **Phase 1 before all:** Cannot ingest new data without local-first support and validation fixes
- **Phase 2 before 3:** PBP is the foundation; NGS/PFR add incremental value on top
- **Phase 3 before 4:** Documentation needs actual data to be accurate
- **Each phase is independently valuable:** Phase 2 alone enables a basic prediction model

---
*Roadmap created: 2026-03-08*
*Last updated: 2026-03-08 after phase 1 planning*
