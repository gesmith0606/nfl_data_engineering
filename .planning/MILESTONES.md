# Milestones

## v1.2 Silver Expansion (Shipped: 2026-03-15)

**Phases completed:** 5 phases, 10 plans, 25 requirements
**Commits:** 60 | **LOC:** 16,821 Python | **Tests:** 289 passing (103 new)

**Key accomplishments:**
- PBP-derived team performance metrics (EPA, success rate, CPOE, red zone efficiency) and tendencies (pace, PROE, 4th-down aggressiveness) with 3/6-game rolling windows
- Opponent-adjusted EPA with lagged schedule difficulty rankings (1-32) and situational splits (home/away, divisional, game script) with rolling windows
- Advanced player profiles from NGS/PFR/QBR data (separation, RYOE, TTT, pressure, blitz, QBR) with three-tier join strategy across 47K+ player-weeks
- Historical dimension table with combine measurables (speed score, burst, catch radius) and Jimmy Johnson draft chart values for 9,892 players
- Pipeline health monitoring for all 7 Silver paths, config-driven S3 keys, and tech debt cleanup closing all audit gaps

---

## v1.1 Bronze Backfill (Shipped: 2026-03-13)

**Phases completed:** 7 phases, 12 plans, 0 tasks

**Commits:** 50+ | **LOC:** 12,084 Python | **Tests:** 186 passing

**Key accomplishments:**
- Ingested 9 new Bronze data types (PBP, NGS, PFR, QBR, depth charts, draft picks, combine, teams) with full historical coverage
- Backfilled 6 existing types from 2020-2024 to 2016-2025 range (517 files, 93 MB total)
- Built batch ingestion CLI with progress reporting, failure handling, and skip-existing deduplication
- Implemented stats_player adapter for 2025 data via nflverse's new release tag with column mapping
- Fixed Bronze-Silver path alignment for snap_counts and schedules, ensuring end-to-end pipeline
- Complete Bronze inventory: 15 data types, 10 years of history, all passing validate_data()

---

## v1.0 Bronze Expansion (Shipped: 2026-03-08)

**Phases completed:** 7 phases, 11 plans, 0 tasks

**Commits:** 81 | **LOC:** 10,095 Python | **Tests:** 70 milestone-specific

**Key accomplishments:**
- Registry-driven Bronze CLI with 15+ data types via config-only dispatch, local-first storage
- Full PBP ingestion — 103 curated columns (EPA/WPA/CPOE/air yards) for 2010-2025
- Advanced stats expansion — NGS, PFR weekly/seasonal, QBR, depth charts, draft picks, combine
- Complete documentation — data dictionary, inventory script, prediction model badges, implementation guide
- Bronze validation pipeline — validate_data() wired into ingestion with warn-never-block pattern
- 70 milestone-specific tests across infrastructure, PBP, advanced stats, inventory, and validation

---

