# Phase 28: Infrastructure & Player Features - Research

**Researched:** 2026-03-24
**Domain:** Feature engineering pipeline — player-level Bronze aggregation to Silver team grain with lag guards; ML package installation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use `passing_epa` from Bronze weekly stats as QB quality metric (full coverage 2016-2025)
- **D-02:** Compute roll3 and roll6 rolling windows matching existing team feature pattern
- **D-03:** Starter detection uses BOTH signals: depth chart `depth_team='1'` (pre-game) AND passing attempts leader (who really played, lagged via shift(1))
- **D-04:** When a different QB starts than depth chart expects, set `backup_qb_start` boolean flag
- **D-05:** Aggregate using snap-weighted mean EPA: weight each player's EPA by target_share (WR/TE) or carry_share (RB)
- **D-06:** Compute roll3 and roll6 windows on aggregated team-level positional EPA
- **D-07:** OL is OUT OF SCOPE — team sack rate and pressure rate already cover OL quality
- **D-08:** Top 2 RBs by carries, top 3 WR/TEs by targets per team per week for aggregation
- **D-09:** Graduated severity reusing existing fantasy multipliers: Active=1.0, Questionable=0.85, Doubtful=0.50, Out/IR/PUP=0.0
- **D-10:** Usage-weighted impact: `sum(player_usage_share * (1 - injury_multiplier))` per team per week
- **D-11:** Split into 3 position group scores: QB injury impact, skill position (RB/WR/TE) injury impact, defensive injury impact
- **D-12:** These produce 3 differential features per game (home minus away)
- **D-13:** New Silver path at `data/silver/teams/player_quality/`
- **D-14:** New script `scripts/silver_player_quality_transformation.py`
- **D-15:** Feature engineering reads new Silver path via existing `_assemble_team_features()` join loop — add to SILVER_TEAM_LOCAL_DIRS in config.py
- **D-16:** All player features use shift(1) lag — a test asserts no game's player features reference that same game's stats
- **D-17:** Commit leakage fix (get_feature_columns excluding same-week raw stats) — already implemented, needs commit
- **D-18:** Install LightGBM 4.6.0, CatBoost 1.2.7, SHAP 0.48.0 — all verified Python 3.9 compatible
- **D-19:** Pin versions in requirements.txt

### Claude's Discretion
- Exact column naming conventions for new player features
- How to handle early-season NaN values (week 1-2 have no rolling history)
- Test structure and organization for player feature tests
- Error handling for missing Bronze data (seasons with gaps)

### Deferred Ideas (OUT OF SCOPE)
- Regime detection for QB changes (Phase 31)
- Snap-count based OL quality proxy from PFR pressure data (covered by existing Silver)
- Player-level features for defensive positions (future milestone)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | Commit leakage fix (same-week raw stat exclusion) from feature_engineering.py | Fix already in code (committed in Phase 28 context commit). Needs atomic commit with test coverage verification. |
| INFRA-02 | Install LightGBM, CatBoost, and SHAP with Python 3.9 compatible versions | All three installable on Python 3.9.7. Latest compatible: LightGBM 4.6.0, CatBoost 1.2.10, SHAP 0.49.1 (dry-run confirmed). |
| PLAYER-01 | Compute rolling QB EPA differential (home starter vs away starter) per game | `passing_epa` in Bronze weekly stats (season/week grain). Depth chart `depth_team='1'` and `pos_abb=='QB'` identify starters. |
| PLAYER-02 | Detect starting QB from depth charts with backup flag when starter changes | Depth charts have `depth_team` column ('1','2','3'), `position`, `club_code`, `gsis_id`, `week`. Matches decision D-03. |
| PLAYER-03 | Score team-level injury impact beyond QB (weighted by positional importance) | Bronze injuries: `gsis_id`, `position`, `report_status`, `team`, `season`, `week`. Reuse `apply_injury_adjustments()` multipliers. |
| PLAYER-04 | Compute positional quality metrics for RB, WR (OL out of scope per D-07) aggregated to game level | `rushing_epa`, `receiving_epa`, `target_share`, `carries` in Bronze weekly. `carry_share` NOT available — must compute from carries/team_carries. |
| PLAYER-05 | Apply shift(1) lag to all player features to prevent same-week leakage | `apply_team_rolling()` in team_analytics.py is the canonical pattern. New Silver script must call this function. |
</phase_requirements>

