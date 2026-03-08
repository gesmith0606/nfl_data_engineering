# Feature Landscape: NFL Game Prediction Data Platform

**Domain:** NFL game outcome prediction (win/loss, spread, totals)
**Researched:** 2026-03-08
**Mode:** Ecosystem (what data types exist, which matter, what to skip)

## Current State

The platform already has a working Bronze layer with 6 data types (schedules, player_weekly, player_seasonal, snap_counts, injuries, rosters) primarily serving fantasy football projections. The goal is to expand Bronze to also feed game prediction models. nfl-data-py is the primary data source, with 10+ additional import functions available but not yet ingested.

---

## Table Stakes

Features users expect. Missing any of these means a game prediction model is fundamentally incomplete.

| Feature / Data Type | Why Expected | nfl-data-py Function | Complexity | Status |
|---------------------|--------------|----------------------|------------|--------|
| **Play-by-Play with EPA/WPA** | EPA is the single most predictive play-level metric for team quality. Rolling EPA per play is the backbone of modern game prediction. PBP includes ~372 columns covering EPA, WPA, CPOE, success rate, air yards, and play context. | `import_pbp_data(years, columns)` | HIGH (large data: ~50K rows/season, 372 cols) | Not ingested |
| **Game Schedules with Betting Lines** | Spread and total lines embed market consensus on team strength. Closing lines are the strongest single predictor of game outcomes -- they already price in injuries, weather, matchups. Already partially available in schedules. | `import_schedules(years)` -- already ingested but verify spread_line, total_line columns present | LOW | Partially done |
| **Team Season Aggregates (from PBP)** | Team-level offensive/defensive EPA, success rate, turnover rate, and explosive play rate per game. These are Silver-layer derivatives of PBP, not a separate Bronze source. | Derived from PBP in Silver layer | MED | Not built |
| **Injury Reports** | Injury status of key players (especially QBs) materially changes win probability. Already ingested. | Already ingested | LOW | Done |
| **Rosters / Depth Charts** | Knowing who starts matters. Depth charts tell you backup vs starter situations. Rosters already ingested; depth charts available but not ingested. | `import_depth_charts(years)` | LOW | Rosters done, depth charts not |
| **Win Totals / Betting Lines** | Pre-season and weekly betting lines capture market-implied team strength. Separate from schedule spread_line -- these are futures markets. | `import_win_totals(years)` | LOW | Not ingested |
| **Scoring Lines (Weekly)** | Weekly spread and over/under lines from sportsbooks. May overlap with schedule data but provides additional detail. | `import_sc_lines(years)` | LOW | Not ingested |

### PBP Column Prioritization

The full PBP dataset has ~372 columns. For game prediction, prioritize these column groups:

**Must-have columns (ingest always):**
- `epa` -- Expected Points Added per play
- `wpa` -- Win Probability Added per play
- `cpoe` -- Completion Percentage Over Expected
- `success` -- Binary: did the play earn positive EPA?
- `air_yards`, `yards_after_catch` -- Passing efficiency decomposition
- `qb_hit`, `sack`, `interception`, `fumble_lost` -- Negative play indicators
- `play_type`, `pass_attempt`, `rush_attempt` -- Play classification
- `down`, `ydstogo`, `yardline_100` -- Situational context
- `score_differential`, `game_seconds_remaining` -- Game state
- `no_huddle`, `shotgun` -- Tempo and formation
- `penalty`, `penalty_yards` -- Penalty impact
- `touchdown`, `first_down` -- Positive outcome markers
- `home_team`, `away_team`, `posteam`, `defteam` -- Team identifiers
- `season`, `week`, `game_id`, `play_id` -- Keys

**Useful but optional:**
- `air_epa`, `yac_epa` -- EPA decomposition (air vs YAC)
- `xyac_success`, `xyac_mean_yardage` -- Expected YAC models
- `comp_air_epa`, `comp_yac_epa` -- Completion-specific EPA splits
- `wp`, `home_wp` -- Pre-play win probability
- `offense_formation`, `offense_personnel`, `defenders_in_box` -- Scheme context

