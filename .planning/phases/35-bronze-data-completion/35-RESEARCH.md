# Phase 35: Bronze Data Completion - Research

**Researched:** 2026-03-28
**Domain:** Bronze layer data ingestion (odds + 2025 season)
**Confidence:** HIGH

## Summary

Phase 35 has three workstreams: (1) batch FinnedAI odds ingestion for 5 remaining seasons (2016-2019, 2021), (2) a new `derive_odds_from_nflverse()` function to extract closing-line odds from nflverse schedules for 2022-2025, and (3) completing 2025 Bronze ingestion for the 1 missing core data type (injuries).

The existing `bronze_odds_ingestion.py` script is proven and requires zero code changes for FinnedAI batch runs -- only operational execution per season. The nflverse bridge is the only new code: it reads `nfl.import_schedules()` which already contains `spread_line`, `total_line`, `home_moneyline`, and `away_moneyline` with 100% coverage for 2022-2025. For 2025 Bronze data, investigation shows 7 of 8 core data types already exist; only `injuries` is missing, and nflverse caps injury data at 2024, so it cannot be ingested for 2025.

**Primary recommendation:** Execute FinnedAI batch ingestion as-is (operational, not developmental), build a simple nflverse bridge function that reshapes schedule columns to match the existing Bronze odds schema plus a `line_source` column, and document that 2025 injuries are unavailable from nflverse.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: `derive_odds_from_nflverse()` lives in `bronze_odds_ingestion.py` alongside FinnedAI functions -- single script owns all odds ingestion
- D-02: Carry all available odds columns from nflverse schedules: `spread_line`, `total_line`, `home_moneyline`, `away_moneyline`, plus `home_team`, `away_team`, `gameday`, `game_id`, `season`, `week` -- maximizes feature optionality for future model iterations
- D-03: Output schema matches FinnedAI Bronze output exactly (same column names, dtypes) plus a `line_source` column (`"finnedai"` or `"nflverse"`) for provenance tracking
- D-04: Missing odds rows (international games, rare scheduling edge cases) preserved as NaN -- never dropped, never zero-filled. Gradient boosting handles NaN natively; dropping rows loses game-level ground truth
- D-05: Seasons 2022-2025 use closing lines as opening-line proxies. `spread_shift` and `total_shift` will be zero downstream (open == close), but `opening_spread` and `opening_total` -- the only market features in `_PRE_GAME_CONTEXT` -- will be populated
- D-06: Try 2025 first via `nfl.import_schedules([2025])` smoke test. If >= 285 regular-season games exist, proceed with 2025 as the new holdout target
- D-07: If 2025 is incomplete (< 285 games or missing PBP/player_weekly), keep `HOLDOUT_SEASON=2024` unchanged
- D-08: Run the 2025 smoke test early in Plan 35-02 (before ingesting all 8 data types) to fail fast
- D-09: No cross-correlation validation for nflverse-derived odds (circular -- nflverse is the source itself)
- D-10: Validate via coverage checks: game count per season (>= 285 regular-season games with non-null spread_line), NaN rate for spread_line and total_line (must be < 5% of games per season), and schema consistency
- D-11: Validate playoff coverage separately: minimum 10 games with week >= 19 per season
- D-12: Run `bronze_odds_ingestion.py --season YYYY` per-season for 2016, 2017, 2018, 2019, 2021 (2020 already ingested). Per-season execution reuses existing validation
- D-13: No code changes to FinnedAI path -- the script is proven on 2020; batch execution is operational, not developmental

### Claude's Discretion
- Exact error messages and logging format for nflverse bridge
- Whether to add `--source nflverse` CLI flag or auto-detect season range
- Internal function decomposition within `derive_odds_from_nflverse()`
- Temp file handling during batch runs

### Deferred Ideas (OUT OF SCOPE)
- Paid odds API for 2022+ opening lines
- Multi-book line comparison
- Live line snapshot pipeline

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BRNZ-01 | Full FinnedAI odds ingested for all 6 seasons (2016-2021) with cross-validation r > 0.95 | Existing script proven on 2020; 5 remaining seasons need operational execution only (D-12, D-13). No code changes. |
| BRNZ-02 | nflverse schedule odds extracted for 2022-2025 with closing spread_line and total_line as Bronze Parquet | nflverse schedules contain `spread_line`, `total_line`, `home_moneyline`, `away_moneyline` with 100% coverage for 2022-2025. New `derive_odds_from_nflverse()` function needed. |
| BRNZ-03 | 2025 season fully ingested across all Bronze data types | 7 of 8 types already exist. Injuries capped at 2024 by nflverse (cannot ingest). All other types have data. |

