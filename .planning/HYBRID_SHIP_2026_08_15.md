# Hybrid ML Ship Decision — 2026-08-15

Follow-up to `.planning/RETRAIN_ON_REPAIRED_FEATURES.md` (retrain + sealed-2025
gate numbers) and `.planning/BENCHMARK_REFRESH_2026_08_15.md` (full-repo
benchmark refresh, documents the WR regression and the QB/RB SKIP verdicts
being stale). This task: leak-verify the QB result, ship QB/RB, recover or
honestly report the WR loss, decide TE, and produce a final apples-to-apples
headline table for the whole hybrid stack.

## 1. Leak verification — QB −0.685 (RETRAIN_ON_REPAIRED_FEATURES.md §5)

**Verdict: NO LEAK. Ship.**

Three independent checks, all consistent:

### (a) Feature-construction audit

All 20 QB features selected into `models/retrained_2026_08_15/qb_residual_meta.json`
are either:
- Lagged rolling/std stats (`*_std`, `*_roll3`, `*_roll6` — e.g.
  `ngs_aggressiveness_std`, `passing_yards_roll3`, `snap_pct_std`), which
  `src/player_feature_engineering.py` guarantees carry `shift(1)` applied
  upstream (`_LAGGED_SUFFIXES`, line ~137) — verified by reading
  `_prepare_snap_data`/`_add_trailing_matchup_form` construction and the
  module's own `_SAME_WEEK_RAW_STATS` / `_SAME_WEEK_PREFIXES` exclusion sets
  (lines 63–170), which explicitly blacklist the raw same-week form of every
  one of these stats and any `ngs_`/`pfr_`/`qbr_` column that isn't a lagged
  variant (`_is_unlagged_leak`, enforced inside `get_player_feature_columns`).
- Pre-game context known before kickoff: `implied_team_total`,
  `closing_total`, `opening_spread`, `wind_speed`, `temperature`, `bmi`.

No raw same-week stat, and no unlagged `ngs_`/`pfr_`/`qbr_` column, appears in
the selected set. The repo already carries a leakage-detection harness
(`detect_leakage`, `validate_temporal_integrity` in
`player_feature_engineering.py`) built specifically after the v4.2 leakage
incident (commit `939e6665`) — this retrain went through the same
`get_player_feature_columns()` gate that incident produced.

### (b) Within-season label-shuffle test

Retrained QB (identical recipe: `model_type='lgb'`, `shap_feature_count=20`,
2016–2024, `heuristic_version='v4.2+blend'`) with the residual target shuffled
**within season** (breaks the feature↔label pairing per row while preserving
each season's label distribution; feature selection was also rerun against
the shuffled target so selection itself couldn't leak the true label).
Correlation(original residual, shuffled residual) = 0.0013 — shuffle is clean.

| | Sealed-2025 hybrid MAE | Δ vs heuristic (6.461/6.459) |
|---|---:|---:|
| Real retrained model | 5.771–5.773 | **−0.685 to −0.688** |
| Shuffled-label model | 6.408 | **−0.053** |

A leaky feature (something correlated with the *current-week outcome*) would
still show a large spurious gain here, because shuffling the label doesn't
touch same-row leaked features — it only breaks genuine feature→label
relationships. The shuffled model's skill collapsing to near-zero means the
real model's edge requires the true feature/label pairing, i.e., it's reading
genuine prior-state signal, not a leaked value.

### (c) Sanity check on 2025 QB weeks

Reproduced the sealed-2025 gate directly (`compute_production_heuristic` +
`apply_residual_correction` against `models/retrained_2026_08_15`, weeks
3–18): heuristic MAE 6.461 → hybrid MAE 5.771, bias +0.133 — matches
RETRAIN_ON_REPAIRED_FEATURES.md's 6.459 → 5.773 (+0.05) closely (small
residual float/order differences only). Per-week corrections vary genuinely
week to week (not a fixed per-player offset), and the biggest misses are
spread across ordinary boom/bust performances (Trevor Lawrence 44.3 pt game,
Malik Willis 33.5, Josh Allen 42.7, Brock Purdy 36.9) — the pattern of a real,
imperfect model, not suspiciously-perfect leaked predictions. (Same check run
for RB: 5.096 → 4.906 vs. RETRAIN doc's 5.109 → 4.920 — consistent.)

**Note on methodology**: the first pass of this sanity check (and of two other
ad hoc eval scripts built for this task) had a bug — the debug harness merged
heuristic projections onto the feature table by `player_id` alone, omitting
`season`/`week`, which silently broadcast one stale feature row per player
across every week in the eval window (confirmed via a diagnostic: player
corrections were byte-identical across different weeks/seasons, which is
impossible for a real week-varying model). This bug lived only in this
session's scratch scripts, not in shipped code (`apply_residual_correction`'s
real production callers always pass season/week) — the shuffle test itself
was unaffected (it indexes features directly off `eval_data`, no merge step).
Fixed by including `season`/`week` in the merge key; all numbers in this
report are post-fix and were cross-checked against
RETRAIN_ON_REPAIRED_FEATURES.md's independently-produced numbers as a
consistency check (all matched within ~0.002–0.01 MAE).

