# Phase 18: Historical Context - Context

**Gathered:** 2026-03-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Create a static Silver dimension table linking NFL Combine measurables and draft capital to player IDs for rookie evaluation and breakout modeling. Combine and draft data (2000-2025) are joined via pfr_id, with composite scores (speed score, burst score, BMI, catch radius proxy) and Jimmy Johnson trade value chart. Output as a single flat Parquet file at `data/silver/players/historical/combine_draft_profiles.parquet`. Expose via a new CLI script (`silver_historical_transformation.py`). Register new Silver output path in config.py.

</domain>

<decisions>
## Implementation Decisions

### Derived Metrics
- Store BOTH raw combine measurables AND computed composite scores
- Raw columns preserved: forty, bench, vertical, broad_jump, cone, shuttle, ht, wt
- Composite scores to compute:
  - **Speed score**: weight x 200 / (forty^4) — Bill Barnwell's standard formula
  - **BMI**: weight / height_inches^2 (convert ht string to inches first)
  - **Burst score**: vertical + broad_jump, normalized by position
  - **Catch radius proxy**: height in inches (no arm length available in Bronze data — height is the proxy)
- All composite scores also stored as position-percentile columns (e.g., speed_score_pos_pctl = percentile rank within position group across all years in the table)
- **Draft capital**: Jimmy Johnson trade value chart — hardcode as a lookup dict mapping pick number (1-262) to trade value points (Pick 1 = 3000, Pick 32 = 590, Pick 100 = 76, etc.)

### Join Strategy
- Two-step join via pfr_id:
  1. Combine ←→ draft_picks: full outer join on pfr_id (combine has pfr_id, draft_picks has pfr_player_id)
  2. Result → roster linkage via gsis_id (from draft_picks) for downstream player matching
- **Undrafted combine attendees**: included with NaN draft capital (left-join preserves UDFA combine data)
- **Drafted players without combine**: included with NaN measurables (full outer captures both populations)
- One row per player in final output — no duplicates
- Log match rates at INFO level; log unmatched players at WARNING level
- Never fail pipeline on match quality

### Season Scope
- Include ALL draft classes 2000-2025 (26 years of data)
- Covers all active players in PLAYER_DATA_SEASONS (2020-2025) plus historical players for modeling
- Position percentiles computed across all years in the table (cross-era normalization)

### Output Structure
- Single flat Parquet file: `data/silver/players/historical/combine_draft_profiles.parquet`
- No season partitioning — this is a dimension table, not a fact table
- Full regeneration on each run (table is small, ~8K rows)
- Timestamped filename follows existing convention: `combine_draft_profiles_YYYYMMDD_HHMMSS.parquet`

### CLI Design
- New script: `scripts/silver_historical_transformation.py`
- No --seasons flag — always processes all available Bronze combine/draft data (2000-2025)
- Idempotent: regenerates the full dimension table on every run
- Follows existing Silver CLI patterns (argparse, local Bronze read, transform, local Silver write, optional S3)

### Claude's Discretion
- Exact Jimmy Johnson chart values (well-documented, use standard source)
- Height string parsing logic (e.g., "5-11" → 71 inches)
- Burst score position normalization approach
- Column naming for composite scores and percentiles
- How to handle missing/null measurables when computing composites (NaN propagation vs skip)
- Module organization: new src/historical_profiles.py or inline in CLI script

</decisions>

<specifics>
## Specific Ideas

- Speed score is the gold standard combine composite in NFL analytics — it's the primary feature for RB/WR draft evaluation models
- Jimmy Johnson chart is the classic reference; while Rich Hill/OTC charts exist, Jimmy Johnson is most widely used in fantasy football analytics
- Position percentiles enable "this WR ran a 93rd percentile forty for his position" type analysis — critical for rookie/breakout identification
- Catch radius proxy using height alone is a reasonable simplification — height correlates ~0.85 with actual catch radius per NFL combine research

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `nfl_data_adapter.py:fetch_combine()` — Bronze combine reader (seasons 2000+)
- `nfl_data_adapter.py:fetch_draft_picks()` — Bronze draft picks reader (seasons 2000+)
- `config.py:SILVER_PLAYER_S3_KEYS` — registration pattern for new Silver datasets
- `silver_team_transformation.py` — CLI pattern (argparse, local Bronze read, transform, write)
- `utils.py:download_latest_parquet()` — read convention for timestamped files

### Established Patterns
- Local-first storage with optional S3 upload
- Timestamped filenames: `{dataset}_{YYYYMMDD_HHMMSS}.parquet`
- `_read_local_bronze()` helper pattern from silver_team_transformation.py
- Match rate logging at INFO/WARNING levels (Phase 17 pattern)

### Integration Points
- Bronze combine at `data/bronze/combine/season=YYYY/`
- Bronze draft_picks at `data/bronze/draft_picks/season=YYYY/`
- `config.py` — register new SILVER_PLAYER_S3_KEYS entry for 'historical_profiles'
- Join key: pfr_id (shared between combine and draft_picks), gsis_id (draft_picks → roster linkage)
- Downstream: projection engine and future ML models consume this as a static lookup table

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 18-historical-context*
*Context gathered: 2026-03-15*
