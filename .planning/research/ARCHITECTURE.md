# Architecture Patterns

**Domain:** Bronze backfill of 9 new data types across 10 years (2016-2025) into existing NFL data engineering platform
**Researched:** 2026-03-08

## Recommended Architecture

**No new architecture needed.** The existing registry-dispatch pattern in `bronze_ingestion_simple.py` + `NFLDataAdapter` already supports all 9 data types. The v1.0 milestone built the adapter methods, registry entries, validation rules, and storage paths. The backfill is purely an execution problem -- running ingestion commands across season ranges.

### What Already Exists (No Changes Required)

| Component | Location | Status |
|-----------|----------|--------|
| `NFLDataAdapter` fetch methods | `src/nfl_data_adapter.py` | All 15 methods implemented |
| `DATA_TYPE_REGISTRY` entries | `scripts/bronze_ingestion_simple.py` | All 15 types registered |
| `DATA_TYPE_SEASON_RANGES` | `src/config.py` | All 15 ranges defined |
| `validate_data()` required columns | `src/nfl_data_integration.py` | All 15 schemas defined |
| `PBP_COLUMNS` (103 curated) | `src/config.py` | Defined, used by `_build_method_kwargs` |
| `--seasons` batch mode | `scripts/bronze_ingestion_simple.py` | `parse_seasons_range()` with per-season loop |
| Sub-type dispatch (NGS, PFR) | `scripts/bronze_ingestion_simple.py` | `--sub-type` arg wired |
| QBR frequency dispatch | `scripts/bronze_ingestion_simple.py` | `--frequency` arg wired |

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `bronze_ingestion_simple.py` | CLI entry point, registry dispatch, local save | NFLDataAdapter, config.py |
| `NFLDataAdapter` | Wraps nfl-data-py, season validation, error handling | nfl-data-py (external) |
| `NFLDataFetcher.validate_data()` | Schema validation (required columns, nulls) | Called by adapter |
| `config.py` | Season ranges, PBP columns, S3 paths | Referenced by all |
| `data/bronze/` | Local Parquet storage | Written by ingestion script |

### Data Flow (Existing -- Unchanged)

```
CLI args (--data-type, --season/--seasons, --sub-type, --frequency)
    |
    v
DATA_TYPE_REGISTRY lookup --> adapter_method name, bronze_path template
    |
    v
NFLDataAdapter.fetch_*() --> nfl-data-py API call --> pd.DataFrame
    |
    v
NFLDataAdapter.validate_data() --> warn-never-block (issues logged, not raised)
    |
    v
save_local() --> data/bronze/{bronze_path}/filename_{timestamp}.parquet
```

## Storage Path Patterns for All 9 New Types

These are already defined in `DATA_TYPE_REGISTRY["bronze_path"]`:

| Data Type | Local Path | Partition Strategy | Estimated Size/Season |
|-----------|-----------|-------------------|----------------------|
| **pbp** | `data/bronze/pbp/season={YYYY}/` | **Per-season** (not weekly) | ~80-120 MB (103 cols, ~50K plays) |
| **ngs** | `data/bronze/ngs/{sub_type}/season={YYYY}/` | Per-season, 3 sub_types | ~2-5 MB each |
| **pfr_weekly** | `data/bronze/pfr/weekly/{sub_type}/season={YYYY}/` | Per-season, 4 sub_types | ~1-3 MB each |
| **pfr_seasonal** | `data/bronze/pfr/seasonal/{sub_type}/season={YYYY}/` | Per-season, 4 sub_types | ~0.5-1 MB each |
| **qbr** | `data/bronze/qbr/season={YYYY}/` | Per-season, freq-prefixed filename | ~0.1-0.3 MB |
| **depth_charts** | `data/bronze/depth_charts/season={YYYY}/` | Per-season | ~2-4 MB |
| **draft_picks** | `data/bronze/draft_picks/season={YYYY}/` | Per-season | ~0.05 MB |
| **combine** | `data/bronze/combine/season={YYYY}/` | Per-season | ~0.05 MB |
| **teams** | `data/bronze/teams/` | **No season partition** (static) | ~0.01 MB |

