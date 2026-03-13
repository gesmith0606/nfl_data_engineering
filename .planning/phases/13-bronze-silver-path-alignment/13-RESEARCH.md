# Phase 13: Bronze-Silver Path Alignment - Research

**Researched:** 2026-03-12
**Domain:** Local file path alignment between Bronze write paths and Silver read paths
**Confidence:** HIGH

## Summary

Phase 13 addresses four concrete misalignments between how the Bronze ingestion script (`bronze_ingestion_simple.py`) writes data and how the Silver transformation script (`silver_player_transformation.py`) reads it. These are pure code-level path fixes with no library changes, no new dependencies, and no architectural decisions required.

The root cause is that Bronze paths were reorganized in Phase 10 (snap_counts moved from `players/snap_counts/` to `players/snaps/` with week partitioning; schedules moved from `games/` to `schedules/`), but the Silver reader functions were never updated to match. Additionally, `validate_data()` requires `player_id` for snap_counts, but the actual nfl-data-py schema uses `player` (display name) -- this is a known issue documented in MEMORY.md.

**Primary recommendation:** Fix the three Silver reader paths, update validate_data() required columns for snap_counts, and remove the residual old directory.

## Standard Stack

No new libraries or dependencies. This phase modifies only existing Python files:

| File | Change | Purpose |
|------|--------|---------|
| `scripts/silver_player_transformation.py` | Fix `_read_local_bronze()` and `_read_local_schedules()` paths | Align Silver reads with Bronze writes |
| `src/nfl_data_integration.py` | Update `validate_data()` snap_counts required columns | Fix false-negative validation |
| `data/bronze/players/snap_counts/` | Delete directory | Remove 5 residual pre-Phase-10 files |

## Architecture Patterns

### Current Bronze Write Paths (DATA_TYPE_REGISTRY in bronze_ingestion_simple.py)

| Data Type | Bronze Path | Week Partitioned |
|-----------|-------------|------------------|
| `player_weekly` | `players/weekly/season={season}` | No |
| `snap_counts` | `players/snaps/season={season}/week={week}` | Yes |
| `schedules` | `schedules/season={season}` | No |

### Current Silver Read Paths (silver_player_transformation.py)

| Function | Current Read Path | Correct Path |
|----------|-------------------|--------------|
| `_read_local_bronze('weekly', season)` | `players/weekly/season=YYYY/*.parquet` | Correct -- no change needed |
| `_read_local_bronze('snap_counts', season)` | `players/snap_counts/season=YYYY/*.parquet` | **WRONG** -- should be `players/snaps/season=YYYY/week=*/*.parquet` |
| `_read_local_schedules(season)` | `games/season=YYYY/*.parquet` | **WRONG** -- should be `schedules/season=YYYY/*.parquet` |

### Snap Counts: Week-Partitioned Read Pattern

The snap_counts data is week-partitioned (one parquet file per `week=WW/` subdirectory). The Silver reader must concatenate all week files for a given season. The correct glob pattern is:

```python
# Snap counts: read all weeks for a season
pattern = os.path.join(BRONZE_DIR, 'players', 'snaps', f'season={season}', 'week=*', '*.parquet')
files = sorted(globmod.glob(pattern))
if files:
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
```

### validate_data() Column Fix

Current `required_columns` for snap_counts in `nfl_data_integration.py` line 336:
```python
'snap_counts': ['player_id', 'season', 'week'],
```

Actual columns in snap_counts data from nfl-data-py:
```
['defense_pct', 'defense_snaps', 'game_id', 'game_type', 'offense_pct',
 'offense_snaps', 'opponent', 'pfr_game_id', 'pfr_player_id', 'player',
 'position', 'season', 'st_pct', 'st_snaps', 'team', 'week']
```

The data has `player` (display name), not `player_id`. Fix:
```python
'snap_counts': ['player', 'season', 'week'],
```

### Pattern: Data Type to Path Dispatch

Rather than hardcoding paths in `_read_local_bronze()`, consider using a lookup dict matching the Bronze registry pattern. However, given only 3 data types are read by Silver (weekly, snap_counts, schedules), a simple if/elif or dict in the Silver script is sufficient and avoids coupling Silver to the Bronze registry module.