**Skip for game prediction:**
- Player name/ID fields (aggregate to team level)
- Punt/kickoff detail columns
- Penalty detail fields beyond yards
- Expected fantasy point columns

---

## Differentiators

Features that improve prediction accuracy beyond baseline. Not expected but provide measurable edge.

| Feature / Data Type | Value Proposition | nfl-data-py Function | Complexity | Notes |
|---------------------|-------------------|----------------------|------------|-------|
| **Next Gen Stats (NGS)** | Time to throw, separation, rush yards over expected (RYOE), completion probability. These capture talent/scheme quality that box scores miss. RYOE in particular is a better rushing metric than yards per carry. | `import_ngs_data(stat_type, years)` -- types: "passing", "rushing", "receiving" | MED | Weekly aggregates, not play-level. ~20 cols per type. |
| **PFR Advanced Stats** | Pro Football Reference stats: pressure rate, blitz rate, play-action rate, true passing yards. Complementary to PBP-derived metrics, adds defensive scheme context. | `import_seasonal_pfr(years)` / `import_weekly_pfr(years, s_type)` | MED | s_type: "pass", "rush", "rec", "def" |
| **Weather Data** | Research shows weather adds ~2 percentage points of prediction accuracy. Wind >15mph drops FG success 3%, heavy snow reduces scoring by 10 points. Most impactful for totals predictions. | Not in nfl-data-py. Available in PBP (`weather`, `temp`, `wind`) or via external API. Some fields in schedules. | MED | PBP includes partial weather. Full weather needs external source or schedule enrichment. |
| **Quarterback Ratings (QBR)** | ESPN's Total QBR is a more complete QB metric than passer rating, including rushing and sacks. Useful as a team-quality proxy since QB play drives ~60% of team EPA variance. | `import_qbr(years, frequency)` -- frequency: "season" or "weekly" | LOW | Simple tabular data, small footprint. |
| **Rolling / Exponentially Weighted Metrics** | Exponentially weighted rolling EPA (e.g., half-life of 10 games) predicts future performance better than raw season averages. This is a Silver-layer feature, not a new Bronze source. | Derived in Silver from PBP | MED | Key differentiator is the weighting scheme, not the raw data. |
| **Rest Days / Schedule Context** | Short weeks (Thursday games), bye weeks, travel distance, time zone changes. Already partially in schedules (home_rest, away_rest). Extend with travel distance calculation. | Derived from schedules + team locations | LOW | Stadium lat/lng already in data model. |
| **Coaching Data** | Head coach identity and tenure affect team performance, particularly in-game decision-making (4th down, 2-point attempts). Available in schedules (home_coach, away_coach). | Already in schedules | LOW | Limited predictive power alone, but useful as categorical feature. |

### NGS Column Highlights

**Passing:** avg_time_to_throw, avg_completed_air_yards, avg_intended_air_yards, aggressiveness, max_completed_air_distance, avg_air_yards_to_sticks, passer_rating, completion_percentage, expected_completion_percentage, completion_percentage_above_expectation

**Rushing:** efficiency, rush_yards_over_expected, rush_yards_over_expected_per_att, avg_rush_yards, rush_pct_over_expected

**Receiving:** avg_separation, avg_intended_air_yards, avg_cushion, avg_yac, avg_expected_yac, avg_yac_above_expectation, pct_share_of_intended_air_yards

---

## Anti-Features

