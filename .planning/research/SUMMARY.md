# Project Research Summary

**Project:** NFL Data Engineering — v1.3 Prediction Data Foundation
**Domain:** NFL analytics / medallion pipeline feature expansion
**Researched:** 2026-03-15
**Confidence:** HIGH

## Executive Summary

The v1.3 milestone adds 9 new feature categories (weather, coaching, special teams, penalties, rest/travel, turnover luck, referee tendencies, playoff context, red zone trip volume) to an already-working Bronze-Silver-Gold medallion pipeline. The central finding across all four research areas is that 7 of 9 features require zero new Bronze ingestion — they derive entirely from schedules data (`temp`, `wind`, `roof`, `away_rest`, `home_rest`, `away_coach`, `home_coach`, `referee`, `div_game`, `game_type`) and from PBP columns already ingested (`penalty`, `fumble`, `fumble_lost`, `interception`, `yardline_100`, `drive`). Only two areas need new data: a static 32-row stadium coordinates table for travel distance, and an `officials` Bronze type for full referee crew data (though the head referee name is already in schedules and is sufficient for the core feature).

The recommended approach is to extend the existing architecture with one new Silver module (`game_context.py`) and four new functions in the existing `team_analytics.py`, producing five new Silver output paths all joined on `[team, season, week]`. The critical infrastructure prerequisite is expanding `PBP_COLUMNS` in `config.py` by approximately 20-25 columns to expose penalty detail, special teams play columns, and fumble recovery attribution — all of which exist in the nflverse PBP dataset but were deliberately excluded when the 103-column curated set was built for EPA analysis. This column expansion must happen first because it unblocks penalty aggregation, special teams metrics, and turnover luck computation.

The primary risks are implementation traps, not data availability. The most consequential: `_filter_valid_plays()` in `team_analytics.py` silently drops all special teams plays (it keeps only pass/run play types), so new special teams functions must use a dedicated filter; penalties are identified by a `penalty == 1` binary flag, not by `play_type == 'penalty'` (which has zero rows in the dataset); and red zone trip volume requires drive-level grouping (`nunique` on `drive` where any play entered `yardline_100 <= 20`), not play-level counting (which inflates counts by 4-5x). Turnover luck is the highest-signal feature in this milestone — fumble recovery is statistically random (~50% long-run rate), and teams far from 50% regress sharply — but computing it correctly requires fumble recovery attribution columns (`fumble_recovery_1_team`) not in the current Bronze PBP.

## Key Findings

### Recommended Stack

No new runtime dependencies are needed for 7 of 9 features. The existing Python 3.9.7 / pandas 1.5.3 / numpy 1.26.4 / pyarrow 21.0.0 / nfl-data-py 0.3.3 stack is sufficient. `import_officials()` already exists in the installed nfl-data-py 0.3.3 and can be wired up as a new Bronze data type without any package changes. Weather data from an external API (meteostat, Open-Meteo) is explicitly not recommended — schedules Bronze already contains game-time temperature and wind speed from official NFL sources, which is more accurate than nearest-weather-station data that an API would return.

**Core technologies:**
- pandas 1.5.3 — all groupby/agg transforms for new Silver metrics — no change from v1.2
- numpy 1.26.4 — haversine distance for travel calculation (6-line implementation, no geopy needed)
- nfl-data-py 0.3.3 — `import_officials()` for referee crew data (already installed, no upgrade needed)
- pyarrow 21.0.0 — column-projected Parquet reads for expanded PBP columns (reduces memory load)

**Conditional addition (defer unless backtesting shows value):**
- meteostat 1.6.8 — only if precipitation/humidity beyond schedules `temp`/`wind` proves predictive in backtesting

See [STACK.md](./STACK.md) for full analysis including PBP column expansion list, stadium coordinate pattern, and alternatives considered.

### Expected Features

