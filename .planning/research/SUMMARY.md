# Project Research Summary

**Project:** v2.2 Full Odds + Holdout Reset
**Domain:** NFL prediction platform — odds data expansion and holdout evaluation framework rotation
**Researched:** 2026-03-28
**Confidence:** HIGH

## Executive Summary

v2.2 is a data expansion and evaluation framework milestone, not a technology milestone. No new libraries are required. The core work is: (1) completing the FinnedAI odds ingestion for the 5 remaining seasons (2016-2019, 2021) using an already-proven script, (2) bridging 2022+ odds coverage using nflverse schedules which already provide closing lines for free, (3) running the full Bronze/Silver pipeline for the 2025 season to create ground truth for the new holdout, and (4) rotating the holdout from 2024 to 2025 by changing four constants in `config.py`, then retraining the P30 ensemble. The entire milestone is a "run it more times and update the config" problem, not a "build new things" problem.

The key strategic value of v2.2 is that the v2.1 market feature ablation was structurally flawed: only 1 of the 8 training seasons had market data, and the holdout (2024) had zero market data. The conclusion that market features don't help was therefore inconclusive. After v2.2, market features will be populated for the full 2016-2021 training window (6 seasons) and closing-line data will be available for 2022-2025 via nflverse. This means the re-run ablation on the 2025 holdout will be the first genuine test of whether market features improve game prediction accuracy. That test is the milestone's real deliverable.

The primary risks are not technical — they are procedural. Holdout contamination (changing `HOLDOUT_SEASON` before retraining), closing-line leakage (accidentally adding retrospective features to the pre-game context), and stale model evaluation (running the old model against the new holdout) are all well-understood and preventable with strict sequencing discipline. The architecture is already hardened against these: a centralized `HOLDOUT_SEASON` constant propagates the holdout guard to all ML modules, a `LEAKAGE_THRESHOLD` flag triggers investigation if ATS accuracy exceeds 58%, and a latest-file convention ensures idempotent re-ingestion.

## Key Findings

### Recommended Stack

No new dependencies. Every library needed for v2.2 is already installed: pandas 1.5.3, pyarrow 21.0.0, requests 2.32.4, scipy 1.13.1, nfl-data-py 0.3.3, openpyxl, xgboost, lightgbm, catboost, scikit-learn, shap, and optuna. The stack is frozen at current versions, all validated for Python 3.9 compatibility.

**Core technologies:**
- `bronze_odds_ingestion.py`: FinnedAI JSON parser — already proven on 2020; batch-run remaining seasons with no code changes
- `nfl.import_schedules()`: nflverse closing lines — free, already ingested; use as opening-line proxy for 2022+ via a new `derive_odds_from_nflverse()` function
- `src/config.py`: holdout constants — single-file change propagates to all 5+ ML modules via import
- XGB+LGB+CB+Ridge ensemble: retrain on expanded 2016-2024 training window after config update

**What not to add:** paid odds APIs (The Odds API at $99+/mo, SportsDataIO), AusSportsBetting.com XLSX (same closing-line data as nflverse with extra complexity and a personal-use license restriction), FinnedAI scraper re-run for 2022+ (unmaintained since Dec 2023, CLI date range capped at 2021), MLflow/W&B (four config constants outperform experiment tracking infrastructure for this use case).

### Expected Features

**Must have (P1 — required for new holdout baseline):**
- Full 2016-2021 FinnedAI batch ingestion — fills market data gap across training window
- Silver market data regeneration for all 6 FinnedAI seasons — makes market features available to feature vector
- 2025 Bronze + Silver pipeline (all data types) — creates ground truth and features for the new holdout
- Holdout config rotation (unseal 2024, seal 2025) — reestablishes evaluation integrity
- Ensemble retraining on 2016-2024 + new 2025 baseline — the actual deliverable

**Should have (P2 — improves coverage and evaluation rigor):**
- nflverse 2022-2025 closing-line odds ingestion — extends market coverage beyond FinnedAI's 2021 cutoff
- Holdout config automation (computed constants) — future rotations become a one-line change
- Market feature ablation re-run on 2025 holdout — the genuine test now that training data has full market coverage
- Walk-forward CV expansion with 2024 as a new validation fold

