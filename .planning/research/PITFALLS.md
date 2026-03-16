# Pitfalls Research

**Domain:** NFL Prediction Data Foundation — Adding weather, coaching, special teams, penalties, rest/travel, turnover luck, referee tendencies, playoff context, and red zone trip features to an existing medallion architecture platform
**Researched:** 2026-03-15
**Confidence:** HIGH (based on direct inspection of nfl-data-py source, nflverse PBP schema, existing codebase patterns, and schedules data dictionary)

## Critical Pitfalls

### Pitfall 1: Weather Data Is Already in Schedules — Do Not Duplicate with External API

**What goes wrong:**
Developers add a separate weather data pipeline (Open-Meteo, Meteostat, OpenWeatherMap) without realizing that nfl-data-py's `import_schedules()` already includes `temp`, `wind`, `roof`, and `surface` columns per game. This creates duplicate, possibly conflicting weather data, wasted API calls, and an unnecessary external dependency. Worse, historical weather APIs often return data for the nearest weather station (possibly miles from the stadium) and require stadium GPS coordinates, timezone handling, and hourly-to-gametime alignment — all of which the nflverse data already handles.

**Why it happens:**
The schedules data dictionary shows `temp` and `wind` as "double, nullable" which looks like it might be sparse. Developers assume they need a richer source. In reality, nflverse sources weather from official NFL game data (since 1999), which is authoritative for outdoor games.

**How to avoid:**
- First, audit existing schedules Bronze data for `temp`/`wind`/`roof`/`surface` null rates across seasons. They are populated for outdoor games from approximately 2000 onward.
- Dome games correctly show NaN for temp/wind (this is correct — dome games have no weather effect).
- Only consider an external weather API if null rate exceeds 20% for outdoor games AND you need forecast-grade data for upcoming games (pre-kickoff predictions).
- If external weather is needed for forecasting (predicting future games), use Open-Meteo's free Historical Weather API with stadium coordinates — but keep the schedules-sourced weather as ground truth for historical analysis.

**Warning signs:**
- Building a stadium_coordinates.csv and weather API pipeline before checking schedules data coverage
- Weather nulls that are actually dome games misinterpreted as missing data
- Two different temperature values for the same game in the pipeline

**Phase to address:**
Weather data ingestion phase — validate schedules coverage first, defer external API unless forecasting is a requirement

---

### Pitfall 2: PBP Column Selection — The 103 Curated Columns Miss Penalty/Special Teams/Turnover Detail

**What goes wrong:**
The existing `PBP_COLUMNS` list in `config.py` includes only `penalty` (binary), `fumble`, `fumble_lost`, and `interception` (binary) — 103 columns curated for EPA/WPA analysis. But deriving penalty aggregation, special teams metrics, and turnover luck requires columns NOT in the curated set: `penalty_type`, `penalty_yards`, `penalty_team`, `penalty_player_id`, `special_teams_play`, `st_play_type`, `kickoff_attempt`, `punt_attempt`, `kick_distance`, `return_yards`, `fumble_forced`, `fumble_not_forced`, `fumble_recovery_1_team`, `fumble_recovery_1_yards`, `kickoff_returner_player_id`, `punt_returner_player_id`, and more.

If you try to compute penalty rates by type or special teams EPA from the existing Bronze PBP data, you will get empty or incorrect results because the columns were never ingested.

**Why it happens:**
The original PBP column curation was optimized for team EPA, WPA, CPOE, and success rate — run/pass plays only. Special teams plays were explicitly filtered out by `_filter_valid_plays()` in `team_analytics.py`. Penalty detail and fumble recovery attribution were not needed for the v1.0-v1.2 features.

