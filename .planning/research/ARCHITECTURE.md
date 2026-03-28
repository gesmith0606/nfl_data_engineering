# Architecture: Full Odds Ingestion + Holdout Reset

**Domain:** Extending odds data coverage (2016-2021 full, 2022+ sources) and resetting holdout evaluation framework
**Researched:** 2026-03-28
**Confidence:** HIGH (based on direct inspection of existing codebase: bronze_odds_ingestion.py, market_analytics.py, feature_engineering.py, ensemble_training.py, prediction_backtester.py, config.py)

## Current Architecture (What Exists)

```
Bronze (data/bronze/)
  odds/season=2020/             <-- ONLY season 2020 ingested from FinnedAI
  schedules/season=YYYY/        <-- spread_line, total_line (CLOSING lines, all seasons)
  [14 other data types]
       |
       v
Silver (data/silver/)
  teams/market_data/season=YYYY/<-- line movement features (only 2020)
  teams/game_context/           <-- BASE for all Silver joins
  [8 other Silver paths]
       |
       v  (joined on [team, season, week] via _assemble_team_features())
       v  (split home/away, differenced into game-level features)
       |
Gold (feature vector)
  310+ columns, ~100 after SHAP selection
  opening_spread, opening_total in _PRE_GAME_CONTEXT (safe)
  closing-line features EXCLUDED (retrospective leakage)
       |
       v
Ensemble (models/ensemble/)
  HOLDOUT_SEASON = 2024 (sealed)
  TRAINING_SEASONS = 2016-2023
  VALIDATION_SEASONS = [2019, 2020, 2021, 2022, 2023]
  Walk-forward CV: train on seasons < val_season
  Result: 53.0% ATS, +$3.09 on 2024 holdout
```

### Critical Observation: Market Data Gap

FinnedAI covers 2016-2021, but only season 2020 was ingested during v2.1. The existing `bronze_odds_ingestion.py` already supports `--season` for individual seasons AND `SEASONS = list(range(2016, 2022))` for all-at-once processing. The code, team mapping, NewYork disambiguation, and validation pipeline are fully built -- this is a "run it more times" problem, not a "build new things" problem.

For the training window (2016-2023), market features are currently NaN for 2016-2019 and 2022-2023. The model handles this via tree-based NaN routing, but filling these gaps would give the ensemble actual signal instead of fallback paths.

## Target Architecture (v2.2)

```
Bronze (data/bronze/)
  odds/season=2016/   NEW - FinnedAI batch
  odds/season=2017/   NEW - FinnedAI batch
  odds/season=2018/   NEW - FinnedAI batch
  odds/season=2019/   NEW - FinnedAI batch
  odds/season=2020/   EXISTS
  odds/season=2021/   NEW - FinnedAI batch
  odds/season=2022/   NEW - nflverse-derived or paid API
  odds/season=2023/   NEW - nflverse-derived or paid API
  odds/season=2024/   NEW - nflverse-derived or paid API (holdout)
  odds/season=2025/   NEW - nflverse-derived or paid API (new holdout)
       |
       v
Silver (data/silver/)
  teams/market_data/season=2016-2025/  <-- full coverage
       |
       v
Gold (feature vector)
  opening_spread, opening_total: NON-NULL for all training + holdout seasons
       |
       v
Ensemble (models/ensemble/)
  HOLDOUT_SEASON = 2025 (NEW sealed holdout)
  TRAINING_SEASONS = 2016-2024 (2024 unsealed, added to training)
  VALIDATION_SEASONS = [2020, 2021, 2022, 2023, 2024] (shifted forward)
  Baseline: retrain P30 ensemble on expanded data, evaluate on 2025
```

## Component Changes: New vs Modified

### New Components (0)

No entirely new modules are needed. The existing architecture handles all required data flows.

### Modified Components

