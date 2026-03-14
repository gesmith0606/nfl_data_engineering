# Phase 17: Advanced Player Profiles - Research

**Researched:** 2026-03-14
**Domain:** NFL advanced stats integration (NGS, PFR, QBR) into Silver layer
**Confidence:** HIGH

## Summary

Phase 17 integrates three advanced stat sources (NGS, PFR, QBR) from existing Bronze parquet files into a unified Silver player profile with rolling windows. The core challenge is player ID reconciliation across three different ID systems, not the metric computation itself. NGS uses GSIS IDs (100% match with existing player data), PFR uses PFR-specific IDs (requires name+team join), and QBR uses ESPN IDs (requires name+team join).

All three data sources already exist as Bronze parquet files with weekly granularity. The rolling window pattern is well-established from `team_analytics.py:apply_team_rolling()` and needs only minor adaptation for player-level grouping with `min_periods=3`. The output structure (single wide Parquet per season) and CLI pattern (from `silver_team_transformation.py`) are directly reusable.

**Primary recommendation:** Join NGS via `player_gsis_id` = `player_id` (100% match rate proven). Join PFR and QBR via normalized `player_display_name` + `team` + `season` + `week`. Use team abbreviation normalization map for known mismatches (LA/LAR, WAS/WSH).

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Use PLAYER_DATA_SEASONS (2020-2025) for all three sources -- consistent with existing Silver player data
- Do not use each source's full historical range (NGS 2016+, PFR 2018+, QBR 2006+)
- Left-join from Bronze roster/player data as the master list
- Join NGS/PFR/QBR onto roster by name+team+season
- Players without advanced stats get NaN columns -- preserved in output (no silent row drops)
- PFR match rate (~80%) logged at WARNING level with unmatched player names; match rate reported at INFO level
- Never fail the pipeline on match quality -- log warnings only
- Single merged wide Parquet file per season at `data/silver/players/advanced/season=YYYY/`
- All NGS, PFR, and QBR columns in one row per player-week
- Read from Bronze parquet files at data/bronze/ngs/, data/bronze/pfr/, data/bronze/qbr/
- Do not call nfl-data-py live -- Bronze layer is the source of truth
- New script: `scripts/silver_advanced_transformation.py`
- Always processes all three sources (NGS + PFR + QBR) in every run -- no selective --sources flag
- Full season processing via `--seasons` argument
- If Bronze data for a source is missing for a season, log warning and produce output with NaN columns
- New file: `src/player_advanced_analytics.py`
- Rolling windows: shift(1) for lag, groupby([player_id, season]), min_periods=3
- Column naming: `{metric}_roll3`, `{metric}_roll6` suffix

### Claude's Discretion
- Exact NGS/PFR/QBR column selection and naming
- Player ID join logic details (fuzzy matching, name normalization)
- How to handle mid-season team changes for player matching
- NaN coverage logging format at write time
- Whether to include season-to-date (STD) expanding average alongside roll3/roll6

### Deferred Ideas (OUT OF SCOPE)
- Integrate advanced profiles into projection engine (Gold layer) -- tracked as GOLD-01/GOLD-02
- PFR seasonal aggregates as alternative to weekly rolling
- NGS combine-style speed/burst metrics linked to profiles -- Phase 18
- Positional matchup grades using advanced profiles (WR vs CB) -- Phase 5

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PROF-01 | NGS WR/TE profile (separation, catch probability, intended air yards) with rolling windows | Bronze NGS receiving schema verified: `avg_separation`, `catch_percentage`, `avg_intended_air_yards` available weekly. 100% GSIS ID match. |
| PROF-02 | NGS QB profile (time-to-throw, aggressiveness, completed air yards) with rolling windows | Bronze NGS passing schema verified: `avg_time_to_throw`, `aggressiveness`, `avg_completed_air_yards` available weekly. |
| PROF-03 | NGS RB profile (rush yards over expected, efficiency) with rolling windows | Bronze NGS rushing schema verified: `rush_yards_over_expected`, `rush_yards_over_expected_per_att`, `efficiency` available weekly. |
| PROF-04 | PFR pressure rate per QB with rolling windows | Bronze PFR pass schema has `times_pressured_pct` pre-computed, plus `times_hit`, `times_hurried`, `times_sacked` for manual formula. Join by name+team. |
| PROF-05 | PFR blitz rate per defensive team with rolling windows | Bronze PFR def schema has `def_times_blitzed` per defender per week. Aggregate to team level: sum(blitzes)/count(rows) or total blitzes per game. |
| PROF-06 | QBR rolling windows (total QBR, points added) per QB | Bronze QBR has `qbr_total`, `pts_added` weekly. QB-only. Join by normalized name+team. QBR Bronze only has 2006-2023; seasons 2024-2025 will produce NaN. |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | (existing) | DataFrame ops, rolling windows, merges | Already used throughout project |
| pyarrow | (existing) | Parquet read/write | Already used throughout project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | (existing) | NaN handling | Already imported in analytics modules |
| logging | stdlib | Match rate reporting, NaN coverage | Required by coding patterns |

