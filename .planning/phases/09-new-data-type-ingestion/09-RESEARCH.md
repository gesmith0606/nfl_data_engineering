# Phase 9: New Data Type Ingestion - Research

**Researched:** 2026-03-09
**Domain:** Bronze ingestion CLI enhancements + running all 9 new data types
**Confidence:** HIGH

## Summary

Phase 9 is primarily an **execution and CLI enhancement** phase, not a greenfield build. All 9 data types are already registered in `DATA_TYPE_REGISTRY`, all adapter fetch methods exist in `NFLDataAdapter`, and `validate_data()` already has required-column schemas for every new type. The work is: (1) enhance the CLI to support "ingest all variants by default" for sub-type and multi-frequency data types, (2) add schema diff logging and ingestion summary reporting, (3) run the actual ingestion across all types and their valid season ranges, and (4) verify output with `validate_data()`.

The codebase is well-structured for this -- registry dispatch means no if/elif chains, `_safe_call()` handles exceptions gracefully, and `_filter_seasons()` enforces per-type bounds from `DATA_TYPE_SEASON_RANGES`.

**Primary recommendation:** Focus CLI changes on three patterns -- variant looping (sub-types + QBR frequencies), schema diff logging, and end-of-run summary -- then run ingestion per plan grouping (simple types, sub-type types, PBP).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Empty data handling: warn and skip with generic message, no empty Parquet files, print summary at end (ingested vs skipped counts)
- Depth chart 2025 schema: ingest as-is (Bronze stores raw), schema normalization is Silver's job
- Schema diff logging: log column set diffs between seasons for ALL data types (not just depth charts)
- Season range policy: use each type's full valid range from `DATA_TYPE_SEASON_RANGES` (not just 2016-2025)
- QBR file organization: frequency prefix in filename (`weekly_qbr_YYYYMMDD.parquet`, `seasonal_qbr_YYYYMMDD.parquet`), both frequencies by default, `--frequency` flag to filter
- Sub-type data: ingest all variants by default for NGS, PFR weekly, PFR seasonal; `--sub-type` flag to filter to one

### Claude's Discretion
- Schema diff implementation details (how to compare column sets, where to log)
- Exact summary format for ingestion counts
- Whether to add a `--seasons` range flag for multi-season convenience
- Test structure and fixture design

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INGEST-01 | Teams reference data ingested | Teams already registered, `requires_season: False`, single fetch via `fetch_team_descriptions()` -- no season loop needed |
| INGEST-02 | Draft picks data ingested | `fetch_draft_picks()` exists, range 2000-2027, standard season loop |
| INGEST-03 | Combine data ingested | `fetch_combine()` exists, range 2000-2027, standard season loop |
| INGEST-04 | Depth charts ingested (handle 2025 schema) | `fetch_depth_charts()` exists, range 2001-2027, schema diff logging will surface 2025 changes |
| INGEST-05 | QBR weekly + seasonal ingested | `fetch_qbr()` exists, range 2006-2027, CLI needs both-frequencies-by-default loop |
| INGEST-06 | NGS passing/rushing/receiving ingested | `fetch_ngs()` exists, range 2016-2027, CLI needs all-sub-types-by-default loop |
| INGEST-07 | PFR weekly (pass/rush/rec/def) ingested | `fetch_pfr_weekly()` exists, range 2018-2027, CLI needs all-sub-types-by-default loop |
| INGEST-08 | PFR seasonal (pass/rush/rec/def) ingested | `fetch_pfr_seasonal()` exists, range 2018-2027, CLI needs all-sub-types-by-default loop |
| INGEST-09 | PBP ingested for 2016-2025 (103 curated columns) | `fetch_pbp()` exists with PBP_COLUMNS, single-season batch loop already in CLI, range 1999-2027 |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| nfl-data-py | pinned in requirements.txt | Data source for all nflverse data | Only library needed; all fetch methods already wired |
| pandas | existing | DataFrame processing | Already used throughout |
| pyarrow | existing | Parquet serialization | Already used for `.to_parquet()` |

### Supporting
No new libraries needed. All infrastructure exists.

## Architecture Patterns

