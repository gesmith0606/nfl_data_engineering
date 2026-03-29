# Phase 39: Player Feature Vector Assembly - Research

**Researched:** 2026-03-29
**Domain:** Player-week feature engineering from Silver sources (pandas, parquet, temporal lag enforcement)
**Confidence:** HIGH

## Summary

Phase 39 assembles a per-player-per-week feature matrix by joining 9 Silver data sources into a unified DataFrame with enforced temporal integrity. The existing codebase already provides all the building blocks: Silver player sources with pre-computed rolling averages (shift(1) lag baked in), team-level context tables, opponent defensive rankings, and a proven multi-source left-join pattern in `feature_engineering.py`.

The primary technical challenges are: (1) correctly mapping join keys across sources that use different column names (`player_id` vs `player_gsis_id` vs `gsis_id`), (2) deriving Vegas implied team totals from Bronze schedules for seasons 2020-2024 where market_data Silver is available, and (3) building a leakage detection validator that catches any feature with suspiciously high correlation to the target. The existing Silver data covers 2020-2024 with 5,597 player-weeks per season, all required columns present and 0% null on Vegas lines.

**Primary recommendation:** Create a new `src/player_feature_engineering.py` module that adapts the `_assemble_team_features()` left-join pattern from `feature_engineering.py` for player-level rows, with a `validate_temporal_integrity()` function that checks shift(1) compliance and a `detect_leakage()` function that flags r > 0.90 correlations.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Include skill position players (QB, RB, WR, TE) with snap_pct >= 20% in any of their prior 3 games
- **D-02:** Eligibility uses Silver usage `snap_pct_roll3` (already computed with shift(1) lag)
- **D-03:** ~60% of player-weeks pass this filter, removing noise from special-teamers, garbage-time snaps, and practice squad callups
- **D-04:** Include raw stat target columns per position for Phase 40 model training:
  - QB: passing_yards, passing_tds, interceptions, rushing_yards, rushing_tds (5 stats)
  - RB: rushing_yards, rushing_tds, carries, receptions, receiving_yards, receiving_tds (6 stats)
  - WR: targets, receptions, receiving_yards, receiving_tds (4 stats)
  - TE: targets, receptions, receiving_yards, receiving_tds (4 stats)
- **D-05:** Fantasy points derived downstream via `scoring_calculator.py` -- not a model target
- **D-06:** Target columns are actual same-week stats (not lagged) -- these are labels, not features
- **D-07:** Rookies: rolling features are NaN (XGBoost/LGB/CB handle NaN natively). Add draft_round, draft_pick, draft_value, speed_score, burst_score from Silver historical table as cold-start features
- **D-08:** Traded players: `recent_team` in weekly data already reflects current team; matchup/team-quality features join on current team naturally
- **D-09:** Bye weeks: excluded from training data (known zeros, not predictions). Rolling features naturally skip bye gap via shift(1)

### Claude's Discretion
- Module structure: new `player_feature_engineering.py` vs extending existing `feature_engineering.py`
- Exact column naming convention for the player feature vector
- Deduplication strategy for overlapping columns across Silver sources
- Leakage validator implementation details
- Output partitioning scheme (by season, by season+week, etc.)

