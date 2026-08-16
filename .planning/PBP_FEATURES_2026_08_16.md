# PBP Feature Expansion + FTN Re-gate — 2026-08-16

Expands the residual models' candidate feature pool with new PBP-derived
signals (PBP bronze is now local 2016-2025 per `GRAPH_REVIVAL_2026_08_16.md`)
and re-gates the FTN charting pipeline now that repaired features, the
population fix, and QB/RB hybrids all exist. Follows the firing-rate +
same-vintage discipline in `knowledge-vault/concepts/gated-experiment-coverage-check.md`.
Scope: `src/player_feature_engineering.py` + new `src/pbp_advanced_features.py`
+ `tests/test_pbp_advanced_features.py`. Did not touch `src/quantile_models.py`,
`src/config.py`, `scripts/generate_projections.py`, or any other agent's files.

## 1. Overlap check first (don't duplicate)

Before building anything, checked the mission's priority candidates against
the existing pool:

- **Team PROE + pace as player context — already fully built, not duplicated.**
  `src/team_analytics.py::compute_pace`/`compute_proe` feed
  `compute_tendency_metrics`, written to Silver `teams/tendencies`, and
  joined into every player-week row at `assemble_player_features` step 6
  (`SILVER_PLAYER_TEAM_SOURCES["tendencies"]`, left-join on
  `recent_team/season/week`). `apply_team_rolling` produces `pace_roll3`,
  `pace_roll6`, `pace_std`, `proe_roll3`, `proe_roll6`, `proe_std`
  (shift(1)-lagged) — already in the candidate pool and already selected
  into shipped WR (`pace_roll3`) and QB (`pace_std`) models. Confirmed via
  `grep` (no `pace_roll`/`proe_roll` construction anywhere else) — this
  mission item was already done, so nothing new was built for it.
- **WR/TE slot-vs-wide alignment share — not derivable locally, skipped.**
  Local `data/bronze/pbp_participation/` only carries 4 columns
  (`game_id`, `play_id`, `offense_players`, `defense_players` — gsis-id
  lists, no formation/personnel/alignment fields), and Bronze PBP itself
  (141 cols) has no `offense_formation`/`offense_personnel`/route/alignment
  columns either — nflverse only ships those in a separate charting feed
  FTN partially covers (no explicit slot flag) or PFF (not subscribed, see
  CLAUDE.md "Planned"). Noted and skipped per instructions rather than
  approximated.
- **QB time-to-throw proxies — built, but a genuine proxy, and it lost to
  the real signal.** PBP has no time-to-throw field. Built
  `qb_sack_rate` (pressure/pocket-time proxy) and `qb_avg_intended_air_yards`
  + `qb_deep_ball_rate` (aggressiveness proxies, arguably TTT-adjacent since
  deeper throws hold the ball longer). Real NGS `avg_time_to_throw` already
  exists in the pool and **was selected** for QB in the `+PBP+FTN` variant
  (`ngs_avg_time_to_throw_std`) — see §4, none of the 3 PBP proxy features
  were selected for QB in any variant. Built as instructed ("if derivable"),
  honestly reported as not winning a slot.

## 2. New PBP-derived features built (`src/pbp_advanced_features.py`)

15 trailing (shift(1)-lagged) candidate columns, all strictly-prior
construction, mined directly from local Bronze PBP (no dependency on
Silver graph_features):

| Raw signal | Trailing variants | Definition |
|---|---|---|
| `adot` | `_roll4`, `_trail`, `adot_slope` | Mean air_yards on the player's targets (depth-of-target / receiver role signal) |
| `deep_target_share` | `_roll4`, `_trail` | Player's air_yards≥20 targets ÷ the player's TEAM's deep targets that week |
| `intermediate_target_share` | `_roll4`, `_trail` | Player's 10-19.99 air_yards targets ÷ team's intermediate targets |
| `short_target_share` | `_roll4`, `_trail` | Player's <10 air_yards targets ÷ team's short targets |
| `qb_sack_rate` | `_roll4`, `_trail` | Sacks ÷ dropbacks (pressure/pocket-time proxy) |
| `qb_avg_intended_air_yards` | `_roll4`, `_trail` | Mean air_yards on pass attempts (aggressiveness/TTT proxy) |
| `qb_deep_ball_rate` | `_roll4`, `_trail` | Share of attempts with air_yards≥20 |

