# Stack Research: v2.2 Full Odds + Holdout Reset

**Domain:** NFL odds data expansion, holdout framework rotation
**Researched:** 2026-03-28
**Confidence:** HIGH

## Executive Assessment

**No new libraries are needed.** The v2.2 milestone is a data expansion and configuration change, not a technology change. Every tool required already exists in the project.

1. **Full 2016-2021 FinnedAI ingestion:** `bronze_odds_ingestion.py` already supports all 6 seasons. Only 2020 was run during v2.1. Run the remaining 5 seasons (2016-2019, 2021) with the existing `--season` flag.

2. **2022+ odds data:** The critical finding is that nflverse `import_schedules()` already provides closing lines (`spread_line`, `total_line`, moneylines) for ALL seasons including 2022-2025. These are already in Bronze schedules. The only gap is **opening lines** for 2022+, which FinnedAI does not cover. AusSportsBetting.com provides free XLSX data from 2006-present with a `home_line` field, but whether this is opening or closing is ambiguous. Since the v2.1 ablation showed market features (including opening lines) did not improve holdout accuracy, the pragmatic approach is to accept NaN opening lines for 2022+ and rely on nflverse closing lines only.

3. **Holdout reset:** Four constants in `src/config.py`. No code changes to training, backtesting, or prediction logic.

## Recommended Stack

### Core Technologies (Already Installed -- Zero Changes)

| Technology | Version | Purpose in v2.2 | Status |
|------------|---------|-----------------|--------|
| pandas | 1.5.3 | Parse FinnedAI JSON, XLSX if needed, DataFrame ops | Installed |
| pyarrow | 21.0.0 | Write Bronze odds Parquet per season | Installed |
| requests | 2.32.4 | Download FinnedAI JSON (one-time, cached) | Installed |
| scipy | 1.13.1 | `pearsonr` cross-validation of odds sources | Installed |
| nfl-data-py | 0.3.3 | `import_schedules()` for nflverse join + closing lines | Installed |
| openpyxl | installed | XLSX parsing if AusSportsBetting source needed | Installed (added in v2.1) |
| xgboost | >=2.1.4 | Re-train ensemble on expanded training data | Installed |
| lightgbm | 4.6.0 | Re-train ensemble on expanded training data | Installed |
| catboost | 1.2.10 | Re-train ensemble on expanded training data | Installed |
| scikit-learn | >=1.5 | Ridge meta-learner, evaluation metrics | Installed |
| shap | 0.49.1 | Re-run feature selection with full market data | Installed |
| optuna | >=4.0 | Optional re-tune after data expansion | Installed |

### Supporting Libraries (Already Installed -- No Changes)

| Library | Version | v2.2 Use | When Needed |
|---------|---------|----------|-------------|
| json (stdlib) | N/A | Parse FinnedAI `nfl_archive_10Y.json` | Full ingestion of remaining seasons |
| os/datetime (stdlib) | N/A | File paths, timestamps for Parquet naming | Every Bronze write |
| pickle (stdlib) | N/A | Model serialization during re-training | Ensemble save/load |

## What Changes (Configuration Only)

### src/config.py -- Holdout Reset

```python
# BEFORE (v2.1 -- current):
HOLDOUT_SEASON = 2024
TRAINING_SEASONS = list(range(2016, 2024))     # 2016-2023
VALIDATION_SEASONS = [2019, 2020, 2021, 2022, 2023]
PREDICTION_SEASONS = list(range(2016, 2025))   # 2016-2024

# AFTER (v2.2):
HOLDOUT_SEASON = 2025
TRAINING_SEASONS = list(range(2016, 2025))     # 2016-2024 (2024 unsealed)
VALIDATION_SEASONS = [2019, 2020, 2021, 2022, 2023, 2024]  # 2024 joins CV
PREDICTION_SEASONS = list(range(2016, 2026))   # 2016-2025
```