**Defer (v3+):**
- Paid odds API for 2022+ opening lines — only warranted if re-run ablation proves opening-line movement materially improves accuracy
- Multi-book line comparison — v4.0+ concern
- Live line snapshot pipeline — production infrastructure concern

The critical sequencing constraint: ablation must not run until a clean baseline is documented. The sequence is strictly data complete → config update → retrain → baseline → ablation.

### Architecture Approach

v2.2 requires zero new components. Every data flow follows existing patterns: season-partitioned Parquet at Bronze, Silver market transformation per season, left-join on [team, season, week] in feature engineering, holdout guard via config constant. The one minor addition is a `derive_odds_from_nflverse()` function in `bronze_odds_ingestion.py` for 2022+ seasons that uses closing lines as opening-line proxies — same Bronze schema as FinnedAI output, with a `line_source` column for provenance. Downstream code sees no schema differences; `spread_shift` and `total_shift` will be zero for 2022+ (no movement when open == close), but `opening_spread` and `opening_total` — the only market features in `_PRE_GAME_CONTEXT` — will be populated.

**Major components and their v2.2 role:**
1. `scripts/bronze_odds_ingestion.py` — minor modification: add nflverse fallback function for 2022+; no changes needed for FinnedAI batch
2. `src/config.py` — the only required modification: 4 holdout constants + odds season range upper bound
3. `scripts/silver_market_transformation.py` — no changes; run for all new seasons
4. `src/ensemble_training.py` / `src/prediction_backtester.py` — no changes; consume updated config constants automatically
5. `tests/` — update hardcoded `2024` holdout assertions to import `HOLDOUT_SEASON` from config

Scaling is trivial: Bronze odds grows from ~50 KB to ~500 KB; Silver market data from ~100 KB to ~1 MB; ensemble training time from ~5 to ~6 minutes.

### Critical Pitfalls

1. **Closing-line leakage** — if retrospective features (`spread_shift`, `total_shift`, magnitude buckets) are added to `_PRE_GAME_CONTEXT`, ATS accuracy inflates past 58% artificially. Prevention: keep `_PRE_GAME_CONTEXT` read-only during 2022+ ingestion work; existing `LEAKAGE_THRESHOLD = 0.58` in `prediction_backtester.py` provides detection.

2. **Holdout contamination** — changing `HOLDOUT_SEASON` before data and retraining are complete corrupts all evaluation runs. Prevention: treat holdout rotation as the final step in the milestone, atomic with retraining. Never evaluate the old model against the new holdout.

3. **Stale production model** — after config update, `models/ensemble/` still holds the v2.1 model trained on 2016-2023. Running `backtest_predictions.py --holdout` against the new holdout with the stale model produces misleading baseline numbers. Prevention: run `train_ensemble.py` immediately after config update, before any prediction or evaluation scripts.

4. **NaN propagation with partial 2022+ market coverage** — LightGBM may raise on NaN in categoricals if the new 2022+ source does not cover all games. Prevention: coverage audit (NaN rate < 5% per market feature per season) before Silver write; verify `make_lgb_model` handles NaN explicitly.

5. **Incomplete team mapping or season boundary mismatch for new 2022+ source** — any new source uses different team name conventions; playoff games (January dates) may record as season+1 in calendar-year sources. Prevention: dry-run before writing Parquet, zero unmapped team warnings, zero orphans, minimum 10 games with week >= 19 per ingested season.

6. **Unsealing holdout without establishing new baseline first** — changing config then immediately running ablation produces results with no reference point. Prevention: document 2024 baseline metrics (53.0% ATS, +$3.09 profit) before touching config; record new 2025 baseline before running any ablation.

## Implications for Roadmap

The dependency graph implies a strict 3+1 phase sequence. Phases 1-2 can overlap in execution but Phase 3 cannot begin until both are complete, and Phase 4 (holdout reset) is strictly last.

### Phase 1: Full FinnedAI Batch Ingestion (2016-2021)
**Rationale:** The FinnedAI JSON is already downloaded locally. The ingestion script is proven on 2020. Zero code changes needed. This is the lowest-risk, highest-value action: it fills market features for 5 seasons of the training window where they are currently NaN. All downstream Silver and ablation work depends on this Bronze foundation.
**Delivers:** Bronze odds Parquet for 2016, 2017, 2018, 2019, 2021 (joining existing 2020)
**Addresses:** P1 feature "Full 2016-2021 FinnedAI batch ingestion"
**Avoids:** Running Silver transformation before Bronze exists (integration gotcha from PITFALLS.md)