### PBP Size Concern and Mitigation

PBP is the only data type with significant size. At ~100 MB per season with 103 columns:

- **10 seasons = ~1 GB total** -- manageable for local storage
- **Memory during ingestion:** The `--seasons` batch mode already loops one season at a time (`for idx, season in enumerate(season_list, 1):`), so peak memory is one season (~100 MB DataFrame), not 10
- **No weekly partitioning needed:** PBP is fetched per-season from nfl-data-py (the API returns a full season). Splitting into weekly files during Bronze ingestion would add complexity for no benefit -- Silver/Gold layers can filter by week when reading
- **Downcast enabled:** `_build_method_kwargs` passes `downcast=True` for PBP, reducing float64 to float32 where safe (~30% memory reduction)

### QBR Filename Convention

QBR uses frequency-prefixed filenames to avoid weekly/seasonal collision in the same directory:
- `data/bronze/qbr/season=2024/qbr_weekly_20260308_120000.parquet`
- `data/bronze/qbr/season=2024/qbr_seasonal_20260308_120000.parquet`

This is already handled in `bronze_ingestion_simple.py` lines 358-359.

## Validation Rules Already Implemented

From `NFLDataFetcher.validate_data()` in `src/nfl_data_integration.py`:

| Data Type | Required Columns | Additional Rules |
|-----------|-----------------|------------------|
| pbp | `game_id`, `play_id`, `season`, `week` | None beyond null checks |
| ngs | `season`, `season_type`, `week`, `player_display_name`, `player_position`, `team_abbr`, `player_gsis_id` | None |
| pfr_weekly | `game_id`, `season`, `week`, `team`, `pfr_player_name`, `pfr_player_id` | None |
| pfr_seasonal | `player`, `team`, `season`, `pfr_id` | None |
| qbr | `season`, `season_type`, `qbr_total`, `pts_added`, `epa_total`, `qb_plays` | None |
| depth_charts | `season`, `club_code`, `week`, `position`, `full_name`, `gsis_id` | None |
| draft_picks | `season`, `round`, `pick`, `team`, `pfr_player_name`, `position` | None |
| combine | `season`, `player_name`, `pos`, `school`, `ht`, `wt` | None |
| teams | `team_abbr`, `team_name` | None |

**Validation mode is warn-never-block** -- Bronze accepts raw data and logs issues without failing ingestion. This is correct for a data lake.

## Patterns to Follow

### Pattern 1: Single-Season Batch Loop (Already Implemented)
**What:** The `--seasons` range mode iterates one season at a time, not all at once.
**When:** Always for PBP; good practice for all batch ingestion.
**Why:** PBP for 10 seasons simultaneously would require ~1 GB RAM. The per-season loop caps peak memory.
**Code:** `bronze_ingestion_simple.py` lines 326-389.

### Pattern 2: Sub-Type Iteration for NGS and PFR
**What:** NGS has 3 sub_types (`passing`, `rushing`, `receiving`), PFR has 4 (`pass`, `rush`, `rec`, `def`). Each must be ingested separately.
**When:** Backfilling NGS or PFR data.
**Why:** The nfl-data-py API requires a single stat_type per call.
**Example:**
```bash
# NGS: 3 sub_types x 10 seasons = 30 ingestion runs
for sub in passing rushing receiving; do
  python scripts/bronze_ingestion_simple.py --data-type ngs --sub-type $sub --seasons 2016-2025
done

# PFR weekly: 4 sub_types x 8 seasons = 32 ingestion runs
for sub in pass rush rec def; do
  python scripts/bronze_ingestion_simple.py --data-type pfr_weekly --sub-type $sub --seasons 2018-2025
done
```

