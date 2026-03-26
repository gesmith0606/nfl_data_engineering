# Phase 31: Advanced Features & Final Validation - Research

**Researched:** 2026-03-25
**Domain:** Feature engineering (momentum signals, EWM windows), model evaluation, ablation testing
**Confidence:** HIGH

## Summary

Phase 31 adds two new feature categories (momentum/streak signals and adaptive EWM windows) to the existing prediction feature vector, then runs a final sealed holdout evaluation comparing three model configurations. The technical scope is narrow and well-constrained: all patterns already exist in the codebase (rolling windows in `team_analytics.py`, differential features in `feature_engineering.py`, comparison backtesting in `backtest_predictions.py`).

The primary risk is the `get_feature_columns()` leakage guard in `feature_engineering.py`, which uses a pattern-match approach (`_is_rolling()` checks for `roll3`, `roll6`, or `std` in column names). New EWM columns (e.g., `_ewm3`) and momentum columns (e.g., `win_streak`, `ats_cover_sum3`) will NOT pass this guard without updating the filter logic. This is the single most important implementation detail.

**Primary recommendation:** Add momentum features in `feature_engineering.py` (computed from Bronze schedules before the schedule join), add EWM columns in `team_analytics.py` alongside existing roll3/roll6, update `get_feature_columns()` to recognize both new column patterns, re-run feature selection, then extend `backtest_predictions.py` with `--holdout` for the three-way comparison table.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Compute win/loss streak (consecutive W/L count, resets on opposite result) and ATS streak (consecutive covers/non-covers) from Bronze schedules
- **D-02:** Lookback is last 3 games only -- season cumulative already captured by existing `win_pct`
- **D-03:** Streaks are raw counts (uncapped) -- let tree models decide where to split
- **D-04:** Include both binary ATS cover (rolling sum over last 3) AND continuous ATS margin (actual spread minus closing line) as features
- **D-05:** All momentum features use shift(1) lag -- no game references its own result
- **D-06:** EWM windows supplement (not replace) existing fixed roll3/roll6 -- added alongside, then feature selection prunes redundant ones
- **D-07:** Compute EWM at Silver source level in `team_analytics.py` alongside existing rolling columns -- consistent with where roll3/roll6 live
- **D-08:** Single halflife = 3 games -- matches roll3 in recency emphasis, keeps feature growth manageable
- **D-09:** EWM applied to team-level metrics only: EPA, success rate, CPOE, red zone -- not player-level (avoids feature explosion)
- **D-10:** After adding EWM features, re-run Phase 29's feature selection to update SELECTED_FEATURES with the expanded candidate set
- **D-11:** Ship bar is meaningful improvement: at least +1% ATS accuracy OR flipping vig-adjusted profit from negative to positive on 2024 holdout
- **D-12:** Ablation test: run holdout with ensemble + Phase 31 features vs ensemble without Phase 31 features -- ship whichever is better
- **D-13:** Final comparison table shows three columns: v1.4 baseline, Phase-30 ensemble, Phase-31-full -- on ATS accuracy, O/U accuracy, MAE, profit, plus per-season breakdown
- **D-14:** Extend `backtest_predictions.py` with `--holdout` flag that restricts to 2024 and prints the comparison table -- no one-off script

### Claude's Discretion
- Exact EWM column naming convention (e.g., `_ewm3` suffix)
- How to structure the ablation in code (separate config or inline toggle)
- Whether to re-run feature selection as a subprocess or inline call
- Test organization for momentum and EWM features

### Deferred Ideas (OUT OF SCOPE)
- Bayesian stacking (replace Ridge with Bayesian Ridge) -- future enhancement
- Regime detection (pre/post bye, playoff mode) -- could be its own phase
- Pace-adjusted stats -- requires additional data modeling
- In-season model retraining -- v3.0 production infra
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADV-01 | Add momentum/streak signals (win streak, ATS trend) from schedule data | Momentum features computed from Bronze schedules via `_read_bronze_schedules()`, shift(1) lag, integrated into `assemble_game_features()` before schedule join |
| ADV-02 | Implement adaptive EWM windows (halflife-based) alongside fixed rolling windows | EWM added to `apply_team_rolling()` in `team_analytics.py` with `_ewm3` suffix, `get_feature_columns()` updated to recognize EWM pattern |
| ADV-03 | Validate marginal improvement of advanced features on holdout | Three-way comparison via `--holdout` flag on `backtest_predictions.py`, ablation via separate ensemble training with/without Phase 31 features |
</phase_requirements>

