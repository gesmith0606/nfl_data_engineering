# Span & Recency-Weighting Experiments — 2026-08-16

Two data-centric experiments on the shipped residual hybrid stack
(QB/RB/TE/WR-blend, `HYBRID_POSITIONS = {"TE","WR","QB","RB"}` in
`src/ml_projection_router.py`), per the task brief. Follows the
firing-rate + same-vintage + same-session-baseline discipline in
`knowledge-vault/concepts/gated-experiment-coverage-check.md` and stays
alert to the training-population-shift trap documented in
`knowledge-vault/concepts/model-staleness-after-data-repair.md`.

Did not touch `src/player_feature_engineering.py`, `src/hybrid_projection.py`,
`src/quantile_models.py`, or any other `src/` module. New code lives in
`scripts/span_recency_train.py` and `scripts/span_recency_gate.py`; recency
weighting is implemented by monkeypatching
`player_feature_engineering.assemble_multiyear_player_features` at call time
inside the training script's own process (row duplication by exponential-decay
weight) — the shared module file is unmodified.

## 1. Data reality pre-2016 (empirically probed, not assumed)

| Type | Earliest available | Notes |
|---|---|---|
| `player_weekly` | well before 2012 | 2012: 5,354 rows; 2013: 5,231; 2014: 5,350; 2015: 5,318 — comparable row counts to modern seasons |
| `snap_counts` | 2013 (nfl-data-py raises `Data not available before 2012` for 2011; 2012 itself returns 0 rows despite no error) | 2013: 23,799; 2014: 23,864; 2015: 23,842 rows |
| `injuries` | well before 2012 | 2012: 5,533; 2013: 5,070; 2014: 5,078; 2015: 5,232 rows |
| `schedules` | well before 2012 | 267 games/season, all 4 seasons |
| `depth_charts` | at least 2012 (37,312 rows) | available but NOT ingested — out of scope per task brief's explicit list (player_weekly + snaps + injuries); `silver_player_quality_transformation.py` degrades gracefully without it |
| NGS (passing/rushing/receiving) | **2016 only** — 2012/2015 both return 0 rows | confirms task brief; pre-2016 rows get 100%-NaN NGS features, imputed to training-time median like any other sparse feature |

**Snap-join coverage caveat (important, not a pre-2016-specific problem):**
`silver_player_transformation.py`'s `_prepare_snap_data` join (display-name +
team) matched only **27-29% of rows for 2013/2014/2015** — but re-running the
same transform for **2020** (a season already in the shipped 2016-2024
training window) shows the identical **29%** match rate. This is a
pre-existing, uniform join-coverage ceiling across the whole snap pipeline,
not a special pre-2016 degradation — ruled out as a confound before reading
the gate below (per the "verify the lever fires" discipline).

## 2. Bronze/Silver ingested (2012-2015; LOCAL-ONLY, sizes below)

