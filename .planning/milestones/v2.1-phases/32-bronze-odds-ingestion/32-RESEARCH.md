# Phase 32: Bronze Odds Ingestion - Research

**Researched:** 2026-03-27
**Domain:** Historical odds ingestion from FinnedAI/sportsbookreview-scraper JSON into Bronze Parquet
**Confidence:** HIGH

## Summary

Phase 32 ingests historical opening and closing betting lines (2016-2021) from the FinnedAI/sportsbookreview-scraper GitHub repo into Bronze Parquet, joinable to every nflverse game via `game_id`. The primary data source is a JSON file (`nfl_archive_10Y.json`) containing 1,621 games across 2016-2021 with opening/closing spreads, closing moneylines, and over/under totals. Zero null opening spreads exist in the source data.

The highest-risk step is team name mapping: FinnedAI uses inconsistent team nicknames (e.g., "Packers", "Fortyniners", "Washingtom" [sic], "KCChiefs", "LVRaiders") that must be mapped to nflverse abbreviations (e.g., "GB", "SF", "WAS", "KC", "LV"). A complete mapping dictionary has been empirically derived from the actual data. The second risk is sign convention alignment: FinnedAI uses standard sportsbook convention (negative = home favored) while nflverse uses the opposite (positive = home favored via `spread_line`). The ingestion script must negate FinnedAI spreads to match nflverse convention, validated by the Pearson r > 0.95 cross-validation gate.

The FinnedAI data has known quality issues: 5 corrupt entries (team=0) across 2016-2020 (one per season, likely Super Bowl parsing errors), and 2021 has 284 games vs nflverse's 285 (1 missing game). These are expected and handleable -- corrupt entries are dropped, and the missing game is logged as an orphan during the nflverse join.

**Primary recommendation:** Download `nfl_archive_10Y.json` via `requests`, parse with Python `json`, map team names using a hardcoded dictionary, join to nflverse schedules by `(season, home_team, away_team, week)` to inherit `game_id`, negate spreads to match nflverse sign convention, cross-validate closing lines, and write per-season Parquet to `data/bronze/odds/season=YYYY/`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use FinnedAI/sportsbookreview-scraper CSV files as the primary source, not raw SBRO XLSX -- pre-scraped data is more stable (SBRO site could go offline), already parsed, and eliminates openpyxl dependency risk
- **D-02:** Script the download via `requests` into `data/raw/sbro/` as a staging area -- raw files are retained for reproducibility and debugging data quality issues
- **D-03:** If FinnedAI repo is unavailable or incomplete, fall back to direct SBRO XLSX download with openpyxl parsing -- code both paths but FinnedAI first
- **D-04:** Download is a one-time operation (2016-2021 is frozen historical data) -- the script should be idempotent with skip-existing logic, not a recurring pipeline step
- **D-05:** Standalone script `scripts/bronze_odds_ingestion.py` -- odds come from external files, not nfl-data-py, so they don't fit the adapter pattern
- **D-06:** Register `odds` in DATA_TYPE_SEASON_RANGES in `src/config.py` (range: 2016-2021) for validation and pipeline health checks
- **D-07:** Follow the same CLI conventions as other Bronze scripts (--season flag, --dry-run, progress output) but with its own download+parse+validate+write pipeline
- **D-08:** Schema validation function in the script that checks required columns exist and types are correct before writing Parquet
- **D-09:** Include neutral-site and London games -- they are real NFL games with real betting lines; excluding them loses training data and hurts accuracy
- **D-10:** Include playoff games if SBRO covers them -- flag with `game_type` column from nflverse join; the prediction model already handles playoff context (Phase 22)
- **D-11:** Missing opening lines within covered seasons -> NaN (never zero, never dropped) -- downstream feature selection handles NaN gracefully; dropping rows loses the closing line data which is needed for CLV
- **D-12:** Postponed/cancelled games with no final score -> exclude from odds output (no prediction target exists)
- **D-13:** Games where SBRO has data but nflverse join fails -> log as orphan, do not silently drop -- zero orphan tolerance is a success criterion
- **D-14:** One row per game at Bronze level (not per-team) -- this is raw data; per-team reshape with sign flips happens at Silver (Phase 33)
- **D-15:** Required columns: `game_id` (from nflverse join), `season`, `week`, `game_type`, `home_team`, `away_team`, `opening_spread`, `closing_spread`, `opening_total`, `closing_total`
- **D-16:** Include moneylines if SBRO/FinnedAI provides them (`home_moneyline`, `away_moneyline`) -- useful for implied probability in v2.2 betting framework; zero incremental cost to capture now
- **D-17:** Include `nflverse_spread_line` and `nflverse_total_line` merged from schedules for inline cross-validation -- every row carries its own validation data
- **D-18:** Spread sign convention: home-team perspective (negative = home favored), matching nflverse convention -- validate empirically during ingestion with correlation check
- **D-19:** Cross-validation gate: Pearson r > 0.95 between SBRO closing spread and nflverse spread_line, AND >95% of games within 1.0 point -- script fails if either threshold is not met
- **D-20:** Row count validation: compare games per season against expected nflverse game counts (256 regular season pre-2021, 272 post-2021, plus playoffs) -- warn on >5% deviation
- **D-21:** Sign convention check: for games where nflverse spread_line < -7 (clear home favorites), assert SBRO opening spread is also negative -- a single sign flip invalidates the entire season's data

