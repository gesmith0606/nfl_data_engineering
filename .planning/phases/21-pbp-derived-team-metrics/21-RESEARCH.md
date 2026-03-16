# Phase 21: PBP-Derived Team Metrics - Research

**Researched:** 2026-03-16
**Domain:** PBP data transformation, team-level metrics, pandas aggregation
**Confidence:** HIGH

## Summary

Phase 21 adds eleven new team-level metric categories to the Silver layer by computing aggregates from the 140-column PBP Bronze data ingested in Phase 20. All required PBP columns are confirmed present in the data (verified against 2024 season, 49,492 rows, 140 columns). The existing `team_analytics.py` module already has the exact orchestrator pattern (`compute_pbp_metrics`), rolling window function (`apply_team_rolling`), and filtering helpers needed -- the new code follows the same structure with a new `compute_pbp_derived_metrics(pbp_df)` orchestrator.

Key data findings: penalty plays identified via `penalty == 1` flag (3,642 per season), split cleanly into offensive (2,143) and defensive (1,499) via `penalty_team == posteam/defteam`. No `touchback` column exists -- touchbacks must be inferred from `return_yards == 0` combined with returner ID absence. Drive-level red zone trips average 4.0 per team-game (range 0-8), confirming drive-level `nunique` is correct. `drive_time_of_possession` is a string in `"M:SS"` format requiring parsing.

**Primary recommendation:** Follow the established orchestrator pattern exactly. Create `compute_pbp_derived_metrics(pbp_df)` that calls 11 individual `compute_*` functions, merges on `(team, season, week)`, and applies `apply_team_rolling()`. ST and penalty functions receive raw PBP; others receive `_filter_valid_plays()` output.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Single new orchestrator function `compute_pbp_derived_metrics(pbp_df)` in `team_analytics.py` -- mirrors existing `compute_pbp_metrics()` pattern
- Calls 11 individual `compute_*` functions, merges all on `(team, season, week)`, applies `apply_team_rolling()` at the end
- Orchestrator calls `_filter_valid_plays()` once and passes filtered plays to most functions
- ST and penalty functions receive **raw PBP** and apply their own filters (like `compute_fourth_down_aggressiveness()` pattern)
- Red zone trip volume: extend existing `compute_red_zone_metrics()` to add `off_rz_trips` and `def_rz_trips` columns (drive-level `nunique` already computed there)
- Use `penalty == 1` flag to identify penalty plays (not `play_type == 'penalty'`)
- Split offensive vs defensive penalties using `penalty_team` column
- New `_filter_st_plays(pbp_df)` helper -- filters to `special_teams_play == 1` or `play_type in ('field_goal', 'punt', 'kickoff', 'extra_point')`
- FG accuracy buckets: NFL standard 4-bucket split -- <30 / 30-39 / 40-49 / 50+ yards using `kick_distance`
- Punt/kick return touchbacks excluded from return yard average; touchback rate is its own column
- ST metrics split by kicking team vs returning team
- Turnover luck: fumble recovery rate vs 50% baseline; season-to-date cumulative with `shift(1)` lag, not rolling windows
- Single combined parquet file per season under `teams/pbp_derived/season=YYYY/`
- Extend existing `silver_team_transformation.py` -- add `compute_pbp_derived_metrics` import and call
- Add `pbp_derived` key to `SILVER_TEAM_S3_KEYS` in `config.py`
- Add corresponding entry to `check_pipeline_health.py`