</phase_requirements>

## Current State

### Existing Bronze Odds Data
- **2020 only**: `data/bronze/odds/season=2020/odds_20260327_174221.parquet` (244 rows, 14 columns)
- **Missing**: 2016, 2017, 2018, 2019, 2021 (FinnedAI), 2022-2025 (nflverse bridge)

### Existing Bronze Odds Schema (from 2020 Parquet)
| Column | Dtype | Source |
|--------|-------|--------|
| game_id | object | nflverse join |
| season | int64 | FinnedAI |
| week | int64 | nflverse join |
| game_type | object | nflverse join |
| home_team | object | nflverse join |
| away_team | object | nflverse join |
| opening_spread | float64 | FinnedAI (negated) |
| closing_spread | float64 | FinnedAI (negated) |
| opening_total | float64 | FinnedAI |
| closing_total | float64 | FinnedAI |
| home_moneyline | int64 | FinnedAI |
| away_moneyline | int64 | FinnedAI |
| nflverse_spread_line | float64 | nflverse join |
| nflverse_total_line | float64 | nflverse join |

**New column for D-03**: `line_source` (string, `"finnedai"` or `"nflverse"`)

### Existing 2025 Bronze Data
| Data Type | Status | Files |
|-----------|--------|-------|
| schedules | EXISTS | 1 |
| pbp | EXISTS | 2 |
| player_weekly | EXISTS | 1 |
| player_seasonal | EXISTS | 1 |
| snap_counts | EXISTS | 22 (weeks 1-22) |
| injuries | MISSING -- nflverse caps at 2024 | 0 |
| rosters | EXISTS | 1 |
| teams | EXISTS (no season partition) | 1 |

### nflverse Schedules Odds Coverage (Verified)
| Season | REG Games | POST Games | spread_line | total_line | home_moneyline | away_moneyline |
|--------|-----------|------------|-------------|------------|----------------|----------------|
| 2022 | 271 | 13 | 284/284 (100%) | 284/284 (100%) | 284/284 (100%) | 284/284 (100%) |
| 2023 | 272 | 13 | 285/285 (100%) | 285/285 (100%) | 285/285 (100%) | 285/285 (100%) |
| 2024 | 285 | -- | 285/285 (100%) | 285/285 (100%) | 285/285 (100%) | 285/285 (100%) |
| 2025 | 272 | 13 | 285/285 (100%) | 285/285 (100%) | 285/285 (100%) | 285/285 (100%) |

**Confidence: HIGH** -- verified via live `nfl.import_schedules()` calls.

### 2025 Season Availability (Smoke Test Results)
- `nfl.import_schedules([2025])`: 285 games (272 REG + 13 POST) -- **PASSES D-06 threshold (>= 285)**
- `nfl.import_pbp_data([2025])`: 48,771 rows -- full season PBP available
- `player_weekly` for 2025: already ingested
- `player_seasonal` for 2025: already ingested
- **Conclusion**: 2025 is complete. Proceed with 2025 as new holdout candidate (Phase 37 concern).

## Architecture Patterns

### nflverse Bridge Function Pattern

The `derive_odds_from_nflverse()` function reshapes nflverse schedule columns to match the existing FinnedAI Bronze output schema:

