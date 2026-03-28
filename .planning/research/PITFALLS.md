# Pitfalls Research

**Domain:** NFL prediction platform — full odds ingestion and holdout reset (v2.2)
**Researched:** 2026-03-28
**Confidence:** HIGH — grounded in existing codebase, established patterns, and known system state

---

## Critical Pitfalls

### Pitfall 1: Closing-Line Leakage When Expanding Odds Coverage

**What goes wrong:**
When 2022+ market features become available, developers add both opening and closing-line-derived features to `_PRE_GAME_CONTEXT` in `feature_engineering.py`. Closing spread, closing total, `spread_shift`, `total_shift`, `crosses_key_spread`, and `total_magnitude` are computed from the closing line — which is not known until kickoff. Including them as model inputs creates retrospective leakage. The model appears to improve dramatically (could exceed 58% ATS), but the improvement is entirely from knowing the closing line before the game is played.

**Why it happens:**
`market_analytics.py` correctly documents which features are PRE_GAME vs RETROSPECTIVE in its docstring, and only `opening_spread` and `opening_total` are in `_PRE_GAME_CONTEXT`. When ingesting a new 2022+ source, developers may find the source provides opening and closing lines together and add all available columns to the feature context without re-reading the temporal classification comments.

**How to avoid:**
Keep the `_PRE_GAME_CONTEXT` list in `feature_engineering.py` read-only during 2022+ ingestion work. Only add new pre-game features if they match the existing field names and are not closing-line-derived. Run the existing leakage check — `LEAKAGE_THRESHOLD = 0.58` in `prediction_backtester.py` triggers an investigation flag if ATS accuracy exceeds 58%. Never add `spread_shift`, `total_shift`, or any magnitude bucket column to `_PRE_GAME_CONTEXT`.

**Warning signs:**
- ATS accuracy suddenly exceeds 56% during any training run
- Feature importance shows `spread_shift` or `total_shift` among top 5 features
- The ablation report shows market features contributing more than 3% ATS lift

**Phase to address:**
Bronze ingestion phase for the 2022+ source. Add a test asserting that `_PRE_GAME_CONTEXT` contains no closing-line-derived columns.

---

### Pitfall 2: Holdout Contamination When Unsealing 2024

**What goes wrong:**
Unsealing 2024 means changing `HOLDOUT_SEASON = 2024` to `HOLDOUT_SEASON = 2025` in `config.py`. If this change is made before re-training, the production ensemble in `models/ensemble/` was trained with the old guard, but evaluation scripts now target 2025 as holdout. Worse: if the change happens partway through a session, the ablation framework mixes old (2024-sealed) and new (2025-sealed) evaluations in the same report, producing a nonsensical comparison baseline.

**Why it happens:**
`HOLDOUT_SEASON` is a single constant imported by `ensemble_training.py`, `prediction_backtester.py`, and `ablation_market_features.py`. Changing it immediately affects all downstream evaluations. Developers often change it first ("set up the new holdout") then run the existing model against the new holdout before retraining — the model has never seen 2024 data, but also the holdout metrics are now incomparable to the documented v2.0 baseline.

**How to avoid:**
Treat holdout reset as an atomic, last-in-milestone operation with a strict sequence:
1. Document the final 2024 holdout metrics (53.0% ATS, +$3.09 profit) as a baseline before touching anything.
2. Ingest all expanded odds data and run Silver transformations for new seasons first.
3. Only then update `HOLDOUT_SEASON = 2025` and `VALIDATION_SEASONS` (add 2024) in `config.py`.
4. Retrain ensemble from scratch immediately after the config change — never evaluate the old model against the new holdout.
5. Document new baseline explicitly before running any ablation.

**Warning signs:**
- Evaluation reports show 2024 holdout results alongside a `HOLDOUT_SEASON=2025` config
- `VALIDATION_SEASONS` still excludes 2024 after config update
- Training data game count unchanged after adding new seasons to training window

**Phase to address:**
Holdout reset phase — must be last in the milestone sequence, after all data ingestion and Silver transformation phases are complete.

---

### Pitfall 3: Feature NaN Propagation When Market Coverage Is Partial for 2022+

**What goes wrong:**
Market features (`opening_spread`, `opening_total`, etc.) are currently uniformly NaN for 2022-2024 training windows because FinnedAI only covers 2016-2021. When 2022+ odds data is ingested, the feature vector will have mixed coverage — some games have market features, some don't. XGBoost handles NaN internally, but LightGBM and CatBoost behave differently. LGB may throw on NaN in categoricals; CatBoost requires explicit `nan_mode` configuration. Walk-forward CV folds that include seasons where market features are present for 80% of games but absent for 20% create fold-level instability in SHAP-based feature selection.

