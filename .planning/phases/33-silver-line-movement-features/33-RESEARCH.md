# Phase 33: Silver Line Movement Features - Research

**Researched:** 2026-03-27
**Domain:** Silver layer market data transformation, feature engineering integration
**Confidence:** HIGH

## Summary

Phase 33 transforms Bronze odds Parquet (Phase 32 output) into Silver per-team-per-week market data rows, computes line movement features, and integrates the new Silver source into `feature_engineering.py`. The codebase has well-established patterns for all three concerns: `game_context.py` demonstrates per-team unpivoting from home/away game rows, `team_analytics.py` provides the Silver compute module structure, and `feature_engineering.py` has a Silver source loop that auto-discovers new sources via `SILVER_TEAM_LOCAL_DIRS` in config.py.

The implementation is straightforward arithmetic on existing Bronze columns. Opening/closing spread and total values are already float64 in the Bronze Parquet (no NaN for the 2020 season tested). The key complexity is the sign convention for directional features (spread columns must be negated for the away team row) and the temporal categorization (only `opening_spread` and `opening_total` are pre-game safe; all closing-line-derived features are retrospective-only). Both decisions are locked in CONTEXT.md.

Bronze odds data currently exists only for season 2020 (1 file, 244 rows, 14 columns). The full FinnedAI dataset covers 2016-2021, but only season=2020 has been ingested to local Parquet. The Silver transform must handle this gracefully -- processing only seasons where Bronze data exists. For seasons 2022-2024 (no Bronze odds), the left join in `feature_engineering.py` naturally produces NaN for all market columns, which is the correct behavior per D-13/D-14.

**Primary recommendation:** Create `src/market_analytics.py` following `game_context.py` patterns for unpivoting, `scripts/silver_market_transformation.py` following the CLI pattern from `silver_game_context_transformation.py`, then add `market_data` to `SILVER_TEAM_LOCAL_DIRS` and `opening_spread`/`opening_total` to `_PRE_GAME_CONTEXT` in feature_engineering.py.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Symmetric features (same value for both teams): `spread_move_abs`, `total_shift`, `total_move_abs`, `spread_magnitude`, `total_magnitude`, `crosses_key_spread` -- these are properties of the game, not directional
- **D-02:** Directional features (sign-flipped for away team): `opening_spread`, `closing_spread`, `spread_shift` -- home team gets the value as-is (home-team perspective from Bronze), away team gets the negated value
- **D-03:** Opening/closing totals are symmetric (same for both teams) -- no sign flip needed
- **D-04:** The reshape produces columns: `team`, `opponent`, `season`, `week`, `game_id`, `game_type`, plus all market features. `is_home` boolean column for downstream filtering
- **D-05:** Pre-game knowable features (add to `_PRE_GAME_CONTEXT` in feature_engineering.py): `opening_spread`, `opening_total` -- these are known before kickoff and safe for live prediction
- **D-06:** Retrospective-only features (MUST NOT be in `_PRE_GAME_CONTEXT`): `spread_shift`, `total_shift`, `spread_move_abs`, `total_move_abs`, `spread_magnitude`, `total_magnitude`, `crosses_key_spread`, `closing_spread`, `closing_total` -- all depend on the closing line which is only known at kickoff
- **D-07:** Retrospective features are available for historical backtesting and ablation (Phase 34) but excluded from `get_feature_columns()` for live predictions by design -- the `_is_pre_game_context()` filter handles this automatically
- **D-08:** Add a code comment block in market_analytics.py and feature_engineering.py explicitly documenting which features are pre-game vs retrospective, so future developers don't accidentally enable closing-line leakage
- **D-09:** Include `crosses_key_spread` boolean (movement crosses 3, 7, or 10) -- NFL key numbers where point probability spikes
- **D-10:** Include `crosses_key_total` boolean (movement crosses common total thresholds 41, 44, 47)
- **D-11:** Both key-number crossing features are symmetric (same value for home and away)
- **D-12:** Silver market_data transform only runs for seasons where Bronze odds data exists (2016-2021)
- **D-13:** Feature assembly in feature_engineering.py handles missing Silver market_data gracefully -- NaN from left join
- **D-14:** No synthetic data or imputation for 2022-2024 -- NaN is honest
- **D-15:** Steam move flag (`is_steam_move`) set to NaN for all rows -- no timestamps in FinnedAI data
- **D-16:** The `is_steam_move` column exists in schema (not omitted) for forward compatibility

