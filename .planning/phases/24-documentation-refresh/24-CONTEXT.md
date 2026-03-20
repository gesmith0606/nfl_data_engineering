# Phase 24: Documentation Refresh - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Update all project documentation to accurately reflect the current platform state after four milestones (v1.0-v1.3). Covers data dictionary (Bronze/Silver/Gold), Bronze inventory, implementation guide, and CLAUDE.md. No code changes — documentation only.

</domain>

<decisions>
## Implementation Decisions

### Silver Schema Documentation
- **D-01:** Auto-generate Silver schemas from local parquet files (DuckDB/pandas to extract column names, types, sample values), then add brief hand-written descriptions per column
- **D-02:** Add Silver schemas to the existing NFL_DATA_DICTIONARY.md after the Bronze section — one source of truth for all layer schemas
- **D-03:** Replace the existing planned "Games (Silver)" schema section with real auto-generated schemas from actual parquet files — remove planned/aspirational content

### Gold Prediction Schema
- **D-04:** Document planned prediction output columns based on REQUIREMENTS.md (spread prediction, total prediction, edge, confidence tier) — mark as "Planned" with version badges
- **D-05:** Also document the existing fantasy projection output schema (weekly/preseason projections) — complete Gold layer reference covering both existing and planned outputs

### Bronze Inventory Refresh
- **D-06:** Write or update a script that scans data/bronze/ and auto-generates the inventory table from parquet metadata (file counts, sizes, column counts) — ensures PBP shows 140 columns and officials data type is included

### CLAUDE.md Scope
- **D-07:** Full refresh — update test count to 360, add all 11 Silver paths to architecture diagram, add prediction feature vector, refresh status section with v1.3 completion
- **D-08:** Add new v1.2/v1.3 modules to key files table (team_analytics.py, game_context.py, prediction_features.py, and any other new src files)

### Implementation Guide
- **D-09:** Full update — add phases 20-23 as completed with dates, add v1.4 phases 24-27 as planned with status badges

### Claude's Discretion
- Column description wording and formatting for auto-generated Silver schemas
- Exact layout of Gold "Planned" schema badges
- How to handle the prediction data model doc (NFL_GAME_PREDICTION_DATA_MODEL.md) — update if stale, or leave as-is if still accurate

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Documentation files to update
- `docs/NFL_DATA_DICTIONARY.md` — Current data dictionary (1273 lines); Silver section needs expansion from 2 to 12 tables; Gold section needs both existing and planned schemas
- `docs/BRONZE_LAYER_DATA_INVENTORY.md` — Current inventory (33 lines); needs regeneration showing PBP at 140 cols + officials
- `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` — Implementation guide (627 lines); needs v1.3 phases and v1.4 planned phases
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — Prediction model design doc; review for accuracy
- `CLAUDE.md` — Project reference file; needs full refresh (tests, architecture, key files, status)

### Source files for schema extraction
- `data/silver/` — All Silver parquet files organized by path (12 output directories)
- `data/gold/` — Existing fantasy projection parquet files
- `data/bronze/` — All Bronze parquet files for inventory regeneration
- `src/config.py` — S3 paths, scoring configs, data type registries
- `src/team_analytics.py` — v1.2 team metrics module
- `src/game_context.py` — v1.3 game context module
- `src/prediction_features.py` — v1.3 prediction feature assembly

### Requirements
- `.planning/REQUIREMENTS.md` — DOCS-01 through DOCS-05 define success criteria
- `.planning/ROADMAP.md` — Phase 24 success criteria (5 items)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/generate_bronze_inventory.py` or similar — check if an inventory generation script already exists; if so, extend it
- DuckDB MCP tool — can query parquet files directly for schema introspection
- `src/utils.py:download_latest_parquet()` — read convention for getting latest file per prefix

### Established Patterns
- Bronze inventory was previously auto-generated (header says "Generated: 2026-03-11 20:50")
- Data dictionary uses markdown tables with Column Name | Data Type | Nullable | Description | Example format
- Implementation guide uses phase sections with Milestone/Completed/badge format

### Integration Points
- CLAUDE.md is loaded into every Claude Code session — keep it concise but accurate
- Data dictionary is referenced by downstream planning agents — schemas must match actual parquet files
- Bronze inventory is a standalone quick-reference — self-contained table

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. User consistently chose recommended defaults throughout discussion.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 24-documentation-refresh*
*Context gathered: 2026-03-20*