## Architecture Patterns

### Where Momentum Features Live

Momentum features are derived from Bronze schedule data (game results, spread lines). They should be computed in `feature_engineering.py` inside `assemble_game_features()`, between step 1 (team feature assembly) and step 6 (schedule join for labels). This keeps them in the feature assembly pipeline rather than the Silver transformation layer, because they are game-result-derived features that need the schedule join context.

**Pipeline location:**
```
assemble_game_features():
  Step 1: Load Silver team features (existing)
  Step 2: Split home/away (existing)
  Step 3: Join home/away on game_id (existing)
  Step 4: Compute differentials (existing)
  NEW: Compute momentum features from Bronze schedules, shift(1), merge into game_df
  Step 5: Context columns (existing)
  Step 6: Join Bronze schedules for labels (existing)
```

### Momentum Feature Computation Pattern

```python
def _compute_momentum_features(season: int) -> pd.DataFrame:
    """Compute team-level momentum features from Bronze schedules.

    Returns per-team-per-week DataFrame with:
    - win_streak: signed consecutive W/L count (positive=winning, negative=losing)
    - ats_cover_sum3: rolling sum of ATS covers over last 3 games
    - ats_margin_avg3: rolling mean of ATS margin over last 3 games

    All features use shift(1) to prevent same-game leakage.
    """
    schedules = _read_bronze_schedules(season)
    if schedules.empty:
        return pd.DataFrame()

    # Reshape to per-team rows (each game produces two rows: home and away)
    home = schedules.assign(
        team=schedules["home_team"],
        won=(schedules["result"] > 0).astype(int),
        ats_cover=(schedules["result"] > schedules["spread_line"]).astype(int),
        ats_margin=schedules["result"] - schedules["spread_line"],
    )[["game_id", "season", "week", "team", "won", "ats_cover", "ats_margin"]]

    away = schedules.assign(
        team=schedules["away_team"],
        won=(schedules["result"] < 0).astype(int),
        ats_cover=(-schedules["result"] > -schedules["spread_line"]).astype(int),
        ats_margin=-schedules["result"] + schedules["spread_line"],
    )[["game_id", "season", "week", "team", "won", "ats_cover", "ats_margin"]]

    team_games = pd.concat([home, away]).sort_values(["team", "season", "week"])

    # Win streak (signed counter, resets on opposite result)
    # ... groupby team/season, compute streak with shift(1)

    # Rolling ATS features with shift(1)
    g = team_games.groupby(["team", "season"])
    team_games["ats_cover_sum3"] = g["ats_cover"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).sum()
    )
    team_games["ats_margin_avg3"] = g["ats_margin"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )

    return team_games
```

**Critical note on `result` column semantics:** In nflverse schedules, `result` = `home_score - away_score`. Positive means home win. `spread_line` is the home team spread (positive = home favored). So ATS cover for home team = `result > spread_line`.

### EWM Column Placement in `apply_team_rolling()`

```python
# Inside apply_team_rolling(), after existing rolling loop:

# EWM (exponentially weighted mean) with halflife=3
ewm_cols = {}
for col in available_cols:
    ewm_cols[f"{col}_ewm3"] = (
        df.groupby(["team", "season"])[col]
        .transform(lambda s: s.shift(1).ewm(halflife=3, min_periods=1).mean())
    )
df = df.assign(**ewm_cols)
```

### Leakage Guard Update (CRITICAL)

The `_is_rolling()` function in `get_feature_columns()` must be updated to recognize EWM columns:

```python
def _is_rolling(col: str) -> bool:
    """Check if column is a properly lagged rolling/EWM feature."""
    return "roll3" in col or "roll6" in col or "std" in col or "ewm3" in col
```

Momentum features (win_streak, ats_cover_sum3, ats_margin_avg3) need to be added to `_PRE_GAME_CUMULATIVE` since they are pre-game knowable cumulative stats:

