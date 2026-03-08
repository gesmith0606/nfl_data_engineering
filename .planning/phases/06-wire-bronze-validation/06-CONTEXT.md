# Phase 6: Wire Bronze Validation - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Connect `validate_data()` to the bronze ingestion pipeline so ingested data is schema-checked after fetch, before save. Validation warns but never blocks. Closes the integration gap and E2E flow gap identified by the v1.0 milestone audit.

</domain>

<decisions>
## Implementation Decisions

### Validator location
- Add `validate_data()` method to `NFLDataAdapter` that delegates to `NFLDataFetcher.validate_data()`
- Adapter instantiates NFLDataFetcher internally (lazy import) — no DI, no validator parameter
- Ingestion script calls `adapter.validate_data(df, data_type)` — single import, single object

### Validation output
- Summary line after fetch: `✓ Validation passed: N/N columns valid`
- On issues: `⚠ Validation: 2 missing columns (air_yards, snap_pct)` — list specific column names
- Fits existing print-based output style in bronze_ingestion_simple.py

### CLI control
- No new CLI flags — validation always runs
- Failure = warning only, never blocks save (Bronze layer accepts raw data)

### Missing rules
- When validate_data() has no rules for a data type, skip silently — no output
- Types get validated as rules are added over time

### Claude's Discretion
- Exact validate_data() return value parsing (dict structure may vary)
- How to format the summary line when validation returns partial results
- Integration test structure and assertions

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `NFLDataFetcher.validate_data(df, data_type)` in `src/nfl_data_integration.py:303` — already has rules for all data types
- `NFLDataAdapter` in `src/nfl_data_adapter.py` — ingestion script's single interface to data fetching

### Established Patterns
- Registry/dispatch in `DATA_TYPE_REGISTRY` — ingestion loops through seasons, calls adapter method, saves locally
- Print-based output: `Records: N  Columns: M` style, indented with two spaces
- Lazy imports used in adapter (e.g., `from src.nfl_data_integration import NFLDataFetcher`)

### Integration Points
- `bronze_ingestion_simple.py:334` — after `df = method(**kwargs)`, before `save_local(df, local_path)`
- `nfl_data_adapter.py` — new `validate_data()` method added to class
- `docs/BRONZE_LAYER_DATA_INVENTORY.md:66` — claims validate_data() is used during ingestion (currently aspirational, needs to become accurate)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — standard implementation following existing patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-wire-bronze-validation*
*Context gathered: 2026-03-08*
