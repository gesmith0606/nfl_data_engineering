# Roadmap: NFL Data Engineering Platform

## Milestones

- ✅ **v1.0 Bronze Expansion** — Phases 1-7 (shipped 2026-03-08)
- 🚧 **v1.1 Bronze Backfill** — Phases 8-12 (in progress)

## Phases

<details>
<summary>✅ v1.0 Bronze Expansion (Phases 1-7) — SHIPPED 2026-03-08</summary>

- [x] Phase 1: Infrastructure Prerequisites (2/2 plans) — completed 2026-03-08
- [x] Phase 2: Core PBP Ingestion (1/1 plan) — completed 2026-03-08
- [x] Phase 3: Advanced Stats & Context Data (2/2 plans) — completed 2026-03-08
- [x] Phase 4: Documentation Update (3/3 plans) — completed 2026-03-08
- [x] Phase 5: Phase 1 Verification Backfill (1/1 plan) — completed 2026-03-08
- [x] Phase 6: Wire Bronze Validation (1/1 plan) — completed 2026-03-08
- [x] Phase 7: Tech Debt Cleanup (1/1 plan) — completed 2026-03-08

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

### 🚧 v1.1 Bronze Backfill (In Progress)

**Milestone Goal:** Ingest all 15 registered Bronze data types with 10 years of history (2016-2025), prioritizing 2025 season data.

- [x] **Phase 8: Pre-Backfill Guards** - Config fixes, dependency pins, and rate-limit protection before bulk ingestion (completed 2026-03-09)
- [x] **Phase 9: New Data Type Ingestion** - Ingest all 9 new Bronze data types for 2016-2025 (completed 2026-03-09)
- [x] **Phase 10: Existing Type Backfill** - Extend 6 existing data types from 2020-2024 to 2016-2025 (completed 2026-03-12)
- [x] **Phase 11: Orchestration and Validation** - Batch script, failure handling, validation, and inventory regeneration (completed 2026-03-12)
- [ ] **Phase 12: 2025 Player Stats Gap Closure** - Fetch 2025 player weekly/seasonal stats from nflverse's new `stats_player` release tag, closing BACKFILL-02/03 gaps

## Phase Details

### Phase 8: Pre-Backfill Guards
**Goal**: Pipeline is protected against known failure modes before any bulk data fetching begins
**Depends on**: Phase 7 (v1.0 complete)
**Requirements**: SETUP-01, SETUP-02, SETUP-03
**Success Criteria** (what must be TRUE):
  1. Running `bronze_ingestion_simple.py` for injuries with season 2025 skips gracefully (config cap at 2024)
  2. `GITHUB_TOKEN` is set and nfl-data-py downloads use authenticated requests (5000/hr rate limit)
  3. `pip install -r requirements.txt` on a fresh venv installs exact pinned versions of nfl-data-py and numpy<2
**Plans:** 1/1 plans complete

Plans:
- [x] 08-01-PLAN.md — Config guards, dependency pin comments, GITHUB_TOKEN, and injury cap test

### Phase 9: New Data Type Ingestion
**Goal**: All 9 new Bronze data types are ingested with full coverage per type's valid season range
**Depends on**: Phase 8
**Requirements**: INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, INGEST-07, INGEST-08, INGEST-09
**Success Criteria** (what must be TRUE):
  1. Running `bronze_ingestion_simple.py` for teams, draft_picks, and combine produces valid Parquet files in `data/bronze/`
  2. Running ingestion for NGS (3 sub-types), PFR weekly (4 sub-types), PFR seasonal (4 sub-types), and QBR (2 frequencies) produces correctly-named Parquet files for each variant
  3. Running PBP ingestion for any season 2016-2025 produces a Parquet file with 103 curated columns without exceeding available memory
  4. Depth chart ingestion handles 2025 schema differences without error
  5. `validate_data()` passes on every ingested file across all 9 data types
**Plans:** 3/3 plans complete

Plans:
- [x] 09-01-PLAN.md — CLI enhancements (variant looping, schema diff, summary) + simple types (teams, draft picks, combine, depth charts)
- [ ] 09-02-PLAN.md — Sub-type data types (QBR, NGS, PFR weekly, PFR seasonal)
- [x] 09-03-PLAN.md — PBP backfill (2016-2025)

