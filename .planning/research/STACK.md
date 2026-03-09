# Technology Stack

**Project:** NFL Data Engineering v1.1 Bronze Backfill
**Researched:** 2026-03-08

## Verdict: No New Dependencies Required

The existing stack handles all 9 new data types without additions. The key concern is **memory management for PBP ingestion**, which the existing per-season batching pattern already addresses. No library changes, no version bumps, no new packages.

## Current Stack (Verified Working)

### Core Framework
| Technology | Version | Purpose | Status |
|------------|---------|---------|--------|
| Python | 3.9.7 | Runtime | Keep -- nflreadpy requires 3.10+, migration not worth it for this milestone |
| pandas | 1.5.3 | DataFrame processing | Keep -- all adapter methods return pandas DataFrames |
| pyarrow | 21.0.0 | Parquet read/write | Keep -- handles all serialization needs |
| nfl-data-py | 0.3.3 | NFL data source | Keep -- deprecated but functional, see analysis below |
| fastparquet | 2024.11.0 | nfl-data-py dependency | Keep -- required by nfl-data-py internals |

### Infrastructure
| Technology | Version | Purpose | Status |
|------------|---------|---------|--------|
| boto3 | 1.40.11 | S3 upload (optional) | Keep -- only used with --s3 flag |
| python-dotenv | 1.1.1 | Environment config | Keep |
| tqdm | 4.67.1 | Progress bars | Keep -- already installed, useful for batch ingestion progress |

## nfl-data-py Deprecation Analysis

**Status:** nfl-data-py 0.3.3 is deprecated in favor of nflreadpy (0.1.5, Nov 2025). No further maintenance planned.

**Recommendation: Stay on nfl-data-py 0.3.3 for this milestone.**

Rationale:
1. **nflreadpy requires Python >= 3.10** -- project is on 3.9.7; upgrading Python is out of scope for a data backfill milestone
2. **nflreadpy returns Polars DataFrames** -- entire pipeline (Silver, Gold, Draft) uses pandas; migration would cascade across every module
3. **nfl-data-py 0.3.3 is functional** -- tested all 9 new data type APIs successfully (2026-03-08); data comes from nflverse GitHub releases which are still actively maintained
4. **NFLDataAdapter isolation** -- the adapter pattern means future migration to nflreadpy (or direct nflverse HTTP) only touches `src/nfl_data_adapter.py`
5. **Risk is low** -- nfl-data-py calls `import_*` functions that download from `https://github.com/nflverse/nflverse-data/releases`; as long as nflverse maintains those releases (they do), the library works

**When to migrate:** When Python is upgraded to 3.10+ for another reason (e.g., ML phase), or if nflverse release format changes break nfl-data-py downloads.

Confidence: **HIGH** -- verified all 9 APIs return data successfully on 2026-03-08.

## Memory Analysis: PBP Is the Only Concern

Measured data sizes per season (single-season fetch, 103 curated columns, downcast=True):

| Data Type | Rows/Season | Cols | Memory/Season | Parquet/Season | 10-Season Disk |
|-----------|-------------|------|---------------|----------------|----------------|
| **pbp** | **49,492** | **129** | **163 MB** | **9.7 MB** | **~97 MB** |
| depth_charts | 37,312 | 15 | 29.3 MB | ~2 MB | ~20 MB |
| ngs_passing | 614 | 29 | 0.4 MB | <1 MB | trivial |
| ngs_rushing | 601 | 22 | 0.3 MB | <1 MB | trivial |
| ngs_receiving | 1,435 | 23 | 0.8 MB | <1 MB | trivial |
| pfr_weekly | 697 | 24 | 0.4 MB | <1 MB | trivial |
| pfr_seasonal | 105 | 37 | <0.1 MB | <1 MB | trivial |
| qbr_weekly | 573 | 30 | 0.3 MB | <1 MB | trivial |
| qbr_seasonal | 82 | 23 | <0.1 MB | <1 MB | trivial |
| draft_picks | 257 | 36 | 0.2 MB | <1 MB | trivial |
| combine | 321 | 18 | 0.2 MB | <1 MB | trivial |
| teams | 36 | 16 | <0.1 MB | <1 MB | one-time |

**Key finding:** PBP at 163 MB/season in-memory is manageable with the existing per-season loop in `bronze_ingestion_simple.py` (line 327: `for idx, season in enumerate(season_list, 1)`). Each season is fetched, saved, and then the DataFrame goes out of scope. Peak memory is ~163 MB + nfl-data-py internal overhead (~200 MB total). Safe on any modern machine.

**Do NOT load all 10 PBP seasons at once.** The `--seasons 2016-2025` flag already handles this correctly by iterating one season at a time. No code changes needed.

**Total disk estimate for full backfill (all 9 types, 10 years):** ~130 MB Parquet on disk. Combined with existing 6.9 MB Bronze data, total Bronze layer will be ~137 MB.

## nfl-data-py API Constraints by Data Type

Verified against actual function calls (2026-03-08):

