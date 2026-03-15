# Phase 15: PBP Team Metrics and Tendencies - Research

**Researched:** 2026-03-13
**Domain:** PBP aggregation, team-level analytics, rolling windows (pandas)
**Confidence:** HIGH

## Summary

This phase transforms Bronze PBP play-level data into two Silver team-level Parquet outputs: performance metrics (EPA, success rate, CPOE, red zone) and tendencies (pace, PROE, 4th down aggressiveness, early-down run rate). The project already has a mature Silver player pipeline (`player_analytics.py` + `silver_player_transformation.py`) that establishes all patterns -- rolling windows, local-first storage, config registration, CLI structure. The new team module follows these patterns exactly, with the key difference being `groupby(['team', 'season'])` instead of `groupby('player_id')`.

Data inspection of the 2024 Bronze PBP file (49,492 plays, 103 columns) confirms all required columns are present: `epa`, `success`, `cpoe`, `xpass`, `play_type`, `posteam`, `defteam`, `yardline_100`, `drive`, `down`, `fourth_down_converted`, `fourth_down_failed`, `no_huddle`. The `xpass` column has only 0.4% nulls on pass+run plays, making PROE calculation straightforward. `cpoe` has 11.3% nulls on pass plays (expected -- it's undefined for non-completed pass situations). Playoff games (season_type='POST', weeks 19-22) must be filtered out.

**Primary recommendation:** Create a new `src/team_analytics.py` module with pure functions for each metric group, a new `scripts/silver_team_transformation.py` CLI that mirrors the player script's structure, and fix the existing `player_analytics.py` rolling window bug in-place.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Rolling windows are lagged: use `shift(1)` so week N's rolling value uses only prior weeks (no data leakage for prediction models)
- min_periods=1 for both roll3 and roll6 -- values start appearing at Week 2; Week 1 is always NaN
- Include season-to-date (STD) expanding average alongside roll3 and roll6
- Groupby must use (entity, season) not entity alone -- prevents cross-season contamination
- Fix existing bug in `player_analytics.py:compute_rolling_averages()` in-place: change `groupby('player_id')` to `groupby(['player_id', 'season'])`
- PROE: Use nflfastR's `xpass` column from Bronze PBP data: PROE = actual_pass_rate - mean(xpass)
- Include all non-special plays (play_type in ['pass', 'run'] -- exclude punts, kickoffs, spikes, kneels, penalties)
- Early-down run rate uses 1st and 2nd down (down <= 2)
- 4th down aggressiveness: Two columns -- go rate (% of 4th downs where team went for it vs punt/FG) and success rate (conversion rate when going for it)
- Both get rolling windows (roll3, roll6, std)
- Red zone = yardline_100 <= 20 (no separate goal-to-go tier)
- Four red zone metrics: TD rate, success rate, pass/rush split, EPA/play
- Both offense AND defense sides -- prefix columns with off_ and def_
- TD rate denominator is drive-based: TDs / unique drives entering the red zone (use PBP `drive` column)
- Two separate Parquet files per team-week:
  - `data/silver/teams/pbp_metrics/season=YYYY/` -- EPA/play, success rate, CPOE, red zone metrics
  - `data/silver/teams/tendencies/season=YYYY/` -- pace, PROE, 4th down aggressiveness, early-down run rate
- One row per (team, season, week) with offense and defense as column prefixes (off_, def_)
- Include both raw weekly values AND rolling columns (raw + _roll3 + _roll6 + _std per metric)
- Column naming convention: `metric_rollN` suffix (e.g., off_epa_per_play_roll3, pace_roll6) -- matches existing player_analytics.py convention
- Update `docs/NFL_DATA_DICTIONARY.md` with schemas for both new Silver team tables

### Claude's Discretion
- Exact play filtering logic for edge cases (e.g., two-point conversions, overtime)
- How to handle teams with zero red zone trips in a week (NaN vs 0)
- Pace calculation details (plays per game vs plays per 60 minutes)
- CPOE aggregation method (mean of play-level CPOE vs team-level calculation)

### Deferred Ideas (OUT OF SCOPE)
- Comprehensive Silver data dictionary update across all layers -- could be a standalone doc task after v1.2 completes
- Exponentially-weighted moving averages (EWM) as alternative to fixed windows -- tracked as EWM-01 in REQUIREMENTS.md for v1.3+
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PBP-01 | Team EPA per play (offense + defense, pass/rush splits) with 3-game and 6-game rolling windows | `epa` column present with 1.2% null; filter to play_type in ['pass','run']; group by posteam (offense) and defteam (defense) |
| PBP-02 | Team success rate (offense + defense) with rolling windows | `success` column present with 1.2% null; binary 0/1 indicator per play; mean aggregation |
| PBP-03 | Team CPOE aggregate (per QB and per team) with rolling windows | `cpoe` column 11.3% null on pass plays (expected); aggregate as mean of non-null play-level values |
| PBP-04 | Red zone efficiency (offense + defense) with rolling windows | `yardline_100` and `drive` columns present; use drive-based denominator for TD rate |
| PBP-05 | Fix existing rolling window bug -- groupby must use (entity, season) | Line 213 of player_analytics.py: `groupby('player_id')` needs `['player_id', 'season']` |
| TEND-01 | Pace (plays per game) per team with rolling windows | Count of pass+run plays per team-week; mean ~61.5 plays/team-week in 2024 data |
| TEND-02 | PROE per team with rolling windows | `xpass` present with 0.4% null on pass+run plays; PROE = actual_pass_rate - mean(xpass) |
| TEND-03 | 4th down aggressiveness (go rate, success rate) with rolling windows | `fourth_down_converted` and `fourth_down_failed` columns present; also need play_type filter for punt/FG |
| TEND-04 | Early-down run rate with rolling windows | Filter down<=2, compute rush_attempt/total_plays per team-week |
| INFRA-01 | New Silver tables registered in config.py | Add `SILVER_TEAM_S3_KEYS` dict following `SILVER_PLAYER_S3_KEYS` pattern |
| INFRA-02 | Silver team transformation CLI script | Mirror `silver_player_transformation.py` structure: argparse, local Bronze read, transform, local Silver write |
| INFRA-03 | Season/week partition convention with timestamped filenames | Follow existing `metric_YYYYMMDD_HHMMSS.parquet` naming pattern |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | (existing) | DataFrame aggregation, groupby, rolling windows | Already used throughout project |
| numpy | (existing) | NaN handling, conditional logic | Already used throughout project |
| pyarrow | (existing) | Parquet read/write | Already used throughout project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| argparse | stdlib | CLI argument parsing | CLI script |
| logging | stdlib | Structured logging | All modules |
| datetime | stdlib | Timestamp generation | File naming |

No new dependencies required. All work uses existing project libraries.

## Architecture Patterns

### Recommended Project Structure
```
src/
  team_analytics.py          # NEW: pure functions for team-level PBP metrics
  player_analytics.py        # MODIFIED: fix rolling window groupby bug (line 213)
  config.py                  # MODIFIED: add SILVER_TEAM_S3_KEYS dict

scripts/
  silver_team_transformation.py    # NEW: CLI mirroring silver_player_transformation.py
  silver_player_transformation.py  # EXISTING: unchanged

data/silver/teams/
  pbp_metrics/season=YYYY/        # NEW: EPA, success rate, CPOE, red zone
  tendencies/season=YYYY/          # NEW: pace, PROE, 4th down, early-down run rate

tests/
  test_team_analytics.py           # NEW: unit tests for team_analytics.py

docs/
  NFL_DATA_DICTIONARY.md           # MODIFIED: add Silver team table schemas
```

### Pattern 1: Play Filtering (Foundation for All Metrics)
**What:** Filter PBP data to valid plays before any aggregation.
**When to use:** Every metric computation function must start with this filter.
**Example:**
```python
def _filter_valid_plays(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Filter to pass and run plays only, exclude special teams and garbage plays."""
    df = pbp_df.copy()
    # Regular season only (exclude POST)
    df = df[df['season_type'] == 'REG']
    # Limit to weeks 1-18
    df = df[df['week'] <= 18]
    # Valid play types only
    df = df[df['play_type'].isin(['pass', 'run'])]
    # Exclude two-point conversions (no EPA value)
    # Two-point conversions have down=NaN and yardline_100 <= 2 after a TD
    # They're already excluded by nflfastR's EPA model (epa is NaN for these)
    return df
```

### Pattern 2: Offense/Defense Dual Aggregation
**What:** Compute same metric from both team's perspective (posteam = offense, defteam = defense).
**When to use:** EPA, success rate, red zone metrics.
**Example:**
```python
def compute_team_epa(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute EPA per play for each team-week, offense and defense."""
    # Offense: group by possessing team
    off = (valid_plays.groupby(['posteam', 'season', 'week'])
           .agg(off_epa_per_play=('epa', 'mean'),
                off_pass_epa=('epa', lambda x: x[valid_plays.loc[x.index, 'play_type'] == 'pass'].mean()),
                off_rush_epa=('epa', lambda x: x[valid_plays.loc[x.index, 'play_type'] == 'run'].mean()))
           .reset_index()
           .rename(columns={'posteam': 'team'}))

    # Defense: group by defending team
    def_agg = (valid_plays.groupby(['defteam', 'season', 'week'])
               .agg(def_epa_per_play=('epa', 'mean'))
               .reset_index()
               .rename(columns={'defteam': 'team'}))

    return off.merge(def_agg, on=['team', 'season', 'week'], how='outer')
```

### Pattern 3: Rolling Window Application (Reuse Existing Pattern)
**What:** Apply shift(1) + rolling + groupby to team metrics, matching player_analytics.py convention.
**When to use:** After computing raw weekly metrics, before output.
**Example:**
```python
def apply_team_rolling(df: pd.DataFrame, stat_cols: list, windows: list = [3, 6]) -> pd.DataFrame:
    """Apply rolling averages to team-level metrics. Groups by (team, season)."""
    df = df.sort_values(['team', 'season', 'week'])

    for window in windows:
        roll_cols = {}
        for col in stat_cols:
            roll_cols[f"{col}_roll{window}"] = (
                df.groupby(['team', 'season'])[col]
                .transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
            )
        df = df.assign(**roll_cols)

    # Season-to-date
    for col in stat_cols:
        df[f"{col}_std"] = (
            df.groupby(['team', 'season'])[col]
            .transform(lambda s: s.shift(1).expanding().mean())
        )

    return df
```

### Pattern 4: Config Registration
**What:** Register new Silver output paths in config.py.
**When to use:** When adding new Silver output datasets.
**Example:**
```python
SILVER_TEAM_S3_KEYS = {
    "pbp_metrics": "teams/pbp_metrics/season={season}/pbp_metrics_{ts}.parquet",
    "tendencies": "teams/tendencies/season={season}/tendencies_{ts}.parquet",
}
```

### Anti-Patterns to Avoid
- **Cross-season rolling contamination:** Never use `groupby('team')` without also grouping by season. The existing player bug (PBP-05) demonstrates this exact problem.
- **Including playoff weeks:** Always filter `week <= 18` or `season_type == 'REG'` before aggregation.
- **Using `no_play` play_type:** Penalty plays show up as `no_play` -- these should be excluded entirely. The `play_type in ['pass', 'run']` filter handles this.
- **Aggregating EPA with nulls:** EPA is NaN for ~1.2% of plays (kickoffs, etc.). After filtering to pass+run, remaining NaN EPAs should be dropped (not filled with 0).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Expected pass probability | Custom logistic regression | nflfastR's `xpass` column in PBP data | Already calibrated by Ben Baldwin's model; 0.4% null on pass+run plays |
| EPA calculation | Custom expected points model | nflfastR's `epa` column in PBP data | Industry-standard model; recalculating would diverge from nflverse ecosystem |
| CPOE | Custom completion probability model | nflfastR's `cpoe` column in PBP data | Pre-computed per play; just aggregate with mean |
| Success rate | Custom success definition | nflfastR's `success` column (binary 0/1) | Standard definition: 1st down 45%+, 2nd down 60%+, 3rd/4th 100% of yards to go |

**Key insight:** All four core metrics (EPA, CPOE, xpass, success) are pre-computed per play in the nflfastR PBP data. This phase is purely an aggregation and windowing exercise -- no modeling required.

## Common Pitfalls

### Pitfall 1: CPOE Null Rate on Pass Plays
**What goes wrong:** CPOE is NaN on ~11.3% of pass plays (sacks, throwaways, spikes within pass_type='pass').
**Why it happens:** CPOE is only defined for actual pass attempts that reach a target.
**How to avoid:** Use `df['cpoe'].dropna()` or filter to `complete_pass == 1 | incomplete_pass == 1` before aggregating. Do NOT fill NaN with 0 -- that would bias CPOE downward.
**Warning signs:** Team CPOE values that are systematically lower than expected.

### Pitfall 2: Red Zone TD Rate Denominator
**What goes wrong:** Using play count as denominator inflates trips and deflates TD rate.
**Why it happens:** A single red zone trip may have 4-8 plays; counting plays makes TD rate ~5% instead of ~55%.
**How to avoid:** Use `drive` column to count unique drives that enter the red zone (yardline_100 <= 20). TD rate = TDs / unique_red_zone_drives.
**Warning signs:** TD rates below 20% suggest play-level denominator; rates near 55% are correct (NFL average).

### Pitfall 3: 4th Down Go Rate Play Classification
**What goes wrong:** Counting all 4th down plays as "decisions" includes 4th-and-very-long punting situations that aren't real go/no-go decisions.
**Why it happens:** Play-type data includes punts and field goals on 4th down.
**How to avoid:** Count 4th down plays where `play_type in ['pass', 'run']` as "go for it" decisions. Count `play_type in ['punt', 'field_goal']` as "didn't go for it". Exclude `no_play` (penalties).
**Warning signs:** Go rates below 10% are suspicious (NFL average is ~15-20% across all 4th downs).

### Pitfall 4: Pace Calculation Edge Case
**What goes wrong:** Overtime plays inflate play count for some team-weeks.
**Why it happens:** OT adds 10-15 extra plays per team.
**How to avoid:** For pace (plays per game), include all plays including overtime -- this is the standard convention (NFL pace metrics count total plays). The user left this to Claude's discretion. Using total plays per game (including OT) is simpler and matches how pace is commonly reported.
**Warning signs:** Team-weeks with 80+ plays likely include OT.

### Pitfall 5: PROE Aggregation Level
**What goes wrong:** Computing PROE per play then averaging gives different result than computing at game level.
**Why it happens:** xpass varies per play based on situation; aggregation order matters.
**How to avoid:** For PROE: compute per game as `(pass_plays / total_plays) - mean(xpass)`. This is the standard approach -- the actual pass rate is a game-level ratio, and xpass is averaged across all plays in that game.
**Warning signs:** PROE values outside -0.15 to +0.15 range are unusual.

## Code Examples

### Reading Bronze PBP Data (Established Pattern)
```python
def _read_local_pbp(season: int) -> pd.DataFrame:
    """Read the latest PBP parquet file from local Bronze directory."""
    pattern = os.path.join(BRONZE_DIR, 'pbp', f'season={season}', '*.parquet')
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])
```

### Red Zone Metrics (Drive-Based TD Rate)
```python
def compute_red_zone_metrics(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Red zone efficiency: TD rate, success rate, pass/rush split, EPA/play."""
    rz = valid_plays[valid_plays['yardline_100'] <= 20].copy()

    # Offense red zone
    off_rz = rz.groupby(['posteam', 'season', 'week']).agg(
        off_rz_epa=('epa', 'mean'),
        off_rz_success_rate=('success', 'mean'),
        off_rz_pass_rate=('pass_attempt', 'mean'),
        off_rz_tds=('touchdown', 'sum'),
    ).reset_index().rename(columns={'posteam': 'team'})

    # Drive-based TD rate: count unique drives in red zone
    rz_drives = (rz.groupby(['posteam', 'season', 'week'])['drive']
                 .nunique().reset_index()
                 .rename(columns={'posteam': 'team', 'drive': 'off_rz_drives'}))

    off_rz = off_rz.merge(rz_drives, on=['team', 'season', 'week'], how='left')
    off_rz['off_rz_td_rate'] = off_rz['off_rz_tds'] / off_rz['off_rz_drives']

    return off_rz
```

### PROE Calculation
```python
def compute_proe(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Pass Rate Over Expected per team-week."""
    game_agg = valid_plays.groupby(['posteam', 'season', 'week']).agg(
        total_plays=('play_type', 'count'),
        pass_plays=('pass_attempt', 'sum'),
        mean_xpass=('xpass', 'mean'),
    ).reset_index().rename(columns={'posteam': 'team'})

    game_agg['actual_pass_rate'] = game_agg['pass_plays'] / game_agg['total_plays']
    game_agg['proe'] = game_agg['actual_pass_rate'] - game_agg['mean_xpass']

    return game_agg[['team', 'season', 'week', 'proe']]
```

### Fixing the Existing Rolling Window Bug (PBP-05)
```python
# player_analytics.py line 213, CURRENT (buggy):
df.groupby('player_id')[col]
    .transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())

# FIXED:
df.groupby(['player_id', 'season'])[col]
    .transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
```

### Discretion Decisions (Recommended)

**Two-point conversions:** Exclude by relying on the `play_type in ['pass', 'run']` filter plus `epa` being NaN. Two-point conversion plays have `two_point_attempt == 1` if that column exists, but the EPA NaN filter already handles them.

**Zero red zone trips:** Use NaN (not 0). A team with zero red zone trips in a week has undefined efficiency, not zero efficiency. NaN propagates correctly through rolling windows with min_periods=1.

**Pace:** Use total plays per game (count of pass+run plays per team-week). This is simple, standard, and includes overtime. No per-60-minutes normalization needed -- the raw count is the convention.

**CPOE aggregation:** Use mean of play-level CPOE values (dropping NaN). This is the standard approach and matches how CPOE is reported by nflfastR documentation. Do not attempt to recompute from completion probability.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FO DVOA | EPA/play (nflfastR) | ~2019-2020 | EPA is open-source, play-level, widely adopted |
| Custom xpass models | nflfastR's `xpass` column | Pre-computed in PBP data | No modeling needed; just aggregate |
| Season-long averages | Rolling windows (3/6 game) | Standard practice | Better recency weighting for in-season predictions |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | None (pytest runs from project root with `python -m pytest tests/ -v`) |
| Quick run command | `python -m pytest tests/test_team_analytics.py -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PBP-01 | EPA per play offense/defense with rolling | unit | `python -m pytest tests/test_team_analytics.py::TestEPA -v` | Wave 0 |
| PBP-02 | Success rate offense/defense with rolling | unit | `python -m pytest tests/test_team_analytics.py::TestSuccessRate -v` | Wave 0 |
| PBP-03 | CPOE aggregate with rolling | unit | `python -m pytest tests/test_team_analytics.py::TestCPOE -v` | Wave 0 |
| PBP-04 | Red zone efficiency with drive-based denominator | unit | `python -m pytest tests/test_team_analytics.py::TestRedZone -v` | Wave 0 |
| PBP-05 | Rolling window season groupby fix | unit | `python -m pytest tests/test_player_analytics.py::TestRollingSeasonFix -v` | Wave 0 |
| TEND-01 | Pace (plays per game) with rolling | unit | `python -m pytest tests/test_team_analytics.py::TestPace -v` | Wave 0 |
| TEND-02 | PROE with rolling | unit | `python -m pytest tests/test_team_analytics.py::TestPROE -v` | Wave 0 |
| TEND-03 | 4th down aggressiveness with rolling | unit | `python -m pytest tests/test_team_analytics.py::TestFourthDown -v` | Wave 0 |
| TEND-04 | Early-down run rate with rolling | unit | `python -m pytest tests/test_team_analytics.py::TestEarlyDownRunRate -v` | Wave 0 |
| INFRA-01 | Config registration | unit | `python -m pytest tests/test_team_analytics.py::TestConfig -v` | Wave 0 |
| INFRA-02 | CLI script runs | smoke | `python scripts/silver_team_transformation.py --help` | Wave 0 |
| INFRA-03 | Output file naming and partitioning | unit | `python -m pytest tests/test_team_analytics.py::TestOutput -v` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_team_analytics.py -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_team_analytics.py` -- covers PBP-01 through TEND-04, INFRA-01, INFRA-03
- [ ] Add cross-season rolling test to `tests/test_player_analytics.py` for PBP-05 fix validation

## Open Questions

1. **Overtime plays in pace metric**
   - What we know: OT adds 10-15 plays for some team-weeks. Including OT is simpler and standard.
   - What's unclear: Whether downstream projection models should normalize for OT.
   - Recommendation: Include OT plays in pace. If needed later, add an `is_overtime` flag column.

2. **Teams with bye weeks**
   - What we know: Bye weeks produce no PBP data -- the team simply won't appear for that week.
   - What's unclear: Whether to insert explicit NaN rows for bye weeks.
   - Recommendation: Don't insert bye week rows. Rolling windows handle missing weeks naturally (the prior non-bye-week values carry forward).

## Sources

### Primary (HIGH confidence)
- Local Bronze PBP data inspection: `data/bronze/pbp/season=2024/` -- 49,492 plays, 103 columns, all required columns verified present
- Existing codebase: `src/player_analytics.py`, `src/config.py`, `scripts/silver_player_transformation.py` -- established patterns
- `config.py:PBP_COLUMNS` -- all 103 curated PBP columns documented

### Secondary (MEDIUM confidence)
- nflfastR documentation for EPA, CPOE, xpass, success definitions -- well-established in NFL analytics community
- NFL red zone TD rate conventions (drive-based denominator) -- standard practice

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries; all pandas/numpy operations on existing Bronze schema
- Architecture: HIGH - mirrors existing player Silver pipeline exactly; all patterns established
- Pitfalls: HIGH - verified against actual PBP data (null rates, column values, play type distributions)
- Data availability: HIGH - confirmed all 10 seasons (2016-2025) present in Bronze PBP

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (stable -- no external API dependencies; pure aggregation of existing data)