### Current Project Structure (Relevant Files)
```
src/
  config.py                          # DATA_TYPE_SEASON_RANGES, PBP_COLUMNS, validate_season_for_type
  nfl_data_adapter.py                # NFLDataAdapter -- all 13 fetch_* methods
  nfl_data_integration.py            # NFLDataFetcher.validate_data() -- required column schemas
scripts/
  bronze_ingestion_simple.py         # DATA_TYPE_REGISTRY, CLI, main() loop
tests/
  test_advanced_ingestion.py         # Existing tests for adapter fetch methods + validation
  test_pbp_ingestion.py              # PBP column curation + CLI kwargs tests
  test_bronze_validation.py          # Validation wiring tests
```

### Pattern 1: Registry Dispatch (Already Established)
**What:** Each data type is a dict entry in `DATA_TYPE_REGISTRY` with `adapter_method`, `bronze_path`, `requires_week`, `requires_season`, and optional `sub_types`.
**When to use:** Always -- adding behavior is config-only.
**Key insight:** The registry already has entries for all 9 types. No new registry entries are needed.

### Pattern 2: Variant Looping (NEW -- Needs Implementation)
**What:** When `--sub-type` is not specified for NGS/PFR types, loop through all sub_types in the registry entry. When `--frequency` is not specified for QBR, loop through both `["weekly", "seasonal"]`.
**Where to implement:** In `main()` of `bronze_ingestion_simple.py`, before the season loop.
**Design:**

```python
# Determine variants to iterate
if "sub_types" in entry and args.sub_type is None:
    variants = [(k, v) for k, v in [("sub_type", st) for st in entry["sub_types"]]]
elif args.data_type == "qbr" and args.frequency is None:
    variants = [("frequency", "weekly"), ("frequency", "seasonal")]
else:
    variants = [None]  # single pass

for variant in variants:
    if variant:
        setattr(args, variant[0], variant[1])
    # ... existing season loop ...
```

**Current blocker:** CLI currently makes `--sub-type` **required** for sub-type data types (lines 284-296). This validation must be relaxed to allow None (meaning "all").

**QBR frequency default:** Currently `default="weekly"`. Must change to `default=None` so None means "both". The `--frequency` flag already exists.

### Pattern 3: Schema Diff Logging (NEW -- Needs Implementation)
**What:** Compare column sets between the current season's DataFrame and the previous season's. Log differences.
**Implementation recommendation:**

```python
def log_schema_diff(data_type: str, season: int, current_cols: set, prev_cols: set):
    """Log column differences between seasons."""
    new_cols = current_cols - prev_cols
    removed_cols = prev_cols - current_cols
    if new_cols or removed_cols:
        print(f"  Schema diff {data_type} {season} vs {season-1}: "
              f"+{len(new_cols)} new, -{len(removed_cols)} removed")
        if new_cols:
            print(f"    Added: {sorted(new_cols)}")
        if removed_cols:
            print(f"    Removed: {sorted(removed_cols)}")
```

**Where:** Track `prev_cols` as a variable in the season loop. Update after each successful fetch. Only compare when both current and previous exist.

### Pattern 4: Ingestion Summary (NEW -- Needs Implementation)
**What:** Print a summary at the end of each data type run showing ingested vs skipped.
**Implementation recommendation:**

```python
ingested = 0
skipped = 0
skipped_reasons = []

# ... in season loop ...
if df.empty:
    skipped += 1
    continue
ingested += 1

# ... after loop ...
print(f"\n{ingested}/{ingested + skipped} seasons ingested, "
      f"{skipped} skipped: empty data")
```

### Anti-Patterns to Avoid
- **Do NOT modify NFLDataAdapter for this phase.** All adapter methods are correct. Changes go in `bronze_ingestion_simple.py` only.
- **Do NOT add season-specific workarounds.** If QBR 2024 returns empty, the generic "warn and skip" handles it.
- **Do NOT validate season ranges manually.** Use `validate_season_for_type()` from config.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Season range validation | Custom min/max checks | `validate_season_for_type()` from config.py | Already handles all 13 data types with callable upper bounds |
| Error handling on fetch | Custom try/except in CLI | `_safe_call()` in NFLDataAdapter | Already returns empty DataFrame on any exception |
| Column validation | Custom schema checks | `NFLDataFetcher.validate_data()` | Already has required_columns dict for all 13 types |
| Season range parsing | Custom parser | `parse_seasons_range()` already in CLI | Already handles "2016-2025" and single "2024" |

## Common Pitfalls

