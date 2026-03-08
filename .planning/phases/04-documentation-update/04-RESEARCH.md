# Phase 4: Documentation Update - Research

**Researched:** 2026-03-08
**Domain:** Technical documentation, Parquet schema introspection, Markdown generation
**Confidence:** HIGH

## Summary

Phase 4 is a documentation-only phase with no new features or code changes beyond one utility script (`scripts/generate_inventory.py`). The work involves updating 4 existing Markdown files to reflect the actual state of the NFL data platform after Phases 1-3 expanded Bronze from 2 data types (games, plays) to 15 data types across the `DATA_TYPE_REGISTRY`.

The current documentation is severely outdated: the data dictionary only covers Games and Plays with 3 "planned" entries; the inventory shows 2 files totaling 0.21 MB (actual: 31+ local files, 7 MB); the implementation guide references an obsolete 8-week Delta Lake/PySpark roadmap; and the prediction data model has no implementation status indicators. All 4 docs were last meaningfully updated March 4, 2026 before the Bronze expansion work.

**Primary recommendation:** Use `pyarrow.parquet.read_schema()` on local Parquet files to auto-generate accurate column specs for the data dictionary, and build `scripts/generate_inventory.py` to scan `data/bronze/` for file metrics. For data types without local files (PBP, NGS, PFR, QBR, depth_charts, draft_picks, combine), extract column info from mock DataFrames in `tests/test_advanced_ingestion.py` and `tests/test_pbp_ingestion.py` plus the `DATA_TYPE_REGISTRY` and `NFLDataAdapter` method signatures.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **DOC-01 Data Dictionary**: Full specs for all data types (column name, data type, nullable, description, business rules, example). One entry per sub-type (NGS Passing/Rushing/Receiving separate; PFR pass/rush/rec/def separate). Include source notes per table (nfl-data-py function, season range, quirks). S3 paths primary, local as fallback. Auto-generate column specs from Parquet schemas where possible.
- **DOC-03 Bronze Inventory**: Create `scripts/generate_inventory.py` as standalone reusable utility. Default scans `data/bronze/` locally; `--s3` flag for S3 scan. Metrics: file count, total size (MB), season range, column count, last ingestion date. No row counts. Script outputs markdown table replacing inventory doc content.
- **DOC-02 Prediction Data Model**: Inline status badges (implemented/in-progress/planned). Keep aspirational content but badge clearly. Cross-reference data dictionary for column specs (no duplicate schemas).
- **DOC-04 Implementation Guide**: Rewrite phases to match actual GSD Phases 1-4. Include v2 requirements (SLV-01 to SLV-03, ML-01 to ML-03) as upcoming. Replace Delta Lake/PySpark/Spark references with pandas/pyarrow/Parquet/DuckDB/XGBoost/LightGBM. Living roadmap.

### Claude's Discretion
- Exact ordering of tables within the data dictionary
- Status badge format/styling (emoji vs text markers)
- Inventory script --help detail level
- Implementation guide section structure

### Deferred Ideas (OUT OF SCOPE)
- S3-only storage migration
- Databricks/MLflow evaluation
- Neo4j integration docs
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DOC-01 | NFL Data Dictionary updated with all Bronze data types and actual column names | Schema introspection via pyarrow on 6 local data types; mock DataFrames + adapter signatures for 9 remaining types; DATA_TYPE_REGISTRY for metadata |
| DOC-02 | NFL Game Prediction Data Model marks implemented vs planned tables | Current doc structure identified (1210 lines); Bronze/Silver/Gold sections need status badges; cross-references to data dictionary |
| DOC-03 | Bronze Layer Data Inventory reflects actual 40+ files | Local scan shows 31 files / 7 MB across 6 types (games, weekly, seasonal, snap_counts, injuries, rosters); Phase 2-3 types not locally stored; script must handle both |
| DOC-04 | Data model implementation guide updated with realistic phase status | Current guide has obsolete 8-week PySpark/Delta roadmap (2166 lines); needs complete rewrite to match GSD Phases 1-4 + v2 requirements |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pyarrow | (installed in venv) | Read Parquet schemas without loading data | `pq.read_schema()` is the standard lightweight schema introspection method |
| os/pathlib | stdlib | Walk local filesystem for inventory | Standard library, no dependencies |
| argparse | stdlib | CLI for generate_inventory.py | Matches existing script patterns |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| boto3 | (installed) | S3 scanning for --s3 mode in inventory script | Only when `--s3` flag is passed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pyarrow schema read | pandas read_parquet | pandas loads full data into memory; pyarrow reads only metadata footer |

