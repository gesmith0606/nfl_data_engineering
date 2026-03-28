# Feature Research

**Domain:** Full odds ingestion (all 2016-2021 seasons + 2022+ sourcing) and holdout framework reset for NFL game prediction
**Researched:** 2026-03-28
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features the prediction pipeline requires. Missing these = market features wasted or evaluation untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Full 2016-2021 FinnedAI ingestion (all 6 seasons) | Only 2020 ingested today; market features NaN for 5/6 available seasons -- wasted signal in training window | LOW | Script exists and is proven on 2020; supports `--season` for any 2016-2021; batch-run all 6 |
| Silver market data regeneration for 2016-2021 | Silver market_data exists only for 2020; feature vector needs all FinnedAI seasons | LOW | `silver_market_transformation.py` already works; run for each new Bronze season |
| Holdout season rotation: unseal 2024, seal 2025 | 2024 holdout exhausted (used for v2.0/v2.1 ship decisions); 2025 is next unseen season | MEDIUM | Change `HOLDOUT_SEASON` + derived constants in config.py; verify holdout guards in 6 source files (ensemble_training, model_training, feature_selector, prediction_backtester) |
| 2025 Bronze data ingestion (schedules, PBP, player/team stats) | Need 2025 game results for new holdout ground truth; 2025 NFL season completed Jan 2026 | MEDIUM | Data available via nfl-data-py; run existing ingestion scripts for season 2025 |
| 2025 Silver transformations (all paths) | Need complete feature vector for 2025 games to serve as holdout evaluation data | MEDIUM | Run all 6 Silver transformation scripts for season 2025; depends on Bronze existing |
| New ensemble baseline on 2025 holdout | After rotation, retrain on 2016-2024 and establish sealed baseline on 2025 | MEDIUM | Run existing `train_ensemble.py` + `backtest_predictions.py --holdout` with updated config |
| Batch ingestion with skip-existing for odds | Re-running full 2016-2021 should not re-write season=2020 which already exists | LOW | Script has idempotent download; add per-season Parquet existence check |
| Feature vector assembly including 2024-2025 | 2024 was holdout (features exist); 2025 needs new feature assembly after Silver runs | MEDIUM | Run `feature_engineering.py` assembly for 2025 after Silver is complete |

### Differentiators (Competitive Advantage)

Features that improve coverage or evaluation rigor beyond the minimum.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| 2022-2025 odds from nflverse schedules | nflverse `import_schedules()` returns closing spread_line and total_line for every season; closes 2022+ gap for free with zero new dependencies | LOW | CLOSING lines only (no opening lines available); opening_spread/opening_total will be NaN for 2022+; XGBoost/LightGBM/CatBoost handle NaN natively |
| Unified Bronze odds schema with source provenance | FinnedAI (2016-2021) has opening+closing+moneylines; nflverse (2022+) has closing only; `source` column distinguishes provenance and explains NaN patterns | MEDIUM | Schema union approach: NaN for fields missing from a given source; single Bronze odds path for all downstream consumers |
| Holdout rotation automation (computed constants) | Make `TRAINING_SEASONS`, `VALIDATION_SEASONS`, `PREDICTION_SEASONS` derive from `HOLDOUT_SEASON` so future rotations are a one-line config change | LOW | Currently 4 separate hardcoded lists; compute: `TRAINING = range(2016, HOLDOUT)`, `VALIDATION = range(2019, HOLDOUT)`, `PREDICTION = range(2016, HOLDOUT+1)` |
| Walk-forward CV expansion with 2024 as new fold | Unsealing 2024 lets it become a new validation fold (train 2016-2023, validate 2024), giving richer CV | LOW | Append 2024 to `VALIDATION_SEASONS`; walk-forward CV already handles arbitrary fold lists |
| Pre-holdout baseline archival | Save v2.0/v2.1 sealed 2024 metrics alongside v2.2 sealed 2025 metrics for longitudinal comparison | LOW | Archive `models/ensemble/` metadata JSON before retraining |
| Market feature ablation on new holdout | With 6 seasons of market data in training (vs 1 in v2.1), genuinely test whether market features help | MEDIUM | Use existing `scripts/ablation_market_features.py`; this is the real test after ingestion is complete |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Paid odds API (The Odds API, SportsDataIO, OpticOdds) | Complete historical odds with timestamps and multiple books | Recurring cost ($50-500/mo), API credential management, dependency on external service uptime | nflverse closing lines are free and already integrated; sufficient for batch prediction |
| FinnedAI scraper re-run for 2022+ seasons | Would provide opening+closing lines for recent seasons | Scraper unmaintained since Dec 2023; CLI date range capped at 2021; SBRO website likely changed; HIGH breakage risk | Use nflverse schedules for 2022+; accept no opening lines |
| Opening line features for 2022+ | Opening-to-closing movement is known sharp action signal | No free source provides 2022+ opening lines; approximating/estimating them introduces noise worse than NaN | Let opening_spread/opening_total be NaN for 2022+; gradient boosting handles missing values natively |
| Multiple sportsbook line comparison | Pinnacle vs consensus vs offshore could improve edge detection | Adds schema complexity, multiple source dependencies, and unclear model lift for game-level spreads | Stick with single consensus line; multi-book is a v4.0+ concern |
| Automatic holdout rotation on a schedule | Prevents forgetting to rotate after each season | Premature unsealing wastes holdout integrity; rotation should be a deliberate milestone decision tied to model improvement work | Manual config change at milestone boundaries only |
| AusSportsBetting.com integration | Free Excel download with odds from 2006+ | Different schema (decimal odds, no moneylines), single closing line only (same as nflverse), unclear data quality, personal-use license restriction | nflverse is simpler, already integrated, same closing-line data |
| Moneyline-derived features for 2022+ | Implied probability from moneylines can be a feature | nflverse has no moneyline data; computing implied probability from spreads is circular with existing spread features | Only use moneylines where FinnedAI provides them (2016-2021); NaN for 2022+ |

