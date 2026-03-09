# Phase 10: Existing Type Backfill - Research

**Researched:** 2026-03-09
**Domain:** Bronze ingestion backfill for 6 existing data types (schedules, player_weekly, player_seasonal, snap_counts, injuries, rosters)
**Confidence:** HIGH

## Summary

Phase 10 extends 6 already-working Bronze data types from their current 2020-2024/2025 coverage back to 2016. All fetch methods exist in `NFLDataAdapter`, all registry entries exist in `DATA_TYPE_REGISTRY`, the `--seasons` range flag is already implemented, and `validate_data()` has required-column schemas for all 6 types. The work is primarily execution -- running the CLI with `--seasons 2016-2019` for most types -- with two code fixes needed first.

The two code issues are: (1) `fetch_snap_counts` in the adapter passes `(season, week)` positionally to `nfl.import_snap_counts(years)` which requires a list, causing a crash; and (2) the success criteria requires week-level partitioning for snap_counts, but `import_snap_counts` returns all weeks in one DataFrame. These require an adapter fix and a post-fetch split-by-week loop in the ingestion script.

**Primary recommendation:** Fix the snap_counts adapter and ingestion path first (one small code change), then run the existing CLI with `--seasons 2016-2019` (or `2016-2025` for full re-ingestion) for each of the 6 data types. Four of the six types (schedules, player_weekly, player_seasonal, rosters) should work with zero code changes via the existing `--seasons` flag.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BACKFILL-01 | Schedules extended to 2016-2025 | `fetch_schedules()` works, range 1999-2027. Run `--data-type schedules --seasons 2016-2025`. Existing data in `games/` will remain; new data goes to `schedules/` per registry. |
| BACKFILL-02 | Player weekly extended to 2016-2025 | `fetch_weekly_data()` works, range 2002-2027. Run `--data-type player_weekly --seasons 2016-2025 --week 0` (week param ignored by nfl-data-py; data contains all weeks). Existing `requires_week: True` means CLI requires `--week` even though it's unused for this API call. |
| BACKFILL-03 | Player seasonal extended to 2016-2025 | `fetch_seasonal_data()` works, range 2002-2027. Run `--data-type player_seasonal --seasons 2016-2025`. No week needed. Straightforward. |
| BACKFILL-04 | Snap counts extended to 2016-2025 with week-level partitioning | **Requires adapter fix.** Current `fetch_snap_counts(season, week)` passes int to API expecting list. Need to: (a) fix adapter to pass `[season]`, (b) add post-fetch week-split logic to save one file per week per season. Valid from 2012. |
| BACKFILL-05 | Injuries extended to 2016-2024 | `fetch_injuries()` works, range 2009-2024 (capped). Run `--data-type injuries --seasons 2016-2024`. Config cap at 2024 already enforced by `validate_season_for_type()`. |
| BACKFILL-06 | Rosters extended to 2016-2025 | `fetch_rosters()` works (uses `import_seasonal_rosters`), range 2002-2027. Run `--data-type rosters --seasons 2016-2025`. No week needed. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| nfl-data-py | pinned in requirements.txt | Data source for all nflverse data | All 6 fetch methods already wired |
| pandas | existing | DataFrame processing | Already used throughout |
| pyarrow | existing | Parquet serialization | Already used for `.to_parquet()` |

### Supporting
No new libraries needed. All infrastructure exists from Phase 9.

## Architecture Patterns

### Current Project Structure (Relevant Files)
```
src/
  config.py                          # DATA_TYPE_SEASON_RANGES, validate_season_for_type
  nfl_data_adapter.py                # NFLDataAdapter -- fetch_snap_counts needs fix
  nfl_data_integration.py            # NFLDataFetcher.validate_data() -- all 6 schemas
scripts/
  bronze_ingestion_simple.py         # DATA_TYPE_REGISTRY, --seasons flag, main() loop
data/bronze/
  games/season=YYYY/                 # OLD schedules path (2020-2025)
  schedules/season=YYYY/             # NEW schedules path per registry (will be created)
  players/weekly/season=YYYY/        # player_weekly (2020-2024, no week subdir)
  players/seasonal/season=YYYY/      # player_seasonal (2020-2024)
  players/snap_counts/season=YYYY/   # snap_counts (2020-2024, no week subdir)
  players/injuries/season=YYYY/      # injuries (2020-2024)
  players/rosters/season=YYYY/       # rosters (2020-2024)
```