| Component | File | Change Type | What Changes |
|-----------|------|-------------|--------------|
| Config constants | `src/config.py` | **Modify** | `HOLDOUT_SEASON = 2025`, `TRAINING_SEASONS = 2016-2024`, `VALIDATION_SEASONS = [2020..2024]`, `PREDICTION_SEASONS = 2016-2025`, odds season range `2016-2025` |
| Config: data source registry | `src/config.py` | **Modify** | `DATA_TYPE_SEASON_RANGES["odds"]` upper bound from `2021` to `2025` (if 2022+ data available) |
| Bronze odds ingestion | `scripts/bronze_odds_ingestion.py` | **Minor modify** | Add nflverse-derived odds fallback for 2022+ seasons (new function) |
| Silver market transformation | `scripts/silver_market_transformation.py` | **No change** | Already processes any season with Bronze odds data |
| Market analytics | `src/market_analytics.py` | **No change** | Pure computation, season-agnostic |
| Feature engineering | `src/feature_engineering.py` | **No change** | Already joins market_data via `SILVER_TEAM_LOCAL_DIRS`, NaN-tolerant |
| Ensemble training | `src/ensemble_training.py` | **No change** | Reads `HOLDOUT_SEASON` and `VALIDATION_SEASONS` from config |
| Prediction backtester | `src/prediction_backtester.py` | **No change** | Reads `HOLDOUT_SEASON` from config |
| Feature selector | `src/feature_selector.py` | **No change** | Reads `HOLDOUT_SEASON` from config |
| Model training | `src/model_training.py` | **No change** | Reads `HOLDOUT_SEASON` from config |
| Ablation script | `scripts/ablation_market_features.py` | **No change** | Reads from config |
| Tests | `tests/` | **Modify** | Update hardcoded `2024` holdout references in test assertions |

### Key Insight: Config-Driven Holdout Reset

The holdout guard is centralized in `src/config.py` via `HOLDOUT_SEASON = 2024`. Every module imports this constant. Changing it to `2025` propagates the holdout boundary everywhere automatically:

- `ensemble_training.py` line 349: `train_data = all_data[all_data["season"] < HOLDOUT_SEASON]`
- `ensemble_training.py` line 136: `if val_season == HOLDOUT_SEASON: raise ValueError(...)`
- `prediction_backtester.py` line 179: `holdout_season: int = HOLDOUT_SEASON`
- `feature_selector.py` line 65: `if HOLDOUT_SEASON in data["season"].values: raise ValueError(...)`
- `model_training.py` line 90: `if val_season == HOLDOUT_SEASON: raise ValueError(...)`

This is a one-line change with system-wide effect. The risk is in tests that assert specific season numbers.

## Data Flow: Full Odds Ingestion (2016-2021)

```
FinnedAI JSON (already downloaded: data/raw/sbro/nfl_archive_10Y.json)
    |
    v  parse_finnedai(json_path, seasons=[2016,2017,2018,2019,2021])
    |  (2020 already exists, skip)
    v  resolve_newyork() -> align_spreads() -> join_to_nflverse()
    |  validate_cross_correlation() + validate_sign_convention()
    v
data/bronze/odds/season={2016..2021}/odds_TIMESTAMP.parquet
    |
    v  silver_market_transformation.py --seasons 2016 2017 2018 2019 2020 2021
    |  compute_movement_features() -> reshape_to_per_team()
    v
data/silver/teams/market_data/season={2016..2021}/market_data_TIMESTAMP.parquet
```

This is entirely mechanical -- the code exists, the data source is already downloaded, the pipeline is proven on season 2020. The JSON contains 2011-2021, but the `validate_season_for_type("odds", season)` guard limits to 2016-2021 (matching nflverse schedule coverage for cross-validation).

## Data Flow: 2022+ Odds Sourcing

This is the harder problem. Three options, in order of preference:

### Option A: nflverse-Derived Opening Lines (Recommended)

nflverse `import_schedules()` provides `spread_line` and `total_line` for all seasons (these are **closing** lines). For 2022+, we can synthesize a minimal odds record:

