# Feature Research

**Domain:** NFL Prediction Data Foundation — weather, coaching, special teams, penalties, rest/travel, turnover luck, referee tendencies, playoff context, red zone trip volume
**Researched:** 2026-03-15
**Confidence:** HIGH (all 9 feature categories verified against existing Bronze schema; 7 of 9 derivable from existing Bronze data without new external sources)

---

## Context: What Already Exists

### Bronze Data Available for Derivation

| Bronze Source | Key Columns for v1.3 Features | Already Ingested |
|---------------|-------------------------------|-----------------|
| `schedules` | `gameday`, `home_team`, `away_team`, `home_coach`, `away_coach`, `referee`, `stadium`, `stadium_id`, `temp`, `wind`, `roof`, `surface`, `div_game`, `overtime`, `spread_line`, `total_line` | Yes (1999-2025) |
| `pbp` | `penalty`, `fumble`, `fumble_lost`, `interception`, `drive`, `yardline_100`, `goal_to_go`, `touchdown`, `epa`, `play_type`, `posteam`, `defteam`, `game_seconds_remaining`, `score_differential` | Yes (2010-2025, 103 columns) |
| `player_weekly` | `interceptions`, `sack_fumbles`, `sack_fumbles_lost`, `rushing_fumbles`, `rushing_fumbles_lost`, `receiving_fumbles`, `receiving_fumbles_lost` | Yes (2002-2025) |
| `teams` | `team_abbr`, `team_division`, `team_conference` | Yes (static) |

### Silver Data Already Built (v1.2)

| Silver Output | Relevant to v1.3 | Relationship |
|---------------|-------------------|-------------|
| Team EPA/success rate | Red zone, penalties | Baseline for comparing penalty-adjusted EPA |
| Situational splits (home/away, game script) | Rest/travel, playoff context | Extend with rest differential and elimination flags |
| SOS (opponent-adjusted EPA) | All features | Normalize new features by opponent quality |
| Team tendencies (pace, PROE) | Penalties, special teams | Context for penalty-adjusted decision metrics |

---

## Feature Landscape

### Table Stakes (Prediction Model Expects These)

These features appear in virtually every serious NFL prediction model. Missing them leaves predictive signal on the table that competitors capture.

| Feature | Why Expected | Complexity | Bronze Dependency | Notes |
|---------|--------------|------------|-------------------|-------|
| **Weather categorization** | Wind >15 mph reduces passing EPA by 8-12%; temp <32F shifts run/pass balance; rain reduces scoring ~3 pts/game. Every Vegas model includes weather. | LOW | `schedules`: `temp`, `wind`, `roof`, `surface` | Already in Bronze. Categorize into bins (dome, good, cold, windy, precipitation). Dome games get neutral weather. Flag "weather games" where wind>15 OR temp<32. |
| **Rest days differential** | Post-2011 CBA research shows rolling 3-week net rest has more signal than single-game rest. Thursday games after Sunday = 3 days rest. Bye weeks provide 13 days. | MEDIUM | `schedules`: `gameday`, `home_team`, `away_team` | Compute days_rest per team per game from date deltas. Net rest = team_rest minus opponent_rest. Rolling 3-week cumulative net rest. |
| **Turnover luck / fumble recovery regression** | Fumble recovery is ~50% random (R-squared of year-over-year turnover margin is 0.01). Teams with extreme recovery rates regress hard. Essential regression-to-mean feature. | MEDIUM | `pbp`: `fumble`, `fumble_lost`, `interception`, `posteam`, `defteam` | Compute forced fumbles vs recovered fumbles per team-game. Recovery rate. Expected turnovers (based on sacks, passes defended). Turnover luck = actual minus expected. |
| **Red zone trip volume** | Existing Silver has red zone *efficiency* (TD rate). But trip COUNT is the volume multiplier — a team scoring on 50% of 6 trips differs from 50% of 2 trips. Drive-level aggregation needed. | MEDIUM | `pbp`: `drive`, `yardline_100`, `posteam`, `game_id` | Count distinct drives that cross the 20-yard line per team per game. Separate offensive and defensive trip counts. Combine with existing red zone efficiency for expected red zone points. |
| **Penalty aggregation** | Penalty yards per game correlates with undisciplined play and coaching quality. Opponent-drawn penalty rate reveals scheming advantage. Penalty EPA measures actual impact. | MEDIUM | `pbp`: `penalty`, `epa`, `posteam`, `defteam`, `yards_gained` | Committed penalties per game, penalty yards, penalty EPA. Split by offense/defense. Opponent-drawn rate (penalties your opponents commit). Rolling 3/6 game windows. |
| **Playoff/elimination context** | Teams mathematically eliminated play differently than teams fighting for seeding. Win-and-in games show elevated performance. Garbage-time games pollute season averages. | MEDIUM | `schedules`: `gameday`, `home_score`, `away_score`, `div_game`; `teams`: division/conference | Requires standings computation from game results. Tag games with: playoff_clinched, eliminated, division_leader, wildcard_contender. Late-season (weeks 15-18) context flags. |

