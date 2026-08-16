# Graph Feature Revival — 2026-08-16

Executes opportunity-scan move #3 (`OPPORTUNITY_SCAN_2026_08_16.md` §Part 2
candidate #3): PBP bronze + graph feature pipeline was structurally dead
locally — Neo4j down, `data/silver/graph_features` absent, `data/bronze/pbp`
and `pbp_participation` absent entirely — so every true graph-module feature
live-probed as 100% NaN across every model family. This task: (1) ingest PBP
bronze 2016-2025 with participation, (2) regenerate Silver `graph_features`,
(3) verify consumers actually pick it up, (4) re-gate TE residual, (5) re-gate
quantile. Scope: data ingest + `scripts/compute_graph_features.py` +
`scripts/train_quantile_models.py` + `models/quantile*` + a standalone TE-only
retrain to `models/te_graph_2026_08_16/`. Did not touch `src/feature_engineering.py`,
the game ensemble, `models/residual/` shipped artifacts, or WR/QB/RB anything
(owned by a concurrent agent).

## 1. PBP bronze ingest (2016-2025, `--include-participation`)

One season per command, foreground. Each season took **~3.1-3.4 seconds**
(the mission's ~100-400MB/season estimate was for raw upstream size; the
parquet output nflverse ships is far smaller and nfl_data_py pulls from a
cached release, not a live scrape):

| Season | Records | Time |
|---|---:|---:|
| 2016 | 47,651 | 3.35s |
| 2017 | 47,245 | 3.14s |
| 2018 | 47,109 | 3.09s |
| 2019 | 47,260 | 3.12s |
| 2020 | 47,705 | 3.23s |
| 2021 | 49,922 | 3.27s |
| 2022 | 49,434 | 3.15s |
| 2023 | 49,665 | 3.43s |
| 2024 | 49,492 | 3.27s |
| 2025 | 48,771 | 3.36s |

Total: **54 MB** `data/bronze/pbp/` + **12 MB** `data/bronze/pbp_participation/`
= **66 MB** for all 10 seasons. Sanity-checked 2016 (full season through
playoffs, weeks 1-21, EPA populated on 45,245/47,109 relevant rows). All
other `compute_graph_features.py` inputs (`players/rosters`, `depth_charts`,
`players/injuries`, `players/weekly`, `pfr/weekly/def`, `schedules`) already
existed locally for 2016-2025 (TD-08/09/10 committed paths + prior ingests) —
PBP/participation were the only missing pieces.

**Local-only, confirmed**: `data/*` is gitignored at the top with a targeted
`!data/bronze/...` allowlist per TD-08/09/10; `data/bronze/pbp/` and
`pbp_participation/` have **no** allowlist entry, so both stay git-ignored by
default — no action needed, this is already the correct state per the
mission's "do NOT gitignore-allowlist it" instruction.

## 2. Silver `compute_graph_features.py` (2016-2025)

One season per command, ~65-96s/season (faster than the ~2.5 min/season
documented estimate):

| Season | Time | Output size |
|---|---:|---:|
| 2016 | 65.0s | 1.46 MB |
| 2017 | 78.1s | 1.47 MB |
| 2018 | 71.6s | 1.49 MB |
| 2019 | 75.6s | 1.48 MB |
| 2020 | 70.2s | 1.55 MB |
| 2021 | 80.1s | 1.60 MB |
| 2022 | 86.6s | 1.56 MB |
| 2023 | 84.3s | 1.58 MB |
| 2024 | 85.6s | 1.56 MB |
| 2025 | 96.2s | 1.79 MB |

**`data/silver/graph_features/` total: 16 MB** across 10 seasons — well
under the ~30MB threshold. **Recommend allowlist + commit** (TD-08/09/10
pattern) — production (Railway/HF Spaces) needs this Silver output and it's
cheap enough to ship in git; not committed by this task per instructions
(data-layer changes only, no repo-policy edits).