```python
def derive_odds_from_nflverse(season: int) -> pd.DataFrame:
    """Create Bronze-compatible odds from nflverse schedules.

    Uses closing lines as both opening and closing (no movement data).
    This gives opening_spread/opening_total for the feature vector
    even though spread_shift/total_shift will be 0.
    """
    sched = nfl.import_schedules([season])
    return pd.DataFrame({
        "game_id": sched["game_id"],
        "season": season,
        "week": sched["week"],
        "game_type": sched["game_type"],
        "home_team": sched["home_team"],
        "away_team": sched["away_team"],
        "opening_spread": sched["spread_line"],   # closing as proxy
        "closing_spread": sched["spread_line"],
        "opening_total": sched["total_line"],
        "closing_total": sched["total_line"],
        "home_moneyline": sched.get("home_moneyline", np.nan),
        "away_moneyline": sched.get("away_moneyline", np.nan),
        "nflverse_spread_line": sched["spread_line"],
        "nflverse_total_line": sched["total_line"],
    })
```

**Trade-off:** Line movement features (spread_shift, total_shift, magnitude buckets, key crossings) will all be zero/null for 2022+. But `opening_spread` and `opening_total` -- the only two features that actually enter the prediction model via `_PRE_GAME_CONTEXT` -- will be populated.

**Why this is acceptable:** The model already treats closing-line-derived features as retrospective (excluded from `_PRE_GAME_CONTEXT`). Only `opening_spread` and `opening_total` feed the ensemble. Using closing lines as a proxy for opening lines introduces ~1-2 point noise (typical line movement), but this is far better than NaN for 3 seasons of training data.

### Option B: The Odds API (Paid, Historical)

The Odds API offers historical odds data including opening and closing lines from multiple bookmakers. Covers 2022+ with proper opening/closing separation. Requires paid subscription ($79/month for historical access).

**When to use:** Only if ablation proves that line movement features (not just opening_spread/opening_total) materially improve holdout accuracy. The v2.1 ablation already showed market features did NOT improve the sealed holdout, so this is unlikely to be worth the cost.

### Option C: Kaggle NFL Betting Dataset

The Kaggle "NFL Scores and Betting Data" dataset (by Toby Crabtree) provides historical NFL betting data. Coverage and recency need verification, but it may bridge the 2022-2024 gap as a free alternative.

**Recommendation:** Start with Option A (nflverse-derived). It requires zero new dependencies, zero cost, and fills the gap in the feature vector. If future ablation shows line movement features matter, revisit Option B.

## Data Flow: Holdout Reset

```
BEFORE (v2.1):
  HOLDOUT_SEASON = 2024  (sealed)
  TRAINING_SEASONS = [2016, 2017, ..., 2023]
  VALIDATION_SEASONS = [2019, 2020, 2021, 2022, 2023]

AFTER (v2.2):
  HOLDOUT_SEASON = 2025  (newly sealed)
  TRAINING_SEASONS = [2016, 2017, ..., 2024]  (+1 year of data)
  VALIDATION_SEASONS = [2020, 2021, 2022, 2023, 2024]  (shifted +1)
  PREDICTION_SEASONS = [2016, 2017, ..., 2025]  (+1 year)
```

### Holdout Reset Procedure

1. **Verify 2025 data availability:** Check that Bronze schedules for season 2025 exist with final scores (`home_score`, `away_score` not null), `spread_line` and `total_line` populated. Without completed 2025 games, there is no holdout to evaluate against.

2. **Update config.py:** Single-line changes to `HOLDOUT_SEASON`, `TRAINING_SEASONS`, `VALIDATION_SEASONS`, `PREDICTION_SEASONS`.

3. **Ingest 2025 Bronze data:** Ensure all 16 Bronze types have 2025 data (schedules, PBP, player_weekly, etc.). Most should already exist from v1.1 backfill infrastructure.

