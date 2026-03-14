# Feature Research

**Domain:** NFL Silver Layer Expansion — PBP-derived team metrics, rolling window analytics, situational breakdowns, advanced player profiles
**Researched:** 2026-03-13
**Confidence:** HIGH (existing Bronze schema verified against local Parquet files; feature scope derived from `docs/NFL_GAME_PREDICTION_DATA_MODEL.md`, `src/player_analytics.py`, and PBP column inventory in `docs/NFL_DATA_DICTIONARY.md`)

---

## Context: What Already Exists in Silver

The v1.1 Silver layer already produces three output families from `src/player_analytics.py` and `scripts/silver_player_transformation.py`. New features must integrate with these without breaking downstream consumers.

| Existing Silver Output | Storage Path | What It Produces | Who Consumes It |
|------------------------|--------------|------------------|-----------------|
| Player usage metrics | `data/silver/player_usage/season=YYYY/` | target_share, carry_share, snap_pct, air_yards_share per player-week | Gold projection engine (usage multiplier 0.80–1.15) |
| Opponent rankings | `data/silver/opp_rankings/season=YYYY/` | Rank 1-32 by pts allowed per position per team-week | Gold projection engine (matchup multiplier 0.85–1.15) |
| Rolling averages | `data/silver/rolling_stats/season=YYYY/` | 3-game + 6-game + season-to-date for 15 player stats | Gold projection engine (roll3=45%, roll6=30%, std=25%) |

`compute_game_script_indicators()` and `compute_venue_splits()` exist in `player_analytics.py` but are inline-embedded in the usage table — not stored as standalone Silver tables. They are partially implemented and should become proper standalone outputs in v1.2.

---

## Feature Landscape

### Table Stakes (Users Expect These)

These are the minimum features a Silver layer must have to support the planned Gold game prediction model. Without them, the prediction model design in `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` (SLV-01 to SLV-03) cannot be executed.

| Feature | Why Expected | Complexity | Bronze Dependency | Notes |
|---------|--------------|------------|-------------------|-------|
| Team EPA per play (offense + defense) | Foundation of all modern NFL prediction models; nflfastR ecosystem considers it non-negotiable | MEDIUM | `pbp`: `epa`, `play_type`, `posteam`, `defteam`, `season`, `week` | Scrimmage plays only; exclude punts, kickoffs, kneels, spikes. Compute pass_epa and rush_epa splits separately. |
| Success rate per team (offense + defense) | Directly complements EPA; success = EPA > 0 per play; universally used | LOW | `pbp`: `success`, `play_type`, `posteam` | Group by team-week. Offensive and defensive variants. |
| CPOE team aggregate | Separates QB quality from receiver drops/run-after-catch; play-level `cpoe` already in PBP | MEDIUM | `pbp`: `cpoe`, `passer_player_id`, `posteam`, `pass_attempt` | Aggregate per QB (player profile) and per team-week. NULL when no pass plays. |
| Rolling windows on all team metrics | Season-only averages miss momentum and hot/cold streaks; 3-game and 6-game are the established pattern | MEDIUM | Derived from team EPA aggregates | Follow `shift(1)` before rolling convention from `compute_rolling_averages()`. |
| Pace (plays per game) | Total opportunity count determines all position volumes; critical multiplier for projection model | LOW | `pbp`: `play_type`, `posteam`, `game_id` | Count non-special-teams plays per team per game; exclude kneels, spikes, kick plays. |
| Pass Rate Over Expected (PROE) | `pass_oe` is already in PBP play-level; team PROE is the aggregate; identifies run-heavy schemes | LOW | `pbp`: `pass_oe`, `posteam`, `play_type` | Mean of play-level `pass_oe` grouped by team-week; exclude spikes/kneels from denominator. |
| Red zone efficiency (offense + defense) | Best single predictor of TD count per game; cannot be inferred from total yardage | MEDIUM | `pbp`: `yardline_100`, `touchdown`, `play_type`, `posteam` | Red zone = `yardline_100 <= 20`. Compute TD rate, success rate, and pass/rush split inside red zone. |
| Situational breakdowns (home/away, divisional) | `div_game` and `home_team` already in schedules; promotes inline tags to a proper standalone table | LOW | `schedules`: `div_game`, `home_team`, `away_team` | Tag each team-week row. Build rolling home/away splits for key metrics. |
| Strength of Schedule (opponent-adjusted EPA) | Required to normalize team rankings so a team facing weak opponents is not overrated | HIGH | Requires team EPA table to exist first (sequential, same build) | Build in second pass: compute raw EPA, then adjust each game's EPA for average opponent quality faced. |

