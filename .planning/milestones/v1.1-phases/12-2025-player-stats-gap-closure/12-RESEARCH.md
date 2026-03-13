# Phase 12: 2025 Player Stats Gap Closure - Research

**Researched:** 2026-03-12
**Domain:** nflverse data migration (player_stats -> stats_player tag), column mapping, Bronze ingestion
**Confidence:** HIGH

## Summary

The 2025 player stats gap exists because nflverse migrated from the `player_stats` release tag to a new `stats_player` tag. The `nfl-data-py` library's `import_weekly_data()` hardcodes the old `player_stats` tag URL pattern (`player_stats_{year}.parquet`), which returns 404 for 2025. The new `stats_player` tag uses different file naming (`stats_player_week_{year}.parquet`) and a different column schema -- 115 columns vs the old 53 core columns, with several renamed columns and 67 new columns (defensive stats, kicking, special teams).

The column mapping is well-defined: 4 columns were renamed (`interceptions` -> `passing_interceptions`, `sacks` -> `sacks_suffered`, `sack_yards` -> `sack_yards_lost`, `recent_team` -> `team` in weekly), 1 column was dropped (`dakota` -- replaced by `passing_cpoe`), and 67 new columns were added. The mapping must happen at ingestion time so downstream code (scoring_calculator, player_analytics, projection_engine) continues working without modification.

For seasonal data, the `stats_player` tag provides a pre-aggregated `stats_player_reg_{year}.parquet` file. However, this file lacks 14 share/rate columns present in the existing 2024 seasonal schema (`ay_sh`, `dom`, `ppr_sh`, `rfd_sh`, `rtd_sh`, `rtdfd_sh`, `ry_sh`, `tgt_sh`, `w8dom`, `wopr_x`, `wopr_y`, `yac_sh`, `yptmpa`). The CONTEXT.md decision to aggregate from weekly data is the correct approach since it allows computing these derived columns.

**Primary recommendation:** Download directly from `stats_player` tag via HTTPS, apply a well-defined column rename map at ingestion, keep extra columns alongside mapped ones, and aggregate seasonal from weekly.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Bypass nfl-data-py for 2025+ player stats -- download directly from nflverse/nflverse-data GitHub releases using the `stats_player` tag URL
- New adapter method in NFLDataAdapter (e.g., `_fetch_stats_player()`) handles the direct GitHub download
- Only used for seasons >= STATS_PLAYER_MIN_SEASON (2025) -- existing `import_weekly_data` continues to work for 2016-2024
- GITHUB_TOKEN: use if available for 5000/hr rate limit, fall back to unauthenticated (60/hr) with warning -- consistent with Phase 8 no-hard-blocking pattern
- Map columns at Bronze ingestion so saved Parquet matches 2016-2024 schema exactly
- Discover mapping by reading a 2024 Bronze file to get exact column list, then comparing against downloaded 2025 data
- STATS_PLAYER_COLUMN_MAP constant defined in config.py (follows config-as-source-of-truth pattern from Phase 9)
- Extra columns in the new schema: keep alongside mapped columns (more data available, slightly wider schema than 2016-2024 but all 53 original columns present)
- Log schema diff showing mapped vs new columns
- Aggregate from weekly data only -- do not attempt to fetch seasonal directly from the new tag
- Aggregation logic lives in NFLDataAdapter (e.g., `_aggregate_seasonal_from_weekly()`)
- Match existing 2024 seasonal file schema exactly -- read 2024 seasonal Bronze file as reference
- Season-conditional routing inside existing `fetch_weekly_data()` -- if season >= STATS_PLAYER_MIN_SEASON, call new internal method
- Same conditional routing in `fetch_seasonal_data()` -- route to aggregation method for 2025+
- Registry entries unchanged -- `--data-type player_weekly --season 2025` just works transparently
- STATS_PLAYER_MIN_SEASON = 2025 constant in config.py
- Run full Silver processing + validation on 2025 data

### Claude's Discretion
- Exact GitHub release URL construction and HTTP download implementation
- Schema diff logging format
- Aggregation logic details (which columns to sum vs average vs recalculate)
- Test structure and fixture design
- Error handling for network failures during GitHub download

