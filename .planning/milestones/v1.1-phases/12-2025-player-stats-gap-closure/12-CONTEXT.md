# Phase 12: 2025 Player Stats Gap Closure - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Fetch 2025 player weekly and seasonal stats from nflverse's new `stats_player` release tag (replacing the archived `player_stats` tag), with column mapping for backward compatibility. Produces Bronze Parquet files compatible with 2016-2024 schema. Verifies Silver pipeline processes 2025 data successfully.

</domain>

<decisions>
## Implementation Decisions

### Data source strategy
- Bypass nfl-data-py for 2025+ player stats — download directly from nflverse/nflverse-data GitHub releases using the `stats_player` tag URL
- New adapter method in NFLDataAdapter (e.g., `_fetch_stats_player()`) handles the direct GitHub download
- Only used for seasons >= STATS_PLAYER_MIN_SEASON (2025) — existing `import_weekly_data` continues to work for 2016-2024
- GITHUB_TOKEN: use if available for 5000/hr rate limit, fall back to unauthenticated (60/hr) with warning — consistent with Phase 8 no-hard-blocking pattern

### Column mapping approach
- Map columns at Bronze ingestion so saved Parquet matches 2016-2024 schema exactly
- Discover mapping by reading a 2024 Bronze file to get exact column list, then comparing against downloaded 2025 data
- STATS_PLAYER_COLUMN_MAP constant defined in config.py (follows config-as-source-of-truth pattern from Phase 9)
- Extra columns in the new schema: keep alongside mapped columns (more data available, slightly wider schema than 2016-2024 but all 53 original columns present)
- Log schema diff showing mapped vs new columns

### Seasonal data derivation
- Aggregate from weekly data only — do not attempt to fetch seasonal directly from the new tag
- Aggregation logic lives in NFLDataAdapter (e.g., `_aggregate_seasonal_from_weekly()`)
- Match existing 2024 seasonal file schema exactly — read 2024 seasonal Bronze file as reference for which columns to produce and how to aggregate (sum counting stats, recalculate rate stats as needed)

### Pipeline integration
- Season-conditional routing inside existing `fetch_weekly_data()` — if season >= STATS_PLAYER_MIN_SEASON, call new internal method; otherwise use existing `import_weekly_data`
- Same conditional routing in `fetch_seasonal_data()` — route to aggregation method for 2025+
- Registry entries unchanged — `--data-type player_weekly --season 2025` just works transparently
- STATS_PLAYER_MIN_SEASON = 2025 constant in config.py (easy to update if nflverse backfills)
- Verify PLAYER_DATA_SEASONS already covers 2025, add comment noting 2025 uses stats_player tag
- Run full Silver processing + validation on 2025 data (not just verify it runs — check output quality)

### Claude's Discretion
- Exact GitHub release URL construction and HTTP download implementation
- Schema diff logging format
- Aggregation logic details (which columns to sum vs average vs recalculate)
- Test structure and fixture design
- Error handling for network failures during GitHub download

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `NFLDataAdapter` in nfl_data_adapter.py: `fetch_weekly_data()` and `fetch_seasonal_data()` — add conditional routing here
- `_safe_call()` in NFLDataAdapter: Exception handling with empty DataFrame fallback
- `_filter_seasons()` in NFLDataAdapter: Season range validation using config
- `validate_data()` in nfl_data_integration.py: Bronze validation with common column checks
- `save_local()` in bronze_ingestion_simple.py: Directory creation and Parquet write
- `DATA_TYPE_REGISTRY` in bronze_ingestion_simple.py: player_weekly and player_seasonal entries already exist
- `silver_player_transformation.py`: Silver pipeline that must process 2025 without error

### Established Patterns
- Registry dispatch: CLI routes to adapter method via config — no code changes needed in CLI
- Local-first with `--s3` opt-in: All saves go to data/bronze/ by default
- Callable-based max season: All types use `get_max_season` or static lambda
- Schema diff logging: Already done for depth charts in Phase 9 — reuse pattern
- Warn-never-block validation: validate_data() is informational, never blocks save
- GITHUB_TOKEN: Already set up in .env via Phase 8

### Integration Points
- `nfl_data_adapter.py:fetch_weekly_data()` — add season >= 2025 conditional
- `nfl_data_adapter.py:fetch_seasonal_data()` — add season >= 2025 conditional with aggregation
- `config.py` — add STATS_PLAYER_MIN_SEASON and STATS_PLAYER_COLUMN_MAP constants
- `data/bronze/players/weekly/season=2024/` — reference schema source for column mapping
- `data/bronze/players/seasonal/season=2024/` — reference schema source for seasonal aggregation
- `silver_player_transformation.py` — verify 2025 processing end-to-end

</code_context>

<specifics>
## Specific Ideas

No specific requirements — straightforward gap closure using direct GitHub release downloads with column mapping for backward compatibility.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 12-2025-player-stats-gap-closure*
*Context gathered: 2026-03-12*
