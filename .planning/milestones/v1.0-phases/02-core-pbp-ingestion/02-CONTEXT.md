# Phase 2: Core PBP Ingestion - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Ingest full play-by-play data with EPA, WPA, CPOE, and air yards into the Bronze layer. This is the foundation dataset for game prediction models. Column curation (~80 from 390), memory-safe single-season processing, and storage for 2010-2025.

</domain>

<decisions>
## Implementation Decisions

### Season depth
- Ingest 2010-2025 (16 seasons) — captures modern NFL era post-rule-changes
- All seasons ingested in one pass (loop one season at a time for memory safety)
- Update REQUIREMENTS.md PBP-04 from "2020-2025" to "2010-2025"

### Storage partitioning
- One file per season: `data/bronze/pbp/season=YYYY/pbp_{timestamp}.parquet`
- Week column preserved inside each file for downstream DuckDB/pandas filtering
- Timestamped files — consistent with existing Bronze convention (`download_latest_parquet()` resolves latest)

### Compression
- Aggressive compression: Parquet snappy (default) + downcast all numeric columns
- Goal: minimize ~4GB raw footprint for 16 seasons of PBP data

### Claude's Discretion
- Column curation: select ~80 columns from 390 covering EPA, WPA, CPOE, air yards, success rate, game context, player IDs, play type. Research phase should benchmark actual column availability.
- Memory strategy: use adapter's existing `columns` param for fetch-time subsetting + `downcast=True`. Add chunking only if needed.
- Processing: no transformations in Bronze — raw curated columns only.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `NFLDataAdapter.fetch_pbp(seasons, columns, downcast)`: Already supports column subsetting and numeric downcasting
- `DATA_TYPE_REGISTRY["pbp"]`: Entry exists with `bronze_path: "pbp/season={season}"`, `requires_week: False`
- `_build_method_kwargs()`: Dispatches to `fetch_pbp` — currently passes `seasons=[args.season]` only
- `save_local()` + `upload_to_s3()`: Generic Parquet save/upload utilities

### Established Patterns
- Registry dispatch: adding PBP behavior requires only registry entry changes (Phase 1)
- Adapter `_safe_call()`: wraps all nfl-data-py calls with error handling
- `validate_season_for_type("pbp", season)`: already configured for 1999+

### Integration Points
- `bronze_ingestion_simple.py`: CLI already dispatches `--data-type pbp` through registry
- Need to wire `columns` and `downcast` kwargs through `_build_method_kwargs()`
- Multi-season loop: CLI currently takes single `--season`; need batch mode or wrapper script
- `NFLDataFetcher.validate_data()` has PBP validation stub (`['game_id', 'play_id', 'season', 'week']`)

</code_context>

<specifics>
## Specific Ideas

- Compress aggressively — disk space matters for local-first workflow with 16 seasons of PBP
- Keep week column inside per-season files so DuckDB can filter without needing per-week partitioning

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-core-pbp-ingestion*
*Context gathered: 2026-03-08*
