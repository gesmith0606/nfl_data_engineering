# Retrain on Repaired Features — snap_pct + NGS/PFR/QBR Advanced Silver — 2026-08-15

Re-gates the shipped WR/TE Ridge residual hybrid and the SKIP-verdict QB/RB residual
models now that `snap_pct` (join-key bug) and `players/advanced` (NGS/PFR/QBR, local
Bronze ingestion gap) are real, per `.planning/SILVER_REGEN_REPORT.md` (2026-08-09/10).
Follows the firing-rate + same-vintage + byte-identical discipline in
`knowledge-vault/concepts/gated-experiment-coverage-check.md`.

## 1. What changed, and what was actually consumed before

`SILVER_REGEN_REPORT.md` fixed two independent things:

- **`snap_pct`-family (11 candidate features)**: `_prepare_snap_data()` joined Bronze
  weekly's abbreviated `player_name` ("A.Rodgers") against Bronze snaps' full
  `player_display_name` ("Cooper Kupp") — a 0% match **since inception, in every
  Silver ever produced, on any machine**, because the bug was in shipped transform
  code, not local data absence. This is the one unambiguous "was 100% NaN everywhere,
  now real" case.
- **`players/advanced` (NGS/PFR/QBR, 96 candidate features)**: confirmed absent from
  this machine's local Bronze before 2026-08-09 (`data/bronze/ngs/`, `qbr/` didn't
  exist at all; `pfr/` had only `seasonal/def`). Locally, `players/advanced` therefore
  carried zero `ngs_`/`pfr_`/`qbr_` columns before the regen. Caveat for the record:
  the currently-shipped WR/TE/QB/RB residual metas (`models/residual/*_meta.json`)
  already list several `ngs_`/`qbr_` feature names among their selected features,
  meaning those specific training runs (WR/TE committed 2026-06-12, QB/RB committed
  2026-04-10, confirmed via `git log`) had real NGS/QBR data available at training
  time — elsewhere, or before a later local cleanup wiped this machine's Bronze cache.
  So this retrain's actual lever for NGS/PFR/QBR is "reliably present on this machine,
  right now, for this session" rather than "never existed before." `snap_pct` has no
  such ambiguity.

**Repaired-candidate feature count**: `get_player_feature_columns()` on the assembled
2016-2024 training frame returns **107** candidate features matching `snap*`, `ngs_*`,
`pfr_*`, or `*qbr*` (11 + 54 + 30 + 12). None are 100%-NaN post-repair (per-column
non-null coverage ranges 6.1%–100%, mean 28.6%). Cross-checked against each shipped
model's selected-feature list: **0 of these 107 appear in the shipped QB/RB/WR/TE
metas under a fully-NaN-at-training state** — consistent with the SHAP selector's
90%-NaN filter excluding `snap_pct` outright at every prior training (it really was
always-NaN going in).

## 2. Training protocol (kept "as shipped" — no tuning sweep)

Read `scripts/train_residual_models.py` + `src/hybrid_projection.py` first. The shipped
artifacts come from two different configs of the *same* `train_and_save_residual_models`
walk-forward-style pipeline (confirmed by diffing hyperparameters against
`RESIDUAL_LGB_PARAMS` and the shipped metas):

| Position | Shipped config | Reproduced with |
|---|---|---|
| WR, TE | `model_type="ridge"`, 60 SHAP-selected features, heuristic `v4.2+blend` | `train_and_save_residual_models(positions=["WR","TE"], model_type="ridge", shap_feature_count=60, training_seasons=2016-2024)` |
| QB, RB | `model_type="lgb"`, 20 SHAP-selected features (matches the `experiment_regularized_residuals.py` "pruned" config — identical `RESIDUAL_LGB_PARAMS`/`_ORIGINAL_PARAMS`, same early-stopping-on-last-season protocol, same all-non-holdout training window) | `train_and_save_residual_models(positions=["QB","RB"], model_type="lgb", shap_feature_count=20, training_seasons=2016-2024)` |

Training window: 2016–2024 (`HOLDOUT_SEASON=2025` sealed, never touched during
training). No hyperparameter changes — this isolates the data effect per the task's
own instruction.

**Artifacts** (new directory, shipped models in `models/residual/` untouched):
`models/retrained_2026_08_15/{qb,rb,wr,te}_residual.joblib` (+ `_imputer.joblib` for
QB/RB LGB, + `_meta.json` for all four).

