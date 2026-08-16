# Ensemble Player-Aggregate Features — 2026-08-16

Opportunity-scan move #2 (`.planning/OPPORTUNITY_SCAN_2026_08_16.md` candidate #2):
the game-prediction ensemble (`models/ensemble/`, 52.92% OOF ATS) has never read
player-level Silver — `src/feature_engineering.py::assemble_game_features()` only
joins `SILVER_TEAM_LOCAL_DIRS` (`.planning/ENSEMBLE_HEALTH_2026_08_15.md` §2). The
repaired `players/usage` (snap_pct join-bug fix) and `players/advanced` (NGS/PFR/QBR
ingestion) Silver carry real signal now — a routine value refresh of the one
existing partial player-aggregate (`teams/player_quality`) already moved sealed-2025
spread ATS by +0.8pt. This task: add team-aggregated player features and gate a
retrain.

## Pre-registered gate (written before step 4 ran)

> Promote-recommend only if OOF ATS improves **≥ +0.5pt** over shipped **52.92%**
> AND the sealed-2025 holdout ATS/profit is **not worse**. Otherwise HOLD/keep
> shipped. (Same shape as `ENSEMBLE_HEALTH_2026_08_15.md`'s gate.)

## 1. Feature design + construction provenance

Audited `scripts/silver_player_quality_transformation.py` (the existing
`teams/player_quality` team-feature construction) first and mirrored it exactly:
raw team-week aggregates are computed from **same-week actual** per-player stats
(fine — the raw column is never itself exposed as a model feature), then
`team_analytics.apply_team_rolling()` shift(1)-lags them into `_roll3`/`_roll6`/`_std`
columns, and `get_feature_columns()`'s existing rolling-suffix allowlist is what
actually enforces "trailing/lagged only" — only those derivatives can ever be
selected. This is the same double-layer the shipped `qb_passing_epa`,
`rb_weighted_epa`, etc. use.

New function `src/feature_engineering.py::_compute_player_team_features(season)`
reads `players/usage` + `players/advanced` (joined on `player_id`/`player_gsis_id` —
real ids, never name-only, per the join-key lesson in
`knowledge-vault/concepts/gated-experiment-coverage-check.md`) and builds 10 raw
team-week metrics across 4 idea groups (not a firehose — the brief's four
suggested directions, minus injury-adjusted availability, which was dropped to
avoid duplicating `teams/player_quality`'s existing `*_injury_impact` columns):

| Group | Raw feature | Definition |
|---|---|---|
| QB trailing efficiency composite | `qb_dakota` | Starter's (max-attempts that team-week) `dakota` (usage) |
| | `qb_cpoe` | Starter's NGS completion % above expectation (advanced) |
| | `qb_pressure_rate` | Starter's PFR pressured-rate (advanced) |
| Skill-corps concentration/continuity | `skill_snap_share_hhi` | Herfindahl index of RB/WR/TE `snap_pct` (renormalized; 1/N=even, 1.0=one player has it all) |
| | `skill_target_share_hhi` | Herfindahl index of RB/WR/TE `target_share` |
| | `skill_snap_participation_count` | Count of RB/WR/TE with `snap_pct >= 0.30` that week (rotation depth) |
| Weighted receiver separation (NGS) | `wr_weighted_separation` | WR/TE `ngs_avg_separation`, target-share weighted |
| | `wr_weighted_yac_oe` | WR/TE `ngs_avg_yac_above_expectation`, target-share weighted |
| Rushing-room efficiency (NGS) | `rb_weighted_ryoe` | RB `ngs_rush_yards_over_expected_per_att`, carry-share weighted |
| | `rb_time_to_los` | RB `ngs_avg_time_to_los`, carry-share weighted (lower = more room) |

Each raw metric produces `_roll3`/`_roll6`/`_std` (10 × 3 = 30 candidate columns),
diffed home-minus-away exactly like every other team source. **Non-duplication
check**: grepped the shipped 120-feature list and `teams/player_quality`'s own
column set — none of these 10 names or their construction overlap
`qb_passing_epa`, `rb_weighted_epa`, `wr_te_weighted_epa`, `*_injury_impact`, or
`backup_qb_start`.

## 2. Wiring — additive, opt-in flag

`assemble_game_features(season, include_player_features=False)`,
`_assemble_team_features(season, include_player_features=False)`, and
`assemble_multiyear_features(seasons=None, include_player_features=False)` all
default to `False` — the shipped 120-feature path is called with no arguments
throughout the existing codebase (`scripts/backtest_predictions.py`,
`scripts/generate_predictions.py`, `scripts/run_feature_selection.py`, etc.), so
it is **byte-for-byte unchanged**: verified `assemble_game_features(2024)` returns
the identical column set/shape before and after this change (1124 cols, unaffected
by the new code being present but not invoked). `scripts/train_ensemble.py` gained
`--include-player-features`, which assembles with the flag on, unions the new
30 candidates into the feature-selection pool, and re-runs
`feature_selector.select_features_for_fold` (SHAP + correlation filter — the same
function `run_feature_selection.py::run_final_selection()` calls) at the same
target count as `--features-from`, rather than hand-picking which new columns to
keep, per the task's "append candidates and let the existing SHAP selection
choose" instruction.

## 3. Lever-firing check (coverage, before the headline numbers)

Per `knowledge-vault/concepts/gated-experiment-coverage-check.md`'s rule — verify
the lever actually fires before reading the verdict. Non-NaN coverage of the 10
**selected** features (below) across all 10 seasons, real per-game DataFrames via
`assemble_game_features(season, include_player_features=True)`:

| Feature | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `diff_qb_dakota_roll6` | 82.8 | 87.5 | 87.9 | 87.9 | 93.8 | 94.1 | 94.1 | 94.1 | 94.1 | 94.1 |
| `diff_qb_pressure_rate_roll3` | 0.0 | 0.0 | 87.9 | 83.6 | 90.2 | 94.1 | 94.1 | 90.4 | 91.5 | 91.5 |
| `diff_qb_pressure_rate_std` | 0.0 | 0.0 | 87.9 | 84.4 | 91.0 | 94.1 | 94.1 | 94.1 | 92.6 | 91.9 |
| `diff_rb_time_to_los_roll6` | 82.0 | 83.2 | 84.8 | 85.9 | 91.4 | 91.9 | 92.6 | 91.9 | 93.4 | 93.4 |
| `diff_rb_weighted_ryoe_roll3` | 0.0 | 0.0 | 83.6 | 85.5 | 90.6 | 89.7 | 91.5 | 91.9 | 92.6 | 93.4 |
| `diff_skill_target_share_hhi_roll6` | 82.8 | 87.5 | 87.9 | 87.9 | 93.8 | 94.1 | 94.1 | 94.1 | 94.1 | 94.1 |
| `diff_wr_weighted_separation_roll3` | 82.8 | 86.7 | 87.9 | 87.5 | 93.8 | 93.8 | 92.6 | 93.8 | 93.4 | 94.1 |
| `diff_wr_weighted_separation_roll6` | 82.8 | 86.7 | 87.9 | 87.5 | 93.8 | 93.8 | 93.0 | 93.8 | 93.4 | 94.1 |
| `diff_wr_weighted_yac_oe_roll3` | 82.8 | 86.7 | 87.9 | 87.5 | 93.8 | 93.8 | 92.6 | 93.8 | 93.4 | 94.1 |
| `diff_wr_weighted_yac_oe_roll6` | 82.8 | 86.7 | 87.9 | 87.5 | 93.8 | 93.8 | 93.0 | 93.8 | 93.4 | 94.1 |

**Verdict on firing: real signal, not a silent no-op.** 80-94% coverage from 2018
onward (real football sparsity from HHI/composite construction being far more
robust to any single player's missing NGS reading than a per-player feature would
be — averaging survives individual gaps). `qb_pressure_rate`/`rb_weighted_ryoe`
are legitimately 0% in 2016-2017 — nflverse's PFR-advanced and NGS-rushing feeds
don't start until ~2018, matching the known coverage floor already documented in
`OPPORTUNITY_SCAN_2026_08_16.md`'s NGS-sparsity caveat, not a join bug. The sealed
holdout (2025) sits at 91.5-94.1% across all 10 selected features — the lever is
fully live where it's gated.

## 4. Selection results

`python scripts/train_ensemble.py --include-player-features --features-from
models/ensemble/metadata.json --ensemble-dir models/ensemble_playerfeat_2026_08_16`
— ran in **22.8s** (well under the 10-minute ceiling, no chunking needed).

- Candidate pool: 351 (120 prior-shipped ∪ 30 new player-aggregate diffs ∪ the
  rest of the full 318-column candidate space already computed by
  `get_feature_columns()`).
- Selected: 120 (same target count as shipped). **10 of the 30 new player-feature
  candidates were SHAP-selected** (33% hit rate) — spanning all 4 idea groups
  (QB composite: dakota + pressure rate; skill concentration: target-share HHI;
  receiver separation: both separation and YAC-OE; rushing room: RYOE and
  time-to-LOS). `skill_snap_share_hhi` and `skill_snap_participation_count`
  candidates were not selected (dropped by the correlation filter or ranked
  below the cutoff — both are collinear with `skill_target_share_hhi`, which was
  selected).
- 50 of the original 120 were replaced — **but this is not entirely attributable
  to the new features**; see the confound-isolation control below.

## 5. Same-session baseline — reused 2026-08-15's no-tuning retrain, cross-validated fresh

Per instruction, reused `ENSEMBLE_HEALTH_2026_08_15.md`'s no-tuning retrain
comparison (`models/ensemble_retrained_2026_08_15/`, same 120 shipped features,
current data) as the baseline rather than re-baselining into a new directory
(out of this task's file scope — only `models/ensemble_playerfeat_2026_08_16/` is
authorized). Reproducibility was **not** simply assumed: a same-session control
run (§6) that re-runs `select_features_for_fold` on the *original* (no
player-feature) candidate pool landed at OOF ATS 52.60% / sealed-holdout ATS
50.18%/-11.36u profit — within 0.3pt and **exactly matching profit to two decimal
places** against the 08-15 doc's own retrain (52.86% OOF / 50.2% holdout /
-11.36u). That match confirms no data-vintage confound crept in between the two
sessions (per the vault's "same data vintage" rule) — training-season Silver is
still the bit-for-bit-identical state `ENSEMBLE_HEALTH_2026_08_15.md` §2
established.

## 6. Confound isolation — reselection-process noise vs. new-feature signal

`select_features_for_fold` (a single quick-XGB-SHAP pass on all training data) is
a lighter procedure than the original `run_feature_selection.py` CV-cutoff-search
that produced the shipped 120. To avoid crediting the player features for an
effect that's really just "a different selection procedure was used," ran a
**control**: identical reselection procedure (same function, same target_count
120, same correlation threshold), same candidate-pool-union approach, but
`include_player_features=False` (no new columns available to select) —
`C:\...\scratchpad\control_reselect_noplayer\` (outside the repo; not one of the
authorized artifact dirs, so not committed to `models/`).

| Metric | Shipped (120, CV-search selected) | Control (reselect only, +0 new feats) | Treated (reselect + 10 new player feats) |
|---|---:|---:|---:|
| OOF Spread ATS | 52.92% | 52.60% | **54.14%** |
| OOF Spread profit | +16.09u | +6.55u | **+52.36u** |
| OOF Total O/U | 49.81% | 49.75% | 49.81% |
| Sealed-2025 Spread ATS | 51.7%* | 50.18% | **49.45%** |
| Sealed-2025 Spread profit | -3.73u | -11.36u | **-15.18u** |
| Sealed-2025 Total O/U | 48.9%* | 52.21% | 52.57% |

*Shipped sealed-2025 numbers are the "current data" reproduction from
`ENSEMBLE_HEALTH_2026_08_15.md` §3 (51.7% ATS / -3.73u), not the ship-time
metadata snapshot.

**Isolated reading**: vs. the control (same procedure, no player features), the
10 new player features are responsible for **OOF Spread ATS +1.54pt / +$45.81u**
— a real, non-trivial in-sample/CV gain, not selection-procedure noise. But
sealed-2025 holdout moves the *wrong* direction on the same isolated comparison:
**-0.73pt ATS / -3.82u profit**. The features generalize backward (CV) but not
forward (2025) — a classic overfit-to-training-period-role-patterns signature,
plausible given 2025's real injury/role churn already flagged in
`ENSEMBLE_HEALTH_2026_08_15.md` §2-3 as materially different from 2016-2024.

## 7. Gate check (against shipped, the pre-registered comparison)

- OOF ATS improved ≥0.5pt vs shipped 52.92%? **Yes — 54.14%, +1.22pt.**
- Sealed-2025 holdout ATS/profit not worse? **No — 49.45% vs 51.7% (-2.25pt),
  profit -15.18u vs -3.73u (-11.45u worse).**

**Verdict: HOLD. Do not promote `models/ensemble_playerfeat_2026_08_16/`.** Both
gate conditions must hold; only the first does. The confound-isolated view (§6)
shows this isn't a fluke of the looser single-shot reselection procedure — the
new features are pulling their own weight on OOF and pulling the *wrong* way on
the sealed holdout. `models/ensemble_playerfeat_2026_08_16/` is left on disk as
evidence (12 artifact files + metadata), same convention as
`models/ensemble_retrained_2026_08_15/` from the prior health check — not
recommended for promotion. `models/ensemble/` (shipped) is untouched.

## 8. Tests

Added to `tests/test_feature_engineering.py` (46 tests total in the file, all
passing): `TestHelperFunctions` (7 tests — HHI and share-weighted-average unit
tests incl. all-NaN/all-zero edge cases), `TestPlayerTeamFeatures` (8 tests incl.
`test_shift1_lag_excludes_current_week` — the leak-free construction test,
verifying week 4's `_roll3` value reflects only weeks 1-3's raw values, not week
4's own; `test_missing_advanced_still_produces_usage_derived_features` for
graceful NGS/PFR-down degradation), `TestPlayerFeaturesOptIn` (4 tests verifying
the flag is strictly additive and that only `_roll3`/`_roll6`/`_std` player-feature
columns ever reach `get_feature_columns()`, never the raw same-week column).

```
tests/test_feature_engineering.py .......................................... [100%]  46 passed
tests/test_ensemble_training.py ................................................. [100%]  49 passed
```

## Files touched

- `src/feature_engineering.py` — `_compute_player_team_features()`,
  `_herfindahl()`, `_share_weighted_avg()`, `_PLAYER_TEAM_STAT_COLS`;
  `include_player_features` param (default `False`) threaded through
  `_assemble_team_features`/`assemble_game_features`/`assemble_multiyear_features`.
- `tests/test_feature_engineering.py` — 19 new tests (see §8).
- `scripts/train_ensemble.py` — `--include-player-features` flag; candidate-pool
  union + `select_features_for_fold` reselection when set.
- `models/ensemble_playerfeat_2026_08_16/` — new artifacts (not promoted; kept
  as evidence). `models/ensemble/` (shipped) untouched.
- `.planning/ENSEMBLE_PLAYER_FEATURES_2026_08_16.md` — this report.
