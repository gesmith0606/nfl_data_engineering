# Phase 11: Orchestration and Validation - Research

**Researched:** 2026-03-11
**Domain:** Batch script orchestration, data validation, inventory generation
**Confidence:** HIGH

## Summary

Phase 11 is the final phase of the v1.1 Bronze Backfill milestone. It requires two deliverables: (1) a batch orchestration script that runs all 15 data types in sequence with graceful failure handling, and (2) a validation sweep that confirms data completeness and regenerates the Bronze inventory document.

All infrastructure for this phase already exists. The `DATA_TYPE_REGISTRY` in `bronze_ingestion_simple.py` defines all 15 data types with their adapter methods, paths, sub-types, and season requirements. The `generate_inventory.py` script already scans `data/bronze/` and produces markdown. The `NFLDataAdapter.validate_data()` method is wired in. The work is composing these pieces into a batch runner and updating the inventory.

**Primary recommendation:** Create a new `scripts/bronze_batch_ingestion.py` that iterates over `DATA_TYPE_REGISTRY`, calls the existing ingestion logic per type/season, catches and records failures, and prints a summary. Then run the inventory generator to update `docs/BRONZE_LAYER_DATA_INVENTORY.md`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ORCH-01 | Batch ingestion script runs all data types in sequence with progress reporting | `DATA_TYPE_REGISTRY` has all 15 types; existing `_build_method_kwargs()` and adapter methods handle all variants; script loops over registry keys with progress counter |
| ORCH-02 | Script handles failures gracefully (skip failed type, continue, report at end) | Wrap each type's ingestion in try/except, accumulate failures in a list, print summary table at end |
| VALID-01 | All ingested data passes Bronze validate_data() checks | `NFLDataAdapter.validate_data()` already works; batch script should call it per file and collect pass/warn/fail counts |
| VALID-02 | Bronze inventory regenerated reflecting full 10-year dataset | `scripts/generate_inventory.py` exists and works; run it with `--output docs/BRONZE_LAYER_DATA_INVENTORY.md` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3.9+ | 3.9 | Script runtime | Already pinned in project |
| pandas | installed | DataFrame operations | Already used everywhere |
| pyarrow | installed | Parquet read/write + schema inspection | Already used by generate_inventory.py |
| nfl-data-py | pinned | NFL data fetching | Already the sole data source |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| argparse | stdlib | CLI argument parsing | Batch script CLI |
| datetime | stdlib | Timestamps for filenames | Already used in ingestion |
| logging | stdlib | Structured logging | Batch script should use logging |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom batch script | Make/Taskfile | Overkill for 1 sequential loop; Python gives better error handling and progress reporting |
| Sequential execution | asyncio/multiprocessing | Risk of API rate limiting; sequential is safer and simpler for nfl-data-py |

## Architecture Patterns

### Recommended Project Structure
```
scripts/
├── bronze_ingestion_simple.py    # Existing single-type CLI
├── bronze_batch_ingestion.py     # NEW: batch orchestration (ORCH-01, ORCH-02)
├── generate_inventory.py         # Existing: inventory regeneration (VALID-02)
└── validate_bronze_coverage.py   # Optional: standalone validation (VALID-01)
```

### Pattern 1: Registry-Driven Batch Loop
**What:** Iterate over `DATA_TYPE_REGISTRY` keys, calling existing adapter methods per type
**When to use:** The batch script
**Example:**
```python
from scripts.bronze_ingestion_simple import DATA_TYPE_REGISTRY, _build_method_kwargs, save_local
from src.config import DATA_TYPE_SEASON_RANGES

results = []  # list of (data_type, variant, season, status, message)

for data_type, entry in DATA_TYPE_REGISTRY.items():
    # Determine season range from config
    min_season, max_fn = DATA_TYPE_SEASON_RANGES[data_type]
    seasons = list(range(max(min_season, 2016), max_fn() + 1))

    # Determine variants
    variants = entry.get("sub_types", [None])

    for variant in variants:
        for season in seasons:
            try:
                # fetch + save + validate
                results.append((data_type, variant, season, "OK", ""))
            except Exception as e:
                results.append((data_type, variant, season, "FAIL", str(e)))
                continue  # ORCH-02: skip and continue
```

### Pattern 2: Failure Accumulation and Summary
**What:** Collect all results (pass/fail) during the run, print a summary table at the end
**When to use:** Required by ORCH-02
**Example:**
```python
# After all types processed
failures = [r for r in results if r[3] == "FAIL"]
successes = [r for r in results if r[3] == "OK"]

print(f"\n{'='*60}")
print(f"BATCH INGESTION COMPLETE")
print(f"  Succeeded: {len(successes)}")
print(f"  Failed:    {len(failures)}")
if failures:
    print(f"\nFailures:")
    for dtype, variant, season, status, msg in failures:
        label = f"{dtype}" + (f"/{variant}" if variant else "")
        print(f"  {label} season={season}: {msg}")
```