```python
BRONZE_READ_PATHS = {
    'weekly': 'players/weekly/season={season}',
    'snap_counts': 'players/snaps/season={season}/week=*',
    'seasonal': 'players/seasonal/season={season}',
}
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-file parquet read | Custom file scanning | `pd.concat([pd.read_parquet(f) for f in glob])` | Standard pandas pattern, handles schema alignment |
| Path construction | String concatenation | `os.path.join()` with glob patterns | Cross-platform, already used in codebase |

## Common Pitfalls

### Pitfall 1: Forgetting to Concatenate Week-Partitioned Files
**What goes wrong:** Using `files[-1]` (latest single file) for snap_counts only returns one week of data.
**Why it happens:** The existing `_read_local_bronze()` takes the last file only, which works for non-partitioned types but not for week-partitioned data.
**How to avoid:** For snap_counts, glob across all `week=*/` subdirectories and `pd.concat()` all files.
**Warning signs:** snap_df has unexpectedly few rows (one week instead of full season).

### Pitfall 2: Old Directory Left Behind
**What goes wrong:** If the old `players/snap_counts/` directory remains, future code might accidentally read from it.
**Why it happens:** Phase 10 created the new `players/snaps/` path but did not clean up the old one.
**How to avoid:** `rm -rf data/bronze/players/snap_counts/` as part of this phase. Verify with `ls`.

### Pitfall 3: Breaking Existing Silver Output
**What goes wrong:** Changing read paths could introduce regressions if the data schema differs between old and new paths.
**Why it happens:** Old snap_counts files (pre-Phase-10) were not week-partitioned and may have different row counts.
**How to avoid:** After fixing paths, run the full Silver pipeline and verify output row counts match expectations.

## Code Examples

### Fix 1: _read_local_bronze with snap_counts support

```python
def _read_local_bronze(data_type: str, season: int) -> pd.DataFrame:
    """Read the latest parquet file(s) from local Bronze directory."""
    if data_type == 'snap_counts':
        # Snap counts are week-partitioned under players/snaps/
        pattern = os.path.join(BRONZE_DIR, 'players', 'snaps', f'season={season}', 'week=*', '*.parquet')
        files = sorted(globmod.glob(pattern))
        if not files:
            return pd.DataFrame()
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    # Default: single file per season partition
    pattern = os.path.join(BRONZE_DIR, 'players', data_type, f'season={season}', '*.parquet')
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])
```

### Fix 2: _read_local_schedules path correction

```python
def _read_local_schedules(season: int) -> pd.DataFrame:
    """Read schedule data from local Bronze directory."""
    pattern = os.path.join(BRONZE_DIR, 'schedules', f'season={season}', '*.parquet')
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])
```

### Fix 3: validate_data required columns

```python
# In validate_data() required_columns dict:
'snap_counts': ['player', 'season', 'week'],  # was ['player_id', 'season', 'week']
```

## Existing Data Inventory

### Old Paths (to be removed/ignored)

| Path | Files | Status |
|------|-------|--------|
| `data/bronze/players/snap_counts/season=2020-2024/` | 5 files (one per season, non-partitioned) | Remove |
| `data/bronze/games/season=2020-2025/` | 6 files | Kept (legacy, but Silver now reads from `schedules/`) |

### New Paths (correct)

| Path | Coverage | Notes |
|------|----------|-------|
| `data/bronze/players/snaps/season=2016-2025/week=*/` | 10 seasons, week-partitioned | Created in Phase 10 |
| `data/bronze/schedules/season=2016-2025/` | 10 seasons | Created in Phase 10 |
| `data/bronze/players/weekly/season=2016-2025/` | 10 seasons | Correct, Silver already reads this |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.1 |
| Config file | none (pytest runs from root) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SC-1 | snap_counts reads from `players/snaps/` | integration | `python -c "from scripts.silver_player_transformation import _read_local_bronze; df = _read_local_bronze('snap_counts', 2020); print(len(df))"` | No -- manual verification |
| SC-2 | schedules reads from `schedules/` | integration | `python -c "from scripts.silver_player_transformation import _read_local_schedules; df = _read_local_schedules(2020); print(len(df))"` | No -- manual verification |
| SC-3 | validate_data snap_counts passes | unit | `python -m pytest tests/ -k snap -x` | No -- needs test |
| SC-4 | Old snap_counts dir removed | smoke | `test ! -d data/bronze/players/snap_counts` | No -- shell check |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green + Silver pipeline run for at least one season

### Wave 0 Gaps
- [ ] No new test file strictly required -- existing 186 tests cover core functionality
- [ ] Manual verification via Silver pipeline run is the primary validation: `python scripts/silver_player_transformation.py --season 2020`

## Open Questions

None. All four success criteria are well-defined with clear code changes.

## Sources

### Primary (HIGH confidence)
- `scripts/bronze_ingestion_simple.py` lines 28-123 -- DATA_TYPE_REGISTRY with actual Bronze write paths
- `scripts/silver_player_transformation.py` lines 77-93 -- current Silver read functions with wrong paths
- `src/nfl_data_integration.py` lines 331-353 -- validate_data required_columns (snap_counts expects player_id)
- `data/bronze/players/snaps/` directory -- confirmed week-partitioned structure with `player` column (not `player_id`)
- `data/bronze/players/snap_counts/` directory -- confirmed 5 residual pre-Phase-10 files exist

### Secondary (MEDIUM confidence)
- MEMORY.md -- documents known snap_counts schema issue (`player` not `player_id`)
- STATE.md decisions -- confirms Phase 10 registry changes and week_partition flag

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, pure path fixes
- Architecture: HIGH -- paths verified against actual filesystem and Bronze registry
- Pitfalls: HIGH -- all scenarios verified against actual data

**Research date:** 2026-03-12
**Valid until:** Indefinite (paths are stable, no external dependencies)