### Differentiators (Competitive Advantage)

Features that make this analytics layer competitive with open-source NFL analytics tools (nflfastR, nflreadr) while staying within the existing projection model's architecture.

| Feature | Value Proposition | Complexity | Bronze Dependency | Notes |
|---------|-------------------|------------|-------------------|-------|
| NGS separation + catch probability (WR/TE profile) | Route-running quality independent of QB accuracy; identifies breakout WRs before box scores show it | MEDIUM | `ngs` receiving: `avg_separation`, `avg_intended_air_yards`, `catch_probability` — already ingested 2016-2025 | Join to `player_id` via `player_gsis_id`. Weekly. Add rolling windows. |
| NGS time-to-throw + aggressiveness (QB profile) | Measures QB decision-making speed and downfield aggression independent of completion% | MEDIUM | `ngs` passing: `avg_time_to_throw`, `aggressiveness`, `avg_completed_air_yards` — already ingested | Rolling windows. Join to player_weekly via `player_gsis_id`. |
| NGS RYOE (Rushing Yards Over Expected, RB profile) | Separates RB skill from offensive line quality; one of the best breakout signals for RBs | MEDIUM | `ngs` rushing: `rush_yards_over_expected`, `efficiency` — already ingested | Rolling windows. Requires `player_gsis_id` join. |
| PFR pressure rate (QB profile) | Quantifies pass-blocking quality and QB performance under duress; predictive of fumbles and sacks | MEDIUM | `pfr_weekly` (pass): `times_sacked`, `times_hit`, `times_hurried` — already ingested 2018-2025 | pressure_rate = (hits + hurries + sacks) / dropbacks. Rolling windows. |
| PFR blitz rate (defensive tendency) | Indicates defensive playcalling philosophy; blitz-heavy teams inflate WR/TE target depth | MEDIUM | `pfr_weekly` (def): `blitz` column — already ingested | Normalize per team per game. Rolling windows. Requires defensive team join. |
| QBR rolling windows | ESPN's composite QB metric; better than raw stats for head-to-head comparisons; already in Bronze | LOW | `qbr` weekly: `qbr_total`, `pts_added` — already ingested 2006-2025 | Apply same rolling window transform as other player stats. |
| 4th down aggressiveness index | Reflects modern coaching analytics adoption; aggressive coaches maintain lead differently | MEDIUM | `pbp`: `fourth_down_converted`, `fourth_down_failed`, `play_type`, `ydstogo` | Compute go-rate on 4th down vs expected go-rate by field position (public go-for-it calculator benchmarks). Rolling windows. |
| Combine measurables linked to players | Speed score, burst score, catch radius — enables rookie projection improvement and breakout-year identification | MEDIUM | `combine` (already ingested 2000-2025) + `rosters` or `player_weekly` for player_id join | Speed score = weight_lbs * 200 / 40_time^4. Static join table, one-time build, refresh annually. |
| Draft capital per player | Pick value (Johnson trade chart) as a rookie baseline signal; first-round picks outperform ADP | MEDIUM | `draft_picks` (already ingested 2000-2025) | Map pick number to trade chart value. Link `player_id` via name + draft_year join against rosters. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Play-level Silver table (copy of Bronze PBP) | Preserves granularity for ad-hoc queries downstream | A Silver copy of 103-column PBP adds zero transformation value and doubles storage. DuckDB can query Bronze PBP directly for any analytical query. | Query Bronze PBP directly using DuckDB for play-level analysis. Silver should aggregate, not copy. |
| WPA rolling aggregates at team level | WPA is in PBP; rolling WPA sounds useful | WPA collapses toward zero when summed across plays per game (it sums to approximately the win probability change for the whole game, not a useful average). EPA is the correct aggregation unit. | Use EPA exclusively for team-level rolling aggregates. |
| Real-time within-game metrics | Faster feedback loops during live games | Requires streaming infrastructure (Kafka/Flink); completely out of scope for batch Parquet pipeline. nfl-data-py only provides post-game data. | Weekly batch refresh is the correct granularity. Accept one-week lag. |
| Weather normalization factor on EPA | Temperature and wind affect scoring and EPA | Schedules and PBP already include `temp` and `wind`. Weather API was explicitly evaluated and rejected in the prediction model design doc (adds ~2pp improvement for high complexity). | Tag outdoor vs dome games using `roof` column. Optionally filter outdoor games for weather-sensitive analysis. |
| Positional matchup grades (WR1 vs CB1) | Useful for DFS and individual projection adjustments | Requires a graph join (WR to CB assignment); cannot be expressed cleanly in flat Parquet. Explicitly deferred to Phase 5 Neo4j. | Use opponent positional rankings (already implemented) as the proxy matchup signal. |
| NGS data before 2016 | More historical coverage | Next Gen Stats tracking chips were not deployed before 2016. nfl-data-py returns empty or raises errors for NGS before 2016. | Accept 2016 as the NGS historical floor. Do not attempt to backfill or interpolate. |
| Per-play EPA normalization by down-and-distance | Some analysts argue raw EPA is biased by situation | Creates a new derived metric that diverges from the public nflfastR standard, making cross-validation harder. MAE improvement is marginal per published research. | Use raw EPA. Note situational context via down and yardline tags in play-level Bronze if needed. |