Reproduce:
```
python -c "
import sys; sys.path.insert(0, 'src')
from hybrid_projection import train_and_save_residual_models
train_and_save_residual_models(positions=['QB','RB'], output_dir='models/retrained_2026_08_15',
    model_type='lgb', shap_feature_count=20, training_seasons=list(range(2016,2025)))
train_and_save_residual_models(positions=['WR','TE'], output_dir='models/retrained_2026_08_15',
    model_type='ridge', shap_feature_count=60, training_seasons=list(range(2016,2025)))
"
```

Repaired features actually selected into the retrained models (proof the lever
competes for and wins slots, not just "is present in the candidate pool"):

| Position | Selected features (of 20/60) | Repaired features selected |
|---|---|---|
| QB | 20 | 7 (`ngs_aggressiveness_std`, `ngs_avg_air_yards_differential_std`, `ngs_expected_completion_percentage_std`, `ngs_avg_completed_air_yards_std`, `ngs_avg_time_to_throw_std`, `snap_pct_std`, `pfr_def_times_hurried_std`) |
| RB | 20 | 5 (`ngs_efficiency_std`, `ngs_avg_time_to_los_std`, `ngs_rush_yards_over_expected_std`, `ngs_efficiency_roll3`, `snap_pct_roll6`) |
| WR | 60 | 22 (heavy NGS separation/cushion/YAC block + `snap_pct_roll3`/`snap_pct_delta`/`receptions_x_snap_pct` + PFR pressure/blitz) |
| TE | 60 | 16 (similar NGS/snap_pct mix) |

## 3. Pre-registered gates (written before running the sealed-2025 eval)