### Deferred Ideas (OUT OF SCOPE)
None

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BACKFILL-02 | Player weekly extended to include 2025 | Direct download from `stats_player` tag with column mapping produces schema-compatible Bronze Parquet |
| BACKFILL-03 | Player seasonal extended to include 2025 | Weekly-to-seasonal aggregation produces schema-compatible seasonal Bronze Parquet |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | existing | DataFrame operations, parquet I/O | Already used project-wide |
| requests | stdlib-adjacent | HTTP download from GitHub releases | Simple, reliable, no new dependency needed (urllib3 also acceptable) |
| pyarrow | existing | Parquet read/write | Already a project dependency via pandas |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| os/dotenv | existing | GITHUB_TOKEN from .env | Auth header for GitHub API rate limits |
| io.BytesIO | stdlib | In-memory parquet read from HTTP response | Avoid temp file for single download |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| requests | urllib.request | requests is cleaner API but adds dependency; urllib is stdlib |
| Direct download | nflreadr (R) | Would require R runtime; Python-only is simpler |
| Direct download | Wait for nfl-data-py update | Uncertain timeline; direct download is reliable now |

**Installation:**
No new dependencies needed. `requests` may need to be added if not already installed; otherwise `urllib.request` from stdlib works fine.

## Architecture Patterns

### Recommended Changes
```
src/
  config.py              # Add STATS_PLAYER_MIN_SEASON, STATS_PLAYER_COLUMN_MAP
  nfl_data_adapter.py    # Add _fetch_stats_player(), _aggregate_seasonal_from_weekly()
                         # Modify fetch_weekly_data() and fetch_seasonal_data() with conditional routing
scripts/
  bronze_ingestion_simple.py  # No changes needed (registry dispatch handles it)
```

### Pattern 1: Season-Conditional Routing
**What:** Inside existing `fetch_weekly_data()`, check if season >= STATS_PLAYER_MIN_SEASON. If yes, delegate to `_fetch_stats_player()` instead of `nfl.import_weekly_data()`.
**When to use:** Any season where the old `player_stats` tag lacks data.
**Example:**
```python
def fetch_weekly_data(self, seasons: List[int], columns=None) -> pd.DataFrame:
    seasons = self._filter_seasons("player_weekly", seasons)
    if not seasons:
        return pd.DataFrame()

    from src.config import STATS_PLAYER_MIN_SEASON
    old_seasons = [s for s in seasons if s < STATS_PLAYER_MIN_SEASON]
    new_seasons = [s for s in seasons if s >= STATS_PLAYER_MIN_SEASON]

    frames = []
    if old_seasons:
        nfl = self._import_nfl()
        frames.append(self._safe_call("fetch_weekly_data", nfl.import_weekly_data, old_seasons, columns))
    if new_seasons:
        for s in new_seasons:
            frames.append(self._fetch_stats_player(s))

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
```

### Pattern 2: Column Mapping at Ingestion
**What:** Rename new schema columns to match old schema names so downstream code works unchanged.
**When to use:** After downloading from `stats_player` tag, before returning DataFrame.
**Example:**
```python
# In config.py
STATS_PLAYER_COLUMN_MAP = {
    "passing_interceptions": "interceptions",
    "sacks_suffered": "sacks",
    "sack_yards_lost": "sack_yards",
    "team": "recent_team",
}

# In adapter
def _apply_column_mapping(self, df: pd.DataFrame) -> pd.DataFrame:
    from src.config import STATS_PLAYER_COLUMN_MAP
    return df.rename(columns=STATS_PLAYER_COLUMN_MAP)
```

### Pattern 3: Seasonal Aggregation from Weekly
**What:** Group weekly data by player/season, sum counting stats, recalculate rate stats.
**When to use:** For `fetch_seasonal_data()` when season >= STATS_PLAYER_MIN_SEASON.