```python
_PRE_GAME_CUMULATIVE = {
    "wins", "losses", "ties", "win_pct", "division_rank",
    "games_behind_division_leader", "ref_penalties_per_game",
    "backup_qb_start",
    # Phase 31 momentum features
    "win_streak", "ats_cover_sum3", "ats_margin_avg3",
}
```

### Three-Way Holdout Comparison Design

Extend `backtest_predictions.py` with `--holdout` flag. When set, restrict evaluation to 2024 season and print a three-column comparison table:

| Metric | v1.4 XGBoost | Phase-30 Ensemble | Phase-31 Full |
|--------|-------------|-------------------|---------------|
| ATS Accuracy | X% | X% | X% |
| O/U Accuracy | X% | X% | X% |
| MAE | X.XX | X.XX | X.XX |
| Profit (units) | +X.XX | +X.XX | +X.XX |
| ROI | +X.X% | +X.X% | +X.X% |

This requires loading three model configurations and running predictions for each on the same 2024 data.

### Ablation Structure

Recommend an inline toggle approach rather than separate config. The ablation runs two ensemble trainings:
1. Ensemble with Phase 31 features (full candidate set including momentum + EWM)
2. Ensemble without Phase 31 features (original Phase 30 candidate set)

Feature selection re-run (D-10) naturally handles this: run feature selection twice (once with expanded features, once with original features) and compare holdout results. The ensemble metadata already stores `selected_features`, so loading different ensemble artifacts provides the ablation.

### EWM Column Naming Convention

Recommend `_ewm3` suffix (matching the halflife=3 parameter). Examples:
- `off_epa_per_play_ewm3`
- `success_rate_ewm3`
- `cpoe_ewm3`
- `rz_td_rate_ewm3`

This parallels `_roll3` / `_roll6` / `_std` and naturally passes the updated `_is_rolling()` check.

### Anti-Patterns to Avoid
- **Computing momentum in Silver layer:** Momentum features are game-result-derived (from labels), NOT play-by-play derived. They belong in feature_engineering.py, not team_analytics.py.
- **Using shift(0) or no shift on momentum:** Every momentum feature MUST use shift(1) to prevent same-game leakage.
- **Modifying existing roll3/roll6 columns:** EWM supplements, never replaces. Feature selection will prune redundant ones.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| EWM computation | Custom exponential weighting | `pandas.DataFrame.ewm(halflife=3)` | Numerically stable, handles edge cases, well-tested |
| Win streak logic | Complex state machine | Simple groupby + cumsum with reset | Pandas groupby transform handles the per-team grouping cleanly |
| Feature selection re-run | Manual feature filtering | Existing `scripts/run_feature_selection.py` | Already handles SHAP + correlation + holdout guard |
| Comparison table formatting | Custom string formatting | Extend existing `run_comparison_backtest()` | Already has side-by-side format, just add third column |

## Common Pitfalls

### Pitfall 1: Leakage Guard Blocks New Features
**What goes wrong:** New EWM columns (e.g., `off_epa_per_play_ewm3`) silently fail the `_is_rolling()` check in `get_feature_columns()` and are excluded from the feature set. Model trains without them; no error, just missing features.
**Why it happens:** `_is_rolling()` only checks for `roll3`, `roll6`, and `std` substrings.
**How to avoid:** Update `_is_rolling()` to include `ewm3` BEFORE computing or testing EWM features.
**Warning signs:** Feature count doesn't increase after adding EWM columns.

### Pitfall 2: Momentum Feature Computed After Schedule Join
**What goes wrong:** If momentum features are computed in the schedule join step (step 6), they could include the current game's result, causing leakage.
**Why it happens:** The schedule data includes the current game's score and spread line.
**How to avoid:** Compute momentum features as a separate step with explicit shift(1), merge by team+season+week BEFORE the schedule label join.
**Warning signs:** Suspiciously high ATS accuracy on training data.

### Pitfall 3: ATS Margin Sign Convention
**What goes wrong:** `result` column in nflverse is `home_score - away_score`. For the away team, ATS margin must be negated. Getting this wrong means away team momentum features are inverted.
**Why it happens:** Forgetting to flip signs when reshaping schedules to per-team rows.
**How to avoid:** Explicitly compute away-team ATS margin as `-result + spread_line` (or equivalently `-(result - spread_line)`).
**Warning signs:** Away-team momentum features show inverse correlation with expected behavior.

