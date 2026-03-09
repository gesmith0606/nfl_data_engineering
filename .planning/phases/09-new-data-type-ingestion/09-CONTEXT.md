# Phase 9: New Data Type Ingestion - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Ingest all 9 new Bronze data types (teams, draft picks, combine, depth charts, QBR, NGS, PFR weekly, PFR seasonal, PBP) with full historical coverage per type's valid range in DATA_TYPE_SEASON_RANGES. All types are already registered in both DATA_TYPE_REGISTRY and NFLDataAdapter — this phase runs ingestion, handles edge cases, and verifies output.

</domain>

<decisions>
## Implementation Decisions

### Empty data handling
- Warn and skip: log generic warning (`No data returned for {type} season {year}, skipping`), do not save an empty Parquet file
- No known-reason hints — keep warnings generic and maintenance-free
- Exceptions from nfl-data-py (network errors, API failures) treated same as empty data: warn, skip, continue (NFLDataAdapter._safe_call() already returns empty DataFrame)
- Print a summary at end of each data type ingestion showing ingested vs skipped counts (e.g., `8/10 seasons ingested, 2 skipped: empty data`)

### Depth chart 2025 schema
- Ingest as-is — Bronze stores raw data, schema normalization is Silver's job
- Log schema diffs when column sets change between seasons (e.g., `2025 depth_charts: 3 new columns, 1 removed vs 2024`)
- Schema diff logging applies to ALL data types, not just depth charts — any type could have cross-year schema changes

### Season range policy
- Use each type's full valid range from DATA_TYPE_SEASON_RANGES (not just 2016-2025)
- Examples: draft_picks from 2000, teams from 1999, PFR from 2018, NGS from 2016
- Trust the config as source of truth for min/max bounds per type
- Update INGEST requirements (INGEST-01 through INGEST-09) to reflect "full valid range per type" instead of "2016-2025"

### QBR file organization
- Frequency prefix in filename: `weekly_qbr_YYYYMMDD.parquet` and `seasonal_qbr_YYYYMMDD.parquet` (matches v1.0 pattern)
- Both frequencies ingested by default when running `--data-type qbr`; use `--frequency weekly` to filter to one
- "Ingest all variants by default" pattern applies to ALL sub-type data: NGS (passing/rushing/receiving), PFR weekly (pass/rush/rec/def), PFR seasonal (pass/rush/rec/def)
- Explicit `--sub-type` or `--frequency` flag overrides to ingest a single variant

### Claude's Discretion
- Schema diff implementation details (how to compare column sets, where to log)
- Exact summary format for ingestion counts
- Whether to add a `--seasons` range flag for multi-season convenience (e.g., `--seasons 2016-2025`)
- Test structure and fixture design

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DATA_TYPE_REGISTRY` in bronze_ingestion_simple.py: All 9 types already registered with adapter_method, bronze_path, sub_types
- `NFLDataAdapter` in nfl_data_adapter.py: All fetch methods exist (fetch_team_descriptions, fetch_draft_picks, fetch_combine, etc.)
- `_safe_call()` in NFLDataAdapter: Already handles exceptions and returns empty DataFrame
- `_filter_seasons()` in NFLDataAdapter: Already validates season ranges using config
- `validate_season_for_type()` in config.py: Auto-enforces per-type season bounds
- `save_local()` in bronze_ingestion_simple.py: Handles directory creation and Parquet write
- `parse_seasons_range()` in bronze_ingestion_simple.py: Parses "2016-2025" range strings

### Established Patterns
- Registry dispatch: Adding data type behavior is config-only (no code changes)
- Local-first with `--s3` opt-in: All saves go to data/bronze/ by default
- Callable-based max season: All types use get_max_season or static lambda
- Sub-type looping: NGS, PFR already have `sub_types` lists in registry
- QBR frequency prefix: Already decided in v1.0 (STATE.md)
- Warn-never-block validation: validate_data() is informational, never blocks save

### Integration Points
- `bronze_ingestion_simple.py:main()` — CLI entry point, already dispatches via registry
- `bronze_ingestion_simple.py:_build_method_kwargs()` — Builds adapter call kwargs per type
- `nfl_data_adapter.py:NFLDataAdapter` — All fetch methods, season filtering
- `config.py:DATA_TYPE_SEASON_RANGES` — Source of truth for valid ranges

</code_context>

<specifics>
## Specific Ideas

No specific requirements — straightforward ingestion work building on existing v1.0 patterns. The main change is making the CLI smarter about looping through all variants/frequencies by default.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-new-data-type-ingestion*
*Context gathered: 2026-03-09*