### Anti-Patterns to Avoid
- **Modifying downstream code:** The column mapping MUST happen at Bronze ingestion. Never change scoring_calculator.py, player_analytics.py, or projection_engine.py to handle new column names.
- **Fetching seasonal from stats_player tag directly:** The `stats_player_reg_{year}.parquet` file lacks 14 share/rate columns (`ay_sh`, `dom`, `ppr_sh`, etc.) that the existing seasonal schema has. Aggregation from weekly is required.
- **Removing `dakota` column:** The old schema has `dakota` but the new schema has `passing_cpoe` instead. Map `passing_cpoe` to `dakota` for backward compatibility since downstream code may reference it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP download | Custom socket/urllib logic | `requests.get()` or `urllib.request.urlopen()` | Error handling, redirects, timeouts handled |
| Parquet from bytes | Save to temp file then read | `pd.read_parquet(io.BytesIO(response.content))` | No temp file management needed |
| Column mapping | Inline dict in adapter | `STATS_PLAYER_COLUMN_MAP` in config.py | Single source of truth, easy to update |
| Seasonal share columns | Custom formulas | Reference 2024 seasonal file for aggregation rules | Ensures exact schema match |

## Common Pitfalls

### Pitfall 1: Missing `dakota` Column
**What goes wrong:** The new `stats_player` schema has `passing_cpoe` instead of `dakota`. If not mapped, any code referencing `dakota` will fail.
**Why it happens:** `dakota` was an nflverse-specific composite metric that was renamed/replaced.
**How to avoid:** Include `"passing_cpoe": "dakota"` in STATS_PLAYER_COLUMN_MAP.
**Warning signs:** KeyError on `dakota` in downstream processing.

### Pitfall 2: Weekly File Has `team` Not `recent_team`
**What goes wrong:** The `stats_player_week` file uses `team` while all downstream code uses `recent_team`. Player analytics groups by `recent_team` extensively.
**Why it happens:** nflverse standardized naming in the new tag.
**How to avoid:** Map `team` -> `recent_team` in the column map.
**Warning signs:** Empty merges in player_analytics.py, missing opponent rankings.

### Pitfall 3: Seasonal Share Columns Are Not Simple Aggregations
**What goes wrong:** The 14 seasonal-only columns (`ay_sh`, `dom`, `ppr_sh`, `tgt_sh`, etc.) are team-level share metrics that need recalculation, not simple sums.
**Why it happens:** Share metrics = player_stat / team_stat, computed across the full season.
**How to avoid:** Compute shares after aggregating raw stats. For example: `tgt_sh = player_targets / team_targets`.
**Warning signs:** Share values > 1.0 (summing weekly shares instead of recalculating).

### Pitfall 4: POST Season Games Included
**What goes wrong:** The weekly file includes both REG and POST season types (weeks 1-22). If not handled, seasonal aggregation may mix regular and postseason.
**Why it happens:** The 2024 data also includes both, so this is expected behavior. The existing seasonal files have `season_type` column.
**How to avoid:** Filter to REG only when aggregating seasonal data (matching existing 2024 seasonal behavior where season_type='REG').

### Pitfall 5: `games` Column in Seasonal
**What goes wrong:** The seasonal schema has a `games` column that counts games played. This must be derived from weekly data.
**How to avoid:** Count distinct weeks per player when aggregating.

### Pitfall 6: GitHub Rate Limiting
**What goes wrong:** Unauthenticated GitHub API calls are limited to 60/hour. Downloading a ~774 KB parquet file counts as one request.
**Why it happens:** GitHub rate limits by IP for unauthenticated requests.
**How to avoid:** Use GITHUB_TOKEN in Authorization header if available. Log a warning if falling back to unauthenticated.
**Warning signs:** HTTP 403 with rate limit headers.

## Code Examples

### Download from stats_player Tag
```python
# Source: verified against actual GitHub release structure
import io
import os
import logging
import pandas as pd

logger = logging.getLogger(__name__)

STATS_PLAYER_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{season}.parquet"
)

def _fetch_stats_player(self, season: int) -> pd.DataFrame:
    """Download player stats from nflverse stats_player release tag."""
    import urllib.request
    from src.config import STATS_PLAYER_COLUMN_MAP

    url = STATS_PLAYER_URL.format(season=season)
    headers = {}
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    else:
        logger.warning(
            "No GITHUB_TOKEN found. Using unauthenticated GitHub API (60 req/hr limit)."
        )

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        df = pd.read_parquet(io.BytesIO(data))
        logger.info("stats_player %d: %d rows, %d columns", season, len(df), len(df.columns))

        # Apply column mapping for backward compatibility
        df = df.rename(columns=STATS_PLAYER_COLUMN_MAP)
        return df
    except Exception:
        logger.exception("Failed to download stats_player for season %d", season)
        return pd.DataFrame()
```