## Architecture Patterns

### Inventory Script Structure
```
scripts/generate_inventory.py
  ├── scan_local(base_dir)      # Walk data/bronze/, collect file metadata
  ├── scan_s3(bucket, prefix)   # List S3 objects (reuses patterns from check_pipeline_health.py)
  ├── format_markdown(results)  # Output markdown tables
  └── main()                    # argparse CLI
```

### Pattern 1: Parquet Schema Introspection
**What:** Use `pyarrow.parquet.read_schema()` to extract column names, types, and nullability from Parquet files without loading data.
**When to use:** Generating data dictionary entries from actual files.
**Example:**
```python
import pyarrow.parquet as pq

schema = pq.read_schema("data/bronze/games/season=2020/schedules_full_20260306_223734.parquet")
for field in schema:
    print(f"{field.name}: {field.type} (nullable={field.nullable})")
```

### Pattern 2: Registry-Driven Documentation
**What:** Use `DATA_TYPE_REGISTRY` from `scripts/bronze_ingestion_simple.py` as the source of truth for which data types exist, their S3 paths, sub-types, and season requirements.
**When to use:** Ensuring data dictionary and inventory cover all 15 data types.

### Pattern 3: Status Badge Convention
**What:** Emoji-based inline status for the prediction data model doc.
**Example:** `### Games Table ✅ Implemented` vs `### Weather Data 📋 Planned`

### Anti-Patterns to Avoid
- **Duplicating column specs**: The prediction data model should link to the data dictionary for schemas, not repeat them.
- **Hardcoding file counts**: The inventory should be generated by a script, not manually maintained.
- **Mixing actual vs aspirational**: Without clear badges, readers cannot tell what is real vs planned.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parquet schema extraction | Manual column lists | `pyarrow.parquet.read_schema()` | Schemas can change between seasons; auto-extraction stays accurate |
| File inventory | Hand-counted tables | `scripts/generate_inventory.py` with os.walk | Re-runnable, always current |
| Season range info | Hardcoded ranges | `DATA_TYPE_SEASON_RANGES` from `src/config.py` | Single source of truth |

## Common Pitfalls

### Pitfall 1: Schema Variations Across Seasons
**What goes wrong:** Parquet schemas for the same data type may differ slightly between seasons (e.g., `years_exp` is `int32` in 2021 but `double` in 2020 for rosters).
**Why it happens:** nfl-data-py upstream data evolves; pandas type inference varies based on null counts.
**How to avoid:** Document the "canonical" schema from the most recent season. Note type variations as "may vary by season" in the data dictionary.
**Warning signs:** Different column counts or types across season partitions for the same data type.

### Pitfall 2: Missing Local Files for Phase 2-3 Data Types
**What goes wrong:** PBP, NGS, PFR, QBR, depth charts, draft picks, and combine data were added in Phases 2-3 but may not have local Parquet files (only 31 files found locally, all from original 6 types).
**Why it happens:** Phase 2-3 ingestion may have been run to different locations, or tests used mocks only.
**How to avoid:** For data types without local files, extract column info from: (1) `PBP_COLUMNS` in `src/config.py` (103 curated columns for PBP), (2) mock DataFrames in test files, (3) `NFLDataAdapter` method signatures + nfl-data-py documentation.
**Warning signs:** `generate_inventory.py` reporting 0 files for expected data types.

### Pitfall 3: S3 Path Inconsistency Between Code and Docs
**What goes wrong:** Docs reference one S3 path pattern while code uses another (e.g., `games/` vs `schedules/`, `plays/` vs `pbp/`).
**Why it happens:** The old docs used `plays/` but the registry uses `pbp/`; old docs used `games/` but local storage uses `games/` while the registry says `schedules/`.
**How to avoid:** Use `DATA_TYPE_REGISTRY["bronze_path"]` as the authoritative source for S3/local paths. Cross-check with `PLAYER_S3_KEYS` in `src/config.py`.
**Warning signs:** Path patterns in docs not matching what the ingestion script actually writes.