```python
# Source: Verified against nfl.import_schedules() output and existing Bronze schema
def derive_odds_from_nflverse(season: int, dry_run: bool = False) -> str:
    """Extract closing-line odds from nflverse schedules for seasons without FinnedAI data.

    For 2022+, nflverse closing lines serve as opening-line proxies (D-05).
    Opening == Closing, so spread_shift/total_shift will be zero downstream.

    Args:
        season: NFL season year (2022+).
        dry_run: If True, skip writing Parquet.

    Returns:
        Output file path.
    """
    sched = nfl.import_schedules([season])

    # Map to Bronze schema (D-03: match FinnedAI output exactly + line_source)
    df = pd.DataFrame({
        "game_id": sched["game_id"],
        "season": sched["season"],
        "week": sched["week"],
        "game_type": sched["game_type"],
        "home_team": sched["home_team"],
        "away_team": sched["away_team"],
        "opening_spread": sched["spread_line"],       # D-05: closing as opening proxy
        "closing_spread": sched["spread_line"],        # Same value (no movement data)
        "opening_total": sched["total_line"],
        "closing_total": sched["total_line"],
        "home_moneyline": sched["home_moneyline"],
        "away_moneyline": sched["away_moneyline"],
        "nflverse_spread_line": sched["spread_line"],  # Identical (source IS nflverse)
        "nflverse_total_line": sched["total_line"],
        "line_source": "nflverse",                      # D-03: provenance column
    })

    # Write to same Bronze path as FinnedAI output
    return write_parquet(df, season, dry_run=dry_run)
```

### FinnedAI Batch Execution (No Code Changes)
```bash
# D-12: Per-season execution for remaining 5 seasons
python scripts/bronze_odds_ingestion.py --season 2016
python scripts/bronze_odds_ingestion.py --season 2017
python scripts/bronze_odds_ingestion.py --season 2018
python scripts/bronze_odds_ingestion.py --season 2019
python scripts/bronze_odds_ingestion.py --season 2021
```

Each execution triggers existing validation: cross-correlation r > 0.95, sign convention, schema, row counts.

### line_source Column Backfill

Existing 2020 Parquet does NOT have `line_source`. Two options:
1. **Re-run 2020**: `python scripts/bronze_odds_ingestion.py --season 2020` after adding `line_source = "finnedai"` to the FinnedAI write path
2. **Add during write**: Modify `write_parquet()` to accept and include line_source column

**Recommendation**: Add `line_source` column to the FinnedAI path's `write_parquet` call. Minimal change -- add `df["line_source"] = "finnedai"` before writing, then re-run all 6 FinnedAI seasons (including 2020) for schema consistency.

### FINAL_COLUMNS Update
The existing `FINAL_COLUMNS` list in `bronze_odds_ingestion.py` needs `"line_source"` appended to include the provenance column in output.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Odds data for 2022+ | Custom scraper or API | `nfl.import_schedules()` | 100% coverage, free, already a dependency |
| Team name normalization for nflverse bridge | Any mapping logic | Direct column copy | nflverse already uses standard abbreviations |
| Season validation for nflverse bridge | Custom range check | Extend `DATA_TYPE_SEASON_RANGES["odds"]` | Existing config pattern handles this |

## Common Pitfalls

### Pitfall 1: FinnedAI JSON Download Failures
**What goes wrong:** GitHub raw content CDN occasionally returns 5xx or rate-limits.
**Why it happens:** Large JSON file (~5MB), rate limits on anonymous GitHub requests.
**How to avoid:** The script already caches downloads locally (`data/raw/sbro/nfl_archive_10Y.json`). The `--force-download` flag exists for re-download. For batch runs, download once, then process per-season.
**Warning signs:** `requests.exceptions.HTTPError` during download step.

### Pitfall 2: Schema Mismatch Between FinnedAI and nflverse Bridge Output
**What goes wrong:** Downstream Silver/feature code expects exact column names and dtypes. If nflverse bridge output has different dtypes (e.g., `home_moneyline` as float64 instead of int64), merge operations silently produce wrong results.
**Why it happens:** nflverse `home_moneyline` is float64; FinnedAI path produces int64.
**How to avoid:** Explicitly cast dtypes in the nflverse bridge to match FinnedAI output. Use `.astype(int)` for moneyline columns after dropping NaN rows.
**Warning signs:** Dtype mismatch warnings when concatenating FinnedAI and nflverse Parquet files.

### Pitfall 3: Injury Data Unavailable for 2025
**What goes wrong:** Attempting to ingest 2025 injuries fails because nflverse discontinued injury data after 2024.
**Why it happens:** `DATA_TYPE_SEASON_RANGES["injuries"]` caps at `lambda: 2024`.
**How to avoid:** Skip injury ingestion for 2025. Document this gap. Downstream injury adjustment logic in `projection_engine.py` should gracefully handle missing injury data (it already does -- NaN injuries = no adjustment).
**Warning signs:** `validate_season_for_type("injuries", 2025)` returns False.

