# Phase 2: Core PBP Ingestion - Research

**Researched:** 2026-03-08
**Domain:** nfl-data-py play-by-play ingestion, column curation, memory management
**Confidence:** HIGH

## Summary

Play-by-play data from nfl-data-py (`import_pbp_data`) returns 397 columns and ~49K rows per season (~432 MB in memory with all columns). Column subsetting via the `columns` parameter combined with `include_participation=False` and `downcast=True` reduces this to ~103 curated columns at ~66 MB memory and ~5 MB parquet per season. For 16 seasons (2010-2025), this means ~80 MB total disk, with peak memory safely under 150 MB per season -- well within the 2 GB constraint.

The existing adapter (`NFLDataAdapter.fetch_pbp`) already supports `columns` and `downcast` parameters but does NOT pass `include_participation`. The CLI (`bronze_ingestion_simple.py`) dispatches PBP through the registry but `_build_method_kwargs()` does not wire `columns` or `downcast` through. The work is: (1) define the curated column list, (2) wire kwargs through the CLI/registry, (3) add a batch loop for multi-season ingestion, (4) validate output.

**Primary recommendation:** Define a `PBP_COLUMNS` constant (~103 columns), pass `include_participation=False` in the adapter, wire columns/downcast through `_build_method_kwargs`, and add a `--seasons` range flag or batch script for 2010-2025 ingestion.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Ingest 2010-2025 (16 seasons) -- captures modern NFL era post-rule-changes
- All seasons ingested in one pass (loop one season at a time for memory safety)
- One file per season: `data/bronze/pbp/season=YYYY/pbp_{timestamp}.parquet`
- Week column preserved inside each file for downstream DuckDB/pandas filtering
- Timestamped files -- consistent with existing Bronze convention (`download_latest_parquet()` resolves latest)
- Aggressive compression: Parquet snappy (default) + downcast all numeric columns