### Phase 2: Silver Market Expansion + 2022+ Odds Sourcing
**Rationale:** Once FinnedAI Bronze is complete, Silver market data can be regenerated for all 6 seasons. This phase also adds the nflverse-derived odds function for 2022+ seasons (closing lines as opening-line proxies), extending market coverage through 2025. The schema-compatible fallback approach avoids any downstream code changes.
**Delivers:** Silver market_data for 2016-2025; opening_spread/opening_total populated for full training + holdout window
**Uses:** `silver_market_transformation.py` (no changes), minor addition to `bronze_odds_ingestion.py`
**Avoids:** Pitfall 1 (closing-line leakage) — `_PRE_GAME_CONTEXT` stays read-only during this phase; Pitfall 5 (season boundary mismatch) — playoff coverage check at Bronze ingestion time

### Phase 3: 2025 Bronze + Silver Data Pipeline
**Rationale:** The holdout reset requires 2025 game results and feature vectors. This phase runs all 16 Bronze data types and all Silver transformation scripts for season 2025. It is largely independent of the odds work and can overlap Phase 2 in execution, but must complete before the config rotation in Phase 4. The 2025 NFL season completed January 2026, so data should be available via nfl-data-py — but availability must be verified before committing to 2025 as the new holdout.
**Delivers:** Complete Bronze and Silver data for 2025; feature vector assembly possible; ground truth (final scores) confirmed
**Avoids:** Pitfall 2 (holdout contamination) — cannot rotate holdout to 2025 without its feature vector existing first

### Phase 4: Holdout Reset + Baseline Establishment
**Rationale:** This is the final, atomic phase. Only when Phases 1-3 are complete does it become safe to rotate the holdout. The sequence is strictly: (1) document current 2024 baseline metrics, (2) update `config.py` constants, (3) run `train_ensemble.py` immediately, (4) run `backtest_predictions.py --holdout` to establish 2025 baseline, (5) update tests to import `HOLDOUT_SEASON` from config. No ablation until the baseline is documented.
**Delivers:** P30 ensemble retrained on 2016-2024, sealed baseline on 2025 holdout, updated test suite
**Avoids:** Pitfall 3 (stale production model) — config change and retraining are atomic; Pitfall 6 (no baseline before ablation)

### Phase 5: Market Feature Ablation + Validation (v2.2.x)
**Rationale:** Only after the new baseline exists does the ablation become meaningful. With 6 seasons of FinnedAI market data in training (vs 1 in v2.1) and nflverse closing lines for 2025 holdout, this is the first structurally valid test of whether market features improve game prediction. Use the existing `scripts/ablation_market_features.py` with the existing ship-or-skip gate (strict > on holdout ATS accuracy).
**Delivers:** Definitive answer on market feature value; decision on whether to pursue 2022+ opening lines via paid API in v3.0

### Phase Ordering Rationale

- Phases 1 and 3 are independent and can run in parallel; Phase 2 requires Phase 1 complete (Silver needs Bronze odds)
- Phase 4 is strictly last — holdout rotation is irreversible within a milestone; doing it early corrupts all interim evaluations
- Phase 5 is post-baseline by design — running ablation without a documented baseline was the structural flaw of v2.1
- The config change in Phase 4 is a one-line propagation across the entire codebase via `HOLDOUT_SEASON`; every guard, training boundary, and evaluation target updates automatically

### Research Flags

Phases with standard patterns (skip additional research):
- **Phase 1:** Proven pipeline (run on 2020), no code changes, FinnedAI JSON already downloaded locally
- **Phase 2 (FinnedAI Silver):** Same transformation script tested on season 2020; seasonal loop is idiomatic
- **Phase 4:** Config-driven holdout is documented and tested; retraining is standard `train_ensemble.py`
- **Phase 5:** Ablation script already exists; ship-or-skip gate already implemented