### Claude's Discretion
- Exact column names for the 11 metric categories (follow existing naming conventions: `off_`/`def_` prefix, descriptive suffix)
- Whether `_filter_st_plays()` needs season_type/week filtering or inherits from the orchestrator
- How to handle edge cases: teams with 0 FG attempts in a game, 0 punt returns, etc. (NaN is fine)
- Explosive play yard thresholds confirmation (20+ pass, 10+ rush per PBP-08 requirement)
- Drive efficiency column naming for 3-and-out rate, avg drive plays/yards

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PBP-01 | Team penalty rates (count, yards/game, offensive holding/DPI/roughing) with off/def split and rolling windows | `penalty == 1` flag confirmed (3,642/season). `penalty_team` splits cleanly to off (2,143) / def (1,499). `penalty_type` has specific types (False Start, Offensive Holding, DPI, Roughing the Passer). |
| PBP-02 | Opponent-drawn penalty rates with rolling windows | Same `penalty_team` logic inverted: penalties drawn = opponent's penalties. Defensive penalties drawn by offense = `penalty_team == defteam` grouped by `posteam`. |
| PBP-03 | Turnover luck metrics (fumble recovery rate, earned vs lucky turnovers, regression-to-mean indicator) | `fumble == 1` (663/season), `fumble_recovery_1_team` column present (608 non-null). Compare recovery team to posteam to determine own/opponent recovery. |
| PBP-04 | Red zone trip volume (drive-level counts per team/game) | Existing `compute_red_zone_metrics()` already uses `drive` `nunique`. Mean 4.0 trips/team-game (range 0-8) confirms drive-level counting is correct. |
| PBP-05 | Special teams FG accuracy by distance bucket | `field_goal_attempt == 1` (1,166/season), `kick_distance` range 19-70 yards, `field_goal_result` values: made/missed/blocked. |
| PBP-06 | Special teams punt/kick return averages and touchback rates | `punt_attempt` (2,119), `kickoff_attempt` (2,956), `return_yards` present. No `touchback` column -- use `return_yards == 0 AND returner_player_id IS NULL` proxy. |
| PBP-07 | 3rd down conversion rates (off/def) with rolling windows | `third_down_converted` (2,864/season), `third_down_failed` (4,334). Filter `down == 3` plays. |
| PBP-08 | Explosive play rates (20+ yd pass, 10+ yd rush) off/def with rolling windows | Pass 20+ yards: 1,672/season. Rush 10+ yards: 1,804/season. Use `yards_gained` with `play_type` filter. |
| PBP-09 | Drive efficiency (3-and-out rate, avg drive length in plays and yards, drives/game) | `drive_play_count` and `drive_time_of_possession` present. TOP is string format "M:SS" -- needs parsing to seconds. |
| PBP-10 | Team sack rates (OL protection rate + defensive pass rush rate) | `sack == 1` (1,392/season). Compute as sacks / dropbacks for both off and def sides. |
| PBP-11 | Time of possession per team with rolling windows | `drive_time_of_possession` (string "M:SS") needs parsing. Sum per team-game from drive-level grouping. |
| INTEG-02 | All new features use rolling windows (3-game, 6-game, season-to-date) with shift(1) lag | `apply_team_rolling()` already implements exactly this. Turnover luck uses expanding window instead (per user decision). |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | existing | All DataFrame aggregation and groupby operations | Already used throughout project |
| numpy | existing | NaN handling, conditional logic (np.where) | Already used throughout project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyarrow | existing | Parquet read/write | Already used for all Bronze/Silver I/O |

No new dependencies required. All computation is pandas groupby/agg operations.

## Architecture Patterns

### Recommended Project Structure
```
src/
  team_analytics.py         # Add 11 new compute_* functions + orchestrator + _filter_st_plays helper
scripts/
  silver_team_transformation.py  # Add compute_pbp_derived_metrics import + call in run loop
src/
  config.py                 # Add pbp_derived to SILVER_TEAM_S3_KEYS
scripts/
  check_pipeline_health.py  # Add pbp_derived to REQUIRED_SILVER_PREFIXES
tests/
  test_team_analytics.py    # Add unit tests for all 11 new compute functions
```