TE-position coverage at compute time (season 2016 sample, `report_quality`
output): WR player-weeks 74.7%, RB player-weeks (OL features) 88.8%, **TE
player-weeks 94.7%**. `vacated_opportunity` correctly empty for 2016 (needs
season N-1 data, 2015 absent) and populated from 2017 onward. Week-1 temporal
leak checks all passed (`OK: ... is all NaN in week 1`).

## 3. Consumer verification — before/after coverage (firing-rate check)

`src/player_feature_engineering.py` (distinct file from `src/feature_engineering.py`,
not touched) reads `data/silver/graph_features/season=YYYY/` directly via
`_join_graph_features`, `_join_wr_matchup_features`, `_join_te_*`,
`_join_red_zone_features`, etc. — all previously no-op'd gracefully (Neo4j
down, no Silver fallback = 100% NaN, confirmed in `OPPORTUNITY_SCAN_2026_08_16.md`).

**Before** (from the opportunity scan, this session's starting point): every
true graph-module feature probed **100% NaN** — Neo4j down + no local Silver
fallback. Quantile: 58/486 selected features were graph-pattern, "mostly
100% NaN." TE candidate pool: 0 true graph features even reached the
shipped 60-feature selection (they weren't live enough to compete).

**After** — TE-position rows (`assemble_multiyear_player_features(2016..2025)`,
8,621 TE player-weeks), previously-dead graph features now non-NaN for a
large majority of rows:

| Feature | Non-null | Feature | Non-null |
|---|---:|---|---:|
| `te_def_trail_yds_per_tgt` | 99.9% | `route_rate_trail4` | 93.7% |
| `te_def_trail_comp_rate` | 99.9% | `route_rate_slope` | 86.3% |
| `te_def_trail_lb_coverage_share` | 99.9% | `off_rz_pass_rate_roll3/6` | 100.0% |
| `te_def_trail_cb_coverage_share` | 99.9% | `def_rz_epa_roll6` | 99.9% |
| `qb_wr_chemistry_epa_roll3` | 91.6% | `wr_matchup_light_box_epa_trail8` | 72.0% |
| `rz_target_share_roll3` | 90.3% | `wr_matchup_heavy_box_epa_trail8` | 65.3% |
| `rz_carry_share_roll3` | 35.9% | `wr_matchup_middle_epa_trail8` | 59.8% |
| `te_matchup_rz_personnel_lb_rate_trail8` | 49.2% | `historical_absorption_rate` | 78.0% |
| `script_volatility` | 99.2% | `injury_cascade_target_boost` | 78.0% |

(`rz_carry_share_roll3`/`rz_usage_vs_general`/`te_matchup_rz_personnel_lb_rate_trail8`
land in the 35-49% range — genuinely position-appropriate sparsity, e.g.
carry-share for a receiving position, not a pipeline defect.)

**Quantile candidate pool** (pooled across all 4 positions, 500 total
candidate columns, up from 486 pre-ingest): 255/500 (51%) still ≥50% NaN
pooled, but of the 67 graph-pattern candidate columns only **28/67 remain
≥50% NaN pooled** (down conceptually from "58/486 ... mostly 100% NaN"
pre-ingest) — and those 28 are structurally position-restricted features
(`te_def_trail_*`, `wr_def_trail_*`, `te_matchup_*` are 0% NaN for their own
position and ~100% NaN for the other three, which drags the *pooled* rate up
without indicating any remaining defect — confirmed directly above: TE-only
rows show `te_def_trail_*` at 99.9% non-null).

**Verdict: the dead-graph-feature problem is fixed.** Both the TE candidate
pool and the quantile candidate pool now see live, materially-covered
graph-pattern features instead of the prior universal-100%-NaN state.

## 4. TE re-gate — **KEEP SHIPPED**

Standard protocol, exact recipe from `HYBRID_SHIP_2026_08_15.md`'s TE ship:
`train_and_save_residual_models(positions=['TE'], model_type='ridge',
shap_feature_count=60, training_seasons=2016-2024)`, called directly (not
via the CLI, which hardcodes `models/residual/`) with `output_dir=
'models/te_graph_2026_08_16'` so the shipped TE artifact was never touched.
35s to train, `n_train=7214` (identical population to shipped).

**Feature selection changed materially**: 26/60 features are new vs the
shipped set, and 16 of those are genuine graph-pattern features that
couldn't have been selected before (`qb_wr_chemistry_epa_roll3`,
`route_rate_slope`, `route_rate_trail4`, `rz_target_share_roll3`,
`rz_carry_share_roll3`, `rz_td_rate_roll3`, `rz_usage_vs_general`,
`team_rz_trips_roll3`, `te_matchup_rz_personnel_lb_rate_trail8`,
`opp_rz_td_rate_allowed_roll3`, plus several `off_rz_*`/`def_rz_*` variants).
The shipped model selected **zero** true graph-pattern features.

**Gate eval** (`unified_evaluation.compute_production_heuristic` +
`compute_actual_fantasy_points` + `hybrid_projection.apply_residual_correction`
with `model_dir=None` for shipped vs `model_dir='models/te_graph_2026_08_16'`
for treated — same recipe as `RETRAIN_ON_REPAIRED_FEATURES.md` §7; verified
the two artifacts genuinely diverge, only 14/951 identical predictions,
correlation 0.986, mean |diff| 0.36pt — no silent fallback):

| Slice | n | Shipped MAE | Graph-retrain MAE | Gap (shipped − treated) |
|---|---:|---:|---:|---:|
| Sealed 2025, weeks 3-18 | 951 | 3.449 | 3.491 | **−0.042** |
| 2022-2024 pooled, weeks 3-18 | 2,559 | 3.433 | 3.425 | +0.008 |

**Pre-registered gate**: beat shipped on sealed-2025 by ≥0.03 MAE **AND**
hold on 2022-24. Sealed-2025 gap is **negative** (graph-retrain is 0.042
MAE *worse*, not better) — the primary gate fails outright. The 2022-24
hold-check technically passes (+0.008, essentially flat) but that's moot
once sealed-2025 already misses.

**Verdict: KEEP SHIPPED TE.** Reported honestly per instructions — reviving
the graph features did get 16 of them into the TE candidate pool and
selected, but at a fixed 60-feature budget they displaced other,
apparently more load-bearing features, and net sealed-2025 MAE got
slightly worse. Consistent with the opportunity scan's own framing: TE
already won comfortably pre-revival (0 graph features in its shipped set),
so this was flagged as "not an urgent fix for accuracy" — that read holds.
`models/residual/te_residual*` **untouched** (confirmed via mtime, still
2026-08-15 23:26); new artifact parked at `models/te_graph_2026_08_16/`.

## 5. Quantile re-gate — **HOLD, do not promote**

Same protocol as `QUANTILE_REFIT_2026_08_15.md`:
`python scripts/train_quantile_models.py --positions QB RB WR TE --output-dir
models/quantile_graph_2026_08_16`. 500 feature columns (up from 486), 45s
train time, 38,490 rows, OOF 31,256 rows spanning validation seasons
2018-2025 — same population shape as the prior refit.

**Pooled 8-season conformal width factors/coverage** — nearly identical to
the currently-shipped model, no material change:

| Position | Width factor | Pooled OOF coverage (before → after) |
|---|---:|---|
| QB | 1.25 | 81.3% → 80.9% |
| RB | 1.15 | 81.4% → 81.9% |
| WR | 1.10 | 82.3% → 81.4% |
| TE | 1.10 | 80.8% → 81.8% |

**Sealed-2025 walk-forward OOF (trained 2016-2024 only) — the gate slice**:

| Position | n | Conformal coverage before → after | Pinball (conformal) before → after | Q50 MAE before → after |
|---|---:|---|---|---|
| QB | 517 | 82.4% → **80.5%** (in-band) | 1.863 → 1.821 (better) | 5.89 → 5.75 |
| RB | 891 | 79.5% → **79.1%** (in-band) | 1.520 → 1.490 (better) | 4.76 → 4.69 |
| WR | 1,673 | 87.5% → **87.5%** (unchanged, still over ceiling) | 1.135 → 1.099 (better) | 3.56 → 3.44 |
| TE | 1,004 | 82.6% → **86.0%** (**newly over ceiling**) | 0.939 → 0.855 (better) | 2.82 → 2.69 |

**Pre-registered gate**: pinball/interval quality not worse than just-promoted
**AND** conformal coverage stays in [75,85] per position. Pinball loss and
Q50 MAE improved at every single position — a clean, consistent win on point
accuracy and interval sharpness. But the coverage half of the gate is
conjunctive, and it breaks: WR was already 2.5pp over the 85% ceiling before
(unchanged, a pre-existing soft miss) and **TE is now newly over the
ceiling** (82.6% → 86.0%, +3.4pp — it was cleanly in-band before this
retrain and is not anymore). Both misses are in the safe direction
(over-coverage, not under), and both plausibly trace to the same
single-season-sampling-noise mechanism the prior report used to wave off
WR's miss — but the instruction is explicit: "only recommend promotion if
clearly better," and 2 of 4 positions failing the stated coverage band on
the gate's own designated slice is not "clearly better."

**Verdict: HOLD — do not promote.** `models/quantile/` (the 2026-08-15
promoted artifact) stays shipped. `models/quantile_graph_2026_08_16/` is
preserved as a researched artifact with a genuinely better pinball/MAE
profile — worth revisiting with a finer conformal factor grid or
season-weighted OOF (the same follow-up `QUANTILE_REFIT_2026_08_15.md`
already flagged for WR) rather than a blanket re-promote.

## 6. Reproduce

```bash
# 1. PBP bronze ingest (one season per command)
for s in 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025; do
  python scripts/bronze_ingestion_simple.py --season $s --data-type pbp --include-participation
done

# 2. Silver graph features (one season per command)
for s in 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025; do
  python scripts/compute_graph_features.py --seasons $s
done

# 3. TE-only retrain (standalone output dir, does NOT touch models/residual/)
python -c "
import sys; sys.path.insert(0, 'src')
from hybrid_projection import train_and_save_residual_models
train_and_save_residual_models(
    positions=['TE'], scoring_format='half_ppr',
    output_dir='models/te_graph_2026_08_16',
    use_graph_features=False, model_type='ridge',
    shap_feature_count=60,
    training_seasons=[2016,2017,2018,2019,2020,2021,2022,2023,2024],
)
"

# 4. Quantile retrain
python scripts/train_quantile_models.py --positions QB RB WR TE \
    --output-dir models/quantile_graph_2026_08_16
```

Gate eval scripts (TE matched-MAE comparison, quantile sealed-2025 OOF slice
comparison) followed the exact recipe in `RETRAIN_ON_REPAIRED_FEATURES.md` §7
/ `QUANTILE_REFIT_2026_08_15.md` §5 — not committed under `scripts/` for the
same concurrent-agent-safety reason noted there.

## Files touched

- `data/bronze/pbp/season={2016..2025}/`, `data/bronze/pbp_participation/season={2016..2025}/`
  — new, local-only (not gitignore-allowlisted, per instructions).
- `data/silver/graph_features/season={2016..2025}/` — new, 16 MB total.
  **Recommend allowlisting + committing** (not done here).
- `models/te_graph_2026_08_16/te_residual{.joblib,_meta.json}` — new,
  researched artifact, NOT promoted. `models/residual/te_residual*`
  untouched (verified via mtime).
- `models/quantile_graph_2026_08_16/*.pkl`, `metadata.json` — new, researched
  artifact, NOT promoted. `models/quantile/` untouched.
- `.planning/holdout_ledger.json` — appended sealed-2025 usage entry.
- Not touched: `src/feature_engineering.py`, game ensemble, `models/residual/`
  shipped artifacts, WR/QB/RB training or artifacts, `scripts/train_residual_models.py`
  (called the underlying function directly instead, to control `output_dir`).
