# NFL Data Engineering Platform

## What This Is

A comprehensive NFL data engineering platform built on Medallion Architecture (Bronze/Silver/Gold) that powers both fantasy football projections and game outcome predictions. Currently local-first with S3 as optional storage.

## Core Value

A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models.

## Requirements

### Validated

- Bronze layer: 6 data types ingested (schedules, player_weekly, player_seasonal, snap_counts, injuries, rosters) for 2020-2024
- Silver layer: usage metrics, rolling averages, opponent rankings
- Gold layer: weekly + preseason projections (PPR/Half-PPR/Standard)
- Draft tool: snake, auction, mock draft, waiver wire
- Pipeline monitoring: GHA cron + health check
- Backtesting: MAE 4.91, r=0.51 across 3 seasons
- 71 unit tests passing

### Active

- [ ] Update data model and data dictionary to reflect actual nfl-data-py capabilities and game prediction needs
- [ ] Expand Bronze layer with new data types for game prediction (full PBP, NGS, PFR advanced, draft picks, combine, depth charts, QBR, betting lines, officials)
- [ ] Update Bronze Layer Data Inventory doc to reflect current state (31 files, not 2)
- [ ] Extend NFLDataFetcher with new fetch methods
- [ ] Extend bronze_ingestion_simple.py CLI with new data types
- [ ] Ingest new data types for 2020-2025

### Out of Scope

- Neo4j Phase 5 — deferred until prediction model is validated
- ML model training (RF/XGBoost) — depends on complete bronze data first
- Live Sleeper league integration — deferred to draft season
- S3 sync — AWS credentials expired, local-first workflow active

## Context

Existing documentation (do not duplicate — reference and update in place):
- `CLAUDE.md` — project reference, commands, architecture
- `copilot-instructions.md` — AI assistant instructions, data flow, patterns
- `development_tasks.md` — complete task history (16 phases done)
- `docs/NFL_DATA_DICTIONARY.md` — table definitions, 200+ columns
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — ML prediction model design
- `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` — 8-week implementation roadmap
- `docs/BRONZE_LAYER_DATA_INVENTORY.md` — bronze inventory (stale)
- `.planning/codebase/` — GSD codebase map (7 documents)

nfl-data-py provides additional data sources not yet ingested:
- `import_pbp_data` — full PBP (300+ cols with EPA, WPA, CPOE, air yards)
- `import_ngs_data` — Next Gen Stats (time to throw, separation, RYOE)
- `import_seasonal_pfr` / `import_weekly_pfr` — Pro Football Reference advanced stats
- `import_draft_picks` — draft capital and player evaluation
- `import_combine_data` — combine measurables
- `import_depth_charts` — positional depth
- `import_qbr` — ESPN quarterback ratings
- `import_win_totals` / `import_sc_lines` — betting lines
- `import_officials` — referee data

## Constraints

- **Data source**: nfl-data-py is the primary API; some functions have quirks (e.g., `import_rosters` vs `import_seasonal_rosters`)
- **Storage**: Local-first (data/bronze/, data/silver/, data/gold/) with S3 as optional fallback
- **Seasons**: Player data 2020-2025; schedules back to 1999; PBP back to 1999
- **Python**: 3.9 compatible; pandas/pyarrow for all processing

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Local-first storage | AWS credentials expired March 2026 | -- Pending (refresh creds later) |
| nfl-data-py as primary source | Battle-tested, covers 95% of needed data | Good |
| Parquet format | Columnar, compressed, pandas-native | Good |
| Update existing docs in-place | Avoid duplication with 6+ existing doc files | -- Pending |

---
*Last updated: 2026-03-07 after GSD project initialization*
