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

_Pending — filled in below after coverage report, walk-forward, and sealed
one-shot confirmation runs. This section intentionally left as a stub at
commit time so the design above is provably pre-registered before any
number was read._