### Pattern 1: Season-Range Batch Ingestion (Already Working)
**What:** The CLI's `--seasons 2016-2025` flag loops one season at a time through `parse_seasons_range()`, calling the adapter's fetch method per season.
**When to use:** For all 6 data types (4 work immediately, 2 need fixes first).
**Example:**
```bash
# Schedules backfill -- works with zero code changes
python scripts/bronze_ingestion_simple.py --data-type schedules --seasons 2016-2025

# Player seasonal -- works with zero code changes
python scripts/bronze_ingestion_simple.py --data-type player_seasonal --seasons 2016-2025
```

### Pattern 2: Snap Counts Week-Level Partitioning (Needs Implementation)
**What:** `import_snap_counts([season])` returns ALL weeks for that season in one DataFrame. To achieve week-level partitioning, the ingestion script must group by `week` column and save one file per week per season.
**When to use:** Only for snap_counts (BACKFILL-04).
**Example:**
```python
# In adapter: fix to pass list
def fetch_snap_counts(self, seasons: List[int]) -> pd.DataFrame:
    seasons = self._filter_seasons("snap_counts", seasons)
    if not seasons:
        return pd.DataFrame()
    nfl = self._import_nfl()
    return self._safe_call("fetch_snap_counts", nfl.import_snap_counts, seasons)

# In ingestion script: post-fetch split
if args.data_type == "snap_counts" and "week" in df.columns:
    for week_num, week_df in df.groupby("week"):
        week_path = bronze_path.format(season=season, week=week_num)
        save_local(week_df, os.path.join("data", "bronze", week_path, filename))
```

### Pattern 3: Player Weekly Storage (Existing Discrepancy)
**What:** Registry says `requires_week: True` and path `players/weekly/season={season}/week={week}`, but `import_weekly_data([season])` returns all weeks. Existing data is stored at `players/weekly/season=YYYY/` without week subdirectories.
**When to use:** Understanding that the existing pattern stores all weeks in one file per season. The success criteria says "Parquet files for seasons 2016-2025" (not week-level), so the current storage pattern is acceptable.

### Anti-Patterns to Avoid
- **Passing single int to nfl-data-py functions expecting lists:** Always wrap in `[season]`. This is the snap_counts bug.
- **Re-ingesting data that already exists:** Seasons 2020-2024/2025 already have data. Re-running is harmless (new timestamped files), but wastes time. Target only missing seasons (2016-2019, plus 2025 where missing).
- **Assuming week parameter matters for API calls:** For player_weekly and snap_counts, `nfl-data-py` ignores week params and returns all weeks for the requested season(s).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Season range parsing | Custom arg parser | `parse_seasons_range()` in CLI | Already handles "2016-2025" format |
| Season bounds validation | Manual range checks | `validate_season_for_type()` from config | Enforces per-type min/max including injury 2024 cap |
| Data validation | Custom column checks | `adapter.validate_data(df, data_type)` | Already has required columns for all 6 types |
| Schema diff tracking | Manual column comparison | `log_schema_diff()` in CLI | Already compares consecutive seasons |

## Common Pitfalls

### Pitfall 1: Snap Counts Adapter Crash
**What goes wrong:** `fetch_snap_counts(season, week)` passes `season` (int) to `nfl.import_snap_counts(years)` which requires a list/range, causing `ValueError: Input must be list or range`.
**Why it happens:** Adapter was written with a `(season, week)` signature assuming the API takes individual args, but it takes a list.
**How to avoid:** Change adapter signature to `fetch_snap_counts(self, seasons: List[int])` and pass `seasons` directly. Update `_build_method_kwargs` to pass `seasons=[args.season]` instead of `season`/`week`.
**Warning signs:** Any attempt to run `--data-type snap_counts` through the CLI will fail.

### Pitfall 2: Player Weekly Week Argument
**What goes wrong:** Registry has `requires_week: True` for player_weekly, so CLI requires `--week`. But `fetch_weekly_data` passes `seasons=[args.season]` to `import_weekly_data(seasons)` which returns ALL weeks regardless.
**Why it happens:** The `--week` was originally used for S3 path partitioning, not for API filtering.
**How to avoid:** For backfill, pass any `--week` value (e.g., `--week 0`). The data saved will contain all weeks but be stored at the specified week path. Alternatively, update registry to `requires_week: False` and adjust bronze_path.
**Warning signs:** Confusing file naming if `--week 1` is used but file contains weeks 1-18.