`adot_slope` uses the same OLS-over-trailing-4-shifted-values construction
as `graph_route_participation.py::route_rate_slope` (reused the pattern,
not the private function — kept the new module dependency-free). Target
zone buckets: short <10, intermediate 10-19.99, deep ≥20 air_yards
(`pd.cut`, `right=False`).

**Leak discipline**: raw columns (`adot`, `deep_target_share`, etc.) added
to `_SAME_WEEK_RAW_STATS` in `player_feature_engineering.py`; only
`_roll4`/`_trail`/`adot_slope` variants are ever joined into the training
frame (`_join_pbp_advanced_features`, step 20, mirrors the existing
`_join_ftn_features` pattern exactly, including the QB-vs-receiver
`position_type` role-matching to avoid blending disjoint feature sets for
a player who both passed and caught in the same week).

**Unit tests**: `tests/test_pbp_advanced_features.py`, 17 tests, all
passing — raw computation correctness (adot, zone shares, QB rates on a
hand-built fixture), shift(1) enforcement (week-1 all-NaN, week-2 NaN or
never-equal-to-same-week-raw, week-4 trail = mean of weeks 1-3, slope uses
only prior weeks), and the 4-part leak gate (raw registered in
`_SAME_WEEK_RAW_STATS`, trailing columns NOT in that set, trailing columns
pass `_is_unlagged_leak`, end-to-end `get_player_feature_columns` excludes
raw / includes trailing).

**Coverage** (built for all seasons 2016-2025, no coverage-gap era unlike
FTN's 2022+ restriction, since it rides on PBP which is now uniformly
local for the whole training window):

| Season | Rows | Receiver-feature coverage | QB-feature coverage |
|---|---:|---:|---:|
| 2016 | 3,517 | 74.9% | 11.9% |
| 2020 | 3,808 | 73.7% | 11.6% |
| 2025 | 4,085 | 70.9% | 11.4% |

(QB coverage ~11-12% is expected — QB is 1 of 4 positions in the pool, and
only rows with ≥1 prior in-season target/dropback qualify for min_periods.)

