# FTN Build Results

**Date:** 2026-06-12
**Task:** Productionize FTN charting data pipeline from spike → production code
**Status:** COMPLETE

---

## 1. What Was Built

### Files Created

| File | Purpose |
|------|---------|
| `scripts/bronze_ftn_ingestion.py` | Bronze CLI: fetches FTN via `nfl_data_py.import_ftn_data`, writes `data/bronze/ftn_charting/season=YYYY/`. Guards against pre-2022 requests. Optional S3 upload. |
| `src/ftn_features.py` | Silver feature computation: `compute_ftn_player_week()`, `add_ftn_trailing_features()`, `build_ftn_silver()`, `FTN_FEATURE_COLUMNS` registry (22 trailing columns). |
| `scripts/silver_ftn_transformation.py` | Silver CLI: `--seasons 2022-2025` → reads Bronze FTN + PBP, builds receiver + QB player-week aggregates, writes Silver parquet. |
| `tests/test_ftn_pipeline.py` | 25 tests: ingestion guard, empty df, missing cols, season gaps, shift(1) lag enforcement, leak gate (all passing). |

### Files Modified (additive only)

| File | Change |
|------|--------|
| `src/player_feature_engineering.py` | Added step 19 `_join_ftn_features()` in `assemble_player_features()`. Added 11 raw FTN column names to `_SAME_WEEK_RAW_STATS` exclusion set. Added `_join_ftn_features()` function (left-join on player_id/season/week, NaN-fill for missing seasons). |

### Data Generated

| Layer | Path | Rows |
|-------|------|------|
| Bronze | `data/bronze/ftn_charting/season=2022/` | 41,643 plays |
| Bronze | `data/bronze/ftn_charting/season=2023/` | 48,225 plays |
| Bronze | `data/bronze/ftn_charting/season=2024/` | 48,031 plays |
| Silver | `data/silver/players/ftn/season=2022/` | 5,240 player-weeks |
| Silver | `data/silver/players/ftn/season=2023/` | 5,317 player-weeks |
| Silver | `data/silver/players/ftn/season=2024/` | 5,171 player-weeks |

### Feature Columns Produced (22 trailing features)

Receiver (WR/TE):
- `ftn_catchable_rate_roll4`, `ftn_catchable_rate_trail`
- `ftn_contested_rate_roll4`, `ftn_contested_rate_trail`
- `ftn_drop_rate_roll4`, `ftn_drop_rate_trail`
- `ftn_pa_target_share_roll4`, `ftn_pa_target_share_trail`
- `ftn_created_rec_rate_roll4`, `ftn_created_rec_rate_trail`

QB:
- `ftn_blitz_rate_roll4`, `ftn_blitz_rate_trail`
- `ftn_avg_pass_rushers_roll4`, `ftn_avg_pass_rushers_trail`
- `ftn_out_of_pocket_rate_roll4`, `ftn_out_of_pocket_rate_trail`
- `ftn_throw_away_rate_roll4`, `ftn_throw_away_rate_trail`
- `ftn_interception_worthy_rate_roll4`, `ftn_interception_worthy_rate_trail`
- `ftn_play_action_rate_roll4`, `ftn_play_action_rate_trail`

---

## 2. Leak Gate Results

**Result: ZERO LEAKS — ALL PASS**

| Check | Result |
|-------|--------|
| Raw FTN columns in `_SAME_WEEK_RAW_STATS` | 11/11 blocked |
| Trailing FTN columns NOT in `_SAME_WEEK_RAW_STATS` | 22/22 correctly allowed |
| `_is_unlagged_leak()` on trailing FTN columns | 0/22 flagged |
| `get_player_feature_columns()` raw FTN in output | 0 (correctly excluded) |
| `get_player_feature_columns()` trailing FTN in output | 22 (correctly included) |
| Pytest leak gate tests | 4 tests PASS |

Temporal integrity: shift(1) is applied within `(player_id, season)` groups before any rolling calculation. Week 1 trailing features are NaN (no prior week). Verified by `test_shift1_applied_roll4_week1_nan`.

**NaN coverage for pre-2022 seasons:** Expected and documented. FTN coverage starts 2022. For seasons 2016-2021 in training, all 22 FTN feature columns will be NaN. The Ridge model handles NaN-filled features via `fillna(0)` in training; production inference does the same.

---

## 3. Signal Measurement

### Methodology Clarification

The spike reported `contested_rate partial_r = 0.054 (p < 0.001)`. That used a player-level (cross-season) shift, which understates season-boundary isolation. Our production trailing features use the correct `(player_id, season)` grouping. Both approaches were measured.

### 3a. Partial Correlations (Trailing FTN ~ next_week_half_ppr | lag_targets)

**Spike methodology replicated on Silver data** (player-level lag, >=3 targets filter, 2022-2024, n=7,296):

