# Phase 32: Bronze Odds Ingestion - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Historical opening and closing lines exist as validated Bronze Parquet, joinable to every nflverse game. SBRO XLSX archives for 2016-2021, `odds` registered as a Bronze data type with schema validation.

</domain>

<decisions>
## Implementation Decisions

### SBRO file acquisition
- **D-01:** Use FinnedAI/sportsbookreview-scraper CSV files as the primary source, not raw SBRO XLSX — pre-scraped data is more stable (SBRO site could go offline), already parsed, and eliminates openpyxl dependency risk
- **D-02:** Script the download via `requests` into `data/raw/sbro/` as a staging area — raw files are retained for reproducibility and debugging data quality issues
- **D-03:** If FinnedAI repo is unavailable or incomplete, fall back to direct SBRO XLSX download with openpyxl parsing — code both paths but FinnedAI first
- **D-04:** Download is a one-time operation (2016-2021 is frozen historical data) — the script should be idempotent with skip-existing logic, not a recurring pipeline step

### Registry integration pattern
- **D-05:** Standalone script `scripts/bronze_odds_ingestion.py` — odds come from external files, not nfl-data-py, so they don't fit the adapter pattern
- **D-06:** Register `odds` in DATA_TYPE_SEASON_RANGES in `src/config.py` (range: 2016-2021) for validation and pipeline health checks
- **D-07:** Follow the same CLI conventions as other Bronze scripts (--season flag, --dry-run, progress output) but with its own download+parse+validate+write pipeline
- **D-08:** Schema validation function in the script that checks required columns exist and types are correct before writing Parquet

### Edge case handling
- **D-09:** Include neutral-site and London games — they are real NFL games with real betting lines; excluding them loses training data and hurts accuracy
- **D-10:** Include playoff games if SBRO covers them — flag with `game_type` column from nflverse join; the prediction model already handles playoff context (Phase 22)
- **D-11:** Missing opening lines within covered seasons → NaN (never zero, never dropped) — downstream feature selection handles NaN gracefully; dropping rows loses the closing line data which is needed for CLV
- **D-12:** Postponed/cancelled games with no final score → exclude from odds output (no prediction target exists)
- **D-13:** Games where SBRO has data but nflverse join fails → log as orphan, do not silently drop — zero orphan tolerance is a success criterion

### Output schema design
- **D-14:** One row per game at Bronze level (not per-team) — this is raw data; per-team reshape with sign flips happens at Silver (Phase 33)
- **D-15:** Required columns: `game_id` (from nflverse join), `season`, `week`, `game_type`, `home_team`, `away_team`, `opening_spread`, `closing_spread`, `opening_total`, `closing_total`
- **D-16:** Include moneylines if SBRO/FinnedAI provides them (`home_moneyline`, `away_moneyline`) — useful for implied probability in v2.2 betting framework; zero incremental cost to capture now
- **D-17:** Include `nflverse_spread_line` and `nflverse_total_line` merged from schedules for inline cross-validation — every row carries its own validation data
- **D-18:** Spread sign convention: home-team perspective (negative = home favored), matching nflverse convention — validate empirically during ingestion with correlation check

### Data quality gates
- **D-19:** Cross-validation gate: Pearson r > 0.95 between SBRO closing spread and nflverse spread_line, AND >95% of games within 1.0 point — script fails if either threshold is not met
- **D-20:** Row count validation: compare games per season against expected nflverse game counts (256 regular season pre-2021, 272 post-2021, plus playoffs) — warn on >5% deviation
- **D-21:** Sign convention check: for games where nflverse spread_line < -7 (clear home favorites), assert SBRO opening spread is also negative — a single sign flip invalidates the entire season's data

### Claude's Discretion
- Exact FinnedAI repo file structure and parsing details (inspect at implementation time)
- Column name mapping from raw SBRO/FinnedAI format to standardized output schema
- Logging verbosity and progress reporting format
- Temporary file handling during download

</decisions>

<specifics>
## Specific Ideas

- Accuracy is the overriding goal — capture every available data point; never drop rows for convenience
- Moneylines captured now (even if unused until v2.2) because re-running ingestion later is waste
- Inline cross-validation (D-17) means every downstream consumer can verify data quality without re-joining schedules
- The one-row-per-game Bronze schema is cleaner raw data; the per-team reshape is a Silver concern with proper sign convention handling

</specifics>

<canonical_refs>
## Canonical References

### Data sources
- `.planning/research/SUMMARY.md` — Full research on SBRO, FinnedAI, nflverse schedules, openpyxl, pitfalls
- `.planning/research/ARCHITECTURE.md` — Component breakdown, join strategy, sign convention validation

### Existing patterns
- `scripts/bronze_ingestion_simple.py` — Registry dispatch pattern, CLI conventions, validation flow
- `src/config.py` — DATA_TYPE_SEASON_RANGES, S3 paths, Bronze configuration
- `src/nfl_data_adapter.py` — Adapter pattern (odds won't use this, but follows its validation approach)
- `src/utils.py` — `download_latest_parquet()`, shared utilities

### Requirements
- `.planning/REQUIREMENTS.md` §ODDS-01, §ODDS-02, §ODDS-03 — Bronze odds requirements

### Validation reference
- `.planning/ROADMAP.md` §Phase 32 Success Criteria — four criteria that must be TRUE

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DATA_TYPE_SEASON_RANGES` in config.py: add `"odds": (2016, 2021)` for validation
- `bronze_ingestion_simple.py` CLI structure: argparse pattern, --season flag, progress printing
- `src/utils.py` timestamp filename pattern: `{name}_{YYYYMMDD}_{HHMMSS}.parquet`
- `requests` library already installed: HTTP download for FinnedAI/SBRO files

### Established Patterns
- Bronze Parquet files: `data/bronze/{type}/season={YYYY}/{filename}_{timestamp}.parquet`
- Schema validation: check required columns exist, warn-never-block at Bronze level
- Season range validation: `validate_season_for_type()` in config.py

### Integration Points
- nflverse schedules already in Bronze: `data/bronze/schedules/season=YYYY/` — join source for game_id, spread_line, total_line
- `check_pipeline_health.py`: will need odds added to its Bronze checks
- Phase 33 (Silver): reads Bronze odds Parquet as input for line movement features
- Phase 34 (CLV): uses nflverse closing lines from schedules, not Bronze odds closing lines

</code_context>

<deferred>
## Deferred Ideas

- No-vig implied probability from moneylines — v2.2 Betting Framework
- 2022-2024 opening lines (paid source like BigDataBall) — post-v2.1 if line movement features prove material
- Real-time odds API integration — v2.2+
- Multi-book line comparison — out of scope

</deferred>

---

*Phase: 32-bronze-odds-ingestion*
*Context gathered: 2026-03-27*