### Claude's Discretion
- Exact module structure of market_analytics.py (function decomposition)
- Silver CLI script argument handling details
- Logging verbosity and progress reporting
- Test fixture design for the reshape logic

### Deferred Ideas (OUT OF SCOPE)
- No-vig implied probability from moneylines -- v2.2 Betting Framework
- Rolling average of line movement across games (momentum signal) -- backlog if ablation positive
- Multi-book consensus features -- out of scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LINE-01 | Compute spread movement (closing - opening) and total movement per game with nflverse sign convention | Bronze Parquet has `opening_spread`, `closing_spread`, `opening_total`, `closing_total` as float64. Spread shift = `closing_spread - opening_spread`. Total shift = `closing_total - opening_total`. Sign convention inherited from Bronze (positive = home favored). D-02 defines directional sign flipping for per-team rows. |
| LINE-02 | Categorize movement into direction buckets (large >2pts, medium 1-2, small <1, none) | Implemented as `spread_magnitude` categorical column derived from `spread_move_abs`. Bucket thresholds: large (abs > 2.0), medium (1.0 <= abs <= 2.0), small (0 < abs < 1.0), none (abs == 0). Symmetric per D-01. |
| LINE-03 | Detect steam moves where data supports it; NaN where timestamps unavailable | Per D-15/D-16: `is_steam_move` column set to NaN for all rows. FinnedAI data has no timestamp granularity. Column exists for forward compatibility. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 1.5.3 (existing) | DataFrame arithmetic for movement computation, unpivoting | Already in venv; all project transforms use pandas |
| pyarrow | existing | Parquet read/write | Already in venv; project standard |
| numpy | existing | NaN handling, boolean operations | Already in venv |

### Supporting
No new dependencies required. All operations are arithmetic on existing Bronze columns.

**Installation:** None -- all libraries already installed.

## Architecture Patterns

### Recommended Project Structure
```
src/
  market_analytics.py          # NEW: Silver market data compute module
scripts/
  silver_market_transformation.py  # NEW: Silver CLI for market_data
src/
  config.py                    # MODIFY: add market_data to SILVER_TEAM_LOCAL_DIRS + S3 keys
  feature_engineering.py       # MODIFY: add opening_spread/opening_total to _PRE_GAME_CONTEXT
data/silver/teams/market_data/
  season=2020/                 # Output: market_data_YYYYMMDD_HHMMSS.parquet
```

### Pattern 1: Per-Team Unpivot (from game_context.py)
**What:** Convert per-game Bronze rows (home_team, away_team) into two per-team rows with directional adjustments.
**When to use:** Any time game-level data must join to `_assemble_team_features()` which expects [team, season, week] keys.
**Example from game_context.py lines 70-117:**
```python
# Home row: keep columns as-is, add is_home=True
home = schedules_df.rename(columns={
    "home_team": "team",
    "away_team": "opponent",
}).assign(is_home=True)

# Away row: swap home/away, add is_home=False
away = schedules_df.rename(columns={
    "away_team": "team",
    "home_team": "opponent",
}).assign(is_home=False)

result = pd.concat([home[cols], away[cols]], ignore_index=True)
```