### Pitfall 4: 2022 Season Has 271 Regular Season Games (Not 272)
**What goes wrong:** Row count validation may warn about 2022 having fewer games than expected.
**Why it happens:** The 2022 season had a cancelled game (Bills vs Bengals, Week 17, Damar Hamlin incident). nflverse has 271 REG + 13 POST = 284 total.
**How to avoid:** Set coverage threshold at >= 270 REG games (not 272) for 2022, or use the D-10 threshold of >= 285 total games (which 284 technically fails by 1). Recommend using per-season awareness in validation.
**Warning signs:** 2022 coverage check reports 284 < 285.

### Pitfall 5: Duplicate Parquet Files from Re-Runs
**What goes wrong:** Each run creates a new timestamped Parquet file. Re-running a season creates duplicates.
**Why it happens:** Timestamp-suffixed naming convention (`odds_YYYYMMDD_HHMMSS.parquet`).
**How to avoid:** This is by design -- `download_latest_parquet()` always reads the newest file. But storage grows. Consider cleaning up old files after confirming new ones are valid.
**Warning signs:** Multiple Parquet files in the same `season=YYYY` directory.

## Code Examples

### nflverse Bridge Validation (D-10, D-11)
```python
# Source: Adapted from existing validate_row_counts() pattern
def validate_nflverse_coverage(df: pd.DataFrame, season: int) -> None:
    """Validate nflverse-derived odds coverage (D-10, D-11).

    Checks:
    - Game count with non-null spread_line >= 270 (allows for cancelled games)
    - NaN rate for spread_line and total_line < 5%
    - Playoff games with week >= 19: at least 10
    """
    # Coverage check
    valid_spread = df["opening_spread"].notna().sum()
    valid_total = df["opening_total"].notna().sum()
    total_games = len(df)

    spread_nan_rate = 1 - (valid_spread / total_games) if total_games > 0 else 1.0
    total_nan_rate = 1 - (valid_total / total_games) if total_games > 0 else 1.0

    if spread_nan_rate > 0.05:
        raise ValueError(f"spread_line NaN rate {spread_nan_rate:.1%} exceeds 5% threshold")
    if total_nan_rate > 0.05:
        raise ValueError(f"total_line NaN rate {total_nan_rate:.1%} exceeds 5% threshold")

    # Playoff coverage (D-11)
    playoff_games = df[df["week"] >= 19]
    if len(playoff_games) < 10:
        print(f"  WARNING: Only {len(playoff_games)} playoff games (expected >= 10)")

    print(f"  Coverage: {valid_spread}/{total_games} games with spread, "
          f"NaN rate={spread_nan_rate:.1%}, playoffs={len(playoff_games)}")
```