### Differentiators (Competitive Advantage)

Features that most hobbyist models skip but pro-level models include. Higher complexity but meaningful signal.

| Feature | Value Proposition | Complexity | Bronze Dependency | Notes |
|---------|-------------------|------------|-------------------|-------|
| **Coaching staff tracking with change detection** | New HC/OC produces ~2-3 week adjustment period with lower offensive efficiency. Mid-season coordinator changes create inflection points. Fantasy analysts track this manually; automating it is rare. | HIGH | `schedules`: `home_coach`, `away_coach` (HC only); **external source needed for OC/DC** | HC available in schedules. OC/DC requires external data (manual CSV or web scraping). Detect changes via week-over-week coach name comparison. Flag games_since_coaching_change. |
| **Referee crew tendencies** | Referee crews show consistent penalty rate patterns (Bill Vinovich averages fewest flags since 2016). DPI-prone crews inflate passing props. Over/under crews affect total scoring. Betting markets adjust when crew assignments are announced. | MEDIUM | `schedules`: `referee` | Referee name already in schedules. Compute per-referee: penalties/game, penalty yards/game, scoring average. Join to upcoming games. Rolling referee stats across seasons. |
| **Travel distance and time zone factors** | West-to-east travel for 1pm ET games shows measurable disadvantage (circadian misalignment). International games (London, Germany) create extreme travel. Back-to-back road games compound fatigue. | MEDIUM | `schedules`: `stadium_id`, `home_team`, `away_team`; **stadium coordinates lookup needed** | Requires a static stadium-to-coordinates mapping (32 stadiums + international venues). Compute great-circle distance, time zone crossings, consecutive away games. |
| **Special teams metrics** | Kicking accuracy, punt net yards, kick return average, and blocked kicks affect field position and scoring. Special teams EPA is available in PBP but rarely aggregated at team level. | MEDIUM | `pbp`: `play_type` (includes 'punt', 'field_goal', 'kickoff', 'extra_point'), `epa`, `yards_gained`, `posteam` | Filter PBP to special teams plays. Compute: FG%, punt net avg, kick return avg, special teams EPA per game. Blocked kick counts. Coverage unit EPA. |
| **Turnover-adjusted EPA** | Standard EPA already penalizes turnovers, but separating "skill turnovers" (bad decisions) from "luck turnovers" (tipped-ball INTs, strip fumbles) provides a cleaner team quality signal. | HIGH | `pbp`: all turnover columns + `epa` | Requires play-level turnover classification. Compute EPA with turnovers removed, EPA with expected (not actual) turnover count. The delta measures luck-adjusted team quality. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **External weather API integration** | "More granular weather data" — hourly forecasts, precipitation type, humidity | PBP already has temp/wind per game; schedules has roof/surface. External API adds a new dependency, rate limits, and historical backfill complexity for ~1-2 percentage points of model improvement. Not worth the infrastructure cost at this stage. | Use `temp` and `wind` from existing Bronze schedules data. Categorize into weather bins. Dome flag from `roof` column. |
| **Real-time referee assignment tracking** | "Get referee assignments as soon as announced" | Referee assignments come 1-2 days before games. Historical tendencies (which we compute from schedules) are the actual signal. Real-time scraping adds fragility for marginal timing gain. | Compute referee historical stats from schedules `referee` column. Apply to upcoming games when schedule data includes referee (typically available by Wednesday). |
| **Detailed penalty type breakdown** | "Track holding vs DPI vs false start separately" | PBP `penalty` column is just a flag (0/1). Getting penalty type requires parsing the `desc` text field, which is messy and inconsistent. The aggregate penalty rate per team captures 90% of the signal. | Use penalty flag + EPA for aggregate impact. If penalty type needed later, parse `desc` field in a separate enhancement phase. |
| **Coaching scheme classification** | "Label teams as West Coast, Air Raid, Shanahan zone-run" | Scheme labels are subjective, change within games, and mix concepts. The existing PROE, early_down_run_rate, pace, and shotgun rate from v1.2 tendencies already capture scheme behavior quantitatively without subjective labels. | Continue using quantitative tendencies (PROE, pace, shotgun %, no-huddle %) already in Silver. |
| **Player-level rest tracking** | "Track individual player rest and load management" | Requires injury report cross-referencing, practice participation data, and snap count trends — massive complexity. Team-level rest differential captures the schedulable advantage. | Use team-level rest days from schedules. Player availability is already handled by injury adjustments in Gold projections. |
| **Elo ratings** | "Compute team Elo like FiveThirtyEight" | Elo is a single-number summary that loses the multi-dimensional signal captured by EPA, SOS, and situational splits already in Silver. It is redundant with what the ML model will learn from the feature vector. | The existing EPA + SOS + situational features already provide richer team quality signals than Elo. An ML model trained on these features will outperform Elo-based predictions. |