Features that sound useful but are not worth the complexity, have poor signal-to-noise, or create maintenance burden disproportionate to predictive value.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Combine Data for Game Prediction** | Research shows combine metrics have minimal predictive value for NFL game outcomes. Forty time and vertical jump weakly predict individual player performance and even that is position-specific. For game-level prediction, combine data is noise. | Use actual in-season performance metrics (EPA, NGS) which capture realized ability, not potential. |
| **Draft Capital / Draft Picks** | Draft position is a weak proxy for talent. After year 1-2, actual performance data dominates. Only marginally useful for rookie projections, which the fantasy system already handles. | Use roster/depth chart data + actual stats. Draft pick data (`import_draft_picks`) is useful for the fantasy draft tool, not game prediction. |
| **Referee / Officials Data** | NFL analysis shows "no evidence of systematic bias in penalties." Refs work ~17 games/year -- too small a sample for reliable patterns. Penalty volume varies but doesn't systematically predict outcomes beyond noise. | Include penalty yards as an aggregate team stat from PBP. Skip referee identity as a feature. |
| **Play-Level Player Tracking (raw NGS)** | Raw tracking data (x,y coordinates at 10Hz) is massive, requires specialized processing, and the useful signals are already distilled into NGS aggregate stats. Not available via nfl-data-py anyway. | Use NGS aggregate stats (`import_ngs_data`) which distill tracking into useful metrics. |
| **Historical Head-to-Head Records** | Team matchup history beyond 2-3 years has negligible predictive value due to roster turnover, coaching changes, and scheme evolution. A "rivalry effect" is mostly narrative, not statistical. | Use recent (rolling 2-3 season) team performance metrics instead. If needed, division_game_flag captures the relevant context. |
| **Stadium Elevation / Altitude** | Denver is the only stadium with meaningful elevation (5,280 ft). One-team edge is better handled as a Denver-specific adjustment than a general feature. | Include dome_game_flag and surface type. Skip elevation as a general feature. |
| **Detailed Penalty Breakdown by Type** | Individual penalty types (holding vs DPI vs false start) add dimensionality without proven predictive lift for game outcomes. | Aggregate to total penalty yards per game in Silver layer. |
| **Full Weather API Integration** | Building and maintaining a separate weather data pipeline is high complexity for ~2 percentage points of accuracy gain. PBP data already includes partial weather. | Extract weather from PBP data fields (temp, wind, weather description) or from schedule data. Do not build a separate weather ingestion pipeline. |

---

## Feature Dependencies

```
PBP Data (Bronze) --> Team EPA Aggregates (Silver) --> Game Prediction Features (Gold)
                  --> Success Rate by Down/Distance (Silver) --> Situational Model (Gold)
                  --> Turnover Rates (Silver) --> Game Prediction Features (Gold)

Schedules (Bronze) --> Rest/Travel Features (Silver) --> Game Prediction Features (Gold)
                   --> Betting Lines (Silver) --> Market-Adjusted Predictions (Gold)

NGS Data (Bronze) --> QB Efficiency Metrics (Silver) --> Enhanced Prediction (Gold)
                  --> RB RYOE Metrics (Silver) --> Enhanced Prediction (Gold)

Injuries (Bronze) + Depth Charts (Bronze) --> Starter Availability (Silver) --> Injury-Adjusted Predictions (Gold)

PFR Advanced (Bronze) --> Defensive Scheme Metrics (Silver) --> Matchup-Adjusted Predictions (Gold)

Win Totals (Bronze) --> Pre-Season Priors (Silver) --> Early-Season Predictions (Gold)
```

**Critical path:** PBP is the foundation. Everything else adds incremental value but PBP + Schedules alone can build a competitive model.

---

## MVP Recommendation

### Phase 1: Foundation (must-have for any prediction model)
1. **PBP ingestion** -- Ingest play-by-play data for 2020-2025 with prioritized columns. This is the single highest-value data type. ~50K plays/season, but column-pruning keeps it manageable.
2. **Verify schedule betting lines** -- Confirm spread_line, total_line, over_under columns are present and populated in existing Bronze schedules data.
3. **Team EPA aggregates in Silver** -- Build rolling offensive/defensive EPA per play, success rate, and turnover rate by team-week. This is the core predictive feature set.

### Phase 2: Enhancement (meaningful accuracy gains)
4. **Depth charts** -- Identify starter availability, especially QB.
5. **Win totals / scoring lines** -- Market-implied team strength as a feature and model anchor.
6. **QBR data** -- Quick win: small data, easy ingest, complements EPA.
7. **NGS data** -- Time to throw, RYOE, separation. Three stat types, each ~20 columns.

### Phase 3: Advanced (diminishing returns but still valuable)
8. **PFR advanced stats** -- Pressure rate, blitz rate, play-action metrics.
9. **Weather extraction from PBP** -- Parse existing PBP weather fields into structured features.
10. **Rest/travel distance features** -- Derive from schedules + team location data.