### Column Map Constant
```python
# Source: derived from empirical schema comparison (2024 Bronze vs 2025 stats_player)
STATS_PLAYER_MIN_SEASON = 2025

STATS_PLAYER_COLUMN_MAP = {
    "passing_interceptions": "interceptions",
    "sacks_suffered": "sacks",
    "sack_yards_lost": "sack_yards",
    "team": "recent_team",
    "passing_cpoe": "dakota",
}
```

### Seasonal Aggregation from Weekly
```python
# Columns that should be summed across weeks
SUM_COLS = [
    "attempts", "completions", "passing_yards", "passing_tds", "interceptions",
    "sacks", "sack_yards", "sack_fumbles", "sack_fumbles_lost",
    "passing_air_yards", "passing_yards_after_catch", "passing_first_downs",
    "passing_epa", "passing_2pt_conversions",
    "carries", "rushing_yards", "rushing_tds", "rushing_fumbles",
    "rushing_fumbles_lost", "rushing_first_downs", "rushing_epa",
    "rushing_2pt_conversions",
    "receptions", "targets", "receiving_yards", "receiving_tds",
    "receiving_fumbles", "receiving_fumbles_lost", "receiving_air_yards",
    "receiving_yards_after_catch", "receiving_first_downs", "receiving_epa",
    "receiving_2pt_conversions",
    "special_teams_tds", "fantasy_points", "fantasy_points_ppr",
]

# Columns that need recalculation (not simple sum)
# target_share, air_yards_share, wopr, pacr, racr -> recalculate from aggregated totals
# dakota -> average weighted by attempts
# games -> count of distinct weeks
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `player_stats` tag | `stats_player` tag | 2025 season | 2025+ data only available under new tag |
| `player_stats_{year}.parquet` | `stats_player_week_{year}.parquet` | 2025 | File naming changed |
| 53 columns (offense only) | 115 columns (offense + defense + kicking + ST) | 2025 | Much wider schema, more data available |
| `nfl.import_weekly_data()` | Direct GitHub download | 2025 | nfl-data-py not updated for new tag |

**Deprecated/outdated:**
- `player_stats` tag: No 2025 data. Files for 2016-2024 still available under old tag.
- `nfl.import_weekly_data()` for 2025+: Returns 404. Still works for 2016-2024.

## Verified Schema Facts

### Weekly Schema (2024 Bronze -> 2025 stats_player)
- **2024 Bronze:** 55 columns (53 core + 2 metadata: `data_source`, `ingestion_timestamp`)
- **2025 stats_player_week:** 115 columns
- **Columns in both:** 48
- **Renamed (old -> new):** `interceptions` -> `passing_interceptions`, `sacks` -> `sacks_suffered`, `sack_yards` -> `sack_yards_lost`, `recent_team` -> `team`, `dakota` -> `passing_cpoe`
- **Removed (metadata only):** `data_source`, `ingestion_timestamp` (added by ingestion script, not in source)
- **New columns (67):** Defensive stats (15 `def_*`), kicking (28 `fg_*`/`pat_*`/`gwfg_*`), special teams (4), other (20 including `game_id`, `penalties`, `penalty_yards`, `misc_yards`, `fumble_recovery_*`)

### Seasonal Schema (2024 Bronze)
- **2024 Bronze:** 60 columns (58 core + 2 metadata)
- **Seasonal-only columns (14):** `ay_sh`, `dom`, `games`, `ppr_sh`, `rfd_sh`, `rtd_sh`, `rtdfd_sh`, `ry_sh`, `tgt_sh`, `w8dom`, `wopr_x`, `wopr_y`, `yac_sh`, `yptmpa`
- **`stats_player_reg` file:** Has `games` but lacks the other 13 share/rate columns -- confirms need for custom aggregation

### Download URLs (verified working)
- Weekly: `https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.parquet` (774 KB)
- Reg seasonal: `https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2025.parquet` (not used per decision)

## Open Questions

1. **`dakota` vs `passing_cpoe` semantic equivalence**
   - What we know: `dakota` was a completion-percentage-over-expected metric in the old schema. `passing_cpoe` is present in the new schema.
   - What's unclear: Whether they are computed identically. `dakota` may have been a more complex composite.
   - Recommendation: Map `passing_cpoe` -> `dakota` for now. If downstream results differ meaningfully, investigate further. LOW impact since `dakota` is not used in scoring or projections.

2. **Seasonal share column formulas**
   - What we know: The 13 share columns (`ay_sh`, `dom`, `ppr_sh`, etc.) are team-level share metrics.
   - What's unclear: Exact formulas for `dom`, `w8dom`, `yptmpa`, `wopr_x` vs `wopr_y`.
   - Recommendation: Reference the 2024 seasonal file + nflverse documentation to derive formulas. If formulas are uncertain, compute from weekly aggregates using common definitions.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | none (pytest runs from project root) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACKFILL-02 | Weekly 2025 download + column mapping produces compatible schema | unit | `python -m pytest tests/test_stats_player.py::test_column_mapping -x` | No -- Wave 0 |
| BACKFILL-02 | Conditional routing in fetch_weekly_data for 2025+ | unit | `python -m pytest tests/test_stats_player.py::test_conditional_routing -x` | No -- Wave 0 |
| BACKFILL-02 | validate_data passes on mapped 2025 weekly data | unit | `python -m pytest tests/test_stats_player.py::test_weekly_validation -x` | No -- Wave 0 |
| BACKFILL-03 | Seasonal aggregation from weekly produces correct schema | unit | `python -m pytest tests/test_stats_player.py::test_seasonal_aggregation -x` | No -- Wave 0 |
| BACKFILL-03 | validate_data passes on aggregated 2025 seasonal data | unit | `python -m pytest tests/test_stats_player.py::test_seasonal_validation -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_stats_player.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_stats_player.py` -- covers BACKFILL-02, BACKFILL-03 (column mapping, routing, aggregation, validation)
- [ ] Test fixtures: mock DataFrame with stats_player schema (115 columns) for unit tests without network

## Sources

### Primary (HIGH confidence)
- GitHub API `repos/nflverse/nflverse-data/releases/tags/stats_player` -- confirmed tag exists, file naming pattern `stats_player_week_{year}.parquet`, 542 assets
- GitHub API `repos/nflverse/nflverse-data/releases/tags/player_stats` -- confirmed NO 2025 files under old tag
- Direct download of `stats_player_week_2025.parquet` -- inspected actual schema (115 columns, 19421 rows)
- Direct download of `stats_player_reg_2025.parquet` -- inspected seasonal-equivalent schema (113 columns, 2020 rows, has `games` but lacks share columns)
- `nfl_data_py.import_weekly_data` source code -- confirmed hardcoded URL uses old `player_stats` tag
- Local `data/bronze/players/weekly/season=2024/` -- verified existing 2024 schema (55 columns)
- Local `data/bronze/players/seasonal/season=2024/` -- verified existing seasonal schema (60 columns)
- `src/scoring_calculator.py`, `src/player_analytics.py`, `src/projection_engine.py` -- verified downstream usage of `interceptions`, `sacks`, `sack_yards`, `recent_team`, `dakota`

### Secondary (MEDIUM confidence)
- [nflverse-data releases page](https://github.com/nflverse/nflverse-data/releases) -- 25 release tags listed
- [nflreadr releases reference](https://nflreadr.nflverse.com/reference/nflverse_releases.html) -- confirms stats_player tag name

### Tertiary (LOW confidence)
- `dakota` vs `passing_cpoe` equivalence -- assumed equivalent based on naming, not verified against nflverse source code

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, well-understood HTTP download + pandas
- Architecture: HIGH -- conditional routing pattern is simple, column mapping is well-defined from empirical comparison
- Pitfalls: HIGH -- all identified from actual schema comparison and downstream code grep
- Seasonal aggregation: MEDIUM -- share column formulas need validation against 2024 reference data

**Research date:** 2026-03-12
**Valid until:** 2026-06-12 (stable -- nflverse tag structure unlikely to change mid-season)