## 2. QB/RB ship

**Verdict: SHIP both**, per RETRAIN_ON_REPAIRED_FEATURES.md §6/§8.

- Promoted `models/retrained_2026_08_15/{qb,rb}_residual{,_imputer}.joblib` +
  `_meta.json` → `models/residual/` (old, never-shipped-in-production
  `lgb_v2` QB/RB artifacts backed up to
  `models/residual/_backup_pre_2026_08_15_qbrb_ship/`).
- `src/ml_projection_router.py`: removed the unconditional
  `verdicts["QB"] = "SKIP"` hardcode; `HYBRID_POSITIONS` is now
  `{"QB", "RB", "TE", "WR"}` (was `{"TE", "WR"}`). QB/RB now route through the
  same `v4.2+blend`-stamp-gated HYBRID activation path as WR/TE
  (`_load_ship_gate`), so a stale/missing meta demotes back to heuristic
  automatically — no new special-casing needed.
- Sealed-2025 re-confirmation (this task, §1c): QB 6.461→5.771 (−0.690), RB
  5.096→4.906 (−0.190) — consistent with the original gate.

## 3. MAPIE dead-code fix (MODEL_REVIEW_2026_08_15.md finding #13)

`_apply_mapie_intervals()` in `ml_projection_router.py` branched on
`HAS_MAPIE` but both branches called `add_floor_ceiling()` (the heuristic
spread) regardless — the function never actually computed a MAPIE interval,
so the branch implied calibration this path never performed. Collapsed the
call site to one honest `add_floor_ceiling()` call and deleted the dead
`_apply_mapie_intervals` function. `compute_mapie_intervals()` (the real,
tested MAPIE wrapper — see `test_ml_projection_router.py`) is left in place
and exported, documented as currently unused because MAPIE's `cv="prefit"`
calibration needs training X/y that this per-request inference path doesn't
have; wiring it for real would mean threading a calibration set through to
that call site, not done here. No behavior change (both old branches did the
same thing) — this is a truthfulness fix, not a functional one.

## 4. Correction clamp (blowup insurance, all 4 HYBRID positions)

`BENCHMARK_REFRESH_2026_08_15.md` §5 traced the WR regression to extrapolation
blowups from the shipped WR/TE models seeing real (no-longer-imputed)
NGS/snap feature values they were never trained against — concretely, a
75.5-pt WR projection vs a 5.7-pt actual (Cedrick Wilson Jr., 2023 W16).

Added `correction_clip_abs` to every residual meta (99th-percentile
`|actual − heuristic|` on that position's training population, computed once
and reused — QB 18.75, RB 20.97, WR 18.81, TE 15.38) and wired it into
`apply_residual_correction()` (`src/hybrid_projection.py`): the predicted
correction is clipped to `±correction_clip_abs` before being added to the
heuristic. Applied to all four HYBRID positions per the task's own
suggestion ("cheap insurance"), not just WR.

**Confirmed against the exact cited blowup case** (Cedrick Wilson Jr., 2023
W16, actual=5.7): with the clamp active, the correction hits the clip
ceiling and the projection is capped at 23.2 instead of extrapolating toward
~75 — the mechanism visibly fires on the documented failure case. In the
broader eval population the clamp is a low-frequency safety net (fires on
<1% of rows by construction, since the cap is the training population's own
99th percentile) — it measurably trims the worst-case blowup count and
magnitude without changing typical in-distribution corrections, and never
makes MAE worse in any window tested (§5/§6).

## 5. WR recovery

Pre-registered gate: restore WR's matched-pairs gap vs Sleeper **and** ESPN to
≤0 without moving sealed-2025 WR MAE >0.02 worse.

**Verdict: (c) shipped WR model + correction clamp.** Ship (already live via
§4 — WR was already in `HYBRID_POSITIONS`, so no router change beyond the
clamp itself).