### Claude's Discretion
- Exact FinnedAI repo file structure and parsing details (inspect at implementation time)
- Column name mapping from raw SBRO/FinnedAI format to standardized output schema
- Logging verbosity and progress reporting format
- Temporary file handling during download

### Deferred Ideas (OUT OF SCOPE)
- No-vig implied probability from moneylines -- v2.2 Betting Framework
- 2022-2024 opening lines (paid source like BigDataBall) -- post-v2.1 if line movement features prove material
- Real-time odds API integration -- v2.2+
- Multi-book line comparison -- out of scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ODDS-01 | Download and parse SBRO XLSX archives into Parquet with opening/closing spreads and totals (2016-2021) | FinnedAI JSON is primary source (D-01); data is `nfl_archive_10Y.json` with 1,621 games for 2016-2021; JSON schema fully documented with 25 columns including `home_open_spread`, `home_close_spread`, `open_over_under`, `close_over_under`; SBRO XLSX fallback path also needed (D-03) |
| ODDS-02 | Map SBRO team names to nflverse game_id with validated team name mapping dictionary | Complete mapping dictionary derived: 44 unique FinnedAI names -> 32 nflverse abbreviations; includes relocations (Oakland->LV, SanDiego->LAC, St.Louis->LA), typos ("Washingtom", "Fortyniners"), and inconsistencies ("KCChiefs", "LVRaiders", "Tampa", "Kansas"); 5 corrupt team=0 entries must be dropped |
| ODDS-03 | Register 'odds' as a Bronze data type with schema validation in the ingestion registry | Add `"odds": (2016, lambda: 2021)` to `DATA_TYPE_SEASON_RANGES` in `src/config.py`; standalone script pattern (D-05) not registry dispatch; schema validation function checks 10+ required columns and types |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| requests | 2.32.4 (installed) | Download FinnedAI JSON from GitHub raw URL | Already in venv; single HTTP GET to fetch ~2MB JSON |
| pandas | existing | Parse JSON, DataFrame operations, Parquet write | Project standard for all data processing |
| pyarrow | existing | Parquet engine for `df.to_parquet()` | Project standard storage format |
| json | stdlib | Parse downloaded JSON file | Standard library; FinnedAI data is JSON not CSV |
| nfl-data-py | existing | `import_schedules()` for nflverse join data | Already used for all Bronze schedule ingestion |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| openpyxl | >= 3.1.0 | SBRO XLSX fallback parsing | Only if FinnedAI source is unavailable (D-03); NOT currently installed |
| scipy.stats | existing | `pearsonr()` for cross-validation gate | Compute Pearson r between SBRO and nflverse closing spreads |
| argparse | stdlib | CLI interface matching other Bronze scripts | Standard CLI pattern for `--season`, `--dry-run` flags |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FinnedAI JSON | Raw SBRO XLSX | XLSX requires openpyxl install + complex sheet parsing; JSON is pre-parsed |
| requests + json | pandas.read_json(url) | Direct URL read risks timeout on large file; download-first is more robust and supports caching (D-02) |
| Manual team mapping dict | fuzzy string matching | Fuzzy matching is fragile and over-engineered for 44 known names; hardcoded dict is deterministic |