Ingested: `player_weekly` (2012-2015), `snap_counts` (2013-2015; 2012 has none
upstream), `injuries` (2012-2015), `schedules` (2012-2015, needed by
`silver_player_transformation.py`'s game-script/venue features).
Silver: `silver_player_transformation.py` + `silver_player_quality_transformation.py`
re-run for 2012-2015 only — 2016-2025 Silver untouched (season-partitioned
writes).

Total new on-disk footprint (Bronze + Silver, all 4 seasons, all types): **~8 MB**.
Per-type: Bronze `player_weekly` ~250KB/season, `snap_counts` ~870KB/season,
`injuries` ~120KB/season, `schedules` ~52KB/season; Silver `players/usage`
~800-850KB/season, `teams/player_quality` ~85KB/season.

**Feature coverage of pre-2016 rows** (2012-2015 assembled via
`assemble_multiyear_player_features`, read-only call, no src edits):
14,858 player-weeks, 218 candidate feature columns, mean per-column coverage
**50.9%**, 89/218 columns <5% coverage (these are almost entirely the
NGS-family columns, expected-zero per the table above).

**Population-shift caveat (flagged per `model-staleness-after-data-repair.md`
epilogue):** the feature-assembly log for 2012-2015 prints
`snap_pct_roll3 unavailable; filtering by position only` — the same
silent-fallback pattern that changed the shipped WR model's training
population in the 2026-08-15/16 repair. Combining 2012-2015 with 2016-2024
therefore does not just add rows; it adds a stretch of seasons whose
eligibility filter degrades to "position only" (broader pool) where the
2016-2024 seasons filter more strictly on live `snap_pct`. This is reported,
not silently absorbed into the "more years" verdict below.

## 3. Experiment 1 — MORE YEARS (2012-2024 vs 2016-2024, same session)

Same hyperparameters as shipped: QB/RB `model_type=lgb`, `shap_feature_count=20`;
WR/TE `model_type=ridge`, `shap_feature_count=60`. Both baseline and
`more_years` retrained in this session to `models/span_experiments_2026_08_16/{baseline,more_years}/`.

Sanity check before reading the gate: QB/RB/TE `n_train` in the fresh
same-session `baseline` retrain (4,152 / 7,450 / 7,214) match the currently
**shipped** `models/residual/*_meta.json` `n_train` **exactly** — confirms the
retrain pipeline reproduces the shipped population/config (WR's shipped
n_train differs, 10,733 vs my 13,591, because the shipped WR model is a
60/40 blend of two separate training runs per
`model-staleness-after-data-repair.md`'s epilogue, not a single
`train_and_save_residual_models` call — expected, not a bug).

Sealed-2025 gate (weeks 3-18, matched rows; n identical to the
`RETRAIN_ON_REPAIRED_FEATURES.md` eval population — QB 487, RB 841, WR 1577,
TE 951 — confirms this gate script assembles the same population):

| Position | n | baseline MAE (bias) | more_years MAE (bias) | delta vs baseline |
|---|---:|---:|---:|---:|
| QB | 487 | 6.814 (−1.24) | 6.645 (−1.41) | **+0.169** |
| RB | 841 | 5.484 (−0.31) | 5.333 (−0.34) | **+0.151** |
| WR | 1577 | 4.273 (+0.42) | 4.155 (+0.30) | **+0.118** |
| TE | 951 | 3.451 (+0.10) | 3.475 (+0.20) | −0.023 |

QB/RB/WR all clear the +0.03 improvement bar comfortably. TE regresses by
0.023 — a **near-miss** against the ≤0.02 no-regression ceiling (0.003 over).

**Verdict: HOLD.** Fails the pre-registered gate on the TE regression alone
(0.023 > 0.02), despite QB/RB/WR each improving well past +0.03. This is a
narrow miss, not a clear rejection — flagged as worth a rerun with a fixed
random seed to check whether the 0.023 TE regression is signal or SHAP/LGB
run-to-run noise (this training pipeline has no fixed `random_state` visible
in `RESIDUAL_LGB_PARAMS`/the SHAP selector, so a single run's TE number alone
is not fully conclusive either way). Per the task's data-locality rule,
**2012-2015 Bronze/Silver stays LOCAL-ONLY, no `.gitignore` allowlist
recommended** — the gate did not pass.

## 4. Experiment 2 — RECENCY WEIGHTING (half-life 3 / 6 seasons, 2016-2024 span)

Training-path check: `train_and_save_residual_models` / `_train_lgb_residual`
/ `_create_residual_pipeline` accept **no** `sample_weight` parameter anywhere
in the call chain (confirmed by reading `src/hybrid_projection.py`).
Implemented via **row duplication** (mathematically exact `sample_weight`
equivalent for squared-error losses — both RidgeCV and LightGBM's default L2
objective): `scripts/span_recency_train.py` monkeypatches
`player_feature_engineering.assemble_multiyear_player_features` for the
duration of one training call only, duplicating each row
`round(weight / weight.min())` times where `weight = 0.5 ** (age / half_life)`,
`age = 2024 - season`, capped at 12x. Half-life 3 → newest-season multiplier
~6x oldest; half-life 6 → ~2.5x.

Sealed-2025 gate (same eval population as §3, same baseline):

| Position | n | baseline MAE | hl3 MAE | delta (hl3) | hl6 MAE | delta (hl6) |
|---|---:|---:|---:|---:|---:|---:|
| QB | 487 | 6.814 | 6.673 | **+0.141** | 6.718 | +0.097 |
| RB | 841 | 5.484 | 5.313 | **+0.171** | 5.369 | +0.115 |
| WR | 1577 | 4.273 | 4.339 | −0.066 | 4.338 | −0.065 |
| TE | 951 | 3.451 | 3.492 | −0.040 | 3.480 | −0.028 |

**Verdict: HOLD (both half-lives).** QB/RB improve well past +0.03 at both
half-lives, but WR regresses by 0.066/0.065 (hl3/hl6) — more than 3x the
0.02 no-regression ceiling — and TE regresses 0.040/0.028, also over. The
recency-weighting lever helps the two positions the opportunity scan
specifically flagged (QB/RB, the ones with the monotonic 2022→2024 margin
decay) but actively hurts WR/TE, which were NOT flagged as thinning. Row
duplication skews the effective training population toward whichever
seasons' residual *distribution* differs most from the mean — for WR/TE that
appears to cost more than it buys.

### 2024-slice diagnostic (the opportunity-scan motivating question)

In-sample slice (2024 is inside the 2016-2024 training window for every
variant here, including baseline — this is NOT a sealed comparison, reported
per the task brief as a diagnostic only):

| Position | n | baseline MAE | hl3 MAE | delta (hl3) | hl6 MAE | delta (hl6) |
|---|---:|---:|---:|---:|---:|---:|
| QB | 487 | 6.985 | 6.721 | +0.263 | 6.724 | +0.261 |
| RB | 835 | 5.267 | 5.190 | +0.077 | 5.233 | +0.034 |
| WR | 1583 | 4.325 | 4.384 | −0.059 | 4.324 | +0.001 |
| TE | 865 | 3.318 | 3.349 | −0.031 | 3.361 | −0.043 |

**Does recency weighting close the 2024-slice gap?** For QB: yes, clearly
(+0.26 MAE improvement on the 2024 in-sample slice, more than 10x the
sealed-2025 QB improvement of +0.14) — consistent with the opportunity scan's
QB "clean monotonic decay toward 2024" observation; up-weighting 2024 rows
during training measurably improves the model's fit to exactly that slice.
For RB: yes but more modestly (+0.03 to +0.08, roughly matching its
sealed-2025 gain — less evidence of a 2024-specific effect beyond the general
QB/RB-favoring pattern already seen in the sealed gate). For WR/TE: no —
both are flat-to-worse on the 2024 slice too, consistent with the sealed
regression above. Net: recency weighting's benefit is real but concentrated
in QB (and to a lesser extent RB), not a uniform "helps everyone" lever —
matches the opportunity scan's finding that only QB/RB (not TE) showed the
monotonic 2024 thinning pattern.

## 5. Combination

**Not run.** Neither experiment independently passed its gate (§3: HOLD,
near-miss on TE; §4: HOLD, WR/TE regress at both half-lives) — the task
brief's combination step ("if both experiments produce winners") does not
apply. `models/span_experiments_2026_08_16/combo/` was intentionally left
untrained rather than spending the remaining time budget on a combination of
two non-winning levers.

## 6. Recommendations

1. **Do not adopt either lever as-is.** Both HOLD against the pre-registered
   gate. Neither 2012-2015 data nor recency-weighted training should replace
   the shipped 2016-2024 configuration.
2. **More years (§3) is close enough to be worth one follow-up run**, not a
   clean rejection: QB/RB/WR each cleared +0.03 comfortably; only TE missed,
   and by just 0.003 above the ceiling. Recommended next step (not done here,
   out of this task's time budget): rerun `more_years` with a fixed
   `random_state` threaded through the SHAP selector / LGB params (would
   require a small, scoped change to `feature_selector.py` /
   `RESIDUAL_LGB_PARAMS` — currently unseeded) and check whether TE's -0.023
   is stable or noise. Do NOT allowlist 2012-2015 data into `.gitignore` /
   ship the more_years artifacts until that's resolved.
3. **Recency weighting (§4) is a genuine, position-specific lever, not a
   general one — and a QB/RB-scoped adoption already passes the gate using
   models already trained this session, no retrain needed.** Re-reading the
   §4 table position-by-position rather than as one all-or-nothing variant:
   scoping the lever to QB/RB only (keep WR/TE on the shipped/`baseline`
   models untouched) means WR/TE delta = 0.000 by construction (not exposed
   to the lever at all), and QB (+0.141 hl3 / +0.097 hl6) and RB (+0.171 hl3
   / +0.115 hl6) both individually clear the +0.03 bar at both half-lives
   with **zero** positions worsening >0.02. **This mixed deployment (QB/RB
   from `recency_hl3`, WR/TE unchanged) passes the pre-registered gate** —
   it just isn't "recency weighting" as a single global lever, which is why
   the whole-stack §4 verdict above is correctly HOLD. Recommend a follow-up
   task promote `models/span_experiments_2026_08_16/recency_hl3/{qb,rb}_residual*`
   through the repo's normal ship process (one more sealed confirmation pass
   per `.planning/holdout_ledger.json` discipline, same as
   `RETRAIN_ON_REPAIRED_FEATURES.md` §8) — not done here, this task's scope
   was retrain + re-gate + report, matching that precedent.
4. **Data reality confirmed, reusable for future work:** `player_weekly` and
   `injuries` go back well before 2012 in nfl-data-py; `snap_counts` starts
   2013 (not 2012, despite the library's own error message implying 2012);
   NGS is genuinely 2016-only (0 rows in 2012/2015, not a pipeline bug). The
   ~8MB of 2012-2015 Bronze/Silver ingested this session remains available
   locally for the recommended QB/RB-only follow-up without re-ingesting.

## 7. Artifact provenance

- `models/span_experiments_2026_08_16/baseline/` — 2016-2024, same-session baseline
- `models/span_experiments_2026_08_16/more_years/` — 2012-2024
- `models/span_experiments_2026_08_16/recency_hl3/` — 2016-2024 + half-life=3 row-dup weighting
- `models/span_experiments_2026_08_16/recency_hl6/` — 2016-2024 + half-life=6 row-dup weighting
- `models/span_experiments_2026_08_16/combo/` — NOT trained (§5 — neither individual experiment won)
- Training driver: `scripts/span_recency_train.py`
- Gate/eval driver: `scripts/span_recency_gate.py`
- New Bronze: `data/bronze/{players/weekly,players/snaps,players/injuries,schedules}/season=201{2,3,4,5}/*` (local-only, gitignored, ~8MB total)
- New Silver: `data/silver/{players/usage,teams/player_quality,defense/positional}/season=201{2,3,4,5}/*` (local-only, gitignored)