### Pattern 1: Orchestrator with Individual Compute Functions
**What:** Single orchestrator calls individual metric functions, merges results, applies rolling windows.
**When to use:** Always -- this is the established pattern.
**Example:**
```python
# Source: existing compute_pbp_metrics() in team_analytics.py
def compute_pbp_derived_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    valid = _filter_valid_plays(pbp_df)
    # ST/penalty functions get raw pbp_df
    penalties_df = compute_penalty_metrics(pbp_df)
    opp_penalties_df = compute_opp_drawn_penalties(pbp_df)
    # Most functions get filtered valid plays
    third_down_df = compute_third_down_rates(valid)
    explosive_df = compute_explosive_plays(valid)
    sack_df = compute_sack_rates(valid)
    # ... etc
    # Merge all on (team, season, week)
    merged = penalties_df.merge(opp_penalties_df, on=["team", "season", "week"], how="outer")
    # ... chain merges
    # Apply rolling
    stat_cols = [c for c in merged.columns if c not in {"team", "season", "week"}]
    # Exclude turnover luck from rolling (uses expanding window separately)
    result = apply_team_rolling(merged, stat_cols)
    return result
```

### Pattern 2: Raw PBP Functions (ST/Penalty)
**What:** Functions that need plays beyond run/pass (penalties, ST) receive raw PBP and filter themselves.
**When to use:** For penalty and special teams metrics.
**Example:**
```python
# Source: existing compute_fourth_down_aggressiveness() pattern
def compute_penalty_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    df = pbp_df.copy()
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]
    pen = df[df["penalty"] == 1]
    # ... aggregate by posteam/defteam
```

### Pattern 3: Drive-Level Aggregation
**What:** Group by `(posteam, season, week, drive)` first, then aggregate to team-week level.
**When to use:** Red zone trips, drive efficiency, TOP.
**Example:**
```python
# Drive-level first, then team-week
drive_stats = valid.groupby(["posteam", "season", "week", "drive"]).agg(
    drive_plays=("play_id", "count"),
    drive_yards=("yards_gained", "sum"),
).reset_index()
# Then team-week aggregation
team_week = drive_stats.groupby(["posteam", "season", "week"]).agg(
    avg_drive_plays=("drive_plays", "mean"),
    total_drives=("drive", "nunique"),
).reset_index()
```

### Anti-Patterns to Avoid
- **Using `_filter_valid_plays()` for ST or penalty metrics:** This filters to `play_type in ('pass', 'run')` which excludes ST plays entirely and excludes penalty-only plays. ST and penalty functions MUST receive raw PBP.
- **Play-level red zone counting:** Counting `yardline_100 <= 20` plays gives 15+ per team-game. Use `drive` `nunique` for 3-5 trips/game.
- **Using `play_type == 'penalty'`:** Wrong approach. Penalties are flagged via `penalty == 1` on plays that also have a regular play_type.
- **Applying rolling windows to turnover luck:** Per user decision, turnover luck uses season-to-date cumulative (expanding window with shift(1)), not rolling windows.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rolling windows with lag | Custom shift/rolling logic | `apply_team_rolling()` | Already handles shift(1), min_periods=1, expanding STD |
| Valid play filtering | Custom play_type + season_type filter | `_filter_valid_plays()` | Handles all edge cases (missing columns, NaN EPA) |
| Parquet I/O with paths | Manual path construction | `_save_local_silver()` + `SILVER_TEAM_S3_KEYS` | Consistent with all other Silver outputs |

## Common Pitfalls

### Pitfall 1: No `touchback` Column in PBP Data
**What goes wrong:** Code references `df['touchback']` which does not exist.
**Why it happens:** nflverse PBP schema has no dedicated touchback flag in the 140-column subset.
**How to avoid:** Define touchback as: `return_yards == 0 AND returner_player_id IS NULL` (for kickoffs) or `punt_in_endzone == 1` (for punts). For kickoffs, when `kickoff_in_endzone == 1` but the ball is returned, that's NOT a touchback.
**Warning signs:** KeyError on 'touchback' column.

### Pitfall 2: `drive_time_of_possession` is a String
**What goes wrong:** Attempting arithmetic on "7:13" string values.
**Why it happens:** nflverse stores TOP as "M:SS" string format.
**How to avoid:** Parse to seconds: `top_parts = df['drive_time_of_possession'].str.split(':'); seconds = top_parts[0].astype(float) * 60 + top_parts[1].astype(float)`. Handle NaN before splitting.
**Warning signs:** TypeError on string arithmetic.