**How to avoid:**
- Create a second PBP column set (e.g., `PBP_EXTENDED_COLUMNS`) in `config.py` that adds the approximately 20-25 columns needed for penalty, special teams, and turnover analysis.
- Do NOT replace `PBP_COLUMNS` — it is used by existing ingestion and the curated 103 columns are correct for the existing Silver pipeline.
- Re-ingest PBP with the extended column set into a separate Bronze path (or augment existing files). PBP files are large (approximately 50-100 MB per season); re-ingestion is expensive but necessary.
- Alternatively, ingest the additional columns alongside existing PBP as a "PBP supplement" to avoid re-downloading 10 seasons of full PBP.

**Warning signs:**
- `KeyError: 'penalty_type'` when trying to aggregate penalties from existing Bronze PBP
- Special teams analysis returning zero rows because `_filter_valid_plays()` excludes them
- Fumble recovery team attribution impossible with only `fumble_lost` binary flag

**Phase to address:**
Must be addressed in the very first phase — PBP column expansion is a prerequisite for penalty aggregation, special teams metrics, and turnover luck computation

---

### Pitfall 3: Special Teams Plays Filtered Out by Existing Pipeline

**What goes wrong:**
The existing `_filter_valid_plays()` function in `team_analytics.py` keeps only `play_type in ('pass', 'run')`. Special teams plays have `play_type` values like `punt`, `kickoff`, `field_goal`, `extra_point`, and `no_play` (penalties on special teams). Any special teams metric computation that passes through the shared filter will silently return empty DataFrames.

**Why it happens:**
The filter was correctly designed for EPA-based team metrics where special teams plays are noise. But developers building new features may reuse `_filter_valid_plays()` out of habit or assume it is a general-purpose "clean plays" filter.

**How to avoid:**
- Create separate filter functions for special teams analysis: `_filter_special_teams_plays()` that keeps `special_teams_play == 1` or `play_type in ('punt', 'kickoff', 'field_goal', 'extra_point')`.
- Do NOT modify `_filter_valid_plays()` — it is tested and correct for its purpose.
- Document clearly that special teams metrics require their own filter chain.
- In `team_analytics.py`, add comments noting that the module handles run/pass plays only; special teams belong in a separate module or clearly separated functions.

**Warning signs:**
- Special teams DataFrames with 0 rows after filtering
- Kick return yards or punt return yards all showing as NaN
- Field goal accuracy computed on zero attempts

**Phase to address:**
Special teams metrics phase — create dedicated filter before building any aggregations

---

### Pitfall 4: Coaching Data Requires Manual Curation for Mid-Season Changes and Coordinators

**What goes wrong:**
The schedules data includes `home_coach` and `away_coach` per game, which seems sufficient. But these are head coaches only — no OC or DC. Mid-season coaching changes (firings, interim promotions) are captured game-by-game in schedules, which is correct. However, developers often try to derive "coaching tenure" or "games under current coach" from schedules alone and hit edge cases: bye weeks skip a game (tenure gap), Week 1 coaches may be new hires (no prior games), and the same coach name may appear for different roles across seasons.

The real pitfall is that OC/DC changes — which have huge scheme impact — are not in any nfl-data-py dataset. There is no automated source for coordinator changes.

**Why it happens:**
Head coach is the only coaching role tracked in nflverse schedules. OC/DC tracking requires either manual curation, scraping Pro Football Reference coaching pages, or a third-party API (none of which are free and reliable for historical data).

**How to avoid:**
- Use schedules `home_coach`/`away_coach` for head coach tracking — it is game-level and handles mid-season changes automatically.
- Compute "games under current HC" by grouping consecutive games with the same coach per team, NOT by counting from season start.
- For OC/DC: create a manual CSV dimension table (`coaching_changes.csv`) with columns: `season, team, role (HC/OC/DC), coach_name, start_week, end_week`. Populate for 2016-2025 from Pro Football Reference coaching pages. Accept that this requires approximately 2-4 hours of manual data entry.
- Do NOT attempt to scrape PFR automatically — it violates their ToS and the page structure changes frequently.
- Flag OC/DC data as LOW confidence / incomplete for older seasons.

**Warning signs:**
- Coach tenure calculation returning negative values (bye week gaps)
- "Games under coach" resetting mid-season unexpectedly
- Assuming OC/DC data exists somewhere in nfl-data-py (it does not)