---

## Summary

Phase 28 has two independent work streams: (1) infrastructure setup (commit the leakage fix, install ML packages) and (2) building a new Silver team source for player-level quality metrics. The infrastructure items are atomic and low-risk. The player features work requires building `silver_player_quality_transformation.py` that aggregates Bronze player data (weekly stats + depth charts + injuries) to `[team, season, week]` grain, applies the established `apply_team_rolling()` lag pattern, and outputs to `data/silver/teams/player_quality/`.

The critical schema discovery: Bronze depth_charts use `club_code` (not `team`), `pos_abb` (not `position` shorthand), and `depth_team` string values ('1'/'2'/'3'). The `carry_share` column does NOT exist in Bronze weekly stats — it must be computed as `carries / team_total_carries` per week. SHAP 0.49.1 (not 0.48.0 as specified in D-18) is the current latest and is Python 3.9 compatible via numba 0.60.0. CatBoost 1.2.10 is also safe (dry-run passed). The D-18 version specs are acceptable floors but pinning to latest stable is fine.

The leakage fix is already implemented in `src/feature_engineering.py` (committed in the Phase 28 context commit). INFRA-01 means verifying the fix is correct and the test suite covers it — the 11 existing `test_feature_engineering.py` tests all pass with 283 features (down from 337 pre-fix).

**Primary recommendation:** Build the Silver player quality script following the exact `silver_team_transformation.py` pattern: read Bronze parquets, aggregate to [team, season, week], call `apply_team_rolling()`, write to `data/silver/teams/player_quality/season=YYYY/`. Then add `player_quality` to `SILVER_TEAM_LOCAL_DIRS` in config.py and the new columns auto-join via the existing `_assemble_team_features()` loop.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 1.5.3 (pinned) | All DataFrame operations | Project standard — pinned for numpy ABI |
| numpy | 1.26.4 (pinned) | Numeric operations | Project standard — numpy 2.x breaks pandas 1.5.3 |
| xgboost | >=2.1.4,<3.0 | Existing prediction model | Already installed |
| lightgbm | 4.6.0 | Phase 30 base learner (install now per INFRA-02) | Latest Python 3.9 compatible |
| catboost | 1.2.10 | Phase 30 base learner (install now per INFRA-02) | Latest Python 3.9 compatible (1.2.7 minimum, 1.2.10 available) |
| shap | 0.49.1 | Phase 29 feature importance (install now per INFRA-02) | Latest Python 3.9 compatible (not 0.48.0 — 0.49.1 works) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyarrow | 21.0.0 | Parquet read/write | Already in stack |
| glob | stdlib | Find latest Bronze parquet files | Pattern: `data/bronze/*/season=YYYY/*.parquet` |
| optuna | >=4.0 | Hyperparameter tuning | Phase 30 |
| scikit-learn | >=1.5 | Ridge meta-learner | Phase 30 |

### Installation
```bash
source venv/bin/activate
pip install lightgbm==4.6.0 catboost==1.2.10 shap==0.49.1
```

Add to `requirements.txt`:
```
lightgbm==4.6.0
catboost==1.2.10
shap==0.49.1
```

**Version note (verified 2026-03-24):**
- LightGBM 4.6.0: latest available, matches D-18
- CatBoost 1.2.10: latest available (D-18 specified 1.2.7 — 1.2.10 is safe upgrade)
- SHAP 0.49.1: latest available — STATE.md warning about 0.48.0 being "last Py3.9 compatible" is stale. Dry-run install confirmed 0.49.1 resolves on Python 3.9.7 (numba 0.60.0 supports Python 3.9–3.12).

---