**Installation (only if SBRO fallback needed):**
```bash
pip install openpyxl>=3.1.0
```

No new dependencies needed for the primary path.

## Architecture Patterns

### Recommended Project Structure
```
scripts/
  bronze_odds_ingestion.py    # Standalone ingestion script (D-05)
src/
  config.py                   # Add odds to DATA_TYPE_SEASON_RANGES (D-06)
data/
  raw/sbro/                   # Staging area for downloaded JSON (D-02)
    nfl_archive_10Y.json
  bronze/odds/                # Output Parquet files
    season=2016/odds_YYYYMMDD_HHMMSS.parquet
    season=2017/...
    ...
    season=2021/...
```

### Pattern 1: FinnedAI JSON Schema (Verified from Live Data)
**What:** The FinnedAI `nfl_archive_10Y.json` contains 2,956 entries (2011-2021). For this phase, only 2016-2021 (1,621 entries) are relevant.
**JSON fields per entry:**
```python
{
    "season": 2020,                    # int or str (mixed types in dataset)
    "date": 20200910.0,                # float, format YYYYMMDD
    "home_team": "Chiefs",             # Nickname, NOT abbreviation
    "away_team": "Texans",             # Nickname, NOT abbreviation
    "home_1stQtr": "7",                # str (not used for odds)
    "away_1stQtr": "0",                # str (not used for odds)
    "home_final": "34",                # str (useful for validation)
    "away_final": "20",                # str
    "home_close_ml": -350,             # int, standard ML format
    "away_close_ml": 290,              # int
    "home_open_spread": -10.0,         # float, NEGATIVE = home favored
    "away_open_spread": 10.0,          # float, mirror of home
    "home_close_spread": -10.5,        # float
    "away_close_spread": 10.5,         # float
    "home_2H_spread": ...,             # Not needed for Bronze
    "away_2H_spread": ...,             # Not needed
    "2H_total": ...,                   # Not needed
    "open_over_under": 53.5,           # float
    "close_over_under": 54.0           # float
}
```

### Pattern 2: Team Name Mapping Dictionary (Complete, Verified)
**What:** Maps all 44 unique FinnedAI team nicknames to nflverse abbreviations.
**Critical:** This dictionary is season-agnostic because FinnedAI already uses relocated names in the correct years (Oakland for pre-2020, Raiders for post-2020).
```python
FINNEDAI_TO_NFLVERSE = {
    # Standard nicknames (32 current + historical)
    "Cardinals": "ARI", "Falcons": "ATL", "Ravens": "BAL", "Bills": "BUF",
    "Panthers": "CAR", "Bears": "CHI", "Bengals": "CIN", "Browns": "CLE",
    "Cowboys": "DAL", "Broncos": "DEN", "Lions": "DET", "Packers": "GB",
    "Texans": "HOU", "Colts": "IND", "Jaguars": "JAX", "Chiefs": "KC",
    "Chargers": "LAC", "Rams": "LA", "Dolphins": "MIA", "Vikings": "MIN",
    "Patriots": "NE", "Saints": "NO", "Giants": "NYG", "Jets": "NYJ",
    "Eagles": "PHI", "Steelers": "PIT", "Seahawks": "SEA",
    "Buccaneers": "TB", "Titans": "TEN",
    # San Francisco variant
    "Fortyniners": "SF",
    # Relocated teams (appear in earlier seasons)
    "Oakland": "OAK",    # 2016-2019
    "Raiders": "LV",     # 2020-2021
    "SanDiego": "SD",    # 2016 only
    "St.Louis": "STL",   # Not in 2016-2021 range (pre-2016)
    "LosAngeles": "LA",  # 2016 only (before "Rams" naming settled)
    # Washington variants
    "Commanders": "WAS", # Used across all seasons in FinnedAI
    "Washingtom": "WAS", # Typo in 2020 data
    # Inconsistent multi-word names (2020 data quality issues)
    "KCChiefs": "KC",
    "Kansas": "KC",      # Truncated "Kansas City"
    "LVRaiders": "LV",
    "Tampa": "TB",       # Truncated "Tampa Bay"
    "BuffaloBills": "BUF",
    "NewYork": "NYJ",    # Ambiguous -- requires game-level resolution
}
```