### Pitfall 3: FG `kick_distance` vs Actual Yard Line
**What goes wrong:** Using `kick_distance` directly as the FG attempt distance.
**Why it happens:** `kick_distance` in nflverse PBP is the total kick distance (ball travel), not the yard line. For FGs, it closely matches the yard line + ~7 yards for snap + hold.
**How to avoid:** For bucket classification, `kick_distance` is appropriate -- it represents actual kick length and is what NFL broadcasts use for FG distance. Values range 19-70 in the data.
**Warning signs:** Unexpected bucket distributions if using `yardline_100` directly.

### Pitfall 4: ST Play Filtering Overlap
**What goes wrong:** Missing field_goal plays because they have `special_teams_play == 0` in some edge cases.
**Why it happens:** In the 2024 data, all 1,166 FG attempts have `special_teams_play == 1`. However, the CONTEXT decision to use `special_teams_play == 1 OR play_type in ('field_goal', 'punt', 'kickoff', 'extra_point')` provides belt-and-suspenders safety.
**How to avoid:** Use the union filter as specified in the CONTEXT decisions.
**Warning signs:** FG count mismatch between ST filter and direct `field_goal_attempt == 1`.

### Pitfall 5: Turnover Luck Expanding Window vs Rolling
**What goes wrong:** Applying standard `apply_team_rolling()` to turnover luck metrics, which creates `_roll3`/`_roll6` columns.
**Why it happens:** Following the default pattern without reading the user decision that turnover luck uses season-to-date cumulative.
**How to avoid:** Compute turnover luck with `groupby(['team', 'season']).expanding().mean()` with `shift(1)` lag. Exclude turnover luck raw columns from the `apply_team_rolling()` stat_cols list.
**Warning signs:** Turnover luck metrics have `_roll3`/`_roll6` columns that shouldn't exist.

### Pitfall 6: Penalty Split Missing Rows
**What goes wrong:** Off/def penalty counts don't sum to total because some plays have `penalty == 1` but `penalty_team` is null or doesn't match either team.
**Why it happens:** In the 2024 data, all 3,642 penalty plays split cleanly (2,143 off + 1,499 def = 3,642). But older seasons or edge cases could differ.
**How to avoid:** Verify `penalty_team` is not null before splitting. Drop rows where `penalty_team` doesn't match either `posteam` or `defteam`.
**Warning signs:** Penalty totals don't reconcile.

## Code Examples

### Penalty Metrics (PBP-01)
```python
# Verified column names and distributions from 2024 PBP data
def compute_penalty_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    df = pbp_df.copy()
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    pen = df[df["penalty"] == 1].copy()
    pen = pen.dropna(subset=["penalty_team"])

    # Offensive penalties (penalty_team == posteam)
    off_pen = pen[pen["penalty_team"] == pen["posteam"]]
    off_agg = off_pen.groupby(["posteam", "season", "week"]).agg(
        off_penalties=("penalty", "sum"),
        off_penalty_yards=("penalty_yards", "sum"),
    ).reset_index().rename(columns={"posteam": "team"})

    # Defensive penalties
    def_pen = pen[pen["penalty_team"] == pen["defteam"]]
    def_agg = def_pen.groupby(["defteam", "season", "week"]).agg(
        def_penalties=("penalty", "sum"),
        def_penalty_yards=("penalty_yards", "sum"),
    ).reset_index().rename(columns={"defteam": "team"})

    result = off_agg.merge(def_agg, on=["team", "season", "week"], how="outer")
    return result
```

### ST Filter Helper
```python
def _filter_st_plays(pbp_df: pd.DataFrame) -> pd.DataFrame:
    df = pbp_df.copy()
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    st_mask = (df.get("special_teams_play", pd.Series(dtype=float)) == 1)
    type_mask = df["play_type"].isin(["field_goal", "punt", "kickoff", "extra_point"])
    return df[st_mask | type_mask].reset_index(drop=True)
```