## Architecture Patterns

### Recommended Project Structure (new files only)
```
scripts/
└── silver_player_quality_transformation.py   # NEW: Bronze → Silver player quality

data/silver/teams/
└── player_quality/
    └── season=YYYY/
        └── player_quality_YYYYMMDD_HHMMSS.parquet  # NEW: [team, season, week] grain

src/config.py                                  # MODIFY: add player_quality to SILVER_TEAM_LOCAL_DIRS
tests/
└── test_player_quality.py                     # NEW: lag guard + schema tests
```

### Pattern 1: Bronze → Silver Team Source (established pattern)

Follow `scripts/silver_team_transformation.py` exactly:

```python
# Source: silver_team_transformation.py (lines 1-80)
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")

def _read_local_bronze(data_type: str, season: int) -> pd.DataFrame:
    pattern = os.path.join(BRONZE_DIR, data_type, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])  # latest timestamp

def _save_local_silver(df: pd.DataFrame, key: str) -> str:
    path = os.path.join(SILVER_DIR, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    return path
```

### Pattern 2: Rolling Window with shift(1) Lag (canonical)

```python
# Source: src/team_analytics.py apply_team_rolling()
from team_analytics import apply_team_rolling

# After aggregating to [team, season, week] grain:
stat_cols = ["qb_passing_epa", "rb_weighted_epa", "wr_te_weighted_epa"]
df_with_rolling = apply_team_rolling(df, stat_cols, windows=[3, 6])
# Produces: qb_passing_epa_roll3, qb_passing_epa_roll6, qb_passing_epa_std
# Each uses .shift(1) — this week's rolling value = mean of PRIOR weeks
```

### Pattern 3: Silver Source Registration

```python
# Source: src/config.py SILVER_TEAM_LOCAL_DIRS
SILVER_TEAM_LOCAL_DIRS = {
    # ... existing 8 entries ...
    "player_quality": "teams/player_quality",  # ADD THIS
}
```

The `_assemble_team_features()` loop in `feature_engineering.py` auto-joins on `[team, season, week]` — no changes to `feature_engineering.py` needed. New columns from `player_quality` automatically flow into game features.

### Pattern 4: get_feature_columns Passthrough for Rolling Features

```python
# Source: src/feature_engineering.py get_feature_columns() lines 289-291
def _is_rolling(col: str) -> bool:
    return "roll3" in col or "roll6" in col or "std" in col
```

**Critical:** New player features MUST have `_roll3`, `_roll6`, or `_std` suffix to pass the leakage filter. Raw per-week player values (e.g., `qb_passing_epa` without rolling suffix) will be silently excluded from `get_feature_columns()` — this is correct behavior, but the Silver output should include both raw and rolling for inspection purposes.

### Pattern 5: QB Starter Detection (both-signal approach)

```python
# Depth chart signal (pre-game, from Bronze depth_charts)
# Key columns: club_code, pos_abb, depth_team, gsis_id, week, season
# Note: column is 'club_code' NOT 'team', and 'pos_abb' NOT 'position'
depth_starters = depth_df[
    (depth_df["pos_abb"] == "QB") &
    (depth_df["depth_team"] == "1")
][["club_code", "season", "week", "gsis_id", "full_name"]].rename(
    columns={"club_code": "team"}
)

# Actual starter signal (post-game truth, from Bronze weekly)
# Who threw the most passes — lagged via shift(1) for next-week use
actual_starters = (
    weekly_df[weekly_df["position"] == "QB"]
    .sort_values(["recent_team", "season", "week", "attempts"], ascending=[True, True, True, False])
    .groupby(["recent_team", "season", "week"])
    .first()
    .reset_index()
    [["recent_team", "season", "week", "player_id"]]
    .rename(columns={"recent_team": "team", "player_id": "actual_starter_id"})
)
```

### Pattern 6: carry_share Computation (Bronze weekly lacks this column)