**For market_analytics.py:** Same pattern but with sign flipping per D-02:
```python
# Home row: directional spreads as-is
home["opening_spread"] = odds_df["opening_spread"]  # positive = home favored
home["spread_shift"] = odds_df["spread_shift"]

# Away row: negate directional features
away["opening_spread"] = -odds_df["opening_spread"]
away["spread_shift"] = -odds_df["spread_shift"]

# Symmetric features: same for both rows
for col in ["total_shift", "spread_move_abs", "total_move_abs",
            "spread_magnitude", "total_magnitude",
            "crosses_key_spread", "crosses_key_total",
            "opening_total", "closing_total", "is_steam_move"]:
    home[col] = odds_df[col]
    away[col] = odds_df[col]
```

### Pattern 2: Silver Source Auto-Discovery (from feature_engineering.py)
**What:** `_assemble_team_features()` iterates `SILVER_TEAM_SOURCES` (aliased from `SILVER_TEAM_LOCAL_DIRS`) and left-joins each source on [team, season, week].
**Key code (lines 186-198):**
```python
for name, subdir in SILVER_TEAM_SOURCES.items():
    if name == "game_context":
        continue  # Already loaded as base
    df = _read_latest_local(subdir, season)
    if df.empty:
        continue
    base = base.merge(
        df, on=["team", "season", "week"], how="left",
        suffixes=("", f"__{name}"),
    )
```
**Integration point:** Adding `"market_data": "teams/market_data"` to `SILVER_TEAM_LOCAL_DIRS` is sufficient. No code changes in the loop itself.

### Pattern 3: Feature Column Filtering (from feature_engineering.py)
**What:** `get_feature_columns()` uses `_PRE_GAME_CONTEXT` and `_PRE_GAME_CUMULATIVE` sets plus `_is_rolling()` to decide which columns are valid features.
**Key logic (lines 362-415):**
- Non-suffixed columns: only if pre-game or rolling
- `_home`/`_away` suffixed: only if `_is_pre_game_context()` returns True
- `diff_` prefixed: only if rolling or pre-game context
- The `_is_pre_game_context()` helper strips suffixes and `diff_` prefix, then checks against the sets

**For opening_spread/opening_total:** Adding them to `_PRE_GAME_CONTEXT` set means they pass all three filter paths (non-suffixed, suffixed, diff_). Retrospective features like `spread_shift` are NOT in the set, so they are automatically excluded from `get_feature_columns()` -- no explicit exclusion needed.

### Pattern 4: Silver CLI Script (from silver_game_context_transformation.py)
**What:** CLI wrapper with `--season`/`--seasons` args, local save + optional S3 upload.
**Key structure:**
```python
def run_market_transform(seasons: list, s3_bucket=None):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for season in seasons:
        odds_df = _read_local_odds(season)
        if odds_df.empty:
            print(f"  No Bronze odds for season {season}, skipping.")
            continue
        market_df = compute_market_features(odds_df)
        key = SILVER_TEAM_S3_KEYS["market_data"].format(season=season, ts=ts)
        _save_local_silver(market_df, key, ts)
```

### Anti-Patterns to Avoid
- **Rolling windows on market data:** Line movement is a single-game property, not a trend. Do NOT apply rolling averages to spread_shift (D-deferred: momentum signal is backlog item, not Phase 33).
- **Imputing NaN for missing seasons:** Per D-14, 2022-2024 missing data stays NaN. Never zero-fill or forward-fill market columns.
- **Adding retrospective features to _PRE_GAME_CONTEXT:** This would create closing-line leakage. The temporal comment block (D-08) is the safety net.
- **Building a custom game_id:** Always inherit game_id from Bronze odds, which already joined to nflverse in Phase 32.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-team unpivot | Custom reshape logic | Follow `game_context.py::_unpivot_schedules()` pattern exactly | Proven pattern, handles edge cases |
| Feature gating | Custom inclusion/exclusion logic | Add to `_PRE_GAME_CONTEXT` set in feature_engineering.py | Existing filter handles all column variants (suffixed, diff_, raw) |
| Silver auto-discovery | Custom market_data join in feature_engineering.py | Add to `SILVER_TEAM_LOCAL_DIRS` dict in config.py | The existing loop handles it with zero special-casing |
| S3 upload | Custom boto3 code | Copy `_try_s3_upload()` from silver_team_transformation.py | Identical pattern across all Silver scripts |

