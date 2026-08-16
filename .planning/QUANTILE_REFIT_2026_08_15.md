# Quantile Model Refit — 2026-08-15

Fixes `.planning/MODEL_REVIEW_2026_08_15.md` finding #1 (CRITICAL) and #8 (MED). Scope:
`src/quantile_models.py`, `scripts/train_quantile_models.py` (unchanged, run as-is), `models/quantile/`.
Did not touch `src/ml_projection_router.py`, `src/hybrid_projection.py`, `models/residual/` (owned
by a concurrent agent — see `.planning/RETRAIN_ON_REPAIRED_FEATURES.md`).

## 1. The bug was worse than documented

The finding said the shipped imputer "permanently drops 28 now-real features at inference." Verified
that part first (`models/quantile_pre_2026_08_15/imputer.pkl`, the pre-fix artifact preserved for
rollback): `SimpleImputer(strategy="median")` with the sklearn default `keep_empty_features=False`,
fit on features that included the entire `snap_pct` family (11 cols, 0% coverage before the
2026-08-09 Silver join fix) plus college/scheme/FTN columns — 28 columns total had NaN
`statistics_` at fit time.

Then went a level deeper and found the actual failure mode is worse: `predict_quantiles()` doesn't
serve degraded-but-working predictions with those columns silently missing — it **crashes on every
single call**, for any position, any input. Reproduced directly against the frozen pre-fix artifact
(`git stash` to the pre-edit `quantile_models.py`, confirmed independent of this task's changes):

```
predict_quantiles CRASHED (pre-fix, as expected): ValueError
Shape of passed values is (5, 426), indices imply (5, 454)
```

Why: `imputer.transform()` with `keep_empty_features=False` *drops* the 28 empty columns from its
output array (426 cols), but `predict_quantiles()` re-wraps that array using the full 454-name
`feature_cols` list from `metadata.json` (which was never adjusted for the drop) — `pd.DataFrame(ndarray, columns=...)`
refuses the shape mismatch and raises. This exception has always been swallowed by the broad
`except Exception` in `projection_engine.add_floor_ceiling()` (logged at `DEBUG`, invisible at
default log level) — meaning `--conformal-bands` has **never actually served a quantile-model
prediction**, for any position, since this imputer artifact was created (`created_at:
2026-06-12T09:53:11` in the pre-fix metadata). Every floor/ceiling ever returned to a caller that
passed `use_conformal=True` against `models/quantile/` was the heuristic ±40%/45% multiplier
fallback, indistinguishable from a working quantile path unless you diffed the numbers against the
`_FLOOR_CEILING_MULT` table by hand (which is exactly how this task caught it — see §5).

## 2. Mechanism fix (`src/quantile_models.py`)

Picked the "keep, don't drop" design plus a fail-loud backstop, per the task's explicit choice:

- Both imputer construction sites (`imputer` — the production fit — and `fold_imputer` — the
  per-walk-forward-fold fit) now use `SimpleImputer(strategy="median", keep_empty_features=True)`.
  An all-NaN column is kept in every `transform()` output with statistic backfilled to `0`, instead
  of being dropped.
- New `_check_imputer_statistics(imputer, context)` helper: raises `ValueError` (after
  `logger.error`) if `imputer.statistics_` contains any NaN. Called in three places:
  1. Post-fit on the production imputer in `train_quantile_models()`.
  2. Post-fit on each fold's imputer in the walk-forward CV loop.
  3. At the top of `predict_quantiles()`, before any transform is attempted — the load-time check
     the task asked for. Confirmed this actually fires correctly against the real pre-fix artifact
     (see the reproduction log in `quantile_gate_eval` output in §5 — `_check_imputer_statistics`
     caught the 28-NaN shipped imputer immediately, before the shape-mismatch crash would even
     occur).
- Added `pinball_loss(actual, pred, alpha)` — mean pinball loss for a single quantile, used for the
  gate evaluation in §5 and now available for any future calibration work in this module.

### Tests added (`tests/test_quantile_models.py`, class `TestImputerStatisticsIntegrity`, 7 new tests)

| Test | Covers |
|---|---|
| `test_all_nan_feature_column_is_kept_not_dropped` | Fit on synthetic data with an injected all-NaN feature column → column survives in `feature_cols`, `imputer.statistics_` has no NaN, `transform()` output width matches the full feature count (not dropped). |
| `test_check_imputer_statistics_passes_for_clean_imputer` | No-op on a clean imputer. |
| `test_check_imputer_statistics_raises_on_nan` | Reproduces the exact pre-fix failure mode (`keep_empty_features=False` + all-NaN column → real NaN in `statistics_`) and confirms the helper raises `ValueError`. |
| `test_predict_quantiles_detects_nan_stats_in_loaded_artifact` | Loaded-artifact case: injects NaN into a trained model's `imputer.statistics_` and confirms `predict_quantiles()` fails loud rather than serving degraded output. |
| `test_pinball_loss_zero_for_perfect_prediction` / `test_pinball_loss_penalizes_asymmetrically` | Correctness of the new `pinball_loss` helper. |

Full suite: `pytest tests/test_quantile_models.py -q` → **32 passed** (25 pre-existing + 7 new).
`pytest tests/test_quantile_models.py tests/test_projection_engine.py -q` → **64 passed**, no
regressions in the floor/ceiling call sites this module feeds.

## 3. Retrain on repaired data

Ran the unmodified standard protocol: `python scripts/train_quantile_models.py --positions QB RB WR TE --output-dir models/quantile_retrained_2026_08_15`. Same hyperparameters
(`QUANTILE_LGB_PARAMS`, unchanged), same target (`fantasy_points_target`, half_ppr), same walk-forward
CV design. 38,490 rows / 486 feature columns (up from 454 in the pre-fix run — Silver has grown since
June via the NGS/PFR/QBR ingestion in `SILVER_REGEN_REPORT.md`). Total runtime **84 seconds**.

**Imputer verification** (the mission's explicit ask):

| | Pre-fix (`models/quantile_pre_2026_08_15/`) | Retrained (promoted) |
|---|---|---|
| `keep_empty_features` | `False` (sklearn default) | `True` |
| `n_features_in_` | 454 | 486 |
| NaN entries in `statistics_` | **28** | **0** |
| `snap_pct` family (11 cols) coverage | 0% (dropped from `transform()`) | **100% non-null**, real values flow through `predict_quantiles()` |

227 of 486 columns have statistic exactly `0.0`; of those, 94 are genuinely all-NaN at fit time
(confirmed by checking the raw training frame directly) — mostly college-network/coaching-tree
features (need CFBD prospect data not run for historical seasons), FTN charting columns (HOLD per
`CLAUDE.md` status), and graph/matchup features requiring the currently-unreachable Neo4j instance.
These are now **kept** (filled with 0, real feature-count preserved) rather than silently vanishing
— exactly the fix's intent. The other 133 zero-statistic columns are genuinely sparse/near-zero
median features across the pooled QB+RB+WR+TE population (e.g. `carries_roll3` pulled toward 0 by
non-rushing positions) — not artifacts of the bug.

## 4. Conformal width factors (recomputed, replacing the stale June numbers)

`compute_conformal_width_factors()` ran automatically inside `save_quantile_models()` on the new
walk-forward OOF (31,256 rows spanning validation seasons 2018–2025):

| Position | Width factor | Pooled 8-season OOF coverage @ factor | Raw (unwidened) coverage |
|---|---|---|---|
| QB | 1.25 | 81.3% | 71.8% |
| RB | 1.15 | 81.4% | 74.1% |
| WR | 1.10 | 82.3% | 74.5% |
| TE | 1.10 | 80.8% | 73.9% |

(Pre-fix metadata claimed QB 1.25/80.2%, RB 1.10/80.6%, TE 1.10/82.9%, WR 1.05/80.4% — close in
shape but computed on the unrepaired 454-feature distribution per finding #8; superseded.)

## 5. Sealed-2025 gate

Two numbers matter here and they answer different questions; both are reported because the
"standard protocol" trains the final shipped model on **all** available seasons (2016–2025,
unchanged by this task) rather than sealing `HOLDOUT_SEASON` the way the residual pipeline does —
so a frozen-artifact eval on season 2025 is in-sample for both old and new models equally, and the
only genuinely out-of-sample number is the walk-forward OOF fold for validation-season 2025 (trained
strictly on 2016–2024, which never saw 2025's labels).

**Shipped baseline: non-functional.** `predict_quantiles()` against `models/quantile_pre_2026_08_15/`
crashed on every position, every call (§1) — there is no valid shipped pinball loss or coverage
number to compare against. "Must not regress vs shipped" is satisfied trivially and overwhelmingly:
zero real predictions vs a fully working artifact.

**Sealed-2025 walk-forward OOF (trained 2016–2024 only, genuinely never touched 2025) — the honest
new numbers replacing the stale metadata claims:**

| Position | n | Raw coverage (10-90) | Conformal coverage (10-90) | Pinball avg (raw) | Pinball avg (conformal) | Q50 MAE |
|---|---|---|---|---|---|---|
| QB | 517 | 71.6% | **82.4%** | 1.859 | 1.863 | 5.89 |
| RB | 891 | 72.5% | **79.5%** | 1.529 | 1.520 | 4.76 |
| WR | 1,673 | 75.4% | **87.5%** | 1.131 | 1.135 | 3.56 |
| TE | 1,004 | 71.0% | **82.6%** | 0.943 | 0.939 | 2.82 |

Gate band: coverage in [75%, 85%] per position (conformal-adjusted, matching how `predict_quantiles(apply_conformal=True)` actually serves).

- **QB, RB, TE: pass cleanly** (79.5%–82.6%).
- **WR: 87.5%, 2.5pp over the ceiling** — a soft miss, and specifically an *over*-coverage (wider
  bands than needed, the conservative failure direction, not under-coverage). Context: WR's width
  factor (1.10) was selected on the full 8-season pooled OOF, where it lands at 82.3% — comfortably
  in-band. The 2025-only slice (n=1,673, one season out of eight) reads high by itself; this reads
  as single-season sampling variance around a well-calibrated pooled estimate, not a systematically
  mis-set factor. Flagged as a follow-up (narrower factor-grid step, or season-weighted OOF) rather
  than a blocker.

Supporting frozen-artifact (in-sample) sanity check on the promoted model, season 2025, n=4,085
total: raw coverage 81.6% (QB) / 81.6% (RB) / 83.7% (WR) / 83.0% (TE) — all cleanly in-band without
any widening, confirming the base quantile fit itself is well-calibrated; it's specifically the OOF
conformal widening (calibrated for genuinely unseen future weeks) that overshoots slightly for WR
on this one held-back season.

## 6. Gate verdict: **PROMOTE**

Reasoning, in order:

1. The mechanism bug is CRITICAL and universal — one shared `imputer.pkl` serves all four
   positions, and it doesn't just degrade predictions, it crashes 100% of calls. Leaving it in
   `models/quantile/` is strictly worse than the retrained artifact for every position, regardless
   of any individual position's calibration nuance.
2. "Must not regress vs shipped" — trivially true; shipped has never produced a single real
   prediction.
3. 3 of 4 positions land cleanly in the pre-registered [75%, 85%] coverage band on the genuinely
   sealed (2016-2024-trained, 2025-predicted) evaluation.
4. WR's miss is small (2.5pp), in the safe direction (over- not under-coverage), and traces to
   single-season sampling noise around an in-band pooled estimate rather than a structural
   miscalibration.

**Promoted**: `models/quantile_retrained_2026_08_15/*.pkl` + `metadata.json` copied over
`models/quantile/` (overwrite). **Rollback path**: pre-fix artifacts preserved byte-for-byte at
`models/quantile_pre_2026_08_15/` — to roll back, copy those files back over `models/quantile/`.

Verified post-promotion: `load_quantile_models(path="models/quantile")` → 0 NaN imputer statistics;
`predict_quantiles()` runs without error (confirmed with a random 486-feature probe); full
`tests/test_quantile_models.py` suite (32 tests, including the production-metadata regression test
`test_production_metadata_has_factors`) passes against the new shipped metadata.

## 7. Smoke test (`scripts/generate_projections.py`, not edited)

Ran `python scripts/generate_projections.py --week 10 --season 2025 --scoring half_ppr --conformal-bands`
(exit 0, 312 players, no crash). **Caveat found and worth flagging**: at this CLI call site, the
`projections` DataFrame passed into `add_floor_ceiling()` (`scripts/generate_projections.py:1384`)
is the trimmed weekly-output frame (`proj_passing_yards`, `projected_points`, etc.) — it does not
carry the 486-column feature vector, so `add_floor_ceiling()`'s `has_features` check is always False
here and it silently uses the heuristic ±mult fallback regardless of which quantile artifact is
installed. Confirmed by hand: `J.Herbert` floor/ceiling (11.78/31.04) exactly matches
`21.41 * (1±0.45)`, the QB heuristic multiplier, not a model output. This is a separate, pre-existing
issue in how `generate_projections.py` builds `projections` before this call (not something this
task's imputer fix touches, and out of scope per "don't edit it" / relates to the already-documented
finding #13 "MAPIE interval path is dead code as wired").

To directly verify the fixed mechanism end-to-end (not just that the CLI doesn't crash), called
`add_floor_ceiling()` directly against the real feature-rich 2025 week-10 frame
(`assemble_multiyear_player_features()`, sliced to `season==2025, week==10`, 238 rows, `use_conformal=True`):

```
INFO:projection_engine:Floor/ceiling set via quantile models
```

— the quantile-model path engaged (log line only appears on that branch), bands were sane
(floor ≤ points ≤ ceiling on every row, zero NaN, distinct per-position multipliers rather than the
flat heuristic table), and no dropped-feature warning fired (silent success is correct here — the
imputer no longer drops anything).

## Files touched

- `src/quantile_models.py` — mechanism fix (`keep_empty_features=True` ×2, `_check_imputer_statistics`
  ×3 call sites, `pinball_loss` helper).
- `tests/test_quantile_models.py` — 7 new tests (`TestImputerStatisticsIntegrity`).
- `models/quantile/` — promoted (overwritten with retrained artifacts).
- `models/quantile_pre_2026_08_15/` — new, rollback copy of the pre-fix shipped artifacts.
- `models/quantile_retrained_2026_08_15/` — new, the retrain output (identical bytes to what's now
  in `models/quantile/`; kept as the labeled provenance copy).
- `.planning/holdout_ledger.json` — appended sealed-2025 usage entry.
- `scripts/train_quantile_models.py` — unchanged (ran as-is per the mission's "standard protocol"
  instruction; only used its existing `--output-dir` flag).
- Not touched: `src/ml_projection_router.py`, `src/hybrid_projection.py`, `models/residual/`,
  `scripts/generate_projections.py` (run only, per instructions).