**WARNING: "NewYork" is ambiguous** -- could be NYG or NYJ. Resolution requires matching by date + opponent against nflverse schedules. Only appears in 2020 season.

### Pattern 3: Sign Convention Alignment (Empirically Verified)
**What:** FinnedAI and nflverse use OPPOSITE sign conventions for spreads.
**Evidence:**
- nflverse `spread_line`: positive = home favored (verified: when `home_moneyline < away_moneyline`, `spread_line > 0` in 148/148 cases for 2020)
- FinnedAI `home_open_spread`: negative = home favored (standard sportsbook convention; verified: Packers at home, ML -250, spread -4.5)
- **Action:** Negate FinnedAI spreads before storing: `opening_spread = -home_open_spread`
- **Validation (D-21):** After negation, for nflverse games where `spread_line > 7` (clear home favorites), assert `opening_spread > 0`

### Pattern 4: Join Strategy (nflverse Schedules)
**What:** Join FinnedAI odds to nflverse schedules to inherit `game_id`.
**Join keys:** `(season, week, home_team)` -- NOT `(season, week, home_team, away_team)` because that adds unnecessary constraint. Home team + week uniquely identifies a game.
**Problem:** FinnedAI has no `week` column -- only `date` (YYYYMMDD float).
**Solution:** Join nflverse schedules (which has `gameday` as date string and `week`) to FinnedAI by `(season, home_team, gameday)`. Convert FinnedAI `date` float to date string: `str(int(date))` -> `"20200910"` -> parse to date.
**nflverse `gameday` format:** Date string like `"2020/09/10"` -- verify exact format and parse both sides to `datetime.date` for robust matching.

### Pattern 5: Expected Game Counts (Verified)
| Season | nflverse Total | FinnedAI Total | FinnedAI Corrupt (team=0) | Expected Matchable |
|--------|---------------|----------------|--------------------------|-------------------|
| 2016 | 267 | 267 | 1 | 266 |
| 2017 | 267 | 267 | 1 | 266 |
| 2018 | 267 | 267 | 1 | 266 |
| 2019 | 267 | 267 | 1 | 266 |
| 2020 | 269 | 269 | 1 | 268 |
| 2021 | 285 | 284 | 0 | 284 |
| **Total** | **1,622** | **1,621** | **5** | **1,616** |

Note: 2021 has 1 fewer game in FinnedAI than nflverse. The 5 corrupt entries (team=0) are likely Super Bowl rows with parsing errors. After cleaning, expect ~1,616 matched games and ~6 orphan nflverse games without odds data.