### Pattern 3: Skip Already-Ingested Data
**What:** Check if parquet files already exist for a type/season before fetching
**When to use:** Make the batch script idempotent so re-runs don't re-download everything
**Example:**
```python
import glob

def already_ingested(data_type: str, season: int, base_dir: str = "data/bronze") -> bool:
    """Check if at least one parquet file exists for this type/season."""
    pattern = os.path.join(base_dir, "**", f"season={season}", "*.parquet")
    # Match against the data type's bronze_path pattern
    path = entry["bronze_path"].format(season=season, week="*", sub_type="*")
    full_pattern = os.path.join(base_dir, path, "*.parquet")
    return len(glob.glob(full_pattern)) > 0
```

### Anti-Patterns to Avoid
- **Re-implementing ingestion logic:** The batch script should reuse functions from `bronze_ingestion_simple.py`, not duplicate the fetch/save/validate chain.
- **Aborting on first failure:** ORCH-02 explicitly requires skip-and-continue behavior.
- **Parallel fetching:** nfl-data-py downloads from nflverse GitHub; parallel requests risk rate limiting even with GITHUB_TOKEN.
- **Hardcoding season ranges:** Use `DATA_TYPE_SEASON_RANGES` from config.py for dynamic bounds.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Data type enumeration | Custom list of types | `DATA_TYPE_REGISTRY` from bronze_ingestion_simple.py | Already complete with all 15 types, sub-types, paths |
| Season range calculation | Hardcoded year lists | `DATA_TYPE_SEASON_RANGES` from config.py | Handles per-type min/max including injury cap |
| Data validation | Custom schema checks | `NFLDataAdapter.validate_data()` | Already validates columns, nulls, type-specific rules |
| Inventory generation | Custom directory scanner | `scripts/generate_inventory.py` | Already scans, aggregates, formats markdown |
| Parquet file saving | Custom writer | `save_local()` from bronze_ingestion_simple.py | Handles directory creation, naming |

## Common Pitfalls

### Pitfall 1: Memory Exhaustion on PBP
**What goes wrong:** PBP data for a single season is large (~100MB in memory). Batch processing all 10 seasons sequentially can accumulate memory if DataFrames are not released.
**Why it happens:** Python garbage collection may not reclaim large DataFrames immediately.
**How to avoid:** Process one season at a time (already the pattern in bronze_ingestion_simple.py), explicitly `del df` after save, and use `gc.collect()` after PBP seasons.
**Warning signs:** Process memory exceeding 2GB during batch run.

### Pitfall 2: QBR Empty Data for Recent Seasons
**What goes wrong:** QBR seasonal data for 2024-2025 returns 0 rows from nflverse.
**Why it happens:** Known nflverse delay (documented in STATE.md decisions).
**How to avoid:** Treat 0-row returns as warnings, not failures. The batch script should log "0 rows returned" and continue, not count it as a failure.
**Warning signs:** QBR seasonal shows as "failed" when it should show "skipped (empty)".

### Pitfall 3: Player Weekly/Seasonal 2025 Returns 404
**What goes wrong:** nflverse has not published 2025 player weekly/seasonal data yet.
**Why it happens:** Data not yet available (HTTP 404).
**How to avoid:** The adapter's `_safe_call` already catches exceptions and returns empty DataFrame. Batch script should handle this gracefully as "no data available" not "failure".
**Warning signs:** 2025 showing as failed for player_weekly and player_seasonal.

### Pitfall 4: Snap Counts Week Partitioning
**What goes wrong:** Snap counts need week-level file splitting unlike most other types.
**Why it happens:** The `week_partition: True` flag in the registry triggers per-week file writing.
**How to avoid:** Reuse the existing week-partition logic from `bronze_ingestion_simple.py` rather than writing a flat file.
**Warning signs:** Snap count files missing week partitions.

### Pitfall 5: Inventory Data Type Naming Mismatch
**What goes wrong:** The inventory scanner derives data type names from directory paths (e.g., `players/weekly`), but the registry uses different keys (e.g., `player_weekly`).
**Why it happens:** Directory structure uses slashes, registry uses underscores.
**How to avoid:** The inventory is directory-based and independent of the registry -- this is by design. The inventory should reflect the actual file system structure, showing all 15+ directory groupings.
**Warning signs:** Inventory shows fewer than 15 data type rows.

### Pitfall 6: Existing Data Re-ingestion
**What goes wrong:** Running the batch script when data already exists creates duplicate timestamped files, wasting disk space.
**Why it happens:** The ingestion pattern appends timestamped files, never overwrites.
**How to avoid:** Add a `--force` flag; by default, skip types/seasons that already have files. Or accept duplicates since `download_latest_parquet()` always reads the newest.
**Warning signs:** `data/bronze/` size doubling after each batch run.

## Code Examples

