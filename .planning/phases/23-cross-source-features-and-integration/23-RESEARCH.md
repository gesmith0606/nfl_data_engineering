# Phase 23: Cross-Source Features and Integration - Research

**Researched:** 2026-03-18
**Domain:** Cross-source Silver feature engineering, pipeline health monitoring, integration testing
**Confidence:** HIGH

## Summary

Phase 23 computes two new cross-source Silver features (referee tendency profiles and playoff/elimination context), extends pipeline health monitoring to cover all v1.3 Silver paths, and validates that all Silver sources assemble into a complete prediction feature vector via an integration test.

All source data is available from Phases 20-22. The referee feature joins schedules Bronze `referee` column to per-team rows via `_unpivot_schedules()`. Playoff/elimination context derives W-L-T records from schedules `home_score`/`away_score` columns. Both use the established expanding-window-with-shift(1) pattern from Phase 21. The integration test joins all Silver outputs on `[team, season, week]` and validates column completeness and null patterns.

**Primary recommendation:** Place referee tendencies and playoff context in `game_context.py` (extends the existing schedules-derived module), add two new entries to `SILVER_TEAM_S3_KEYS`, and write a dedicated `tests/test_feature_vector.py` for the integration test.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Referee data source:** Use `referee` column from schedules Bronze (head ref name per game) -- NOT full officials Bronze crew data
- **Referee join approach:** Join schedules referee assignments to existing penalty Silver metrics (`off_penalties`, `def_penalties` from `team_analytics.py`) via `game_id`
- **Referee granularity:** Season-to-date cumulative (expanding window with `shift(1)` lag) -- matches turnover luck pattern from Phase 21
- **Referee columns produced:** Penalty rate per game by this ref crew (total penalties called per game officiated). Single focused signal, not scoring impact or home bias
- **Referee name normalization:** Simple `strip()` + `title()` on referee names -- no fuzzy matching or manual alias mapping. Should produce 20-25 unique active referees per season
- **W-L computation:** Derive from schedules `home_score`/`away_score` columns -- compare scores to determine W/L/T per team per week. Cumulative sum with `shift(1)` lag
- **Division rank:** Rank teams 1-4 within each division by `win_pct`. Ties broken by total wins (no complex NFL tiebreakers). Uses `TEAM_DIVISIONS` dict already in `config.py`
- **Late season contention:** Binary flag -- `win_pct >= 0.400 AND week >= 10`. Simple, interpretable
- **Games behind:** Include `games_behind_division_leader` as continuous column alongside division rank
- **Spot-check validation:** Verify final W-L-T and division rank against official NFL standings for 2023 and 2024 seasons
- **Output columns (playoff):** `wins`, `losses`, `ties`, `win_pct`, `division_rank`, `games_behind_division_leader`, `late_season_contention`
- **Feature vector scope:** Test-only validation -- no production `assemble_features()` function. The ML phase will build its own feature pipeline
- **Feature vector sources:** All four Silver source groups on `[team, season, week]`
- **Null policy:** Assert no nulls in core columns (wins, penalties, EPA) for weeks 2+. Allow nulls in Week 1 rolling columns and weather edge cases
- **Pipeline health:** Extend `check_pipeline_health.py` to validate all new v1.3 Silver output paths

### Claude's Discretion
- Whether referee tendencies go in `game_context.py` or a new `cross_source_features.py` module
- Exact column naming for referee penalty rate
- Whether playoff context columns get rolling windows or remain cumulative-only
- How to handle tie games in W-L-T
- Specific null assertions for each source in the integration test

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CROSS-01 | Referee tendency profiles (penalty rate, scoring impact per crew) joining schedules referee with penalty Silver metrics | Referee data verified in schedules Bronze (17 unique refs/season, clean names). Join path: `_unpivot_schedules()` adds `referee` per-team row, then compute ref season-to-date penalty rate via expanding window. `off_penalties`/`def_penalties` available in pbp_derived Silver. |
| CROSS-02 | Playoff/elimination context (win/loss standings, division rank, clinch/elimination flag) using simple proxy method | `home_score`/`away_score` verified in schedules Bronze. `TEAM_DIVISIONS` dict in config.py maps 32 teams to 8 divisions. Standings computation validated against 2023 (BAL 13-4, KC 11-6) and 2024 data. No ties in 2023 or 2024; ties existed pre-2022 OT rule change. |
| INTEG-01 | Pipeline health monitoring for all new Silver output paths | `check_pipeline_health.py` already monitors `pbp_derived` and `game_context` in `REQUIRED_SILVER_PREFIXES`. Need to add referee tendencies and playoff context Silver path entries. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.x | DataFrame transforms, expanding windows, groupby | Already used throughout pipeline |
| numpy | 1.x | Numeric operations | Already used throughout pipeline |
| pytest | 7.x | Integration test for feature vector | Already used for 71+ existing tests |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyarrow | 14.x | Parquet I/O | Already a dependency for all data read/write |

