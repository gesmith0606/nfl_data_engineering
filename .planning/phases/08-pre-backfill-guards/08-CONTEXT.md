# Phase 8: Pre-Backfill Guards - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Config fixes, dependency pins, and rate-limit protection before bulk data ingestion begins. Three requirements: cap injury season range, configure GITHUB_TOKEN for rate limits, and verify dependency pins. No new data types or ingestion runs in this phase.

</domain>

<decisions>
## Implementation Decisions

### Injury season cap (SETUP-01)
- Static lambda in DATA_TYPE_SEASON_RANGES: `"injuries": (2009, lambda: 2024)`
- Simple, explicit — if the source ever returns, update the constant
- validate_season_for_type() already wired into bronze_ingestion_simple.py, so this automatically causes graceful skips

### GITHUB_TOKEN configuration (SETUP-02)
- Environment variable only — set GITHUB_TOKEN in .env (already gitignored)
- python-dotenv already a dependency and load_dotenv() already called
- No startup validation or hard blocking — keep it simple
- nfl-data-py's underlying nflverse downloads respect GITHUB_TOKEN for 5,000 req/hr vs 60 req/hr

### Dependency pinning (SETUP-03)
- nfl_data_py==0.3.3 and numpy==1.26.4 are ALREADY pinned in requirements.txt
- Verify pins exist and add inline comments explaining why (numpy 2.x breaks pandas 1.5.3)
- No constraint file or lock file — exact version pins are sufficient

### Claude's Discretion
- Whether to add a brief comment block at the top of requirements.txt explaining pinning strategy
- Test structure for verifying the injury season cap works as expected

</decisions>

<specifics>
## Specific Ideas

No specific requirements — straightforward config/infrastructure changes with clear success criteria from the roadmap.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `validate_season_for_type()` in config.py: Already validates season ranges and is wired into bronze_ingestion_simple.py — injury cap will work automatically
- `DATA_TYPE_SEASON_RANGES` dict in config.py: All 15 data types registered with (min, max_callable) tuples
- `.env` + python-dotenv: Already set up for environment variable loading

### Established Patterns
- Callable-based max season bounds: All entries use `get_max_season` callable — injury cap follows same pattern with `lambda: 2024`
- Registry dispatch: Adding/modifying data type config is config-only, no code changes needed
- Warn-never-block validation: Bronze accepts raw data; validation is informational

### Integration Points
- `config.py:201` — injuries entry in DATA_TYPE_SEASON_RANGES (change target)
- `requirements.txt:38-39` — nfl_data_py and numpy pins (verify + comment)
- `.env` — GITHUB_TOKEN addition (not committed)
- `bronze_ingestion_simple.py:312` — already calls validate_season_for_type(), no changes needed

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-pre-backfill-guards*
*Context gathered: 2026-03-09*