### Anti-Patterns to Avoid
- **Constructing game_id independently:** Never build `game_id` from SBRO/FinnedAI data. Always join to nflverse schedules and inherit the canonical `game_id`.
- **Storing SBRO closing lines as truth:** nflverse `spread_line`/`total_line` is canonical. SBRO closing lines are cross-validation reference only.
- **Using team=0 entries:** These are corrupt parsing artifacts. Drop them before any processing.
- **Assuming FinnedAI has CSV files:** The repo contains JSON only (`nfl_archive_10Y.json`), despite README mentioning CSV format option. The pre-scraped data is JSON.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Team name fuzzy matching | Levenshtein distance matcher | Hardcoded FINNEDAI_TO_NFLVERSE dict | Only 44 names; fuzzy matching can silently mismatch ("Raiders" -> wrong team in wrong year) |
| Date parsing | Custom regex parser | `datetime.strptime(str(int(date)), "%Y%m%d")` | FinnedAI dates are simple YYYYMMDD floats |
| Parquet writing | Custom serializer | `df.to_parquet(path, index=False)` via existing `save_local()` pattern | Project standard in bronze_ingestion_simple.py |
| Cross-validation stats | Manual correlation | `scipy.stats.pearsonr()` | Already in venv; one-liner |
| Season validation | Custom range check | `validate_season_for_type("odds", season)` after adding to registry | Existing pattern in config.py |

**Key insight:** The entire ingestion pipeline is download + dict-lookup + date-join + negate + validate. No ML, no complex parsing, no streaming. The complexity is in the data quality validation, not the code.

## Common Pitfalls

### Pitfall 1: Sign Convention Mismatch
**What goes wrong:** Opening/closing spreads stored with wrong sign, causing all downstream line movement features to be inverted.
**Why it happens:** FinnedAI uses standard sportsbook convention (negative = home favored) but nflverse uses opposite (positive = home favored). Easy to forget the negation.
**How to avoid:** Negate FinnedAI spreads immediately after parsing: `opening_spread = -home_open_spread`. Validate with D-21 check: for games where nflverse `spread_line > 7`, assert `opening_spread > 0`.
**Warning signs:** Pearson r between `opening_spread` and nflverse `spread_line` is negative (~-0.95 instead of +0.95).

### Pitfall 2: Ambiguous "NewYork" Team Name
**What goes wrong:** "NewYork" in FinnedAI 2020 data gets mapped to NYJ when it should be NYG (or vice versa).
**Why it happens:** FinnedAI has inconsistent team naming in 2020 season specifically; "NewYork" could be either team.
**How to avoid:** Do not map "NewYork" statically. Instead, resolve by matching `(season, date, opponent)` against nflverse schedules to determine which NY team is correct.
**Warning signs:** Orphan count increases; cross-validation correlation drops for 2020 specifically.

### Pitfall 3: FinnedAI Date Format Edge Cases
**What goes wrong:** Date column is a float (`20200910.0`), and some entries may have unexpected values.
**Why it happens:** JSON parsing from scraped data; the `date` field was numeric in the source.
**How to avoid:** Convert to int first (`int(date)`), then to string, then parse. Handle potential NaN dates by checking `pd.notna()` before conversion.
**Warning signs:** `ValueError` during date parsing; games that should join by date failing to match.

### Pitfall 4: Corrupt team=0 Entries
**What goes wrong:** 5 entries across 2016-2020 have `home_team=0` (integer zero, not string), causing mapping failures.
**Why it happens:** Super Bowl or special game parsing errors in the FinnedAI scraper.
**How to avoid:** Filter out entries where `str(home_team) == '0' or str(away_team) == '0'` before any processing. Log count per season.
**Warning signs:** KeyError in team mapping dictionary; unexpected NaN in home_team column.

### Pitfall 5: 2020 Season Team Name Chaos
**What goes wrong:** 2020 season in FinnedAI has 38 unique team names instead of 32, with duplicates like "Chiefs"/"KCChiefs"/"Kansas" all meaning KC.
**Why it happens:** Multiple scraping runs or source format changes mid-season in 2020.
**How to avoid:** The mapping dictionary handles all variants. After mapping, assert exactly 32 unique teams per season.
**Warning signs:** More than 32 mapped team abbreviations in a single season; duplicate games after join.