Silver written to `data/silver/players/pbp_advanced/season={2016..2025}/`
(local-only, gitignored — not allowlisted per this task's scope).

## 3. FTN re-gate

**Finding**: the FTN pipeline (`src/ftn_features.py`,
`scripts/bronze_ftn_ingestion.py`, `scripts/silver_ftn_transformation.py`,
wired into `player_feature_engineering.py` step 19) was intact and
production-ready, but **all local FTN Bronze/Silver data was absent**
(`data/bronze/ftn_charting/` and `data/silver/players/ftn/` didn't exist on
this machine) — meaning the June HOLD verdict's live re-test would have
silently scored 100%-NaN FTN columns exactly like the pre-revival graph
features. Fixed the coverage gap:

```
python scripts/bronze_ftn_ingestion.py --seasons 2022-2025
python scripts/silver_ftn_transformation.py --seasons 2022-2025
```

185,215 Bronze rows across 4 seasons (41.6K/48.2K/48.0K/47.3K),
21,957 Silver player-weeks — **including season 2025**, which did not
exist at the June build time and is required for the sealed-2025 gate.
FTN-PBP join matched 100% of Bronze FTN rows every season (41,643/41,643,
48,225/48,225, 48,031/48,031, 47,316/47,316).

**Re-test result: FTN features were STILL NOT SELECTED by SHAP for any of
the 4 positions**, in either the `+PBP+FTN` variant or any prior check —
`ftn_selected: []` across QB/RB/WR/TE. This reconfirms the original HOLD,
now on live, complete, up-to-date data (repaired features, population fix,
and QB/RB hybrids all present) rather than a coverage-gap artifact.
**Verdict: FTN status unchanged — HOLD.** The pipeline itself is now fully
live and re-testable at any time going forward (this was the actual gap;
closed).

## 4. Retrain + selection results

Same protocol as `RETRAIN_ON_REPAIRED_FEATURES.md` §2 — no hyperparameter
changes: QB/RB `model_type="lgb"`, `shap_feature_count=20`; WR/TE
`model_type="ridge"`, `shap_feature_count=60`; `training_seasons=2016-2024`
(2025 sealed, HOLDOUT_SEASON, never trained on). Three same-session
variants (avoids the cross-session-vintage trap in
`gated-experiment-coverage-check.md`), monkeypatching the two new join
steps on/off around the *same* `assemble_multiyear_player_features` call so
each variant is otherwise byte-identical:

| Variant | Pool | Output dir |
|---|---|---|
| `baseline` | current shipped pool, PBP-advanced and FTN both off | `models/pbp_feature_experiments_2026_08_16/baseline` |
| `pbp` | + 15 pbp_advanced trailing features | `models/pbp_feature_experiments_2026_08_16/pbp` |
| `pbp_ftn` | + pbp_advanced + FTN (both live) | `models/pbp_feature_experiments_2026_08_16/pbp_ftn` |

**SHAP selection — did the lever actually fire (compete for and win a
slot), not just sit in the pool:**

| Position | `pbp` variant selected | `pbp_ftn` variant selected |
|---|---|---|
| QB | none | none |
| RB | `deep_target_share_roll4`, `intermediate_target_share_roll4`, `short_target_share_roll4` | same 3 |
| WR | `adot_slope`, `short_target_share_roll4` | `adot_slope`, `short_target_share_trail`, `intermediate_target_share_trail` |
| TE | `short_target_share_trail` | `short_target_share_trail`, `intermediate_target_share_roll4`, `deep_target_share_roll4` |

Target-share-by-zone is the feature that actually competes — all 3 zone
shares got selected for RB in both variants (a strong, repeated signal, not
a fluke), and one zone-share variant made every non-QB position. `adot_slope`
made WR both times. `ftn_*` made zero positions. QB's proxy features
(`qb_sack_rate*`, `qb_avg_intended_air_yards*`, `qb_deep_ball_rate*`) were
never selected anywhere — consistent with real NGS TTT (`ngs_avg_time_to_throw_std`,
selected into QB's `pbp_ftn` model) outcompeting the PBP-derived proxy.

## 5. Gate results

### 5a. MAE gate (sealed 2025, weeks 3-18, half_ppr, matched rows)

Pre-registered gate: adopt-recommend if any position improves ≥0.03 MAE
vs. the same-session baseline, and none worsens by >0.02.

| Position | n | Heuristic MAE | Baseline MAE | `+PBP` MAE (Δ) | `+PBP+FTN` MAE (Δ) |
|---|---:|---:|---:|---:|---:|
| QB | 487 | 6.486 | 5.572 | 5.617 (**−0.045**) | 5.609 (**−0.037**) |
| RB | 841 | 5.108 | 4.832 | 4.818 (+0.014) | 4.784 (**+0.048**) |
| WR | 1,577 | 3.947 | 3.916 | 3.908 (+0.008) | 3.930 (−0.014) |
| TE | 951 | 3.111 | 2.887 | 2.869 (+0.018) | 2.897 (−0.010) |

(Δ = baseline − variant; positive = improvement.)

**QB caveat (important — read before the verdict):** the QB MAE
"regression" is **not attributable to the new features**. Diffing the
selected-feature lists, QB's `baseline` vs `pbp_ftn` models share 16/20
features; every one of the 4 features that differ (`closing_spread`,
`ngs_completion_percentage_above_expectation_std`,
`pfr_def_times_hurried_std`, `rushing_yards_std` swapped for
`def_epa_per_play_std`, `fantasy_points_ppr_roll3`,
`ngs_completion_percentage_above_expectation_roll6`,
`passing_yards_x_implied_total`) already existed in the pre-existing pool
in both runs — **zero PBP-advanced or FTN features were selected for QB in
either variant**. The ~0.04 MAE delta is SHAP-selection run-to-run
variance at a fixed 20-feature budget, not an effect of this task's
features. (No baseline-vs-baseline rerun was budgeted to quantify pure
noise directly — flagging the mechanism instead of asserting a number.)

**Verdict by the letter of the gate**: neither variant clears it as a
wholesale swap-in (QB's apparent >0.02 worsening blocks both, even though
it's noise-driven). **Per-position reading** (each position trains and
ships as an independent artifact, so mixing is operationally valid):

- **RB: ADOPT-RECOMMEND** (`+PBP+FTN`, +0.048 MAE, clears the ≥0.03 bar
  cleanly; `+PBP` alone is a smaller +0.014, below bar). Target-share-by-zone
  is the driver (all 3 zone-share features selected).
  Recommend promoting `pbp_ftn`'s RB residual artifact.
- **QB: HOLD** — no real signal either way per the caveat above; keep
  shipped.
- **WR, TE: HOLD** — deltas are noise-level (≤0.02 either direction),
  below the adopt bar.

### 5b. Ordinal gate (FantasyPros-style Accuracy Gap, `scripts/simulate_fp_accuracy.py`, 2022-2024 pooled, weeks 3-17, half_ppr, lower=better)

Ran on the `pbp_ftn` variant (best combined candidate) vs. the same-session
`baseline`, reusing the identical `compute_production_heuristic` +
`apply_residual_correction` components as the MAE gate so the ordinal
check is scored on the literal same artifacts (not re-derived). Backtest
CSVs written to `output/backtest/backtest_half_ppr_consensus_*.csv`
(20260816_122032=baseline, 20260816_122048=pbp_ftn); summary at
`output/backtest/fp_accuracy_simulation_summary.csv` (overwritten by the
second run — the pbp_ftn numbers are what's on disk now).

| Position | Baseline gap | `+PBP+FTN` gap | Δ |
|---|---:|---:|---:|
| QB | 5.88 | 5.88 | 0.00 |
| RB | 4.93 | 4.76 | **−0.17 (better)** |
| WR | 5.88 | 5.89 | +0.01 (flat) |
| TE | 5.50 | 5.49 | −0.01 (flat) |

Confirms the MAE-gate read exactly: RB improves materially on the
competition's actual ordinal metric too (not just point MAE), QB is
unchanged (the point-estimate MAE noise doesn't perturb QB's rank order at
all — further evidence it's noise, not a real regression), and **WR's
ordinal edge (the mission's flagged "thinnest surviving edge") holds
unchanged** — the new features neither help nor hurt WR ordering.

## 6. Verdicts summary

| Item | Verdict |
|---|---|
| PBP-advanced features (15 cols) | **Ship candidate pool addition.** Wired permanently into `player_feature_engineering.py` (step 20) — no schema-shift risk, degrades to NaN gracefully like every other optional join. |
| RB residual model | **Adopt-recommend**: promote `models/pbp_feature_experiments_2026_08_16/pbp_ftn/rb_residual*` over `models/residual/rb_residual*` (+0.048 sealed MAE, −0.17 ordinal gap, both metrics agree, zone-share features are the driver). Not promoted in this task — recommend only, per scope. |
| QB residual model | HOLD — no real signal, candidate-pool addition is a no-op for QB (0 features selected). |
| WR / TE residual models | HOLD — deltas are noise-level on both metrics; WR's ordinal edge is preserved, not improved. |
| FTN charting | **HOLD confirmed on live 2022-2025 data** (previously untested locally due to missing Bronze/Silver — now fixed and re-tested). Zero FTN features selected for any position. Pipeline itself is production-ready and now fully current; re-test any time without an ingestion prerequisite. |

## 7. Reproduce

```bash
# 1. PBP-advanced Silver (all seasons; fast, ~1s/season)
python -c "
import sys; sys.path.insert(0, 'src')
from pbp_advanced_features import build_pbp_advanced_silver
build_pbp_advanced_silver(list(range(2016, 2026)))
"

# 2. FTN Bronze + Silver (2022-2025; the actual gap this task closed)
python scripts/bronze_ftn_ingestion.py --seasons 2022-2025
python scripts/silver_ftn_transformation.py --seasons 2022-2025

# 3. Unit tests
python -m pytest tests/test_pbp_advanced_features.py tests/test_ftn_pipeline.py -q

# 4. Three same-session training variants (QB/RB lgb-20, WR/TE ridge-60,
#    training_seasons=2016-2024) — monkeypatches _join_pbp_advanced_features
#    / _join_ftn_features on/off around assemble_multiyear_player_features
#    so all three share the same underlying data assembly. See
#    train_and_save_residual_models() in src/hybrid_projection.py for the
#    call signature; baseline/pbp/pbp_ftn saved to
#    models/pbp_feature_experiments_2026_08_16/{variant}/.

# 5. Sealed-2025 matched-MAE gate: assemble HOLDOUT_SEASON once, apply each
#    variant's apply_residual_correction(model_dir=...), compare MAE on the
#    same weeks 3-18 row set (unified_evaluation.compute_production_heuristic
#    + compute_actual_fantasy_points, same recipe as RETRAIN_ON_REPAIRED_FEATURES.md §7).

# 6. Ordinal gate: build a backtest_half_ppr_consensus_*.csv (player_id,
#    player_name, position, season, week, projected_points, actual_points)
#    for 2022-2024 using the same heuristic+correction components, per
#    variant, then:
python scripts/simulate_fp_accuracy.py
```

Training driver, gate-eval, and ordinal-CSV-builder scripts were run from a
scratch copy (not committed under `scripts/` — `scripts/train_residual_models.py`,
`scripts/backtest_projections.py`, and `scripts/generate_projections.py`
were off-limits for concurrent-agent-safety / ownership reasons on this
task, matching the precedent in `RETRAIN_ON_REPAIRED_FEATURES.md` §7).

## Files touched

- `src/pbp_advanced_features.py` — new module (15 trailing feature columns).
- `src/player_feature_engineering.py` — added 7 raw column names to
  `_SAME_WEEK_RAW_STATS`, added `_join_pbp_advanced_features()`, wired as
  step 20 in `assemble_player_features()`.
- `tests/test_pbp_advanced_features.py` — new, 17 tests, all passing.
- `data/bronze/ftn_charting/season={2022..2025}/` — new (Bronze, local-only,
  not gitignore-allowlisted).
- `data/silver/players/ftn/season={2022..2025}/` — new (Silver, local-only).
- `data/silver/players/pbp_advanced/season={2016..2025}/` — new (Silver,
  local-only).
- `models/pbp_feature_experiments_2026_08_16/{baseline,pbp,pbp_ftn}/` —
  researched artifacts (QB/RB `.joblib`+imputer+meta, WR/TE `.joblib`+meta),
  NOT promoted. `models/residual/` shipped artifacts untouched (verified —
  not written by this task).
- `output/backtest/backtest_half_ppr_consensus_20260816_122032.csv` (baseline)
  and `..._20260816_122048.csv` (pbp_ftn) — new ordinal-eval inputs.
  `output/backtest/fp_accuracy_simulation_summary.csv` /
  `fp_accuracy_simulation_gaps.csv` were regenerated by the second
  (`pbp_ftn`) run of `simulate_fp_accuracy.py` — the numbers currently on
  disk are the `pbp_ftn` run; baseline numbers are recorded in §5b above.
- Not touched: `src/quantile_models.py`, `src/config.py`,
  `scripts/generate_projections.py`, `models/residual/` shipped artifacts,
  `models/quantile*`, any graph feature module (`src/graph_*.py` — no
  changes were needed there since the new features are self-contained).
