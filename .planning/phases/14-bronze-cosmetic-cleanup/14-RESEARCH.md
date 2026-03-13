# Phase 14: Bronze Cosmetic Cleanup - Research

**Researched:** 2026-03-12
**Domain:** File system cleanup, documentation accuracy
**Confidence:** HIGH

## Summary

Phase 14 addresses 3 cosmetic inconsistencies left from the backfill phases. All three items are purely housekeeping -- no data content changes, no code logic changes, no new dependencies. The filesystem operations are straightforward (mv files, rm empty dirs, rm duplicate files) and the documentation updates correct known inaccuracies about GITHUB_TOKEN usage.

The existing codebase already handles all three inconsistencies at runtime (download_latest_parquet picks newest file, Silver reader expects season-level paths), so this phase eliminates confusion for humans browsing the data directory and reading documentation.

**Primary recommendation:** Write a single Python cleanup script that handles both filesystem operations (player_weekly normalization + draft_picks dedup), then manually update documentation files. Script provides reproducibility and logging.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- player_weekly: Move parquet files from `data/bronze/players/weekly/season=YYYY/week=0/` up to `data/bronze/players/weekly/season=YYYY/` for seasons 2016-2019. Delete empty `week=0/` directories after move. No rename needed.
- draft_picks: Keep the newer file (later timestamp) per season, delete the older file. 26 seasons affected (2000-2025).
- GITHUB_TOKEN docs: Clarify that nfl-data-py does NOT use GITHUB_TOKEN. The custom StatsPlayerAdapter in `src/nfl_data_adapter.py` DOES use it. Update CLAUDE.md, workflow comments, and Phase 8 references.

### Claude's Discretion
- Script vs manual cleanup approach (script preferred for reproducibility)
- Whether to log deletions/moves to stdout
- Exact wording of documentation updates

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

## Standard Stack

No new libraries needed. This phase uses only:

| Tool | Purpose |
|------|---------|
| Python stdlib (shutil, pathlib, os) | File move/delete operations |
| Manual text editing | Documentation updates |

## Architecture Patterns

### Cleanup Script Pattern

A single-purpose script in `scripts/` that:
1. Takes no arguments (hardcoded paths -- this is a one-time cleanup)
2. Logs every operation to stdout (move X from A to B, delete X)
3. Performs dry-run by default, with `--execute` flag for actual operations
4. Returns summary counts (files moved, files deleted, dirs removed)

```
scripts/bronze_cosmetic_cleanup.py
```

### File Operations

**player_weekly normalization (4 seasons):**
```
BEFORE: data/bronze/players/weekly/season=2016/week=0/player_weekly_20260311_193051.parquet
AFTER:  data/bronze/players/weekly/season=2016/player_weekly_20260311_193051.parquet
```
- Seasons: 2016, 2017, 2018, 2019
- Each has exactly 1 file in `week=0/`
- After move, remove empty `week=0/` directory

**draft_picks deduplication (26 seasons):**
```
BEFORE: data/bronze/draft_picks/season=2000/draft_picks_20260309_160416.parquet  (older)
        data/bronze/draft_picks/season=2000/draft_picks_20260309_160425.parquet  (newer -- KEEP)
AFTER:  data/bronze/draft_picks/season=2000/draft_picks_20260309_160425.parquet
```
- Seasons: 2000-2025 (26 total)
- Each has exactly 2 files; delete the one with the earlier timestamp
- Timestamp is in the filename: `_YYYYMMDD_HHMMSS.parquet`

### Documentation Updates

Files that contain inaccurate GITHUB_TOKEN claims requiring correction:

| File | Current Claim | Correction |
|------|---------------|------------|
| `CLAUDE.md` | No explicit GITHUB_TOKEN claim | Add note in Configuration section if needed |
| `.planning/REQUIREMENTS.md` line 13 | "GITHUB_TOKEN configured for nfl-data-py downloads" | Clarify: configured for StatsPlayerAdapter, GHA, gh CLI (not nfl-data-py) |
| `.planning/ROADMAP.md` line 45 | "nfl-data-py downloads use authenticated requests" | Clarify: nfl-data-py does NOT use GITHUB_TOKEN |
| `.planning/research/SUMMARY.md` | "Set GITHUB_TOKEN for 5000/hr limit" | Clarify this applies to StatsPlayerAdapter and gh CLI, not nfl-data-py |
| `.planning/research/PITFALLS.md` | Multiple references implying nfl-data-py uses token | Add clarification notes |

Note: `.planning/phases/08-*` files already contain accurate nuanced documentation (Phase 8 verification correctly noted the limitation). The Phase 8 research files are historical records and should NOT be modified -- they correctly discovered the limitation.