Phases that need verification before execution:
- **Phase 2 (nflverse 2022+ fallback):** Verify `import_schedules()` column names for 2022-2025 match expectations (`spread_line`, `total_line`, moneylines present, no breaking schema changes) — nfl-data-py 0.3.3 is archived and schema changes are possible
- **Phase 3:** Verify 2025 data availability in nfl-data-py before committing to 2025 holdout; smoke test: `nfl.import_schedules([2025])` and check game count; if 2025 data is incomplete, fall back to `HOLDOUT_SEASON = 2024` with expanded FinnedAI training coverage as the v2.2 deliverable

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All libraries installed and validated; no new dependencies; confirmed by requirements.txt inspection |
| Features | HIGH | Dependency graph based on direct codebase inspection; all affected files and line numbers identified in ARCHITECTURE.md |
| Architecture | HIGH | Config-driven holdout and Parquet-native pipeline are well-understood; nflverse schema for 2022-2025 is the one unverified element |
| Pitfalls | HIGH | All 6 pitfalls grounded in specific code locations with line numbers; recovery paths are straightforward and low-cost |

**Overall confidence:** HIGH

### Gaps to Address

- **2025 nfl-data-py coverage:** nfl-data-py 0.3.3 is archived (Sept 2025). The 2025 NFL season completed January 2026. Whether the archived version has full 2025 PBP and player stats needs verification before Phase 3 begins. Mitigation: run `nfl.import_schedules([2025])` as a smoke test; if row count is below ~285 games, fall back to 2024 holdout.
- **nflverse schedules schema for 2022+:** `import_schedules()` may have added or renamed columns between 2021 and 2025. The `derive_odds_from_nflverse()` function uses explicit column selection; a KeyError would surface immediately. Low risk, but worth a schema spot-check before writing Bronze Parquet.
- **2025 holdout fallback scope:** If 2025 data is incomplete, the reduced v2.2 scope is: FinnedAI batch ingestion only (Phases 1-2) with `HOLDOUT_SEASON` remaining at 2024 and `TRAINING_SEASONS` still 2016-2023. Market features would be populated for 6/8 training seasons (up from 1/8), making a re-run ablation more meaningful without requiring a holdout rotation. This is a valid deliverable.

## Sources

### Primary (HIGH confidence — direct codebase inspection)
- `scripts/bronze_odds_ingestion.py` — FinnedAI team mapping (44 entries), season range, `validate_cross_correlation`, `validate_row_counts`, `LEAKAGE_THRESHOLD`
- `src/config.py` — `HOLDOUT_SEASON=2024`, `TRAINING_SEASONS`, `VALIDATION_SEASONS`, `PREDICTION_SEASONS`
- `src/ensemble_training.py` — holdout guard at line 349, walk-forward CV structure, holdout raise at line 136
- `src/prediction_backtester.py` — `LEAKAGE_THRESHOLD=0.58`, `evaluate_clv`, holdout season default
- `src/feature_engineering.py` — `_PRE_GAME_CONTEXT` columns (only `opening_spread`/`opening_total` from market sources)
- `src/market_analytics.py` — PRE_GAME vs RETROSPECTIVE feature classification docstring
- `src/feature_selector.py` — holdout guard at line 65
- `src/model_training.py` — holdout guard at line 90

### Secondary (HIGH confidence — official documentation)
- [nflverse/nfl_data_py GitHub](https://github.com/nflverse/nfl_data_py) — `import_schedules()` returns `spread_line`, `total_line`, moneylines for all seasons
- [nflreadr load_schedules docs](https://nflreadr.nflverse.com/reference/load_schedules.html) — 46 column definitions confirmed
- [FinnedAI/sportsbookreview-scraper](https://github.com/FinnedAI/sportsbookreview-scraper) — covers 2016-2021; unmaintained since Dec 2023; CLI date range capped at 2021

### Tertiary (MEDIUM confidence — alternatives for future reference)
- [AusSportsBetting.com NFL Historical Data](https://www.aussportsbetting.com/data/historical-nfl-results-and-odds-data/) — free XLSX, 2006+; NOT recommended (closing-line only, personal-use license, complexity outweighs benefit vs nflverse)
- [The Odds API Historical](https://the-odds-api.com/historical-odds-data/) — paid $99+/mo, mid-2020+ coverage; revisit only if ablation proves opening-line movement matters
- [Kaggle NFL Scores and Betting Data](https://www.kaggle.com/datasets/tobycrabtree/nfl-scores-and-betting-data) — potential free 2022+ bridge; coverage and recency unverified

---
*Research completed: 2026-03-28*
*Ready for roadmap: yes*