No new dependencies needed. All work uses existing libraries.

## Architecture Patterns

### Module Placement Decision

**Recommendation: Extend `game_context.py`** rather than creating a new module.

Rationale:
- Both referee tendencies and playoff context derive primarily from schedules Bronze data
- `_unpivot_schedules()` already produces per-team rows with `game_id` -- referee is just another column to carry through
- The `compute_game_context()` orchestrator follows the same merge-on-`[team, season, week]` pattern
- Adding 2 new compute functions to an existing 342-line module keeps it cohesive (schedules-derived features)
- A new `cross_source_features.py` would have only ~100 lines and one external dependency (pbp_derived for referee join validation)

### Recommended Structure

```
src/game_context.py          # Add compute_referee_tendencies() + compute_playoff_context()
src/config.py                # Add 2 new SILVER_TEAM_S3_KEYS entries
scripts/silver_team_transformation.py  # Wire new computes + save to Silver
scripts/check_pipeline_health.py       # Add new Silver prefixes to REQUIRED_SILVER_PREFIXES
tests/test_game_context.py   # Add unit tests for referee + playoff functions
tests/test_feature_vector.py # NEW -- integration test for full feature vector assembly
```

### Pattern 1: Referee Tendency via Expanding Window

**What:** Compute season-to-date referee penalty rate per game for each team-week
**When to use:** When a team's game has a referee assignment

The approach:
1. `_unpivot_schedules()` must include `referee` column in its output (currently not in `cols` list -- needs adding)
2. Also include `home_score` and `away_score` (needed for playoff context)
3. For each referee, compute their total penalties per game across all their games that season (not team-specific -- referee-level stat)
4. Map referee's cumulative penalty rate to each team-week row where that referee officiated
5. Use `shift(1)` on the referee's cumulative to avoid look-ahead (referee's rate entering this game, not including this game)

**Key insight:** The referee penalty rate is a referee-level stat mapped to teams, not a team-level stat. Each game has one referee, and the referee's penalty-calling tendency is the same for both teams in that game. The expanding window operates on the referee's game history, not the team's.

```python
# Conceptual approach (not production code)
def compute_referee_tendencies(unpivoted_df, pbp_derived_df):
    """Compute season-to-date referee penalty rate per game."""
    # 1. Get total penalties per game from pbp_derived
    #    off_penalties + def_penalties = total penalties for that team in that game
    #    Sum both teams' penalties per game_id = total penalties that referee called

    # 2. Group by referee + season, expanding mean with shift(1)
    #    ref_penalties_per_game = cumulative avg of total penalties per game for this ref

    # 3. Map back to team rows via referee column
    return df[["team", "season", "week", "ref_penalties_per_game"]]
```

### Pattern 2: Standings Computation via Cumulative Sum

**What:** Compute W-L-T record, division rank, games behind from game results
**When to use:** For playoff/elimination context columns

```python
# Conceptual approach
def compute_playoff_context(unpivoted_df):
    """Compute standings-based features from schedule results."""
    # 1. Determine game result: compare team score vs opponent score
    #    Need home_score/away_score carried through unpivot

    # 2. Cumulative W/L/T with shift(1) -- standings entering this week
    #    wins = cumsum(win_flag).shift(1), etc.

    # 3. win_pct = wins / (wins + losses + ties)

    # 4. Division rank: within each (season, week, division), rank by win_pct
    #    Tiebreaker: total wins

    # 5. games_behind = (leader_wins - team_wins) / 2 (standard baseball-style)
    #    Or simpler: leader_win_pct - team_win_pct expressed in games

    # 6. late_season_contention = (win_pct >= 0.400) & (week >= 10)
```