### Anti-Patterns to Avoid
- **Modifying historical phase files:** Phase 8 research/verification docs already accurately note the GITHUB_TOKEN limitation. Don't rewrite history.
- **Renaming files during move:** The filenames are correct; only the directory location is wrong.
- **Deleting without logging:** Every delete/move must be printed to stdout for audit trail.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timestamp comparison | String parsing of filenames | Sort filenames lexicographically | Timestamps are `YYYYMMDD_HHMMSS` format -- lexicographic sort is chronological |
| File discovery | Manual path construction | `pathlib.Path.glob()` | Handles edge cases, cross-platform |

## Common Pitfalls

### Pitfall 1: Moving File Over Existing File
**What goes wrong:** If a parquet file already exists at the season level (e.g., from a previous partial cleanup), `shutil.move` could overwrite or fail.
**How to avoid:** Check destination before moving. If destination exists, compare files. Skip with warning if already cleaned.

### Pitfall 2: Deleting the Wrong Draft Picks File
**What goes wrong:** Keeping the older file instead of newer.
**How to avoid:** Sort filenames lexicographically (ascending). The LAST one is newest due to `YYYYMMDD_HHMMSS` format. Delete all but the last.

### Pitfall 3: Git Tracking of Data Files
**What goes wrong:** Data files are in `.gitignore` via the `data/` pattern, so git won't track these changes. But the cleanup script itself should be committed.
**How to avoid:** Commit the script. The file operations happen locally and are not git-tracked (which is correct).

### Pitfall 4: Breaking Silver Reader
**What goes wrong:** Silver reader already expects files at season level (Phase 13 alignment). Moving files FROM week=0 TO season level is the fix, not a break.
**How to avoid:** Verify after cleanup that `silver_player_transformation.py` can still find the files.

## Code Examples

### File Move Pattern
```python
from pathlib import Path
import shutil

base = Path("data/bronze/players/weekly")
for year in range(2016, 2020):
    week0_dir = base / f"season={year}" / "week=0"
    if not week0_dir.exists():
        continue
    for parquet in week0_dir.glob("*.parquet"):
        dest = week0_dir.parent / parquet.name
        if dest.exists():
            print(f"  SKIP (already exists): {dest}")
            continue
        shutil.move(str(parquet), str(dest))
        print(f"  MOVED: {parquet} -> {dest}")
    # Remove empty week=0 directory
    if not any(week0_dir.iterdir()):
        week0_dir.rmdir()
        print(f"  REMOVED empty dir: {week0_dir}")
```

### Draft Picks Dedup Pattern
```python
base = Path("data/bronze/draft_picks")
for season_dir in sorted(base.glob("season=*")):
    files = sorted(season_dir.glob("draft_picks_*.parquet"))
    if len(files) <= 1:
        continue
    # Keep newest (last in sorted order), delete rest
    keep = files[-1]
    for f in files[:-1]:
        f.unlink()
        print(f"  DELETED: {f}")
    print(f"  KEPT: {keep}")
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | (none -- uses defaults) |
| Quick run command | `python -m pytest tests/ -v -x` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map

This phase has no formal requirement IDs (gap closure). Validation is filesystem-based:

| Check | Behavior | Test Type | Automated Command | File Exists? |
|-------|----------|-----------|-------------------|-------------|
| player_weekly paths | No `week=0/` dirs exist for 2016-2019 | smoke | `test ! -d data/bronze/players/weekly/season=2016/week=0` | N/A (shell check) |
| player_weekly files | Files exist at season level for 2016-2019 | smoke | `ls data/bronze/players/weekly/season=2016/*.parquet` | N/A (shell check) |
| draft_picks count | Exactly 1 file per season dir | smoke | `for d in data/bronze/draft_picks/season=*/; do echo $(ls $d/*.parquet \| wc -l) $d; done` | N/A (shell check) |
| existing tests | 71 tests still pass | regression | `python -m pytest tests/ -v` | Yes |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -v -x` (ensure no regressions)
- **Phase gate:** Full suite green + filesystem checks above

### Wave 0 Gaps
None -- no new test files needed. Validation is filesystem inspection after script execution.

## Open Questions

None. All three cleanup items are fully specified with clear before/after states. The CONTEXT.md decisions lock every implementation detail.

## Sources

### Primary (HIGH confidence)
- Direct filesystem inspection of `data/bronze/` -- confirmed exact file counts and paths
- CONTEXT.md -- locked decisions from discuss phase
- Phase 8 verification docs -- confirmed GITHUB_TOKEN limitation is already accurately documented in historical files

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` line 13 -- confirmed inaccurate SETUP-02 wording
- `.planning/ROADMAP.md` line 45 -- confirmed inaccurate Phase 8 success criteria wording

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no libraries needed, stdlib only
- Architecture: HIGH - straightforward file operations with known before/after states
- Pitfalls: HIGH - verified actual filesystem state, edge cases are minimal

**Research date:** 2026-03-12
**Valid until:** indefinite (filesystem state is static until script runs)