### Pitfall 3: Schedules Path Migration
**What goes wrong:** Old data lives in `data/bronze/games/season=YYYY/` but registry points to `data/bronze/schedules/season=YYYY/`. Downstream code reading schedules might look in the wrong place.
**Why it happens:** Registry was updated during v1.0/v1.1 but old data was never moved.
**How to avoid:** The backfill creates new files at the registry path. Verify downstream readers use the registry path, not hardcoded `games/`.

### Pitfall 4: Injuries 2025 Season Attempt
**What goes wrong:** Running `--seasons 2016-2025` for injuries fails because `validate_season_for_type("injuries", 2025)` returns False (capped at 2024).
**Why it happens:** nflverse discontinued injury data after 2024.
**How to avoid:** Use `--seasons 2016-2024` for injuries. The CLI validates all seasons upfront and exits on first invalid season.

### Pitfall 5: Rate Limiting During Bulk Ingestion
**What goes wrong:** Fetching 10 seasons sequentially hits GitHub/nflverse rate limits.
**Why it happens:** nfl-data-py downloads data from GitHub. Without `GITHUB_TOKEN`, limit is 60 requests/hour.
**How to avoid:** Phase 8 already configured `GITHUB_TOKEN` for 5000 req/hr. Verify it's still set in `.env`.

## Code Examples

### Running the Full Backfill (4 simple types)
```bash
source venv/bin/activate

# Schedules: 2016-2025 (valid range 1999+)
python scripts/bronze_ingestion_simple.py --data-type schedules --seasons 2016-2025

# Player seasonal: 2016-2025 (valid range 2002+)
python scripts/bronze_ingestion_simple.py --data-type player_seasonal --seasons 2016-2025

# Injuries: 2016-2024 only (capped at 2024)
python scripts/bronze_ingestion_simple.py --data-type injuries --seasons 2016-2024

# Rosters: 2016-2025 (valid range 2002+)
python scripts/bronze_ingestion_simple.py --data-type rosters --seasons 2016-2025
```

### Player Weekly (Needs Week Arg)
```bash
# --week is required by registry but unused by API; data contains all weeks
python scripts/bronze_ingestion_simple.py --data-type player_weekly --seasons 2016-2025 --week 0
```

### Snap Counts (After Fix)
```bash
# After adapter fix, run similarly to other types
python scripts/bronze_ingestion_simple.py --data-type snap_counts --seasons 2016-2025
```

### Adapter Fix: fetch_snap_counts
```python
# BEFORE (broken):
def fetch_snap_counts(self, season: int, week: int) -> pd.DataFrame:
    nfl = self._import_nfl()
    return self._safe_call("fetch_snap_counts", nfl.import_snap_counts, season, week)

# AFTER (fixed):
def fetch_snap_counts(self, seasons: List[int]) -> pd.DataFrame:
    seasons = self._filter_seasons("snap_counts", seasons)
    if not seasons:
        return pd.DataFrame()
    nfl = self._import_nfl()
    return self._safe_call("fetch_snap_counts", nfl.import_snap_counts, seasons)
```

### Registry + Build-Method-Kwargs Fix for Snap Counts
```python
# Registry change:
"snap_counts": {
    "adapter_method": "fetch_snap_counts",
    "bronze_path": "players/snaps/season={season}/week={week}",
    "requires_week": False,       # Changed from True
    "requires_season": True,
    "week_partition": True,       # NEW: signals post-fetch week splitting
},

# _build_method_kwargs change: remove snap_counts special case
# It now falls through to the standard `seasons=[args.season]` path
```

### Post-Fetch Week Splitting for Snap Counts
```python
# In main() ingestion loop, after df is fetched:
if entry.get("week_partition") and "week" in df.columns:
    for week_num, week_df in df.groupby("week"):
        week_path = entry["bronze_path"].format(season=season, week=int(week_num))
        week_filename = f"{args.data_type}_{ts}.parquet"
        week_local_path = os.path.join("data", "bronze", week_path, week_filename)
        save_local(week_df, week_local_path)
    continue  # Skip the default single-file save
```

## Existing Data Inventory