---

## Feature Dependencies

```
[Bronze PBP (epa, cpoe, success, pass_oe, play_type, posteam, defteam)]
    └──required by──> [Team EPA per play + Success Rate]
                          └──required by──> [Strength of Schedule (SOS)]
                          └──feeds──>       [Rolling Team EPA windows (3g, 6g)]
                                                └──enhances──> [Gold matchup multiplier]

[Bronze PBP (pass_oe, posteam)]
    └──required by──> [Pass Rate Over Expected (PROE) per team]

[Bronze PBP (yardline_100, touchdown, play_type)]
    └──required by──> [Red Zone Efficiency per team]

[Bronze PBP (play_type, posteam, game_id)]
    └──required by──> [Pace (plays per game)]

[Bronze PBP (fourth_down_converted, fourth_down_failed)]
    └──required by──> [4th Down Aggressiveness Index]

[Bronze Schedules (div_game, home_team, away_team)]
    └──required by──> [Situational Breakdowns (home/away, divisional tags)]
    └──already used──> [compute_game_script_indicators() — inline in usage table]

[Bronze NGS receiving]
    └──required by──> [Player Profile: separation, catch probability, RYOE]

[Bronze NGS passing]
    └──required by──> [Player Profile: time-to-throw, aggressiveness, QB CPOE]

[Bronze NGS rushing]
    └──required by──> [Player Profile: RYOE, time-to-LOS]

[Bronze PFR Weekly (pass)]
    └──required by──> [QB Profile: pressure rate, hits, hurries]

[Bronze PFR Weekly (def)]
    └──required by──> [Team Profile: blitz rate]

[Bronze QBR (weekly)]
    └──required by──> [QBR rolling window per QB]

[Bronze Combine + Draft Picks]
    └──required by──> [Historical Context: combine measurables + draft capital]
    └──requires──>    [player_id fuzzy join via rosters or player_weekly]

[Existing Silver: rolling_stats (player)]
    └──already consumed by──> [Gold projection engine (roll3, roll6, std)]
    └──NOT replaced by──>     [New team-level rolling metrics — these are separate tables]

[Team EPA per play (new Silver table)]
    └──must exist before──> [Strength of Schedule (SOS)]
    └──conflicts with──>    [WPA team aggregates — see anti-features]
```

### Dependency Notes

- **SOS requires team EPA to be computed first.** SOS is calculated as the average offensive EPA of all opponents a team has faced. This means team EPA aggregation must complete in the same Silver build run before the SOS pass runs. Implement as sequential steps in the same script, not separate pipelines.
- **Combine and draft capital require a fuzzy name join.** Bronze `combine` and `draft_picks` tables do not contain GSIS player IDs. They must be joined to `rosters` or `player_weekly` via player name + draft year. Name formatting differences (e.g., "Patrick Mahomes II" vs "Patrick Mahomes") require normalization. This is the highest-risk join in the entire milestone.
- **NGS profiles are additive to existing player metrics.** The existing usage metrics (target_share, snap_pct) remain the primary projection inputs. NGS metrics are additive columns that improve rookie and breakout-year modeling without disrupting the current rolling average weights in the projection engine.
- **PROE and 4th down aggressiveness are team-level tendencies, not player-level.** They belong in a dedicated `team_tendencies` Silver table, not appended to the player usage table.
- **Game script and venue splits are already implemented in `player_analytics.py`.** The v1.2 work is to promote these from inline-embedded columns to a standalone `situational` Silver table with proper rolling window splits.

---

## MVP Definition