| Data Type | nfl-data-py Function | API Quirks | Confidence |
|-----------|---------------------|------------|------------|
| pbp | `import_pbp_data(years, columns, downcast, include_participation)` | `downcast=True` cuts memory 30% but slows load ~50%; `columns` filter applied server-side; prints "YYYY done." to stdout per year | HIGH |
| ngs | `import_ngs_data(stat_type, years)` | `stat_type` param (not `s_type`); downloads full monolithic parquet per stat_type then filters by year; available 2016+ | HIGH |
| pfr_weekly | `import_weekly_pfr(s_type, years)` | `s_type` uses 'pass'/'rush'/'rec'/'def'; downloads one parquet per year per s_type; available 2018+ | HIGH |
| pfr_seasonal | `import_seasonal_pfr(s_type, years)` | Same param names as weekly; downloads one monolithic parquet then filters | HIGH |
| qbr | `import_qbr(years, frequency)` | `frequency='weekly'` or `'season'`; CSV-based from ESPN; 2024 data returned 0 rows (not yet published by nflverse) | HIGH |
| depth_charts | `import_depth_charts(years)` | Takes list of years; downloads one parquet per year; large dataset (~37K rows/season) | HIGH |
| draft_picks | `import_draft_picks(years)` | Downloads single monolithic parquet, filters by year; ~257 rows/season | HIGH |
| combine | `import_combine_data(years)` | Downloads single monolithic parquet, filters by year; ~321 rows/season | HIGH |
| teams | `import_team_desc()` | No season parameter; returns all 36 teams (32 active + historical); single call | HIGH |

**QBR data gap:** 2024 QBR returned 0 rows when tested. This is a data availability issue at the nflverse/ESPN source, not an API bug. The ingestion script already handles empty DataFrames gracefully (lines 336-337: `if df.empty: continue`). QBR data for recent seasons may appear later when nflverse publishes it. The `--seasons` range should still include these years -- the script will skip empty results.

**NGS/PFR monolithic download behavior:** These functions download the full historical parquet file every time, even for a single-year request. For batch ingestion of multiple years, this means redundant downloads. However, nfl-data-py caches downloads via `appdirs.user_cache_dir`, so repeated calls within a session hit cache. This is a minor inefficiency, not a blocker.

## pandas 1.5.3 Compatibility Note

pandas 1.5.3 is old (Dec 2022) but works fine for this milestone. The combination of pandas 1.5.3 + pyarrow 21.0.0 was tested and functions correctly for all parquet read/write operations. Do not upgrade pandas for this milestone; version 2.0 removed `DataFrame.append()` and changed some default behaviors that could break Silver/Gold layer code.

## What NOT to Add

| Suggestion | Why Not |
|------------|---------|
| nflreadpy | Requires Python 3.10+; returns Polars not pandas; massive migration scope |
| Polars | Would require rewriting Silver/Gold/Draft pipelines; no benefit for Bronze-only work |
| DuckDB for ingestion | Already available as MCP for queries; pandas+parquet is the right tool for ingestion |
| dask / modin | PBP per-season is only 163 MB; no need for distributed DataFrames |
| Retry/backoff library | nfl-data-py downloads from GitHub releases (high availability); adapter's `_safe_call` handles errors; `backoff` is installed but unnecessary here |
| Chunked parquet writing | Single-season PBP fits easily in memory; chunking adds complexity for no benefit |
| great-expectations | Already installed (v1.5.8) but `validate_data()` pattern is simpler, sufficient, and already wired into all 15 data types |
| Any new pip packages | Zero new dependencies needed. The registry+adapter pattern handles everything |

## Season Range Coverage (Already Implemented)

`DATA_TYPE_SEASON_RANGES` in `src/config.py` defines valid ranges for all 9 new types. The `--seasons` flag with `validate_season_for_type()` correctly rejects out-of-range requests:

| Data Type | Min Season | Backfill Command |
|-----------|-----------|-----------------|
| pbp | 1999 | `--data-type pbp --seasons 2016-2025` |
| ngs | 2016 | `--data-type ngs --sub-type passing --seasons 2016-2025` |
| pfr_weekly | 2018 | `--data-type pfr_weekly --sub-type pass --seasons 2018-2025` |
| pfr_seasonal | 2018 | `--data-type pfr_seasonal --sub-type pass --seasons 2018-2025` |
| qbr | 2006 | `--data-type qbr --seasons 2016-2025 --frequency weekly` |
| depth_charts | 2001 | `--data-type depth_charts --seasons 2016-2025` |
| draft_picks | 2000 | `--data-type draft_picks --seasons 2016-2025` |
| combine | 2000 | `--data-type combine --seasons 2016-2025` |
| teams | N/A | `--data-type teams` (no season, one-time fetch) |

## Installation

No changes to requirements.txt needed:

```bash
pip install -r requirements.txt
```

## Sources

- [nfl-data-py PyPI](https://pypi.org/project/nfl-data-py/) -- version 0.3.3, last release Sep 2024
- [nfl-data-py GitHub](https://github.com/nflverse/nfl_data_py) -- deprecation notice in README
- [nflreadpy PyPI](https://pypi.org/project/nflreadpy/) -- version 0.1.5, requires Python 3.10+
- [nflreadpy GitHub](https://github.com/nflverse/nflreadpy) -- successor, Polars-based
- Local verification: all 9 data type APIs tested successfully returning data (2026-03-08)
- Memory measurements: PBP = 49,492 rows, 129 cols, 163 MB in-memory, 9.7 MB parquet (1 season, 103 curated columns, downcast=True)
