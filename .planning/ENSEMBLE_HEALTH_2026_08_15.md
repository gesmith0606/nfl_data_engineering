# Ensemble Health Check — 2026-08-15

Scope: `models/ensemble/` (XGB+LGB+CB+Ridge stacking, spread+total, 120 SHAP-selected
features). Question: is it healthy on today's repaired data, and did the repair change what
it could learn? Read-only on `src/`/`scripts/`; only writes are this report and
`models/ensemble_retrained_2026_08_15/`.

## Pre-registered gate (written before step 4 ran)

> Recommend redeploy only if retrained OOF ATS improves **≥0.5 points** over shipped **AND**
> the sealed-2025 holdout does not degrade. Otherwise keep shipped.

## 1. Artifact inventory

`models/ensemble/` (12 files):

| File | Modified | Note |
|---|---|---|
| `xgb_spread.json`, `xgb_total.json` | Jun 24 13:30 | checkout timestamp |
| `cb_spread.cbm`, `cb_total.cbm` | Jun 24 13:30 | checkout timestamp |
| `ridge_*.pkl`, `calibrator_*.pkl` | Jun 24 13:30 | checkout timestamp |
| `oof_spread.parquet`, `oof_total.parquet` | Jun 24 13:30 | walk-forward OOF preds, n=1599/target |
| `lgb_spread.txt`, `lgb_total.txt` | **Aug 10 14:36** | rewritten by the CRLF fix |
| `metadata.json` | Jun 24 13:30 | `ensemble_version: "3.0"`, `trained_at: 2026-06-10T02:36:12Z` |

- `.gitattributes` pins `models/ensemble/lgb_*.txt -text` (added 2026-08-10, per
  `SMALL_FIXES_2026_08_10.md`) so Windows `core.autocrlf` can never re-corrupt the LightGBM
  text-format byte-offset headers again. **Confirmed present and correctly scoped.**
- **Load test (this session):** `src.ensemble_training.load_ensemble()` loads all 4 model
  types for both targets cleanly — `lgb_spread` 81 trees, `lgb_total` 1 tree,
  `xgb_spread.n_features_in_ == 120`. No corruption. The Aug 10 CRLF fix holds.
- Training seasons: 2016–2024. Holdout: 2025 (sealed). Meta-learner: `mean` (equal-weight
  average of XGB/LGB/CB — Ridge stacking was CV-tested but the mean beat it, so
  `ridge_coefficients = [0.333, 0.333, 0.333]` for both targets; the Ridge artifact is loaded
  but effectively a pass-through).
- **Number provenance correction:** the task brief's "52.92% OOF ATS, +$3.09 sealed-2024
  holdout" conflates two different model generations. **+$3.09 / 53.0% ATS on sealed-2024**
  is the **v2.0** model (Phase 31, shipped 2026-03-27 — `MILESTONES.md` line 369) —
  superseded, not what's in `models/ensemble/` today. **52.92% OOF ATS** is the currently
  shipped **v3.0** model (trained 2026-06-10, holdout season **2025**, not 2024). The v3.0
  metadata's own sealed-2025 holdout check was mixed at ship time (mean-meta spread ATS
  50.92% vs legacy-ridge 53.87%; mean-meta was still selected because CV/OOF selection is the
  documented decision basis, not the single-use holdout). This report treats 52.92% OOF ATS +
  the 2025 holdout as the correct baseline for the currently shipped artifacts.

## 2. Feature coverage delta