No new dependencies needed. Everything builds on existing pandas/pyarrow stack.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── player_advanced_analytics.py   # NEW: NGS/PFR/QBR processing + rolling
├── player_analytics.py            # EXISTING: PBP-derived player metrics
├── team_analytics.py              # EXISTING: team metrics (pattern reference)
├── config.py                      # MODIFY: add SILVER_PLAYER_S3_KEYS entry
scripts/
├── silver_advanced_transformation.py  # NEW: CLI script
├── silver_team_transformation.py      # EXISTING: pattern reference
tests/
├── test_player_advanced_analytics.py  # NEW: unit tests
```

### Pattern 1: Player Rolling Window (adapted from team_analytics.py)
**What:** Rolling averages grouped by (player_id, season) with shift(1) lag and min_periods=3
**When to use:** All NGS/PFR/QBR metric columns
**Example:**
```python
# Adapted from team_analytics.apply_team_rolling()
def apply_player_rolling(
    df: pd.DataFrame,
    stat_cols: list,
    player_col: str = "player_gsis_id",
    windows: list = None,
) -> pd.DataFrame:
    if windows is None:
        windows = [3, 6]
    df = df.sort_values([player_col, "season", "week"])
    for window in windows:
        roll_cols = {}
        for col in stat_cols:
            roll_cols[f"{col}_roll{window}"] = (
                df.groupby([player_col, "season"])[col]
                .transform(
                    lambda s: s.shift(1).rolling(window, min_periods=3).mean()
                )
            )
        df = df.assign(**roll_cols)
    # Optional STD (season-to-date expanding average)
    for col in stat_cols:
        df[f"{col}_std"] = (
            df.groupby([player_col, "season"])[col]
            .transform(lambda s: s.shift(1).expanding(min_periods=3).mean())
        )
    return df
```

### Pattern 2: Bronze Local Read (from silver_team_transformation.py)
**What:** Read latest parquet file from local Bronze directory
**When to use:** All data source reads (NGS, PFR, QBR)
**Example:**
```python
def _read_local_bronze(subdir: str, season: int) -> pd.DataFrame:
    pattern = os.path.join(BRONZE_DIR, subdir, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])
```

### Pattern 3: Player ID Join Strategy
**What:** Three-tier join based on data source ID system
**When to use:** Merging NGS/PFR/QBR onto master player list

**Tier 1 - NGS (direct ID join, 100% match):**
```python
# NGS player_gsis_id == player weekly player_id (verified 100% overlap)
ngs_df.merge(master, left_on=["player_gsis_id", "season", "week"],
             right_on=["player_id", "season", "week"], how="right")
```

**Tier 2 - PFR (name+team join, ~80% match):**
```python
# Normalize names and team abbreviations before join
# PFR uses "LA" for Rams; standard uses "LA". QBR uses "LAR".
pfr_df.merge(master, left_on=["pfr_player_name_norm", "team_norm", "season", "week"],
             right_on=["player_display_name_norm", "recent_team_norm", "season", "week"],
             how="right")
```

**Tier 3 - QBR (name+team join, QB-only):**
```python
# QBR uses "WSH" vs standard "WAS", "LAR" vs "LA"
qbr_df.merge(master, left_on=["name_display_norm", "team_norm", "season", "week"],
             right_on=["player_display_name_norm", "recent_team_norm", "season", "week"],
             how="right")