### Batch Script Core Loop
```python
#!/usr/bin/env python3
"""Batch Bronze ingestion -- runs all 15 data types with failure handling."""

import sys
import os
import time
from datetime import datetime
from typing import List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bronze_ingestion_simple import DATA_TYPE_REGISTRY
from src.nfl_data_adapter import NFLDataAdapter
from src.config import DATA_TYPE_SEASON_RANGES

# Result: (data_type, variant, season, status, detail)
Result = Tuple[str, str, int, str, str]

def run_batch(season_start: int = 2016, season_end: int = 2025,
              skip_existing: bool = True) -> List[Result]:
    results: List[Result] = []
    adapter = NFLDataAdapter()
    total_types = len(DATA_TYPE_REGISTRY)

    for idx, (data_type, entry) in enumerate(DATA_TYPE_REGISTRY.items(), 1):
        print(f"\n[{idx}/{total_types}] Processing: {data_type}")

        # Determine valid seasons for this type
        min_s, max_fn = DATA_TYPE_SEASON_RANGES.get(data_type, (2016, lambda: 2025))
        effective_start = max(min_s, season_start)
        effective_end = min(max_fn(), season_end)
        seasons = list(range(effective_start, effective_end + 1))

        # ... fetch, save, validate per season ...

    return results
```

### Progress Output Format (ORCH-01)
```
[1/15] Processing: schedules
  Season 2016... OK (272 rows, 50 cols)
  Season 2017... OK (268 rows, 50 cols)
  ...
[2/15] Processing: pbp
  Season 2016... OK (45,832 rows, 103 cols)
  ...
[7/15] Processing: snap_counts
  Season 2020... OK (5,832 rows, 18 cols, 18 week files)
  ...

============================================================
BATCH INGESTION COMPLETE
  Types processed: 15/15
  Succeeded: 142
  Skipped (empty): 3
  Failed: 0
```

### Validation Sweep (VALID-01)
```python
def validate_all_bronze(base_dir: str = "data/bronze") -> dict:
    """Walk all parquet files in bronze and run validate_data()."""
    adapter = NFLDataAdapter()
    results = {"passed": 0, "warnings": 0, "failed": 0, "issues": []}

    for dirpath, _, filenames in os.walk(base_dir):
        for fname in filenames:
            if not fname.endswith(".parquet"):
                continue
            filepath = os.path.join(dirpath, fname)
            df = pd.read_parquet(filepath)
            # Derive data_type from path...
            try:
                val = adapter.validate_data(df, data_type)
                if val.get("is_valid"):
                    results["passed"] += 1
                else:
                    results["warnings"] += 1
            except Exception as e:
                results["failed"] += 1
                results["issues"].append((filepath, str(e)))

    return results
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual per-type ingestion | Registry-driven CLI with --seasons range | v1.0 (Phase 1) | Adding a type is config-only |
| S3-first storage | Local-first with --s3 opt-in | v1.1 (March 2026) | No AWS credentials needed |
| Hand-written inventory | Auto-generated from filesystem scan | v1.0 (Phase 4) | generate_inventory.py exists |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.1 |
| Config file | pytest runs from project root |
| Quick run command | `python -m pytest tests/test_generate_inventory.py -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ORCH-01 | Batch script runs all types with progress | unit | `python -m pytest tests/test_batch_ingestion.py::test_runs_all_types -x` | Wave 0 |
| ORCH-02 | Failures skipped, summary printed | unit | `python -m pytest tests/test_batch_ingestion.py::test_failure_handling -x` | Wave 0 |
| VALID-01 | validate_data passes on all files | integration | `python -m pytest tests/test_batch_ingestion.py::test_validation_sweep -x` | Wave 0 |
| VALID-02 | Inventory reflects 15 types | unit | `python -m pytest tests/test_generate_inventory.py -x` | Existing (8 tests) |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_batch_ingestion.py tests/test_generate_inventory.py -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_batch_ingestion.py` -- covers ORCH-01, ORCH-02, VALID-01
- Existing `tests/test_generate_inventory.py` covers VALID-02 (8 tests already passing)

## Open Questions

1. **Should the batch script re-download existing data?**
   - What we know: Data already exists for all 15 types from Phase 9 and 10 execution
   - What's unclear: Whether the user wants idempotent re-runs or just the script capability
   - Recommendation: Default to skip-existing with `--force` flag for re-download. Since data is already present, the script primarily proves repeatability.

2. **How to map directory paths back to registry data types for validation?**
   - What we know: Directory paths (e.g., `players/weekly`) differ from registry keys (e.g., `player_weekly`)
   - What's unclear: Whether validation should use registry mapping or generic column checks
   - Recommendation: Build a reverse mapping from `bronze_path` patterns to registry keys. This is a small lookup dict.

## Sources

### Primary (HIGH confidence)
- `scripts/bronze_ingestion_simple.py` -- all 15 data types in DATA_TYPE_REGISTRY
- `src/config.py` -- DATA_TYPE_SEASON_RANGES with per-type season bounds
- `src/nfl_data_adapter.py` -- all fetch methods and validate_data()
- `scripts/generate_inventory.py` -- existing inventory scanner and markdown formatter
- `docs/BRONZE_LAYER_DATA_INVENTORY.md` -- current inventory (outdated, shows only 6 types)

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` -- accumulated decisions about QBR empty data, player 2025 404s, snap count week partitioning

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in use, no new dependencies
- Architecture: HIGH - all building blocks exist, phase is composition work
- Pitfalls: HIGH - known from Phase 9 and 10 execution (documented in STATE.md)

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable -- no external dependencies changing)