| Feature | Partial r | p-value | n | Significant? |
|---------|-----------|---------|---|--------------|
| `ftn_contested_rate` (lag1) | **+0.0501** | <0.0001 | 7,296 | YES (p<0.001) |
| `ftn_created_rec_rate` (lag1) | **+0.0249** | 0.0336 | 7,296 | YES (p<0.05) |
| `ftn_catchable_rate` (lag1) | -0.0092 | 0.431 | 7,296 | no |
| `ftn_drop_rate` (lag1) | -0.0139 | 0.236 | 7,296 | no |
| `ftn_pa_target_share` (lag1) | +0.0191 | 0.103 | 7,296 | Marginal |

**Season-scoped trailing features** (production-faithful, >=1 prior week with FTN, n=7,290):

| Feature | Partial r | p-value | n | Significant? |
|---------|-----------|---------|---|--------------|
| `ftn_pa_target_share_roll4` | -0.0237 | 0.0435 | 7,290 | YES (p<0.05) |
| `ftn_pa_target_share_trail` | -0.0279 | 0.0172 | 7,290 | YES (p<0.05) |
| `ftn_catchable_rate_roll4` | +0.0153 | 0.191 | 7,290 | no |
| `ftn_catchable_rate_trail` | +0.0175 | 0.136 | 7,290 | no |
| `ftn_contested_rate_roll4` | -0.0036 | 0.758 | 7,290 | no |
| `ftn_contested_rate_trail` | -0.0062 | 0.599 | 7,290 | no |
| others | <0.020 | >0.15 | 7,290 | no |

**Interpretation:** The `contested_rate` lag1 signal (r=0.050) from the spike replicates. However, when averaged into a rolling season-scoped trailing mean, the signal collapses to near-zero (r=-0.004). This is a known issue with rolling aggregation: a single high-contested-target game becomes diluted over 4-week windows. The spike's signal is real for the most recent prior game but does not persist as a rolling mean.

The `ftn_pa_target_share_trail` shows a statistically significant **negative** partial r (-0.028), suggesting receivers who accumulate more play-action targets over a season underperform the next week vs their target-share baseline. Effect size is small.

Baseline `lag_targets ~ next_half_ppr`: r = 0.286, confirming the FTN effects are secondary.

### 3b. WR Ridge Residual Probe

**Setup:** WR-only, seasons 2022 train → 2023-2024 eval, weeks 3-18. Base features: 45 rolling columns from Silver usage. FTN features: 22 trailing columns. Sample restricted to rows with FTN data (89.7% coverage on WR rows).

| Model | Features | MAE (2023-2024 eval) | n |
|-------|----------|----------------------|---|
| Base Ridge | 45 rolling cols | 4.4608 | 3,444 |
| Base + FTN Ridge | 45 + 22 FTN trailing | 4.4589 | 3,444 |
| Delta | | **+0.0018 (-0.04%)** | |

Heuristic (roll3 mean baseline): MAE = 5.068. The Ridge probe substantially outperforms the heuristic (-0.607), but adding FTN features contributes negligible improvement over base Ridge (+0.0018 MAE, +0.04%).

---

## 4. SHIP / HOLD Recommendation

### HOLD — Do Not Add FTN Features to Production Hybrid Feature Set

**Rationale:**

1. **No measured improvement.** The Ridge probe shows +0.0018 MAE delta vs base, which is noise-level (< 0.04%). The production target is 4.71 MAE; this does not move the needle.

2. **contested_rate signal decays with aggregation.** The spike's confirmed r=0.050 signal applies to single-game lag1 (prior game's contested-target rate), but the lagged rolling mean (the correct leak-safe form) loses the signal entirely in 4-week windows. A week-4 trailing mean of contested rate is dominated by game-to-game noise.

3. **Coverage gap complicates training.** FTN covers only 2022-2025. Adding 22 FTN columns to a model trained on 2016-2025 data introduces 4 seasons of complete NaN (2016-2021) that Ridge must handle via zero-fill, introducing a systematic bias toward zero for pre-2022 players.

4. **Better levers available.** The current WR heuristic improvement path (per-position recency, matchup factor revival) produced -0.07 MAE (4.78→4.71). FTN trailing features provide ~0% improvement compared to that.

**Conditions for revisiting (SHIP):**

- If the feature set is extended to use the most-recent single-week FTN values (lag1 of weekly aggregates, not multi-week rolling), the `contested_rate` signal may materialize. This requires careful scoping: lag1 within season — NOT across seasons.
- When the training window is restricted to 2022+ only (e.g. for a 2022-forward model variant), the NaN coverage issue disappears and the marginal improvement could be tested cleanly.
- If a longer FTN history becomes available (2019-2021), covering more of the training window.

**The pipeline itself (Bronze → Silver → trailing features) is production-ready and registered in `assemble_player_features` step 19.** The data flows correctly; the HOLD is on whether to include the features in the active model feature set until the signal is stronger.

---

## 5. Commits

| Hash | Message |
|------|---------|
| e2b2533 | feat(ftn): Bronze→Silver FTN charting pipeline + leak-safe player-week features |

Files: `scripts/bronze_ftn_ingestion.py`, `scripts/silver_ftn_transformation.py`, `src/ftn_features.py`, `tests/test_ftn_pipeline.py`, `src/player_feature_engineering.py`