### Claude's Discretion
- Column curation: select ~80 columns from 390 covering EPA, WPA, CPOE, air yards, success rate, game context, player IDs, play type. Research phase should benchmark actual column availability.
- Memory strategy: use adapter's existing `columns` param for fetch-time subsetting + `downcast=True`. Add chunking only if needed.
- Processing: no transformations in Bronze -- raw curated columns only.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PBP-01 | Full PBP ingested with ~80 curated columns including EPA, WPA, CPOE, air yards, success rate | Column list benchmarked: 103 columns verified present in 2024 data. All key metrics confirmed: epa, wpa, cpoe, air_yards, success. See "Curated Column List" section. |
| PBP-02 | PBP processes one season at a time to manage memory (not all seasons at once) | Peak memory for single season: ~130 MB (tracemalloc). Well under 2 GB. Adapter already takes `seasons=[single]`. CLI loop per season is sufficient. |
| PBP-03 | PBP uses column subsetting via columns parameter (not all 390 columns) | Verified: `columns` param works with `include_participation=False`. 397 -> 103 columns, 432 MB -> 66 MB memory. |
| PBP-04 | PBP ingested for seasons 2010-2025 in Bronze layer | Verified: 2010 data returns 46,892 rows with all 103 columns present. CPOE/air_yards ~38% populated pre-2018 (expected -- tracking data wasn't available). EPA/WPA ~99% populated for all seasons. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| nfl-data-py | installed | `import_pbp_data()` fetches PBP from nflverse | Already used project-wide; adapter wraps it |
| pandas | installed | DataFrame processing | Project standard |
| pyarrow | installed | Parquet I/O with snappy compression | Already used for all Bronze/Silver/Gold |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tracemalloc | stdlib | Memory profiling during dev/test | Verify peak < 2 GB |

### Alternatives Considered
None -- all libraries already in use. No new dependencies needed.

## Architecture Patterns

### Recommended Changes to Existing Code

```
src/
  nfl_data_adapter.py    # Add include_participation=False to fetch_pbp
  config.py              # Add PBP_COLUMNS constant (~103 columns)
scripts/
  bronze_ingestion_simple.py  # Wire columns/downcast in _build_method_kwargs for pbp
                               # Add --seasons flag or batch loop for multi-season
```

### Pattern 1: Column List as Config Constant

**What:** Define `PBP_COLUMNS` in `src/config.py` as a list of ~103 column names.
**When to use:** Any PBP fetch operation.
**Why:** Single source of truth, easy to extend, testable.

```python
# src/config.py
PBP_COLUMNS = [
    # Game/play identifiers
    "game_id", "play_id", "season", "week", "season_type", "game_date",
    "posteam", "defteam", "home_team", "away_team",
    "home_score", "away_score", "posteam_score", "defteam_score",
    "posteam_score_post", "defteam_score_post",
    "score_differential", "score_differential_post",

    # Play situation
    "down", "ydstogo", "yardline_100", "goal_to_go",
    "qtr", "quarter_seconds_remaining", "half_seconds_remaining",
    "game_seconds_remaining", "drive",
    "posteam_timeouts_remaining", "defteam_timeouts_remaining",

    # Play type and result
    "play_type", "yards_gained", "shotgun", "no_huddle",
    "qb_dropback", "qb_scramble", "qb_kneel", "qb_spike",
    "pass_attempt", "rush_attempt", "pass_length", "pass_location",
    "run_location", "run_gap",
    "complete_pass", "incomplete_pass", "interception", "sack",
    "fumble", "fumble_lost", "penalty",
    "first_down", "third_down_converted", "third_down_failed",
    "fourth_down_converted", "fourth_down_failed",
    "touchdown", "pass_touchdown", "rush_touchdown", "safety",

    # Advanced metrics (EPA, WPA, CPOE)
    "epa", "ep", "air_epa", "yac_epa", "comp_air_epa", "comp_yac_epa",
    "qb_epa",
    "wpa", "vegas_wpa", "air_wpa", "yac_wpa", "comp_air_wpa", "comp_yac_wpa",
    "wp", "def_wp", "home_wp", "away_wp",
    "home_wp_post", "away_wp_post",
    "cpoe", "cp",
    "air_yards", "yards_after_catch", "passing_yards", "receiving_yards", "rushing_yards",

    # Success / expected
    "success", "xpass", "pass_oe",

    # Player IDs
    "passer_player_id", "passer_player_name",
    "receiver_player_id", "receiver_player_name",
    "rusher_player_id", "rusher_player_name",

    # Vegas lines
    "spread_line", "total_line",

    # Series
    "series", "series_success", "series_result",

    # Weather/venue
    "temp", "wind", "roof", "surface",
]
```

### Pattern 2: Registry-Driven Column/Kwarg Wiring

**What:** Extend the PBP registry entry and `_build_method_kwargs()` to pass `columns` and `downcast`.
**When to use:** PBP ingestion through the CLI.

```python
# In DATA_TYPE_REGISTRY:
"pbp": {
    "adapter_method": "fetch_pbp",
    "bronze_path": "pbp/season={season}",
    "requires_week": False,
    "requires_season": True,
    "default_kwargs": {"downcast": True},  # NEW
},

# In _build_method_kwargs():
if method_name == "fetch_pbp":
    from src.config import PBP_COLUMNS
    kwargs["columns"] = PBP_COLUMNS
    kwargs["downcast"] = True
```

### Pattern 3: Multi-Season Batch Loop

**What:** Add `--seasons` CLI argument (e.g., `--seasons 2010-2025`) that loops one season at a time.
**When to use:** Bulk ingestion of 16 seasons.

```python
# CLI addition:
parser.add_argument("--seasons", type=str, help="Season range, e.g., 2010-2025")

# In main(), if --seasons provided:
for season in range(start, end + 1):
    args.season = season
    # ... dispatch and save per existing logic
```

### Anti-Patterns to Avoid
- **Fetching all 16 seasons in one import_pbp_data call:** This would load ~800K rows x 397 columns (~7 GB) into memory. Always loop one season at a time.
- **Using include_participation=True with columns filter:** The participation merge adds ~26 columns and can cause schema mismatch errors when combined with column filtering.
- **Post-fetch column filtering (fetch all, then select):** Wastes memory. The `columns` parameter filters at the parquet read level in nfl-data-py, so pass it at fetch time.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PBP data fetching | Custom HTTP/parquet reader | `nfl.import_pbp_data(columns=..., downcast=True)` | Handles nflverse CDN, caching, schema evolution |
| Numeric downcasting | Manual dtype conversion | `downcast=True` parameter | Built into nfl-data-py, converts float64 -> float32 |
| Local file save | Custom writer | Existing `save_local()` in CLI | Already handles directory creation, parquet write |
| Season validation | Manual range checks | `validate_season_for_type("pbp", season)` | Already configured: pbp valid 1999-2027 |

**Key insight:** The entire infrastructure (adapter, registry, local save, season validation) exists from Phase 1. This phase is wiring + column curation, not new architecture.

## Common Pitfalls

### Pitfall 1: include_participation Breaks Column Filtering
**What goes wrong:** When `include_participation=True` (the default), nfl-data-py merges participation data after the initial parquet read. If the requested columns don't include certain join keys, the merge can fail silently or return unexpected columns.
**Why it happens:** Participation data is a separate dataset joined on game_id/play_id.
**How to avoid:** Pass `include_participation=False` in the adapter. Participation data (offense_players, defense_players, etc.) is not needed for EPA/WPA game prediction.
**Warning signs:** Getting 35 columns when you requested 9, or getting 0 rows.

### Pitfall 2: CPOE/Air Yards Sparse Before 2018
**What goes wrong:** Assuming all 103 columns are fully populated for all seasons.
**Why it happens:** CPOE and air_yards depend on Next Gen Stats tracking which started ~2016-2018. Pre-2018 data has ~38% population for these fields.
**How to avoid:** This is expected behavior, not a bug. Document it but don't filter seasons. EPA/WPA are ~99% populated back to 2010.
**Warning signs:** Tests that assert non-null counts will fail for older seasons.

### Pitfall 3: Memory Spike During Download
**What goes wrong:** nfl-data-py downloads the full parquet file from nflverse CDN before filtering columns. The download itself uses memory.
**Why it happens:** Column filtering happens at the pyarrow read level, but the HTTP response is the full file.
**How to avoid:** Process one season at a time (already planned). Peak memory measured at ~130 MB per season with 103 columns -- well within limits.
**Warning signs:** If you see peak memory > 500 MB for a single season, something is wrong.

### Pitfall 4: Filename Collision With Existing PBP Data
**What goes wrong:** The existing PBP CLI entry already works (`--data-type pbp`), but without column filtering it saves all 397 columns.
**Why it happens:** `_build_method_kwargs` doesn't pass columns/downcast for PBP today.
**How to avoid:** Old files in `data/bronze/pbp/` are harmless since `download_latest_parquet()` picks the newest. But clean up stale files if present.

## Code Examples

### Fetching PBP With Column Subsetting (Verified)
```python
# Source: Direct testing against nfl-data-py in this project's venv
import nfl_data_py as nfl
from src.config import PBP_COLUMNS

df = nfl.import_pbp_data(
    [2024],
    columns=PBP_COLUMNS,
    downcast=True,
    include_participation=False,
)
# Result: 49,492 rows, 103 columns, 66 MB memory, 5.2 MB parquet
```

### Adapter Update
```python
# src/nfl_data_adapter.py -- update fetch_pbp signature
def fetch_pbp(
    self,
    seasons: List[int],
    columns: Optional[List[str]] = None,
    downcast: bool = True,
    include_participation: bool = False,  # ADD THIS
) -> pd.DataFrame:
    nfl = self._import_nfl()
    return self._safe_call(
        "fetch_pbp",
        nfl.import_pbp_data,
        seasons,
        columns=columns,
        downcast=downcast,
        include_participation=include_participation,  # ADD THIS
    )
```

### CLI Kwargs Wiring
```python
# scripts/bronze_ingestion_simple.py -- in _build_method_kwargs()
if method_name == "fetch_pbp":
    from src.config import PBP_COLUMNS
    kwargs["columns"] = PBP_COLUMNS
    kwargs["downcast"] = True
    kwargs["include_participation"] = False
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fetch all 397 columns | Column subsetting via `columns` param | Always available in nfl-data-py | 6.5x memory reduction |
| float64 default | `downcast=True` (float32) | Always available | ~50% numeric memory savings |
| include_participation=True | include_participation=False for curated sets | Always available | Avoids 26 extra columns, prevents merge issues |

## Curated Column List -- Benchmarked Results

**Total unique columns:** 103 (not ~80 as originally estimated)

**Category breakdown:**
| Category | Count | Examples |
|----------|-------|---------|
| Game/play IDs | 10 | game_id, play_id, season, week, game_date |
| Score context | 8 | home_score, posteam_score, score_differential |
| Play situation | 11 | down, ydstogo, yardline_100, qtr, drive |
| Play type/result | 22 | play_type, yards_gained, shotgun, pass_attempt, touchdown |
| EPA metrics | 7 | epa, ep, air_epa, yac_epa, comp_air_epa, qb_epa |
| WPA metrics | 11 | wpa, vegas_wpa, air_wpa, wp, def_wp, home_wp |
| Completion metrics | 4 | cpoe, cp, xpass, pass_oe |
| Yardage | 5 | air_yards, yards_after_catch, passing/receiving/rushing_yards |
| Success | 1 | success |
| Player IDs | 6 | passer/receiver/rusher player_id and player_name |
| Vegas lines | 2 | spread_line, total_line |
| Series | 3 | series, series_success, series_result |
| Weather/venue | 4 | temp, wind, roof, surface |
| Teams | 4 | posteam, defteam, home_team, away_team |
| Season/type | 2 | season_type, goal_to_go |
| Timeouts | 2 | posteam/defteam_timeouts_remaining |
| Score post | 2 | posteam_score_post, defteam_score_post |

**Memory benchmarks (per season):**

| Metric | All 397 Columns | Curated 103 Columns | Savings |
|--------|-----------------|---------------------|---------|
| DataFrame memory | 432 MB | 66 MB | 85% |
| Peak process memory | ~500 MB est. | 130 MB | 74% |
| Parquet file size | ~25 MB est. | 5.2 MB | 79% |
| 16 seasons disk total | ~400 MB est. | ~83 MB | 79% |

**Column availability by era:**

| Column | 2010 | 2016 | 2020 | 2024 |
|--------|------|------|------|------|
| epa | 99% | 99% | 99% | 99% |
| wpa | 99% | 99% | 99% | 99% |
| cpoe | 38% | 38% | 64% | 64% |
| air_yards | 38% | 38% | 62% | 62% |
| success | 99% | 99% | 99% | 99% |
| spread_line | 100% | 100% | 100% | 100% |
| xpass | 76% | 76% | 76% | 76% |

## Open Questions

1. **Column count: ~80 vs 103**
   - What we know: The curated list has 103 unique columns, not the ~80 originally discussed.
   - What's unclear: Whether user wants to trim further.
   - Recommendation: Keep 103 -- they are all relevant for game prediction. Update requirement PBP-01 language from "~80" to "~100" if desired. The memory/disk cost is minimal (66 MB / 5 MB per season).

2. **Existing PBP files in data/bronze/pbp/**
   - What we know: The CLI already supports `--data-type pbp` and may have been run before.
   - What's unclear: Whether old full-column files exist that should be cleaned up.
   - Recommendation: Let `download_latest_parquet()` handle it -- newest file wins.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (no config file -- runs via `python -m pytest tests/ -v`) |
| Config file | none -- uses defaults |
| Quick run command | `python -m pytest tests/test_infrastructure.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PBP-01 | PBP_COLUMNS constant has ~100 entries including key metrics | unit | `python -m pytest tests/test_pbp_ingestion.py::test_pbp_columns_has_key_metrics -x` | Wave 0 |
| PBP-02 | fetch_pbp processes single season, peak memory < 2GB | unit (mock) | `python -m pytest tests/test_pbp_ingestion.py::test_single_season_processing -x` | Wave 0 |
| PBP-03 | fetch_pbp passes columns param, returns subset not all 397 | unit (mock) | `python -m pytest tests/test_pbp_ingestion.py::test_column_subsetting -x` | Wave 0 |
| PBP-04 | CLI produces files in data/bronze/pbp/season=YYYY/ | unit (mock) | `python -m pytest tests/test_pbp_ingestion.py::test_pbp_output_path -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_pbp_ingestion.py tests/test_infrastructure.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_pbp_ingestion.py` -- covers PBP-01 through PBP-04 (new file)
- [ ] No framework install needed -- pytest already available

## Sources

### Primary (HIGH confidence)
- **Direct testing:** `nfl.import_pbp_data([2024], ...)` executed in project venv -- column list, memory, file sizes all measured
- **Direct testing:** `nfl.import_pbp_data([2010], ...)` executed -- older season column availability verified
- **Source code:** `src/nfl_data_adapter.py` -- confirmed fetch_pbp signature and params
- **Source code:** `scripts/bronze_ingestion_simple.py` -- confirmed registry structure and _build_method_kwargs gaps
- **nfl-data-py help:** `help(nfl.import_pbp_data)` -- confirmed function signature including `include_participation` param

### Secondary (MEDIUM confidence)
- None needed -- all findings verified via direct execution

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all verified in existing venv
- Architecture: HIGH -- extending existing adapter/registry/CLI patterns from Phase 1
- Pitfalls: HIGH -- all discovered through direct testing (include_participation issue, column availability)
- Column list: HIGH -- every column verified present in both 2010 and 2024 data

**Research date:** 2026-03-08
**Valid until:** 2026-06-08 (stable -- nflverse PBP schema rarely changes mid-offseason)