### Deferred Ideas (OUT OF SCOPE)
- Opportunity-efficiency decomposition (two-stage prediction) -- Phase 41
- TD regression from red zone features -- Phase 41
- Role momentum features (snap share trajectory) -- Phase 41
- Ensemble stacking per position -- Phase 41
- Team-total constraint enforcement -- Phase 42
- Preseason mode (prior-season aggregates) -- Phase 42
- MAPIE confidence intervals -- Phase 42
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FEAT-01 | Player-level feature vector assembled from 9 Silver sources into per-player-per-week rows with proper temporal lags | Silver sources verified: usage (113 cols), advanced (119 cols), historical (63 cols), defense/positional (6 cols), player_quality (28 cols), game_context (22 cols), market_data (20 cols), pbp_metrics (63 cols), tendencies (23 cols). All have `[team, season, week]` or `[player_id, season, week]` join keys. Rolling features already use shift(1). |
| FEAT-02 | All player features use shift(1) to prevent same-game stat leakage | Silver rolling columns (45 in usage, many in advanced) already apply shift(1) in `compute_rolling_averages()`. Team-level rolling features also pre-shifted. Validator needed to confirm no raw same-week stats slip through as features. |
| FEAT-03 | Matchup features include opponent defense vs position rank and EPA allowed, lagged to week N-1 | `defense/positional` Silver has `avg_pts_allowed` and `rank` per `[team, position, week]`. **Gap found**: no EPA-allowed column exists -- only fantasy points allowed and rank. Must either derive EPA from team `def_epa_per_play` in pbp_metrics (position-agnostic) or compute from Bronze PBP per opponent-position. Recommendation: use `def_epa_per_play` from pbp_metrics as a team-level proxy and `rank` from defense/positional as the position-specific signal. |
| FEAT-04 | Vegas implied team totals derived from spread/total lines included as features | Bronze schedules have `spread_line` and `total_line` with 0% nulls for 2020-2024. Silver `market_data` has `opening_spread` and `opening_total` also at 0% nulls. Formula: `implied_total = (total_line / 2) - (spread_line / 2)`, clipped [5.0, 45.0]. Already implemented in `player_analytics.compute_implied_team_totals()`. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | (project version) | DataFrame assembly, joins, rolling computations | Already used throughout codebase |
| numpy | (project version) | Division guards, NaN handling, correlation computation | Already used throughout codebase |
| pyarrow | (project version) | Parquet read/write | Already used throughout codebase |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| logging | stdlib | Progress reporting during multi-source join | Every function |

No new dependencies needed. All required libraries are already in the project.

## Architecture Patterns

### Recommended Project Structure
```
src/
    player_feature_engineering.py  # NEW: player-week feature assembly
    feature_engineering.py         # EXISTING: game-level feature assembly (unchanged)
    config.py                      # MODIFY: add SILVER_PLAYER_LOCAL_DIRS, PLAYER_LABEL_COLUMNS
scripts/
    assemble_player_features.py    # NEW: CLI to generate player feature vectors
tests/
    test_player_feature_engineering.py  # NEW: validation tests
data/
    gold/
        player_features/           # NEW: output location
            season=2024/
                player_features_20260329_120000.parquet
```

### Pattern 1: Multi-Source Left Join (adapted from feature_engineering.py)
**What:** Start with a base table (players/usage, which has player_id + opponent_team + position), then left-join each additional source on the appropriate key.
**When to use:** Always -- this is the core assembly pattern.
**Example:**
```python
# Source: feature_engineering.py _assemble_team_features() pattern
def assemble_player_features(season: int) -> pd.DataFrame:
    """Assemble player-week feature vector from Silver sources."""
    # Base: usage (has player_id, recent_team, opponent_team, position, week)
    base = _read_latest_local("players/usage", season)
    if base.empty:
        return pd.DataFrame()

    # Join advanced on player GSIS ID
    advanced = _read_latest_local("players/advanced", season)
    if not advanced.empty:
        base = base.merge(
            advanced,
            left_on=["player_id", "season", "week"],
            right_on=["player_gsis_id", "season", "week"],
            how="left",
            suffixes=("", "__adv"),
        )
        # Drop duplicate columns
        dup_cols = [c for c in base.columns if c.endswith("__adv")]
        base = base.drop(columns=dup_cols)

    # Join team sources on [recent_team, season, week]
    for name, subdir in SILVER_TEAM_SOURCES.items():
        df = _read_latest_local(subdir, season)
        if df.empty:
            continue
        base = base.merge(
            df, left_on=["recent_team", "season", "week"],
            right_on=["team", "season", "week"],
            how="left", suffixes=("", f"__{name}"),
        )
        dup_cols = [c for c in base.columns if c.endswith(f"__{name}")]
        base = base.drop(columns=dup_cols)

    # Join opponent defense on [opponent_team, season, week, position]
    defense = _read_latest_local("defense/positional", season)
    if not defense.empty:
        # Shift defense rankings by 1 week (use prior week's ranking)
        defense = defense.sort_values(["team", "position", "season", "week"])
        defense[["avg_pts_allowed", "rank"]] = (
            defense.groupby(["team", "position", "season"])[["avg_pts_allowed", "rank"]]
            .shift(1)
        )
        base = base.merge(
            defense.rename(columns={"avg_pts_allowed": "opp_avg_pts_allowed", "rank": "opp_rank"}),
            left_on=["opponent_team", "season", "week", "position"],
            right_on=["team", "season", "week", "position"],
            how="left",
        )
    return base
```

