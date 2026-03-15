# Phase 16: Strength of Schedule and Situational Splits - Research

**Researched:** 2026-03-14
**Domain:** NFL team analytics — opponent-adjusted EPA and situational performance splits
**Confidence:** HIGH

## Summary

Phase 16 extends the Silver team analytics layer with two new datasets: (1) Strength of Schedule (SOS) — opponent-adjusted EPA rankings using lagged opponent strength, and (2) Situational Splits — home/away, divisional/non-divisional, and game script EPA splits. All computation derives from the existing Bronze PBP data, reusing `_filter_valid_plays()` and `apply_team_rolling()` from `team_analytics.py`.

The implementation is straightforward pandas aggregation and merging. The SOS computation requires building an opponent-game mapping from PBP columns (`posteam`/`defteam`), computing cumulative opponent EPA through week N-1 (lagged), and adjusting raw EPA. Situational splits tag plays using existing PBP columns (`home_team`, `score_differential`) plus a static division lookup. Both datasets follow the established wide-format pattern with rolling windows.

**Primary recommendation:** Add `compute_sos_metrics()` and `compute_situational_splits()` functions to `team_analytics.py`, following the same pattern as `compute_pbp_metrics()` and `compute_tendency_metrics()`. Extend `silver_team_transformation.py` to call both after existing computations. Register two new entries in `SILVER_TEAM_S3_KEYS`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- SOS Methodology: Simple average opponent-adjusted EPA using lagged (week N-1) opponent strength only
- Additive adjustment: adj_off_epa = raw_off_epa - mean(opponents_def_epa); adj_def_epa = raw_def_epa - mean(opponents_off_epa)
- Offense and defense SOS computed separately
- Week 1 opponent-adjusted EPA equals raw EPA (no opponent history)
- Output includes both rank (1-32) AND numeric SOS score
- Home/away from PBP: posteam == home_team
- Divisional games via static TEAM_DIVISIONS dict in config.py
- Game script: score_differential column, binary 7+ threshold (leading/trailing), neutral excluded
- Two separate Parquet datasets: sos/ and situational/
- Wide format: one row per (team, season, week)
- NaN for non-applicable situations
- Rolling windows (roll3, roll6, std) with min_periods=1
- Extend existing silver_team_transformation.py (no new script)
- Always compute all 4 datasets per run
- Full season processing only
- PBP is sole input (no schedule Bronze dependency)
- New functions in team_analytics.py

### Claude's Discretion
- Column naming for adjusted EPA variants
- Bye week handling in SOS (skip vs carry forward)
- Whether to include success rate splits alongside EPA splits
- TEAM_DIVISIONS dict format and placement in config.py

### Deferred Ideas (OUT OF SCOPE)
- Forward-looking SOS (remaining schedule difficulty) — SOS-03, v1.3+
- Weather/indoor splits
- Quarter-by-quarter game script analysis
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SOS-01 | Opponent-adjusted EPA using lagged opponent strength (through week N-1 only) | Lagged computation pattern verified; `compute_team_epa()` output provides raw EPA per team-week; opponent mapping derivable from PBP `posteam`/`defteam` columns |
| SOS-02 | Schedule difficulty rankings (1-32) per team per week | pandas `rank()` with `ascending=False` on SOS score; rank 1 = hardest schedule |
| SIT-01 | Home/away performance splits with rolling windows | PBP `home_team`/`away_team` columns verified present; `posteam == home_team` reliably identifies home plays |
| SIT-02 | Divisional vs non-divisional game tags and performance splits | Static TEAM_DIVISIONS dict needed; all 32 team abbreviations verified from PBP data |
| SIT-03 | Game script splits (leading/trailing by 7+) with rolling EPA | `score_differential` column verified: float32, range -46 to 46, 5.5% NaN rate (kickoff/timeout rows filtered by `_filter_valid_plays`) |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | (existing) | All aggregation, groupby, rolling, ranking | Already used throughout team_analytics.py |
| numpy | (existing) | NaN handling, conditional logic | Already imported in team_analytics.py |