**Must have (P1 — table stakes, all derivable from existing Bronze):**
- Weather categorization — wind >15 mph reduces passing EPA 8-12%; every Vegas model includes weather; LOW complexity using schedules `temp`/`wind`/`roof`; dome games get neutral weather via `is_dome` flag
- Rest days differential — peer-reviewed research shows rolling 3-week net rest has more predictive signal than raw rest days; use existing `away_rest`/`home_rest` from schedules; derive `rest_advantage = home_rest - away_rest`
- Penalty aggregation — committed + opponent-drawn penalty rates capture team discipline and scheming advantage; MEDIUM complexity using `penalty == 1` flag from PBP (not `play_type == 'penalty'`, which returns zero rows)
- Turnover luck metrics — highest regression-to-mean signal in NFL analytics (fumble recovery R-squared YoY = 0.01); requires extended PBP columns for fumble recovery attribution
- Red zone trip volume — fills a gap in existing Silver (v1.2 has red zone efficiency rate but not trip count volume); requires drive-level PBP grouping, not play-level
- Referee tendencies — rare differentiator at low cost; referee name already in schedules Bronze; aggregate penalty rates per referee across seasons
- Playoff/elimination context — standings derivable from schedules game results via cumsum; use simple proxies (`win_pct`, `games_behind_division_leader`), not full NFL tiebreaker logic

**Should have (P2 — competitive differentiators, small external data or higher complexity):**
- Special teams metrics — FG%, punt net average, return yards, blocked kicks; requires expanded PBP columns (`field_goal_result`, `kick_distance`, punt columns) and dedicated ST filter
- Travel distance — haversine from 32 static stadium coordinates; extend rest-days signal with cross-country travel and time zone change flags
- Coaching HC change detection — detect mid-season HC changes week-over-week from schedules `home_coach`/`away_coach`; compute tenure and adjustment window flags

**Defer to v1.4+ (P3):**
- Coaching OC/DC tracking — no automated data source; requires 2-4 hours manual CSV curation from Pro Football Reference (scraping violates ToS)
- Turnover-adjusted EPA — play-level classification of "skill" vs. "luck" turnovers; HIGH complexity, depends on turnover luck foundation being validated first
- Penalty type breakdown — requires parsing `desc` text field which is unstructured; aggregate penalty rates capture 90% of the signal

**Anti-features (explicitly excluded after research):**
- External weather API integration — schedules data is more accurate and zero added complexity; only needed for future-game forecasting (a Gold-layer concern)
- Real-time referee assignment tracking — historical tendencies are the actual predictive signal; live scraping adds fragility for marginal timing gain
- Elo ratings — redundant with EPA + SOS + situational splits already in Silver v1.2
- Full NFL tiebreaker logic for playoff context — weeks of development for a feature that matters only in Weeks 15-18; Vegas spread already prices in playoff implications

See [FEATURES.md](./FEATURES.md) for full feature landscape, dependency graph, and prioritization matrix.

### Architecture Approach

The architecture adds one new Silver module (`src/game_context.py`) and four new functions to the existing `src/team_analytics.py`, producing five new Silver output paths all sharing the universal join key `[team, season, week]`. Schedule-derived features (weather, rest/travel, coaching, referee tendencies, playoff context) belong in `game_context.py`, which reads existing schedules Bronze and unpivots home/away game rows into per-team rows via a shared `_unpivot_schedules()` helper. PBP-derived features (penalties, turnover luck, special teams, red zone trips) extend `team_analytics.py` following its established groupby-aggregate-merge-rolling pattern. The Gold layer assembles these into a ~130-column prediction feature vector via left joins on the team-week key.

