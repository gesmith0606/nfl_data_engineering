# Phase 33: Silver Line Movement Features - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Line movement features exist as Silver per-team-per-week rows ready for feature assembly. Compute spread/total movement, categorize magnitude, detect steam moves (NaN where timestamps unavailable), integrate opening_spread and opening_total into feature_engineering.py as pre-game features. Phase 32 Bronze odds Parquet is the input.

</domain>

<decisions>
## Implementation Decisions

### Per-team sign convention for directional features
- **D-01:** Symmetric features (same value for both teams): `spread_move_abs`, `total_shift`, `total_move_abs`, `spread_magnitude`, `total_magnitude`, `crosses_key_spread` — these are properties of the game, not directional
- **D-02:** Directional features (sign-flipped for away team): `opening_spread`, `closing_spread`, `spread_shift` — home team gets the value as-is (home-team perspective from Bronze), away team gets the negated value
- **D-03:** Opening/closing totals are symmetric (same for both teams) — no sign flip needed
- **D-04:** The reshape produces columns: `team`, `opponent`, `season`, `week`, `game_id`, `game_type`, plus all market features. `is_home` boolean column for downstream filtering

### Feature temporal categorization
- **D-05:** Pre-game knowable features (add to `_PRE_GAME_CONTEXT` in feature_engineering.py): `opening_spread`, `opening_total` — these are known before kickoff and safe for live prediction
- **D-06:** Retrospective-only features (MUST NOT be in `_PRE_GAME_CONTEXT`): `spread_shift`, `total_shift`, `spread_move_abs`, `total_move_abs`, `spread_magnitude`, `total_magnitude`, `crosses_key_spread`, `closing_spread`, `closing_total` — all depend on the closing line which is only known at kickoff
- **D-07:** Retrospective features are available for historical backtesting and ablation (Phase 34) but excluded from `get_feature_columns()` for live predictions by design — the `_is_pre_game_context()` filter handles this automatically
- **D-08:** Add a code comment block in market_analytics.py and feature_engineering.py explicitly documenting which features are pre-game vs retrospective, so future developers don't accidentally enable closing-line leakage

### Key number crossing features
- **D-09:** Include `crosses_key_spread` boolean (movement crosses 3, 7, or 10) — these are the NFL key numbers where point probability spikes; a line moving through them signals strong market action
- **D-10:** Include `crosses_key_total` boolean (movement crosses common total thresholds 41, 44, 47) — less established than spread key numbers but captures market conviction on totals
- **D-11:** Both are symmetric features (same value for home and away — the game either crossed a key number or it didn't)

### Coverage gap handling (2022-2024)
- **D-12:** Silver market_data transform only runs for seasons where Bronze odds data exists (2016-2021) — it reads from `data/bronze/odds/season=YYYY/` and if no file exists, that season is skipped
- **D-13:** Feature assembly in feature_engineering.py handles missing Silver market_data gracefully — when the left join finds no market_data row for a team/week, all market columns become NaN. This is the standard pattern used by all Silver sources
- **D-14:** No synthetic data or imputation for 2022-2024 — NaN is honest and lets feature selection handle sparsity. Accuracy is the priority; fabricated data would corrupt the model

### Steam move handling
- **D-15:** Steam move flag (`is_steam_move`) set to NaN for all rows — FinnedAI data has no timestamps, so steam moves cannot be computed. This satisfies success criterion 3 ("explicitly set to NaN where timestamps are unavailable")
- **D-16:** The column exists in the schema (not omitted) so downstream consumers don't break when a future data source provides timestamps

### Claude's Discretion
- Exact module structure of market_analytics.py (function decomposition)
- Silver CLI script argument handling details
- Logging verbosity and progress reporting
- Test fixture design for the reshape logic

</decisions>

<specifics>
## Specific Ideas

- Accuracy is the overriding goal — include key number crossing features because they capture meaningful NFL betting market signals
- The temporal categorization (D-05 through D-08) is the single most important design decision in this phase — getting it wrong invalidates all Phase 34 ablation results
- The feature_engineering.py integration should follow the exact same join pattern used by the 9 existing Silver sources — no special-casing for market data

</specifics>

<canonical_refs>
## Canonical References

### Existing patterns (MUST follow)
- `src/team_analytics.py` — Silver transform module pattern: shared utilities, compute functions, per-season output
- `scripts/silver_team_transformation.py` — Silver CLI pattern: argparse, season loop, progress output
- `src/feature_engineering.py` lines 362-404 — `_PRE_GAME_CONTEXT`, `_PRE_GAME_CUMULATIVE`, `get_feature_columns()` filter logic
- `src/config.py` line 490 — `SILVER_TEAM_LOCAL_DIRS` dict (add `market_data` entry)

### Input data
- `scripts/bronze_odds_ingestion.py` — Bronze odds schema: game_id, season, week, home_team, away_team, opening_spread, closing_spread, opening_total, closing_total, home_moneyline, away_moneyline, nflverse_spread_line, nflverse_total_line
- `data/bronze/odds/season=2020/` — Example Bronze output (244 rows, 14 columns)

### Requirements
- `.planning/REQUIREMENTS.md` §LINE-01, §LINE-02, §LINE-03 — Line movement requirements

### Research
- `.planning/research/SUMMARY.md` §Expected Features — feature list with pre-game vs retrospective categorization
- `.planning/research/SUMMARY.md` §Critical Pitfalls — leakage, sign convention, key numbers

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SILVER_TEAM_LOCAL_DIRS` in config.py: add `"market_data": "teams/market_data"` for discovery
- `feature_engineering.py` Silver source loop: iterates `SILVER_TEAM_LOCAL_DIRS`, reads latest Parquet per season, left joins on [team, season, week] — market_data plugs in with zero special-casing
- `team_analytics.py` module structure: shared utilities at top, compute functions in middle, orchestration at bottom
- `download_latest_parquet()` in utils.py: reads Bronze odds input

### Established Patterns
- Silver Parquet files: `data/silver/teams/{source}/season={YYYY}/{source}_{timestamp}.parquet`
- Per-team-per-week reshape: used in game_context.py (weather/rest are per-team) — same pattern applies here
- Rolling windows: NOT applicable for market_data — line movement is a single-game property, not a trend

### Integration Points
- `src/config.py` SILVER_TEAM_LOCAL_DIRS: needs `market_data` entry
- `src/feature_engineering.py` `_PRE_GAME_CONTEXT`: needs `opening_spread`, `opening_total`
- `src/feature_engineering.py` Silver source loop: auto-discovers new source via config
- Phase 34 (CLV): reads closing lines from nflverse schedules, not from Silver market_data

</code_context>

<deferred>
## Deferred Ideas

- No-vig implied probability from moneylines — v2.2 Betting Framework
- Rolling average of line movement across games (momentum signal) — add to backlog if ablation shows movement features are material
- Multi-book consensus features — out of scope

</deferred>

---

*Phase: 33-silver-line-movement-features*
*Context gathered: 2026-03-27*
