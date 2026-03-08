# Phase 3: Advanced Stats & Context Data - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Ingest all remaining Bronze data types — NGS (3 stat types), PFR weekly + seasonal (4 sub-types each), QBR (weekly + seasonal), depth charts, draft picks, and combine data. Add validate_data() rules and tests for each new type.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation decisions delegated to Claude. User trusts best judgment on:

**Season ranges:** Use requirements as-is (NGS: 2016-2025, PFR: 2018-2025, QBR: 2006-2025, depth charts: 2020-2025, draft picks: 2000-2025, combine: 2000-2025). Config already has correct min years. No need to go deeper than specified — these ranges match data availability and ML training needs.

**QBR frequency:** Ingest both weekly and seasonal. Store as separate ingestion runs (same bronze path `qbr/season=YYYY/` but distinguish via filename: `qbr_weekly_{ts}.parquet` and `qbr_seasonal_{ts}.parquet`). Adapter already supports `frequency` param.

**Validation strictness:** Practical approach — required column checks (must-have columns per type) + non-empty DataFrame check + season column presence. No row count thresholds or null % checks at Bronze level (that's Silver's job). Keep it simple and extensible.

**Ingestion order & batching:** No special ordering — all types are independent. Use existing `--seasons` batch flag per type. A convenience wrapper script or `--data-type all` flag is nice-to-have but not required. Sequential runs are fine — total data is small (~50MB across all types).

**Storage conventions:** Same as Phase 2 — per-season files, timestamped, snappy compression. Sub-type data types (NGS, PFR) already have correct bronze_path patterns with `{sub_type}` in registry.

**Test coverage:** 1 test per data type minimum (VAL-03). Mock nfl-data-py calls to avoid API dependency. Test that adapter methods exist, accept correct params, and return DataFrames. Test that validate_data() catches missing required columns.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `NFLDataAdapter`: All 7 fetch methods already implemented (fetch_ngs, fetch_pfr_weekly, fetch_pfr_seasonal, fetch_qbr, fetch_depth_charts, fetch_draft_picks, fetch_combine)
- `DATA_TYPE_REGISTRY`: All 7 entries exist with correct bronze_path, sub_types, and requires_week/season flags
- `_build_method_kwargs()`: Already handles sub-type dispatch (stat_type for NGS, s_type for PFR) and QBR frequency
- `parse_seasons_range()` + `--seasons` flag: Batch ingestion ready from Phase 2
- `save_local()` / `upload_to_s3()`: Generic save utilities
- `validate_season_for_type()`: Season validation per type already configured

### Established Patterns
- Registry dispatch: all new types already registered — CLI dispatches without code changes
- Adapter `_safe_call()` + `_filter_seasons()`: Error handling and season validation built in
- PBP test pattern: `tests/test_pbp_ingestion.py` provides template for mocking adapter calls

### Integration Points
- `NFLDataFetcher.validate_data()` in `nfl_data_integration.py`: Needs new entries in required_columns dict for each type
- Tests: New test file(s) following `test_pbp_ingestion.py` mock pattern
- No new CLI code needed — registry already handles dispatch

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Follow existing patterns from Phase 1-2.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-advanced-stats-context-data*
*Context gathered: 2026-03-08*