---

## Feature Dependencies

```
Weather Categorization (from schedules)
    └── no dependencies, standalone Bronze derivation

Rest Days Differential (from schedules)
    └── requires: schedules with gameday dates
    └── enhances: Situational Splits (add rest context to home/away)

Travel Distance
    └── requires: Stadium Coordinates Lookup (static CSV, ~35 rows)
    └── enhances: Rest Days Differential (combined rest+travel fatigue score)

Penalty Aggregation (from PBP)
    └── requires: existing PBP Bronze data
    └── enhances: Team EPA (penalty-adjusted EPA variant)

Turnover Luck Metrics (from PBP)
    └── requires: existing PBP Bronze data
    └── enhances: Team EPA (luck-adjusted EPA variant)

Red Zone Trip Volume (from PBP)
    └── requires: existing PBP Bronze data
    └── enhances: existing Red Zone Efficiency (volume * efficiency = expected points)

Referee Tendencies (from schedules)
    └── requires: schedules with referee names
    └── enhances: Penalty Aggregation (referee-adjusted penalty expectation)

Playoff/Elimination Context
    └── requires: schedules with scores (completed games)
    └── requires: teams with division/conference structure
    └── sequential: must process games in chronological order within a season

Coaching Staff Tracking
    └── requires: schedules with home_coach/away_coach (HC available)
    └── requires: External OC/DC source (manual CSV or scraping) for full value
    └── enhances: All team metrics (flag regime changes for window adjustments)

Special Teams Metrics (from PBP)
    └── requires: existing PBP Bronze data (punt, field_goal, kickoff, extra_point play types)
    └── standalone: does not depend on other v1.3 features
```

### Dependency Notes

