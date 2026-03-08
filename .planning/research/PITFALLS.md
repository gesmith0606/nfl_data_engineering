# Domain Pitfalls

**Domain:** NFL data pipeline expansion (Bronze layer, 9+ new nfl-data-py data types)
**Researched:** 2026-03-08

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: nfl-data-py Is Archived -- Dependency Is Dead

**What goes wrong:** The project depends entirely on `nfl_data_py==0.3.3` for all data ingestion. The nfl-data-py repository was [archived by the nflverse team on September 25, 2025](https://github.com/nflverse/nfl_data_py) and is now read-only. No bug fixes, no new season support, no Python version updates. The replacement is [nflreadpy](https://github.com/nflverse/nflreadpy), which uses Polars instead of pandas and has a different API (`load_*` instead of `import_*`).

**Why it happens:** The project pinned `nfl_data_py==0.3.3` and never evaluated successor libraries. The archived library still works for now because it pulls data from nflverse GitHub repos, but those data endpoints could change without the library being updated to match.

**Consequences:**
- Any nflverse data format change breaks all ingestion silently (returns empty DataFrames or crashes)
- Python 3.13+ is already broken (known issue #122, never fixed)
- NumPy 2.0 breaks `import_pbp_data` with `AttributeError: np.float_` (issue #98, never fixed)
- Adding 9 new data types deepens the dependency on a dead library
- Future migration becomes harder the more code depends on nfl-data-py's API

**Warning signs:**
- `pip install nfl-data-py` starts showing deprecation warnings
- NumPy or Python upgrades break imports
- nflverse GitHub data URLs change and nfl-data-py cannot follow them

**Prevention:**
- **Phase 1 decision:** Either (a) migrate to nflreadpy before expanding, or (b) expand on nfl-data-py with an explicit adapter layer that isolates the library calls, making future migration a single-module swap
- Option (b) is pragmatic: nfl-data-py still works today on Python 3.9 with NumPy 1.x, and the nflverse data repos it reads from are the same ones nflreadpy reads. But build the adapter now
- Add a thin `DataSourceAdapter` class that wraps all `nfl.import_*` calls. New data types go through the adapter. When migration happens, only the adapter changes
- Pin `numpy<2.0` explicitly in requirements.txt as a safety measure

**Detection:** Monitor nflverse data repo structure for breaking changes. Pin the library version (already done). Track nflreadpy releases for feature parity.

**Confidence:** HIGH -- archived status confirmed via GitHub, nflreadpy is the official successor per nflverse.

**Phase:** Address in Phase 1 (before adding any new data types). Either migrate or build the adapter layer.

---

### Pitfall 2: import_rosters vs import_seasonal_rosters

**What goes wrong:** `nfl.import_rosters()` exists in nfl-data-py but returns incorrect or incomplete data. The correct function is `nfl.import_seasonal_rosters()`. This is already known and fixed in the current codebase (`fetch_rosters` on line 265 of `nfl_data_integration.py`), but anyone adding new fetch methods or writing tests may accidentally use the wrong function. The same trap pattern exists across other nfl-data-py functions.

**Why it happens:** Both functions exist, both accept the same parameters, and the naming suggests `import_rosters` is the canonical one. The nfl-data-py documentation does not clearly warn about this. Similar confusing function pairs may exist for new data types.

**Consequences:** Roster data is wrong or incomplete, causing downstream join failures in Silver/Gold layers. Player-team mappings break, draft tool shows stale rosters.

**Warning signs:**
- DataFrame has fewer rows than expected
- Missing columns that documentation says should exist
- Player counts per team are suspiciously low

**Prevention:**
- Document this prominently in the codebase (add a comment in `nfl_data_integration.py` near the import)
- Add a linting rule or grep check in CI: flag any use of `nfl.import_rosters(` (without `seasonal_`)
- If building a `DataSourceAdapter`, make the adapter the only place `nfl.*` functions are called
- For every new `import_*` function, verify the correct function signature against the GitHub source code, not the PyPI documentation

**Detection:** Compare row counts against known NFL data constraints (32 teams, 53-man rosters = ~1,700 rows per season)

**Confidence:** HIGH -- confirmed in project memory and existing code fix.

**Phase:** Address in Phase 1 (documentation + guard) since the fix already exists but lacks enforcement.

---

### Pitfall 3: Play-by-Play Data Is 100x Larger Than Current Bronze Layer

**What goes wrong:** The current Bronze layer is 7 MB across 31 files. A single season of PBP data is approximately 50,000 rows with 390 columns -- roughly 150-300 MB in memory per season. Loading 6 seasons (2020-2025) simultaneously would consume 1-2 GB of RAM. The existing pipeline pattern of "fetch all seasons at once, filter later" will cause OOM kills.

**Why it happens:** The current data types (player_weekly, snap_counts, etc.) are player-aggregated and small. PBP is play-level: every snap, penalty, timeout, and two-minute warning for every game. Developers who have only worked with the small data types will apply the same patterns.

**Consequences:**
- `MemoryError` or OOM kills during ingestion
- GitHub Actions runners (7GB limit) will crash on multi-season PBP loads
- Local disk fills up (6 seasons of PBP parquet = 500+ MB)
- Slow ingestion (minutes vs. seconds per season)
- Existing `download_latest_parquet()` reads full files into memory -- fine for 1 MB, dangerous for 300 MB

**Warning signs:**
- Ingestion script hangs for 5+ minutes on a single data type
- System swap usage spikes
- `MemoryError` or process killed without error message

**Prevention:**
- Process PBP one season at a time, never all seasons in a single DataFrame
- Use `downcast=True` parameter on `import_pbp_data()` to convert float64 to float32 (~30% memory reduction)
- Partition PBP parquet files by season AND week (not just season) to keep individual files manageable
- For Silver/Gold processing of PBP, use DuckDB for SQL-on-Parquet instead of loading into pandas (already configured as MCP)
- Consider using `nfl.cache_pbp()` for local caching (4-5x faster on subsequent loads)
- Do NOT filter columns at Bronze layer -- store the full dataset (Medallion principle: Bronze = raw). Filter at Silver.

**Detection:** Monitor memory during test ingestion of a single PBP season before scaling to multi-season.

**Confidence:** HIGH -- PBP data size is well-documented in nflverse community (~50K rows x 390 cols per season).

**Phase:** Address in Phase 1 (PBP ingestion design). Must be solved before PBP is added as a data type.

---

### Pitfall 4: Different Data Types Have Different Season Ranges

**What goes wrong:** The current code uses a single `available_seasons = range(1999, 2026)` for all data types. But each nfl-data-py function has different historical availability:

| Data Type | Earliest Season | Notes |
|-----------|----------------|-------|
| Schedules | 1999 | Full coverage |
| PBP | 1999 | Full coverage, but pre-2006 is sparse |
| Player weekly | 1999 | Quality improves after 2010 |
| NGS (passing/rushing/receiving) | **2016** | Next Gen Stats tracking started 2016 |
| PFR advanced (pass/rush/rec) | **2018** | Pro Football Reference advanced stats |
| Combine | ~2000 | Varies by year |
| Draft picks | ~1980 | Historical draft data |
| QBR | ~2006 | ESPN metric, limited history |
| Depth charts | ~2001 | Varies, some years incomplete |
| Win totals / SC lines | ~2020 | Betting data, very recent only |
| Officials | ~2015 | Referee data |

**Why it happens:** The current `NFLDataFetcher` applies the same season validation to every data type. When someone requests NGS data for 2015, it passes validation but the API returns an empty DataFrame silently (no error raised).

**Consequences:**
- Empty DataFrames that pass validation (row_count = 0 is caught, but 3 rows when you expected 500 is not)
- Misleading "data ingested" messages for seasons that don't exist
- Downstream Silver/Gold layers produce garbage from incomplete data
- Backfill scripts that loop over 2020-2025 will silently produce empty data for types that start later

**Warning signs:**
- Empty DataFrames from fetch calls with no error raised
- High null percentages in joined datasets
- Inconsistent season coverage across Bronze tables

**Prevention:**
- Add per-data-type season ranges in `src/config.py`:
  ```python
  DATA_TYPE_SEASONS = {
      'ngs_passing': range(2016, 2026),
      'ngs_rushing': range(2016, 2026),
      'pfr_weekly': range(2018, 2026),
      'win_totals': range(2020, 2026),
      ...
  }
  ```
- Validate requested seasons against the data-type-specific range, not the global range
- Add a minimum row count assertion per data type per season (e.g., NGS passing should have 32+ rows per season)
- Document the source of each data type (NFL NGS, PFR, ESPN, PFF) and its coverage window

**Detection:** Ingested data with suspiciously few rows. Empty or near-empty parquet files. Season gaps in Silver layer aggregations.

**Confidence:** MEDIUM -- NGS starting at 2016 and PFR from 2018 confirmed via nflverse docs. Other ranges are approximate and need verification against actual API responses.

**Phase:** Address in Phase 1 (config + validation) before ingesting any new data types.

---

## Moderate Pitfalls

### Pitfall 5: Column Name Inconsistencies Across Data Types

**What goes wrong:** nfl-data-py uses different column naming conventions across functions. The project already hit this with `receiving_air_yards` vs `air_yards`, `offense_pct` vs `snap_pct`, and `player` vs `player_id`. Adding 9 new data types introduces more naming conflicts:

- Player ID: `player_id`, `gsis_id`, `pfr_player_id`, `ngs_player_id`, `pfr_id`
- Team: `team`, `recent_team`, `team_abbr`, `posteam`
- Name: `player_name`, `player`, `passer_player_name`, `player_display_name`

**Why it happens:** Each upstream data source (NFL NGS, PFF, PFR, ESPN) uses its own schema. nfl-data-py passes these through without normalization.

**Prevention:**
- Define a canonical column schema in `src/config.py` for each data type
- Build column mapping into the fetch layer (not the Silver transformation)
- Add schema validation assertions immediately after fetch: assert expected columns exist before writing to Bronze
- Standardize on `player_id` (GSIS ID) as the canonical join key and map all other identifiers to it

**Detection:** `KeyError` exceptions in Silver transformations. Columns with all NaN values after joins.

**Confidence:** HIGH -- multiple instances already documented in CONCERNS.md.

**Phase:** Phase 1 (schema registry) and ongoing for each new data type.

---

### Pitfall 6: NGS and PFR Functions Require stat_type Parameter

**What goes wrong:** Several nfl-data-py functions require a `stat_type` parameter that splits a single "data type" into 3 separate API calls:

- `import_ngs_data(stat_type, years)` -- stat_type: `"passing"`, `"rushing"`, `"receiving"`
- `import_seasonal_pfr(s_type, years)` -- s_type: `"pass"`, `"rush"`, `"rec"`
- `import_weekly_pfr(s_type, years)` -- s_type: `"pass"`, `"rush"`, `"rec"`

Note the inconsistencies:
- NGS uses full words (`"passing"`, `"rushing"`, `"receiving"`), PFR uses abbreviations (`"pass"`, `"rush"`, `"rec"`)
- Parameter name differs: `stat_type` vs `s_type`
- PyPI documentation was historically incorrect about the NGS parameter name (documented as `columns` when it should be `stat_type` -- see issue #34)

**Why it happens:** nfl-data-py wraps different upstream data sources with different conventions and never normalized them.

**Prevention:**
- Create three separate CLI data types per function: `ngs_passing`, `ngs_rushing`, `ngs_receiving`, `pfr_pass`, `pfr_rush`, `pfr_rec`
- Do NOT concatenate the three stat types into one DataFrame (their schemas differ: passing has `avg_time_to_throw`, rushing has `rush_yards_over_expected`)
- Store as separate Parquet files with the stat_type in the S3 key
- Verify parameter names against the actual nfl-data-py source code, not PyPI docs

**Detection:** `TypeError` from missing stat_type. DataFrames with mixed schemas if someone concatenates.

**Confidence:** HIGH -- confirmed via PyPI documentation and GitHub issue #34.

**Phase:** Phase 2 (when implementing NGS and PFR fetch methods).

---

### Pitfall 7: Hardcoded Season Upper Bound Will Block 2026 Data

**What goes wrong:** `NFLDataFetcher.available_seasons` is hardcoded as `range(1999, 2026)`, and `validate_data()` line 365 rejects seasons > 2025. The draft assistant defaults to `--season 2026`, which would be filtered out. Adding 9 new data types without fixing this means none of them will work for the current season.

**Prevention:**
- Replace `range(1999, 2026)` with `range(1999, datetime.date.today().year + 1)` or a config constant
- Fix the validation check on line 365 to use the same dynamic range
- Add a test that verifies the current year is always valid

**Detection:** Fetch calls for 2026 returning "No valid seasons provided" error.

**Confidence:** HIGH -- confirmed in code and CONCERNS.md.

**Phase:** Phase 1 (prerequisite fix before any new data types).

---

### Pitfall 8: No Local-First Support in Bronze Ingestion Script

**What goes wrong:** The current `bronze_ingestion_simple.py` requires AWS credentials and fails immediately if they are missing (line 90-92: `return 1`). Silver and Gold scripts have been updated for local-first operation, but Bronze ingestion has not. Since AWS credentials are expired, adding 9 new data types to this script means none of them can be ingested.

**Prevention:**
- Add local file output to `bronze_ingestion_simple.py`: write parquet to `data/bronze/{dataset}/season={YYYY}/week={WW}/`
- Follow the same pattern used in `silver_player_transformation.py` and `generate_projections.py`
- Add `--no-s3` flag or auto-detect invalid credentials and fall back to local
- S3 upload becomes optional, not required

**Detection:** Bronze ingestion failing with "Missing AWS credentials" before any data is fetched.

**Confidence:** HIGH -- confirmed in code review.

**Phase:** Phase 1 (prerequisite fix).

---

### Pitfall 9: Validation Only Checks Required Columns for 8 Known Types

**What goes wrong:** `validate_data()` has a hardcoded `required_columns` dict with 8 entries (lines 330-338). Adding 9 new data types without updating this dict means validation returns `is_valid: True` for any DataFrame, even empty or malformed ones. Validation becomes a false safety net.

**Prevention:**
- Add required columns for every new data type to the validation dict
- Better: make required columns configurable per data type in `src/config.py` rather than hardcoded in the validation method
- Add minimum row count checks (e.g., "NGS passing for one season should have at least 32 rows for 32 starting QBs")
- Add column-presence assertions separate from null-percentage checks

**Detection:** Validation always passing for new data types regardless of content.

**Confidence:** HIGH -- confirmed in code (lines 330-338).

**Phase:** Phase 1 (extend validation as each new data type is added).

---

## Minor Pitfalls

### Pitfall 10: Bronze Ingestion CLI Uses elif Chain Instead of Dispatch

**What goes wrong:** Adding 9 new data types to `bronze_ingestion_simple.py` means adding 9 more `elif` blocks to the existing 8-way chain (lines 99-144). This creates a 17-way if/elif chain that is hard to read, test, and maintain. Each block has slightly different logic for S3 key construction, making it easy to introduce copy-paste bugs.

**Prevention:**
- Refactor to a dispatch table before expanding:
  ```python
  DATA_TYPE_CONFIG = {
      'ngs_passing': {'fetch_method': 'fetch_ngs_passing', 's3_prefix': 'ngs/passing', 'weekly': False},
      ...
  }
  ```
- Each data type becomes a config entry, not a code branch

**Phase:** Phase 1 (refactor before adding new types, not after).

---

### Pitfall 11: PBP Currently Fetches Only 10-13 Columns

**What goes wrong:** The existing `fetch_play_by_play()` defaults to 13 columns (line 85-87) and the bronze ingestion script requests only 10 (lines 106-108). For game prediction purposes, the valuable columns are EPA, WPA, CPOE, air yards, completion probability, and other advanced metrics -- none of which are in the current default.

**Prevention:**
- Bronze should store ALL columns (Medallion Architecture principle: Bronze = raw, unfiltered)
- Remove the `columns` parameter default from the Bronze-level PBP fetch
- Create named column subsets in config for Silver-layer filtering
- Use Parquet columnar storage -- unused columns have near-zero read cost when queried by column

**Phase:** Phase 2 (when redesigning PBP ingestion for full column support).

---

### Pitfall 12: Broad Exception Handling Hides Data Source Errors

**What goes wrong:** Every fetch method catches `Exception` and re-raises after logging. When adding 9 new data types, some will have unique failure modes:
- Combine data: may not exist for the current season (combine hasn't happened yet in March)
- Win totals: may not be published until late summer
- Depth charts: schema may change mid-season as teams update rosters
- NGS data: may return errors if stat_type is wrong

All of these get caught as generic `Exception` with no guidance on the actual problem.

**Prevention:**
- Add data-type-specific error handling that gives actionable messages:
  - "Combine data not yet available for 2026 season (typically published in March after the Combine)"
  - "NGS data requires stat_type parameter: passing, rushing, or receiving"
  - "Win totals typically available starting in June for the upcoming season"
- Distinguish between "data doesn't exist yet" (expected, temporal) and "API is broken" (unexpected)

**Phase:** Phase 2 (after basic ingestion works, before production use).

---

### Pitfall 13: S3 Key Pattern Inconsistency for New Data Types

**What goes wrong:** The existing S3 key patterns lack consistency:
- `games/season=YYYY/week=WW/schedules_*.parquet`
- `plays/season=YYYY/week=WW/pbp_*.parquet`
- `players/weekly/season=YYYY/week=WW/player_weekly_*.parquet`

Some use category names (`games`, `plays`), others use entity names (`players/weekly`). No convention exists for NGS, PFR, combine, draft, etc.

**Prevention:**
- Define S3/local key templates in `src/config.py` for ALL data types before implementation
- Establish a consistent pattern: `{source}/{data_type}/season=YYYY/[week=WW/]{data_type}_YYYYMMDD_HHMMSS.parquet`
- Seasonal data (combine, draft, rosters) should omit the `week=` partition
- Stat-typed data (NGS, PFR) should include stat_type in the key or directory

**Phase:** Phase 1 (define key patterns before writing any new ingestion code).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1: Setup | nfl-data-py archived (Pitfall 1) | Decide: migrate to nflreadpy or build adapter layer |
| Phase 1: Setup | Season cap at 2025 (Pitfall 7) | Dynamic year calculation |
| Phase 1: Setup | No local Bronze writes (Pitfall 8) | Add local-first support to bronze_ingestion_simple.py |
| Phase 1: Config | Season ranges vary (Pitfall 4) | Define per-type season ranges in config.py |
| Phase 1: Config | Key pattern chaos (Pitfall 13) | Define all S3/local key templates upfront |
| Phase 1: Refactor | elif chain (Pitfall 10) | Dispatch table before adding types |
| Phase 2: PBP | Memory explosion (Pitfall 3) | Per-season processing, downcast=True, full columns |
| Phase 2: NGS/PFR | stat_type confusion (Pitfall 6) | 3 API calls per type, verify param names |
| Phase 2: All types | Column drift (Pitfall 5) | Schema registry, centralized mapping |
| Phase 2: All types | Broken validation (Pitfall 9) | Extend validation dict per type |
| Phase 3: Joins | Player ID mismatches (Pitfall 5) | Standardize on GSIS ID, add ID resolution |
| Phase 3: Combine/Draft | Temporal unavailability (Pitfall 12) | Actionable error messages per type |
| All phases | API function traps (Pitfall 2) | Verify against GitHub source, not PyPI docs |

## Priority Order for Addressing Pitfalls

1. **Before any expansion:** Fix Pitfalls 7 (season cap), 8 (local-first bronze), 1 (adapter layer decision)
2. **During Phase 1:** Address Pitfalls 4 (season ranges), 9 (validation), 10 (dispatch refactor), 5 (schema registry), 13 (key patterns)
3. **Per data type:** Address Pitfalls 6 (NGS/PFR stat_type), 3 (PBP memory), 11 (PBP columns) as each type is implemented
4. **After basic expansion:** Address Pitfalls 12 (error handling), 2 (rosters guard enforcement)

## Sources

- [nfl-data-py GitHub (archived)](https://github.com/nflverse/nfl_data_py) -- HIGH confidence, verified archived status
- [nflreadpy GitHub (replacement)](https://github.com/nflverse/nflreadpy) -- HIGH confidence, official successor
- [nflreadpy documentation](https://nflreadpy.nflverse.com/) -- HIGH confidence
- [nflreadpy load functions API](https://nflreadpy.nflverse.com/api/load_functions/) -- HIGH confidence
- [nfl-data-py PyPI](https://pypi.org/project/nfl-data-py/) -- HIGH confidence, function signatures
- [nfl-data-py Issue #34 (docs error)](https://github.com/nflverse/nfl_data_py/issues/34) -- HIGH confidence, stat_type vs columns param
- [nfl-data-py Issue #98 (NumPy 2.0)](https://github.com/nflverse/nfl_data_py/issues/98) -- HIGH confidence, np.float_ removed
- [nfl-data-py Issue #122 (Python 3.13)](https://github.com/nflverse/nfl_data_py/issues/122) -- HIGH confidence, install failure
- Project files: `src/nfl_data_integration.py`, `.planning/codebase/CONCERNS.md`, `.planning/PROJECT.md` -- HIGH confidence, direct code review

---

*Pitfalls audit: 2026-03-08*