```

### Anti-Patterns to Avoid
- **Inner join on advanced stats:** Would silently drop players without advanced data. Always use left join from master player list.
- **Cross-season rolling windows:** Must groupby [player_id, season] to prevent week 18 of season N bleeding into week 1 of season N+1.
- **Team abbreviation assumption:** PFR uses "LA" for Rams, QBR uses "LAR", NGS uses "LAR". Must normalize.
- **Processing NGS week=0 rows:** Week 0 is seasonal aggregate in NGS data. Filter to week > 0 for weekly rolling windows.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rolling windows | Custom window logic | `apply_team_rolling()` pattern adapted for players | Proven shift(1) + groupby pattern, handles edge cases |
| Pressure rate | Manual (hits+hurries+sacks)/dropbacks | PFR `times_pressured_pct` column | Already pre-computed in Bronze PFR data |
| Parquet read/write | Custom S3 logic | `_read_local_bronze()` / `_save_local_silver()` patterns | Established local-first patterns from silver_team_transformation.py |
| Name normalization | Regex-based fuzzy matching | Simple `.str.strip().str.lower()` normalization | Sufficient for ~80% match; fuzzy matching adds complexity for marginal gain |

**Key insight:** PFR already provides `times_pressured_pct` pre-computed. PROF-04 can use this directly rather than computing (hits+hurries+sacks)/dropbacks. However, the raw components should also be preserved as columns for downstream analysis.

## Common Pitfalls

### Pitfall 1: Team Abbreviation Mismatches
**What goes wrong:** Joins fail silently, producing all-NaN advanced columns for affected teams
**Why it happens:** Three sources use different abbreviations (LA vs LAR, WAS vs WSH)
**How to avoid:** Create a normalization map applied before any join:
```python
TEAM_ABBR_NORM = {"LAR": "LA", "WSH": "WAS"}  # Map non-standard -> standard
```
**Warning signs:** NaN coverage > 50% for specific teams in output

### Pitfall 2: NGS Week 0 Seasonal Aggregates
**What goes wrong:** Seasonal totals mixed with weekly data inflate rolling averages
**Why it happens:** NGS data includes week=0 rows (season-level aggregates alongside weekly rows)
**How to avoid:** Filter `df[df['week'] > 0]` before any weekly processing
**Warning signs:** Unusually high values in week 1 rolling averages

### Pitfall 3: QBR Limited Season Coverage
**What goes wrong:** Pipeline fails when QBR data missing for 2024-2025 seasons
**Why it happens:** Bronze QBR only covers through 2023. Seasons 2024-2025 have no QBR data.
**How to avoid:** Per locked decision: log warning and produce NaN QBR columns for missing seasons. Never fail on missing data.
**Warning signs:** QBR NaN coverage is 100% for seasons 2024+

### Pitfall 4: PFR Blitz Rate - Player vs Team Level
**What goes wrong:** Confusing individual defender blitz counts with team-level blitz rate
**Why it happens:** PFR def data has one row per defender per game, not per team
**How to avoid:** PROF-05 requires team-level blitz rate. Must aggregate `def_times_blitzed` to team level before applying rolling windows. This is a team metric living in the player profile for convenience.
**Warning signs:** Thousands of rows instead of ~32 per week

### Pitfall 5: QBR Column Applied to Non-QBs
**What goes wrong:** QBR values appear on RB/WR/TE rows
**Why it happens:** Merging QBR without position filtering
**How to avoid:** Only merge QBR data onto QB-position rows. For non-QB rows, QBR columns should be NaN.
**Warning signs:** QBR values on WR rows

### Pitfall 6: min_periods=3 Produces NaN for First 2 Weeks
**What goes wrong:** Users expect rolling values from week 1 but see NaN
**Why it happens:** min_periods=3 requires at least 3 data points, combined with shift(1) means first 3 weeks produce NaN
**How to avoid:** This is by design (success criteria #5). Document in output metadata.
**Warning signs:** Expected behavior, not a bug

## Code Examples

### NGS Column Selection (PROF-01, PROF-02, PROF-03)

```python
# Source: Bronze NGS parquet inspection (2023 season)