4. **Run Silver transformations:** All 10 Silver paths for season 2025. This is the most work but it is all existing code: `silver_team_transformation.py`, `silver_player_transformation.py`, `silver_game_context_transformation.py`, etc.

5. **Ingest 2025 odds:** Use Option A (nflverse-derived) for 2025, then run `silver_market_transformation.py --seasons 2025`.

6. **Assemble features:** `feature_engineering.py` already handles any season with Silver data.

7. **Retrain ensemble:** `scripts/train_ensemble.py` with updated config. The ensemble automatically trains on `season < HOLDOUT_SEASON` (now 2025 instead of 2024).

8. **Baseline evaluation:** `scripts/backtest_predictions.py --holdout` evaluates on the new 2025 holdout.

### Timing Constraint

The 2025 NFL regular season runs September 2025 through January 2026. The season is complete (March 2026), so 2025 holdout data should be available. However, nfl-data-py may not yet have full 2025 PBP/stats data. This needs verification before committing to 2025 as holdout.

## Integration Points

### Internal Boundaries

| Boundary | Communication | Direction | Notes |
|----------|---------------|-----------|-------|
| Bronze odds -> Silver market | Parquet file read | silver_market_transformation reads bronze odds | Season-partitioned, latest-file convention |
| Silver market -> Feature engineering | Parquet file read via `_read_latest_local()` | feature_engineering reads `teams/market_data/` | Left join on [team, season, week], NaN-safe |
| Config -> All ML modules | Python import | `HOLDOUT_SEASON` flows to ensemble, backtester, selector | One constant, many consumers |
| Config -> Bronze ingestion | Python import | `DATA_TYPE_SEASON_RANGES["odds"]` validates seasons | Must update upper bound if adding 2022+ |

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| FinnedAI GitHub JSON | HTTPS download, cached locally | Already downloaded at `data/raw/sbro/nfl_archive_10Y.json` |
| nflverse schedules | `nfl.import_schedules([season])` | Required for cross-validation join AND Option A fallback |
| nflverse PBP/stats | `nfl.import_pbp_data()` etc. | Required for 2025 Bronze/Silver pipeline |

## Architectural Patterns

### Pattern 1: Config-Driven Holdout Guard

**What:** All holdout enforcement flows from `HOLDOUT_SEASON` in `config.py`. No module hardcodes the season number.

**When to use:** Anytime the holdout boundary changes.

**Trade-offs:** Clean separation, but tests may hardcode season numbers in assertions. Grep for `2024` in test files before changing.

### Pattern 2: Schema-Compatible Fallback Data

**What:** For 2022+ odds, generate Bronze Parquet files with the exact same schema as FinnedAI-derived files, but with closing lines as opening line proxies.

**When to use:** When a data source covers a subset of seasons and you need to fill gaps with a degraded-but-schema-compatible alternative.

**Trade-offs:** Downstream code sees no schema differences. Line movement features become trivially zero (no movement when open == close), but the features that actually enter the model (`opening_spread`, `opening_total`) are populated. The model does not know the difference.

### Pattern 3: Idempotent Season-Partitioned Ingestion

**What:** The existing `bronze_odds_ingestion.py` writes to `data/bronze/odds/season=YYYY/odds_TIMESTAMP.parquet`. Running it again for the same season produces a new timestamped file. The latest-file convention (`sorted(glob)[-1]`) always picks the newest.

**When to use:** Re-running ingestion for corrections or additions.

**Trade-offs:** Accumulates files. No destructive overwrites. Disk usage is minimal (odds data is small).

## Anti-Patterns

### Anti-Pattern 1: Hardcoding Holdout Season in Tests

**What people do:** Write `assert holdout_season == 2024` or `assert 2024 not in training_seasons` in test files.

**Why it's wrong:** Breaks when holdout rotates. The whole point of centralized config is to avoid this.

**Do this instead:** Import `HOLDOUT_SEASON` from config in tests: `assert holdout_season == HOLDOUT_SEASON`.

### Anti-Pattern 2: Mixing Opening and Closing Lines Without Flagging