**Impact analysis:** These constants are consumed by:
- `ensemble_training.py` -- `HOLDOUT_SEASON` excluded from training, `VALIDATION_SEASONS` define walk-forward folds
- `prediction_backtester.py` -- `evaluate_holdout()` uses `HOLDOUT_SEASON` for sealed evaluation
- `scripts/train_ensemble.py` -- reads config for training boundaries
- `scripts/backtest_predictions.py --holdout` -- reads config for holdout season
- `scripts/ablation_market_features.py` -- reads config for holdout comparison

No code logic changes needed. The framework is already parameterized.

### scripts/bronze_odds_ingestion.py -- No Code Changes

The script already supports:
- `--season 2016` through `--season 2021` (individual seasons)
- No `--season` flag processes all 2016-2021 (default `SEASONS = list(range(2016, 2022))`)
- The FinnedAI JSON contains all 6 seasons; parsing filters by requested season

To complete full ingestion, simply run:
```bash
python scripts/bronze_odds_ingestion.py  # Processes all 2016-2021
```

## 2022+ Odds Data: Decision

### Recommended: Do NOT add a new data source for 2022+

**Rationale:**
1. **v2.1 ablation proved market features did not improve holdout accuracy.** The P30 ensemble (without market features) was shipped as production. Adding 2022+ opening lines serves research interest, not model improvement.
2. **nflverse already provides closing lines for 2022-2025.** The closing line is what CLV uses. CLV tracking works for all seasons without any new data.
3. **Opening lines for 2022+ are NaN in the feature vector.** Gradient boosting handles NaN natively. The ensemble trains on 2016-2024; with full FinnedAI coverage for 2016-2021, that is 6 seasons of opening line data for the model to learn from.
4. **Adding AusSportsBetting.com introduces a second team mapping, a second sign convention, a second schema, and a second validation pipeline.** Complexity for no proven benefit.

### If 2022+ Opening Lines Become Needed Later

| Source | Seasons | Cost | Effort | When |
|--------|---------|------|--------|------|
| AusSportsBetting.com XLSX | 2006-present | Free | Medium (new team mapping, XLSX parsing, validation) | If future ablation shows opening lines improve model |
| BigDataBall | 2016-present | ~$30/season | Medium (same integration pattern) | If AusSportsBetting data quality is poor |
| The Odds API | mid-2020+ | $99+/mo | Low (JSON API, well-documented) | If live/ongoing odds capture needed for v3.0+ |

## What NOT to Add

| Avoid | Why | What Exists Instead |
|-------|-----|---------------------|
| MLflow / W&B | Experiment tracking for holdout rotation is overkill. Config constants + git commits provide full audit trail. | `HOLDOUT_SEASON` in config.py, model metadata JSON in `models/` |
| Any paid odds API | Monthly cost for data the model has not been proven to need | nflverse closing lines (free, complete) |
| nflreadpy | Requires Python 3.10+; project pinned to 3.9 | nfl-data-py 0.3.3 |
| New ML libraries | Re-training uses identical ensemble architecture | XGB+LGB+CB+Ridge already installed |
| Database for odds (SQLite/DuckDB) | Pipeline is Parquet-native; DB adds complexity for no benefit | Parquet with `download_latest_parquet()` |
| AusSportsBetting.com integration | Second data source, second mapping, for a feature that failed ablation | FinnedAI for 2016-2021, nflverse for 2022+ closing lines |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| 2016-2021 opening lines | FinnedAI JSON (existing) | SBRO XLSX direct | FinnedAI is the same data pre-scraped; already validated with r=0.997 |
| 2022+ opening lines | Skip (NaN) | AusSportsBetting XLSX | Complexity for unproven benefit; revisit if ablation changes |
| 2022+ closing lines | nflverse schedules (existing) | The Odds API | nflverse is free, already ingested, and is the project's ground truth |
| Holdout management | Config constants | MLflow experiment tracking | Four constants vs. new infrastructure; git provides history |
| Ensemble re-training | Same architecture | Add new base learners | No evidence current architecture is the bottleneck |

