# Phase 14: Bronze Cosmetic Cleanup - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Clean up 3 cosmetic inconsistencies left from backfill phases: normalize player_weekly paths, deduplicate draft_picks files, and fix GITHUB_TOKEN documentation. No data content changes — only file locations, duplicate removal, and doc accuracy.

</domain>

<decisions>
## Implementation Decisions

### player_weekly week=0 normalization
- Move parquet files from `data/bronze/players/weekly/season=YYYY/week=0/` up to `data/bronze/players/weekly/season=YYYY/` for seasons 2016-2019
- Delete empty `week=0/` directories after move
- Pattern should match 2020-2025 which store files directly at season level
- No rename needed — just `mv` the file up one level

### draft_picks deduplication
- Keep the newer file (later timestamp: `_160425`/`_160426`/etc.) per season — it's the latest ingestion
- Delete the older file (earlier timestamp: `_160416`/`_160417`/etc.)
- 26 seasons affected (2000-2025), each with exactly 2 files
- `download_latest_parquet()` already picks newest, so this is purely cosmetic cleanup

### GITHUB_TOKEN documentation
- nfl-data-py (v0.3.3) does NOT use GITHUB_TOKEN for its downloads — it fetches from nflverse repos without auth
- The custom `StatsPlayerAdapter` in `src/nfl_data_adapter.py` DOES use GITHUB_TOKEN for direct GitHub API calls (stats_player tag)
- Update documentation to clarify: GITHUB_TOKEN is used by (1) the stats_player adapter, (2) GitHub Actions workflows, and (3) `gh` CLI — NOT by nfl-data-py
- Update CLAUDE.md, workflow comments, and any Phase 8 references that overstate GITHUB_TOKEN's role

### Claude's Discretion
- Script vs manual cleanup approach (script preferred for reproducibility)
- Whether to log deletions/moves to stdout
- Exact wording of documentation updates

</decisions>

<specifics>
## Specific Ideas

No specific requirements — all 3 items are clear-cut cleanup with obvious correct approaches.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `download_latest_parquet()` in `src/utils.py`: Already handles duplicates by picking newest timestamp — confirms dedup approach is safe
- `bronze_ingestion_simple.py`: Registry-based ingestion with `week_partition` flag — can verify correct path pattern

### Established Patterns
- Bronze data at `data/bronze/{type}/season=YYYY/` (season-level) or `data/bronze/{type}/season=YYYY/week=WW/` (week-partitioned)
- `week_partition` registry flag determines which pattern a data type uses
- player_weekly is NOT week-partitioned (seasonal aggregation) — week=0 was a bug

### Integration Points
- Silver reader in `silver_player_transformation.py` reads `data/bronze/players/weekly/season=YYYY/` — already expects season-level files (Phase 13 alignment)
- No downstream code reads from `week=0/` path

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 14-bronze-cosmetic-cleanup*
*Context gathered: 2026-03-12*
