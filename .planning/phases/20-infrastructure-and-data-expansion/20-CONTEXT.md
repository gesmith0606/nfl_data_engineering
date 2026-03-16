# Phase 20: Infrastructure and Data Expansion - Context

**Gathered:** 2026-03-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Expand Bronze data to unblock all v1.3 Silver features. Three deliverables: (1) expand PBP_COLUMNS to include penalty detail, special teams, fumble recovery, and drive columns; (2) ingest officials data as a new Bronze type; (3) add stadium coordinates to config. No Silver transforms in this phase — those are Phases 21-23.

</domain>

<decisions>
## Implementation Decisions

### PBP Column Expansion (INFRA-01)
- Extend the existing `PBP_COLUMNS` list in `config.py` by appending ~25 new columns — do NOT create a separate `PBP_EXTENDED_COLUMNS` list
- New columns include: `penalty_type`, `penalty_yards`, `penalty_team`, `penalty_player_id`, `penalty_player_name`, `special_teams_play`, `st_play_type`, `kickoff_attempt`, `punt_attempt`, `kick_distance`, `return_yards`, `field_goal_result`, `field_goal_attempt`, `extra_point_result`, `extra_point_attempt`, `punt_blocked`, `fumble_forced`, `fumble_not_forced`, `fumble_recovery_1_team`, `fumble_recovery_1_yards`, `fumble_recovery_1_player_id`, `kickoff_returner_player_id`, `punt_returner_player_id`, `drive_play_count`, `drive_time_of_possession`
- Verify each column exists in the nflverse PBP schema before adding
- Re-ingest all PBP data for 2016-2025 with the expanded column set (full re-download, not supplement)
- Existing Silver pipeline must still pass all 289 tests after expansion (new columns are additive — no existing columns removed)

### Officials Bronze Ingestion (INFRA-02)
- Add `officials` as a new Bronze data type using `nfl.import_officials()` from nfl-data-py 0.3.3
- Follow the existing registry dispatch pattern in `bronze_ingestion_simple.py` — new entry in `DATA_TYPE_REGISTRY`
- Add corresponding entry in `DATA_TYPE_SEASON_RANGES` in `config.py` (2015-2025 based on nflverse coverage)
- Officials data joins to schedules via `game_id` — include `game_id`, `official_name`, `official_position`, `jersey_number` columns
- The `referee` column already in schedules Bronze is the simpler fallback for head referee tendencies; officials data adds position-specific crew detail for Phase 23

### Stadium Coordinates (INFRA-03)
- Store as a static dict `STADIUM_COORDINATES` in `config.py` — approximately 35 entries (32 team home stadiums + international venues like London, Munich, Mexico City)
- Each entry: team abbreviation -> (latitude, longitude, timezone, venue_name)
- Include timezone for time zone differential computation in Phase 22
- Haversine distance will be computed in Phase 22's `game_context.py` module — this phase just provides the lookup data
- Sanity check: NYJ-to-LAR should compute to approximately 2,450 miles

### Claude's Discretion
- Exact list of ~25 PBP columns to add (verify against nflverse schema, err on the side of including more)
- Whether to add an `NFLDataAdapter.fetch_officials()` method or wire directly in the registry
- Ordering and grouping of new columns within `PBP_COLUMNS` (suggest grouping by category: penalty, ST, fumble recovery, drive)
- Whether to include `fumble_recovery_2_*` columns (rare but exists in nflverse)
- International venue list (London Tottenham, London Wembley, Munich, Mexico City, Sao Paulo, Madrid — confirm which have hosted NFL games)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Infrastructure Requirements
- `.planning/REQUIREMENTS.md` — INFRA-01, INFRA-02, INFRA-03 define the three deliverables
- `.planning/ROADMAP.md` — Phase 20 success criteria (4 items including regression test requirement)

### Research
- `.planning/research/SUMMARY.md` — Executive summary: 7 of 9 features need zero new Bronze; only officials + stadium coords are new
- `.planning/research/PITFALLS.md` — Pitfall 2 (PBP column selection) is critical: existing 103 columns miss penalty/ST/turnover detail
- `.planning/research/STACK.md` §Officials Data — `import_officials()` details, column schema, join pattern via game_id
- `.planning/research/FEATURES.md` — Feature dependency graph showing Phase 20 unblocks Phases 21-23

### Existing Code
- `src/config.py` — `PBP_COLUMNS` (line 156), `DATA_TYPE_SEASON_RANGES` (line 221), `DATA_TYPE_REGISTRY` pattern
- `scripts/bronze_ingestion_simple.py` — `DATA_TYPE_REGISTRY` dict (line 28) for adding officials
- `src/nfl_data_integration.py` — `NFLDataFetcher` class with existing fetch methods pattern

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DATA_TYPE_REGISTRY` in `bronze_ingestion_simple.py` — dispatch pattern for adding `officials` as a new Bronze type (config-only addition)
- `DATA_TYPE_SEASON_RANGES` in `config.py` — season validation for the new officials type
- `PBP_COLUMNS` list in `config.py` — extend in place with ~25 new columns (currently 103 columns at line 156)
- `NFLDataFetcher` class — follows consistent fetch method pattern; may need `fetch_officials()` method
- `TEAM_DIVISIONS` dict in `config.py` — same pattern for `STADIUM_COORDINATES` static dict

### Established Patterns
- Registry dispatch: adding a data type is config-only (registry entry + season range)
- `download_latest_parquet()` for reading Bronze files — officials will follow this pattern
- Local-first storage: `data/bronze/` mirrors S3 structure
- Timestamp-suffixed filenames: `dataset_YYYYMMDD_HHMMSS.parquet`

### Integration Points
- `PBP_COLUMNS` is used by `fetch_play_by_play()` in `nfl_data_integration.py` — expanding it automatically flows through existing ingestion
- Officials S3 path needs a new entry in `PLAYER_S3_KEYS` (or a new `GAME_S3_KEYS` section)
- Stadium coordinates will be consumed by Phase 22's `game_context.py` — just provide the lookup

</code_context>

<specifics>
## Specific Ideas

- PBP re-ingestion is a one-time ~500MB+ download across 10 seasons — batch ingestion with `--skip-existing` won't help since we need to replace existing files with expanded column sets
- The `penalty == 1` flag (binary) is already in PBP_COLUMNS; the new columns add the detail (type, yards, team, player)
- Research confirmed `_filter_valid_plays()` in `team_analytics.py` drops ST plays — this is fine for Phase 20 (no Silver transforms here), but Phase 21 must use a dedicated ST filter

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 20-infrastructure-and-data-expansion*
*Context gathered: 2026-03-15*