`src/feature_engineering.py::assemble_game_features()` — the game-ensemble's only feature
source — reads exclusively from `SILVER_TEAM_LOCAL_DIRS` (`teams/pbp_metrics`, `tendencies`,
`sos`, `situational`, `pbp_derived`, `game_context`, `referee_tendencies`, `playoff_context`,
`player_quality`, `market_data`). It never reads `players/usage` or `players/advanced` — those
feed only the player-level fantasy pipeline (`src/player_feature_engineering.py`). **This
matters: the Aug 9–10 repair (snap_pct join-bug fix in `players/usage`, NGS/PFR/QBR ingestion
into `players/advanced`) touched exactly the two Silver paths the game ensemble never reads.**
None of the 120 selected features are graph-derived either (no graph-prefixed feature is in
the SHAP-selected list at all — graph features aren't part of this model).

Built the real feature vector for all 10 seasons (2016–2025) via
`assemble_game_features()` and measured non-NaN coverage for each of the 120 selected
features:

| Season | Rows | Features present | Majority-NaN (<50%) |
|---|---|---|---|
| 2023 | 272 | 120/120 | 0 |
| 2024 | 272 | 120/120 | 0 |
| 2025 | 272 | 120/120 | 0 |

**Zero of the 120 shipped features are majority-NaN today, and zero were snap/advanced-derived
to begin with** — so the framing "which selected features were majority-NaN and are real now"
doesn't apply to this model; that's a fantasy-projection-pipeline story, not a game-ensemble
one. Coverage floor across all 10 seasons is legitimate football sparsity, not missing data:

| Feature | Min coverage (any season) | Why |
|---|---|---|
| `diff_fg_pct_long_roll3` | 50.7% | only non-NaN in games with a long-FG attempt in the trailing window |
| `diff_leading_off_epa_roll3` / `_leading_def_epa_roll3` | 55–56% | only defined for teams that led recently |
| `diff_trailing_off_epa_roll3` / `_trailing_def_epa_roll3` | 65% | same — trailing-game-state conditional |
| `diff_fourth_down_success_rate_roll3` | 66% | only teams that went for it on 4th |
| `temperature_away` | 66% | domes have no temperature reading |

113/120 features have <99.9% coverage in at least one season, all of the same
situational/conditional character (leading/trailing splits, FG distance buckets, weather).
None fall below 50%.

**But the repair did change one thing the ensemble consumes — the 2025 holdout season's
`teams/player_quality` Silver, not the training seasons.** Diffing the pre- vs post-repair
`player_quality` parquet for `season=2025` (both dated in the file, old=Apr 30, new=Aug 9
22:07):

| Feature | Rows differing (of 570) |
|---|---|
| `skill_injury_impact` | 400 (70%) |
| `def_injury_impact` | 495 (87%) |
| `qb_injury_impact` | 87 (15%) |
| `rb_weighted_epa` | 11 (2%) |

Same shape (570 rows × 28 cols) both times — this is a value refresh, not a schema or
row-count change (likely from re-running against refreshed injury/depth-chart Bronze during
the Aug 9 `player_quality` re-verification pass, per `SILVER_REGEN_REPORT.md`). Spot-checked
three training seasons (2020, 2022, 2023) for the same before/after pair: **all three are
byte-identical** (same file size to the byte), confirming training-season inputs are
untouched. **Net effect: the repair left the model's 2016–2024 training data bit-for-bit
identical, but materially changed the values the sealed-2025 holdout evaluation now sees**
(explored quantitatively in step 3).

## 3. Reproduce-check (shipped model, current data)

**OOF ATS (from `models/ensemble/oof_{spread,total}.parquet`, walk-forward CV predictions
saved at training time — these don't depend on today's data, they reproduce by construction):**

Recomputed via the same `evaluate_ats`/`evaluate_ou` logic `backtest_predictions.py` uses:

| | n (non-push) | ATS/O-U | Profit | ROI |
|---|---|---|---|---|
| Spread OOF | 1557 of 1599 | **52.92%** | +16.09u | +1.03% |
| Total OOF | 1582 of 1599 | 49.81% | -77.64u | -4.91% |

**Spread OOF ATS reproduces exactly: 52.92%, matching the documented figure to the basis
point, n=1557 matching the metadata's own "n=1557 OOF" note.** Documented number confirmed
correct as-is — no drift, since this is a fixed artifact independent of today's Silver state.

**Live re-run against current data — `scripts/backtest_predictions.py --ensemble --seasons
2025`** (the sealed holdout, genuinely out-of-sample since 2025 was excluded from training):

| | Shipped model, current data | Metadata's ship-time holdout_check (2026-06-10) | Delta |
|---|---|---|---|
| Spread ATS | 51.7% (140-131-1, n=271 non-push) | 50.92% (mean-meta) | +0.8pt |
| Spread profit | -3.73u | n/a (MAE-only in ledger) | — |
| Total O/U | 48.9% (133-139-0) | 48.90% | 0.0pt (exact) |

Total O/U reproduces to the decimal. Spread ATS drifted +0.8pt — **this is the 2025
`player_quality` value refresh from step 2 showing up**, not data corruption or a pipeline
break: the model weights are unchanged, only the 2025 injury/EPA feature *values* it's scored
against shifted. A ~0.8pt swing on a 271-game sealed sample from a genuine (not spurious)
mid-season data correction is unremarkable, not a red flag.

**Full-season backtest (2016–2025, in-sample + holdout combined) for context only — do not
compare to the 52.92% OOF figure, this is NOT out-of-sample:** 68.5% ATS, +$793.64/+30.8%
ROI. Expected to look far better than OOF since 2016–2024 games were seen during training;
included here only to confirm the pipeline runs end-to-end on all 10 seasons without error.

**Verdict: documented numbers reproduce.** No drift on the fixed OOF figures (exact match).
Small, explained drift (+0.8pt ATS, 0.0pt O/U) on the sealed-2025 holdout, fully attributable
to the real (not corrupting) `player_quality` refresh identified in step 2. No red flags.

## 4. Retrain comparison (no tuning, default params)

`python scripts/train_ensemble.py --ensemble-dir models/ensemble_retrained_2026_08_15
--features-from models/ensemble/metadata.json` — reused the shipped 120-feature list so the
comparison isolates "same features, current data" rather than confounding with a fresh
feature-selection pass. Ran in **12.3s** (well under the 10-minute ceiling — no chunking
needed).

| Metric | Shipped (trained 2026-06-10) | Retrained (2026-08-15) | Delta |
|---|---|---|---|
| Spread XGB CV MAE | 10.0921 | 10.0813 | -0.011 |
| Spread LGB CV MAE | 10.0858 | 10.0858 | 0.000 |
| Spread CB CV MAE | 10.0923 | 10.0923 | 0.000 |
| Spread meta (mean) CV MAE | 10.0387 | 10.0307 | -0.008 |
| Total meta (mean) CV MAE | 10.8999 | 10.8950 | -0.005 |
| **Spread OOF ATS** | **52.92%** | **52.86%** | **-0.06pt** |
| Total OOF O/U | 49.81% | 49.94% | +0.13pt |
| Spread sealed-2025 holdout ATS | 51.7% (140-131-1) | 50.2% (136-135-1) | -1.5pt |
| Spread sealed-2025 holdout profit | -3.73u | -11.36u | -7.63u |
| Total sealed-2025 holdout O/U | 48.9% | 48.9% | 0.0pt |

Both runs selected the same meta-learner (`mean`, equal-weight) and produced near-identical
per-base-model CV MAE — confirming what step 2 predicted: **since 2016–2024 training-season
Silver is bit-for-bit unchanged, retraining on "current" data reproduces essentially the same
model.** The tiny residual differences (CV MAE to the 3rd decimal, OOF ATS -0.06pt) are
training noise (walk-forward CV fold refits, early-stopping, floating point) — not signal.
The sealed-2025 holdout drop (-1.5pt ATS) reflects the same `player_quality` value refresh
from step 2 hitting the *retrained* model's holdout scoring too, compounded with normal
retrain-to-retrain noise; it is not evidence the retrained model generalizes worse.

**Gate check:**
- OOF ATS improved ≥0.5pt? **No — it went down 0.06pt.**
- Holdout didn't degrade? **No — ATS -1.5pt, profit -7.63u worse.**

**Verdict: KEEP SHIPPED. Do not redeploy.** Neither gate condition is met; the retrain is a
noise-level replica of the shipped model, not an improvement. `models/ensemble_retrained_
2026_08_15/` is left on disk as evidence but should not be promoted.

## Bottom line

- **Artifact health: GOOD.** All 12 shipped files load cleanly; the Aug 10 CRLF fix
  (`.gitattributes`) is in place and verified working end-to-end (81-tree `lgb_spread`
  loads).
- **Repair impact on this model: none on training, small-but-real on holdout scoring.** The
  Aug 9–10 repair fixed `players/usage`/`players/advanced` (fantasy-pipeline-only paths this
  ensemble never reads) and, as a side effect of the same session, refreshed
  `teams/player_quality` for the 2025 season only (training seasons 2016–2024 are
  byte-identical before/after). The game ensemble's 120 features were never majority-NaN and
  aren't snap/advanced-derived — the "did the repair unlock new signal" framing doesn't apply
  here; that would show up in the fantasy projection models instead.
- **Documented numbers: reproduce.** 52.92% OOF ATS matches exactly. Sealed-2025 holdout
  drifted +0.8pt ATS / 0.0pt O/U vs the ship-time number, fully explained by the real
  `player_quality` 2025 refresh, not corruption or pipeline drift.
- **Retrain verdict: keep shipped, do not redeploy.** Pre-registered gate not met in either
  direction (OOF flat-to-slightly-down, holdout down). Ran to completion in 12s — no blocker,
  no chunking needed.

## Files touched

- `models/ensemble_retrained_2026_08_15/` — new retrained artifacts (12 files), for
  comparison only, not recommended for promotion.
- `.planning/ENSEMBLE_HEALTH_2026_08_15.md` — this report.