# PROF-01: WR/TE receiving profile
NGS_RECEIVING_COLS = [
    "avg_separation",          # Average separation from nearest defender
    "catch_percentage",        # Catch rate
    "avg_intended_air_yards",  # Average depth of target
    "avg_cushion",            # Pre-snap cushion
    "avg_yac",                # Yards after catch
    "avg_expected_yac",       # Expected YAC
    "avg_yac_above_expectation",  # YAC over expected
]

# PROF-02: QB passing profile
NGS_PASSING_COLS = [
    "avg_time_to_throw",                        # Time from snap to throw
    "aggressiveness",                            # Tight-window throw rate
    "avg_completed_air_yards",                   # Completed air distance
    "avg_intended_air_yards",                    # Average depth of target
    "avg_air_yards_differential",                # Intended - completed
    "completion_percentage_above_expectation",   # CPOE (NGS version)
    "expected_completion_percentage",            # xComp%
]

# PROF-03: RB rushing profile
NGS_RUSHING_COLS = [
    "rush_yards_over_expected",          # RYOE total
    "rush_yards_over_expected_per_att",  # RYOE per attempt
    "efficiency",                         # Rush efficiency
    "avg_time_to_los",                   # Time to line of scrimmage
    "rush_pct_over_expected",            # Rush % over expected
]
```

### PFR Pressure Rate (PROF-04)

```python
# Source: Bronze PFR pass parquet inspection (2023 season)
# times_pressured_pct is pre-computed in PFR data
# Also preserve raw components for downstream analysis

PFR_PRESSURE_COLS = [
    "times_pressured_pct",  # Pre-computed pressure rate
    "times_sacked",         # Raw sack count
    "times_hurried",        # Raw hurry count
    "times_hit",            # Raw hit count
    "times_blitzed",        # How often QB was blitzed
    "passing_bad_throw_pct",  # Bad throw rate (bonus metric)
]
```

### PFR Team Blitz Rate (PROF-05)

```python
# Source: Bronze PFR def parquet inspection (2023 season)
# PFR def data is per-defender per-game. Must aggregate to team level.