- **Travel Distance requires Stadium Coordinates:** A one-time static lookup table of ~35 venues (32 NFL stadiums + international). This is a 30-minute manual data entry task, not a complex dependency.
- **Coaching OC/DC requires external data:** HC names are in schedules, but OC/DC changes (which have the most fantasy impact) need a separate data source. This can be a manually maintained CSV initially.
- **Playoff Context requires chronological processing:** Standings must be computed game-by-game within each season. Cannot be parallelized across weeks, but can be parallelized across seasons.
- **Seven of nine features derive entirely from existing Bronze data.** Only coaching (OC/DC) and travel (coordinates) need new external data, both of which are small static datasets.

---

## MVP Definition

### Launch With (v1.3 Core)

Features derivable entirely from existing Bronze data, with clear predictive signal.

- [x] **Weather categorization** — LOW complexity, HIGH signal for passing models, zero new dependencies
- [x] **Rest days differential** — MEDIUM complexity, established predictive value, date math on schedules
- [x] **Penalty aggregation** — MEDIUM complexity, PBP-derived, captures team discipline and opponent exploitation
- [x] **Turnover luck metrics** — MEDIUM complexity, strongest regression-to-mean signal in NFL analytics
- [x] **Red zone trip volume** — MEDIUM complexity, fills a gap in existing red zone efficiency (volume missing)
- [x] **Referee tendencies** — MEDIUM complexity, referee name already in schedules, useful for over/under signals
- [x] **Playoff/elimination context** — MEDIUM complexity, standings derivable from game results, important late-season

### Add After Validation (v1.3 Extended)

Features requiring small external data sources or higher complexity transforms.

- [ ] **Special teams metrics** — Trigger: after PBP-derived features are stable; adds field position signal
- [ ] **Travel distance** — Trigger: after rest days are computed; requires stadium coordinates CSV (one-time creation)
- [ ] **Coaching staff tracking (HC)** — Trigger: after standings computation proves chronological processing works; HC detection from schedules data

### Future Consideration (v1.4+)

- [ ] **Coaching OC/DC tracking** — Requires external data source; defer until HC tracking proves value
- [ ] **Turnover-adjusted EPA** — HIGH complexity; requires play-level turnover classification; defer until base turnover luck metrics are validated
- [ ] **Penalty type breakdown** — Requires PBP `desc` text parsing; defer until aggregate penalty rates prove useful

---

## Feature Prioritization Matrix

| Feature | Predictive Value | Implementation Cost | Data Source | Priority |
|---------|-----------------|---------------------|-------------|----------|
| Weather categorization | MEDIUM | LOW | Existing Bronze (schedules) | P1 |
| Rest days differential | MEDIUM | MEDIUM | Existing Bronze (schedules) | P1 |
| Penalty aggregation | MEDIUM | MEDIUM | Existing Bronze (PBP) | P1 |
| Turnover luck metrics | HIGH | MEDIUM | Existing Bronze (PBP) | P1 |
| Red zone trip volume | HIGH | MEDIUM | Existing Bronze (PBP) | P1 |
| Referee tendencies | MEDIUM | MEDIUM | Existing Bronze (schedules) | P1 |
| Playoff/elimination context | MEDIUM | MEDIUM | Existing Bronze (schedules + teams) | P1 |
| Special teams metrics | MEDIUM | MEDIUM | Existing Bronze (PBP) | P2 |
| Travel distance | LOW-MEDIUM | MEDIUM | Static CSV + schedules | P2 |
| Coaching HC tracking | MEDIUM | MEDIUM | Existing Bronze (schedules) | P2 |
| Coaching OC/DC tracking | HIGH | HIGH | External source needed | P3 |
| Turnover-adjusted EPA | HIGH | HIGH | Derived from turnover luck | P3 |

**Priority key:**
- P1: Core v1.3 milestone — all derivable from existing Bronze data
- P2: Extended v1.3 — small external data or higher complexity
- P3: Future — requires external sources or depends on P1/P2 validation

---

## Competitor Feature Analysis