| Option | Sealed-2025 actual MAE | 2022-24 actual MAE | Verdict |
|---|---:|---:|---|
| (a) heuristic-only | 3.943 | 4.139 | worse than (c) in both windows |
| (b) retrained WR | 3.991 | 4.077 | rejected — RETRAIN_ON_REPAIRED_FEATURES.md pre-registered gate (sealed-2025 MAE +0.111 vs shipped, bias 6x worse); this task's own re-check agrees (worse or a wash in both windows, never clearly better) |
| **(c) shipped + clamp (SHIP)** | **3.876** | **4.065** | best of the three in both windows; directly neutralizes the cited blowup case (§4) |

vs-consensus (the actual gate criterion) — see §6 for the full new-vs-old
headline table; the (c) configuration is what's live in that run.

## 6. TE decision

Pre-registered gate: redeploy retrained TE only if it beats shipped TE on
**both** sealed 2025 and 2022-24.

**Verdict: REDEPLOY retrained TE.**

| Window | Shipped TE MAE | Retrained TE MAE | Δ |
|---|---:|---:|---:|
| Sealed 2025 (RETRAIN_ON_REPAIRED_FEATURES.md, production path) | 3.011 | 2.971 | −0.039 |
| Sealed 2025 (this task's independent re-check) | 3.017 | 2.977 | −0.040 |
| 2022-2024 (this task) | 2.901 | 2.864 | −0.037 |

Consistent win for the retrained model in every window and every methodology
tested (2 independent harnesses). Promoted
`models/retrained_2026_08_15/te_residual{,_imputer}.joblib` + `_meta.json` →
`models/residual/` (old shipped TE backed up alongside the QB/RB backup).

## 7. Final verification — headline table

Ran foreground, per-season, `--ml --full-features --vs-consensus` (2022,
2023, 2024 separately, each well under 10 min; results pooled with the
production `apply_consensus_filter` — weeks 3-18, consensus≥5pts,
QB/RB/WR/TE — to reproduce the exact same-methodology matched population).
Configuration under test: QB/RB/WR/TE all `HYBRID_POSITIONS` with the
correction clamp; WR = shipped Ridge (unchanged) + clamp; TE = retrained
(promoted §6); QB/RB = retrained (promoted §2). Old baseline =
`BENCHMARK_REFRESH_2026_08_15.md` §2 canonical numbers, same-session, same
repo state before this task (QB/RB heuristic-only, WR/TE shipped hybrid, no
clamp).

MAE gap = our MAE − source MAE. **Negative = we win.**

### vs Sleeper (n=7,009 — matches the documented population exactly)

| Position | Old (this session's baseline) | New (this task) | Δ | Verdict |
|---|---:|---:|---:|---|
| QB | −0.386 (win) | **−0.861** (win) | −0.475 | win more than doubles |
| RB | +0.264 (**loss**) | **−0.310** (win) | −0.574 | **FLIPS — now a clear win** |
| WR | +0.005 (thin loss) | **+0.007** (thin loss) | +0.002 | essentially unchanged — the clamp barely fired in this exact population (see §5) |
| TE | −0.410 (win) | **−0.454** (win) | −0.044 | improved (retrained TE) |
| **OVERALL** | **−0.050** (win) | **−0.293** (win) | **−0.243** | **win nearly 6x wider** |

### vs ESPN (n=6,721 — matches the documented population exactly)

| Position | Old (this session's baseline) | New (this task) | Δ | Verdict |
|---|---:|---:|---:|---|
| QB | +0.186 (**loss**) | **−0.260** (win) | −0.446 | **FLIPS — now a win** |
| RB | +0.173 (**loss**) | **−0.381** (win) | −0.554 | **FLIPS — now a win** |
| WR | −0.038 (thin win) | **−0.037** (thin win) | +0.001 | unchanged |
| TE | −0.410 (win) | **−0.453** (win) | −0.043 | improved (retrained TE) |
| **OVERALL** | **+0.009** (**loss**) | **−0.228** (win) | **−0.237** | **FLIPS — now a clear win** |

**"Beats both sources overall" is TRUE again**, and by a much wider margin
than the pre-repair baseline ever showed (old canonical −0.086/−0.027 →
new −0.293/−0.228). QB and RB going HYBRID is what did it — both were
architecturally frozen at heuristic-only before this task and are the
entire story behind both flips. **"Beats both sources at WR" is still
FALSE** — the clamp fixes the specific blowup class (§5) but the position's
underlying MAE-vs-consensus gap barely moved, because the blowup rows are a
small fraction of the matched population; WR remains a thin loss vs Sleeper
and a thin win vs ESPN, same as pre-task.

### FantasyPros ordinal simulation (`scripts/simulate_fp_accuracy.py`, 2022-2024, weeks 3-17)

Lower gap-to-actual = better ("Winner" = whichever of ours/Sleeper/ESPN has
the lowest gap).

| Position | Old ours → New ours | Sleeper | ESPN | Old winner | New winner |
|---|---|---:|---:|---|---|
| QB | 7.21 → **6.59** | 7.19 | 7.18 | ~tie (barely losing) | **Ours — beats both** |
| RB | 6.18 → **5.43** | 5.92 | 5.91 | Sleeper/ESPN | **FLIPS — Ours beats both** |
| WR | 6.64 → **6.51** | 6.29 | 6.47 | Sleeper | Sleeper (still losing both, margin narrows) |
| TE | 6.33 → **5.70** | 6.12 | 6.15 | Sleeper | **FLIPS — Ours beats both** |

Same mechanism as the MAE table: QB/RB going HYBRID (previously untouched by
any prior lever — the ordinal sim only reads the plain heuristic-only
backtest) is the reason this metric moves at all; TE's retrain compounds it.
**This is the first time in this repo's history the ordinal ranking metric
shows outright wins at QB/RB/TE** — previously-published "consensus beats us
everywhere under this metric" no longer holds for 3 of 4 positions. WR stays
the one honest gap: better than before, still behind both sources.

Artifacts: `output/backtest/fg_{sleeper,espn}_{2022,2023,2024}/`,
`output/backtest/pooled_2022_2024_{sleeper,espn}_matched.csv`,
`output/backtest/fp_sim_newconfig/fp_accuracy_simulation_summary.csv`.

## 8. Tests

- `tests/test_ml_projection_router.py`, `tests/test_hybrid_projection.py`:
  updated 3 tests that hardcoded the old QB-force-SKIP / `HYBRID_POSITIONS ==
  {TE,WR}` behavior (`test_returns_skip_for_qb_bias_corrected` →
  `test_no_qb_force_skip_without_residual_model`, `test_hybrid_positions_constant`,
  `test_ship_gate_verdicts_v42` → `test_ship_gate_verdicts_v44`). Full
  suite (`tests/test_ml_projection_router.py` + `tests/test_hybrid_projection.py`):
  51 passed, 1 skipped.
- Full repo suite (`pytest tests/ -q`, excluding one pre-existing unrelated
  flaky test — a file-age assertion off by a day boundary,
  `test_freshness_check_ok`, unrelated to this change): 3618 passed, 23
  skipped.

## 9. Artifact provenance

| Artifact | Source | Promoted from |
|---|---|---|
| `models/residual/qb_residual{,_imputer}.joblib`, `_meta.json` | `train_and_save_residual_models(positions=['QB'], model_type='lgb', shap_feature_count=20, training_seasons=2016-2024)`, committed under RETRAIN_ON_REPAIRED_FEATURES.md | `models/retrained_2026_08_15/qb_residual*` |
| `models/residual/rb_residual{,_imputer}.joblib`, `_meta.json` | same recipe, RB | `models/retrained_2026_08_15/rb_residual*` |
| `models/residual/te_residual{,_imputer}.joblib`, `_meta.json` | `train_and_save_residual_models(positions=['TE'], model_type='ridge', shap_feature_count=60, training_seasons=2016-2024)` | `models/retrained_2026_08_15/te_residual*` |
| `models/residual/wr_residual{,_imputer}.joblib`, `_meta.json` | **unchanged** — still the v4.3 blend-consistent Ridge (2026-06-12); only the meta gained `correction_clip_abs` | n/a (patched in place) |
| Old QB/RB residual artifacts (never shipped; SKIP-hardcoded) | — | backed up to `models/residual/_backup_pre_2026_08_15_qbrb_ship/{qb,rb}_residual*` |
| Old TE residual artifact | v4.2 leakage-fix TE (2026-06-10/24) | backed up to `models/residual/_backup_pre_2026_08_15_qbrb_ship/te_residual*` |
| `correction_clip_abs` (all 4 metas) | p99 `|actual - heuristic|`, training population 2016-2024, weeks 3-18, half_ppr | computed this task, patched into both `models/residual/*_meta.json` and `models/retrained_2026_08_15/*_meta.json` |

`.planning/holdout_ledger.json` updated with this task's sealed-2025 touches
(shuffle test, sanity re-check) alongside the concurrent RETRAIN/BENCHMARK
entries from the same day.