## Feature Dependencies

```
Full FinnedAI batch ingestion (2016-2021)
    +-- Silver market data for all 6 seasons
         +-- Feature vector has market data across training window (2016-2021)

nflverse schedule odds extraction (2022-2025)         [parallel with above]
    +-- Unified Bronze odds schema with source column
         +-- Closing-line coverage for full 2016-2025 range

2025 Bronze ingestion (schedules, PBP, stats, teams)  [parallel with above]
    +-- 2025 Silver transformations (all 6 paths)
         +-- 2025 feature vector assembly
              +-- Holdout evaluation data exists for 2025

Holdout config rotation (HOLDOUT_SEASON = 2025)
    +-- REQUIRES: 2025 feature vector + game results exist
    +-- REQUIRES: All Silver data for 2025 complete
    +-- Validation seasons update (add 2024 as fold)
         +-- Ensemble retraining (train on 2016-2024)
              +-- New sealed baseline on 2025 holdout
                   +-- Market feature ablation vs baseline
```

### Dependency Notes

- **Silver market data requires FinnedAI ingestion:** Cannot compute line movement features without Bronze odds Parquet files
- **Holdout rotation requires 2025 data pipeline complete:** Cannot evaluate on 2025 if Bronze/Silver/Gold data doesn't exist
- **Ablation requires new baseline:** Need "without market" baseline retrained on 2016-2024 before comparing "with market"
- **nflverse odds and FinnedAI ingestion are independent:** Can run in parallel; no shared dependency
- **Config rotation must happen AFTER data exists but BEFORE retraining:** Order is critical for holdout guard integrity
- **2025 Bronze ingestion is independent of odds work:** Can run in parallel with FinnedAI batch and nflverse odds

## MVP Definition

### Launch With (v2.2 Core)

Minimum to establish a new, trustworthy holdout baseline with full market feature coverage.

- [ ] Full 2016-2021 FinnedAI batch ingestion -- fills market data gap in training window
- [ ] Silver market data for all FinnedAI seasons -- makes market features available to feature vector
- [ ] 2025 Bronze + Silver pipeline (all data types) -- creates ground truth and features for new holdout
- [ ] Holdout config rotation (2024 unsealed, 2025 sealed) -- reestablishes evaluation integrity
- [ ] Ensemble retraining + new 2025 baseline -- the deliverable: new model with honest evaluation numbers

### Add After Validation (v2.2.x)

Features to add once core holdout reset is working.

- [ ] nflverse 2022-2025 odds integration -- extends closing-line coverage beyond FinnedAI's 2021 cutoff
- [ ] Holdout config automation (computed constants) -- makes future rotations trivial
- [ ] Market feature ablation on new holdout -- the real test of market data value with 6x more training coverage
- [ ] Walk-forward CV expansion with 2024 fold -- richer cross-validation signal

### Future Consideration (v3+)