The MVP for v1.2 is the minimum set of features that (a) directly improves Gold projection accuracy and (b) lays the foundation for the planned game prediction model at Gold layer.

### Launch With (v1.2 core — P1)

- [ ] Team EPA per play (offense + defense, pass + rush splits) with 3-game and 6-game rolling windows — feeds matchup multiplier improvement in Gold
- [ ] Success rate by team (offense + defense) with rolling windows — standard EPA complement; used in every public NFL prediction model
- [ ] Red zone efficiency (offense + defense) with rolling windows — most direct predictor of TD count; highest-leverage single projection improvement
- [ ] CPOE team aggregate per QB and per team with rolling windows — differentiates QB quality from scheme; improves QB projection variance estimate
- [ ] Pass Rate Over Expected (PROE) per team with rolling windows — quantifies run-heavy vs pass-heavy tendency; critical for RB/WR share projections
- [ ] Pace (plays per game) per team with rolling windows — total volume predictor; affects all position projections multiplicatively
- [ ] Strength of Schedule (opponent-adjusted EPA per team) — normalizes team rankings against varying opponent quality; required for SOS column in Gold
- [ ] Situational tags (home/away, divisional, game script) as standalone Silver table — promotes existing inline logic to proper output; low effort, high value for Gold features

### Add After Validation (v1.2 extensions — P2)

- [ ] NGS player profiles (WR/TE separation, QB time-to-throw, RB RYOE) with rolling windows — add after confirming team EPA rolling windows are stable and backtest shows improvement
- [ ] PFR pressure rate (QB) and blitz rate (team defense) with rolling windows — add when integrating into QB and WR Silver player profiles
- [ ] QBR rolling windows — low-effort add-on once NGS passing profile is built (same Bronze data, same transform)
- [ ] 4th down aggressiveness index with rolling windows — add after team tendencies table is established

### Future Consideration (v2+ — P3)

- [ ] Combine measurables + draft capital linked to players — defer until rookie breakout modeling is an explicit Gold target; the name-based join is complex and the output is a one-time static table
- [ ] Exponentially-weighted rolling windows (EWMA) — add if backtesting shows EWMA outperforms fixed 3-game/6-game windows; requires backtest infrastructure update to test the hypothesis
- [ ] SOS with forward-looking schedule-remaining adjustment — current SOS is backward-looking (past opponents faced); forward-looking requires schedule data lookup and is a different use case (preseason projections vs in-season)

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Team EPA/play + rolling windows | HIGH | MEDIUM | P1 |
| Success rate + rolling windows | HIGH | LOW | P1 |
| Red zone efficiency + rolling windows | HIGH | MEDIUM | P1 |
| CPOE team aggregate + rolling windows | HIGH | MEDIUM | P1 |
| Pass Rate Over Expected (PROE) | HIGH | LOW | P1 |
| Pace (plays per game) | HIGH | LOW | P1 |
| Strength of Schedule (SOS) | HIGH | HIGH | P1 |
| Situational tags (home/away, divisional) | MEDIUM | LOW | P1 |
| NGS player profiles (separation, RYOE) | HIGH | MEDIUM | P2 |
| PFR pressure + blitz rates | MEDIUM | MEDIUM | P2 |
| QBR rolling windows | MEDIUM | LOW | P2 |
| 4th down aggressiveness index | MEDIUM | MEDIUM | P2 |
| Combine measurables + draft capital | MEDIUM | HIGH | P3 |
| Exponentially-weighted rolling (EWMA) | LOW | MEDIUM | P3 |
| SOS forward-looking (schedule-remaining) | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for v1.2 core — directly feeds Gold layer improvements
- P2: Should have — add after P1 is validated via backtest improvement
- P3: Nice to have — defer to v1.3 or beyond

---

## Output Table Map

Each Silver feature group maps to a named output table (local Parquet, local-first):

| Output Table | Partition | Contents | Source Bronze Data | Feeds Gold Layer |
|-------------|-----------|----------|--------------------|------------------|
| `team_epa/season=YYYY/week=WW/` | season + week | Off/def EPA per play, pass/rush splits, success rate, rolling windows (3g, 6g, std) | PBP | Game prediction matchup features, updated opp rankings |
| `team_tendencies/season=YYYY/week=WW/` | season + week | PROE, pace, 4th down aggression, rolling windows | PBP | Projection volume multiplier |
| `sos/season=YYYY/week=WW/` | season + week | Opponent-adjusted EPA rank 1-32, raw SOS score | team_epa (same run) | Gold matchup multiplier replacement/supplement |
| `situational/season=YYYY/week=WW/` | season + week | Home/away flags, divisional flag, game script label, rolling home/away EPA splits | Schedules + PBP | Gold context features |
| `player_profiles/season=YYYY/week=WW/` | season + week | NGS separation/RYOE/TTT, PFR pressure/blitz, QBR rolling per player-week | NGS, PFR, QBR | Gold QB/WR/RB projections |
| `player_context/` | static (annual refresh) | Combine measurables + draft capital score per player_id | Combine, Draft Picks | Gold rookie/breakout baseline |