### Pitfall 4: Feature Explosion from EWM
**What goes wrong:** Adding EWM to ALL stat columns in all Silver sources produces hundreds of new features, exceeding the 150-feature budget.
**Why it happens:** `apply_team_rolling()` is called by 5 Silver computation functions, each with 10-30 stat columns.
**How to avoid:** Per D-09, restrict EWM to specific metrics: EPA, success rate, CPOE, red zone. Add a parameter to `apply_team_rolling()` to control which columns get EWM treatment, or apply EWM selectively in a post-processing step.
**Warning signs:** Feature count jumps by 200+ after adding EWM.

### Pitfall 5: Ensemble Metadata Mismatch
**What goes wrong:** Phase 31 ensemble trained with new features but `predict_ensemble()` loads Phase 30 metadata with old feature list.
**Why it happens:** Ensemble metadata is saved per-training run. If you retrain only some models, metadata can be stale.
**How to avoid:** Always retrain the full ensemble pipeline when features change (per Phase 30 design: metadata.json stores the definitive feature list).
**Warning signs:** Missing feature warnings during prediction.

### Pitfall 6: Win Streak Reset Logic Off-by-One
**What goes wrong:** Streak counter includes the current game or resets one game too late.
**Why it happens:** Shift(1) must be applied AFTER computing the streak, not before.
**How to avoid:** Compute streak on unshifted data, then shift(1) the final streak column.
**Warning signs:** Streak of 1 after a loss when it should be 0 (or vice versa).

## Code Examples

### EWM in apply_team_rolling()

```python
# Source: pandas official docs + existing apply_team_rolling pattern
def apply_team_rolling(
    df: pd.DataFrame,
    stat_cols: List[str],
    windows: Optional[List[int]] = None,
    ewm_cols: Optional[List[str]] = None,
    ewm_halflife: int = 3,
) -> pd.DataFrame:
    """Apply shifted rolling averages, expanding average, and EWM by team.

    Args:
        df: Team-level weekly stats with team, season, week columns.
        stat_cols: Columns for rolling windows.
        windows: Rolling window sizes (default: [3, 6]).
        ewm_cols: Subset of stat_cols to also compute EWM for. None = skip EWM.
        ewm_halflife: Halflife parameter for EWM (default: 3).
    """
    # ... existing rolling logic ...

    # EWM (exponentially weighted mean)
    if ewm_cols:
        available_ewm = [c for c in ewm_cols if c in df.columns]
        ewm_data = {}
        for col in available_ewm:
            ewm_data[f"{col}_ewm{ewm_halflife}"] = (
                df.groupby(["team", "season"])[col]
                .transform(lambda s: s.shift(1).ewm(halflife=ewm_halflife, min_periods=1).mean())
            )
        df = df.assign(**ewm_data)

    return df
```

### Win Streak Computation

```python
# Compute signed win streak per team-season
def _compute_win_streak(series: pd.Series) -> pd.Series:
    """Compute running win/loss streak from a binary win series.

    Positive values = winning streak length, negative = losing streak length.
    """
    streaks = []
    current = 0
    for won in series:
        if won == 1:
            current = max(current, 0) + 1
        else:
            current = min(current, 0) - 1
        streaks.append(current)
    return pd.Series(streaks, index=series.index)

# Apply per team-season group, then shift(1)
team_games["win_streak_raw"] = team_games.groupby(["team", "season"])["won"].transform(
    _compute_win_streak
)
team_games["win_streak"] = team_games.groupby(["team", "season"])["win_streak_raw"].shift(1)
```

### Holdout Comparison Table