| Feature | Pro Models (Sharp Football, PFF) | Hobbyist Models (Kaggle, tutorials) | Our Approach |
|---------|----------------------------------|--------------------------------------|-------------|
| Weather | Full weather API integration, hourly data | Often ignored or dome-only flag | Categorize from existing temp/wind/roof in schedules — 80% of the signal for 10% of the effort |
| Rest/travel | Detailed fatigue indices with travel distance, time zones, altitude | Days-rest differential only | Days-rest differential first (P1), travel distance extension (P2) |
| Turnovers | Fumble recovery rate regression, expected turnovers, turnover-adjusted metrics | Raw turnover margin | Turnover luck (P1) with expected turnover models; turnover-adjusted EPA deferred to P3 |
| Penalties | Penalty EPA, type breakdown, opponent-drawn rates, referee-adjusted | Total penalties per game | Aggregate penalty EPA and opponent-drawn rates (P1); type breakdown deferred (anti-feature) |
| Referee | Crew-specific over/under, DPI rates, penalty yards per game | Almost never included | Historical referee tendencies from schedules data (P1) — rare differentiator at low cost |
| Special teams | Full special teams EPA, coverage unit grades, returner value | Kicking accuracy only or ignored | PBP-derived special teams EPA and FG% (P2) |
| Coaching | Scheme labels, coordinator tracking, change impact windows | Ignored | HC change detection from schedules (P2); OC/DC deferred (P3) |
| Playoff context | Elimination/clinch flags, motivation indices | Win-loss record only | Standings-derived context flags (P1) |
| Red zone | Trip volume + efficiency + expected points | Efficiency rate only | Volume from PBP drives (P1) combined with existing v1.2 efficiency |

---

## Sources

- **Existing Bronze schema:** Verified against `docs/NFL_DATA_DICTIONARY.md` and `src/config.py` PBP_COLUMNS (103 columns) — HIGH confidence
- **Weather impact:** Web search findings on wind >15 mph reducing passing EPA 8-12%, temp <32F favoring rush — [Sharp Football Analysis](https://www.sharpfootballanalysis.com), [Parlay Savant 2026 Guide](https://www.parlaysavant.com/insights/sports-prediction-models-2026) — MEDIUM confidence
- **Rest differential research:** Lopez & Bliss (2024) study showing post-2011 CBA diminished bye advantage; rolling 3-week net rest has more signal — [Frontiers paper](https://www.frontiersin.org/journals/behavioral-economics/articles/10.3389/frbhe.2024.1479832/full), [SumerSports analysis](https://sumersports.com/the-zone/nfl-schedule-rest-differential-analysis/), [arXiv](https://arxiv.org/abs/2408.10867) — HIGH confidence (peer-reviewed)
- **Turnover luck:** Fumble recovery ~50% random, R-squared 0.01 year-over-year — [PMC research](https://pmc.ncbi.nlm.nih.gov/articles/PMC5969004/), [Harvard Sports Analysis Collective](https://harvardsportsanalysis.org/2014/10/how-random-are-turnovers/), [StatsbyLopez](https://statsbylopez.com/2013/12/18/fumble-luck-part-i/) — HIGH confidence (multiple academic sources)
- **Referee tendencies:** Consistent crew-specific patterns, home team penalty bias — [Harvard Sports Analysis Collective](https://harvardsportsanalysis.org/2025/09/inside-the-flags-a-data-driven-investigation-of-nfl-penalties/), [nflpenalties.com](https://www.nflpenalties.com/all-referees.php?year=2023&view=total), [ESPN](https://www.espn.com/nfl/story/_/id/46087159/debunking-nfl-officiating-conspiracy-theories-data) — MEDIUM confidence (effect size debated)
- **nfl-data-py officials function:** `import_officials()` exists in nfl-data-py but we already have `referee` in schedules — [nfl-data-py GitHub](https://github.com/nflverse/nfl_data_py) — HIGH confidence
- **Travel/fatigue:** [Sports Book Review fatigue index](https://www.sportsbookreview.com/picks/nfl/fatigue-index/) — MEDIUM confidence

---
*Feature research for: NFL Prediction Data Foundation (v1.3)*
*Researched: 2026-03-15*
