# Pitfalls Research

**Domain:** Bronze backfill of 9 new NFL data types across 10 years (2016-2025)
**Researched:** 2026-03-08
**Confidence:** HIGH (project-specific quirks verified from codebase, nflverse docs, and GitHub issues)

## Critical Pitfalls

### Pitfall 1: nfl-data-py Is Archived -- No Bug Fixes Coming

**What goes wrong:**
The `nfl-data-py` repository was [archived by nflverse on September 25, 2025](https://github.com/nflverse/nfl_data_py). No further maintenance, bug fixes, or Python version updates will be released. The replacement is [nflreadpy](https://nflreadpy.nflverse.com/), which returns Polars DataFrames and has a different API (`load_*` instead of `import_*`). Known unfixed bugs include: NumPy 2.0 `np.float_` incompatibility ([issue #98](https://github.com/nflverse/nfl_data_py/issues/98)), Python 3.13 install failure, and `import_injuries` 404 for 2025 season.

**Why it happens:**
The project is pinned to `nfl-data-py==0.3.3` and `numpy==1.26.4`. This works today because nfl-data-py pulls from nflverse-data GitHub releases which are still active. But adding 9 new data types deepens the dependency on a dead library.

**How to avoid:**
- Pin exact versions in `requirements.txt`: `nfl-data-py==0.3.3`, `numpy<2` (already done)
- Complete the full backfill NOW while nflverse-data release URLs are stable
- The existing `NFLDataAdapter` in `src/nfl_data_adapter.py` already isolates all `nfl.import_*` calls -- this is the correct pattern. Do not add nfl-data-py imports anywhere else
- Plan nflreadpy migration as a separate future milestone, not part of this backfill

**Warning signs:**
- `AttributeError: np.float_` on import -- means numpy was upgraded past 2.0
- 404 errors from GitHub releases -- means nflverse-data URLs changed
- Import failures after any `pip install --upgrade`

**Phase to address:**
Pre-work (verify dependency pins) before any backfill phase begins.

---

### Pitfall 2: PBP Memory Explosion on Multi-Season Loads

**What goes wrong:**
Each PBP season is ~40K rows x 400+ columns, roughly 150-300 MB in RAM. Loading 10 seasons simultaneously causes OOM kills. Setting `include_participation=True` doubles column count and memory. The current Bronze layer is 7 MB total -- PBP alone will be ~500 MB on disk.

**Why it happens:**
The ingestion script already loops one season at a time (line 327 of `bronze_ingestion_simple.py`) and passes `columns=PBP_COLUMNS` (103 curated columns) with `include_participation=False`. These protections are correct. The risk is that a developer bypasses the CLI and calls the adapter directly with `seasons=[2016, 2017, ..., 2025]`.

**How to avoid:**
- The per-season loop in `bronze_ingestion_simple.py` is correct -- do not change it
- Always pass `columns=PBP_COLUMNS` to avoid loading all 400+ columns
- Always pass `include_participation=False` (already the adapter default)
- Add `gc.collect()` after each season's Parquet write to release memory
- For backfill, add a `--dry-run` flag that fetches one season first

**Warning signs:**
- Process killed by OOM killer with no error message
- Script hangs for 5+ minutes with no progress output
- System swap usage spikes during PBP ingestion

**Phase to address:**
Phase 1 (PBP backfill) -- verify per-season batching is enforced, add memory monitoring.

---

### Pitfall 3: Injury Data Source Is Dead After 2024

**What goes wrong:**
The nflverse injury data source died after the 2024 season. `import_injuries()` returns 404 errors for 2025. This is confirmed by [nflverse's data schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html): "data source died after the 2024 season." The existing Bronze layer has injuries for 2020-2024 only.

**Why it happens:**
The upstream NFL data source for injuries was discontinued. nflverse has no replacement. The `DATA_TYPE_SEASON_RANGES` in config.py currently says injuries go from 2009 to dynamic max (`get_max_season`), which is wrong for 2025+.

**How to avoid:**
- Update `DATA_TYPE_SEASON_RANGES["injuries"]` max to a static `2024` (not `get_max_season`)
- Backfill injuries for 2016-2019 (currently only have 2020-2024) while the API still serves historical data
- For 2025+ injury data, plan a separate source (e.g., Sleeper MCP injury status)
- Add a fallback warning in the ingestion script when a data type has a known dead end

**Warning signs:**
- HTTP 404 or empty DataFrame for injury season 2025
- Validation showing 0 rows returned for a season

**Phase to address:**
Phase 1 (existing data type backfill) -- fix season range, backfill 2016-2019, document the gap.

---

### Pitfall 4: Depth Chart Schema Change in 2025+

**What goes wrong:**
Starting in 2025, nflverse depth chart data uses ISO8601 timestamps instead of week-number assignments. This is confirmed by [nflverse's data schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html): "2025+ uses ISO8601 timestamps instead of week assignments." Code that filters by `week` column will silently return empty results for 2025+ data.

**Why it happens:**
The upstream data source changed format. The registry entry has `requires_week: False` (correct for fetching), but downstream consumers may assume a `week` column exists in the returned data.

**How to avoid:**
- When backfilling 2016-2024, validate that the `week` column exists in all returned DataFrames
- For 2025+, add a schema transformation that maps timestamps to approximate weeks
- Validate schema consistency across years BEFORE writing to storage
- Consider adding a `schema_version` metadata field

**Warning signs:**
- Missing `week` column in depth chart DataFrames for 2025+
- Downstream Silver transforms failing on `week` column lookups
- Schema validation warnings about unexpected columns

**Phase to address:**
Phase 2 (new data type ingestion) -- depth charts need special handling for schema evolution.

---

### Pitfall 5: GitHub Rate Limiting on Bulk Downloads

**What goes wrong:**
nfl-data-py downloads from `https://github.com/nflverse/nflverse-data/releases/`. GitHub rate limits unauthenticated requests to 60/hour and authenticated to 5,000/hour. A full backfill of 15 data types across 10 years is ~150+ individual downloads. PFR alone is 4 stat types x 2 frequencies x 8 seasons = 64 calls. Without auth tokens or delays, you hit 403 errors partway through.

**Why it happens:**
The existing `_safe_call` in the adapter returns an empty DataFrame on error but does NOT retry. A 403 from rate limiting looks the same as "no data exists" -- silent data gaps.

**How to avoid:**
- Set `GITHUB_TOKEN` environment variable (used by StatsPlayerAdapter and gh CLI; nfl-data-py v0.3.3 does not read this token) for authenticated GitHub API rate limits (5000/hr)
- Add a configurable delay between API calls (1-2 seconds) in the batch loop
- Add retry logic with exponential backoff for 403/429 responses
- Batch by data type (all seasons of PBP, then all seasons of NGS) rather than by season
- Log HTTP status codes, not just empty/non-empty DataFrame results

**Warning signs:**
- HTTP 403 or 429 errors in logs
- Empty DataFrames returned for seasons that should have data
- Ingestion speed degrading as the run progresses
- Successive data types returning empty after the first few succeed

**Phase to address:**
Phase 1 (pre-backfill) -- add rate limiting, retry logic, and GITHUB_TOKEN to adapter.

---

### Pitfall 6: Schema Drift Across Years for the Same Data Type

**What goes wrong:**
NFL data schemas are not stable across years. Known examples from this project:
- `snap_counts`: uses `offense_pct` (not `snap_pct`) and `player` (not `player_id`)
- `player_weekly`: uses `receiving_air_yards` (not `air_yards`)
- `player_seasonal`: has `wopr_x`/`wopr_y` merge artifacts from nfl-data-py joining
- PBP: `xpass`, `pass_oe`, `cpoe` may be absent in pre-2016 data
- Team abbreviations change: `OAK` -> `LV` (2020), `SD` -> `LAC` (2017), `STL` -> `LA` (2016)

When backfilling 2016-2025, early seasons may have fewer columns, different names, or different dtypes.

**Why it happens:**
The NFL adds tracking capabilities over time. nfl-data-py returns whatever the upstream source provides. Bronze layer stores raw data, but Parquet files with mismatched schemas across years cannot be trivially queried together.

**How to avoid:**
- Store each season as a separate Parquet file (already the pattern) -- do NOT concatenate across years
- Run `validate_data()` on each season's DataFrame independently
- Build a schema registry that records actual columns returned per (data_type, season) pair
- For PBP, always pass `columns=PBP_COLUMNS` to force consistent schema (missing columns become NaN)
- Maintain a team abbreviation mapping table for historical join resolution

**Warning signs:**
- `validate_data()` reporting missing required columns for early seasons
- Parquet read errors when loading files from different seasons into the same DataFrame
- Team abbreviation mismatches in joins (e.g., "OAK" in 2019 vs. "LV" in 2020)

**Phase to address:**
Phase 1 (before backfill) -- add per-season schema logging; Phase 3 (validation) -- cross-year schema comparison.

---

## Moderate Pitfalls

### Pitfall 7: QBR Weekly vs. Seasonal Filename Collision

**What goes wrong:**
QBR data comes in two frequencies: `weekly` and `seasonal`, both fetched via `import_qbr(frequency=...)`. If both are saved with the same filename pattern, one overwrites the other. The existing code handles this with `qbr_{frequency}_{ts}.parquet` (line 358-359 of `bronze_ingestion_simple.py`), but a batch backfill script might not replicate this logic.

**Why it happens:**
The QBR registry entry has no `sub_types` key (unlike NGS and PFR). The frequency distinction is handled in filename logic, not path structure -- a one-off pattern easy to forget.

**How to avoid:**
- Already solved in `bronze_ingestion_simple.py` -- verify any new batch script replicates this
- Consider restructuring QBR path to `qbr/{frequency}/season={season}/` for consistency with NGS/PFR
- Test by ingesting both weekly and seasonal QBR for a single season, verify two distinct files

**Warning signs:**
- Only one QBR file per season when there should be two
- QBR seasonal data unexpectedly having `week` columns

**Phase to address:**
Phase 2 (QBR ingestion) -- verify both frequencies produce distinct files.

---

### Pitfall 8: NGS Data Only Available from 2016 -- Silent Empty Returns

**What goes wrong:**
NGS (Next Gen Stats) data only exists from 2016 onward. The NFL's RFID tracking system was deployed in 2016. Requesting earlier seasons returns empty DataFrames with no error. The `DATA_TYPE_SEASON_RANGES` correctly shows `ngs: (2016, get_max_season)`, and `_filter_seasons` silently skips invalid seasons with only a log warning.

**Why it happens:**
Different data types have different availability windows. A batch script that tries 2010-2025 for everything will get empty results for NGS 2010-2015 with no clear error.

**How to avoid:**
- The existing `_filter_seasons` + `DATA_TYPE_SEASON_RANGES` validation is correct
- Add a per-type summary at the end of batch ingestion showing seasons attempted vs. seasons with data
- Validate expected row counts are non-zero for each season
- NGS has 3 sub-types (passing, rushing, receiving) -- each needs a separate ingestion call

**Warning signs:**
- Empty Parquet files (0 rows) written for seasons before availability window
- Batch completion reporting fewer seasons than expected with no error

**Phase to address:**
Phase 2 (NGS ingestion) -- validate availability window, add summary reporting.

---

### Pitfall 9: Snap Counts Adapter Has Unique (season, week) Signature

**What goes wrong:**
Every adapter method except `fetch_snap_counts` takes `seasons: List[int]`. `fetch_snap_counts` takes `(season: int, week: int)` -- two positional ints. A batch script that generically calls `adapter.method(seasons=[s])` will break for snap counts.

**Why it happens:**
The underlying `nfl.import_snap_counts()` takes `(season, week)` not a list. The adapter mirrors this, and `_build_method_kwargs` has special-case handling (line 186-187 of `bronze_ingestion_simple.py`). For 10-year backfill, this means 10 seasons x 18 weeks = 180 individual API calls.

**How to avoid:**
- The existing special-case in `_build_method_kwargs` handles this correctly
- For backfill, snap counts need nested loops (season x week), not just season-level iteration
- Add progress reporting: "Ingesting snap_counts season 2016 week 5/18..."
- Consider if weekly granularity is needed for all 10 years or just recent seasons

**Warning signs:**
- `TypeError: fetch_snap_counts() got an unexpected keyword argument 'seasons'`
- Snap counts returning all weeks when only one was requested

**Phase to address:**
Phase 1 (existing type backfill) -- snap counts need week-level loop, not just season-level.

---

### Pitfall 10: Disk Space Exhaustion During Full Backfill

**What goes wrong:**
The current Bronze layer is 7 MB across 31 files. Full backfill estimate:
- PBP: ~50 MB/season x 10 seasons = ~500 MB
- NGS: ~5 MB/season x 3 types x 10 seasons = ~150 MB
- PFR: ~2 MB/season x 4 types x 2 frequencies x 8 seasons = ~128 MB
- Existing types extended: ~50 MB
- All other new types: ~50 MB
- **Estimated total: 850 MB to 1.2 GB** (100x increase from current 7 MB)

Each ingestion run creates a NEW timestamped file. Re-running the backfill doubles disk usage.

**Why it happens:**
The timestamped file convention preserves history but means re-runs create duplicates, not updates.

**How to avoid:**
- Before backfill, verify ~2 GB free disk space
- Add a `--replace` flag that removes old files before writing
- Or add a dedup/cleanup step that keeps only the latest file per partition
- Monitor disk usage during long batch runs

**Warning signs:**
- `OSError: [Errno 28] No space left on device`
- Multiple timestamped files in the same partition directory
- Disk usage growing faster than expected

**Phase to address:**
Phase 1 (pre-backfill) -- disk space check and dedup strategy.

---

### Pitfall 11: Column Name Inconsistencies Across Data Types

**What goes wrong:**
nfl-data-py uses different column naming conventions across functions:
- Player ID: `player_id`, `gsis_id`, `pfr_player_id`, `ngs_player_id`, `pfr_id`, `player_gsis_id`
- Team: `team`, `recent_team`, `team_abbr`, `posteam`, `club_code`
- Name: `player_name`, `player`, `passer_player_name`, `player_display_name`, `pfr_player_name`, `full_name`

**Why it happens:**
Each upstream source (NFL NGS, PFR, ESPN) uses its own schema. nfl-data-py passes these through without normalization. This is correct for Bronze (raw data), but creates join headaches at Silver.

**How to avoid:**
- At Bronze layer: store as-is (do not rename columns)
- Document canonical join keys per data type in the data dictionary
- At Silver layer: build explicit column mapping transforms
- Standardize on GSIS `player_id` as the canonical join key

**Warning signs:**
- `KeyError` in Silver transformations
- Columns with all NaN values after joins
- Duplicate rows from join key mismatches

**Phase to address:**
Phase 2 (as each new data type is added) and Phase 3 (Silver integration).

---

### Pitfall 12: NGS and PFR Parameter Name Inconsistencies

**What goes wrong:**
- `import_ngs_data()` uses `stat_type` with full words: `"passing"`, `"rushing"`, `"receiving"`
- `import_weekly_pfr()` / `import_seasonal_pfr()` use `s_type` with abbreviations: `"pass"`, `"rush"`, `"rec"`, `"def"`
- PyPI documentation was historically incorrect about the NGS parameter name ([issue #34](https://github.com/nflverse/nfl_data_py/issues/34))

**Why it happens:**
nfl-data-py wraps different upstream sources with different conventions and never normalized them.

**How to avoid:**
- The existing adapter handles this correctly: `fetch_ngs` passes `stat_type=`, `fetch_pfr_weekly` passes `s_type=`
- The registry in `bronze_ingestion_simple.py` uses `sub_types` lists and maps the correct keyword arg
- Verify against actual nfl-data-py source code, not PyPI docs
- Do NOT concatenate different stat types into one DataFrame (their schemas differ)

**Warning signs:**
- `TypeError` from wrong parameter name
- DataFrames with mixed schemas if stat types are concatenated

**Phase to address:**
Phase 2 (NGS and PFR ingestion).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip validation on backfill | 2x faster ingestion | Corrupt data undetected | Never -- validation is warn-only, negligible cost |
| Load all PBP columns | Simpler code | 3x memory usage, schema instability | Never -- always use `PBP_COLUMNS` |
| Skip `gc.collect()` between PBP seasons | Marginally faster | OOM on machines with <16 GB RAM | Only if >32 GB RAM |
| Hardcode season ranges | Quick fix | Breaks next year | Never -- use `DATA_TYPE_SEASON_RANGES` |
| Ignore empty DataFrames | No error handling | Silent data gaps | Never -- log and flag |
| No delay between API calls | Faster backfill | 403 rate limit hits | Never -- add 1-2s delay |
| Single run with no dedup | Quick completion | Duplicate files on re-run | MVP only -- add dedup before second run |
| Stay on nfl-data-py forever | No migration work | Dead dependency, frozen on Python 3.9 | Acceptable for this milestone only |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `import_rosters()` | Using the broken function | Use `import_seasonal_rosters()` -- fixed in adapter |
| `import_ngs_data()` | Passing `years` as first positional arg | Use keyword: `stat_type="passing", years=[2024]` |
| `import_qbr()` | Forgetting `frequency` param | Defaults to `"weekly"` -- pass explicitly for seasonal |
| `import_pbp_data()` | Setting `include_participation=True` | Causes OOM -- always `False` |
| `import_snap_counts()` | Passing seasons as list | Takes `(season, week)` positional ints |
| `import_injuries()` | Requesting 2025 data | Data source dead after 2024 -- will 404 |
| `import_depth_charts()` | Assuming `week` column exists in 2025+ | 2025+ uses ISO timestamps instead |
| GitHub API calls (StatsPlayerAdapter, gh CLI) | No auth token | Set `GITHUB_TOKEN` for 5000/hr vs. 60/hr limit (nfl-data-py does not use it) |
| numpy version | Upgrading to 2.x | Pin `numpy<2` -- nfl-data-py uses deprecated `np.float_` |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Multi-season PBP load | OOM kill, process hangs | One season at a time + `gc.collect()` | >2 seasons on 8 GB RAM |
| No delay between API calls | 403 errors mid-backfill | 1-2s delay + GITHUB_TOKEN | >60 calls/hr unauthenticated |
| Full-column PBP reads | 3x slower, 3x memory | Always pass `columns=PBP_COLUMNS` | Any PBP load |
| Snap counts 10yr x 18wk | 180 API calls, ~30 min | Accept sequential, add progress bar | Always slow |
| Re-running backfill | Disk fills 2x | Dedup before re-run or `--replace` flag | Second run of any backfill |
| All data types in one batch | Rate limited at ~60 calls | Split into multiple runs or add GITHUB_TOKEN | >60 unauthenticated calls |

## "Looks Done But Isn't" Checklist

- [ ] **PBP backfill:** Verify all 103 curated columns present per season -- early seasons may lack `xpass`, `pass_oe`, `cpoe`
- [ ] **NGS backfill:** Verify all 3 sub-types (passing, rushing, receiving) ingested per season, starting from 2016 only
- [ ] **PFR backfill:** Verify 4 stat types x 2 frequencies = 8 combinations per season, starting from 2018 only
- [ ] **QBR backfill:** Verify BOTH weekly AND seasonal files exist per season (frequency-prefixed filenames)
- [ ] **Injuries backfill:** Confirm 2025 is NOT attempted (data source dead) -- max is 2024; backfill 2016-2019
- [ ] **Depth charts 2025:** Confirm schema change (ISO timestamps vs. weeks) is handled or documented
- [ ] **Snap counts:** Confirm week-level loop ran for all 18 weeks per season, not just week 1
- [ ] **Team abbreviations:** Confirm OAK/SD/STL data has correct historical abbreviations in each season
- [ ] **Disk space:** Confirm total Bronze is ~1 GB (not 2+ GB from duplicates)
- [ ] **Validation:** Confirm `validate_data()` ran on every file with required columns defined for all 15 types
- [ ] **Rate limiting:** Confirm no 403 errors in logs, GITHUB_TOKEN was set
- [ ] **Dependencies:** Confirm `numpy<2` and `nfl-data-py==0.3.3` pinned in requirements.txt

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| PBP OOM crash | LOW | Kill process, restart with single-season mode, add `gc.collect()` |
| Duplicate files from re-run | LOW | Script to find and remove all but latest timestamp per partition |
| Schema mismatch across years | MEDIUM | Re-validate each file, build schema registry, document gaps |
| Rate limiting (403s) | LOW | Wait 1 hour, set GITHUB_TOKEN, re-run with delays |
| Injury 2025 data missing | LOW | Accept gap, update season range to static 2024 |
| Depth chart schema change | MEDIUM | Add transformation step for 2025+, re-ingest with new schema handling |
| Numpy 2.0 breakage | LOW | `pip install "numpy<2"` -- crash happens before write, no data corruption |
| Disk full during backfill | MEDIUM | Free space, dedup existing files, restart from last successful season |
| Wrong import_rosters | LOW | Already fixed in adapter -- re-run with correct function |
| GITHUB_TOKEN not set | LOW | Set token, re-run failed data types only |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| nfl-data-py archived | Pre-work | Pin versions, verify all imports work |
| PBP memory explosion | Phase 1 (PBP) | Monitor RSS during ingestion, verify <4 GB peak |
| Injury data dead after 2024 | Phase 1 (existing backfill) | Update config range, verify 2016-2024 ingested, 2025 skipped |
| Depth chart schema change | Phase 2 (new types) | Compare 2024 vs 2025 schemas, add migration if needed |
| GitHub rate limiting | Phase 1 (pre-backfill) | Add delays, set GITHUB_TOKEN, verify no 403s in logs |
| Schema drift across years | Phase 1 + Phase 3 | Per-season schema log; cross-year comparison report |
| QBR filename collision | Phase 2 (QBR) | Verify two files per season (weekly + seasonal) |
| NGS availability window | Phase 2 (NGS) | Verify 2016 is earliest with data, log empty returns |
| Snap counts unique signature | Phase 1 (existing backfill) | Verify week-level loop, check 180 files created |
| Disk space exhaustion | Phase 1 (pre-backfill) | Check disk space, add dedup, estimate total size |
| Column name inconsistencies | Phase 2 + Phase 3 | Document join keys, validate at Silver layer |
| NGS/PFR param differences | Phase 2 | Already handled in adapter -- verify via test |

## Sources

- [nfl-data-py GitHub (archived)](https://github.com/nflverse/nfl_data_py) -- confirmed archived Sep 25, 2025
- [nflreadpy (successor)](https://nflreadpy.nflverse.com/) -- official replacement, Polars-based
- [nflverse Data Schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html) -- availability windows, injury death, depth chart schema change
- [nfl-data-py PyPI](https://pypi.org/project/nfl-data-py/) -- function signatures
- [nfl-data-py Issue #98 (NumPy 2.0)](https://github.com/nflverse/nfl_data_py/issues/98) -- np.float_ incompatibility
- [nfl-data-py Issue #34 (docs error)](https://github.com/nflverse/nfl_data_py/issues/34) -- stat_type param mislabeled
- [nflverse-data releases](https://github.com/nflverse/nflverse-data/releases) -- data hosting, download source
- [nflverse NGS data repo](https://github.com/nflverse/ngs-data) -- NGS data sourcing details
- Project codebase: `src/nfl_data_adapter.py`, `src/config.py`, `scripts/bronze_ingestion_simple.py`, `src/nfl_data_integration.py`
- Project memory: known quirks from v1.0 (snap_counts schema, import_rosters bug, PBP participation OOM)

---
*Pitfalls research for: NFL Bronze data backfill (9 new types, 10 years)*
*Researched: 2026-03-08*