**Phase to address:**
Coaching tracking phase — start with HC from schedules (automated), defer OC/DC to a manual curation sub-task

---

### Pitfall 5: Rest Days Calculation Has Five Hidden Edge Cases

**What goes wrong:**
The schedules data already includes `away_rest` and `home_rest` columns (days of rest for each team). Developers either: (a) ignore these columns and try to compute rest from game dates, introducing bugs, or (b) trust these columns blindly without understanding their edge cases.

The five edge cases:
1. **Week 1**: Rest days are computed from the previous season's last game — typically 200+ days for non-playoff teams, which is meaningless. The column shows this, but it skews averages.
2. **Bye weeks**: The team playing after a bye shows approximately 13-14 days rest, which is correct but needs to be flagged as "post-bye" rather than just a high rest number.
3. **Thursday games**: Short rest (3-4 days) after a Sunday game. The column captures this, but the predictive signal is about the transition, not the absolute number.
4. **International games**: Teams traveling to London/Munich/Madrid/Dublin may have extra travel fatigue not captured in rest days. The `stadium` column can identify international venues, but travel distance is not in the data.
5. **Monday-to-Sunday turnarounds**: 6 days rest looks normal but is short for teams used to a full week.

**Why it happens:**
Rest days as a raw number is a leaky feature — the signal is in the relative rest (your rest vs. opponent rest) and the context (short week after long travel, post-bye, etc.).

**How to avoid:**
- Use the existing `away_rest` and `home_rest` columns — do NOT recompute from game dates.
- Derive features: `rest_advantage = home_rest - away_rest`, `is_short_rest = rest < 6`, `is_post_bye = rest >= 13`, `is_thursday_game = weekday == 'Thursday'`.
- For international games, flag using `stadium` column (look for non-US stadium names like Tottenham Hotspur Stadium, Wembley Stadium, Allianz Arena, etc.) and add a binary `is_international` feature.
- Cap rest days at 14 for feature engineering (anything above 14 is Week 1 or post-bye, which should be handled by dedicated flags).
- For travel distance: create a static lookup of team home stadiums with coordinates, compute great-circle distance to game venue. This requires a 32-row stadium_coordinates table, not a complex pipeline.

**Warning signs:**
- Rest days feature with values >200 (Week 1 not capped)
- Model giving massive weight to rest days feature (likely overfitting to Week 1 noise)
- International game rest looking "normal" despite 5,000+ mile travel

**Phase to address:**
Rest and travel factors phase — derive from existing schedules columns, add travel distance as a static lookup

---

### Pitfall 6: Turnover Luck Requires Fumble Recovery Attribution Not in Curated PBP

**What goes wrong:**
"Turnover luck" in NFL analytics means the gap between forced fumbles and recovered fumbles — since fumble recovery is essentially random (close to 50/50), teams that recover a high percentage of fumbles are "lucky" and will regress. Computing this requires knowing WHO recovered each fumble (offense or defense), which needs `fumble_recovery_1_team` from PBP. The existing curated PBP only has `fumble` and `fumble_lost` — `fumble_lost` tells you the possessing team lost it, but you cannot compute fumble recovery rate for the defensive team without the recovery columns.

Additionally, interception luck (INT rate vs. expected INT rate based on pass location/depth) requires either NGS expected completion or a model — it is not a simple column lookup.

**Why it happens:**
Turnover luck is a second-order derived metric. Developers focus on counting turnovers (easy with existing columns) rather than measuring luck/regression potential (requires recovery attribution).

**How to avoid:**
- Add `fumble_recovery_1_team`, `fumble_recovery_1_yards`, `fumble_forced`, `fumble_not_forced` to the extended PBP column set.
- Compute: `forced_fumbles` (defense), `fumbles_recovered` (defense), `fumble_recovery_rate = recovered / (forced_fumbles + opponent_forced)`. League average is approximately 50%.
- For interception luck: compare actual INT rate to expected INT rate. The simplest proxy is the team's INT rate vs. league average — teams far above average will regress.
- Do NOT use turnover differential as a stable feature — it has among the lowest year-over-year correlation of any NFL stat.