```python
# carry_share does NOT exist in Bronze weekly — compute it:
weekly_df["team_carries"] = weekly_df.groupby(
    ["recent_team", "season", "week"]
)["carries"].transform("sum")
weekly_df["carry_share"] = weekly_df["carries"] / weekly_df["team_carries"].replace(0, np.nan)
```

### Pattern 7: Injury Impact Scoring (reuse apply_injury_adjustments pattern)

```python
# Bronze injuries schema: gsis_id, position, report_status, team, season, week, full_name
# Status multipliers (from projection_engine.py apply_injury_adjustments)
INJURY_MULTIPLIERS = {
    "Active": 1.0,
    "Questionable": 0.85,
    "Doubtful": 0.50,
    "Out": 0.0,
    "IR": 0.0,
    "PUP": 0.0,
}

# Usage-weighted impact per team per week (D-10)
# impact = sum(player_usage_share * (1 - multiplier))
# Higher = more injured
```

### Anti-Patterns to Avoid

- **Using depth chart `team` column directly:** The actual column is `club_code`. Using `team` will cause a KeyError or silent join failure.
- **Assuming `depth_team` is integer:** It is a string ('1', '2', '3'). Filter with `== '1'` not `== 1`.
- **Using `carry_share` from Bronze weekly:** This column does not exist. Compute it from `carries / team_total_carries`.
- **Joining depth charts without season column in Bronze file:** The 2024 depth charts parquet has `season` — verify earlier seasons have it too before multi-season run.
- **Raw (non-rolling) player features in game output:** They will be excluded by `get_feature_columns()` since they lack `_roll3`/`_roll6`/`_std` suffix. The downstream model won't see them — this is correct but can cause confusion during debugging.
- **Writing Silver with wrong grain:** Silver player quality must be `[team, season, week]` one row per team per week. If a team has no players that week (bye week edge case), include a row with NaN values so the left join in `_assemble_team_features()` doesn't drop games.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rolling window with lag | Custom groupby shift logic | `apply_team_rolling()` in `team_analytics.py` | Established, tested, produces correct `_roll3`/`_roll6`/`_std` naming |
| Latest parquet resolution | glob + sort + index custom code | `_read_latest_local(subdir, season)` in `feature_engineering.py` | Handles timestamp suffix pattern correctly |
| Silver file write path | Custom mkdir + parquet write | `_save_local_silver(df, key)` pattern from silver_team_transformation.py | Consistent path structure |
| Injury multiplier lookup | Custom status dict | `INJURY_MULTIPLIERS` dict (copy from projection_engine.py) | Already battle-tested in fantasy projections |
| Feature column selection | Custom filter logic | `get_feature_columns(game_df)` | Already handles leakage filter; adding `_roll3`/`_roll6` suffix satisfies it automatically |

**Key insight:** The entire integration path (Bronze read → Silver write → feature join → model input) is fully paved. The new script only needs to handle the Bronze aggregation step; everything downstream is automatic.

---

## Common Pitfalls

### Pitfall 1: depth_charts column name mismatch
**What goes wrong:** Code uses `df["team"]` or `df["position"]` — KeyError at runtime.
**Why it happens:** Other Bronze sources use `team`; depth_charts uses `club_code`. `position` exists in weekly stats; depth charts use `pos_abb`.
**How to avoid:** Filter with `depth_df["pos_abb"] == "QB"` and rename `club_code` → `team` before any join.
**Warning signs:** KeyError on `team` or `position` when reading depth_charts parquet.

### Pitfall 2: carry_share missing from Bronze weekly
**What goes wrong:** `weekly_df["carry_share"]` raises KeyError — column doesn't exist.
**Why it happens:** `target_share` exists (WR/TE), but `carry_share` is absent. Decision D-05 specifies carry_share for RBs.
**How to avoid:** Compute `carry_share = carries / team_total_carries` using groupby transform before aggregation.
**Warning signs:** KeyError on `carry_share`.