### Pattern 2: Leakage Detection via Correlation
**What:** After assembly, compute Pearson correlation between every feature column and each target column. Flag any feature with |r| > 0.90.
**When to use:** Every time the feature vector is assembled or modified.
**Example:**
```python
def detect_leakage(
    df: pd.DataFrame,
    feature_cols: list,
    target_cols: list,
    threshold: float = 0.90,
) -> list:
    """Flag features with suspiciously high correlation to targets."""
    warnings = []
    for target in target_cols:
        if target not in df.columns:
            continue
        for feat in feature_cols:
            if feat not in df.columns:
                continue
            r = df[[feat, target]].dropna().corr().iloc[0, 1]
            if abs(r) > threshold:
                warnings.append((feat, target, r))
    return warnings
```

### Pattern 3: Temporal Integrity Validation
**What:** Verify that all rolling feature columns are properly lagged (week N features do not contain week N stats).
**When to use:** As a test assertion and as a runtime validator.
**Example:**
```python
def validate_temporal_integrity(df: pd.DataFrame) -> list:
    """Check that rolling features do not correlate with same-week raw stats."""
    violations = []
    # For each raw stat column, check correlation with its _roll3 counterpart
    raw_stats = ["passing_yards", "rushing_yards", "receiving_yards", "targets", "carries"]
    for stat in raw_stats:
        roll_col = f"{stat}_roll3"
        if stat in df.columns and roll_col in df.columns:
            # If shift(1) is correct, correlation should be moderate (0.3-0.7)
            # If shift(1) is missing, correlation will be > 0.90
            r = df[[stat, roll_col]].dropna().corr().iloc[0, 1]
            if abs(r) > 0.90:
                violations.append((stat, roll_col, r))
    return violations
```

### Pattern 4: Implied Team Total Derivation
**What:** Compute Vegas implied team totals from spread and total lines as player-level features.
**When to use:** For FEAT-04, deriving from Bronze schedules or Silver market_data.
**Example:**
```python
# Source: player_analytics.py compute_implied_team_totals() formula
def _add_implied_totals(df: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    """Add Vegas implied team total to each player-week row."""
    sched = schedules[["season", "week", "home_team", "away_team", "spread_line", "total_line"]].copy()
    sched["implied_home"] = ((sched["total_line"] / 2) - (sched["spread_line"] / 2)).clip(5.0, 45.0)
    sched["implied_away"] = ((sched["total_line"] / 2) + (sched["spread_line"] / 2)).clip(5.0, 45.0)

    # Reshape to per-team
    home = sched[["season", "week", "home_team", "implied_home"]].rename(
        columns={"home_team": "team", "implied_home": "implied_team_total"}
    )
    away = sched[["season", "week", "away_team", "implied_away"]].rename(
        columns={"away_team": "team", "implied_away": "implied_team_total"}
    )
    team_totals = pd.concat([home, away], ignore_index=True)

    df = df.merge(team_totals, left_on=["recent_team", "season", "week"],
                  right_on=["team", "season", "week"], how="left")
    return df
```

### Anti-Patterns to Avoid
- **Using raw same-week stats as features:** Only `_roll3`, `_roll6`, `_std` columns are valid features. Raw `targets`, `carries`, `passing_yards` from the same week are labels (D-06).
- **One-hot encoding player_id:** The model should learn cross-player patterns, not memorize individual players. Use draft capital/combine features instead.
- **Modifying feature_engineering.py:** Game-level and player-level feature assembly serve different purposes. Keep them in separate modules.
- **Joining historical profiles on `player_id`:** Historical uses `gsis_id`, usage uses `player_id`. They are the same format (`00-XXXXXXX`) but different column names -- must rename before join.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rolling averages with shift(1) | Custom lag logic | Silver usage/advanced pre-computed `_roll3`, `_roll6`, `_std` columns | Already battle-tested in `player_analytics.compute_rolling_averages()` with correct shift(1) |
| Implied team totals formula | Custom formula | `player_analytics.compute_implied_team_totals()` pattern | Already clipped [5.0, 45.0], handles missing lines |
| Local Parquet reading | Custom glob logic | `_read_latest_local()` from `feature_engineering.py` | Sorted glob pattern already proven |
| Fantasy point scoring | Custom calculation | `scoring_calculator.py` | Handles all 3 formats, already tested |

**Key insight:** Nearly all feature computation is already done in the Silver layer. This phase is primarily a JOIN operation across pre-computed sources, not a computation phase.

## Common Pitfalls

