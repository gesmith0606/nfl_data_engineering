# NFL Data Engineering Platform

## What This Is

A comprehensive NFL data engineering platform built on Medallion Architecture (Bronze/Silver/Gold) that powers both fantasy football projections and game outcome predictions. Features 15+ Bronze data types (PBP, NGS, PFR, QBR, depth charts, combine, draft picks), registry-driven ingestion, and local-first storage.

## Core Value

A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models.

## Requirements

### Validated

- ✓ Infrastructure: local-first storage, dynamic season validation, adapter pattern, registry CLI — v1.0
- ✓ PBP: 103 curated columns (EPA/WPA/CPOE/air yards) for 2010-2025, memory-safe batching — v1.0
- ✓ Advanced stats: NGS, PFR weekly/seasonal, QBR, depth charts, draft picks, combine — v1.0
- ✓ Documentation: data dictionary, Bronze inventory, prediction model badges, implementation guide — v1.0
- ✓ Validation: validate_data() for all data types, wired into ingestion pipeline — v1.0
- ✓ Bronze layer: 6 original types (schedules, player_weekly, player_seasonal, snap_counts, injuries, rosters) — pre-v1.0
- ✓ Silver layer: usage metrics, rolling averages, opponent rankings — pre-v1.0
- ✓ Gold layer: weekly + preseason projections (PPR/Half-PPR/Standard) — pre-v1.0
- ✓ Draft tool: snake, auction, mock draft, waiver wire — pre-v1.0
- ✓ Pipeline monitoring: GHA cron + health check — pre-v1.0
- ✓ Backtesting: MAE 4.91, r=0.51 across 3 seasons — pre-v1.0
- ✓ 141 total tests passing (71 original + 70 milestone) — v1.0

### Active

(Fresh for next milestone — define with `/gsd:new-milestone`)

### Out of Scope

- Neo4j Phase 5 — deferred until prediction model is validated
- S3 sync — AWS credentials expired, local-first workflow active
- Live Sleeper league integration — deferred to draft season

## Context

Shipped v1.0 with 10,095 LOC Python across 7 phases and 11 plans.
Tech stack: Python 3.9, pandas, pyarrow, nfl-data-py, local Parquet storage (S3 optional).
Bronze layer now has 15+ data types covering schedules, player stats, PBP, NGS, PFR, QBR, depth charts, combine, draft picks.
Silver/Gold layers serve fantasy football projections; game prediction ML is the next frontier.

Existing documentation (reference in place):
- `CLAUDE.md` — project reference, commands, architecture
- `docs/NFL_DATA_DICTIONARY.md` — table definitions for all 15+ Bronze types
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — ML prediction model design
- `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` — implementation roadmap
- `docs/BRONZE_LAYER_DATA_INVENTORY.md` — bronze inventory (auto-generated)

## Constraints

- **Data source**: nfl-data-py is the primary API; some functions have quirks (e.g., `import_rosters` vs `import_seasonal_rosters`)
- **Storage**: Local-first (data/bronze/, data/silver/, data/gold/) with S3 as optional fallback
- **Seasons**: Player data 2020-2025; schedules back to 1999; PBP back to 1999
- **Python**: 3.9 compatible; pandas/pyarrow for all processing

## Key Decisions

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

---
*Last updated: 2026-03-08 after v1.0 milestone*