**Major components:**
1. `src/game_context.py` (NEW) — five functions: `compute_weather_features()`, `compute_rest_travel()`, `compute_coaching_changes()`, `compute_referee_tendencies()`, `compute_playoff_context()`. Writes to `teams/game_context/season=YYYY/`. Requires `STADIUM_COORDINATES` dict added to config.
2. `src/team_analytics.py` (EXTEND) — four new functions: `compute_penalty_metrics()`, `compute_turnover_luck()`, `compute_special_teams_metrics()`, `compute_red_zone_trips()`. Writes to four new Silver paths under `teams/`.
3. `src/config.py` (MODIFY) — expand `PBP_COLUMNS` by ~20-25 columns to `PBP_EXTENDED_COLUMNS`; add five new `SILVER_TEAM_S3_KEYS` entries; add `STADIUM_COORDINATES` dict (32 teams, static).
4. `scripts/silver_game_context_transformation.py` (NEW) — orchestrates game_context functions, writes Silver; parallel to existing silver_team_transformation.py.
5. `scripts/silver_team_transformation.py` (MODIFY) — calls four new team_analytics functions alongside existing ones.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for full component map, data flow diagrams, anti-patterns, join strategy, and 7-phase build order with rationale.

### Critical Pitfalls

1. **PBP 103-column gap blocks penalties, special teams, and turnover luck** — `penalty_type`, `penalty_yards`, `field_goal_result`, `kick_distance`, `fumble_recovery_1_team`, and ~15 more columns exist in nflverse PBP but are not in the current `PBP_COLUMNS`. Create `PBP_EXTENDED_COLUMNS` in config.py; do not replace existing `PBP_COLUMNS`. Must be addressed in Phase 1 before any PBP-derived feature work begins.

2. **`_filter_valid_plays()` silently drops special teams plays** — the existing filter keeps only `play_type in ('pass', 'run')`. Special teams functions must use a dedicated `_filter_special_teams_plays()` keeping `play_type in ('punt', 'kickoff', 'field_goal', 'extra_point')`. Never modify the existing filter — it is tested and correct for its purpose.

3. **`play_type == 'penalty'` returns zero rows** — penalties on nullified plays have `play_type = 'no_play'`; penalties during valid plays keep the underlying play type. Always identify penalty plays via `penalty == 1` flag. Use `penalty == 1 AND penalty_yards != 0` for accepted-only penalties.

4. **Rest days Week 1 distortion** — `away_rest`/`home_rest` correctly show 200+ days for Week 1. Cap at 14 days in feature engineering; add `is_post_bye` flag for rest >= 13 days; add `is_short_rest` flag for rest < 6 days. Always use the existing columns, never recompute from game dates.

5. **Red zone trip play-level overcounting** — drive-level grouping is required: group by `[game_id, posteam, drive]`, check `yardline_100.min() <= 20` per drive, count unique qualifying drives. Expected output is 3-5 trips per team per game. Play-level counting produces 15-20+ and correlates with pace rather than red zone ability.

See [PITFALLS.md](./PITFALLS.md) for all 10 pitfalls with recovery strategies, warning signs, and a "Looks Done But Isn't" verification checklist.

## Implications for Roadmap

Based on dependency analysis from ARCHITECTURE.md's build order and the pitfall-to-phase mapping from PITFALLS.md, a 7-phase structure is recommended. The ordering is driven by hard dependencies (PBP column expansion unblocks three later phases; referee tendencies joins data from both PBP and schedules modules), risk isolation (each phase independently testable), and the principle that infrastructure prerequisites ship before features that depend on them.

### Phase 1: PBP Column Expansion (Infrastructure)
**Rationale:** Hard prerequisite for Phases 2, 3, and 7 — penalties, special teams, and turnover luck all require columns not in current Bronze PBP. Attempting any PBP-derived feature without this causes silent KeyErrors and empty DataFrames. Must be first.
**Delivers:** `PBP_EXTENDED_COLUMNS` config entry (~128 total columns), ingestion or supplemental join of additional PBP columns for 2016-2025, verified column availability in Bronze parquet files.
**Addresses:** Foundational prerequisite for penalty aggregation, special teams metrics, turnover luck.
**Avoids:** Pitfall 2 (missing PBP columns), Pitfall 6 (fumble recovery attribution impossible without `fumble_recovery_1_team`), Pitfall 3 (special teams analysis returning empty frames).