**What people do:** Use nflverse closing lines as "opening" lines without documenting the approximation.

**Why it's wrong:** Creates silent data quality degradation. Someone later runs an ablation on "opening line movement" and gets zero signal for 2022+.

**Do this instead:** Add a `line_source` column to Bronze odds: `"finnedai"` for 2016-2021, `"nflverse_proxy"` for 2022+. Downstream can filter or flag.

### Anti-Pattern 3: Unsealing Holdout Without Establishing New Baseline

**What people do:** Change `HOLDOUT_SEASON` to 2025 and immediately start tuning, without first recording the baseline ensemble performance on the new holdout.

**Why it's wrong:** No reference point. You cannot tell if changes improve or regress.

**Do this instead:** Step 1: change config. Step 2: retrain P30 ensemble on expanded training data. Step 3: evaluate on 2025 holdout. Step 4: record baseline. Step 5: then tune.

## Suggested Build Order

Based on dependency analysis:

```
Phase 1: Full FinnedAI Ingestion (2016-2021)
  No code changes needed -- run existing scripts
  Depends on: nothing (JSON already downloaded)
  Output: Bronze odds for 6 seasons instead of 1
  Risk: LOW (proven pipeline)
     |
     v
Phase 2: Silver Market Expansion + 2022+ Odds
  Add nflverse-derived odds function to bronze_odds_ingestion.py
  Run silver_market_transformation.py for all seasons
  Update DATA_TYPE_SEASON_RANGES if needed
  Depends on: Phase 1 (for 2016-2021 Bronze odds)
  Output: Silver market data for all training seasons
  Risk: LOW (nflverse fallback) to MEDIUM (schema alignment)
     |
     v
Phase 3: Holdout Reset + Baseline
  Update config.py constants (HOLDOUT_SEASON, TRAINING_SEASONS, etc.)
  Verify 2025 data availability
  Ensure full Bronze/Silver pipeline for 2024-2025
  Retrain ensemble, establish baseline on 2025 holdout
  Update tests with config-based assertions
  Depends on: Phase 2 (full market data coverage)
  Output: New baseline metrics on 2025 holdout
  Risk: MEDIUM (2025 data availability, test updates)
```

## Scaling Considerations

| Concern | Current (1 season odds) | After v2.2 (10 seasons) |
|---------|------------------------|------------------------|
| Bronze odds disk usage | ~50 KB | ~500 KB (trivial) |
| Silver market disk usage | ~100 KB | ~1 MB (trivial) |
| Feature vector width | 310+ cols (unchanged) | 310+ cols (unchanged) |
| Training data rows | ~2,000 games (2016-2023) | ~2,300 games (2016-2024) |
| Ensemble training time | ~5 minutes | ~6 minutes (linear in rows) |
| Feature selection time | ~10 minutes | ~12 minutes |

No scaling concerns. The data is small and the pipeline is fast.

## Sources

- Direct codebase inspection: `scripts/bronze_odds_ingestion.py`, `src/market_analytics.py`, `src/feature_engineering.py`, `src/ensemble_training.py`, `src/prediction_backtester.py`, `src/config.py`
- [FinnedAI sportsbookreview-scraper](https://github.com/FinnedAI/sportsbookreview-scraper) -- source JSON covers 2011-2021
- [nflverse nfl_data_py](https://github.com/nflverse/nfl_data_py) -- schedules with spread_line/total_line
- [nflverse schedules documentation](https://nflreadr.nflverse.com/reference/load_schedules.html) -- field definitions
- [The Odds API Historical Data](https://the-odds-api.com/historical-odds-data/) -- paid 2022+ option
- [Kaggle NFL Scores and Betting Data](https://www.kaggle.com/datasets/tobycrabtree/nfl-scores-and-betting-data) -- potential free 2022+ bridge

---
*Architecture research for: v2.2 Full Odds + Holdout Reset*
*Researched: 2026-03-28*