**Warning signs:**
- Using raw turnover differential as a predictive feature (it is noisy, not sticky)
- Fumble recovery rate at 70%+ for a team (lucky, will regress)
- Model treating turnovers as a skill metric rather than a luck-adjusted one

**Phase to address:**
Turnover luck phase — depends on PBP column expansion phase completing first

---

### Pitfall 7: Referee Data from nfl-data-py Uses a Static CSV That May Lag

**What goes wrong:**
`nfl.import_officials()` fetches from a static CSV on GitHub (`nflverse/nfldata/master/data/officials.csv`). This data covers 2015-present and includes `game_id`, `official_name`, `position`, `jersey_number`. However: (a) the CSV may not be updated promptly for the current season, (b) it joins to schedules via `game_id`, and (c) the `referee` column in schedules already has the head referee name per game (going back further than the officials CSV).

Developers may build a complex officials pipeline when the schedules `referee` column is sufficient for "referee crew tendencies" (the crew chief's name identifies the crew).

**Why it happens:**
The separate officials dataset has ALL officials (7 per game), which feels more complete. But for prediction purposes, the referee (crew chief) is the only official whose identity meaningfully correlates with penalty rates — the full crew data adds complexity without proportional signal.

**How to avoid:**
- Start with the `referee` column from schedules (already in Bronze, covers 1999-present).
- Aggregate penalty rates per referee from PBP: join PBP penalty data to schedules via `game_id`, group by `referee`.
- Only use `import_officials()` if you need position-specific analysis (e.g., "this line judge calls more holding penalties") — which is a niche use case.
- Test coverage: the officials CSV starts at 2015; the schedules `referee` column covers all seasons in the data.

**Warning signs:**
- Building a separate officials ingestion pipeline when `referee` is already in schedules
- Officials data missing for recent weeks (CSV update lag)
- Joining officials to PBP requiring a complex game_id + position mapping when you only need crew-level rates

**Phase to address:**
Referee tendencies phase — use schedules `referee` column first, defer full officials ingestion

---

### Pitfall 8: Playoff Context Requires Real-Time Standings That Do Not Exist in Any nfl-data-py Dataset

**What goes wrong:**
Computing "team is eliminated" or "team has clinched playoff berth" at any given week requires: (a) current W-L records for all 32 teams, (b) remaining schedule, (c) tiebreaker rules (head-to-head, division record, conference record, SOS, etc.). This is a combinatorial problem — NFL tiebreakers have approximately 12 levels and depend on multi-team scenarios.

Developers either oversimplify (use W-L record only) or overengineer (implement full tiebreaker logic). Neither is productive for a feature that has marginal predictive value before Week 14.

**Why it happens:**
"Playoff implications" feels like an important feature, but the signal is weak until late in the season. Before Week 12, almost every team is technically alive, so the feature is nearly constant (no signal). After Week 16, the feature is strongly predictive but you only have 2-3 weeks of data.

**How to avoid:**
- Compute standings from schedules: `result > 0` for home win, `result < 0` for away win. Aggregate wins/losses per team through week N-1.
- Use simple proxies instead of full clinch/elimination: `win_pct` (through week N-1), `games_behind_division_leader`, `is_above_500`.
- DO NOT implement full NFL tiebreaker logic — it is a huge effort for minimal predictive gain. ESPN/NFL.com APIs have this, but they are not in nfl-data-py.
- Add a `late_season_contention` binary feature: `win_pct >= 0.400 AND week >= 14` as a simple proxy for "team still cares."
- The most predictive playoff context feature is actually the Vegas line (already in schedules as `spread_line`) — it already prices in playoff implications.

**Warning signs:**
- Spending multiple phases implementing NFL tiebreaker algorithms
- Playoff context feature showing zero variance before Week 12
- Trying to find a "clinch number" API in nfl-data-py (it does not exist)

**Phase to address:**
Playoff context phase — use standings proxies, not full clinch/elimination logic

---

### Pitfall 9: Red Zone Trip Volume Requires Drive-Level Aggregation, Not Play-Level

**What goes wrong:**
Red zone efficiency (already computed in team_analytics.py as `red_zone_success_rate`) measures what happens inside the 20. But red zone TRIP VOLUME — how many times a team reaches the red zone per game — requires drive-level analysis. The PBP `drive` column identifies drives, and `yardline_100 <= 20` identifies red zone plays, but counting trips means counting UNIQUE drives that enter the red zone, not counting red zone plays.

Developers who count red zone plays instead of red zone drives will overcount high-pace teams (more plays per drive) and undercount efficient teams (score quickly on fewer plays).

**Why it happens:**
Play-level aggregation is the default pattern in the existing pipeline. Drive-level aggregation requires grouping by `game_id + posteam + drive` first, then checking if any play in that drive has `yardline_100 <= 20`.

**How to avoid:**
- Group PBP by `game_id`, `posteam`, `drive`.
- For each drive, check `yardline_100.min() <= 20` — if yes, that drive entered the red zone.
- Count distinct red zone drives per team per game, then aggregate to per-game averages.
- Keep both metrics: `rz_trips_per_game` (volume) and `rz_success_rate` (efficiency, already exists).

**Warning signs:**
- Red zone "trips" count much higher than expected (3-5 per team per game is normal, not 15-20)
- Red zone trips correlating perfectly with total plays (measuring pace, not red zone ability)
- Using `yardline_100 <= 20 AND play_type in ('pass', 'run')` without drive grouping

**Phase to address:**
Red zone trip volume phase — can be computed alongside penalty aggregation since both use PBP data

---

### Pitfall 10: PBP `play_type` for Penalty Plays Is Not 'penalty' — It Is 'no_play' or the Underlying Play Type

**What goes wrong:**
Developers expect `play_type == 'penalty'` to identify penalty plays. In nflverse PBP data, there is no `play_type` value of `'penalty'`. Instead, penalties on plays that were nullified show `play_type = 'no_play'`. Penalties that occur during a valid play (e.g., defensive holding on a completed pass) keep the original `play_type` of `'pass'` or `'run'`. The `penalty` column (binary 1/0) is the correct identifier for "a penalty occurred on this play."

This means filtering `play_type == 'penalty'` returns zero rows, and filtering `play_type in ('pass', 'run')` misses penalties that occurred on nullified plays.

**Why it happens:**
The PBP data models plays by what actually happened, not by what flag was thrown. A penalty that nullifies a play results in `play_type = 'no_play'`. This is counter-intuitive if you expect penalties to be a play type.

**How to avoid:**
- Always use the `penalty == 1` binary flag to identify penalty plays, NOT `play_type`.
- For penalty analysis, use: `pbp_df[pbp_df['penalty'] == 1]` to get all plays with penalties.
- Combine with `penalty_type` to categorize by penalty kind (holding, pass interference, etc.).
- For counting "accepted penalties": use `penalty == 1 AND penalty_yards != 0` (some penalties are declined or offset).
- When computing penalty rates alongside EPA metrics, note that nullified plays (`play_type = 'no_play'`) have no EPA — they are excluded from EPA calculations but should be included in penalty rate calculations.

**Warning signs:**
- Zero penalty plays found (filtering on play_type instead of penalty flag)
- Penalty rate calculation that only counts penalties on valid plays, missing all pre-snap and nullifying penalties
- EPA analysis accidentally including penalty yardage as "yards gained"

**Phase to address:**
Penalty aggregation phase — establish the correct filter pattern in the first penalty-related function

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reusing `PBP_COLUMNS` instead of creating `PBP_EXTENDED_COLUMNS` | Avoids PBP re-ingestion | Cannot compute penalties, special teams, or turnover luck | Never — must expand columns |
| Using raw turnover count instead of luck-adjusted | Simpler computation | Noisy feature that hurts model accuracy | Only for initial EDA, never in production features |
| Hardcoding OC/DC data instead of CSV dimension table | Faster initial development | Unmaintainable, no audit trail | Never — use CSV even if small |
| Skipping dome/retractable roof logic in weather features | Simpler weather pipeline | Dome games with NaN weather treated as missing data instead of "no weather effect" | Only if you add `is_dome` binary and treat NaN correctly |
| Computing standings only from wins (ignoring ties) | Simpler W-L calculation | NFL games can tie (rare but happens) — standings will be wrong | Acceptable if you document the approximation |
| Using absolute rest days instead of relative rest advantage | One fewer column | Loses the most predictive rest signal (advantage over opponent) | Never — always compute rest advantage |
| Building a full weather API pipeline | "Complete" weather coverage | Massive complexity for approximately 2pp model improvement; nflverse already has weather | Only if predicting future games where schedules weather is not yet available |
| Implementing full NFL tiebreaker logic | Accurate clinch/elimination scenarios | Weeks of development for a feature that matters only in Weeks 15-18 | Never — Vegas lines already capture this signal |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| PBP penalty columns | Assuming `penalty` binary is sufficient for rate-by-type analysis | Need `penalty_type`, `penalty_yards`, `penalty_team` from extended PBP columns |
| Schedules weather | Treating NaN temp/wind as "missing data" | NaN means dome/closed roof — use `roof` column to disambiguate |
| Officials data | Building separate ingestion pipeline via `import_officials()` | Use `referee` column from schedules (already in Bronze) for crew-level analysis |
| Schedules rest days | Recomputing from game dates using `gameday` | Use existing `away_rest`/`home_rest` columns — they handle edge cases correctly |
| Schedules coaches | Assuming OC/DC data exists somewhere in nfl-data-py | Only HC is available via `home_coach`/`away_coach`; OC/DC requires manual curation |
| PBP special teams | Running special teams plays through `_filter_valid_plays()` | Create dedicated `_filter_special_teams_plays()` — existing filter excludes them |
| nfl-data-py archival | Assuming nfl-data-py will continue to receive updates indefinitely | Package was archived September 2025; plan nflreadpy migration for Python 3.10+ |
| PBP `play_type` for penalties | Expecting penalty plays to have `play_type = 'penalty'` | Penalties show as `play_type = 'no_play'` or the underlying play type — use `penalty == 1` flag |
| Fumble recovery team | Using `fumble_lost` to compute defensive recovery rate | `fumble_lost` is from the possessing team's perspective; need `fumble_recovery_1_team` for defensive attribution |
| International game detection | Checking for `location` column or `home_team` patterns | Check `stadium` column for known international venues (Tottenham Hotspur Stadium, Wembley, Allianz Arena, Azteca, etc.) |
| Referee name consistency | Assuming referee names are standardized across seasons | Check for variations like "Scott Novak" vs. "S. Novak" — apply string normalization |
| Standings ties | Using `result > 0` for wins only | NFL ties exist (result == 0); compute W-L-T or use win percentage formula: (W + 0.5*T) / G |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading full PBP for penalty analysis | 50-100 MB per season, 10 seasons = 500 MB+ in memory | Load only needed columns via `PBP_EXTENDED_COLUMNS` subset with pyarrow column projection | >5 seasons in a single DataFrame |
| Computing standings from scratch each week | O(teams x weeks x seasons) for full standings history | Pre-compute cumulative standings per season, cache as Silver table | >5 seasons with full tiebreaker logic |
| Drive-level red zone grouping on unfiltered PBP | Groupby on millions of rows with string game_id | Filter to `yardline_100 <= 30` first (broader than 20 to catch entry), then groupby | Full PBP without pre-filtering |
| Re-ingesting all 10 seasons of PBP for column expansion | Hours of download time, 500+ MB | Ingest only the ADDITIONAL columns and join to existing PBP on `game_id + play_id`, or ingest as separate supplemental files | Always — never re-download what you have if avoidable |
| Referee tendency windows too small | High variance, unstable referee penalty rate estimates | Use full-season or multi-season aggregation for referee metrics, not 3-game rolling windows (referee only works approximately 16 games/season) | Single-season rolling windows for referees |
| Weather feature binning too granular | Hundreds of unique temp/wind combinations, sparse bins | Bin temperature into ranges (cold <32F, moderate 32-60F, warm >60F) and wind into (calm <10mph, moderate 10-20mph, windy >20mph) | When used as categorical features in a model |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| External weather API key in source code | Key exposure in git history | Use `.env` for any external API keys; existing pre-commit hook blocks key patterns |
| Scraping Pro Football Reference for coaching data | ToS violation, IP ban | Manual data entry or use licensed data sources only |
| Fetching officials CSV from GitHub raw URL without caching | GitHub rate limiting on repeated ingestion runs | Cache locally like other Bronze data; use `skip-existing` pattern from batch ingestion |

## "Looks Done But Isn't" Checklist

- [ ] **Weather features:** Verify dome games have `is_dome=True` and weather features are zeroed/neutralized, NOT left as NaN
- [ ] **Penalty aggregation:** Verify `penalty_type` column is populated (not all NaN) — it requires extended PBP columns not in existing Bronze
- [ ] **Penalty filter:** Verify penalties are identified via `penalty == 1` flag, not `play_type == 'penalty'` (which does not exist)
- [ ] **Special teams metrics:** Verify special teams plays are NOT being filtered out by `_filter_valid_plays()`
- [ ] **Rest advantage:** Verify Week 1 rest days are capped or flagged — raw values of 200+ days will distort feature distributions
- [ ] **Coaching tenure:** Verify bye weeks do not break consecutive-game counting for "games under coach"
- [ ] **Turnover luck:** Verify fumble recovery rate is close to 50% league-wide — if much higher/lower, recovery attribution is wrong
- [ ] **Referee tendencies:** Verify referee names are consistent across seasons (no variant spellings) — unique referee count should be approximately 20-25 active per season
- [ ] **Playoff standings:** Verify standings match known results for at least 2 historical seasons (spot-check against published standings)
- [ ] **Red zone trips:** Verify per-game average is 3-5 per team (not 15-20, which means counting plays not drives)
- [ ] **International games:** Verify London/Munich/Madrid/Dublin games are flagged as international (check `stadium` column values)
- [ ] **PBP column expansion:** Verify extended columns are ingested into a separate path or augmented, NOT overwriting existing 103-column Bronze PBP
- [ ] **Ties in standings:** Verify standings computation handles `result == 0` (ties) correctly, not just wins and losses

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Missing PBP penalty/ST columns | MEDIUM | Re-ingest PBP with extended columns (2-4 hours download for 10 seasons); or ingest supplemental columns only and join on game_id + play_id |
| Broken special teams filter | LOW | Create new filter function; do not modify existing `_filter_valid_plays()` |
| Wrong fumble recovery attribution | LOW | Add recovery columns to PBP extended set; recompute Silver turnover metrics |
| Incorrect standings computation | MEDIUM | Recompute from schedules with tie handling; validate against known published standings |
| OC/DC data missing | HIGH | Manual research and data entry (2-4 hours); no automated recovery path |
| Weather data duplication (external + schedules) | LOW | Remove external pipeline; use schedules data; keep external only for forecasting future games |
| Referee name inconsistency | LOW | String normalization pass on referee names; build alias lookup table |
| Week 1 rest distortion | LOW | Add cap/flag in feature engineering; re-run Silver transform |
| Penalty filter using play_type | LOW | Change filter to use `penalty == 1` flag; re-run penalty aggregation |
| Red zone trips counted as plays | LOW | Change aggregation to drive-level grouping; re-run red zone metrics |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| PBP column expansion needed | Phase 1 (PBP re-ingestion) | `penalty_type`, `special_teams_play`, `fumble_recovery_1_team` columns present in Bronze |
| Penalty play_type confusion | Phase 2 (Penalty aggregation) | Unit test: `penalty == 1` filter returns >0 rows; `play_type == 'penalty'` filter returns 0 rows |
| Special teams filter exclusion | Phase 3 (Special teams metrics) | Special teams DataFrame has >0 rows; field goal attempts match known game counts |
| Weather NaN = dome confusion | Phase 4 (Weather features) | `is_dome` flag present; no NaN weather values for outdoor games post-2000 |
| Coaching OC/DC manual curation | Phase 5 (Coaching tracking) | `coaching_changes.csv` exists with HC/OC/DC for all 32 teams, 2016-2025 |
| Rest day edge cases | Phase 6 (Rest/travel factors) | Week 1 rest capped; `rest_advantage` and `is_short_rest` features present; international games flagged |
| Turnover luck recovery attribution | Phase 7 (Turnover luck) | Fumble recovery rate close to 50% league-wide; `fumble_recovery_1_team` column available |
| Referee name consistency | Phase 8 (Referee tendencies) | Unique referee count is reasonable (approximately 20-25 active per season, not 50+) |
| Playoff context overengineering | Phase 9 (Playoff context) | Simple standings proxies used; no full tiebreaker implementation; ties handled |
| Red zone trip miscounting | Phase 10 (Red zone trips) | Per-game average is 3-5 per team; drive-level grouping verified with unit test |

## Sources

- nflverse PBP data dictionary: [nflreadr field descriptions](https://nflreadr.nflverse.com/articles/dictionary_pbp.html) — confirmed penalty, special teams, fumble recovery columns exist in full PBP but NOT in the curated 103-column set (HIGH confidence)
- nfl-data-py `import_officials()` source: reads from `nflverse/nfldata/master/data/officials.csv`, derives season from game_id; confirmed by direct inspection of installed package at `venv/lib/python3.9/site-packages/nfl_data_py/__init__.py` line 604 (HIGH confidence)
- Schedules schema: `temp`, `wind`, `roof`, `surface`, `away_rest`, `home_rest`, `away_coach`, `home_coach`, `referee`, `stadium` all confirmed in existing Bronze data dictionary at `docs/NFL_DATA_DICTIONARY.md` (HIGH confidence)
- Existing `PBP_COLUMNS` in `config.py`: 103 columns confirmed, includes `penalty` (binary), `fumble`, `fumble_lost` but NOT `penalty_type`, `penalty_yards`, `penalty_team`, `special_teams_play`, `fumble_recovery_1_team` (HIGH confidence — direct code inspection)
- `_filter_valid_plays()` in `team_analytics.py`: confirmed filters to `play_type in ('pass', 'run')` only, excluding all special teams plays (HIGH confidence — direct code inspection)
- Open-Meteo Historical Weather API: [open-meteo.com](https://open-meteo.com/en/docs/historical-weather-api) — free, covers 1940-present, requires coordinates (MEDIUM confidence)
- nfl-data-py archival: package archived by nflverse September 2025, read-only; [nfl_data_py GitHub](https://github.com/nflverse/nfl_data_py) (MEDIUM confidence — from web search)
- NFL international games 2025: 7 games across 5 countries; [NFL.com announcement](https://www.nfl.com/news/nfl-announces-2025-international-games-to-feature-seven-games-in-five-countries) (HIGH confidence)
- Pro Football Reference historical weather: [PFR weather page](https://www.pro-football-reference.com/about/weather.htm) — official NFL weather data since 1960 (MEDIUM confidence)
- NFL officials data columns: `game_id`, `official_name`, `position`, `jersey_number`, `official_id`, `season`, `season_type` — confirmed via [nflreadr package reference](https://nflreadr.nflverse.com/reference/index.html) (MEDIUM confidence)

---
*Pitfalls research for: NFL Prediction Data Foundation — weather, coaching, PBP-derived metrics, rest/travel, referees, playoff context, red zone trips*
*Researched: 2026-03-15*
