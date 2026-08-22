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