### Pattern 3: _unpivot_schedules Column Addition

**Critical change:** The existing `_unpivot_schedules()` function hard-codes its output `cols` list. To carry `referee`, `home_score`, and `away_score` through the unpivot, these columns must be added.

For the unpivot:
- `referee` stays the same for both home and away rows (same ref for both teams)
- `home_score`/`away_score` need to be mapped: home row gets `team_score=home_score, opp_score=away_score`; away row gets the reverse

```python
# In the home rename: add "home_score": "team_score", "away_score": "opp_score"
# In the away rename: add "away_score": "team_score", "home_score": "opp_score"
# Add "referee" to cols list (unchanged in both home/away)
# Add "team_score", "opp_score" to cols list
```

### Anti-Patterns to Avoid
- **Computing referee rate per team instead of per referee:** The referee's penalty-calling tendency is a referee-level stat. Each team sees a different referee each week, and the prediction signal is "how many penalties does THIS referee typically call?"
- **Using current-week data in standings:** Must use `shift(1)` so standings reflect entering-this-week state, not post-game state
- **Complex NFL tiebreakers:** Out of scope per REQUIREMENTS.md. Simple win_pct ranking with total wins tiebreaker
- **Building a production feature assembly function:** CONTEXT.md explicitly says test-only -- ML phase will build its own pipeline

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Expanding window with lag | Custom loop | `groupby().transform(lambda s: s.shift(1).expanding().mean())` | Pattern already proven in turnover luck (Phase 21) |
| Division rank within group | Manual sorting | `groupby([season, week, division]).rank()` | pandas built-in handles ties correctly |
| Games behind leader | Manual leader lookup | `groupby().transform('max') - col` on wins within division | One-liner with pandas transform |

## Common Pitfalls

### Pitfall 1: _unpivot_schedules Column Filtering
**What goes wrong:** Adding columns to `_unpivot_schedules()` but they get silently dropped because they aren't in the `cols` list or don't exist in both home/away frames.
**Why it happens:** The function filters to `available_cols = [c for c in cols if c in home.columns and c in away.columns]`.
**How to avoid:** Add `referee`, `team_score`, `opp_score` to the `cols` list AND ensure the rename maps produce these column names in both home and away DataFrames.
**Warning signs:** Columns missing from unpivoted output with no error.

### Pitfall 2: Referee Penalty Rate Join Complexity
**What goes wrong:** Trying to join referee stats to pbp_derived on game_id but pbp_derived has no game_id column.
**Why it happens:** pbp_derived is keyed on `[team, season, week]` without game_id.
**How to avoid:** Compute total penalties per game by summing `off_penalties + def_penalties` for both teams sharing the same `(season, week, game_id)` from the unpivoted schedules. The referee rate is computed entirely from the unpivoted+penalty-merged data, then mapped to team rows.
**Warning signs:** Missing join key errors, or computing team-level penalty rate instead of referee-level.

### Pitfall 3: Week 1 Null Standings
**What goes wrong:** Division rank and games_behind are NaN for Week 1 because shift(1) produces no prior data.
**Why it happens:** No games have been played before Week 1, so wins=NaN, win_pct=NaN.
**How to avoid:** Fill Week 1 standings with sensible defaults: wins=0, losses=0, ties=0, win_pct=0.0, division_rank=1 (tied at 0-0), games_behind=0.0, late_season_contention=False. Document this in the null policy.

### Pitfall 4: pbp_derived Not Yet Generated Locally
**What goes wrong:** `data/silver/teams/pbp_derived/` is empty -- no local files exist yet.
**Why it happens:** The Silver team transformation script was run before Phase 21 added `compute_pbp_derived_metrics()`, and hasn't been re-run since.
**How to avoid:** Re-run `python scripts/silver_team_transformation.py --seasons 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025` before running integration tests. The function works (verified 164 columns for 2024) but local parquet files don't exist.
**Warning signs:** Integration test fails with "no parquet files found" for pbp_derived.