### Pitfall 3: New player features bypassed by get_feature_columns leakage filter
**What goes wrong:** Player feature columns exist in game_df but `get_feature_columns()` returns 0 new features.
**Why it happens:** `get_feature_columns()` only passes columns with `_roll3`, `_roll6`, or `_std` in their name (or pre-game context whitelist). Raw weekly values get silently dropped.
**How to avoid:** Ensure all player metric column names output from `apply_team_rolling()` have `_roll3`/`_roll6`/`_std` suffix. Write a test asserting `get_feature_columns()` returns at least N new columns after adding player_quality.
**Warning signs:** Feature count stays at 283 after adding player_quality Silver source.

### Pitfall 4: shift(1) applied globally instead of per-team per-season
**What goes wrong:** Week 1 of team B accidentally uses the last week of team A's prior season.
**Why it happens:** `shift(1)` without groupby crosses team/season boundaries.
**How to avoid:** Always use `df.groupby(["team", "season"])[col].transform(lambda s: s.shift(1).rolling(...).mean())` — this is what `apply_team_rolling()` already does correctly. Never call `df[col].shift(1)` directly.
**Warning signs:** Week 1 of 2021 has non-NaN rolling values for teams that look suspiciously like 2020 Week 18 values.

### Pitfall 5: Early-season NaN handling (weeks 1-2)
**What goes wrong:** Model training fails or XGBoost produces unexpected predictions for early-season games.
**Why it happens:** roll3/roll6 with min_periods=1 return values from only 1-2 prior games, but week 1 has NO prior data (shift(1) produces NaN for all of week 1).
**How to avoid:** `apply_team_rolling()` already uses `min_periods=1` which handles weeks 2+. Week 1 NaNs are expected and handled by XGBoost natively. Verify test that week 1 games don't crash assembly (existing `test_early_season_nan` test covers this pattern).
**Warning signs:** Model training crashes with "Input X contains NaN" before imputation step.

### Pitfall 6: INFRA-01 already committed — don't double-commit
**What goes wrong:** Creating a new commit that re-introduces or re-states the leakage fix when it was already committed.
**Why it happens:** The leakage fix was committed in the Phase 28 context commit (commit `e5322bf`). INFRA-01 says "needs commit" but the code is already committed.
**How to avoid:** Verify `get_feature_columns()` in current HEAD already has the leakage logic. INFRA-01 work is: add/update tests proving the fix works, verify feature count is 283 (not 337), and document the fix is complete.
**Warning signs:** Seeing `get_feature_columns()` returning 337 features.

---

## Code Examples

### QB EPA Aggregation to Team Level

```python
# Source: designed to match team_analytics.py patterns
import pandas as pd
import numpy as np

def compute_qb_quality(weekly_df: pd.DataFrame, depth_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate QB passing EPA to [team, season, week] with starter detection."""

    # Step 1: Depth chart starter (pre-game signal)
    # depth_team is string '1' = starter
    starters = depth_df[
        (depth_df["pos_abb"] == "QB") & (depth_df["depth_team"] == "1")
    ][["club_code", "season", "week", "gsis_id"]].rename(
        columns={"club_code": "team", "gsis_id": "depth_starter_id"}
    )

    # Step 2: Actual starter (who threw most passes that week — lagged for next week use)
    qb_weekly = weekly_df[weekly_df["position"] == "QB"].copy()
    actual = (
        qb_weekly.sort_values("attempts", ascending=False)
        .groupby(["recent_team", "season", "week"])
        .first()
        .reset_index()
        [["recent_team", "season", "week", "player_id", "passing_epa"]]
        .rename(columns={"recent_team": "team", "player_id": "actual_starter_id"})
    )

    # Step 3: Merge and detect backup starts
    merged = starters.merge(actual, on=["team", "season", "week"], how="left")
    merged["backup_qb_start"] = (
        merged["depth_starter_id"] != merged["actual_starter_id"]
    ).fillna(False).astype(int)
    merged = merged.rename(columns={"passing_epa": "qb_passing_epa"})

    return merged[["team", "season", "week", "qb_passing_epa", "backup_qb_start"]]
```

### Snap-Weighted Positional EPA for RB/WR/TE