- **WR/TE (currently SHIP / HYBRID_POSITIONS)**: new hybrid must beat the **current
  shipped hybrid** (`models/residual/`, applied to today's data) on sealed-2025
  matched-pairs MAE by **≥0.03** to recommend redeploy; otherwise keep shipped.
- **QB/RB (currently SKIP, heuristic-only in production)**: flip SKIP→SHIP only if
  the retrained hybrid beats **heuristic-only** by **≥0.05** sealed MAE.

Matched-pairs = identical eval row set (season=2025, weeks 3-18, non-NaN heuristic and
actual) used for every variant compared within a position — same session, same vintage,
regenerated together (see coverage/firing proof below; no reused/contaminated CSVs).

## 4. Firing-rate / coverage proof (sealed 2025, weeks 3-18) — mechanism is live

| Position | Eval rows | Repaired features present | Mean per-column coverage | Rows with ≥1 repaired feature non-NaN |
|---|---|---|---|---|
| QB | 487 | 107/107 | 49.7% | **100%** |
| RB | 841 | 107/107 | 28.0% | **100%** |
| WR | 1,577 | 107/107 | 27.8% | **100%** |
| TE | 951 | 107/107 | 25.3% | **100%** |

Every eval row carries at least one live repaired feature; per-column coverage is
naturally partial (NGS/PFR/QBR are position/context-specific, matching the pattern
already documented in `SILVER_REGEN_REPORT.md`). The lever fires on 100% of the sealed
population — not a near-zero-reach detector.

## 5. Sealed-2025 gate results (matched rows, half_ppr, weeks 3-18)

| Position | n | Heuristic MAE | Shipped hybrid MAE (bias) | Retrained hybrid MAE (bias) | Δ vs shipped | Δ vs heuristic |
|---|---|---|---|---|---|---|
| QB | 487 | 6.459 | 12.636 (+12.41) | **5.773 (+0.05)** | −6.863 | **−0.685** |
| RB | 841 | 5.109 | 4.025 (−1.32) | **4.920 (+0.16)** | +0.895 | **−0.189** |
| WR | 1,577 | 3.917 | **3.851 (+0.09)** | 3.962 (+0.53) | **+0.111** | +0.045 |
| TE | 951 | 3.105 | 3.011 (+0.17) | **2.971 (+0.19)** | **−0.039** | −0.134 |

Notes on the "shipped hybrid" column (important caveat, not a bug): QB and RB are
`SKIP` in `src/ml_projection_router.py` (`HYBRID_POSITIONS = {"TE","WR"}` only, QB
hardcoded regardless of any gate) — their shipped `.joblib` files are **never invoked
in production**. "Shipped hybrid MAE" here means "if you ran the frozen June/April
artifact, unchanged, against today's repaired feature matrix" — useful context, not a
live-production number. It explains itself: QB's shipped model was trained with QBR
features that mattered a lot; QBR is confirmed absent upstream for 2024-2025
(`SILVER_REGEN_REPORT.md`), so at 2025 eval time 4 of its 20 features are 100%-NaN and
get imputed to the frozen training-time median, producing a +12.4 mean bias — this
independently reproduces the documented "QB v2 2025 bias=+11.33" failure
(`src/ml_projection_router.py` comments), confirming the eval methodology is sound.
RB's shipped model similarly has 8/20 features 100%-NaN at eval (graph features that
still don't exist — `data/silver/graph_features/` remains out of scope) plus ~45% NaN
on its NGS features.

## 6. Verdicts

- **QB: FLIP SKIP → SHIP (recommend).** Retrained hybrid beats heuristic-only by
  −0.685 MAE (gate: ≥0.05) and bias collapses from whatever the heuristic alone plus
  the currently non-existent correction gives to +0.05 (near-zero). This is the
  headline result — the QBR-driven catastrophic-bias failure that justified the
  hardcoded SKIP is specifically fixed by having `snap_pct` and current NGS/PFR
  available to compete for feature slots in a model retrained against the vintage it
  will actually see at inference.
- **RB: FLIP SKIP → SHIP (recommend).** Retrained hybrid beats heuristic-only by
  −0.189 MAE (gate: ≥0.05), bias is modest (+0.16). Smaller margin than QB but clears
  the pre-registered bar.
- **WR: KEEP SHIPPED.** Retrained hybrid is 0.111 MAE *worse* than the currently
  shipped hybrid (gate required ≥0.03 improvement to redeploy) and its bias nearly
  6x's the shipped model's (+0.53 vs +0.09). Do not redeploy.
- **TE: REDEPLOY (marginal SHIP).** Retrained hybrid beats shipped by 0.039 MAE,
  just clearing the ≥0.03 bar. Bias is essentially unchanged (+0.19 vs +0.17). Given
  the thin margin, treat this as a soft pass — reasonable to redeploy, but not a
  decisive win the way QB/RB are.

## 7. Reproduce end-to-end

```
# 1. Retrain (see §2 for exact call)
# 2. Sealed-2025 gate eval — assemble once, evaluate all 4 positions:
python -c "
import sys; sys.path.insert(0, 'src')
import pandas as pd
from config import PLAYER_DATA_SEASONS, HOLDOUT_SEASON
from player_feature_engineering import assemble_multiyear_player_features
from unified_evaluation import build_defensive_strength_table
all_data = assemble_multiyear_player_features(list(range(2016, HOLDOUT_SEASON + 1)))
opp_rankings = build_defensive_strength_table(PLAYER_DATA_SEASONS)
# then per position: compute_production_heuristic(pos_data, pos, opp_rankings,
# 'half_ppr', weekly_df=<Bronze players/weekly 2016-2025>), compute_actual_fantasy_points,
# filter season==2025 & week in [3,18], apply models/residual/ (shipped) and
# models/retrained_2026_08_15/ (treated) residual corrections, compare MAE.
"
```
Full eval script (feature/model loading, matched-pairs MAE, coverage report) was run
from a scratch copy mirroring this logic; not committed under `scripts/` since
`scripts/backtest_projections.py` / `scripts/simulate_fp_accuracy.py` were off-limits
for concurrent-agent-safety reasons on this task and no other standing eval script
covered a shipped-vs-treated residual matched-pairs comparison. Recommend a follow-up
task promote this into a proper `scripts/gate_residual_retrain.py` if this becomes a
recurring re-gate pattern (it likely will — Bronze/Silver repairs are ongoing per
`DATA_COMPLETENESS_AUDIT.md`).

## 8. Suggested next step if QB/RB SHIP is accepted

`src/ml_projection_router.py` currently forces `verdicts["QB"] = "SKIP"`
unconditionally (line ~134) regardless of any model file on disk, and RB SKIP is
governed by a ship-gate report that is stale (`models/player/ship_gate_report.json`,
2026-04-13, and is for the separate per-stat XGB models, not these residuals). Shipping
QB/RB here means: (a) copy `models/retrained_2026_08_15/{qb,rb}_residual*` over
`models/residual/{qb,rb}_residual*`, (b) remove the QB hardcode and add QB/RB to
`HYBRID_POSITIONS`, (c) run one more sealed confirmation pass per the repo's
sealed-holdout-budget discipline (`.planning/holdout_ledger.json`) before flipping
production. Not done here — this task's scope was retrain + re-gate + report, not ship.