### Supporting
No new libraries required. All computation uses existing pandas/numpy patterns from Phase 15.

## Architecture Patterns

### Recommended Project Structure
```
src/
  team_analytics.py          # Add compute_sos_metrics(), compute_situational_splits()
  config.py                  # Add TEAM_DIVISIONS dict, SILVER_TEAM_S3_KEYS entries
scripts/
  silver_team_transformation.py  # Extend run_silver_team_transform() with SOS + situational calls
data/silver/teams/
  sos/season=YYYY/           # SOS output
  situational/season=YYYY/   # Situational splits output
tests/
  test_team_analytics.py     # Add SOS + situational test classes
```

### Pattern 1: SOS Computation (Lagged Opponent Adjustment)

**What:** Compute opponent-adjusted EPA by subtracting the mean of opponents' EPA faced through week N-1.

**When to use:** For every team-week starting from week 1.

**Algorithm:**
1. Start with `compute_team_epa()` output (team, season, week, off_epa_per_play, def_epa_per_play)
2. Build opponent schedule: for each team-week, identify the opponent from PBP (`defteam` when team is `posteam`)
3. For week W, compute SOS using opponents' EPA from weeks 1 through W-1 only
4. Week 1: adj_epa = raw_epa (no opponents faced yet)
5. Week 2+: off_sos = mean(opponents' def_epa through W-1); adj_off_epa = raw_off_epa - off_sos
6. Rank 1-32: rank off_sos descending (rank 1 = hardest schedule = highest mean opponent DEF EPA)

**Key implementation detail:** The opponent schedule must be extracted from PBP at the game level, not the play level. Group PBP by `(game_id, posteam)` to get one row per team-game, then extract the opponent.

```python
# Derive opponent schedule from PBP
def _build_opponent_schedule(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Extract unique (team, season, week, opponent) from PBP."""
    games = (
        valid_plays[["game_id", "posteam", "defteam", "season", "week"]]
        .drop_duplicates(subset=["game_id", "posteam"])
        .rename(columns={"posteam": "team", "defteam": "opponent"})
    )
    return games[["team", "season", "week", "opponent"]]
```

### Pattern 2: Situational Split Computation

**What:** Compute EPA separately for different game contexts (home/away, divisional, game script).

**When to use:** For every team-week, producing NaN for non-applicable situations.

**Algorithm:**
1. Tag each play with situational context from PBP columns
2. Compute mean EPA per (team, season, week, situation)
3. Pivot to wide format: one row per (team, season, week) with situation-specific columns
4. Apply rolling windows to all situation columns

```python
# Home/away tagging
is_home = valid_plays["posteam"] == valid_plays["home_team"]

# Game script tagging
leading = valid_plays["score_differential"] >= 7
trailing = valid_plays["score_differential"] <= -7

# Divisional check
def _is_divisional(team, opponent):
    return TEAM_DIVISIONS.get(team) == TEAM_DIVISIONS.get(opponent)
```

### Pattern 3: TEAM_DIVISIONS Dict

**What:** Static mapping of NFL team abbreviations to division strings.

**Format recommendation:** Flat dict mapping team abbrev to division string. Placed in config.py near other NFL constants.

```python
TEAM_DIVISIONS = {
    "ARI": "NFC West", "ATL": "NFC South", "BAL": "AFC North", "BUF": "AFC East",
    "CAR": "NFC South", "CHI": "NFC North", "CIN": "AFC North", "CLE": "AFC North",
    "DAL": "NFC East", "DEN": "AFC West", "DET": "NFC North", "GB": "NFC North",
    "HOU": "AFC South", "IND": "AFC South", "JAX": "AFC South", "KC": "AFC West",
    "LA": "NFC West", "LAC": "AFC West", "LV": "AFC West", "MIA": "AFC East",
    "MIN": "NFC North", "NE": "AFC East", "NO": "NFC South", "NYG": "NFC East",
    "NYJ": "AFC East", "PHI": "NFC East", "PIT": "AFC North", "SEA": "NFC West",
    "SF": "NFC West", "TB": "NFC South", "TEN": "AFC South", "WAS": "NFC East",
}
```

**Note:** These abbreviations match the PBP `posteam` values verified from 2024 data. Historical PBP (pre-2020) may use different abbreviations (e.g., `OAK` instead of `LV`, `SD` instead of `LAC`, `STL` instead of `LA`). Since PLAYER_DATA_SEASONS starts at 2020, the current abbreviations are sufficient. The Rams moved to LA in 2016, the Chargers in 2017, and the Raiders in 2020. If processing seasons before 2020, a mapping function would be needed, but CONTEXT.md specifies no schedule Bronze dependency and data range is 2020-2025.

### Pattern 4: Bye Week Handling in SOS

**Recommendation (Claude's discretion):** Skip bye weeks entirely in SOS output. A team that has a bye in week W simply has no row for that week in the SOS table. The lagged SOS computation naturally handles this because the opponent list through W-1 doesn't change during a bye. This is consistent with how `compute_team_epa()` already works — no plays means no row.

### Pattern 5: Success Rate in Situational Splits

**Recommendation (Claude's discretion):** Do NOT include success rate splits alongside EPA splits. The CONTEXT.md specifies EPA splits, and adding success rate would double the column count without clear downstream consumer need. If needed later, it can be added as a separate enhancement. Keep Phase 16 focused.

### Column Naming Convention

**Recommendation (Claude's discretion):**

SOS columns:
- `off_sos_score` — mean of opponents' DEF EPA faced (numeric SOS)
- `def_sos_score` — mean of opponents' OFF EPA faced
- `adj_off_epa` — raw_off_epa - off_sos_score
- `adj_def_epa` — raw_def_epa - def_sos_score
- `off_sos_rank` — rank 1-32 (1 = hardest)
- `def_sos_rank` — rank 1-32 (1 = hardest)

Situational columns:
- `home_off_epa`, `away_off_epa` — offense EPA when home/away
- `div_off_epa`, `nondiv_off_epa` — offense EPA in divisional/non-divisional
- `leading_off_epa`, `trailing_off_epa` — offense EPA when leading/trailing by 7+
- Same pattern for defense: `home_def_epa`, etc.

Rolling suffixes follow convention: `{col}_roll3`, `{col}_roll6`, `{col}_std`.

### Anti-Patterns to Avoid
- **Circular SOS dependency:** Never use week W opponent data to adjust week W EPA. Always lag by 1 week.
- **Play-level aggregation for opponent schedule:** Don't groupby plays to find opponents — there are ~60 plays per team-game. Group by `(game_id, posteam)` first.
- **Applying rolling windows before pivot:** Situational splits must be pivoted to wide format first, then rolling windows applied. If you apply rolling to long format, you'll get cross-situation contamination.
- **Ranking on adjusted EPA instead of SOS score:** Rankings should be on the SOS score (mean opponent EPA), NOT on the adjusted EPA. The SOS score measures schedule difficulty; the adjusted EPA measures team quality accounting for schedule.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rolling windows | Custom shift/mean logic | `apply_team_rolling()` | Already handles shift(1), groupby, min_periods=1 |
| Play filtering | Custom REG/week/play_type filter | `_filter_valid_plays()` | Tested, handles missing columns |
| Team EPA computation | Re-aggregate EPA from plays | Consume `compute_team_epa()` output | Already computes off/def EPA per team-week |
| Ranking | Manual sort + enumerate | `pandas.DataFrame.rank()` | Handles ties, NaN, ascending/descending |

## Common Pitfalls

### Pitfall 1: Circular SOS Dependency
**What goes wrong:** Using week W opponent data to adjust week W's EPA creates circular dependency — team A's adjustment depends on team B's EPA which depends on team A's EPA.
**Why it happens:** Natural instinct is to use all available data including current week.
**How to avoid:** Strictly use weeks 1 through W-1 for opponent EPA. Week 1 raw EPA = adjusted EPA.
**Warning signs:** Week 1 adjusted EPA differs from raw EPA; test explicitly.

### Pitfall 2: None/NaN posteam Rows
**What goes wrong:** PBP contains ~2,700 rows per season where `posteam` is None (kickoffs, timeouts, quarter breaks). Including these creates phantom teams.
**Why it happens:** Not all PBP rows are plays.
**How to avoid:** `_filter_valid_plays()` already handles this by filtering to `play_type in ('pass', 'run')`. Use it for all computations.
**Warning signs:** More than 32 unique teams in output.

### Pitfall 3: score_differential Sign Convention
**What goes wrong:** Misinterpreting which team `score_differential` refers to.
**Why it happens:** Unclear whether positive means posteam or home team is leading.
**How to avoid:** In nflfastR PBP, `score_differential = posteam_score - defteam_score`. Positive means the possessing team (posteam) is leading. This is correct for our use case — when `score_differential >= 7`, the team with the ball is leading by 7+.
**Warning signs:** Leading/trailing splits are reversed; sanity check with known blowout games.

### Pitfall 4: Situational NaN Semantics
**What goes wrong:** Confusing "team didn't play at home this week" (structural NaN) with "data missing" (error NaN).
**Why it happens:** Wide format naturally produces NaN for non-applicable situations.
**How to avoid:** This is expected behavior, documented in CONTEXT.md. Rolling windows with min_periods=1 will produce values after the first applicable game occurs. Don't try to fill these NaNs.
**Warning signs:** Attempting to ffill or fillna on situational columns.

### Pitfall 5: Multiple Games Per Week for Opponent Schedule
**What goes wrong:** In normal NFL scheduling, each team plays exactly once per week (or has a bye). But the opponent extraction must deduplicate properly.
**Why it happens:** PBP has ~60+ rows per team per game. Grouping by (game_id, posteam) gives exactly one row per team-game.
**How to avoid:** Always `drop_duplicates(subset=['game_id', 'posteam'])` when building opponent schedule.
**Warning signs:** More than 1 opponent per team-week.

### Pitfall 6: SOS Ranking Direction
**What goes wrong:** Rank 1 assigned to easiest schedule instead of hardest.
**Why it happens:** Default `rank(ascending=True)` gives rank 1 to lowest value.
**How to avoid:** Use `rank(ascending=False)` for off_sos (higher opponent DEF EPA = harder schedule for offense). For def_sos, same direction — higher opponent OFF EPA = harder schedule for defense.
**Warning signs:** Historically weak-schedule teams ranked #1.

## Code Examples

### SOS Computation Core Logic
```python
def compute_sos_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute opponent-adjusted EPA and schedule difficulty rankings."""
    valid = _filter_valid_plays(pbp_df)

    # Step 1: Get raw team EPA per week
    team_epa = compute_team_epa(valid)

    # Step 2: Build opponent schedule from PBP
    schedule = _build_opponent_schedule(valid)

    # Step 3: For each team-week, compute lagged SOS
    # Join opponent EPA, filter to weeks < current week, compute mean
    rows = []
    for (team, season), group in schedule.groupby(["team", "season"]):
        weeks = sorted(group["week"].unique())
        for week in weeks:
            # Opponents faced through week-1
            prior_opps = group[group["week"] < week]["opponent"].tolist()

            if not prior_opps:
                # Week 1: no opponents faced yet
                raw = team_epa[
                    (team_epa["team"] == team) &
                    (team_epa["season"] == season) &
                    (team_epa["week"] == week)
                ]
                if raw.empty:
                    continue
                rows.append({
                    "team": team, "season": season, "week": week,
                    "off_sos_score": np.nan, "def_sos_score": np.nan,
                    "adj_off_epa": raw["off_epa_per_play"].iloc[0],
                    "adj_def_epa": raw["def_epa_per_play"].iloc[0],
                })
            else:
                # Get opponents' EPA in prior weeks
                opp_epa = team_epa[
                    (team_epa["team"].isin(prior_opps)) &
                    (team_epa["season"] == season) &
                    (team_epa["week"] < week)
                ]
                off_sos = opp_epa["def_epa_per_play"].mean()  # opponents' DEF EPA
                def_sos = opp_epa["off_epa_per_play"].mean()  # opponents' OFF EPA

                raw = team_epa[
                    (team_epa["team"] == team) &
                    (team_epa["season"] == season) &
                    (team_epa["week"] == week)
                ]
                if raw.empty:
                    continue
                rows.append({
                    "team": team, "season": season, "week": week,
                    "off_sos_score": off_sos, "def_sos_score": def_sos,
                    "adj_off_epa": raw["off_epa_per_play"].iloc[0] - off_sos,
                    "adj_def_epa": raw["def_epa_per_play"].iloc[0] - def_sos,
                })

    result = pd.DataFrame(rows)

    # Step 4: Add rankings per season-week
    result["off_sos_rank"] = result.groupby(["season", "week"])["off_sos_score"].rank(
        ascending=False, method="min"
    )
    result["def_sos_rank"] = result.groupby(["season", "week"])["def_sos_score"].rank(
        ascending=False, method="min"
    )

    # Step 5: Apply rolling windows
    stat_cols = ["off_sos_score", "def_sos_score", "adj_off_epa", "adj_def_epa"]
    result = apply_team_rolling(result, stat_cols)

    return result
```

**Performance note:** The nested loop above is O(teams * weeks * opponents). For 32 teams * 18 weeks = 576 iterations, this completes in under 1 second. A vectorized approach is possible but unnecessary for this data size and would reduce readability.

### Situational Split Core Logic
```python
def compute_situational_splits(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute home/away, divisional, and game script EPA splits."""
    valid = _filter_valid_plays(pbp_df)

    # Tag plays
    valid = valid.copy()
    valid["is_home"] = valid["posteam"] == valid["home_team"]
    valid["is_divisional"] = valid.apply(
        lambda r: TEAM_DIVISIONS.get(r["posteam"]) == TEAM_DIVISIONS.get(r["defteam"]),
        axis=1,
    )
    valid["game_script"] = np.where(
        valid["score_differential"] >= 7, "leading",
        np.where(valid["score_differential"] <= -7, "trailing", "neutral")
    )

    # Compute splits per team-week using groupby + conditional means
    # ... (aggregate, pivot to wide format, apply rolling)
```

### Integration in silver_team_transformation.py
```python
# After existing pbp_metrics and tendencies computation:
from team_analytics import compute_sos_metrics, compute_situational_splits

# 3. Compute SOS metrics
sos_df = compute_sos_metrics(pbp_df)
sos_key = f"teams/sos/season={season}/sos_{ts}.parquet"
_save_local_silver(sos_df, sos_key, ts)

# 4. Compute situational splits
sit_df = compute_situational_splits(pbp_df)
sit_key = f"teams/situational/season={season}/situational_{ts}.parquet"
_save_local_silver(sit_df, sit_key, ts)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw EPA rankings (Phase 15) | Opponent-adjusted EPA (Phase 16) | Now | More meaningful team rankings |
| Single EPA metric per team | Situational EPA splits | Now | Reveals home/away, game-state biases |

## Open Questions

1. **SOS Score for Opponent's Specific-Week EPA vs Season-to-Date EPA**
   - What we know: CONTEXT says "mean of opponents' EPA faced through week N-1"
   - What's unclear: Should we use each opponent's EPA *in the specific week they were faced*, or their cumulative season-to-date EPA at time of facing?
   - Recommendation: Use each opponent's per-game EPA from the week they were faced (e.g., if Team A played Team B in week 3, use Team B's week 3 EPA). This captures opponent strength as it was experienced. The cumulative approach would smooth out opponents but loses signal from individual matchup quality.

2. **Vectorized vs Loop SOS**
   - What we know: Loop approach is clear and fast enough for 32 teams * 18 weeks.
   - What's unclear: Whether reviewer will prefer vectorized pandas.
   - Recommendation: Start with the loop for clarity. If performance becomes an issue (it won't at this scale), refactor to vectorized. Readability > cleverness for a one-season-at-a-time computation.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.1 |
| Config file | `tests/` directory convention (no pytest.ini) |
| Quick run command | `python -m pytest tests/test_team_analytics.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SOS-01 | Week 1 adj_epa == raw_epa | unit | `python -m pytest tests/test_team_analytics.py::TestSOS::test_week1_adj_equals_raw -x` | Wave 0 |
| SOS-01 | Week 2+ adj_epa uses lagged opponent EPA | unit | `python -m pytest tests/test_team_analytics.py::TestSOS::test_lagged_opponent_adjustment -x` | Wave 0 |
| SOS-02 | Rankings 1-32 with rank 1 = hardest | unit | `python -m pytest tests/test_team_analytics.py::TestSOS::test_sos_ranking -x` | Wave 0 |
| SIT-01 | Home/away EPA split with NaN for non-applicable | unit | `python -m pytest tests/test_team_analytics.py::TestSituational::test_home_away_split -x` | Wave 0 |
| SIT-02 | Divisional tagging uses TEAM_DIVISIONS | unit | `python -m pytest tests/test_team_analytics.py::TestSituational::test_divisional_tagging -x` | Wave 0 |
| SIT-03 | Game script 7+ threshold with neutral excluded | unit | `python -m pytest tests/test_team_analytics.py::TestSituational::test_game_script_split -x` | Wave 0 |
| ALL | Rolling windows on SOS/situational columns | unit | `python -m pytest tests/test_team_analytics.py::TestSituational::test_rolling_on_splits -x` | Wave 0 |
| ALL | Idempotency: same input -> same output | unit | `python -m pytest tests/test_team_analytics.py::TestIdempotency -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_team_analytics.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_team_analytics.py` — add TestSOS, TestSituational, TestIdempotency classes
- [ ] Test fixture: multi-team multi-week PBP with home/away, divisional opponents, and varied score differentials

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/team_analytics.py` — verified `_filter_valid_plays()`, `apply_team_rolling()`, `compute_team_epa()` signatures and behavior
- Codebase inspection: `scripts/silver_team_transformation.py` — verified CLI structure, `_read_local_pbp()`, `_save_local_silver()` patterns
- Codebase inspection: `src/config.py` — verified `SILVER_TEAM_S3_KEYS` registration pattern
- Data inspection: 2024 PBP Bronze parquet — verified all required columns (posteam, defteam, home_team, away_team, epa, score_differential, game_id), 32 teams, column types
- Codebase inspection: `tests/test_team_analytics.py` — verified test patterns, fixture helpers

### Secondary (MEDIUM confidence)
- nflfastR documentation: `score_differential = posteam_score - defteam_score` (positive = posteam leading)
- NFL scheduling: divisions are static since 2002 realignment (32 teams, 8 divisions)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, all pandas/numpy already in use
- Architecture: HIGH - follows established Phase 15 patterns exactly
- Pitfalls: HIGH - verified from actual PBP data inspection (None posteam rows, score_differential range and NaN rate)
- SOS algorithm: HIGH - simple additive adjustment with clear lagging rule from CONTEXT.md

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable domain, no external dependency changes expected)