## Common Pitfalls

### Pitfall 1: Sign Convention Asymmetry in Differentials
**What goes wrong:** After `assemble_game_features()` splits into home/away and computes `diff_opening_spread = home - away`, the differential is 2x the spread if both sides have the same sign (they should not -- away is negated per D-02).
**Why it happens:** If away team's `opening_spread` is already negated (e.g., home = +3.0, away = -3.0), then `diff_opening_spread = 3.0 - (-3.0) = 6.0`, which is 2x the actual spread.
**How to avoid:** This is actually the correct behavior -- the differential captures the full spread difference between the two teams. The `diff_` prefix columns are home-away differences. With negated away values, `diff_opening_spread` equals `2 * opening_spread_home`, which is proportional to the actual spread. The model can learn from this. Alternatively, if you want the differential to equal the raw spread, you could keep `opening_spread` symmetric (same for both teams) -- but D-02 explicitly requires sign flipping for directional features.
**Warning signs:** If `diff_opening_spread` values are always exactly 2x the Bronze `opening_spread`, this is expected, not a bug.

### Pitfall 2: Missing Bronze Odds for 2022-2024
**What goes wrong:** Silver transform fails or produces empty output for seasons 2022-2024.
**Why it happens:** FinnedAI data only covers 2016-2021. Currently only season=2020 has been ingested locally.
**How to avoid:** The Silver CLI must skip seasons with no Bronze data (per D-12). The feature_engineering.py left join handles NaN gracefully (per D-13). Test with 2022 data to verify NaN propagation.
**Warning signs:** Errors in `_read_latest_local()` for market_data; downstream model training crashes on NaN market columns.

### Pitfall 3: Duplicate Columns After Silver Join
**What goes wrong:** Columns like `game_type`, `game_id`, or `is_home` appear in market_data and also in the base game_context, creating `game_type__market_data` suffixed duplicates.
**Why it happens:** The merge in `_assemble_team_features()` joins on [team, season, week] only. If market_data output includes `game_id`, `game_type`, or other columns already present in game_context base, they create suffixed duplicates.
**How to avoid:** The existing code drops suffixed duplicates (line 197-198). But it is cleaner to exclude non-feature identifier columns from the Silver Parquet output, OR keep them and let the suffix/drop pattern handle it. The safest approach: include `game_id` and `game_type` in the market_data output (they are useful for debugging) and rely on the existing dedup logic.
**Warning signs:** Columns ending in `__market_data` in the assembled DataFrame.

### Pitfall 4: Magnitude Category as String Column
**What goes wrong:** `spread_magnitude` stored as a string category ("large", "medium", "small", "none") is not numeric and gets silently dropped by `get_feature_columns()` which only includes float64/int64/float32/int32/bool dtypes.
**Why it happens:** The dtype filter on line 396 of feature_engineering.py.
**How to avoid:** Either (a) encode magnitude as ordinal integer (0=none, 1=small, 2=medium, 3=large) so it passes the numeric filter, or (b) accept that the string category exists for interpretability but is not directly used as a model feature -- the `spread_move_abs` numeric column captures the same information. Recommendation: use ordinal integer encoding for `spread_magnitude` and `total_magnitude`.
**Warning signs:** Magnitude columns missing from `get_feature_columns()` output.

## Code Examples