### Phase 2: PBP-Derived Team Metrics (Penalties, Turnover Luck, Red Zone Trips)
**Rationale:** Extends `team_analytics.py` — the project's best-tested, most mature module (847 lines, established groupby-aggregate-merge-rolling pattern). Three features share the same PBP source and the same pattern, so implementing together shares test infrastructure and reduces context-switching cost.
**Delivers:** Three new Silver paths: `teams/penalties/`, `teams/turnover_luck/`, `teams/rz_trips/` with rolling windows (_roll3, _roll6, _std variants via `apply_team_rolling()`).
**Implements:** `compute_penalty_metrics()`, `compute_turnover_luck()`, `compute_red_zone_trips()` in `team_analytics.py`.
**Avoids:** Pitfall 10 (use `penalty == 1` flag not `play_type`), Pitfall 6 (fumble recovery attribution via `fumble_recovery_1_team`), Pitfall 9 (drive-level red zone grouping).

### Phase 3: Special Teams Metrics
**Rationale:** Separate from Phase 2 because special teams require a dedicated filter chain and more complex column combinations (kick_distance + field_goal_result + punt columns + returner columns). Phase 2 validates the extension pattern; Phase 3 applies it to a more complex play-type subset.
**Delivers:** `teams/special_teams/` Silver path — FG%, punt average, kickoff touchback rate, return yards, blocked kick counts, special teams EPA per team-week.
**Implements:** `compute_special_teams_metrics()` and `_filter_special_teams_plays()` in `team_analytics.py`.
**Avoids:** Pitfall 3 (dedicated ST filter required; `_filter_valid_plays()` must not be used or modified).

### Phase 4: Schedule-Derived Context Features (Weather, Rest/Travel, Coaching)
**Rationale:** Creates the new `game_context.py` module and `silver_game_context_transformation.py` script — more infrastructure than Phases 2-3 but reads existing schedules Bronze (no new Bronze dependency). Weather and rest are lowest-complexity features and can be validated quickly before tackling coaching tenure logic.
**Delivers:** New module `src/game_context.py`, new script `scripts/silver_game_context_transformation.py`, `teams/game_context/` Silver path with weather bins, rest advantage, travel distance, coaching tenure, and `STADIUM_COORDINATES` dict in config.py.
**Implements:** `_unpivot_schedules()`, `compute_weather_features()`, `compute_rest_travel()`, `compute_coaching_changes()`.
**Avoids:** Pitfall 1 (external weather API is unnecessary; schedules data is more accurate), Pitfall 5 (cap Week 1 rest at 14 days; add `is_post_bye`, `is_short_rest`, `is_international` flags), Pitfall 4 (HC detection from schedules is automated; OC/DC deferred — no automated source exists).

### Phase 5: Referee Tendencies
**Rationale:** Joins data from two sources (schedules `referee` column + penalty counts from Phase 2 Silver). Can only run after Phase 2 (penalty Silver available) and Phase 4 (game_context module exists to extend). Uses schedules `referee` column directly — the officials Bronze type is not needed for the core feature.
**Delivers:** Referee historical statistics (penalties/game rolling, scoring impact, home bias) added to `teams/game_context/` Silver (or a dedicated `teams/referee/` path).
**Implements:** `compute_referee_tendencies()` in `game_context.py`.
**Avoids:** Pitfall 7 (use schedules `referee` column as primary source; normalize referee name strings; unique count should be ~20-25 active per season, not 50+).