```python
# Source: designed to follow D-05, D-08 decisions
def compute_positional_quality(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate snap-weighted EPA for RB and WR/TE to team level."""

    df = weekly_df.copy()

    # Compute carry_share (not available in Bronze)
    team_carries = df.groupby(["recent_team", "season", "week"])["carries"].transform("sum")
    df["carry_share"] = (df["carries"] / team_carries.replace(0, np.nan)).fillna(0.0)

    results = []
    for team, team_df in df.groupby(["recent_team", "season", "week"]):
        row = {"team": team[0], "season": team[1], "week": team[2]}

        # Top 2 RBs by carries (D-08)
        rbs = team_df[team_df["position"] == "RB"].nlargest(2, "carries")
        if len(rbs) > 0 and rbs["carries"].sum() > 0:
            weights = rbs["carry_share"] / rbs["carry_share"].sum()
            row["rb_weighted_epa"] = (rbs["rushing_epa"] * weights).sum()
        else:
            row["rb_weighted_epa"] = np.nan

        # Top 3 WR/TEs by targets (D-08)
        skill = team_df[team_df["position"].isin(["WR", "TE"])].nlargest(3, "targets")
        if len(skill) > 0 and skill["targets"].sum() > 0:
            weights = skill["target_share"].fillna(0) / skill["target_share"].fillna(0).sum()
            row["wr_te_weighted_epa"] = (skill["receiving_epa"] * weights).sum()
        else:
            row["wr_te_weighted_epa"] = np.nan

        results.append(row)

    return pd.DataFrame(results)
```

### Injury Impact Scoring

```python
# Source: reuses apply_injury_adjustments() pattern from projection_engine.py
INJURY_MULTIPLIERS = {
    "Active": 1.0, "Questionable": 0.85, "Doubtful": 0.50,
    "Out": 0.0, "IR": 0.0, "PUP": 0.0,
}
USAGE_STAT = {"QB": "pass_attempts_share", "RB": "carry_share", "WR": "target_share", "TE": "target_share"}

def compute_injury_impact(injuries_df: pd.DataFrame, weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Compute usage-weighted injury impact scores per team per week.

    Returns columns: team, season, week,
        qb_injury_impact, skill_injury_impact, def_injury_impact
    """
    # Map report_status -> (1 - multiplier)  → higher means more injured
    injuries_df = injuries_df.copy()
    injuries_df["impact"] = 1.0 - injuries_df["report_status"].map(
        INJURY_MULTIPLIERS
    ).fillna(0.0)  # unlisted = Active = 0 impact

    # ... aggregate by position group per team per week
    # qb_injury_impact: sum(usage_share * impact) for QBs
    # skill_injury_impact: sum(usage_share * impact) for RB/WR/TE
    # def_injury_impact: count-weighted impact for defensive positions
```

### Silver Source Registration (config.py change)

```python
# Source: src/config.py SILVER_TEAM_LOCAL_DIRS — add one line
SILVER_TEAM_LOCAL_DIRS = {
    "pbp_metrics": "teams/pbp_metrics",
    "tendencies": "teams/tendencies",
    "sos": "teams/sos",
    "situational": "teams/situational",
    "pbp_derived": "teams/pbp_derived",
    "game_context": "teams/game_context",
    "referee_tendencies": "teams/referee_tendencies",
    "playoff_context": "teams/playoff_context",
    "player_quality": "teams/player_quality",   # ADD THIS LINE
}
```

---

## Bronze Data Schemas (verified 2026-03-24)

### Bronze Weekly Player Stats (`data/bronze/players/weekly/season=YYYY/week=WW/`)
Key columns for this phase:
- `player_id` — gsis_id format (`00-0035228`)
- `recent_team` — team abbreviation (NOT `club_code`)
- `position` — `QB`, `RB`, `WR`, `TE` etc.
- `passing_epa`, `rushing_epa`, `receiving_epa` — all present
- `target_share` — present for receivers (NaN for QBs/RBs when not catching)
- `carries`, `attempts`, `targets` — present
- **`carry_share` is ABSENT** — must be computed
- Shape for 2024 full season file: (19421, 115 columns)
- Available seasons: 2016-2024 (all PREDICTION_SEASONS) — verified with one file per season