- [ ] Paid odds API for opening lines 2022+ -- only if market features prove valuable on 2025 holdout
- [ ] Multi-book line comparison -- only after single-line model is optimized
- [ ] Live line snapshot pipeline -- only in production (v4.0+)

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Full FinnedAI batch (2016-2021) | HIGH | LOW | P1 |
| Silver market data (all 6 seasons) | HIGH | LOW | P1 |
| 2025 Bronze data ingestion | HIGH | MEDIUM | P1 |
| 2025 Silver transformations | HIGH | MEDIUM | P1 |
| Holdout rotation config | HIGH | MEDIUM | P1 |
| Ensemble retraining + baseline | HIGH | LOW | P1 |
| nflverse 2022-2025 odds | MEDIUM | LOW | P2 |
| Holdout config automation | MEDIUM | LOW | P2 |
| Market ablation on new holdout | MEDIUM | LOW | P2 |
| Walk-forward CV expansion | LOW | LOW | P2 |
| Pre-holdout baseline archival | LOW | LOW | P3 |

**Priority key:**
- P1: Must have -- required for new holdout baseline
- P2: Should have -- improves model coverage or evaluation rigor
- P3: Nice to have -- documentation/archival

## Key Insight: Why Market Feature Ablation Was Inconclusive in v2.1

The most important finding for phase ordering: v2.1 tested market features on the 2024 holdout, but:

1. **Training data had mostly NaN market features** -- only season 2020 had odds data out of the 2016-2023 training window
2. **Holdout (2024) had zero market data** -- FinnedAI stops at 2021; 2024 market features were all NaN
3. **The ablation was structurally biased against market features** -- models couldn't learn from NaN-dominated training data, and evaluation on all-NaN holdout was meaningless

With full 2016-2021 ingestion (6 seasons of market data in training) + nflverse 2022+ closing lines + 2025 holdout (which will have closing-line data from nflverse), the ablation becomes a genuine test. **This is the key question v2.2 should answer: do market features actually help when properly populated?**

## Data Source Coverage Matrix

| Season | FinnedAI (opening+closing) | nflverse schedules (closing only) | Status |
|--------|---------------------------|-----------------------------------|--------|
| 2016 | Available | Available | Need to ingest (FinnedAI) |
| 2017 | Available | Available | Need to ingest (FinnedAI) |
| 2018 | Available | Available | Need to ingest (FinnedAI) |
| 2019 | Available | Available | Need to ingest (FinnedAI) |
| 2020 | Ingested (Bronze exists) | Available | Done |
| 2021 | Available | Available | Need to ingest (FinnedAI) |
| 2022 | Not available | Available | Need nflverse extraction |
| 2023 | Not available | Available | Need nflverse extraction |
| 2024 | Not available | Available | Need nflverse extraction (training data after unseal) |
| 2025 | Not available | Available | Need nflverse extraction (new holdout) |

## Sources

- [FinnedAI sportsbookreview-scraper](https://github.com/FinnedAI/sportsbookreview-scraper) -- Pre-scraped NFL odds 2016-2021; scraper unmaintained since Dec 2023; CLI date range capped at 2021
- [nflverse/nfl_data_py](https://github.com/nflverse/nfl_data_py) -- `import_schedules()` returns spread_line/total_line for all seasons; closing lines only
- [nflverse schedules reference](https://nflreadr.nflverse.com/reference/load_schedules.html) -- Confirms spread_line/total_line fields in schedule data
- [AusSportsBetting historical NFL data](https://www.aussportsbetting.com/data/historical-nfl-results-and-odds-data/) -- Free Excel from 2006+; closing line only, no opening lines; NOT recommended
- [The Odds API historical](https://the-odds-api.com/historical-odds-data/) -- Historical odds from June 2020; paid plans only; NOT recommended for this project
- Existing codebase: `scripts/bronze_odds_ingestion.py` (proven FinnedAI pipeline), `src/market_analytics.py` (movement features), `src/config.py` (HOLDOUT_SEASON=2024, VALIDATION_SEASONS, TRAINING_SEASONS, PREDICTION_SEASONS), `src/feature_engineering.py` (_PRE_GAME_CONTEXT with opening_spread/opening_total), `src/ensemble_training.py` (holdout guard), `src/feature_selector.py` (holdout guard), `src/prediction_backtester.py` (holdout evaluation)

---
*Feature research for: v2.2 Full Odds + Holdout Reset*
*Researched: 2026-03-28*
