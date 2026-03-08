# Phase 4: Documentation Update - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Update 4 existing documentation files to reflect the actual data state after Phases 1-3 completed Bronze expansion. No new features — purely aligning docs with reality.

Target files:
1. `docs/NFL_DATA_DICTIONARY.md` — add entries for all 15+ Bronze data types
2. `docs/BRONZE_LAYER_DATA_INVENTORY.md` — reflect actual 40+ files across all data types
3. `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — mark implemented vs planned tables
4. `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` — update with actual phase status

</domain>

<decisions>
## Implementation Decisions

### Data Dictionary (DOC-01)
- **Full specs** for all data types: column name, data type, nullable, description, business rules, example — same depth as existing Games table
- **One entry per sub-type**: NGS Passing, NGS Rushing, NGS Receiving each get their own table entry (same for PFR pass/rush/rec/def). Columns differ significantly between sub-types
- **Include source notes** per table: nfl-data-py function name, season availability range, known quirks/gotchas (e.g., "use import_seasonal_rosters, not import_rosters")
- **S3 paths primary**: Reference `s3://nfl-raw/...` as canonical location. Note local `data/bronze/...` fallback exists for development
- Auto-generate column specs by scanning actual Parquet schemas where possible

### Bronze Inventory (DOC-03)
- **Auto-scan from local data**: Create `scripts/generate_inventory.py` as a standalone reusable utility
- Default scans `data/bronze/` locally; add `--s3` flag to scan `s3://nfl-raw/` when credentials are available
- **Metrics per data type**: file count, total size (MB), season range, column count, last ingestion date
- No row counts (would require reading each Parquet file — too slow for a quick inventory)
- Script outputs markdown table that replaces the inventory doc content

### Prediction Data Model (DOC-02)
- **Inline status badges**: ✅ Implemented, 🚧 In Progress, 📋 Planned — next to each table/section
- **Keep aspirational content** (Platinum Layer, ML pipeline, etc.) but clearly badge as 📋 Planned
- **Cross-reference data dictionary**: Prediction model doc describes tables at high level and links to NFL_DATA_DICTIONARY.md for full column specs. Single source of truth for schemas
- No duplicate column specs between the two docs

### Implementation Guide (DOC-04)
- **Rewrite phases** to match actual work (GSD Phases 1-4 for Bronze expansion) instead of the obsolete 8-week roadmap
- **Include v2 as planned phases**: Show Silver prediction layer (SLV-01 to SLV-03) and ML pipeline (ML-01 to ML-03) from REQUIREMENTS.md as upcoming work
- **Align tech references with actual stack**: Replace Delta Lake, PySpark, Spark references with pandas, pyarrow, Parquet, DuckDB, XGBoost/LightGBM. These are sufficient for NFL data volumes
- Keep implementation guide as a living roadmap, not a historical document

### Claude's Discretion
- Exact ordering of tables within the data dictionary
- Status badge format/styling (emoji vs text markers)
- How much detail to include in the inventory script's --help output
- Implementation guide section structure

</decisions>

<specifics>
## Specific Ideas

- S3 paths should be the canonical storage reference across all docs — local is a development fallback
- The inventory script should be re-runnable after any ingestion to keep docs fresh (not a one-off generation)
- Prediction model doc should serve as both reference and roadmap — readers should see the full vision with clear implementation status

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DATA_TYPE_REGISTRY` in `src/nfl_data_adapter.py`: Contains all data type metadata (bronze_path, sub_types, season ranges) — useful for generating dictionary entries
- `check_pipeline_health.py`: Already scans S3 for file metadata — patterns reusable for inventory script
- `download_latest_parquet()` in `src/utils.py`: Can read actual Parquet files to extract schemas

### Established Patterns
- Parquet schema inspection via `pyarrow.parquet.read_schema()` — lightweight, doesn't load full data
- Existing doc format in `NFL_DATA_DICTIONARY.md` — table-per-type with consistent column spec format
- S3 key pattern: `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`

### Integration Points
- `scripts/generate_inventory.py` (new) will follow existing script patterns (argparse, S3 client setup, local fallback)
- Data dictionary entries should match `DATA_TYPE_REGISTRY` keys for consistency
- `validate_data()` required columns can cross-reference dictionary entries

</code_context>

<deferred>
## Deferred Ideas

- **Migrate to S3-only storage** — remove local data copies, refresh AWS credentials, make S3 the sole source. Current local-first is a workaround for expired credentials; data volumes are small now but will grow with 10+ years per table
- **Evaluate Databricks/MLflow for production** — self-hosted MLflow for experiment tracking when ML pipeline begins. Databricks itself is overkill for NFL data volumes (designed for TB/PB scale)
- **Neo4j integration docs** — Phase 5 deferred; document WR-CB matchup graph model when Neo4j work begins

</deferred>

---

*Phase: 04-documentation-update*
*Context gathered: 2026-03-08*
