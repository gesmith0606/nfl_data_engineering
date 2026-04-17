# Phase 60: Data Quality - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix stale rosters, position misclassifications, and projection sanity issues so users see accurate, current player data across the entire site. Covers DQAL-01 through DQAL-04.

</domain>

<decisions>
## Implementation Decisions

### Roster Refresh Strategy
- **D-01:** Daily GHA cron runs `refresh_rosters.py` to pull Sleeper API data and commit updated Gold parquet. Zero manual effort, audit trail in git.
- **D-02:** When refresh finds a player on the wrong team, auto-fix the Gold parquet and log all changes to `roster_changes.log` for review.
- **D-03:** Roster refresh updates both `recent_team` and `position` from Sleeper API in a single pass (covers DQAL-01 and DQAL-02 together).

### Position Classification
- **D-04:** Sleeper API is the canonical position source for all display and projection contexts. When Sleeper disagrees with nfl-data-py, Sleeper wins.
- **D-05:** Position fixes propagate to Gold layer only (projections + website display). Silver/Bronze keep original nfl-data-py positions for historical accuracy and model training stability.

### Sanity Check Scope
- **D-06:** Critical issues (block deployment) = structural absurdities: backup QB in top 5, negative projections, player on wrong team in top 20, missing positions entirely from output.
- **D-07:** Sanity check runs as a CI gate before website deploys. 0 critical = deploy proceeds; any critical = deploy blocked with report.
- **D-08:** Add data freshness checks: Gold parquet age >7 days = warning, Silver data age >14 days = warning. Catches forgotten pipeline runs before they reach users.

### Consensus Data Freshness
- **D-09:** Live-fetch FantasyPros ECR at sanity check runtime for current consensus rankings (using fetch MCP or requests).
- **D-10:** If FantasyPros fetch fails (rate limit, site down), fall back to hardcoded `CONSENSUS_TOP_50` list. Log a warning that live data was unavailable.

### Claude's Discretion
- Warning threshold calibration (exact rank deviation that triggers warning vs info)
- Sanity check output format (JSON report vs text vs both)
- GHA cron schedule timing (time of day for roster refresh)
- Specific FantasyPros endpoint/scraping approach

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roster refresh
- `scripts/refresh_rosters.py` — Existing Sleeper API roster refresh script with team mapping (SLEEPER_TO_NFLVERSE_TEAM dict)
- `src/nfl_data_integration.py` §304-380 — `validate_data()` method for Bronze-level validation patterns

### Sanity checks
- `scripts/sanity_check_projections.py` — Existing consensus comparison with hardcoded CONSENSUS_TOP_50, projection + prediction checks
- `scripts/check_pipeline_health.py` — Existing S3 freshness + file size checks (model for freshness validation)

### Validation
- `scripts/validate_project.py` — Project-level validation script
- `src/nfl_data_adapter.py` — NFLDataAdapter with local-first reads

### Requirements
- `.planning/REQUIREMENTS.md` §DQAL-01 through DQAL-04 — Acceptance criteria for this phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/refresh_rosters.py`: Already fetches Sleeper player DB, maps teams (SLEEPER_TO_NFLVERSE_TEAM), updates Gold parquet. Needs extension to also update positions.
- `scripts/sanity_check_projections.py`: Already has consensus top-50 comparison, projection validation, prediction validation. Needs FantasyPros live fetch and freshness checks added.
- `scripts/check_pipeline_health.py`: Existing freshness check pattern (S3 key age) that can be adapted for local Gold/Silver parquet freshness.
- `.github/workflows/weekly-pipeline.yml`: Existing GHA cron pattern to model the daily roster refresh cron after.

### Established Patterns
- Gold parquet files stored at `data/gold/projections/season=YYYY/` with timestamped filenames
- `download_latest_parquet()` in `src/utils.py` for reading latest file by prefix
- Sleeper API access via `requests` (no auth needed for public endpoints)
- `scripts/refresh_adp.py` already fetches from Sleeper API — similar pattern for roster refresh

### Integration Points
- GHA workflow: new `daily-roster-refresh.yml` cron job
- CI gate: Vercel/Railway deploy hooks or GHA check on push
- Gold parquet: `refresh_rosters.py` already writes to correct location
- Website: projections API reads from Gold parquet — position/team fixes automatically visible after refresh

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 60-data-quality*
*Context gathered: 2026-04-17*