### Phase 6: Playoff/Elimination Context
**Rationale:** Most complex computation in the milestone — requires cumulative within-season standings, division rank computation, and strict look-ahead prevention via `cumsum` with `shift(1)`. Placed last among feature phases because it benefits from all other game_context infrastructure being stable. Use standings proxies, not full NFL tiebreaker logic.
**Delivers:** `wins`, `losses`, `win_pct`, `division_rank`, `games_behind_division_leader`, `is_above_500`, `late_season_contention` added to `teams/game_context/` Silver.
**Implements:** `compute_playoff_context()` in `game_context.py`.
**Avoids:** Pitfall 8 (no full tiebreaker logic; Vegas spread already prices playoff implications; handle ties as W-L-T not W-L; look-ahead bias via `cumsum` + `shift(1)` within season groups).

### Phase 7: Pipeline Health and Integration Testing
**Rationale:** Five new Silver output paths need health monitoring checks and end-to-end integration tests verifying that the Gold prediction feature vector assembles correctly (~130 columns) from the new Silver joins. This is a first-class deliverable, not an afterthought.
**Delivers:** Updated `check_pipeline_health.py` covering all five new Silver paths; integration tests for Gold feature vector assembly; Silver output validation (red zone trips 3-5/game, penalty column presence, referee count sanity, fumble recovery rate near 50%).
**Avoids:** All 13 items from PITFALLS.md "Looks Done But Isn't" checklist become integration test assertions.

### Phase Ordering Rationale

- PBP column expansion first because it is a hard prerequisite for three later phases; silent failures (empty frames, KeyErrors) are the consequence of skipping this step.
- PBP-derived features (Phases 2-3) before schedule-derived (Phase 4) because they extend mature, well-tested code (`team_analytics.py`) — lower risk for early phases.
- Special teams (Phase 3) after core PBP metrics (Phase 2) because it requires a custom filter and is more complex; Phase 2 validates the extension pattern first.
- Schedule features (Phase 4) after PBP features because they require creating a new module — higher infrastructure risk, better done after the simpler extension pattern is proven.
- Referee tendencies (Phase 5) after both PBP and schedule features because it joins Silver from Phase 2 with Bronze schedules data from Phase 4.
- Playoff context (Phase 6) last among features because cumulative standings is the most complex transform and benefits from all infrastructure being stable.
- Health/integration testing (Phase 7) at end to validate the assembled feature vector before any ML or Gold projection work consumes the new Silver data.

### Research Flags

Phases likely needing deeper research or validation during planning:
- **Phase 1 (PBP column expansion):** Verify which of the ~20-25 extended columns are actually populated in nflverse PBP for seasons 2016-2025. Column schema can change between nflverse versions. Run a column audit on a sample season parquet before committing to the full expanded list. Also decide between re-ingestion vs. supplemental-join approach based on local Bronze freshness.
- **Phase 5 (Referee tendencies):** Referee name consistency across seasons needs a normalization pass before aggregation. Unique referee count should be ~20-25 active per season; if much higher, name variants are causing splitting. Build alias lookup table.
- **Phase 6 (Playoff context):** Standings validation requires spot-checking against published standings for at least 2 historical seasons. NFL ties (result == 0) must be handled correctly with the W-L-T formula: (W + 0.5*T) / G.

Phases with standard patterns (skip or minimize research-phase):
- **Phase 2 (PBP team metrics):** Well-established pattern in existing `team_analytics.py`; 3 new functions follow the exact same groupby-aggregate-merge-rolling template as existing `compute_team_epa()` and `compute_red_zone_metrics()`.
- **Phase 3 (Special teams):** Pattern is clear once Phase 2 is working; primary risk is filter selection, which is fully documented.
- **Phase 4 (Schedule features):** Schedules data schema is confirmed against data dictionary; `_unpivot_schedules()` pattern mirrors `compute_venue_splits()` in `player_analytics.py`. Weather, rest, and coaching transforms are date math and conditional logic.
- **Phase 7 (Pipeline health):** Follows existing `check_pipeline_health.py` pattern with new Silver path entries.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All core recommendations verified against installed package versions and local codebase inspection. No new dependencies required for 7 of 9 features. meteostat rated MEDIUM — not yet tested in project. |
| Features | HIGH | All 9 feature categories verified against existing Bronze schema columns in docs/NFL_DATA_DICTIONARY.md and config.py. Predictive value claims for rest differential and turnover luck backed by peer-reviewed sources. |
| Architecture | HIGH | Based on direct inspection of all source files: team_analytics.py (847 lines), player_analytics.py (418 lines), config.py PBP_COLUMNS (lines 156-203), SILVER_TEAM_S3_KEYS, silver_team_transformation.py patterns. |
| Pitfalls | HIGH | All 10 pitfalls verified via direct code inspection: `_filter_valid_plays()` source confirmed, PBP_COLUMNS gaps confirmed, schedules column list confirmed against data dictionary. |