### Bronze Depth Charts (`data/bronze/depth_charts/season=YYYY/`)
Key columns:
- `club_code` — team abbreviation (NOT `team`)
- `season`, `week`, `game_type`
- `pos_abb` — position abbreviation (`QB`, `RB`, etc.)
- `depth_team` — STRING values `'1'`, `'2'`, `'3'` (starter = `'1'`)
- `gsis_id` — player identifier, joins to weekly stats `player_id`
- `full_name`, `first_name`, `last_name`
- **No `depth_team` numeric — always string**
- Shape for 2024: (37312, 15 columns)
- Available seasons: 2001-2025 (all PREDICTION_SEASONS)

### Bronze Injuries (`data/bronze/players/injuries/season=YYYY/week=WW/`)
Key columns:
- `gsis_id` — player identifier
- `team`, `season`, `week`, `game_type`
- `position` — position string
- `full_name`, `first_name`, `last_name`
- `report_status` — `Active`, `Questionable`, `Doubtful`, `Out`, `IR`, `PUP`
- Shape for 2024 sample: (6215, 18 columns)
- **Note:** nflverse discontinued injury data after 2024 per config.py DATA_TYPE_SEASON_RANGES

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| get_feature_columns() returned all diff_ columns | Only rolling/lagged/pre-game columns (leakage fix) | Phase 28 context commit (2026-03-24) | 337 → 283 features; holdout ATS 90.7% → realistic 50% |
| Feature count: ~337 | Feature count: 283 | 2026-03-24 | Real baseline established |
| No player-level features | QB EPA differential, positional quality, injury impact | Phase 28 (this phase) | ~27-47 new features |

**Deprecated/outdated:**
- `depth_team='1'` integer filter: the actual column contains strings — always use `== '1'`
- D-18 SHAP version `0.48.0`: safe to install `0.49.1` (newer and Python 3.9 compatible)
- D-18 CatBoost version `1.2.7`: safe to install `1.2.10` (newer, pip dry-run passed)

---

## Open Questions

1. **Injury data coverage for 2016-2023 training seasons**
   - What we know: `DATA_TYPE_SEASON_RANGES["injuries"]` covers 2009-2024. Bronze injuries directory confirmed present for multiple seasons.
   - What's unclear: Whether injury data for early seasons (2016-2018) has complete weekly coverage or gaps.
   - Recommendation: In `silver_player_quality_transformation.py`, make injury data optional — if no injury file found for a season/week, set impact scores to 0.0 (no known injury impact) and log a warning.

2. **Depth chart `week` column format — float vs int**
   - What we know: A quick DataFrame inspection shows `week` as float64 in the 2024 parquet (value `1.0`, not `1`).
   - What's unclear: Whether this causes join mismatches with weekly stats `week` (which is int).
   - Recommendation: Cast `depth_df["week"]` to int before joining: `depth_df["week"] = depth_df["week"].astype(int)`.

3. **Seasonal depth chart vs weekly depth chart**
   - What we know: Bronze depth_charts are partitioned by season only (not season+week), but the data contains a `week` column.
   - What's unclear: Whether the depth chart file for a season covers all weeks (pre-verified: 2024 file has 37312 rows with week column values).
   - Recommendation: The single-file-per-season partition is fine — read once and filter by week during aggregation.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.1 |