### Pitfall 6: Missing Week in FinnedAI Data
**What goes wrong:** Joining by `(season, week, home_team)` fails because FinnedAI has no `week` column.
**Why it happens:** FinnedAI only has a `date` field, not an NFL week number.
**How to avoid:** Join by `(season, home_team, gameday_date)` instead. Convert both FinnedAI `date` and nflverse `gameday` to `datetime.date` for matching.
**Warning signs:** Zero matches when trying to join on `week`.

## Code Examples

### Download FinnedAI JSON (D-02)
```python
# Source: Verified against FinnedAI repo structure
import requests, json, os

RAW_DIR = "data/raw/sbro"
JSON_URL = "https://raw.githubusercontent.com/FinnedAI/sportsbookreview-scraper/main/data/nfl_archive_10Y.json"

def download_finnedai(force: bool = False) -> str:
    """Download FinnedAI JSON to staging area. Skip if exists (D-04)."""
    os.makedirs(RAW_DIR, exist_ok=True)
    local_path = os.path.join(RAW_DIR, "nfl_archive_10Y.json")
    if os.path.exists(local_path) and not force:
        print(f"  Already downloaded: {local_path}")
        return local_path
    r = requests.get(JSON_URL, timeout=30)
    r.raise_for_status()
    with open(local_path, "w") as f:
        f.write(r.text)
    print(f"  Downloaded: {local_path} ({len(r.text):,} bytes)")
    return local_path
```

### Parse and Map Team Names
```python
# Source: Derived from empirical analysis of FinnedAI data
import pandas as pd
from datetime import datetime

def parse_finnedai(json_path: str, seasons: list[int]) -> pd.DataFrame:
    """Parse FinnedAI JSON into DataFrame for specified seasons."""
    with open(json_path) as f:
        data = json.load(f)

    # Filter to requested seasons, drop corrupt entries
    records = []
    dropped = 0
    for entry in data:
        season = int(entry["season"])
        if season not in seasons:
            continue
        if str(entry["home_team"]) == "0" or str(entry["away_team"]) == "0":
            dropped += 1
            continue
        records.append(entry)

    if dropped:
        print(f"  Dropped {dropped} corrupt entries (team=0)")

    df = pd.DataFrame(records)
    df["season"] = df["season"].astype(int)

    # Map team names
    df["home_team_nfl"] = df["home_team"].map(FINNEDAI_TO_NFLVERSE)
    df["away_team_nfl"] = df["away_team"].map(FINNEDAI_TO_NFLVERSE)

    # Check for unmapped teams
    unmapped = df[df["home_team_nfl"].isna() | df["away_team_nfl"].isna()]
    if len(unmapped) > 0:
        print(f"  WARNING: {len(unmapped)} games with unmapped teams")

    # Parse dates: float YYYYMMDD -> datetime.date
    df["gameday"] = pd.to_datetime(
        df["date"].astype(int).astype(str), format="%Y%m%d"
    ).dt.date

    return df
```

### Sign Convention Alignment
```python
# Source: Empirically verified -- nflverse positive=home favored,
#         FinnedAI negative=home favored
def align_spreads(df: pd.DataFrame) -> pd.DataFrame:
    """Negate FinnedAI spreads to match nflverse convention."""
    # Negate: FinnedAI -4.5 (home fav) -> +4.5 (nflverse home fav)
    df["opening_spread"] = -df["home_open_spread"]
    df["closing_spread"] = -df["home_close_spread"]
    # Totals have no sign convention issue
    df["opening_total"] = df["open_over_under"]
    df["closing_total"] = df["close_over_under"]
    # Moneylines: keep as-is (D-16)
    df["home_moneyline"] = df["home_close_ml"]
    df["away_moneyline"] = df["away_close_ml"]
    return df
```