| Data Type | Current Coverage | Backfill Target | Missing Seasons | Files to Create |
|-----------|-----------------|-----------------|-----------------|-----------------|
| schedules | 2020-2025 (in `games/`) | 2016-2025 (in `schedules/`) | 2016-2019 (or all 10 in new path) | 4-10 files |
| player_weekly | 2020-2024 | 2016-2025 | 2016-2019, 2025 | 5-6 files |
| player_seasonal | 2020-2024 | 2016-2025 | 2016-2019, 2025 | 5-6 files |
| snap_counts | 2020-2024 (season-level) | 2016-2025 (week-level) | 2016-2019, 2025 + restructure | ~180 files (18 weeks x 10 seasons) |
| injuries | 2020-2024 | 2016-2024 | 2016-2019 | 4 files |
| rosters | 2020-2024 | 2016-2025 | 2016-2019, 2025 | 5-6 files |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Schedules in `games/` dir | Schedules in `schedules/` dir | v1.0 registry | Backfill creates files at new path |
| Snap counts: season-level files | Week-level partitioned files | Phase 10 requirement | Adapter fix + split logic needed |
| `NFLDataFetcher` direct calls | `NFLDataAdapter` wrapper | v1.0 refactor | Adapter is canonical; old fetcher still used for `validate_data()` |

## Open Questions

1. **Player weekly storage: week-split or single file?**
   - What we know: Registry says `requires_week: True` and path includes `week={week}`, but existing data stores all weeks in one file per season at `players/weekly/season=YYYY/`. Success criteria says "Parquet files for seasons 2016-2025" without mentioning week partitioning.
   - What's unclear: Should backfill match existing storage (one file per season) or match registry path (week-level)?
   - Recommendation: Match existing storage pattern (one file per season) since success criteria doesn't require week partitioning for player_weekly. Only snap_counts explicitly requires week-level partitioning.

2. **Should old `games/` directory data be migrated or left in place?**
   - What we know: Old schedules live at `data/bronze/games/`, new ones go to `data/bronze/schedules/`. Downstream Silver code may read from either.
   - What's unclear: Whether any Silver/Gold code reads from `games/` path.
   - Recommendation: Leave old data in place. Create new data at registry path. Verify downstream readers in Phase 11.

3. **Re-ingest existing 2020-2024 seasons or only backfill missing years?**
   - What we know: Re-ingesting is safe (timestamped files). But it duplicates data and takes time.
   - Recommendation: Only ingest missing seasons (2016-2019, plus 2025 where applicable) to minimize time and disk usage. Full re-ingestion can happen in Phase 11 orchestration.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | none (uses default discovery) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACKFILL-04 | Snap counts adapter accepts list, returns all weeks | unit | `python -m pytest tests/test_backfill.py::test_snap_counts_adapter_list -x` | Wave 0 |
| BACKFILL-04 | Week-level partitioning splits DataFrame by week column | unit | `python -m pytest tests/test_backfill.py::test_snap_counts_week_partition -x` | Wave 0 |
| BACKFILL-05 | Injuries 2025 rejected by season validation | unit | `python -m pytest tests/test_infrastructure.py::test_injury_season_cap -x` | Likely exists |
| BACKFILL-01 to 06 | All backfilled files pass validate_data() | integration | Manual: run CLI then `validate_data()` on output | Manual |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backfill.py` -- covers snap_counts adapter fix (BACKFILL-04)
- [ ] Verify `test_infrastructure.py` has injury cap test (BACKFILL-05)

## Sources

### Primary (HIGH confidence)
- **nfl-data-py source code** -- `inspect.getsource(nfl.import_snap_counts)` confirms `years` must be list/range, min 2012
- **Existing codebase** -- `src/nfl_data_adapter.py`, `scripts/bronze_ingestion_simple.py`, `src/config.py` all read directly
- **Existing bronze data** -- filesystem scan confirms 2020-2024/2025 coverage for all 6 types

### Secondary (MEDIUM confidence)
- **nfl-data-py API signatures** -- `help(nfl.import_snap_counts)` confirms `years` parameter

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all infrastructure exists
- Architecture: HIGH -- registry dispatch, adapter layer, CLI all verified by reading source
- Pitfalls: HIGH -- snap_counts bug confirmed by reading both adapter source and nfl-data-py source
- Backfill execution: HIGH -- 4 of 6 types work with zero changes; confirmed by registry analysis

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable -- nfl-data-py API unlikely to change mid-offseason)