### Pattern 3: QBR Dual Frequency
**What:** QBR needs both `--frequency weekly` and `--frequency seasonal` runs.
**When:** Backfilling QBR data.
**Why:** Weekly and seasonal QBR are different datasets from ESPN, both stored in same season directory with frequency-prefixed filenames.
**Example:**
```bash
python scripts/bronze_ingestion_simple.py --data-type qbr --frequency weekly --seasons 2016-2025
python scripts/bronze_ingestion_simple.py --data-type qbr --frequency seasonal --seasons 2016-2025
```

### Pattern 4: Teams is Season-Independent
**What:** Teams data (`import_team_desc()`) returns a static list of all 32 teams. No season parameter.
**When:** Ingesting teams.
**Why:** The adapter method takes no seasons argument; the registry has `requires_season: False`.
**Example:**
```bash
python scripts/bronze_ingestion_simple.py --data-type teams
# One file: data/bronze/teams/teams_{timestamp}.parquet
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Fetching All PBP Seasons at Once
**What:** Passing `--seasons 1999-2025` and loading all 26 seasons of PBP simultaneously.
**Why bad:** Would attempt to hold ~2.6 GB in memory. The per-season loop prevents this, but someone might bypass the CLI and call `adapter.fetch_pbp(seasons=list(range(1999,2026)))` directly.
**Instead:** Always loop one season at a time for PBP. The CLI already does this.

### Anti-Pattern 2: Weekly Partitioning for Season-Level Data
**What:** Splitting NGS, PFR, QBR, depth_charts, etc. into weekly subdirectories.
**Why bad:** These datasets are returned per-season by nfl-data-py. Artificially splitting adds complexity without read-performance benefit at Bronze scale.
**Instead:** Store per-season. Silver layer can filter by week.

### Anti-Pattern 3: Adding Metadata Columns in Adapter
**What:** The old `NFLDataFetcher` added `data_source`, `ingestion_timestamp`, `seasons_requested`, `week_filter` to DataFrames.
**Why bad:** Mixes ingestion metadata with source data at the adapter level. The new `NFLDataAdapter` correctly does NOT add these columns.
**Instead:** Ingestion metadata lives in the filename timestamp and directory structure.

### Anti-Pattern 4: Treating Schedules Path Inconsistency as Normal
**What:** Existing schedules data lives in `data/bronze/games/` (legacy) but registry says `schedules/`.
**Why bad:** Two paths for the same data type causes confusion in downstream reads.
**Instead:** New ingestion will write to `data/bronze/schedules/` per registry. Legacy `games/` directory can remain but should not be used for new reads. Consider a backfill note in the inventory.

## What Needs to Be Built (New Components)

### Required: Backfill Orchestration Script
**What:** A shell script or Python script that runs all the necessary ingestion commands in the right order with error handling and progress reporting.
**Why:** Running 50+ individual CLI commands manually is error-prone. A script ensures completeness and can resume from failures.
**Estimated CLI invocations (using --seasons batch mode):**

| Data Type | Sub-types | Frequencies | CLI Invocations |
|-----------|-----------|-------------|-----------------|
| teams | -- | -- | 1 |
| pbp | -- | -- | 1 (--seasons 2016-2025) |
| ngs | 3 | -- | 3 |
| pfr_weekly | 4 | -- | 4 |
| pfr_seasonal | 4 | -- | 4 |
| qbr | -- | 2 | 2 |
| depth_charts | -- | -- | 1 |
| draft_picks | -- | -- | 1 |
| combine | -- | -- | 1 |
| existing 6 types | -- | -- | 6 (2016-2019 + 2025 gaps) |
| **Total** | | | **~24 CLI invocations** |

### Required: Existing Data Type Backfill (2016-2019 + 2025)
The 6 existing data types only have 2020-2024 data. Backfilling to 2016-2025 means:
- **schedules:** Add 2016-2019 (2025 exists)
- **player_weekly, player_seasonal:** Add 2016-2019 + 2025 (min season is 2002, so all valid)
- **snap_counts:** Add 2016-2019 + 2025 (min season is 2012, valid)
- **injuries:** Add 2016-2019 + 2025 (min season is 2009, valid)
- **rosters:** Add 2016-2019 + 2025 (min season is 2002, valid)

### Required: Inventory Refresh
After backfill, regenerate `docs/BRONZE_LAYER_DATA_INVENTORY.md` using `python scripts/generate_inventory.py --output docs/BRONZE_LAYER_DATA_INVENTORY.md`.

### Optional: Snap Counts Week Handling
**Current issue:** `snap_counts` registry entry has `requires_week: True` and the adapter takes `(season, week)` positional args. For backfill, we need all weeks per season. The `--seasons` batch mode loops seasons but does NOT loop weeks. Options:
1. Add a `--weeks` range flag (e.g., `--weeks 1-18`) to the ingestion script
2. Change snap_counts adapter to accept `seasons` list like other methods and return all weeks
3. Use a wrapper script that loops weeks 1-18 for each season

Option 2 is cleanest but changes the adapter signature. Option 3 is safest for backfill.

### Optional: Player Weekly Week Handling
Same issue as snap_counts -- `player_weekly` registry has `requires_week: True`. For a full-season backfill, the existing data was ingested as full-season files (no week partition despite the registry path template). Need to decide: backfill per-week or per-season? Given existing data is stored per-season in `data/bronze/players/weekly/season=YYYY/`, backfilling per-season is consistent.

## Scalability Considerations

| Concern | Current (31 files, 7 MB) | Post-Backfill (~200+ files, ~1.5 GB) | Notes |
|---------|--------------------------|--------------------------------------|-------|
| Disk space | Trivial | ~1.5 GB (PBP dominates) | Fine for local dev |
| Ingestion time | Minutes | 1-3 hours (API rate limits) | PBP downloads are slow (~30s/season) |
| Read performance | Instant | Instant per-file | download_latest_parquet reads one file |
| Memory | < 50 MB peak | ~150 MB peak (PBP single season) | Per-season loop prevents OOM |

## Suggested Build Order

Based on dependencies and risk:

1. **Teams** (1 run, no dependencies, static data, fast sanity check that pipeline works)
2. **Draft picks + Combine** (simple, season-only, small files, validates basic --seasons flow)
3. **Depth charts** (season-only, medium size, useful for Silver layer)
4. **QBR** (tests frequency-prefixed filename logic -- both weekly and seasonal)
5. **PFR seasonal + PFR weekly** (tests sub-type dispatch, 4 sub_types each)
6. **NGS** (tests sub-type dispatch, 3 sub_types, 2016+ only)
7. **PBP** (largest dataset, do last so any bugs found earlier save re-ingestion time)
8. **Existing 6 types backfill** (add 2016-2019 + 2025 to schedules, player_weekly, etc.)
9. **Inventory refresh + validation** (regenerate docs, run validate_project.py)

**Rationale:** Start with small/fast types to validate the pipeline works end-to-end. Escalate to complex types (sub-types, frequencies). Do PBP last since it is the slowest (~30s per season download) and largest (~100 MB per season). Finding and fixing bugs on small types first avoids wasting time re-ingesting PBP.

## Sources

- `src/config.py` -- DATA_TYPE_SEASON_RANGES, PBP_COLUMNS, validate_season_for_type()
- `src/nfl_data_adapter.py` -- NFLDataAdapter with all 15 fetch methods
- `src/nfl_data_integration.py` -- NFLDataFetcher.validate_data() with required columns for all 15 types
- `scripts/bronze_ingestion_simple.py` -- DATA_TYPE_REGISTRY, _build_method_kwargs, parse_seasons_range, per-season loop
- `docs/NFL_DATA_DICTIONARY.md` -- Schema reference for all Bronze types
- `docs/BRONZE_LAYER_DATA_INVENTORY.md` -- Current inventory (31 files, 6 types, 2020-2024)
- `.planning/PROJECT.md` -- v1.1 milestone definition
