# Phase 35: Bronze Data Completion - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

All Bronze odds and 2025 season data exist as validated Parquet files, providing complete raw inputs for Silver transformations. Covers FinnedAI batch ingestion (2016-2021), nflverse-derived closing-line odds (2022-2025), and full 2025 Bronze ingestion across all 8 core data types.

</domain>

<decisions>
## Implementation Decisions

### nflverse odds bridge shape
- **D-01:** `derive_odds_from_nflverse()` lives in `bronze_odds_ingestion.py` alongside FinnedAI functions — single script owns all odds ingestion
- **D-02:** Carry all available odds columns from nflverse schedules: `spread_line`, `total_line`, `home_moneyline`, `away_moneyline`, plus `home_team`, `away_team`, `gameday`, `game_id`, `season`, `week` — maximizes feature optionality for future model iterations
- **D-03:** Output schema matches FinnedAI Bronze output exactly (same column names, dtypes) plus a `line_source` column (`"finnedai"` or `"nflverse"`) for provenance tracking
- **D-04:** Missing odds rows (international games, rare scheduling edge cases) preserved as NaN — never dropped, never zero-filled. Gradient boosting handles NaN natively; dropping rows loses game-level ground truth
- **D-05:** Seasons 2022-2025 use closing lines as opening-line proxies. `spread_shift` and `total_shift` will be zero downstream (open == close), but `opening_spread` and `opening_total` — the only market features in `_PRE_GAME_CONTEXT` — will be populated. This is the accuracy-optimal choice: populated features with approximate values outperform NaN features that get excluded from splits

### 2025 data fallback
- **D-06:** Try 2025 first via `nfl.import_schedules([2025])` smoke test. If >= 285 regular-season games exist, proceed with 2025 as the new holdout target
- **D-07:** If 2025 is incomplete (< 285 games or missing PBP/player_weekly), keep `HOLDOUT_SEASON=2024` unchanged. Still complete FinnedAI batch ingestion and nflverse 2022+ bridge — the expanded market training coverage (6 seasons vs 1) is a valid deliverable on its own
- **D-08:** Run the 2025 smoke test early in Plan 35-02 (before ingesting all 8 data types) to fail fast and avoid wasted work

### Validation for nflverse-derived odds
- **D-09:** No cross-correlation validation for nflverse-derived odds (nflverse is the source itself — cross-validating against itself is circular)
- **D-10:** Validate via coverage checks: game count per season (>= 285 regular-season games with non-null spread_line), NaN rate for `spread_line` and `total_line` (must be < 5% of games per season), and schema consistency (same columns and dtypes as FinnedAI output)
- **D-11:** Validate playoff coverage separately: minimum 10 games with `week >= 19` per season (ensures postseason odds are captured)

### FinnedAI batch execution
- **D-12:** Run `bronze_odds_ingestion.py --season YYYY` per-season for 2016, 2017, 2018, 2019, 2021 (2020 already ingested). Per-season execution reuses existing validation (r > 0.95 cross-correlation per season) and isolates failures
- **D-13:** No code changes to FinnedAI path — the script is proven on 2020; batch execution is operational, not developmental

### Claude's Discretion
- Exact error messages and logging format for nflverse bridge
- Whether to add `--source` CLI flag or auto-detect season range
- Internal function decomposition within `derive_odds_from_nflverse()`
- Temp file handling during batch runs

</decisions>

<specifics>
## Specific Ideas

- Optimizing for model accuracy: populated approximate features (closing-as-opening proxy) are better than NaN features that get dropped from tree splits
- The real value of this phase is filling 5 seasons of market NaN in the training window — the nflverse bridge for 2022+ is secondary but ensures the new holdout season also has market features

</specifics>

<canonical_refs>
## Canonical References

### Odds ingestion
- `scripts/bronze_odds_ingestion.py` — FinnedAI parser, team mapping (45 entries), cross-validation logic, Bronze output schema
- `src/config.py` — `validate_season_for_type()` for odds season range validation

### Market feature pipeline
- `src/market_analytics.py` — PRE_GAME vs RETROSPECTIVE feature classification; documents which features are safe for pre-game context
- `src/feature_engineering.py` — `_PRE_GAME_CONTEXT` list defining which market columns enter the feature vector (only `opening_spread`, `opening_total`)

### Bronze ingestion patterns
- `scripts/bronze_ingestion_simple.py` — Registry-driven CLI for all 8 core data types; pattern for 2025 ingestion
- `src/nfl_data_adapter.py` — NFLDataAdapter fetch methods; local-first with S3 fallback

### Research
- `.planning/research/SUMMARY.md` — v2.2 research findings, pitfalls, architecture approach

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bronze_odds_ingestion.py`: Complete FinnedAI pipeline (download, parse, map, validate, write) — reuse for batch; extend for nflverse bridge
- `bronze_ingestion_simple.py`: Registry-driven ingestion for all 8 core types — run as-is for 2025
- `FINNEDAI_TO_NFLVERSE` mapping (45 entries): Covers all team name variants including relocations and typos
- `validate_cross_correlation()`: r > 0.95 validation — reuse for FinnedAI seasons only
- `validate_row_counts()`: Game count validation — adapt for nflverse bridge coverage checks

### Established Patterns
- Season-partitioned Parquet: `data/bronze/odds/season=YYYY/odds_YYYYMMDD_HHMMSS.parquet`
- Timestamp-suffixed filenames with `download_latest_parquet()` convention
- Per-season CLI execution: `--season YYYY` flag pattern
- NaN preservation for missing data (D-11 from v2.1: "Missing opening lines preserved as NaN")

### Integration Points
- Bronze odds output feeds `scripts/silver_market_transformation.py` (Phase 36)
- Bronze 2025 data feeds all Silver transformation scripts (Phase 36)
- `line_source` column enables downstream filtering if needed (e.g., ablation by source)

</code_context>

<deferred>
## Deferred Ideas

- Paid odds API for 2022+ opening lines — only warranted if Phase 38 ablation proves opening-line movement materially improves accuracy
- Multi-book line comparison — v4.0+ concern
- Live line snapshot pipeline — production infrastructure concern

</deferred>

---

*Phase: 35-bronze-data-completion*
*Context gathered: 2026-03-28*