### Computing Line Movement Features
```python
# Source: Bronze odds schema (verified from Parquet inspection)
def compute_movement_features(odds_df: pd.DataFrame) -> pd.DataFrame:
    """Compute line movement features from Bronze odds data.

    PRE-GAME features (safe for live prediction):
        opening_spread, opening_total

    RETROSPECTIVE features (historical/ablation only):
        closing_spread, closing_total, spread_shift, total_shift,
        spread_move_abs, total_move_abs, spread_magnitude, total_magnitude,
        crosses_key_spread, crosses_key_total, is_steam_move
    """
    df = odds_df.copy()

    # Movement = closing - opening
    df["spread_shift"] = df["closing_spread"] - df["opening_spread"]
    df["total_shift"] = df["closing_total"] - df["opening_total"]

    # Absolute magnitude
    df["spread_move_abs"] = df["spread_shift"].abs()
    df["total_move_abs"] = df["total_shift"].abs()

    # Magnitude buckets (ordinal: 0=none, 1=small, 2=medium, 3=large)
    df["spread_magnitude"] = pd.cut(
        df["spread_move_abs"],
        bins=[-0.001, 0.0, 1.0, 2.0, float("inf")],
        labels=[0, 1, 2, 3],
    ).astype(float)

    df["total_magnitude"] = pd.cut(
        df["total_move_abs"],
        bins=[-0.001, 0.0, 1.0, 2.0, float("inf")],
        labels=[0, 1, 2, 3],
    ).astype(float)

    # Key number crossing (NFL key numbers: 3, 7, 10 for spreads)
    KEY_SPREAD_NUMBERS = [3, 7, 10]
    open_s = df["opening_spread"].abs()
    close_s = df["closing_spread"].abs()
    df["crosses_key_spread"] = False
    for key_num in KEY_SPREAD_NUMBERS:
        crossed = ((open_s < key_num) & (close_s >= key_num)) | \
                  ((open_s >= key_num) & (close_s < key_num))
        df["crosses_key_spread"] = df["crosses_key_spread"] | crossed

    # Key total thresholds: 41, 44, 47
    KEY_TOTAL_NUMBERS = [41, 44, 47]
    df["crosses_key_total"] = False
    for key_num in KEY_TOTAL_NUMBERS:
        crossed = ((df["opening_total"] < key_num) & (df["closing_total"] >= key_num)) | \
                  ((df["opening_total"] >= key_num) & (df["closing_total"] < key_num))
        df["crosses_key_total"] = df["crosses_key_total"] | crossed

    # Steam move: NaN (no timestamp data per D-15)
    df["is_steam_move"] = float("nan")

    return df
```

### Per-Team Unpivot with Directional Sign Flipping
```python
# Source: game_context.py pattern + D-02 sign convention
def reshape_to_per_team(odds_with_features: pd.DataFrame) -> pd.DataFrame:
    """Reshape game-level odds to per-team-per-week rows.

    Directional columns (D-02): opening_spread, closing_spread, spread_shift
      -> negated for away team
    Symmetric columns (D-01): totals, absolute movement, magnitude, key crossings
      -> same for both teams
    """
    DIRECTIONAL = ["opening_spread", "closing_spread", "spread_shift"]
    SYMMETRIC = [
        "opening_total", "closing_total", "total_shift",
        "spread_move_abs", "total_move_abs",
        "spread_magnitude", "total_magnitude",
        "crosses_key_spread", "crosses_key_total", "is_steam_move",
    ]
    ID_COLS = ["game_id", "season", "week", "game_type"]

    # Home rows
    home = odds_with_features[ID_COLS].copy()
    home["team"] = odds_with_features["home_team"]
    home["opponent"] = odds_with_features["away_team"]
    home["is_home"] = True
    for col in DIRECTIONAL:
        home[col] = odds_with_features[col]
    for col in SYMMETRIC:
        home[col] = odds_with_features[col]

    # Away rows (negate directional)
    away = odds_with_features[ID_COLS].copy()
    away["team"] = odds_with_features["away_team"]
    away["opponent"] = odds_with_features["home_team"]
    away["is_home"] = False
    for col in DIRECTIONAL:
        away[col] = -odds_with_features[col]
    for col in SYMMETRIC:
        away[col] = odds_with_features[col]

    result = pd.concat([home, away], ignore_index=True)
    return result.sort_values(["team", "season", "week"]).reset_index(drop=True)
```

