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

## Status

Pre-registration + machinery + tests committed here, before running
coverage/OOF/sealed numbers. Results and verdict to be appended to this
document in a follow-up commit.