### Defer Indefinitely
- Combine data, draft capital, referee data, raw tracking data, head-to-head history, stadium elevation, full weather API, detailed penalty breakdowns.

---

## Data Volume Estimates

| Data Type | Rows/Season | Columns (pruned) | Size Estimate | Seasons |
|-----------|-------------|-------------------|---------------|---------|
| PBP | ~50,000 | ~60 (from 372) | ~15-20 MB/season | 2020-2025 |
| NGS Passing | ~1,500 | ~20 | <1 MB/season | 2020-2025 |
| NGS Rushing | ~1,000 | ~15 | <1 MB/season | 2020-2025 |
| NGS Receiving | ~2,000 | ~20 | <1 MB/season | 2020-2025 |
| Depth Charts | ~5,000 | ~10 | ~2 MB/season | 2020-2025 |
| Win Totals | ~32 | ~10 | <0.1 MB/season | 2020-2025 |
| Scoring Lines | ~5,000 | ~15 | ~1 MB/season | 2020-2025 |
| QBR Weekly | ~600 | ~15 | <0.5 MB/season | 2020-2025 |
| PFR Advanced | ~2,000 | ~30 | ~1 MB/season | 2020-2025 |
| **Total new Bronze** | | | **~120-150 MB** | 6 seasons |

This is modest. The platform currently holds 7 MB of Bronze data. PBP is the only large addition.

---

## Important Note: nfl-data-py Archival

The nfl-data-py repository was archived by its maintainer in September 2025. The library still functions (it reads from nflverse data releases, not a live API), but there will be no new features or bug fixes. The successor is `nflreadpy`, a Python port of the R `nflreadr` package.

**Recommendation:** Continue using nfl-data-py for now (it works, data is available through 2025 season). Monitor nflreadpy maturity. Plan migration when nflreadpy reaches feature parity and the team needs 2026+ data. This is a Phase 3+ concern, not a blocker.

---

## Sources

- [Frontiers: Advancing NFL win prediction (2025)](https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2025.1638446/full) -- ML model comparison, feature importance via SHAP
- [nflfastR documentation](https://nflfastr.com/articles/nflfastR.html) -- PBP field descriptions, EPA/WPA/CPOE definitions
- [nfl-data-py GitHub](https://github.com/nflverse/nfl_data_py) -- Available import functions, archival status
- [nfl-data-py PyPI](https://pypi.org/project/nfl-data-py/) -- Function signatures, parameter docs
- [NFL.com Next Gen Stats: New metrics for 2025](https://www.nfl.com/news/next-gen-stats-new-advanced-metrics-you-need-to-know-for-the-2025-nfl-season) -- NGS field descriptions
- [Covers: NFL Advanced Metrics](https://www.covers.com/nfl/key-advanced-metrics-betting-tips) -- EPA, CPOE, DVOA explanations
- [Open Source Football: NFL game prediction](https://opensourcefootball.com/posts/2021-01-21-nfl-game-prediction-using-logistic-regression/) -- Rolling EPA weighting approach
- [ParlaySavant: How to Build Sports Prediction Models 2026](https://www.parlaysavant.com/insights/sports-prediction-models-2026) -- Weather impact quantification (+2pp accuracy)
- [Sharp Football Analysis: Weather Impact](https://www.sharpfootballanalysis.com/sportsbook/weather-impact-on-nfl-betting/) -- Wind/precipitation scoring effects
- [ESPN: Debunking officiating conspiracy theories](https://www.espn.com/nfl/story/_/id/46087159/debunking-nfl-officiating-conspiracy-theories-data) -- Referee bias analysis
- [nflreadpy GitHub](https://github.com/nflverse/nflreadpy) -- nfl-data-py successor
- [PubMed: Predictive Value of NFL Combine](https://pubmed.ncbi.nlm.nih.gov/27100168/) -- Combine metrics vs NFL performance
- [nfelo model performance](https://www.nfeloapp.com/games/nfl-model-performance/) -- Elo-based NFL prediction benchmarks
- [Quinnipiac: Predicting NFL Scores](https://iq.qu.edu/experiential-learning/course-projects-and-capstones/student-projects/predicting-nfl-total-score-and-point-spread-bets/) -- Spread/total prediction research