### Pitfall 5: Column Count Mismatch with ~130 Estimate
**What goes wrong:** The CONTEXT.md says "~130 columns" but actual count is ~337 after joining all Silver sources.
**Why it happens:** The 164 pbp_derived columns (many rolling variants) were likely underestimated.
**How to avoid:** The CONTEXT.md says "exact count determined during implementation." The integration test should assert the actual count (likely 330-340 range) and document it. Don't try to force 130.

### Pitfall 6: Referee Name Already Clean
**What goes wrong:** Expecting name normalization to reduce referee count from 50+ to 20-25, but data already has ~17 unique referees per season with clean names.
**Why it happens:** nflverse schedules data uses standardized referee names.
**How to avoid:** Still apply `strip().str.title()` for safety, but expect 17 unique referees per season (not 20-25 as the success criteria states). The 20-25 range in success criteria likely accounts for multi-season accumulation or minor variants. The test should assert 15-25 unique active referees per season rather than exactly 20-25.

## Code Examples

### Adding Columns to _unpivot_schedules

```python
# In game_context.py _unpivot_schedules():
# Add to home rename dict:
#   "home_score": "team_score",
#   "away_score": "opp_score",
# Add to away rename dict:
#   "away_score": "team_score",
#   "home_score": "opp_score",
# Add to cols list:
#   "referee", "team_score", "opp_score"
```

### Expanding Window Pattern (from Phase 21 turnover luck)

```python
# Source: src/team_analytics.py (existing pattern)
df["own_fumble_recovery_rate_std"] = (
    df.groupby(["team", "season"])["own_fumble_recovery_rate"]
    .transform(lambda s: s.shift(1).expanding().mean())
)
```

### Division Rank with pandas

```python
# Rank within division-season-week group by win_pct (descending), ties by wins
df["division_rank"] = df.groupby(["season", "week", "division"])["win_pct"].rank(
    method="min", ascending=False
)
```

### Games Behind Leader