### Pitfall 4: Overly Large Doc Rewrites
**What goes wrong:** The implementation guide is 2166 lines with extensive but obsolete content. A full rewrite risks losing useful reference material.
**Why it happens:** The doc was written as an aspirational guide before implementation; much content is still valuable for future phases.
**How to avoid:** Keep the overall structure but replace the Phase roadmap, update tech stack references, and badge sections. Preserve useful code examples and patterns that are still applicable.

## Code Examples

### Reading Parquet Schema (for data dictionary generation)
```python
# Source: verified on local data 2026-03-08
import pyarrow.parquet as pq

schema = pq.read_schema(parquet_path)
for field in schema:
    col_name = field.name
    col_type = str(field.type)  # e.g., "int32", "string", "double"
    nullable = field.nullable   # bool
```

### Local File Inventory Pattern
```python
# Source: derived from check_pipeline_health.py patterns
import os
from datetime import datetime

def scan_local(base_dir="data/bronze"):
    results = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".parquet"):
                path = os.path.join(root, f)
                stat = os.stat(path)
                rel = os.path.relpath(path, base_dir)
                schema = pq.read_schema(path)
                results.append({
                    "path": rel,
                    "size_mb": stat.st_size / (1024 * 1024),
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                    "columns": len(schema.names),
                })
    return results
```

### DATA_TYPE_REGISTRY Keys (source of truth for all 15 types)
```python
# Source: scripts/bronze_ingestion_simple.py
DATA_TYPE_REGISTRY = {
    "schedules", "pbp", "player_weekly", "player_seasonal",
    "snap_counts", "injuries", "rosters", "teams",
    "ngs",           # sub_types: passing, rushing, receiving
    "pfr_weekly",    # sub_types: pass, rush, rec, def
    "pfr_seasonal",  # sub_types: pass, rush, rec, def
    "qbr",           # frequencies: weekly, seasonal
    "depth_charts", "draft_picks", "combine",
}
# Total: 15 top-level types, expanding to 24+ with sub-types
```

## Existing Doc Assessment

### Current State vs Required State

| Doc | Current Lines | Current Coverage | Required Coverage |
|-----|---------------|------------------|-------------------|
| NFL_DATA_DICTIONARY.md | 863 | Games + Plays (Bronze), 3 planned Bronze, Silver, Gold specs | All 15+ Bronze types with actual schemas |
| BRONZE_LAYER_DATA_INVENTORY.md | 158 | 2 files, 0.21 MB, 2023 W1 only | 31+ local files, 7 MB, all data types/seasons |
| NFL_GAME_PREDICTION_DATA_MODEL.md | 1210 | Full conceptual model, no status indicators | Same content + status badges on every section |
| NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md | 2166 | Obsolete 8-week Delta/PySpark roadmap | Actual GSD phase history + v2 roadmap |

### Data Types Needing Dictionary Entries

| Data Type | Local Files? | Schema Source | Columns | Seasons |
|-----------|-------------|---------------|---------|---------|
| schedules (games) | YES (6 files) | Parquet schema | 50 | 2020-2025 |
| player_weekly | YES (5 files) | Parquet schema | 55 | 2020-2024 |
| player_seasonal | YES (5 files) | Parquet schema | 60 | 2020-2024 |
| snap_counts | YES (5 files) | Parquet schema | 18 | 2020-2024 |
| injuries | YES (5 files) | Parquet schema | 18 | 2020-2024 |
| rosters | YES (5 files) | Parquet schema | 39 | 2020-2024 |
| pbp | NO local | PBP_COLUMNS (103 cols) in config.py | 103 | 2010-2025 |
| ngs_passing | NO local | test mocks + nfl-data-py docs | ~20 | 2016-2025 |
| ngs_rushing | NO local | test mocks + nfl-data-py docs | ~15 | 2016-2025 |
| ngs_receiving | NO local | test mocks + nfl-data-py docs | ~20 | 2016-2025 |
| pfr_weekly (4 sub-types) | NO local | test mocks | ~10 per sub-type | 2018-2025 |
| pfr_seasonal (4 sub-types) | NO local | test mocks | ~10 per sub-type | 2018-2025 |
| qbr | NO local | test mocks | ~10 | 2006-2025 |
| depth_charts | NO local | test mocks | ~10 | 2001-2025 |
| draft_picks | NO local | nfl-data-py docs | ~20 | 2000-2025 |
| combine | NO local | nfl-data-py docs | ~15 | 2000-2025 |
| teams | NO local | adapter method (no season) | ~30 | N/A |

### Key Code References for Documentation