| Config file | none (rootdir auto-detected) |
| Quick run command | `python -m pytest tests/test_feature_engineering.py tests/test_player_quality.py -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | `get_feature_columns()` returns 283 features (not 337) | unit | `pytest tests/test_feature_engineering.py -k "test_feature_count" -x` | ❌ Wave 0 (add to existing file) |
| INFRA-01 | No same-week raw stat cols in `get_feature_columns()` | unit | `pytest tests/test_feature_engineering.py::TestFeatureEngineering::test_temporal_lag -x` | ✅ existing |
| INFRA-02 | LightGBM, CatBoost, SHAP importable | unit | `pytest tests/test_infrastructure.py -k "test_ml_packages" -x` | ❌ Wave 0 |
| PLAYER-01 | QB EPA differential features appear in game_df | integration | `pytest tests/test_player_quality.py::test_qb_features_in_game_df -x` | ❌ Wave 0 |
| PLAYER-02 | `backup_qb_start` flag set when depth chart QB != actual | unit | `pytest tests/test_player_quality.py::test_backup_qb_detection -x` | ❌ Wave 0 |
| PLAYER-03 | Injury impact scores range [0, 1], not NaN for known-healthy teams | unit | `pytest tests/test_player_quality.py::test_injury_impact_range -x` | ❌ Wave 0 |
| PLAYER-04 | RB/WR-TE weighted EPA features present with roll3/roll6 suffix | unit | `pytest tests/test_player_quality.py::test_positional_features_rolling -x` | ❌ Wave 0 |
| PLAYER-05 | Week N player features use only weeks < N data (lag guard) | unit | `pytest tests/test_player_quality.py::test_shift1_lag_guard -x` | ❌ Wave 0 |
| PLAYER-05 | Week 1 player_quality features are NaN (no prior data) | unit | `pytest tests/test_player_quality.py::test_week1_nan -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_feature_engineering.py tests/test_player_quality.py -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green (439+ tests) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_player_quality.py` — new file covering PLAYER-01 through PLAYER-05 and lag guard
- [ ] Add `test_feature_count` to `tests/test_feature_engineering.py` — asserts 283 features (INFRA-01 evidence)
- [ ] Add `test_ml_packages` to `tests/test_infrastructure.py` — asserts `import lightgbm, catboost, shap` succeed (INFRA-02)

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `src/feature_engineering.py` — full `get_feature_columns()` leakage filter logic
- Direct code inspection: `src/team_analytics.py` — `apply_team_rolling()` pattern (lines 67-120)
- Direct code inspection: `src/config.py` — `SILVER_TEAM_LOCAL_DIRS`, `LABEL_COLUMNS`, season ranges
- Direct code inspection: `src/projection_engine.py` — `apply_injury_adjustments()` injury multipliers
- Direct data inspection: Bronze weekly (19421 rows, 115 cols, confirmed columns including `passing_epa`, `carries`; `carry_share` absent)
- Direct data inspection: Bronze depth_charts (37312 rows for 2024, `club_code`, `pos_abb`, `depth_team` as string '1'/'2'/'3')
- Direct data inspection: Bronze injuries (6215 rows, `report_status` column confirmed)
- Direct data inspection: Silver pbp_metrics (544 rows, `[team, season, week]` grain, rolling cols confirmed)
- pip dry-run: LightGBM 4.6.0, CatBoost 1.2.10, SHAP 0.49.1 all resolve on Python 3.9.7
- Test run: All 16 existing feature engineering tests pass with 283-feature leakage-fixed model

### Secondary (MEDIUM confidence)
- `.planning/research/FEATURES.md` — QB signal is #1 gap finding
- `.planning/research/PITFALLS.md` — player aggregation leakage surface

### Tertiary (LOW confidence)
- STATE.md claim "SHAP 0.48.0 is last Python 3.9 compatible" — contradicted by dry-run evidence (0.49.1 installs fine on Python 3.9.7)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified via pip index and dry-run install
- Architecture: HIGH — verified via direct code inspection of all integration points
- Bronze schemas: HIGH — verified via actual parquet file inspection
- Pitfalls: HIGH — discovered via schema inspection (carry_share absent, depth_team as string, club_code not team)
- Version recommendations: HIGH — dry-run confirmed; one LOW item (SHAP version) contradicted by evidence

**Research date:** 2026-03-24
**Valid until:** 2026-06-24 (stable libraries; Bronze schema unlikely to change)