```python
# Within each (season, week, division), compute games behind the leader
df["leader_wins"] = df.groupby(["season", "week", "division"])["wins"].transform("max")
df["games_behind_division_leader"] = (df["leader_wins"] - df["wins"]) / 2.0
df.drop(columns=["leader_wins"], inplace=True)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No standings data | Simple W-L-T standings proxy | Phase 23 | Captures "playing for something" motivation signal |
| No referee features | Ref penalty rate per game | Phase 23 | Single most predictive ref tendency (scoring impact/home bias too noisy at 17 games/ref/season) |

## Data Verified

### Schedules Bronze Schema (Confirmed)

| Column | Type | Notes |
|--------|------|-------|
| `referee` | string | Head referee name per game. ~17 unique per season. Clean names (no normalization needed beyond safety strip/title). |
| `home_score` | float | Final home team score. Non-null for completed games. NaN for future/unplayed games. |
| `away_score` | float | Final away team score. Same null pattern as home_score. |
| `div_game` | int | 0/1 flag for divisional game. 96 div games + 176 non-div per 272 reg season games. |
| `game_id` | string | Format: `2024_01_BAL_KC` (season_week_away_home). |

### Referee Distribution (2024 Season)

17 unique referees, 15-17 games each. Distribution is near-uniform (NFL assigns refs evenly). Simple `strip().title()` normalization produces the same 17 names (data is already clean).

### Standings Verification (2023 Season)

Computation verified against known results:
- BAL: 13-4 (confirmed AFC North winner)
- SF: 12-5, DAL: 12-5, DET: 12-5 (confirmed)
- KC: 11-6 (confirmed AFC West winner)
- Zero ties in 2023 and 2024 seasons

### Current Silver Column Counts

| Source | Columns | Rows (2024) |
|--------|---------|-------------|
| pbp_metrics | 63 | 544 (32 teams x 17 weeks) |
| tendencies | 23 | 544 |
| sos | 21 | 544 |
| situational | 51 | 544 |
| pbp_derived | 164 | 544 (computed on-demand, no local files) |
| game_context | 22 | 570 (includes playoff games) |
| **Total after join** | **~329** | **(minus duplicate join keys)** |

### Phase 23 New Columns

| Feature | New Columns | Notes |
|---------|-------------|-------|
| Referee tendencies | 1 (`ref_penalties_per_game`) | Season-to-date expanding avg |
| Playoff context | 7 (`wins`, `losses`, `ties`, `win_pct`, `division_rank`, `games_behind_division_leader`, `late_season_contention`) | Cumulative with shift(1) |
| **Total after Phase 23** | **~337** | Not ~130 as estimated |

## Open Questions

1. **Column count discrepancy**
   - What we know: Actual count is ~337, not ~130 as CONTEXT.md estimated
   - What's unclear: Whether the success criteria intended to count only "base" columns (excluding rolling variants) or truly expected 130
   - Recommendation: Use the actual count (~337) in the integration test. The ~130 estimate was likely made before pbp_derived's 164 columns were counted. Document the real number.

2. **pbp_derived local data gap**
   - What we know: `data/silver/teams/pbp_derived/` is empty -- no local parquet files exist despite the compute function working
   - What's unclear: Whether the silver_team_transformation script needs to be re-run as a prerequisite or if the integration test should compute on-the-fly
   - Recommendation: Re-run `silver_team_transformation.py` to populate local pbp_derived data before integration testing. This is a prerequisite step in the plan.

3. **Referee penalty data source for rate computation**
   - What we know: pbp_derived has `off_penalties` and `def_penalties` per team-week. To get total penalties per game for a referee, need to sum both teams' penalties.
   - What's unclear: Whether to join pbp_derived to unpivoted schedules, or compute penalties from raw PBP within game_context.py
   - Recommendation: Join pbp_derived penalty columns to unpivoted schedules via `[team, season, week]`, then sum per `game_id` to get total game penalties. This avoids duplicating PBP computation logic.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | `pytest.ini` (if exists) or default |
| Quick run command | `python -m pytest tests/test_game_context.py tests/test_feature_vector.py -v -x` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CROSS-01 | Referee penalty rate computed with expanding window, 15-25 unique refs per season, shift(1) lag | unit | `pytest tests/test_game_context.py::test_referee_tendencies -x` | Wave 0 |
| CROSS-02 | W-L-T standings, division rank 1-4, games_behind, late_season_contention, spot-check 2023+2024 | unit | `pytest tests/test_game_context.py::test_playoff_context -x` | Wave 0 |
| INTEG-01 | Pipeline health covers all new Silver paths | unit | `pytest tests/test_game_context.py::test_health_check_prefixes -x` | Wave 0 |
| Integration | Full feature vector assembly ~337 cols, null policy, left joins on [team,season,week] | integration | `pytest tests/test_feature_vector.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_game_context.py tests/test_feature_vector.py -v -x`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_feature_vector.py` -- NEW file for integration test (CROSS-01/02 + full vector assembly)
- [ ] Add `test_referee_tendencies` and `test_playoff_context` tests to `tests/test_game_context.py`
- [ ] Re-run `silver_team_transformation.py` to populate local pbp_derived parquet files

## Sources

### Primary (HIGH confidence)
- Local Bronze data inspection: `data/bronze/schedules/season=2024/*.parquet` -- verified referee column, 17 unique refs, home_score/away_score, game_id format
- Local Bronze data inspection: `data/bronze/schedules/season=2023/*.parquet` -- verified standings match known 2023 NFL results
- Existing codebase: `src/game_context.py` -- `_unpivot_schedules()` function, column list, orchestrator pattern
- Existing codebase: `src/team_analytics.py` -- `apply_team_rolling()`, expanding window pattern, `compute_pbp_derived_metrics()` (164 columns)
- Existing codebase: `src/config.py` -- `TEAM_DIVISIONS`, `SILVER_TEAM_S3_KEYS`
- Existing codebase: `scripts/check_pipeline_health.py` -- `REQUIRED_SILVER_PREFIXES` dict

### Secondary (MEDIUM confidence)
- Column count estimate (~337 total) based on summing existing Silver table widths minus join key deduplication

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing patterns
- Architecture: HIGH -- extends existing module with proven patterns
- Pitfalls: HIGH -- verified against actual data (referee names, standings, column counts)
- Data model: HIGH -- all source columns verified in local Bronze/Silver parquet files

**Research date:** 2026-03-18
**Valid until:** 2026-04-18 (stable -- no external dependencies changing)