### Phase 10: Existing Type Backfill
**Goal**: All 6 existing data types have complete 2016-2025 coverage (2016-2024 for injuries)
**Depends on**: Phase 8
**Requirements**: BACKFILL-01, BACKFILL-02, BACKFILL-03, BACKFILL-04, BACKFILL-05, BACKFILL-06
**Success Criteria** (what must be TRUE):
  1. Schedules, player weekly, player seasonal, and rosters each have Parquet files for seasons 2016-2025 in `data/bronze/`
  2. Snap counts have Parquet files for seasons 2016-2025 with correct week-level partitioning
  3. Injuries have Parquet files for seasons 2016-2024 (not 2025, source discontinued)
  4. `validate_data()` passes on all backfilled files
**Plans:** 2/2 plans complete

Plans:
- [x] 10-01-PLAN.md — Fix snap_counts adapter, add week partitioning, backfill 5 simple types
- [x] 10-02-PLAN.md — Backfill snap_counts with week partitioning, verify full coverage

### Phase 11: Orchestration and Validation
**Goal**: Full backfill is repeatable via a single command and completeness is verified
**Depends on**: Phase 9, Phase 10
**Requirements**: ORCH-01, ORCH-02, VALID-01, VALID-02
**Success Criteria** (what must be TRUE):
  1. A single script ingests all 15 data types in sequence with progress output showing type, season, and status
  2. When a data type fails mid-run, the script skips it and continues; a summary at the end lists all failures
  3. `BRONZE_LAYER_DATA_INVENTORY.md` reflects all 15 data types with 10-year coverage after regeneration
**Plans:** 2/2 plans complete

Plans:
- [ ] 11-01-PLAN.md — Batch ingestion script with progress, failure handling, skip-existing, and validation (ORCH-01, ORCH-02, VALID-01)
- [ ] 11-02-PLAN.md — Regenerate Bronze inventory reflecting full 10-year dataset (VALID-02)

## Progress

**Execution Order:**
Phases 9 and 10 can execute in parallel after Phase 8. Phase 11 requires both to complete.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Infrastructure Prerequisites | v1.0 | 2/2 | Complete | 2026-03-08 |
| 2. Core PBP Ingestion | v1.0 | 1/1 | Complete | 2026-03-08 |
| 3. Advanced Stats & Context Data | v1.0 | 2/2 | Complete | 2026-03-08 |
| 4. Documentation Update | v1.0 | 3/3 | Complete | 2026-03-08 |
| 5. Phase 1 Verification Backfill | v1.0 | 1/1 | Complete | 2026-03-08 |
| 6. Wire Bronze Validation | v1.0 | 1/1 | Complete | 2026-03-08 |
| 7. Tech Debt Cleanup | v1.0 | 1/1 | Complete | 2026-03-08 |
| 8. Pre-Backfill Guards | v1.1 | 1/1 | Complete | 2026-03-09 |
| 9. New Data Type Ingestion | v1.1 | 3/3 | Complete | 2026-03-09 |
| 10. Existing Type Backfill | v1.1 | Complete    | 2026-03-12 | 2026-03-11 |
| 11. Orchestration and Validation | 2/2 | Complete    | 2026-03-12 | - |
| 12. 2025 Player Stats Gap Closure | v1.1 | 0/0 | Not planned | - |

### Phase 12: 2025 Player Stats Gap Closure
**Goal**: Fetch 2025 player weekly and seasonal stats from nflverse's new `stats_player` release tag (replacing archived `player_stats` tag), with column mapping for backward compatibility
**Depends on**: Phase 11
**Requirements**: BACKFILL-02, BACKFILL-03
**Success Criteria** (what must be TRUE):
  1. `data/bronze/players/weekly/season=2025/` contains a Parquet file with schema compatible with 2016-2024 files (53 data columns + metadata)
  2. `data/bronze/players/seasonal/season=2025/` contains a Parquet file derived from weekly aggregation
  3. `validate_data()` passes on both 2025 files
  4. Existing Silver pipeline (`silver_player_transformation.py`) processes 2025 data without error
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd:plan-phase 12 to break down)

---
*Roadmap created: 2026-03-08*
*Last updated: 2026-03-12 after Phase 12 added (2025 player stats gap closure)*