**Why it happens:**
The existing ensemble training was designed assuming market features are uniformly NaN for 2022-2024. Partial coverage (some games have odds, some don't) is a new scenario. New sources rarely have 100% game coverage — pre-season games, some international games, and early 2022 weeks may not be available.

**How to avoid:**
After ingesting 2022+ odds, run a coverage audit before retraining: compute NaN rate per market feature per season. If any market feature has >5% NaN in a new season, investigate source coverage before proceeding. Verify that `make_lgb_model` in `ensemble_training.py` handles NaN explicitly. Add a test asserting that ensemble training completes without error when market features are 20% NaN.

**Warning signs:**
- LightGBM raises `ValueError: Input data must not contain missing values`
- CatBoost warns about NaN in numeric features
- Feature selection produces inconsistent feature sets across folds for the same season

**Phase to address:**
Silver market transformation phase for 2022+ seasons — verify coverage before writing Parquet. Ensemble retraining phase — add NaN coverage assertion before training.

---

### Pitfall 4: Incomplete Team Mapping for a New 2022+ Odds Source

**What goes wrong:**
The existing `FINNEDAI_TO_NFLVERSE` dict in `bronze_odds_ingestion.py` handles 44 team name variants for FinnedAI, including franchise relocations and data quality issues (Washingtom typo, KCChiefs concatenation). A new 2022+ source will use different team name conventions — sportsbook scrapes may use city names ("Las Vegas"), mascot only ("Raiders"), full names ("Las Vegas Raiders"), or abbreviations. An incomplete mapping silently produces unmapped (None) entries that either become orphans at the nflverse join step or — worse — silently match the wrong team if a partial string match is attempted.

**Why it happens:**
Developers test the new source mapping with a handful of games, see it working, and deploy without checking all 32 teams across all seasons. Edge cases include Washington's sequence of name changes (Redskins → Football Team → Commanders), the Raiders relocation (Oakland 2019 → Las Vegas 2020), and both LA teams (Rams and Chargers both moved to Los Angeles).

**How to avoid:**
For any new source, run ingestion in dry-run mode first and inspect the unmapped team warnings printed by the parser. Require zero unmapped teams and zero orphans before proceeding to validation. The existing `validate_cross_correlation` will catch most issues, but only after all teams are mapped. Add a test fixture for the new source that asserts all 32 nflverse team abbreviations appear in at least one game across the covered seasons.

**Warning signs:**
- `WARNING: Unmapped home teams` or `WARNING: Unmapped away teams` printed during ingestion
- Orphan count exceeds 5 games per season
- `validate_cross_correlation` r < 0.95 (team mismatch causes wrong game joins)

**Phase to address:**
Bronze ingestion phase for the 2022+ source. Dry-run validation must pass before any Parquet is written.

---

### Pitfall 5: Season Boundary Mismatch Between Odds Source and nflverse Schedules

**What goes wrong:**
NFL game dates straddle calendar years. A game played in January 2023 belongs to the 2022 season in nflverse convention, but a new odds source may record it as season=2023. The `join_to_nflverse` function merges on `(season, home_team, gameday)` — if the season field from the new source is off by one for playoff games, all playoff rows become orphans. The existing code handles this correctly for FinnedAI (which uses nflverse-compatible season values), but cannot be assumed for a new source.

**Why it happens:**
NFL season convention is non-obvious: the 2022 season's Super Bowl is played in February 2023. Sportsbooks and scraped sources commonly use the calendar year of the game date rather than the NFL season year. The mismatch only appears in weeks 19-22 (playoffs and Super Bowl), which are often not inspected closely during initial testing.

**How to avoid:**
After ingestion, check that playoff games (week >= 19) are not uniformly orphaned. The existing `validate_row_counts` warns when game count deviates more than 5% from expected — a season with 256 regular season games but 0 playoff games will trigger this. Apply a one-year correction for playoff games if the source uses calendar year: `if month <= 3: season -= 1`.

**Warning signs:**
- Orphan count spikes to 10+ for a specific season
- `validate_row_counts` warns about game count significantly below expected
- No games with week >= 19 appear after the nflverse join

**Phase to address:**
Bronze ingestion phase for the 2022+ source — add a playoff coverage check (minimum 10 games with week >= 19 per season).

---

### Pitfall 6: Stale Production Model After Holdout Reset Without Retraining

**What goes wrong:**
After unsealing 2024 and sealing 2025, the production ensemble in `models/ensemble/` still represents the model trained on 2016-2023. If `generate_predictions.py --ensemble` is run before retraining, predictions are generated from a stale model. More critically: `backtest_predictions.py --holdout` will evaluate the stale model against 2025 holdout, producing results that are meaningless for baseline comparison — the model has never seen the 2022-2024 data added to the training window.

**Why it happens:**
`load_ensemble` reads artifacts from `models/ensemble/` without checking whether the model was trained on the current `TRAINING_SEASONS` range. There is no version stamp on model artifacts that would cause a failure. Model files from v2.0 are still valid pickle files and load without error.

**How to avoid:**
After updating `HOLDOUT_SEASON` and `VALIDATION_SEASONS` in `config.py`, run `train_ensemble.py` before any prediction or backtest script. Consider writing a `models/ensemble/manifest.json` during training that records the training season range — if the manifest's training seasons do not match `TRAINING_SEASONS` from config, `load_ensemble` should warn loudly.

**Warning signs:**
- Model file timestamps are older than the `config.py` modification time
- `backtest_predictions.py --holdout` returns results for season 2024 when `HOLDOUT_SEASON=2025`
- Training game count in the manifest does not include 2024 season games

**Phase to address:**
Ensemble retraining phase — must be gated on config update and must write a training manifest.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hard-coding `SEASONS = list(range(2016, 2022))` in `bronze_odds_ingestion.py` | Simple, no config lookup | Adding 2022+ requires editing the script directly, not just config.py | Never — register the valid season range in config.py alongside other data types |
| Reusing the FinnedAI parser for a new 2022+ source | No new file to maintain | Schema assumptions will break; sign conventions differ by source | Never — write a dedicated parser for each odds source |
| Changing `HOLDOUT_SEASON` as a first step before data work | Forces discipline on holdout thinking | Silently corrupts all evaluation runs until retraining completes | Never — config change must be atomic with retraining |
| Skipping playoff week coverage check in `validate_row_counts` | Faster validation | Playoff orphans inflate null rates and reduce training data silently | Never — add minimum playoff game count assertion |
| Reusing existing Silver market transformation for 2022+ without schema validation | Faster path | 2022+ source columns may differ; silent NaN propagation into feature vector | Never — validate schema before writing Silver Parquet |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| New 2022+ odds source (e.g., The Odds API, covers.com) | Treating it as drop-in replacement for FinnedAI | Write a dedicated Bronze parser with its own team mapping, sign convention validation, and schema test — do not modify `bronze_odds_ingestion.py` in-place |
| nflverse `import_schedules` for 2022+ | Assuming same schema as 2016-2021 | Check nfl-data-py changelog for schema changes; the explicit `sched[[...]]` column selection will raise a KeyError on new required columns |
| FinnedAI JSON re-download for full 6-season backfill | Skipping `--force-download` when cached file already exists | The FinnedAI GitHub JSON may have been updated; use `--force-download` to ensure data consistency across all 6 seasons |
| CLV evaluation after holdout reset | Running `evaluate_clv` against 2025 holdout with a 2023-trained model | Always retrain before evaluating CLV; stale models produce misleading CLV distributions that cannot be compared to v2.0 baseline |
| Silver market transformation for new seasons | Running `silver_market_transformation.py` without confirming Bronze odds exist | Script will silently produce empty Silver Parquet if Bronze odds are missing — check Bronze coverage first |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading all 6+ seasons of Bronze odds simultaneously for Silver transformation | Memory spike when processing 2016-2024 together | Process one season at a time in the Silver transformation loop (existing pattern) | Unlikely at current scale, but partition-per-season is the established pattern |
| Running full ablation sweep (`--counts 60 80 100 120 150`) after every data change | Ablation takes 30-60 minutes per run with 5 feature count variants | Run at default count first; only sweep if the default result is ambiguous | Not a breaking issue, but wastes iteration time during rapid data expansion phases |
| Assembling the full multi-year feature matrix with new seasons before verifying Silver is complete | `assemble_multiyear_features` returns silently empty rows for missing seasons | Verify Silver Parquet exists and has expected row count per season before calling `assemble_multiyear_features` | At current scale this silently drops seasons, not a memory issue |

---

## "Looks Done But Isn't" Checklist

- [ ] **Full 2016-2021 FinnedAI ingestion:** `--season 2020` already done — verify the remaining 5 seasons (2016, 2017, 2018, 2019, 2021) each have a Parquet under `data/bronze/odds/season=YYYY/`
- [ ] **2022+ source identified:** Source confirmed to cover 2022-2024 regular season AND playoffs — verify cross-correlation r >= 0.95 and zero orphans before declaring Bronze complete
- [ ] **Silver market transformation for new seasons:** Transformation runs without error AND output Parquet row count matches expected game count (not just non-empty file)
- [ ] **Holdout config update is complete:** Both `HOLDOUT_SEASON = 2025` AND `VALIDATION_SEASONS` updated to include 2024 AND `TRAINING_SEASONS` is consistent — verify all three in the same commit
- [ ] **Ensemble retrained on expanded data:** `train_ensemble.py` completed after config update — verify manifest records training seasons including 2024
- [ ] **New baseline documented before ablation:** ATS%, profit, CLV metrics written down before running market feature ablation — never run ablation without a documented baseline to compare against
- [ ] **CLV tracking still functional with new holdout:** `evaluate_clv()` uses nflverse `spread_line` (not FinnedAI closing line) — confirm correct source is used for 2025 holdout
- [ ] **Test suite still passing:** After all config changes and retraining, `python -m pytest tests/ -v` passes all 571 tests (v2.1 baseline)

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Closing-line leakage discovered post-training | MEDIUM | Remove retrospective features from `_PRE_GAME_CONTEXT`, retrain ensemble, re-evaluate holdout; no data loss, just compute time |
| Holdout contamination (wrong season evaluated) | LOW | Revert `HOLDOUT_SEASON` in config.py, retrain with correct config, document metrics from correct holdout |
| Incomplete team mapping causing orphans in 2022+ source | LOW | Add missing entries to team mapping dict, re-run ingestion (no re-download needed), re-run Silver transformation |
| Season boundary mismatch (playoff orphans) | LOW | Apply season correction in the new source parser (`if month <= 3: season -= 1`), re-ingest affected seasons |
| Stale production model evaluated against new holdout | LOW | Run `train_ensemble.py` with updated config, overwrite `models/ensemble/`; no data changes needed |
| NaN propagation breaks LightGBM training on partial 2022+ coverage | MEDIUM | Audit new source coverage per season; add explicit NaN handling to `make_lgb_model`; fix before retraining |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Closing-line leakage | Bronze ingestion of 2022+ source — validate temporal feature classification | Assert `_PRE_GAME_CONTEXT` contains only `opening_spread`/`opening_total` from market sources; ATS < 58% after training |
| Holdout contamination | Holdout reset phase (last in milestone) — atomic sequence enforced | `HOLDOUT_SEASON`, `VALIDATION_SEASONS`, and `TRAINING_SEASONS` updated in the same commit; ensemble retrained immediately after |
| NaN propagation in ensemble | Silver market transformation phase — coverage audit before Parquet write | Market feature NaN rate < 5% per season; ensemble training completes without error on partial-coverage data |
| Incomplete team mapping for new source | Bronze ingestion phase for 2022+ source — dry-run required | Zero unmapped team warnings; zero orphans; r >= 0.95 in cross-correlation |
| Season boundary mismatch | Bronze ingestion phase for 2022+ source — playoff coverage check | Each ingested season has >= 10 games with week >= 19 |
| Stale production model | Ensemble retraining phase — gated on config update | Model manifest records training seasons including 2024; `backtest_predictions.py --holdout` shows 2025 as holdout season |

---

## Sources

- Existing codebase: `scripts/bronze_odds_ingestion.py` — team mapping (44 entries), sign convention negation, `validate_cross_correlation`, `validate_row_counts`, `LEAKAGE_THRESHOLD`
- Existing codebase: `src/market_analytics.py` — PRE_GAME vs RETROSPECTIVE feature classification docstring
- Existing codebase: `src/prediction_backtester.py` — `LEAKAGE_THRESHOLD = 0.58`, `HOLDOUT_SEASON` import, `evaluate_clv` nflverse dependency
- Existing codebase: `src/config.py` — `HOLDOUT_SEASON = 2024`, `VALIDATION_SEASONS`, `TRAINING_SEASONS`
- Existing codebase: `src/ensemble_training.py` — walk-forward CV, OOF patterns, model factories
- Existing codebase: `.planning/PROJECT.md` — Key Decisions log, v2.1 completion notes, v2.2 target features
- Project MEMORY.md: "Market features NaN for 2022-2024 training window" and "CLV uses nflverse spread_line (not FinnedAI)"
- Project MEMORY.md: "FinnedAI covers 2016-2021 only; market features NaN for 2022-2024 training window"

---
*Pitfalls research for: NFL prediction platform — v2.2 Full Odds + Holdout Reset*
*Researched: 2026-03-28*