### Config.py Additions
```python
# In SILVER_TEAM_LOCAL_DIRS (line 490):
SILVER_TEAM_LOCAL_DIRS = {
    # ... existing entries ...
    "market_data": "teams/market_data",
}

# In SILVER_TEAM_S3_KEYS (line 232):
SILVER_TEAM_S3_KEYS = {
    # ... existing entries ...
    "market_data": "teams/market_data/season={season}/market_data_{ts}.parquet",
}
```

### Feature Engineering Additions
```python
# In _PRE_GAME_CONTEXT set (line 362):
_PRE_GAME_CONTEXT = {
    "is_dome", "rest_advantage", "is_short_rest", "is_post_bye",
    "travel_miles", "tz_diff", "coaching_tenure", "div_game",
    "temperature", "wind_speed", "is_cold", "is_high_wind",
    "rest_days", "opponent_rest",
    # Market data -- pre-game knowable only (D-05)
    "opening_spread", "opening_total",
}
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, 516 tests passing) |
| Config file | tests/ directory, pytest standard discovery |
| Quick run command | `python -m pytest tests/test_market_analytics.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LINE-01 | spread_shift = closing - opening, total_shift = closing - opening, sign convention correct | unit | `python -m pytest tests/test_market_analytics.py::TestMovementComputation -x` | Wave 0 |
| LINE-01 | Per-team reshape: away team gets negated directional features | unit | `python -m pytest tests/test_market_analytics.py::TestPerTeamReshape -x` | Wave 0 |
| LINE-02 | Magnitude buckets: large >2, medium 1-2, small <1, none 0 | unit | `python -m pytest tests/test_market_analytics.py::TestMagnitudeBuckets -x` | Wave 0 |
| LINE-03 | is_steam_move column exists and is all NaN | unit | `python -m pytest tests/test_market_analytics.py::TestSteamMove -x` | Wave 0 |
| LINE-01 | feature_engineering.py includes opening_spread/opening_total in get_feature_columns() | integration | `python -m pytest tests/test_feature_engineering.py -x -v -k market` | Wave 0 |
| D-06 | Retrospective features excluded from get_feature_columns() | integration | `python -m pytest tests/test_feature_engineering.py -x -v -k retrospective` | Wave 0 |
| D-09/D-10 | Key number crossing computed correctly | unit | `python -m pytest tests/test_market_analytics.py::TestKeyNumberCrossing -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_market_analytics.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_market_analytics.py` -- covers LINE-01, LINE-02, LINE-03, D-09, D-10
- [ ] Additional tests in `tests/test_feature_engineering.py` -- covers D-05, D-06, D-07 (market feature column filtering)

## Sources

### Primary (HIGH confidence)
- **Bronze odds Parquet** -- direct inspection via `pd.read_parquet()`: 14 columns, float64 spreads/totals, zero NaN for 2020 season
- **src/feature_engineering.py** -- full source read: `_assemble_team_features()` loop, `get_feature_columns()` filter, `_PRE_GAME_CONTEXT` set
- **src/game_context.py** -- full source read: `_unpivot_schedules()` pattern for per-team reshape
- **src/config.py** -- grep: `SILVER_TEAM_LOCAL_DIRS` (9 entries), `SILVER_TEAM_S3_KEYS` (8 entries), `LABEL_COLUMNS`
- **scripts/silver_team_transformation.py** -- full source read: CLI pattern with `_save_local_silver()`, `_try_s3_upload()`
- **scripts/silver_game_context_transformation.py** -- full source read: season loop, prior-season chaining
- **scripts/bronze_odds_ingestion.py** -- full source read: FINAL_COLUMNS schema, sign convention negation

### Secondary (MEDIUM confidence)
- **.planning/research/SUMMARY.md** -- project research: feature categorization, architecture approach, pitfalls

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all arithmetic on existing columns
- Architecture: HIGH -- all patterns verified from existing codebase source reads
- Pitfalls: HIGH -- sign convention, NaN handling, and column filtering verified from feature_engineering.py source

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable -- no external dependencies, no API changes expected)