### Pitfall 1: QBR Filename Collision
**What goes wrong:** Both weekly and seasonal QBR get the same filename pattern.
**Why it happens:** Current code already handles this with `qbr_{frequency}_{ts}.parquet` prefix. But if frequency is "seasonal" vs "season" there could be a mismatch.
**How to avoid:** The adapter uses `frequency="weekly"` and `frequency="season"` (not "seasonal"). The filename prefix should match: `qbr_weekly_` and `qbr_season_`. Check that `args.frequency` values match what the adapter expects.
**Warning signs:** Two files with same name in same directory.

### Pitfall 2: Sub-Type Required Validation Conflict
**What goes wrong:** CLI currently exits with error if `--sub-type` is not provided for NGS/PFR types.
**Why it happens:** Lines 284-296 of `bronze_ingestion_simple.py` enforce `args.sub_type is None` as an error.
**How to avoid:** Remove or relax this validation. When `sub_type is None`, interpret as "ingest all sub_types."
**Warning signs:** CLI rejects valid commands like `--data-type ngs --seasons 2016-2025` without `--sub-type`.

### Pitfall 3: PBP Memory on Multi-Season
**What goes wrong:** PBP data is very large (~50K rows per season). Fetching multiple seasons at once can exhaust memory.
**Why it happens:** nfl-data-py loads entire season into memory.
**How to avoid:** The single-season batch loop in `main()` already handles this. PBP is fetched one season at a time. Do NOT change this pattern.
**Warning signs:** MemoryError or kernel killed during PBP ingestion.

### Pitfall 4: Teams Has No Season
**What goes wrong:** Teams data (`fetch_team_descriptions()`) takes no arguments. The season loop must not call it with `seasons=[year]`.
**Why it happens:** `requires_season: False` in registry. The current CLI already handles this -- teams is fetched once, not per-season.
**How to avoid:** Teams runs as a single fetch outside the season loop. The current code structure already supports this since `season_list = [args.season]` but the method takes no kwargs. Verify this path works.
**Warning signs:** TypeError about unexpected keyword argument.

### Pitfall 5: QBR Frequency Naming Mismatch
**What goes wrong:** CONTEXT.md says filenames should be `weekly_qbr_` and `seasonal_qbr_`. But the adapter uses `frequency="season"` (not "seasonal"). The current code uses `qbr_{frequency}_` which would produce `qbr_season_` not `qbr_seasonal_`.
**How to avoid:** Decide whether to match adapter naming (`season`) or CONTEXT.md naming (`seasonal`). Recommend using the adapter value as-is (`qbr_weekly_`, `qbr_season_`) since it matches the nfl-data-py API parameter.
**Warning signs:** Confusion between "seasonal" and "season" in filenames vs API params.

## Code Examples

### Current CLI Flow (bronze_ingestion_simple.py main())
```python
# Lines 327-389: Season loop with fetch -> validate -> save
for idx, season in enumerate(season_list, 1):
    args.season = season
    method = getattr(adapter, entry["adapter_method"])
    kwargs = _build_method_kwargs(entry, args)
    df = method(**kwargs)

    if df.empty:
        print(f"  No data returned for season {season}.")
        continue

    # validate, build path, save_local, optional S3
```

### Existing Test Pattern (test_advanced_ingestion.py)
```python
@patch.object(NFLDataAdapter, "_import_nfl")
def test_fetch_ngs_returns_dataframe(self, mock_import_nfl, stat_type):
    mock_nfl = MagicMock()
    mock_nfl.import_ngs_data.return_value = _ngs_df()
    mock_import_nfl.return_value = mock_nfl

    adapter = NFLDataAdapter()
    df = adapter.fetch_ngs([2024], stat_type=stat_type)
    assert not df.empty
```

