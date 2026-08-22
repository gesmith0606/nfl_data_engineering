# ffopportunity Expected-Points Trailing Features Gate — Pre-Registration (2026-08-21)

Gated experiment for the ffopportunity Expected-Points (EP) Silver features
(`data/silver/ffopportunity_features/season=YYYY/`, 2016-2025, gsis-keyed
player-weeks — see `.planning/FFOPPORTUNITY_COVERAGE.md` and
`scripts/ingest_ffopportunity.py`, both already built by a prior task; this
gate only adds trailing candidate features on top of that existing Silver
and evaluates them). Follows the firing-rate + same-vintage discipline in
`knowledge-vault/concepts/gated-experiment-coverage-check.md` and mirrors
the exact protocol used to promote QB/RB configs in
`.planning/PBP_FEATURES_2026_08_16.md` / `.planning/CONSOLIDATION_2026_08_16.md`
(the pbp_advanced_features precedent: candidate module -> wired into the
per-position hybrid/ML pool -> walk-forward 2022-2024 selection -> one-shot
sealed-2025 confirm).

## Hypothesis

ffopportunity's expected-fantasy-points and actual-minus-expected residual
features, as TRAILING (lagged) aggregates, capture opportunity *quality*
that raw box-score trailing stats miss — e.g. a WR with high expected but
low actual points over recent weeks is a positive-regression candidate.
Adding these as candidate features should improve per-position sealed-2025
MAE for the residual correction models.

## Design (pre-registered before any results are read)

- **Features** (all trailing-window aggregates, shift(1)-lagged so week-N
  values use weeks <N only within (player_id, season) — same discipline as
  every existing trailing feature in `player_feature_engineering.py`,
  reusing the `pbp_advanced_features.py` shift/rolling/expanding pattern):
  - `ffopp_exp_fantasy_points_total_{roll3,roll5,trail}`
  - `ffopp_fantasy_points_over_expected_{roll3,roll5,trail}`
  - `ffopp_total_opportunities_{roll3,roll5,trail}` (`total_opportunities`
    = `pass_attempts + targets + carries`, the opportunity-count signal
    named in the mission brief)
  - 9 columns total, module: `src/ffopportunity_features.py`
    (`FFOPPORTUNITY_EP_FEATURE_COLUMNS`).
- **Wiring**: new `_join_ffopportunity_features()` in
  `src/player_feature_engineering.py`, called as an additional step in
  `assemble_player_features()`, mirroring `_join_pbp_advanced_features()`
  exactly (left-join on `player_id, season, week`, NaN-fill when the Silver
  partition or row is absent). Unlike FTN/pbp_advanced there is no
  `position_type` role split needed — `ingest_ffopportunity.py` already
  merges a player's passer/rusher/receiver contributions onto one row per
  `(player_id, season, week)`. Added to the candidate pool only —
  `get_player_feature_columns()` picks the new columns up automatically
  (numeric, not excluded, passes `_is_unlagged_leak` since the `ffopp_`
  prefix is not in `_SAME_WEEK_PREFIXES` and the raw un-lagged source
  columns are never merged into the training frame, only the lagged
  variants). **No default/shipped model changes** — candidates stay in the
  pool whether the gate ships or holds, per the mission's explicit rule.
- **Gate protocol** (mirrors `CONSOLIDATION_2026_08_16.md` exactly):
  1. Walk-forward CV selection: `train_residual_model()` (Ridge,
     `val_seasons=[2022, 2023, 2024]`, expanding window, weeks 3-18,
     half_ppr) comparing the current shipped candidate pool
     (`get_player_feature_columns`) vs. pool + the 9 EP features, per
     position. Never touches 2025.
  2. Exactly ONE sealed-2025 confirmation read per position that clears
     walk-forward, via `train_and_save_residual_models()` retrained to a
     scratch directory (`training_seasons=2016-2024`, same `model_type`/
     `shap_feature_count` the position currently ships per CLAUDE.md:
     QB/RB `lgb` shap=20, WR/TE `ridge` shap=60) then `apply_residual_correction`
     evaluated against `HOLDOUT_SEASON=2025` actuals, matched rows only.
  3. **Adopt-recommend bar**: sealed MAE improves by >=0.03 (same bar as the
     Aug-16 sprint's RB PBP-feature promotion, `+0.048`/`+0.071`/`+0.096`
     precedent range). **REJECT** (do not even recommend) any position
     whose walk-forward and sealed deltas disagree in sign — that is
     itself a HOLD/inconclusive signal, not evidence for adoption.