def compute_team_blitz_rate(pfr_def_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate defender-level PFR data to team-level blitz/pressure metrics."""
    team_agg = pfr_def_df.groupby(["team", "season", "week"]).agg(
        team_blitzes=("def_times_blitzed", "sum"),
        team_hurries=("def_times_hurried", "sum"),
        team_sacks=("def_sacks", "sum"),
        team_pressures=("def_pressures", "sum"),
    ).reset_index()
    return team_agg
```

### QBR Columns (PROF-06)

```python
# Source: Bronze QBR parquet inspection (2023 season)
# QBR uses ESPN player IDs and team abbreviations

QBR_COLS = [
    "qbr_total",    # Total QBR (0-100 scale)
    "pts_added",    # Points added above replacement
    "qb_plays",     # Number of plays in sample
    "epa_total",    # Total EPA
]

# Team abbreviation normalization for QBR
QBR_TEAM_NORM = {"WSH": "WAS", "LAR": "LA"}
```

### NaN Coverage Logging

```python
# Log NaN coverage at write time per success criteria #4
def log_nan_coverage(df: pd.DataFrame, advanced_cols: list) -> None:
    """Log percentage of non-null values per advanced stat column."""
    for col in advanced_cols:
        if col in df.columns:
            non_null_pct = df[col].notna().mean() * 100
            logger.info("NaN coverage: %s = %.1f%% non-null", col, non_null_pct)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Season-level aggregates only | Weekly rolling windows (roll3, roll6) | Phase 15 (2026-03) | Captures recency and form trends |
| Raw team rankings | Opponent-adjusted EPA | Phase 16 (2026-03) | More accurate strength measurement |
| PBP-only player metrics | NGS/PFR/QBR integration | Phase 17 (current) | Position-specific advanced profiles |

**Data availability notes:**
- QBR Bronze data stops at 2023 (nfl-data-py limitation). Seasons 2024-2025 will have NaN QBR columns.
- NGS and PFR Bronze data covers through 2025.
- PFR weekly pass/def data available from 2018+; within PLAYER_DATA_SEASONS range (2020-2025).

## Open Questions

1. **STD (Season-to-Date) Expanding Average**
   - What we know: `apply_team_rolling()` includes STD via `expanding().mean()`
   - What's unclear: Whether STD adds value alongside roll3/roll6 for player profiles
   - Recommendation: **Include STD** -- it costs minimal computation and matches team_analytics pattern. Use `min_periods=3` on expanding too for consistency.

2. **PFR Blitz Rate Denominator**
   - What we know: PFR def data has `def_times_blitzed` per defender per game
   - What's unclear: What constitutes "blitz rate" -- blitzes/plays, blitzes/game, or % of defenders blitzing
   - Recommendation: Store raw `team_blitzes` count per game. Blitz rate normalization can be deferred since PROF-05 says "blitz rate per defensive team" which is most naturally total blitzes per game with rolling window.

3. **Mid-Season Team Changes**
   - What we know: Players can change teams mid-season (trades, releases)
   - What's unclear: Whether a player appears with different teams in the same season across sources
   - Recommendation: Join on name+team+season+week (not just name+season). This naturally handles mid-season trades since the team field changes per-week.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | tests/ directory (no pytest.ini; uses defaults) |
| Quick run command | `python -m pytest tests/test_player_advanced_analytics.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROF-01 | NGS WR/TE columns extracted with rolling | unit | `pytest tests/test_player_advanced_analytics.py::test_ngs_receiving_profile -x` | Wave 0 |
| PROF-02 | NGS QB columns extracted with rolling | unit | `pytest tests/test_player_advanced_analytics.py::test_ngs_passing_profile -x` | Wave 0 |
| PROF-03 | NGS RB columns extracted with rolling | unit | `pytest tests/test_player_advanced_analytics.py::test_ngs_rushing_profile -x` | Wave 0 |
| PROF-04 | PFR pressure rate with rolling | unit | `pytest tests/test_player_advanced_analytics.py::test_pfr_pressure_rate -x` | Wave 0 |
| PROF-05 | PFR team blitz rate with rolling | unit | `pytest tests/test_player_advanced_analytics.py::test_pfr_team_blitz_rate -x` | Wave 0 |
| PROF-06 | QBR rolling (QB-only) | unit | `pytest tests/test_player_advanced_analytics.py::test_qbr_rolling -x` | Wave 0 |
| SC-4 | Left-join preserves all players (no row drops) | unit | `pytest tests/test_player_advanced_analytics.py::test_left_join_no_drops -x` | Wave 0 |
| SC-5 | min_periods=3 on rolling | unit | `pytest tests/test_player_advanced_analytics.py::test_min_periods -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_player_advanced_analytics.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_player_advanced_analytics.py` -- covers PROF-01 through PROF-06 + success criteria
- [ ] Test fixtures: synthetic NGS/PFR/QBR DataFrames with known values for rolling verification

## Sources

### Primary (HIGH confidence)
- Bronze parquet files inspected directly -- NGS (receiving/passing/rushing), PFR (weekly pass/def), QBR schemas verified with actual 2023 data
- `src/team_analytics.py` -- `apply_team_rolling()` pattern verified
- `scripts/silver_team_transformation.py` -- CLI and local I/O pattern verified
- `src/config.py` -- SILVER_PLAYER_S3_KEYS registration pattern verified
- `src/nfl_data_adapter.py` -- fetch method signatures verified

### Secondary (MEDIUM confidence)
- Player ID match rates: NGS GSIS ID 100% overlap verified via set intersection. PFR ~80% estimated from CONTEXT.md (needs runtime validation).

### Tertiary (LOW confidence)
- QBR data for 2024-2025 seasons: Bronze only has through 2023. The adapter supports QBR fetch but data may not have been ingested for recent seasons.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing tools
- Architecture: HIGH -- direct reuse of team_analytics patterns adapted for player-level
- Pitfalls: HIGH -- verified all data schemas, ID formats, team abbreviation mismatches from actual Bronze files
- Data availability: MEDIUM -- QBR 2024-2025 gap confirmed; PFR match rate needs runtime validation

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable -- Bronze data schemas unlikely to change)