## Stack Patterns by Variant

**If future ablation proves opening lines matter for 2022+:**
- Add AusSportsBetting.com XLSX parser as a new source in `bronze_odds_ingestion.py`
- Build team mapping dict (similar to existing `FINNEDAI_TO_NFLVERSE`)
- Cross-validate against nflverse closing lines (same `pearsonr > 0.95` gate)
- This is additive; no existing code changes

**If holdout reset reveals model degradation on 2025:**
- 2025 data may be incomplete (season in progress or just ended)
- Verify Bronze data coverage for 2025 before sealing
- Consider `HOLDOUT_SEASON = 2024` as fallback with expanded training through 2023

## Version Compatibility

| Package | Compatible With | Notes |
|---------|----------------|-------|
| pandas 1.5.3 | pyarrow 21.0.0 | Already validated across entire pipeline |
| pandas 1.5.3 | openpyxl (any recent) | `pd.read_excel(engine='openpyxl')` for XLSX |
| nfl-data-py 0.3.3 | Python 3.9 | Pinned; archived Sept 2025, last stable |
| scipy 1.13.1 | Python 3.9 | `pearsonr` for cross-validation |
| All ML libs | Python 3.9 | xgboost, lightgbm, catboost, sklearn all tested |

## Installation

```bash
# No new packages. Verify environment:
source venv/bin/activate
python -c "import pandas, pyarrow, scipy, xgboost, lightgbm, catboost; print('All deps OK')"

# Run full odds ingestion (existing script, no changes):
python scripts/bronze_odds_ingestion.py
# Processes all 2016-2021 seasons from FinnedAI JSON
```

## Integration Points

### Data Flow for Full Ingestion

```
FinnedAI JSON (already downloaded, cached at data/raw/sbro/nfl_archive_10Y.json)
    ↓ parse_finnedai() filters to season
    ↓ resolve_newyork() disambiguates NY teams
    ↓ align_spreads() negates for nflverse convention
    ↓ join_to_nflverse() inherits game_id, week
    ↓ validate_cross_correlation() asserts r > 0.95
Bronze odds Parquet (data/bronze/odds/season=YYYY/) -- 6 seasons
    ↓ silver_market_transformation.py (existing)
Silver market_data -- spread_shift, magnitude, key numbers
    ↓ feature_engineering.py (opening_spread, opening_total in _PRE_GAME_CONTEXT)
Ensemble re-training with full market coverage for 2016-2021
```

### Data Flow for Holdout Reset

```
src/config.py (change 4 constants)
    ↓ ensemble_training.py excludes 2025 from training
    ↓ train on 2016-2024 (was 2016-2023)
    ↓ evaluate on sealed 2025 holdout
    ↓ establish new ATS/profit baselines
Gold predictions -- new baseline metrics with 2025 holdout
```

## Sources

- [nflverse/nfl_data_py GitHub](https://github.com/nflverse/nfl_data_py) -- schedules include spread_line, total_line, moneylines for all seasons
- [nflreadr load_schedules docs](https://nflreadr.nflverse.com/reference/load_schedules.html) -- 46 columns including 7+ odds fields
- [FinnedAI/sportsbookreview-scraper](https://github.com/FinnedAI/sportsbookreview-scraper) -- existing source, 2016-2021 JSON, already validated
- [AusSportsBetting.com NFL Historical Data](https://www.aussportsbetting.com/data/historical-nfl-results-and-odds-data/) -- free XLSX, 2006-present, potential future source
- [The Odds API Historical](https://the-odds-api.com/historical-odds-data/) -- paid, $99+/mo, mid-2020+ coverage
- Existing codebase: `bronze_odds_ingestion.py`, `market_analytics.py`, `feature_engineering.py`, `config.py`, `ensemble_training.py`, `prediction_backtester.py`
- Project `requirements.txt` / `pip freeze` -- ground truth for installed packages

---
*Stack research for: v2.2 Full Odds + Holdout Reset*
*Researched: 2026-03-28*