```python
def print_holdout_comparison(
    xgb_results: pd.DataFrame,
    ens_results: pd.DataFrame,
    full_results: pd.DataFrame,
    holdout_season: int = 2024,
) -> None:
    """Print three-way comparison table for holdout season."""
    configs = {
        "v1.4 XGBoost": xgb_results,
        "Phase-30 Ensemble": ens_results,
        "Phase-31 Full": full_results,
    }

    print(f"\n{'=' * 72}")
    print(f"SEALED HOLDOUT -- {holdout_season} Season")
    print(f"{'=' * 72}")
    print(f"  {'Metric':<18} {'v1.4 XGB':>14} {'P30 Ensemble':>14} {'P31 Full':>14}")
    print(f"  {'-' * 60}")

    for label, results in configs.items():
        holdout = results[results["season"] == holdout_season]
        # ... compute and display metrics ...
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | None (pytest runs from project root) |
| Quick run command | `python -m pytest tests/test_feature_engineering.py tests/test_team_analytics.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADV-01 | Momentum features (win_streak, ats_cover_sum3, ats_margin_avg3) present with shift(1) lag | unit | `python -m pytest tests/test_feature_engineering.py::TestMomentumFeatures -x` | No -- Wave 0 |
| ADV-01 | Momentum features pass get_feature_columns() leakage guard | unit | `python -m pytest tests/test_feature_engineering.py::TestMomentumFeatures::test_momentum_in_feature_cols -x` | No -- Wave 0 |
| ADV-02 | EWM columns computed alongside roll3/roll6 with shift(1) | unit | `python -m pytest tests/test_team_analytics.py::TestEWMRolling -x` | No -- Wave 0 |
| ADV-02 | EWM columns recognized by get_feature_columns() | unit | `python -m pytest tests/test_feature_engineering.py::TestEWMFeatures -x` | No -- Wave 0 |
| ADV-03 | --holdout flag on backtest_predictions.py produces three-way comparison | integration | `python -m pytest tests/test_prediction_backtester.py::TestHoldoutComparison -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_feature_engineering.py tests/test_team_analytics.py tests/test_prediction_backtester.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_feature_engineering.py::TestMomentumFeatures` -- covers ADV-01 momentum feature computation and leakage guard
- [ ] `tests/test_team_analytics.py::TestEWMRolling` -- covers ADV-02 EWM computation
- [ ] `tests/test_feature_engineering.py::TestEWMFeatures` -- covers ADV-02 EWM in feature columns
- [ ] `tests/test_prediction_backtester.py::TestHoldoutComparison` -- covers ADV-03 three-way comparison

## Open Questions

1. **Which specific stat columns get EWM treatment?**
   - What we know: D-09 says EPA, success rate, CPOE, red zone only. These exist in Silver PBP metrics.
   - What's unclear: Exact column names in the Silver data (e.g., `off_epa_per_play`, `off_success_rate`, `cpoe`, `rz_td_rate`).
   - Recommendation: Inspect Silver PBP metrics parquet to confirm exact column names. Define a constant list like `EWM_TARGET_COLS` in config.py.

2. **Ablation storage: separate ensemble directory or same?**
   - What we know: Need two ensemble configurations for ablation (with and without Phase 31 features).
   - What's unclear: Whether to save to `models/ensemble_ablation/` or overwrite `models/ensemble/`.
   - Recommendation: Save Phase 31 ensemble to `models/ensemble/` (the default) and keep Phase 30 ensemble backed up or re-trainable. The comparison needs both to coexist temporarily.

## Sources

### Primary (HIGH confidence)
- `src/feature_engineering.py` -- `assemble_game_features()`, `get_feature_columns()`, `_is_rolling()`, `_PRE_GAME_CUMULATIVE`
- `src/team_analytics.py` -- `apply_team_rolling()` pattern (lines 67-128)
- `scripts/backtest_predictions.py` -- `run_comparison_backtest()`, CLI argument structure
- `src/prediction_backtester.py` -- `evaluate_ats()`, `evaluate_holdout()`, `compute_profit()`
- `src/config.py` -- `HOLDOUT_SEASON=2024`, `SELECTED_FEATURES`, `LABEL_COLUMNS`
- Bronze schedules schema: verified columns include `result`, `spread_line`, `total_line`, `home_team`, `away_team`, `home_score`, `away_score`
- pandas ewm documentation: `DataFrame.ewm(halflife=N, min_periods=1).mean()` is the standard API

### Secondary (MEDIUM confidence)
- nflverse schedule conventions: `result` = home_score - away_score, `spread_line` positive = home favored (verified from Bronze data sample)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries needed, all pandas/numpy/existing ML stack
- Architecture: HIGH -- patterns copied directly from existing codebase (rolling windows, feature assembly, comparison backtest)
- Pitfalls: HIGH -- leakage guard issue confirmed by reading `_is_rolling()` source code; sign convention verified from Bronze data

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable codebase, no external dependency changes)