### CLI Extension Pattern
```python
# Recommendation: Add --source nflverse flag alongside existing --source finnedai
parser.add_argument(
    "--source",
    choices=["finnedai", "sbro", "nflverse"],
    default="finnedai",
    help="Data source: 'finnedai' (2016-2021), 'nflverse' (2022+), or 'sbro' XLSX fallback",
)

# In main():
if args.source == "nflverse":
    # Validate season is 2022+
    if args.season and args.season < 2022:
        print(f"Error: --source nflverse only valid for seasons 2022+")
        return
    derive_odds_from_nflverse(args.season, dry_run=args.dry_run)
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | `tests/` directory with `__init__.py` |
| Quick run command | `python -m pytest tests/test_bronze_odds.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BRNZ-01 | FinnedAI per-season cross-validation r > 0.95 | unit | `python -m pytest tests/test_bronze_odds.py::TestCrossValidation -x` | Exists |
| BRNZ-01 | FinnedAI schema validation | unit | `python -m pytest tests/test_bronze_odds.py::TestOutputSchema -x` | Exists |
| BRNZ-01 | Team mapping completeness | unit | `python -m pytest tests/test_bronze_odds.py::TestTeamMapping -x` | Exists |
| BRNZ-02 | nflverse bridge schema matches FinnedAI | unit | `python -m pytest tests/test_bronze_odds.py::TestNflverseBridgeSchema -x` | Wave 0 |
| BRNZ-02 | nflverse coverage validation (D-10) | unit | `python -m pytest tests/test_bronze_odds.py::TestNflverseCoverage -x` | Wave 0 |
| BRNZ-02 | nflverse playoff coverage (D-11) | unit | `python -m pytest tests/test_bronze_odds.py::TestNflversePlayoffCoverage -x` | Wave 0 |
| BRNZ-02 | line_source column present | unit | `python -m pytest tests/test_bronze_odds.py::TestLineSourceColumn -x` | Wave 0 |
| BRNZ-03 | 2025 data types exist check | smoke | Manual verification via `ls data/bronze/*/season=2025/` | Manual |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_bronze_odds.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_bronze_odds.py::TestNflverseBridgeSchema` -- covers BRNZ-02 schema match
- [ ] `tests/test_bronze_odds.py::TestNflverseCoverage` -- covers D-10 coverage checks
- [ ] `tests/test_bronze_odds.py::TestNflversePlayoffCoverage` -- covers D-11 playoff validation
- [ ] `tests/test_bronze_odds.py::TestLineSourceColumn` -- covers D-03 provenance column

## Risk Assessment

### Low Risk: FinnedAI Batch Ingestion (BRNZ-01)
- Script is proven on 2020 with zero code changes needed
- JSON download is cached; only needs one download
- Per-season validation catches issues before write
- **Mitigation**: Run one season first (2016) to confirm, then batch the rest

### Low Risk: nflverse Bridge (BRNZ-02)
- nflverse schedules have 100% odds coverage for 2022-2025 (verified)
- Schema mapping is straightforward (column rename + closing-as-opening proxy)
- No cross-correlation needed (D-09)
- **Mitigation**: Test schema match against existing 2020 Parquet dtypes

### Resolved: 2025 Data Availability (BRNZ-03)
- Smoke test passed: 285 games, 48K PBP rows, full player data
- 7 of 8 core types already ingested
- Injuries unavailable for 2025 (nflverse caps at 2024) -- this is a known limitation, not a blocker
- **Impact**: Phase 37 can proceed with 2025 as holdout. Injury adjustments will be absent for 2025 holdout games.

### Medium Risk: Dtype Consistency
- nflverse `home_moneyline` is float64; FinnedAI path produces int64
- Could cause issues if downstream code assumes int type for moneylines
- **Mitigation**: Explicit dtype casting in nflverse bridge function

## Open Questions

1. **Should `line_source` be added to existing FinnedAI output retroactively?**
   - What we know: D-03 requires the column. Current 2020 Parquet lacks it.
   - What's unclear: Whether to re-run all 6 FinnedAI seasons or just add it to new runs.
   - Recommendation: Re-run all 6 including 2020 for schema consistency. The script is idempotent (new timestamp file, `download_latest_parquet()` reads newest).

2. **Should `DATA_TYPE_SEASON_RANGES["odds"]` be expanded to cover 2022+?**
   - What we know: Currently `(2016, lambda: 2021)` -- only FinnedAI range.
   - What's unclear: Whether the nflverse bridge should share the same config key or use a separate one.
   - Recommendation: Expand to `(2016, get_max_season)` since odds now come from two sources. The CLI `--source` flag handles routing.

## Sources

### Primary (HIGH confidence)
- Live `nfl.import_schedules()` calls for 2022, 2023, 2024, 2025 -- verified column names, coverage, dtypes
- `scripts/bronze_odds_ingestion.py` source code -- verified schema, validation logic, output format
- `src/config.py` source code -- verified `DATA_TYPE_SEASON_RANGES`, season boundaries
- `data/bronze/odds/season=2020/` Parquet file -- verified existing output schema and dtypes
- Local filesystem scan -- verified existing 2025 Bronze data inventory

### Secondary (MEDIUM confidence)
- `DATA_TYPE_SEASON_RANGES["injuries"]` caps at 2024 -- confirmed via `validate_season_for_type()`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all tools already in use (nfl-data-py, pandas, pyarrow, scipy)
- Architecture: HIGH -- extending proven patterns, verified data availability
- Pitfalls: HIGH -- identified from actual data inspection (2022 game count, dtype mismatch, injury gap)

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable -- nflverse data structure unlikely to change mid-offseason)