---

## Rolling Window Specification

All new rolling window metrics follow the pattern established in `compute_rolling_averages()` in `src/player_analytics.py`:

- **3-game window** (`_roll3`): Short-term form; `shift(1)` before `rolling(3, min_periods=1).mean()`
- **6-game window** (`_roll6`): Medium-term trend; same shift-before-rolling pattern
- **Season-to-date** (`_std`): Full season expanding mean; `shift(1)` before `expanding().mean()`
- **Exponentially weighted** (`_ewm`): P3 only — not in v1.2

Column naming convention (extending the existing player stat pattern to team metrics):

```
{metric}_{window}

Examples for team metrics:
  off_epa_per_play_roll3
  def_epa_per_play_roll6
  red_zone_td_rate_std
  pass_rate_oe_roll3
  pace_roll3
  success_rate_roll6
```

The `shift(1)` before rolling is non-negotiable: it ensures week N's rolling average uses only weeks 1 through N-1, preventing the current week's outcome from leaking into the prediction feature. This is the existing pattern in `player_analytics.py` and must be maintained for all new metrics. Missing this causes data leakage in backtesting.

For team-level metrics, the groupby key is `(team, season)` instead of `(player_id)` — but the transform mechanics are identical.

---

## Bronze Data Availability Confirmation

All Bronze data needed for P1 and P2 features is locally available (confirmed from filesystem at `/Users/georgesmith/repos/nfl_data_engineering/data/bronze/`):

| Bronze Data Type | Local Path Confirmed | Seasons Available | Needed For |
|-----------------|---------------------|-------------------|------------|
| PBP | `data/bronze/pbp/season=2016..2025/` | 2016-2025 (10 files) | All P1 team metrics |
| Schedules | `data/bronze/games/season=2020..2025/` | 2020-2025 | Situational tags |
| NGS | Via ingestion pipeline | 2016-2025 | P2 player profiles |
| PFR Weekly | Via ingestion pipeline | 2018-2025 | P2 pressure/blitz |
| QBR | Via ingestion pipeline | 2006-2025 | P2 QBR rolling |
| Combine | `data/bronze/combine/season=2000..2025/` | 2000-2025 | P3 player context |
| Draft Picks | `data/bronze/draft_picks/season=2000..2025/` | 2000-2025 | P3 player context |

**PBP is the critical P1 dependency.** The 103-column Bronze PBP schema already contains all columns needed for P1: `epa`, `cpoe`, `success`, `pass_oe`, `xpass`, `play_type`, `posteam`, `defteam`, `yardline_100`, `touchdown`, `fourth_down_converted`, `fourth_down_failed`, `pass_attempt`, `rush_attempt`, `game_id`, `season`, `week`. No new Bronze ingestion is required before starting P1 work.

**Schedules only cover 2020-2025 locally.** If situational tags need to reach back to 2016, schedules must be backfilled for 2016-2019. This is a low-complexity Bronze operation but must happen before the situational Silver table can cover the full 2016-2025 range. For v1.2 launch, 2020-2025 coverage is sufficient.

---

## Sources

- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — Silver layer planned schema (SLV-01 to SLV-03), prediction model feature categories, out-of-scope decisions
- `docs/NFL_DATA_DICTIONARY.md` — PBP 103-column schema, NGS schemas, PFR schemas
- `src/player_analytics.py` — Existing rolling window implementation pattern (shift(1), expanding, 3/6-game windows, groupby conventions)
- `scripts/silver_player_transformation.py` — Existing Silver pipeline structure and output table paths
- `.planning/PROJECT.md` — v1.2 milestone requirements, constraints, deferred items
- `CLAUDE.md` — Architecture, scoring configs, projection model weights (roll3=45%, roll6=30%, std=25%)

---

*Feature research for: NFL Silver Layer Expansion (v1.2)*
*Researched: 2026-03-13*