- **Coverage first**: EP-Silver join rate to the training population
  (base usage rows), per season/position, computed and reported BEFORE any
  MAE numbers — changed-rows/firing proof, not just presence of the column
  in the schema. A gate with near-zero firing rate is a data problem, not a
  hypothesis result (per the coverage-check doc's Rule).
- **Deconfound / ablation**: ffopportunity EP correlates heavily with raw
  volume (targets/carries/pass_attempts) already in the pool. To make sure
  the gate measures NEW information and not feature-count inflation, a
  matched-count **ablation control set** is built from the SAME Silver
  source and SAME join/lag mechanism: `ffopp_vol_{targets,carries,
  pass_attempts}_{roll3,roll5,trail}` (9 columns, raw volume only, no EP
  model information) — NOT wired into the production candidate pool, used
  only inside this gate's scratch training runs to produce a
  pool+volume-ablation variant alongside pool+EP. If pool+EP does not beat
  pool+volume-ablation by a comparable-or-larger margin, the EP signal is
  not adding information beyond volume and the verdict is HOLD regardless
  of the pool+EP vs baseline delta alone.
- **Verdict rules**: promote per-position ONLY where (a) walk-forward and
  sealed deltas agree in sign, (b) sealed clears the >=0.03 bar, and (c) the
  EP variant beats the volume-ablation variant on the same sealed read —
  marked **SHIP-PENDING-USER** (2.5 weeks before draft, no default flip
  without user go-ahead). Otherwise **HOLD**. Candidates stay in the pool
  either way (matches the PBP-features precedent: RB's zone-share features
  stayed in the pool even for positions that held).

## Files this task will touch

- NEW `src/ffopportunity_features.py` (candidate module).
- NEW `tests/test_ffopportunity_features.py` (lag correctness, join
  correctness, rolling math, empty-history fail-safe).
- `src/player_feature_engineering.py` — additive-only new join step
  (mirrors `_join_pbp_advanced_features`), no changes to existing steps.
- This doc, updated in place with results after the protocol above runs.
- Scratch gate-eval scripts run from the session scratchpad (not committed
  under `scripts/`, matching the `RETRAIN_ON_REPAIRED_FEATURES.md` /
  `PBP_FEATURES_2026_08_16.md` §7 precedent for concurrent-agent-safety on
  `scripts/train_player_models.py`'s neighbors).

Not touched: `src/feature_engineering.py`, `src/ensemble_training.py`,
`scripts/train_ensemble.py`, `scripts/generate_predictions.py`,
`scripts/backtest_predictions.py` (ensemble agent), any `*fp_ecr*`/
`*ecr_bridge*`/`refresh_external_rankings` path (bridge agent), or
`.github/workflows/madden*` (orchestrator).

## Results

### 1. Coverage first (before any MAE number)

Join rate of `ffopp_exp_fantasy_points_total_trail` (representative EP
column) against the training population, per season/position, computed via
`assemble_player_features()` after wiring — i.e. this measures the lever
actually firing, not just the column existing in the schema. Full table:
`.planning/EP_FEATURES_coverage.csv`.

| | raw join rate (all rows) | eligible (week>=3) join rate |
|---|---:|---:|
| Range across all 10 seasons x 4 positions | 83.6% - 92.3% | 88.2% - 98.2% |
| 2016 (oldest, worst case) | 89.2%-91.8% | 94.5%-97.8% |
| 2025 (newest) | 83.6%-90.5% | 88.2%-96.1% |

No season/position combination is anywhere near zero — the join fires
broadly (this is NOT one of the silent-no-op instances the coverage-check
doc warns about). The ~2-15% non-join gap is expected: the ffopportunity
Silver's own coverage is ~89-97% of player-weeks (per
`FFOPPORTUNITY_COVERAGE.md`) plus `min_periods=2` in the trailing window
means every player's first 2 in-season weeks are legitimately NaN
regardless of source coverage. **A real bug was caught and fixed at this
stage**: the module's `_default_silver_dir()` initially pointed at
`data/` instead of `data/silver/` (missing the `silver` path segment) —
the first coverage run showed **0.0% join rate for every single
season/position**, which is exactly the silent-join failure pattern
`gated-experiment-coverage-check.md` warns about. Fixed before any MAE
number was read (see commit history — this doc's design section above was
already committed before this bug was found and fixed).

### 2. Walk-forward CV (2022-2024, Ridge, matches `train_residual_model` protocol)

Full numbers: `.planning/EP_FEATURES_walkforward.json`.

| Position | baseline | +EP | +VOL (ablation) | baseline→EP Δ | EP vs VOL |
|---|---:|---:|---:|---:|---:|
| QB | 5.9058 | 5.8836 | **5.8679** | +0.0222 | VOL beats EP by 0.0157 |
| RB | 4.8908 | **4.8846** | 4.8898 | +0.0062 | EP beats VOL by 0.0052 |
| WR | 4.0228 | **4.0175** | 4.0269 | +0.0053 | EP beats VOL by 0.0094 |
| TE | 3.2268 | 3.2284 | 3.2270 | **−0.0016** | both worse than baseline |

(Δ = baseline − variant; positive = improvement.)

**A second real bug was caught here before results were trusted**: the
first walk-forward run merged the volume-ablation columns into `all_data`
*before* computing "baseline" and "plus_ep" feature pools via
`get_player_feature_columns()` — since that function auto-includes any
numeric non-excluded column, the volume-ablation columns silently leaked
into the "baseline" and "plus_ep" pools too (both variants unintentionally
already contained the 9 `ffopp_vol_*` columns, and "plus_vol_ablation"
double-counted them). This is the exact "contaminated baseline" failure
shape from `gated-experiment-coverage-check.md`'s fourth instance. Caught
because `_select_residual_features` crashed on a duplicate-column-name
`ValueError` during the sealed run (RB `plus_vol` variant), traced back,
and the walk-forward run was fully redone with an explicit exclusion of
`FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS` from the "baseline"/"plus_ep" pool
construction. The numbers above are from the corrected re-run.

**Reading**: QB fails the ablation check outright (volume alone beats EP —
the EP "improvement" over baseline is just feature-count inflation from
correlated volume, exactly the confound this gate was designed to catch).
TE's EP variant is worse than baseline. Only **RB and WR** clear
walk-forward selection (EP beats both baseline and the volume-ablation
control) and qualify for a sealed-2025 touch per the pre-registered
protocol.

### 3. Sealed-2025 one-shot confirmation (RB `lgb` shap=20, WR `ridge` shap=60 — matches shipped model_type/shap_feature_count)

Full numbers: `.planning/EP_FEATURES_sealed.json`.

| Position | baseline MAE | +EP MAE | +VOL MAE | baseline→EP Δ | bias (baseline→EP) |
|---|---:|---:|---:|---:|---:|
| RB (n=841) | 4.7681 | 4.8059 | 4.7723 | **−0.0378 (worse)** | +0.0575 → +0.0617 |
| WR (n=1577) | 3.9488 | 3.9845 | 3.9472 | **−0.0357 (worse)** | +0.5327 → +0.6269 |

Both positions' walk-forward Δ was positive (+0.0062 RB, +0.0053 WR) but
the sealed Δ is negative and an order of magnitude larger in the wrong
direction (−0.038, −0.036) — **walk-forward and sealed signs disagree for
both positions**. Per the pre-registered REJECT rule, both are rejected
outright rather than scored as a borderline HOLD.

This was not SHAP-selection noise on an empty slot (the QB caveat pattern
from `PBP_FEATURES_2026_08_16.md`) — the EP features actually won SHAP
selection slots in both sealed models: RB kept
`ffopp_exp_fantasy_points_total_trail` (1/20 features), WR kept
`ffopp_fantasy_points_over_expected_roll5`,
`ffopp_fantasy_points_over_expected_trail`, and
`ffopp_exp_fantasy_points_total_trail` (3/60 features) — displacing other
features that generalized better to 2025. This is a genuine
overfit-to-walk-forward-folds result, not a measurement artifact. WR's
bias also got materially worse (+0.53 → +0.63 over-projection) with EP
active, consistent with the residual model leaning on the EP signal in a
way that doesn't transfer to the sealed season.

### 4. Verdict

| Position | Walk-forward | Ablation (EP vs VOL) | Sealed | Verdict |
|---|---|---|---|---|
| QB | +0.0222 (looks like improvement) | **FAILS** — VOL beats EP | not spent (ablation already disqualifies) | **HOLD** — EP's apparent gain is volume/feature-count inflation, not new information |
| RB | +0.0062 (clears selection) | EP beats VOL | **−0.0378 (worse)**, sign disagrees with walk-forward | **REJECT** |
| WR | +0.0053 (clears selection) | EP beats VOL | **−0.0357 (worse)**, sign disagrees with walk-forward | **REJECT** |
| TE | −0.0016 (already worse) | both worse than baseline | not spent (walk-forward already fails) | **HOLD** |

**No position ships or is marked SHIP-PENDING-USER.** The 9
`FFOPPORTUNITY_EP_FEATURE_COLUMNS` stay in the candidate pool (per the
pre-registered rule — candidates remain regardless of verdict, matching
the RB zone-share precedent from `PBP_FEATURES_2026_08_16.md`), but no
default/shipped model or projection behavior changes as a result of this
gate. `player_feature_engineering.assemble_player_features()`'s new step
21 join is additive-only and was already exercised end-to-end by every
season assembled during this gate (2016-2025) with no errors, so the
wiring itself is confirmed sound — only the *modeling* verdict is HOLD.

**Takeaway for future gates**: this is a second, independent confirmation
of the `gated-experiment-coverage-check.md` corollary — a feature that
"wins" walk-forward selection by a few thousandths of a MAE point is not
distinguishable from noise/overfitting to the 3-season expanding-window
folds, and the one-shot sealed touch exists precisely to catch that before
a HOLD gets mistaken for a SHIP. Both real bugs caught during this task
(wrong Silver path -> 0% coverage; volume-ablation leaking into the
baseline pool) are now covered by this gate's own passing test suite
(`tests/test_ffopportunity_features.py`) and this doc, respectively.