### Join to nflverse Schedules
```python
# Source: Verified nflverse schema via import_schedules([2020])
import nfl_data_py as nfl

def join_to_nflverse(odds_df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Join odds to nflverse schedules to inherit game_id."""
    sched = nfl.import_schedules([season])
    sched["gameday_date"] = pd.to_datetime(sched["gameday"]).dt.date

    merged = odds_df.merge(
        sched[["game_id", "season", "week", "game_type",
               "home_team", "away_team", "gameday_date",
               "spread_line", "total_line"]],
        left_on=["season", "home_team_nfl", "gameday"],
        right_on=["season", "home_team", "gameday_date"],
        how="left",
        suffixes=("_sbro", ""),
    )

    # Rename nflverse fields for inline cross-validation (D-17)
    merged.rename(columns={
        "spread_line": "nflverse_spread_line",
        "total_line": "nflverse_total_line",
    }, inplace=True)

    # Log orphans (D-13)
    orphans = merged[merged["game_id"].isna()]
    if len(orphans) > 0:
        print(f"  WARNING: {len(orphans)} odds rows with no nflverse match")

    return merged
```

### Cross-Validation Gate (D-19)
```python
from scipy.stats import pearsonr

def validate_cross_correlation(df: pd.DataFrame) -> bool:
    """Assert closing line agreement between SBRO and nflverse."""
    valid = df.dropna(subset=["closing_spread", "nflverse_spread_line"])

    r, _ = pearsonr(valid["closing_spread"], valid["nflverse_spread_line"])
    within_1pt = (
        (valid["closing_spread"] - valid["nflverse_spread_line"]).abs() <= 1.0
    ).mean()

    print(f"  Cross-validation: r={r:.4f}, within 1pt={within_1pt:.1%}")

    if r < 0.95:
        raise ValueError(f"Pearson r={r:.4f} < 0.95 threshold")
    if within_1pt < 0.95:
        raise ValueError(f"Within 1pt={within_1pt:.1%} < 95% threshold")

    return True
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw SBRO XLSX download + openpyxl | FinnedAI pre-scraped JSON | Decision D-01 | Eliminates openpyxl dependency; more stable source |
| Team name fuzzy matching | Hardcoded mapping dictionary | Research finding | 44 known names; deterministic; no false matches |
| Assume same sign convention | Empirically verify + negate | Research finding | FinnedAI and nflverse use opposite conventions |
| Join by (season, week, home, away) | Join by (season, home_team, date) | Research finding | FinnedAI has no week column; date join is required |

**Deprecated/outdated:**
- SBRO XLSX direct download: Still works but FinnedAI JSON is preferred (D-01); keep as fallback (D-03)
- The project research SUMMARY.md assumed CSV files from FinnedAI; actual data is JSON format

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.1 |
| Config file | none (default discovery) |
| Quick run command | `python -m pytest tests/test_bronze_odds.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ODDS-01 | Parse FinnedAI JSON into DataFrame with correct columns and types | unit | `python -m pytest tests/test_bronze_odds.py::test_parse_finnedai -x` | Wave 0 |
| ODDS-01 | Download from GitHub URL with skip-existing logic | unit | `python -m pytest tests/test_bronze_odds.py::test_download_idempotent -x` | Wave 0 |
| ODDS-01 | Sign convention alignment (negation) produces correct values | unit | `python -m pytest tests/test_bronze_odds.py::test_sign_convention -x` | Wave 0 |
| ODDS-01 | Cross-validation gate passes with r > 0.95 | integration | `python -m pytest tests/test_bronze_odds.py::test_cross_validation_gate -x` | Wave 0 |
| ODDS-01 | Parquet output has correct schema and partitioning | unit | `python -m pytest tests/test_bronze_odds.py::test_output_schema -x` | Wave 0 |
| ODDS-02 | All 44 FinnedAI team names map to valid nflverse abbreviations | unit | `python -m pytest tests/test_bronze_odds.py::test_team_mapping_complete -x` | Wave 0 |
| ODDS-02 | "NewYork" ambiguity resolved correctly for NYG vs NYJ | unit | `python -m pytest tests/test_bronze_odds.py::test_newyork_disambiguation -x` | Wave 0 |
| ODDS-02 | Corrupt team=0 entries are dropped and logged | unit | `python -m pytest tests/test_bronze_odds.py::test_corrupt_entries_dropped -x` | Wave 0 |
| ODDS-02 | Join to nflverse produces zero orphan odds rows | integration | `python -m pytest tests/test_bronze_odds.py::test_zero_orphans -x` | Wave 0 |
| ODDS-03 | odds registered in DATA_TYPE_SEASON_RANGES with range 2016-2021 | unit | `python -m pytest tests/test_bronze_odds.py::test_config_registration -x` | Wave 0 |
| ODDS-03 | Schema validation rejects DataFrame missing required columns | unit | `python -m pytest tests/test_bronze_odds.py::test_schema_validation -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_bronze_odds.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_bronze_odds.py` -- covers ODDS-01, ODDS-02, ODDS-03
- [ ] Test fixtures: mock FinnedAI JSON subset (5-10 entries) and mock nflverse schedule DataFrame

