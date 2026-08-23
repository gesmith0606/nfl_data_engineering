# Ensemble Team-EP-Aggregate Features — Gated Re-Experiment (2026-08-21)

Pre-registered **before** any OOF/sealed results were run. This is a re-gate
of the same *shape* of experiment as the 2026-08-16 attempt
(`.planning/ENSEMBLE_PLAYER_FEATURES_2026_08_16.md`, verdict **HOLD**), but
with genuinely new input data.

## What's new vs. the 2026-08-16 HOLD

The 08-16 attempt aggregated `players/usage` + `players/advanced` (snap
shares, dakota, NGS/PFR metrics) into team-week features. It passed the OOF
bar (+1.22pt ATS) but **failed the sealed-2025 holdout** (-2.25pt ATS) and a
confound-isolation control confirmed the signal was CV-only (overfit to
training-period role patterns, didn't generalize forward).

This experiment uses **`data/silver/ffopportunity_features/`** — gsis-keyed
player-week *expected fantasy points* data (ffopportunity xgboost model
outputs: expected yards/TDs/fantasy-points per play, aggregated to
player-weeks; see `.planning/FFOPPORTUNITY_COVERAGE.md`). This dataset **did
not exist** at the time of the 08-16 attempt (ingested 2026-08-18) — it is
not a re-run of the same feature set, it targets a different hypothesis
(opportunity volume + regression-to-expectation, not usage/efficiency
composites) from a source with **no overlap** in underlying columns with
`players/usage`/`players/advanced`. Coverage is also better in early seasons
(ffopportunity covers 2016 at full weeks; NGS/PFR-derived 08-16 features were
~0% in 2016-2017 because those Bronze feeds start ~2018).

## Hypothesis

Team-level aggregates of player expected-points data improve game
predictions (ATS/totals):
- Trailing team offense expected output (summed `exp_fantasy_points_total`
  and its pass/rush/rec role components).
- Actual-minus-expected regression signal: teams overperforming expectation
  regress (summed `fantasy_points_over_expected`, plus a raw-TD variance
  analog).
- Opportunity concentration: how concentrated a team's targets+carries are
  among fewer players (Herfindahl), and RB-specific rushing-workload
  concentration.

An old opportunity scan hinted ~0.8pt ATS from player-derived signals.

## Feature design (9 raw team-week metrics → 27 candidates)

Mirrors the 08-16 construction exactly: same-week team sums/HHI computed in
`src/feature_engineering.py::_compute_ep_team_features()`, then
`team_analytics.apply_team_rolling()` shift(1)-lags them into
`_roll3`/`_roll6`/`_std` (9 × 3 = 27 candidate columns). Only those lagged
derivatives ever reach `get_feature_columns()`'s allowlist — the raw
same-week columns are computed but never exposed as model features (double-
layer discipline, same as the 08-16 and shipped `teams/player_quality`
features).

| Raw feature | Definition |
|---|---|
| `ep_team_exp_fp_total` | Team-week sum of `exp_fantasy_points_total` across all players — trailing team offense expected output |
| `ep_team_fp_over_expected` | Team-week sum of `fantasy_points_over_expected` — team-level actual-minus-expected regression signal |
| `ep_team_exp_pass_fp` | Sum of `exp_pass_fantasy_points` — passing-role expected output |
| `ep_team_exp_rush_fp` | Sum of `exp_rush_fantasy_points` — rushing-role expected output |
| `ep_team_exp_rec_fp` | Sum of `exp_rec_fantasy_points` — receiving-role expected output |
| `ep_team_exp_total_tds` | Sum of `exp_total_tds` — expected scoring-opportunity volume |
| `ep_team_td_over_expected` | Sum(`total_tds`) − sum(`exp_total_tds`) — raw TD variance/luck signal, distinct from the points-level regression signal above |
| `ep_team_opportunity_hhi` | Herfindahl of each player's share of team (targets+carries) that week — opportunity concentration |
| `ep_team_rush_share_hhi` | Herfindahl of each RB's share of team carries that week — rushing-workload concentration specifically |

Non-duplication check: none of these 9 names or their construction overlap
`qb_dakota`/`qb_cpoe`/`qb_pressure_rate`/`skill_*_hhi`/`wr_weighted_*`/
`rb_weighted_*`/`rb_time_to_los` (08-16 features, still present but
opt-in-off) or `teams/player_quality`'s `qb_passing_epa`/`rb_weighted_epa`/
`wr_te_weighted_epa`/`*_injury_impact`/`backup_qb_start`.

## Wiring — additive, opt-in flag (independent of `include_player_features`)

`assemble_game_features(season, include_player_features=False,
include_ep_features=False)`, `_assemble_team_features(...,
include_ep_features=False)`, and `assemble_multiyear_features(...,
include_ep_features=False)` all default to `False` — the shipped
120-feature path is byte-for-byte unchanged (verified: `assemble_game_features(2023)`
returns 1124 cols with or without the new code present, since it's gated off
by default). The two opt-in flags are independent and composable (both can
be True at once — verified in `tests/test_feature_engineering.py::
TestEpFeaturesOptIn::test_flags_are_independent_and_composable`).
`scripts/train_ensemble.py` gained `--include-ep-features`, structured
identically to `--include-player-features`: unions the new 27 candidates
into the feature-selection pool and re-runs
`feature_selector.select_features_for_fold` (SHAP + correlation filter) at
the same target count as `--features-from`, rather than hand-picking which
new columns to keep.

## Gate protocol (pre-registered — no results yet)

Mirrors the ensemble's established evaluation (`ENSEMBLE_PLAYER_FEATURES_
2026_08_16.md` §7) plus the market-features ablation SHIP precedent
(`.planning/PROJECT.md`: market features shipped on **+0.4pt ATS improvement
on the sealed holdout**, 50.2% → 50.6%, `scripts/ablation_market_features.py`
`compute_ship_or_skip`: any strict improvement on sealed holdout is
ship-worthy):

1. **Coverage first** (before any headline number): per-season non-NaN rate
   of the selected EP-feature columns across all 10 seasons, plus a
   nonzero-variance check on the candidate pool. A HOLD with near-zero
   firing rate is a data problem, not a hypothesis rejection (per
   `knowledge-vault/concepts/gated-experiment-coverage-check.md`).
2. **Walk-forward CV OOF ATS** on the retrained candidate ensemble
   (`--include-ep-features --features-from models/ensemble/metadata.json`,
   candidate-pool reselection at 120 features) vs. a same-session, same-
   procedure **control** (identical reselection, `include_ep_features=False`)
   — isolates the new-feature effect from reselection-process noise, exactly
   as `ENSEMBLE_PLAYER_FEATURES_2026_08_16.md` §6 did for the failed
   attempt. This IS the mandatory confound control carried over from that
   doc.
3. **Sealed-2025 holdout** ATS/profit for the same three arms (shipped,
   control, treated).
4. **Decision rule**:
   - Promote-recommend (**SHIP-PENDING-USER**) only if the isolated
     (treated-vs-control) OOF ATS improves by **≥ +0.5pt** (08-16's own bar)
     **AND** the isolated sealed-2025 ATS is **not worse** than control
     (market-features precedent: sealed holdout is the real bar; any
     non-negative isolated delta clears it, mirroring "any improvement means
     SHIP" from `compute_ship_or_skip`).
   - **REJECT to HOLD** if OOF and sealed disagree in sign — this is the
     exact failure mode that killed the 08-16 attempt (CV-only signal that
     reverses out-of-sample) and is treated as disqualifying regardless of
     OOF magnitude.
   - Machinery (the opt-in flag, `_compute_ep_team_features`, tests) ships
     either way — HOLD only blocks promoting a retrained model to
     `models/ensemble/`, never blocks the code.

Shipped `models/ensemble/` is left untouched this session regardless of
verdict; any retrained candidate goes to a new
`models/ensemble_epfeat_2026_08_21/` directory, kept as evidence per the
08-16/08-15 convention.

## Tests (written before results, TDD per repo convention)

`tests/test_feature_engineering.py`: `TestEpTeamFeatures` (7 tests — raw
aggregation math checked against hand computation, HHI checked against hand
computation, shift(1) lag-exclusion test, week-1-all-NaN test, missing-data
graceful-empty test) and `TestEpFeaturesOptIn` (5 tests — flag defaults to
off/byte-identical, strictly additive when on, composable with
`include_player_features`, only rolled/lagged columns ever reach
`get_feature_columns()`, multiyear assembly forwards the flag). All pass
(58/58 in the file, 12 new).

## Results

### 1. Lever-firing check (coverage, before headline numbers)

Non-NaN coverage of the 27 candidate EP-feature columns (real per-game
DataFrames via `assemble_game_features(season, include_ep_features=True)`,
then filtered through `get_feature_columns()`) is **identical across all 27
candidates within a season** (the whole group shares the same shift(1)
early-season NaN pattern, since every raw column comes from the same
`ffopportunity_features` source and the same rolling windows):

| Season | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Coverage | 82.8% | 87.5% | 87.9% | 87.9% | 93.8% | 94.1% | 94.1% | 94.1% | 94.1% | 94.1% |

**Verdict on firing: real signal, not a silent no-op.** 82.8-94.1% coverage
from 2016 onward — notably *better* in early seasons than the 08-16
player-aggregate features (which were ~0% in 2016-2017 because NGS/PFR
Bronze starts ~2018), since ffopportunity's play-level source covers all 10
seasons at full weeks (`.planning/FFOPPORTUNITY_COVERAGE.md`). The residual
~6-17% NaN matches the standard early-season shift(1)-lag sparsity pattern
seen across every other rolled feature group in this repo — not a join bug.
Sealed holdout (2025) sits at 94.1%, same as recent training seasons — fully
live where it's gated.

**Nonzero-variance / changed-columns proof** (2023, `diff_` home-away level):
all 27 candidate columns have real variance (`std` ranging 0.04 for the HHI
diffs to ~16.0 for `exp_fp_total_roll3`) and 256/272 (94.1%) non-null rows —
confirmed via direct inspection, not assumed.

### 2. Selection results

`python scripts/train_ensemble.py --include-ep-features --features-from
models/ensemble/metadata.json --ensemble-dir models/ensemble_epfeat_2026_08_21`
— ran in **27.8s**.

- Candidate pool: 348 (120 prior-shipped ∪ 27 new EP-aggregate diffs ∪ the
  rest of the current 321-column standard candidate space).
- Selected: 120 (same target count as shipped). **9 of the 27 new EP
  candidates were SHAP-selected** (33% hit rate — identical hit rate to the
  08-16 attempt's 10/30) spanning 5 of the 6 idea sub-groups: `fp_over_expected`
  (roll3 + roll6 — the regression-to-expectation signal), `opportunity_hhi`
  (roll3 + std), `td_over_expected` (roll3 + std), `exp_fp_total_std`,
  `exp_pass_fp_roll6`, `rush_share_hhi_roll6`. Not selected: `exp_rush_fp`,
  `exp_rec_fp` (raw, non-`_pass` split), `exp_total_tds` raw candidates —
  dropped by the correlation filter or ranked below cutoff, plausibly
  collinear with the selected `exp_fp_total`/`fp_over_expected` composites.
  50 of the original 120 were replaced overall — per the confound-isolation
  control below, most of that churn is reselection-procedure noise, not
  attributable to the new features specifically.

### 3. Same-session baseline reproduction

Reproduced the currently-shipped ensemble's own numbers in this session
(same `models/ensemble/` artifacts, same current data) to rule out a
data-vintage confound: **OOF ATS 52.92% / +16.09u profit, sealed-2025 ATS
51.66% / -3.73u profit** — the OOF figure and profit match
`ENSEMBLE_PLAYER_FEATURES_2026_08_16.md`'s own shipped-baseline numbers
*exactly* (52.92% / +16.09u), confirming no drift in the shipped model or
training-season Silver since that gate.

### 4. Confound isolation — reselection-process noise vs. new-feature signal

Per the MANDATORY control carried over from the 08-16 HOLD (same
`select_features_for_fold` call, same target_count=120, same correlation
threshold, same candidate-pool-union approach, but `include_ep_features=False`
— no new columns available to select — run outside the repo in
`scratchpad/control_reselect_noep/`, not one of the authorized artifact dirs
per the 08-16 precedent):

| Metric | Shipped (120, CV-search selected) | Control (reselect only, +0 new feats) | Treated (reselect + 9 new EP feats) |
|---|---:|---:|---:|
| OOF Spread ATS | 52.92% | 52.60% | **53.11%** |
| OOF Spread profit | +16.09u | +6.55u | **+21.82u** |
| Sealed-2025 Spread ATS | 51.66% | 49.82% | **50.55%** |
| Sealed-2025 Spread profit | -3.73u | -13.27u | **-9.45u** |

(n=1599 OOF games, n=272 sealed-2025 games — consistent across all three arms.)

**Isolated reading (treated − control)**: the 9 new EP features are
responsible for **OOF Spread ATS +0.51pt / +$15.27u** — clearing the
pre-registered ≥+0.5pt bar, though by a thin margin. Unlike the 08-16
attempt, the sealed-2025 holdout moves the **same direction**: **+0.74pt
ATS / +$3.82u profit**. OOF and sealed **agree in sign** — the disqualifying
condition from the pre-registered protocol (and the exact failure mode that
killed 08-16) does not trigger here.

**Important caveat — the control itself underperforms shipped.** The quick
single-shot `select_features_for_fold` reselection procedure (used for this
gate's isolation test, not the original CV-cutoff-search procedure that
produced the shipped 120) costs ~1.8pt of sealed ATS on its own, with zero
new features (49.82% control vs. 51.66% shipped). The EP features recover
+0.74pt of that gap (to 50.55%) but do **not** fully close it — a naive
`cp -r models/ensemble_epfeat_2026_08_21 models/ensemble` would *regress*
the currently-shipped sealed ATS from 51.66% to 50.55%. This is why the
verdict below is SHIP-PENDING-USER rather than an unconditional promotion:
the isolated signal is real and positive, but confirming it survives the
*production-grade* CV-search selection procedure (`scripts/
run_feature_selection.py`, which the shipped 120 actually went through)
is a separate, heavier retrain out of this session's scope.

### 5. Gate check (against the pre-registered decision rule)

- Isolated OOF ATS improves ≥+0.5pt vs control? **Yes — +0.51pt** (thin
  margin, but clears the bar).
- Isolated sealed-2025 ATS not worse than control? **Yes — +0.74pt, better.**
- OOF and sealed agree in sign? **Yes — both positive.** (Disqualifying
  condition not triggered.)

**Verdict: SHIP-PENDING-USER.** The team-EP-aggregate feature group passes
its pre-registered gate — real coverage, real variance, and a positive,
sign-agreeing signal on both OOF and sealed evaluation once reselection-
procedure noise is controlled for. This is a genuine result-shape difference
from the 08-16 HOLD (which disagreed in sign). Recommendation for the user:
run the full `scripts/run_feature_selection.py` CV-cutoff-search procedure
with the 27 EP candidates unioned into its pool (the same rigor the current
120 shipped features went through) before promoting to `models/ensemble/` —
that heavier search was out of scope for this gate but is the natural next
step given a passing isolated-effect verdict. **Shipped `models/ensemble/`
is left untouched this session** (verified via `git diff --stat
models/ensemble/` — no changes). `models/ensemble_epfeat_2026_08_21/` is
kept on disk as evidence (12 artifact files + metadata), not promoted. The
opt-in machinery (`include_ep_features` flag, `--include-ep-features` CLI
flag, tests) ships regardless of the promotion decision.

### 6. Tests

`tests/test_feature_engineering.py`: 58/58 passing (12 new: `TestEpTeamFeatures`
×7, `TestEpFeaturesOptIn` ×5). `tests/test_ensemble_training.py` +
`tests/test_feature_selector.py`: 33/33 passing (untouched by this change,
confirms no regression).

## Files touched

- `src/config.py` — `SILVER_EP_FEATURES_LOCAL_DIR` constant.
- `src/feature_engineering.py` — `_compute_ep_team_features()`,
  `_read_ep_features()`, `_EP_TEAM_STAT_COLS`; `include_ep_features` param
  (default `False`) threaded through `_assemble_team_features`/
  `assemble_game_features`/`assemble_multiyear_features`, independent of and
  composable with `include_player_features`.
- `tests/test_feature_engineering.py` — 12 new tests (see §6).
- `scripts/train_ensemble.py` — `--include-ep-features` flag; candidate-pool
  union + `select_features_for_fold` reselection when set (shared reselect
  block now triggers on either opt-in flag).
- `models/ensemble_epfeat_2026_08_21/` — new artifacts (not promoted; kept
  as evidence). `models/ensemble/` (shipped) untouched.
- `.planning/ENSEMBLE_EP_FEATURES_GATE.md` — this report.
- Confound-isolation control script kept outside the repo per the 08-16
  precedent (not an authorized artifact dir): `scratchpad/
  run_control_reselect.py` → `scratchpad/control_reselect_noep/`.

## Addendum (2026-08-22) — Full `run_feature_selection.py` CV-search retrain

Per the 08-21 verdict's own recommendation ("run the full CV-cutoff-search
procedure with the 27 EP candidates unioned into its pool before promoting"),
this addendum runs that heavier, production-grade procedure and reports
whether it beats the shipped model — **verdict: it does not.**

### 0. Machinery changes (additive only, per file-ownership scope)

`scripts/run_feature_selection.py` had no way to include the EP candidate
pool at all (only `scripts/train_ensemble.py` had `--include-ep-features`).
Added two additive CLI flags, mirroring existing patterns:

- `--include-ep-features` — threads through to `assemble_multiyear_features`
  exactly like `train_ensemble.py`'s flag of the same name; default `False`
  leaves all existing behavior byte-for-byte unchanged.
- `--output-dir` — lets the CV-search write its `metadata.json` to a
  dedicated evidence directory instead of the shared default
  `models/feature_selection/`, avoiding collisions with concurrent agents.

`scripts/train_ensemble.py` gained `--skip-reselect`: when
`--include-player-features`/`--include-ep-features` is set together with
`--features-from`, the script previously *always* re-ran the quick
single-shot `select_features_for_fold` reselection on top of whatever list
`--features-from` pointed to — exactly the confound this addendum exists to
remove. `--skip-reselect` bypasses that reselection and trusts the
`--features-from` list as-is (while still assembling the new feature columns
into the data so those names resolve). Default behavior for existing
callers (the 08-16/08-21 quick-reselect gates) is unchanged.

`--dry-run` was used throughout to avoid writing `SELECTED_FEATURES` into
the shared `src/config.py` (multiple concurrent agents rely on its current
`None` value; the shipped ensemble already reads its own feature list from
`models/ensemble/metadata.json` via `--features-from`, not from
`SELECTED_FEATURES`). `tests/test_ensemble_training.py` +
`tests/test_feature_selector.py` + `tests/test_feature_engineering.py`:
91/91 passing after these changes (no regressions).

### 1. Full CV-search run (EP candidates included)

`python scripts/run_feature_selection.py --target spread --include-ep-features
--dry-run --output-dir models/ensemble_epfeat_full_2026_08_22/feature_selection`
— walk-forward CV over `VALIDATION_SEASONS` (2019-2024, matching the original
120-feature selection's scheme exactly, per `29-02-SUMMARY.md`), candidate
counts [60, 80, 100, 120, 150], correlation threshold 0.90 (all defaults,
unchanged from the original procedure).

- Candidate pool: 343 (up from the no-EP pool's 316 — the 27 new EP
  candidates, minus a few already present from other concurrent feature
  work landing since 08-21).
- CV MAE by count: 60→10.0850, 80→10.1070, 100→10.0811, **120→10.0756
  (best)**, 150→10.1411. **Optimal count came out to 120 — identical to the
  shipped model's own count** (not a coincidence-free result; see the
  no-EP control below, which came out different).
- Final selection on all training data (2016-2024): 343 → 231 (correlation
  filter, 108 dropped) → 120 selected (111 more dropped by rank).
- **9 of 27 EP candidates survived** (33% hit rate — identical hit rate to
  both the 08-16 attempt and the 08-21 quick-reselect gate):

| EP feature (selected) | SHAP rank (of 120) |
|---|---:|
| `diff_ep_team_fp_over_expected_roll3` | 13 |
| `diff_ep_team_opportunity_hhi_std` | 15 |
| `diff_ep_team_exp_fp_total_std` | 18 |
| `diff_ep_team_td_over_expected_std` | 25 |
| `diff_ep_team_rush_share_hhi_roll6` | 40 |
| `diff_ep_team_opportunity_hhi_roll3` | 55 |
| `diff_ep_team_exp_pass_fp_roll6` | 81 |
| `diff_ep_team_fp_over_expected_roll6` | 97 |
| `diff_ep_team_td_over_expected_roll3` | 101 |

Not selected (18 of 27): all `exp_rec_fp` variants (correlation-dropped
against `exp_pass_fp`), `exp_rush_fp` variants, most `exp_total_tds` raw
candidates, `rush_share_hhi_roll3`/`_std`, `td_over_expected_roll6` — same
qualitative pattern (regression-to-expectation and opportunity-concentration
groups survive; raw expected-volume composites mostly get correlation-
filtered against denser composites) as both prior gates.

### 2. Ensemble training on the full-procedure selection

`python scripts/train_ensemble.py --include-ep-features --features-from
models/ensemble_epfeat_full_2026_08_22/feature_selection/metadata.json
--skip-reselect --ensemble-dir models/ensemble_epfeat_full_2026_08_22` — 120
features, 2639 games, 28.7s. Artifacts saved to
`models/ensemble_epfeat_full_2026_08_22/` (spread + total XGB/LGB/CB/Ridge,
calibrators, `oof_spread.parquet`/`oof_total.parquet`, `metadata.json`,
`feature_selection/metadata.json`).

### 3. Evaluation — OOF + sealed-2025, full-procedure EP-included vs shipped

Evaluation script kept in scratchpad per the 08-16/08-21 precedent (not an
authorized artifact dir): joins `oof_spread.parquet`'s `meta_oof_pred`
against real `spread_line`/`actual_margin` for OOF ATS, and runs
`predict_ensemble` on freshly assembled sealed-2025 features (with
`include_ep_features=True`) for the sealed holdout. **Methodology verified
exact**: re-running this same script against the shipped `models/ensemble/`
reproduces its recorded numbers bit-for-bit (OOF 52.92% / +16.09u, sealed
51.66% / -3.73u — identical to `ENSEMBLE_PLAYER_FEATURES_2026_08_16.md`'s
own shipped-baseline figures), ruling out a data-vintage or methodology
confound.

| Metric | Shipped (120, original selection) | Full-procedure + EP (120, this run) |
|---|---:|---:|
| OOF Spread ATS | 52.92% (n=1557) | **53.89%** |
| OOF Spread profit | +16.09u | **+44.73u** |
| Sealed-2025 Spread ATS | 51.66% (n=271 bet) | **48.71%** (n=271 bet) |
| Sealed-2025 Spread profit | -3.73u | **-19.00u** |

**vs. shipped: OOF improves +0.97pt, but sealed-2025 falls -2.95pt.** OOF
and sealed disagree in sign — the exact disqualifying condition from this
doc's own pre-registered decision rule (§ "Gate protocol", carried over from
the 08-16 HOLD's failure mode).

### 4. No-EP full-procedure control (cheap, run to isolate attribution)

To check whether the sealed-holdout drop is EP-specific or a property of
re-running the full CV-search procedure itself on today's data/candidate
pool, ran the identical procedure with `--include-ep-features` omitted
(kept outside the repo's authorized artifact dirs, per precedent:
`scratchpad/control_fullprocedure_noep/`):

- Candidate pool 316 (no EP). CV search picked **optimal count = 60** — a
  *different* count than both the shipped model (120) and the EP-included
  full-procedure run (120) — the CV-cutoff search is not stably reproducing
  120 without the EP candidates in the pool, on today's data.
- OOF ATS 53.89% (n=1557) / profit +44.73u — numerically identical in
  aggregate to the EP-included run at 4-decimal precision, though only
  83.5% of individual game picks agree between the two (264/1599 differ;
  the aggregate tie is coincidental cancellation, verified game-by-game).
- **Sealed-2025 ATS 46.86%** (n=271 bet) / profit -28.55u — *worse* than
  the EP-included full-procedure run (48.71%) and far worse than shipped
  (51.66%).

**Isolated EP effect within the full procedure** (treated − control):
OOF ≈ +0.00pt (a wash — 53.8857% both), **sealed +1.85pt** (48.71% vs
46.86%). The EP features' isolated sealed-holdout effect is still
*positive* here, consistent in direction with both the 08-21 quick-reselect
isolation (+0.74pt) and, more weakly, the 08-16-style logic — but the
magnitude of the *procedure-level* problem swamps it: **both full-procedure
variants underperform shipped's sealed ATS by a wide margin (-2.95pt with
EP, -4.80pt without)**. Re-running the "more rigorous" CV-search procedure
on today's data does not reproduce anything close to the shipped model's
forward performance, with or without EP features — the opposite of what
the 08-21 doc hoped to confirm.

### 5. Gate check (against the pre-registered decision rule)

- Isolated OOF ATS improves ≥+0.5pt vs control? Not meaningfully — the
  full-procedure isolated OOF delta is ≈0.00pt (both arms landed at
  53.8857%), so this bar is not even reached on OOF in the full-procedure
  frame (contrast with the quick-reselect isolation's +0.51pt).
  Full-procedure vs *shipped* on OOF is +0.97pt, but that comparison
  conflates the EP effect with the reselection-procedure's own (large,
  negative-on-sealed) effect.
- **OOF and sealed disagree in sign (full-procedure + EP vs. shipped): Yes
  — the disqualifying condition triggers.** (+0.97pt OOF, -2.95pt sealed.)
- Does the EP-included full-procedure model beat the shipped model's sealed
  ATS? **No — 48.71% vs 51.66%, a 2.95pt decline.**

**Verdict: DO-NOT-PROMOTE.** The full `run_feature_selection.py` CV-search
retrain, run exactly per the 08-21 recommendation with the 27 EP candidates
unioned into its pool, does **not** beat the shipped model's sealed-2025
ATS — it falls 2.95pt short, and OOF/sealed disagree in sign, the same
disqualifying failure mode that killed the 08-16 attempt. The no-EP control
shows this is **not primarily an EP-feature problem**: the full CV-search
procedure itself, re-run on today's (larger, more evolved) candidate pool
and data, produces a sealed-holdout result 4.80pt worse than shipped even
with *zero* new features. The EP features' own isolated effect remains
mildly positive on sealed (+1.85pt) and roughly neutral on OOF, consistent
in direction with the 08-21 isolation test — but they are not the cause of,
nor a fix for, the larger procedure-reproduction problem this addendum
surfaces.

`models/ensemble/` (shipped) is confirmed untouched this session (`git
status --short models/ensemble/` and `git diff --stat models/ensemble/`
both empty). **Flipping `models/ensemble/` to any variant produced in this
addendum is explicitly a USER decision, and given the numbers above, the
recommendation is not to do so.** `models/ensemble_epfeat_full_2026_08_22/`
(full CV-search selection metadata + trained ensemble artifacts + OOF
parquet files + `eval_results.json`) is kept on disk as evidence, not
promoted. The no-EP full-procedure control's artifacts live outside the
repo's authorized artifact dirs in `scratchpad/control_fullprocedure_noep/`
per the established precedent (not committed).

A follow-up worth flagging for the user separately from this experiment's
scope: the finding in §4 that a same-procedure, same-defaults rerun of
`run_feature_selection.py` today reproduces neither the shipped model's
feature count nor its sealed performance suggests the CV-cutoff-search
procedure itself may be more fragile to candidate-pool/data-vintage drift
than assumed — worth its own investigation independent of the EP-features
question.

### 6. Tests

`tests/test_ensemble_training.py` + `tests/test_feature_selector.py` +
`tests/test_feature_engineering.py`: 91/91 passing (no regressions from the
additive `--include-ep-features`/`--output-dir`/`--skip-reselect` CLI
flags).

### 7. Files touched (this addendum)

- `scripts/run_feature_selection.py` — `--include-ep-features`,
  `--output-dir` CLI flags (additive, default-off/default-path preserves
  existing behavior).
- `scripts/train_ensemble.py` — `--skip-reselect` CLI flag (additive,
  default-off preserves existing quick-reselect behavior for prior gates).
- `models/ensemble_epfeat_full_2026_08_22/` — new evidence dir (full
  CV-search selection + trained ensemble, not promoted).
  `models/ensemble/` (shipped) untouched.
- `.planning/ENSEMBLE_EP_FEATURES_GATE.md` — this addendum.
- Evaluation + no-EP control scripts/artifacts kept outside authorized
  artifact dirs per precedent: `scratchpad/eval_epfeat_full.py`,
  `scratchpad/control_fullprocedure_noep/`.