### FG Buckets (PBP-05)
```python
# kick_distance range in data: 19-70 yards
def _fg_bucket(distance):
    if distance < 30:
        return "short"
    elif distance < 40:
        return "mid"
    elif distance < 50:
        return "long"
    else:
        return "50plus"

# Usage: fg["bucket"] = fg["kick_distance"].apply(_fg_bucket)
# Then pivot or groupby bucket for accuracy rates
```

### Touchback Detection (PBP-06)
```python
# No 'touchback' column exists -- use proxy
# Kickoff touchback: return_yards == 0 AND no returner
ko["is_touchback"] = (ko["return_yards"] == 0) & (ko["kickoff_returner_player_id"].isna())
# Punt touchback: punt_in_endzone == 1
punts["is_touchback"] = punts["punt_in_endzone"] == 1
```

### TOP Parsing (PBP-11)
```python
# drive_time_of_possession is string "M:SS" format
def _parse_top_seconds(top_str):
    if pd.isna(top_str):
        return np.nan
    parts = str(top_str).split(":")
    return float(parts[0]) * 60 + float(parts[1])
```

### Drive Efficiency 3-and-Out Detection (PBP-09)
```python
# 3-and-out: drive with <= 3 plays and no first down/score
# Use drive_play_count from PBP data (already at drive level)
drives = valid.groupby(["posteam", "season", "week", "drive"]).agg(
    plays=("play_id", "count"),
    first_downs=("first_down", "sum"),
    touchdowns=("touchdown", "sum"),
).reset_index()
drives["is_three_and_out"] = (drives["plays"] <= 3) & (drives["first_downs"] == 0) & (drives["touchdowns"] == 0)
```

## Recommended Column Names

Based on existing `off_`/`def_` prefix convention in `team_analytics.py`:

| Metric Category | Columns |
|----------------|---------|
| PBP-01 Penalties | `off_penalties`, `off_penalty_yards`, `def_penalties`, `def_penalty_yards` |
| PBP-02 Opp-drawn | `off_penalties_drawn`, `off_penalty_yards_drawn`, `def_penalties_drawn`, `def_penalty_yards_drawn` |
| PBP-03 Turnover luck | `fumbles_lost`, `fumbles_forced`, `own_fumble_recovery_rate`, `opp_fumble_recovery_rate`, `is_turnover_lucky` |
| PBP-04 RZ trips | `off_rz_trips`, `def_rz_trips` (added to existing `compute_red_zone_metrics`) |
| PBP-05 FG accuracy | `fg_att`, `fg_pct`, `fg_pct_short`, `fg_pct_mid`, `fg_pct_long`, `fg_pct_50plus` |
| PBP-06 Returns | `ko_return_avg`, `ko_touchback_rate`, `punt_return_avg`, `punt_touchback_rate` |
| PBP-07 3rd down | `off_third_down_rate`, `def_third_down_rate` |
| PBP-08 Explosive | `off_explosive_pass_rate`, `off_explosive_rush_rate`, `def_explosive_pass_rate`, `def_explosive_rush_rate` |
| PBP-09 Drive efficiency | `off_three_and_out_rate`, `off_avg_drive_plays`, `off_avg_drive_yards`, `off_drives_per_game`, `def_three_and_out_rate`, `def_avg_drive_plays`, `def_avg_drive_yards` |
| PBP-10 Sack rates | `off_sack_rate`, `def_sack_rate` |
| PBP-11 TOP | `off_top_seconds`, `def_top_seconds` |

## Data Volume Estimates

| Metric | Per Season Rows | Columns (raw) | Columns (with rolling) |
|--------|----------------|---------------|----------------------|
| All 11 categories merged | ~544 (32 teams x 17 weeks) | ~35-40 | ~140-160 |
| Parquet file size (est.) | - | - | ~200-500 KB per season |

## Integration Points

### config.py
```python
SILVER_TEAM_S3_KEYS = {
    # existing...
    "pbp_derived": "teams/pbp_derived/season={season}/pbp_derived_{ts}.parquet",
}
```