## Open Questions

1. **"NewYork" disambiguation strategy**
   - What we know: "NewYork" appears in 2020 FinnedAI data and could be NYG or NYJ
   - What's unclear: Exactly how many games use this name; whether date+opponent uniquely resolves it
   - Recommendation: During implementation, filter FinnedAI 2020 data for "NewYork", extract dates, match against nflverse schedules for both NYG and NYJ home games on those dates. If ambiguous, use opponent name as tiebreaker.

2. **2021 missing game**
   - What we know: FinnedAI has 284 games for 2021, nflverse has 285
   - What's unclear: Which specific game is missing
   - Recommendation: After join, the missing game will appear as a nflverse game with no odds match. Log it. It is acceptable per D-11 (NaN for missing data).

3. **SBRO XLSX fallback implementation depth (D-03)**
   - What we know: FinnedAI JSON is primary; SBRO XLSX is fallback
   - What's unclear: How much effort to invest in XLSX parser if JSON works
   - Recommendation: Implement a minimal XLSX fallback that downloads and parses the file, but do not gold-plate it. The JSON path handles 100% of the data. The XLSX path is insurance against FinnedAI repo deletion.

## Sources

### Primary (HIGH confidence)
- Live Python execution: `requests.get()` of FinnedAI `nfl_archive_10Y.json` -- verified 2,956 entries, 25 columns, 44 unique team names, 1,621 games for 2016-2021
- Live Python execution: `nfl.import_schedules([2020])` -- verified 46 columns, game_id format `2020_01_HOU_KC`, spread_line sign convention (positive = home favored in 148/148 home-favorite games)
- Direct inspection: `scripts/bronze_ingestion_simple.py` -- registry dispatch pattern, CLI conventions, `save_local()` function
- Direct inspection: `src/config.py` -- `DATA_TYPE_SEASON_RANGES` structure, `validate_season_for_type()` function

### Secondary (MEDIUM confidence)
- [FinnedAI/sportsbookreview-scraper](https://github.com/FinnedAI/sportsbookreview-scraper) -- repo structure confirmed (data/nfl_archive_10Y.json); README mentions CSV format but actual pre-scraped data is JSON
- [nflverse schedules data dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html) -- column definitions for spread_line, total_line, moneylines

### Tertiary (LOW confidence)
- None -- all critical claims verified against live data

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries verified installed (except openpyxl fallback); no new dependencies for primary path
- Architecture: HIGH -- FinnedAI JSON schema, team names, sign conventions, game counts all verified empirically against downloaded data and nflverse API
- Pitfalls: HIGH -- team name chaos, sign convention mismatch, corrupt entries, and missing week column all discovered through actual data analysis, not assumed

**Research date:** 2026-03-27
**Valid until:** Indefinite -- 2016-2021 historical data is frozen; FinnedAI repo could be deleted but data is downloadable now