### Pitfall 1: Player ID Column Name Mismatch
**What goes wrong:** Joining usage (`player_id`) with advanced (`player_gsis_id`) and historical (`gsis_id`) fails silently with all-NaN results because the column names differ even though the ID format is identical.
**Why it happens:** Different Silver sources adopted different column names from their upstream Bronze data.
**How to avoid:** Explicitly rename join keys: `advanced.rename(columns={"player_gsis_id": "player_id"})` before merge. Verify with `assert merged["some_advanced_col"].notna().sum() > 0`.
**Warning signs:** If any joined source produces 100% NaN in its columns after merge, the join key was wrong.

### Pitfall 2: Defense/Positional Rankings Not Lagged
**What goes wrong:** The `defense/positional` Silver table contains same-week rankings (how the defense performed this week), not prior-week rankings. Using them directly as features leaks the current game's outcome.
**Why it happens:** `compute_opponent_rankings()` computes rankings for each week based on that week's games. There is no automatic shift(1) applied.
**How to avoid:** Apply `shift(1)` grouped by `[team, position, season]` to both `avg_pts_allowed` and `rank` columns BEFORE joining to the player base table.
**Warning signs:** If `opp_rank` has r > 0.50 with any target stat, it is likely not lagged. After proper lag, correlation should be 0.15-0.30.

### Pitfall 3: Team Source Duplicate Columns
**What goes wrong:** Multiple team sources share column names (e.g., `game_id`, `game_type`, `is_home`, `opponent`). Merging without suffix handling produces `game_id_x`, `game_id_y` proliferation.
**Why it happens:** Team sources were designed for independent use, not joint assembly.
**How to avoid:** Use the suffix dedup pattern from `_assemble_team_features()`: merge with `suffixes=("", f"__{name}")`, then drop all columns ending with `f"__{name}"`.
**Warning signs:** Column count exploding beyond ~200, or columns with `_x`/`_y` suffixes appearing.

### Pitfall 4: Market Data Only Available for 2016-2021 (FinnedAI Range)
**What goes wrong:** Assuming Silver `market_data` covers all training seasons. FinnedAI odds data covers 2016-2021 only. For 2022-2024, market_data columns will be NaN.
**Why it happens:** The market_data Silver was built from FinnedAI Bronze odds which only covers that range.
**How to avoid:** For implied team totals (FEAT-04), derive from Bronze schedules `spread_line` and `total_line` which are available for ALL seasons (from nfl-data-py, not FinnedAI). Only use Silver `market_data` for supplementary line movement features (opening_spread, opening_total), accepting NaN for 2022+. **UPDATE: Verified that Silver market_data has 0% nulls for 2024, meaning schedules-based lines were used as fallback. Safe to use.**
**Warning signs:** Unexpectedly high null rates in market features.

### Pitfall 5: Historical Profiles are Static (No Week Dimension)
**What goes wrong:** Trying to join `players/historical` on `[gsis_id, season, week]` fails because historical has no `week` column -- it is a dimension table with one row per player.
**Why it happens:** Combine measurables and draft capital do not change week-to-week.
**How to avoid:** Join on `[gsis_id]` only (after renaming), and the static features will broadcast to all weeks for that player.
**Warning signs:** Empty merge result or massive row count explosion.

## Code Examples

### Reading Silver Sources (verified pattern)
```python
# Source: feature_engineering.py _read_latest_local()
import glob, os
import pandas as pd

SILVER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "silver")

def _read_latest_local(subdir: str, season: int) -> pd.DataFrame:
    pattern = os.path.join(SILVER_DIR, subdir, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])
```

### Player Eligibility Filter (D-01, D-02)
```python
def _filter_eligible_players(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only skill position players with snap_pct >= 20% in recent 3 games."""
    # Filter to QB/RB/WR/TE
    df = df[df["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    # snap_pct_roll3 already uses shift(1) from Silver -- it is the prior-3-game average
    df = df[df["snap_pct_roll3"] >= 0.20].copy()
    return df
```