### Key _build_method_kwargs Wiring
```python
# Sub-type methods use different param names
if "sub_types" in entry:
    key = "stat_type" if method_name == "fetch_ngs" else "s_type"
    kwargs[key] = args.sub_type

# QBR frequency
if method_name == "fetch_qbr":
    kwargs["frequency"] = args.frequency
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| if/elif dispatch | Registry dispatch | v1.0 | Adding data type is config-only |
| S3 default | Local-first, --s3 opt-in | v1.0 | Works without AWS credentials |
| Multi-season PBP | Single-season batch loop | v1.0 | Memory-safe PBP ingestion |
| Required --sub-type | All variants by default (Phase 9) | v1.1 | CLI convenience for batch runs |

## Open Questions

1. **QBR "season" vs "seasonal" naming**
   - What we know: nfl-data-py API uses `frequency="season"`, CONTEXT.md says `seasonal_qbr_` filename
   - What's unclear: Whether to map "season" to "seasonal" in filenames or use API value as-is
   - Recommendation: Use "season" as-is in filenames to match API. Update CONTEXT.md expectation. This avoids a mapping layer.

2. **Teams requires_season=False path**
   - What we know: Teams is registered with `requires_season: False` and `bronze_path: "teams"` (no season partition)
   - What's unclear: Whether the current season loop handles this correctly (it may try to format `{season}` into a path that has no placeholder)
   - Recommendation: Verify and handle the teams path specially -- it should produce `data/bronze/teams/teams_YYYYMMDD.parquet`

3. **--seasons flag already exists**
   - What we know: `--seasons` is already implemented (lines 266-271) with `parse_seasons_range()`
   - Claude's discretion item about adding it is already resolved
   - Recommendation: No additional work needed here

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, 134 tests collected) |
| Config file | pytest runs from project root |
| Quick run command | `python -m pytest tests/test_advanced_ingestion.py tests/test_pbp_ingestion.py tests/test_bronze_validation.py -v -x` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INGEST-01 | Teams fetch produces valid Parquet | unit | `python -m pytest tests/test_advanced_ingestion.py -x -k "teams"` | Partial (adapter test exists, CLI path test needed) |
| INGEST-02 | Draft picks fetch + validate | unit | `python -m pytest tests/test_advanced_ingestion.py -x -k "draft"` | Yes |
| INGEST-03 | Combine fetch + validate | unit | `python -m pytest tests/test_advanced_ingestion.py -x -k "combine"` | Yes |
| INGEST-04 | Depth charts fetch (2025 schema) | unit | `python -m pytest tests/test_advanced_ingestion.py -x -k "depth"` | Yes |
| INGEST-05 | QBR both frequencies by default | unit | `python -m pytest tests/test_advanced_ingestion.py -x -k "qbr"` | Partial (adapter tests exist, both-by-default CLI test needed) |
| INGEST-06 | NGS all sub-types by default | unit | `python -m pytest tests/test_advanced_ingestion.py -x -k "ngs"` | Partial (adapter tests exist, all-by-default CLI test needed) |
| INGEST-07 | PFR weekly all sub-types by default | unit | `python -m pytest tests/test_advanced_ingestion.py -x -k "pfr_weekly"` | Partial (adapter tests exist, all-by-default CLI test needed) |
| INGEST-08 | PFR seasonal all sub-types by default | unit | `python -m pytest tests/test_advanced_ingestion.py -x -k "pfr_seasonal"` | Partial (adapter tests exist, all-by-default CLI test needed) |
| INGEST-09 | PBP 103 columns, single-season batch | unit | `python -m pytest tests/test_pbp_ingestion.py -v -x` | Yes |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_advanced_ingestion.py tests/test_pbp_ingestion.py tests/test_bronze_validation.py -v -x`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Tests for "all variants by default" CLI behavior (NGS, PFR weekly, PFR seasonal, QBR)
- [ ] Tests for schema diff logging output
- [ ] Tests for ingestion summary output (ingested/skipped counts)
- [ ] Test for teams no-season path handling

## Sources

### Primary (HIGH confidence)
- `scripts/bronze_ingestion_simple.py` -- current CLI implementation, 396 lines
- `src/nfl_data_adapter.py` -- all 13 fetch methods, 407 lines
- `src/config.py` -- DATA_TYPE_SEASON_RANGES with per-type bounds, PBP_COLUMNS
- `src/nfl_data_integration.py` -- validate_data() with required_columns for all 13 types
- `tests/test_advanced_ingestion.py` -- existing adapter + validation tests (24 tests)
- `tests/test_pbp_ingestion.py` -- PBP column curation + CLI tests (7 tests)
- `tests/test_bronze_validation.py` -- validation wiring tests (6 tests)

### Secondary (MEDIUM confidence)
- `.planning/phases/09-new-data-type-ingestion/09-CONTEXT.md` -- user decisions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all infrastructure exists
- Architecture: HIGH -- patterns are established, changes are additive to CLI only
- Pitfalls: HIGH -- codebase is well-understood, edge cases are documented in CONTEXT.md and STATE.md

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable -- no external API changes expected)