### check_pipeline_health.py
```python
REQUIRED_SILVER_PREFIXES = {
    # existing...
    "pbp_derived": "teams/pbp_derived/season={season}/",
}
```

### silver_team_transformation.py
```python
from team_analytics import (
    # existing imports...
    compute_pbp_derived_metrics,
)
# In run loop, after existing compute calls:
pbp_derived_df = compute_pbp_derived_metrics(pbp_df)
# Save with SILVER_TEAM_S3_KEYS["pbp_derived"]
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | tests/ directory, pytest invoked via `python -m pytest tests/ -v` |
| Quick run command | `python -m pytest tests/test_team_analytics.py -v -x` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PBP-01 | Penalty counts/yards by off/def | unit | `python -m pytest tests/test_team_analytics.py::test_compute_penalty_metrics -x` | Wave 0 |
| PBP-02 | Opponent-drawn penalties | unit | `python -m pytest tests/test_team_analytics.py::test_compute_opp_drawn_penalties -x` | Wave 0 |
| PBP-03 | Turnover luck with expanding window | unit | `python -m pytest tests/test_team_analytics.py::test_compute_turnover_luck -x` | Wave 0 |
| PBP-04 | Red zone trip volume (drive-level) | unit | `python -m pytest tests/test_team_analytics.py::test_red_zone_trips -x` | Wave 0 |
| PBP-05 | FG accuracy by distance bucket | unit | `python -m pytest tests/test_team_analytics.py::test_compute_fg_accuracy -x` | Wave 0 |
| PBP-06 | Punt/kick return + touchback | unit | `python -m pytest tests/test_team_analytics.py::test_compute_return_metrics -x` | Wave 0 |
| PBP-07 | 3rd down conversion rates | unit | `python -m pytest tests/test_team_analytics.py::test_compute_third_down_rates -x` | Wave 0 |
| PBP-08 | Explosive play rates | unit | `python -m pytest tests/test_team_analytics.py::test_compute_explosive_plays -x` | Wave 0 |
| PBP-09 | Drive efficiency (3-and-out, avg length) | unit | `python -m pytest tests/test_team_analytics.py::test_compute_drive_efficiency -x` | Wave 0 |
| PBP-10 | Sack rates off/def | unit | `python -m pytest tests/test_team_analytics.py::test_compute_sack_rates -x` | Wave 0 |
| PBP-11 | Time of possession | unit | `python -m pytest tests/test_team_analytics.py::test_compute_top -x` | Wave 0 |
| INTEG-02 | Rolling windows with shift(1) lag | unit | `python -m pytest tests/test_team_analytics.py::test_pbp_derived_rolling -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_team_analytics.py -v -x`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_team_analytics.py` -- add 11-12 new test functions for PBP-derived metrics (file exists, add to it)
- [ ] Test fixtures: extend `_make_pbp_rows()` helper with penalty, ST, fumble, drive, and sack fields

## Sources

### Primary (HIGH confidence)
- Actual PBP parquet data at `data/bronze/pbp/season=2024/` -- direct column inspection and distribution analysis
- Existing `src/team_analytics.py` -- verified orchestrator pattern, rolling window function, filtering helpers
- Existing `scripts/silver_team_transformation.py` -- verified script wiring pattern
- Existing `src/config.py` -- verified `SILVER_TEAM_S3_KEYS` structure and `PBP_COLUMNS` list

### Secondary (MEDIUM confidence)
- nflverse PBP column semantics -- inferred from data distributions (e.g., touchback proxy from return_yards + returner ID)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries needed, all pandas/numpy
- Architecture: HIGH -- follows exact established patterns in team_analytics.py
- Data schema: HIGH -- verified all 140 columns present in actual parquet files
- Pitfalls: HIGH -- discovered from actual data inspection (no touchback column, TOP string format)
- Column names: MEDIUM -- recommended names follow convention but are Claude's discretion per CONTEXT

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (stable -- data schema won't change, patterns are established)