**Overall confidence:** HIGH

### Gaps to Address

- **nfl-data-py archival (September 2025):** The nfl-data-py package was archived by nflverse in September 2025 (MEDIUM confidence from web search). The package is read-only but remains functional on Python 3.9. Long-term migration path is nflreadpy (requires Python 3.10+). Flag for v1.4 planning — do not block v1.3 work on it, but avoid introducing patterns that would be hard to migrate.
- **OC/DC coaching data:** No automated source exists. Head coach change detection from schedules is the automated path. If OC/DC tracking proves valuable after HC tracking is validated, plan 2-4 hours of manual CSV curation from Pro Football Reference (scraping violates their ToS).
- **PBP column backfill strategy:** Two options — (a) re-ingest all 10 seasons of PBP with expanded column set (~2-4 hours, 500+ MB), or (b) ingest supplemental columns only and join on `game_id + play_id`. Option (b) avoids re-downloading but adds join complexity. Decide during Phase 1 planning based on current local Bronze file freshness.
- **meteostat vs. Open-Meteo for future game forecasting:** Schedules weather works for historical analysis, but pre-kickoff game prediction requires forecast-grade weather. This is a Gold-layer concern for a future milestone. Open-Meteo (free, no API key) is the preferred alternative to meteostat when needed.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection — `src/team_analytics.py` (847 lines), `src/player_analytics.py` (418 lines), `src/config.py` PBP_COLUMNS (103 columns, lines 156-203), `_filter_valid_plays()` filter logic confirmed
- `docs/NFL_DATA_DICTIONARY.md` — confirmed schedules columns: temp, wind, roof, surface, away_rest, home_rest, away_coach, home_coach, referee, stadium, div_game, game_type
- nflverse PBP Data Dictionary — full column reference for 370+ PBP columns including penalty, ST, fumble recovery: https://nflreadr.nflverse.com/articles/dictionary_pbp.html
- nfl-data-py source code — verified `import_officials()` in installed v0.3.3: https://github.com/nflverse/nfl_data_py
- nflverse officials raw CSV — 2015+ coverage: https://raw.githubusercontent.com/nflverse/nfldata/master/data/officials.csv
- `.planning/PROJECT.md` — v1.3 milestone requirements

### Secondary (MEDIUM confidence)
- Lopez & Bliss (2024) — rolling 3-week net rest signal, post-2011 CBA analysis: https://www.frontiersin.org/journals/behavioral-economics/articles/10.3389/frbhe.2024.1479832/full
- Harvard Sports Analysis Collective — fumble recovery 50% randomness, referee penalty patterns: https://harvardsportsanalysis.org
- PMC research — turnover margin R-squared year-over-year = 0.01: https://pmc.ncbi.nlm.nih.gov/articles/PMC5969004/
- Sharp Football Analysis — wind >15 mph passing EPA impact: https://www.sharpfootballanalysis.com
- nfl-data-py archival status: https://github.com/nflverse/nfl_data_py (read-only as of September 2025)

### Tertiary (LOW confidence)
- nflpenalties.com — referee tendency concept validation only (used for directional confirmation, not a data source)
- Sports Book Review fatigue index — travel/fatigue signal directional confirmation

---
*Research completed: 2026-03-15*
*Ready for roadmap: yes*