| Code File | What It Provides |
|-----------|-----------------|
| `scripts/bronze_ingestion_simple.py` → `DATA_TYPE_REGISTRY` | All 15 data types, S3 paths, sub-types |
| `src/config.py` → `DATA_TYPE_SEASON_RANGES` | Valid season ranges per type |
| `src/config.py` → `PBP_COLUMNS` | 103 curated PBP columns |
| `src/config.py` → `PLAYER_S3_KEYS` | S3 key templates for player types |
| `src/nfl_data_adapter.py` | Adapter methods (nfl-data-py function mapping) |
| `src/nfl_data_integration.py` → `validate_data()` | Required columns per type |
| `tests/test_advanced_ingestion.py` | Mock schemas for NGS, PFR, QBR, depth charts |
| `tests/test_pbp_ingestion.py` | Mock schemas for PBP |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Delta Lake + PySpark | pandas + pyarrow + Parquet | Phase 1 (Mar 2026) | Implementation guide references obsolete tech |
| 2 Bronze data types | 15 data types via registry | Phases 1-3 (Mar 2026) | Data dictionary covers <15% of actual types |
| Manual file tracking | Need `generate_inventory.py` | Phase 4 (this phase) | Inventory will be auto-generated |
| No status badges on docs | Status badges required | Phase 4 (this phase) | Prediction model doc gets implementation tracking |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed in venv) |
| Config file | none (uses pytest defaults) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOC-01 | Data dictionary has entries for all 15+ data types | manual-only | N/A -- documentation content review | N/A |
| DOC-02 | Prediction model doc has status badges | manual-only | N/A -- documentation content review | N/A |
| DOC-03 | Inventory script runs and generates correct output | unit | `python -m pytest tests/test_generate_inventory.py -x` | Wave 0 |
| DOC-04 | Implementation guide references correct tech stack | manual-only | N/A -- documentation content review | N/A |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q` (ensure no regressions)
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green + manual doc review

### Wave 0 Gaps
- [ ] `tests/test_generate_inventory.py` -- covers DOC-03 (inventory script generates correct markdown output)
- [ ] Verify `python scripts/generate_inventory.py` runs without error on local data

## Open Questions

1. **Column specs for non-local data types**
   - What we know: PBP has 103 columns defined in `PBP_COLUMNS`. Test mocks show 6-10 required columns per NGS/PFR/QBR type. Actual column counts are likely 15-60 per type.
   - What's unclear: Full column lists for NGS, PFR, QBR, depth charts, draft picks, combine beyond the required/mock columns.
   - Recommendation: Document the columns we can verify (from config + tests + adapter). For types without local files, note "representative columns shown; full schema available via `nfl-data-py` API" and include the nfl-data-py function name for reference. This is honest and sufficient -- the data dictionary can be enriched later by running a one-time ingestion.

2. **Inventory file count discrepancy**
   - What we know: CONTEXT.md says "40+ files" but local scan shows 31 files. Phase 2-3 data (PBP, NGS, PFR, QBR, depth charts, draft picks, combine) was ingested via adapter but may not have been saved locally.
   - What's unclear: Whether Phase 2-3 ingestion saved files to a different location or only ran in test mode.
   - Recommendation: `generate_inventory.py` should report what actually exists. If 31 files, report 31. The doc can note "additional data types available via `bronze_ingestion_simple.py` but not yet ingested locally."

## Sources

### Primary (HIGH confidence)
- Local Parquet file schemas via `pyarrow.parquet.read_schema()` -- inspected 31 files
- `scripts/bronze_ingestion_simple.py` `DATA_TYPE_REGISTRY` -- 15 data types
- `src/config.py` `DATA_TYPE_SEASON_RANGES` -- season availability per type
- `src/config.py` `PBP_COLUMNS` -- 103 curated columns
- `src/nfl_data_adapter.py` -- all adapter fetch methods
- `tests/test_advanced_ingestion.py` -- mock schemas for Phase 3 types
- Existing docs: 4 target files read and analyzed

### Secondary (MEDIUM confidence)
- nfl-data-py function names mapped from adapter (column counts inferred from similar projects)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- pure Python stdlib + pyarrow already in project
- Architecture: HIGH -- follows existing script patterns (check_pipeline_health.py, bronze_ingestion_simple.py)
- Pitfalls: HIGH -- verified by inspecting actual local data vs docs; found real discrepancies

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (documentation phase; stable domain)