### Feature Column Identification
```python
# Identifier and label columns to exclude from features
_PLAYER_IDENTIFIER_COLS = {
    "player_id", "player_gsis_id", "gsis_id", "player_name", "player_display_name",
    "headshot_url", "season", "week", "season_type", "game_id",
    "recent_team", "opponent_team", "position", "position_group",
    "team", "opponent", "game_type",
}

# Target labels (same-week actuals, not features)
_PLAYER_LABEL_COLS = {
    "passing_yards", "passing_tds", "interceptions",
    "rushing_yards", "rushing_tds", "carries",
    "targets", "receptions", "receiving_yards", "receiving_tds",
    "fantasy_points_ppr",
}

def get_player_feature_columns(df: pd.DataFrame) -> list:
    """Return valid feature columns (numeric, non-identifier, non-label)."""
    exclude = _PLAYER_IDENTIFIER_COLS | _PLAYER_LABEL_COLS
    return sorted([
        c for c in df.columns
        if c not in exclude
        and df[c].dtype in ("float64", "int64", "float32", "int32", "bool")
    ])
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Heuristic projections only | ML feature vector + heuristic fallback | v3.0 (this phase) | Enables position-specific ML models in Phase 40 |
| Game-level features only | Game + player features in parallel | v3.0 (this phase) | Player-week granularity for fantasy predictions |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already configured) |
| Config file | None (default discovery) |
| Quick run command | `python -m pytest tests/test_player_feature_engineering.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FEAT-01 | 9 Silver sources joined into player-week rows | integration | `python -m pytest tests/test_player_feature_engineering.py::test_assemble_joins_all_sources -x` | Wave 0 |
| FEAT-02 | All features use shift(1), no same-game leakage | unit | `python -m pytest tests/test_player_feature_engineering.py::test_temporal_integrity -x` | Wave 0 |
| FEAT-03 | Opponent defense-vs-position rank and EPA, lagged to N-1 | unit | `python -m pytest tests/test_player_feature_engineering.py::test_matchup_features_lagged -x` | Wave 0 |
| FEAT-04 | Vegas implied team totals as features | unit | `python -m pytest tests/test_player_feature_engineering.py::test_implied_team_totals -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_player_feature_engineering.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_player_feature_engineering.py` -- covers FEAT-01 through FEAT-04
- [ ] Framework install: None needed -- pytest already in project

## Open Questions

1. **Defense EPA per position not in Silver**
   - What we know: `defense/positional` has `avg_pts_allowed` and `rank` but no EPA column. FEAT-03 requires "EPA allowed." Team-level `def_epa_per_play` exists in `pbp_metrics` but is not position-specific.
   - What's unclear: Whether position-specific defensive EPA needs to be computed from Bronze PBP or if team-level `def_epa_per_play` is an acceptable proxy.
   - Recommendation: Use `def_epa_per_play` from Silver `teams/pbp_metrics` as a team-level proxy (lagged) alongside position-specific `opp_rank` from `defense/positional`. This satisfies the spirit of FEAT-03 without requiring a new Silver transformation. The model can learn the interaction between position-specific rank and team-level EPA.

2. **Column count estimate**
   - What we know: Usage (113) + Advanced (119) + Historical (63) + Defense (6) + Player Quality (28) + Game Context (22) + Market Data (20) + PBP Metrics (63) + Tendencies (23) = 457 raw columns. After dedup of shared keys and non-numeric identifiers, ~200 unique feature columns expected.
   - What's unclear: Exact count after deduplication -- depends on how many columns overlap.
   - Recommendation: Assemble first, count after, then document actual count in SUMMARY.md.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `src/feature_engineering.py`, `src/player_analytics.py`, `src/config.py`
- Silver Parquet schema inspection: `data/silver/players/usage/` (113 cols verified), `data/silver/players/advanced/` (119 cols verified), `data/silver/players/historical/` (63 cols, `gsis_id` join key verified), `data/silver/defense/positional/` (6 cols, no EPA column verified), `data/silver/teams/market_data/` (20 cols, 0% null on opening_spread/total)
- Bronze schedules: `spread_line` and `total_line` 0% null for 2020-2024
- `.planning/research/ARCHITECTURE.md` -- player feature vector design, join keys, ~160-col estimate
- `.planning/research/PITFALLS.md` -- same-game leakage risks, shift(1) enforcement

### Secondary (MEDIUM confidence)
- Player ID format consistency verified: `player_id` (usage) = `player_gsis_id` (advanced) = `gsis_id` (historical) all use `00-XXXXXXX` format
- Market data availability: Silver market_data shows 0% nulls for 2024, confirming schedules-based fallback works

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all existing libraries
- Architecture: HIGH - direct adaptation of proven `feature_engineering.py` pattern, all source schemas verified
- Pitfalls: HIGH - based on direct codebase inspection and column-level verification of join keys and null rates

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable -- Silver schemas unlikely to change)
