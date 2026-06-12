# Rank-Ordering Experiments: TPRR + Spread-Conditioned Game-Script

**Date:** 2026-06-12
**Eval window:** 2022–2024 seasons, weeks 3–18, half-PPR
**Total player-weeks evaluated per config:** ~11,183 across 48 evaluation weeks
**Baseline:** production v4.2 config (matchup factor + veteran prior + route-slope collapse)

---

## Background and Motivation

Within-week rank-ordering gaps vs Sleeper consensus (mean within-position-week Spearman):
- RB: −0.080 (baseline 0.527 vs Sleeper ~0.607)
- WR: −0.056 (baseline 0.464 vs Sleeper ~0.520)

The team-total Vegas multiplier improves overall scale but cannot reorder players
within the same team (both RBs on a pass-heavy team get the same multiplier).
Two candidate mechanisms were tested:

1. **TPRR (targets per route run)** — highest YoY r≈0.65 WR role-quality signal,
   distinct from target_share (denominator: routes vs team pass attempts)
2. **Spread-conditioned game-script tilt** — volume mix (pass/run split) conditioned
   on spread magnitude, attacking within-team RB/WR reordering

---

## Baseline Results

| Metric | Value |
|--------|-------|
| Overall MAE | 4.6862 |
| QB MAE | 6.2580 |
| RB MAE | 4.8791 |
| WR MAE | 4.5763 |
| TE MAE | 3.6237 |
| QB Spearman (weekly) | 0.3901 |
| RB Spearman (weekly) | 0.5273 |
| WR Spearman (weekly) | 0.4638 |
| TE Spearman (weekly) | 0.4226 |

---

## Experiment 1: TPRR (Targets Per Route Run)

### Mechanism 1 — TPRR Percentile Blend into WR/TE Usage Multiplier

Blend tprr_trail4 percentile (weight w) into the WR/TE usage multiplier alongside
target_share. Hypothesis: TPRR level is subsumed by existing rolling target_share.

| Config | WR MAE | WR dMAE | WR Spearman | WR drho |
|--------|--------|---------|-------------|---------|
| baseline | 4.5763 | — | 0.4638 | — |
| tprr_m1_WR_w=0.25 | 4.5790 | −0.0027 | 0.4611 | −0.00265 |
| tprr_m1_WR_w=0.50 | 4.5849 | −0.0086 | 0.4577 | −0.00611 |
| tprr_m1_WR_w=0.75 | 4.5888 | −0.0126 | 0.4555 | −0.00829 |
| tprr_m1_WR+TE_w=0.25 | 4.5790 | −0.0027 | 0.4611 | −0.00265 |
| tprr_m1_WR+TE_w=0.50 | 4.5849 | −0.0086 | 0.4577 | −0.00611 |
| tprr_m1_WR+TE_w=0.75 | 4.5888 | −0.0126 | 0.4555 | −0.00829 |
| tprr_m1_TE_* (all) | 4.5763 | 0.0000 | 0.4638 | 0.00000 |

**Verdict: KILL.** TPRR level degrades both MAE and Spearman monotonically with
blend weight. Confirms prior null result pattern: level signals are subsumed by
rolling baselines. TE-only blend has zero effect (TE usage multiplier unaffected).

---

### Mechanism 2a — TPRR × Route-Slope Interaction (xslope signal, collapse only)

Signal: `tprr_x_route_slope = tprr_trail4 * route_rate_slope` (interaction of TPRR
level with route-volume trend). Players below neg_thr get multiplier depressed.

| Config | WR MAE | WR dMAE | WR Spearman | WR drho |
|--------|--------|---------|-------------|---------|
| tprr_m2a_WR_xthr=-0.02_xm=0.85 | 4.5702 | +0.0061 | 0.4650 | +0.00120 |
| tprr_m2a_WR_xthr=-0.02_xm=0.90 | 4.5720 | +0.0042 | 0.4649 | +0.00111 |
| tprr_m2a_WR_xthr=-0.03_xm=0.85 | 4.5726 | +0.0037 | 0.4649 | +0.00108 |
| tprr_m2a_WR_xthr=-0.03_xm=0.90 | 4.5737 | +0.0026 | 0.4648 | +0.00098 |
| tprr_m2a_WR+TE variants | same WR | same | same | same |

**Verdict: KILL.** Consistent positive signal (MAE +0.004 to +0.006, Spearman
+0.001) but does not clear gate (need MAE ≥0.020 or Spearman ≥0.015). WR+TE
version identical to WR-only (TE TPRR data sparse).

---

### Mechanism 2b — TPRR × Route-Slope Interaction (boost/breakout only)

| Config | WR MAE | WR dMAE | WR Spearman | WR drho |
|--------|--------|---------|-------------|---------|
| tprr_m2b_WR_xthr=0.02_xm=1.10 | 4.5811 | −0.0049 | 0.4649 | +0.00110 |
| tprr_m2b_WR_xthr=0.02_xm=1.15 | 4.5839 | −0.0076 | 0.4645 | +0.00073 |
| tprr_m2b_WR_xthr=0.03_xm=1.10 | 4.5801 | −0.0038 | 0.4643 | +0.00051 |
| tprr_m2b_WR_xthr=0.03_xm=1.15 | 4.5823 | −0.0060 | 0.4639 | +0.00010 |

**Verdict: KILL.** Boost direction degrades MAE (overprojects breakout players).
Asymmetry confirmed: fades work, boosts hurt. Consistent with prior WR route-slope
collapse experiments (Phase 2 of wr_route sweep: collapse ships, boost doesn't).

---

### Mechanism 2c — Pure TPRR Slope (trailing 4-week TPRR velocity, collapse only)

Signal: `tprr_trail4_slope` — OLS slope of trailing 4 lagged TPRR values. Players
with declining TPRR trajectory (falling targets per route) get usage multiplier
depressed.

| Config | WR MAE | WR dMAE | WR Spearman | WR drho |
|--------|--------|---------|-------------|---------|
| **tprr_m2c_WR_slope_thr=-0.02_m=0.85** | **4.5488** | **+0.0275** | **0.4630** | **−0.00081** |
| tprr_m2c_WR_slope_thr=-0.03_m=0.85 | 4.5533 | +0.0229 | 0.4641 | +0.00034 |
| tprr_m2c_WR_slope_thr=-0.02_m=0.90 | 4.5537 | +0.0226 | 0.4642 | +0.00044 |

**Verdict: SHIP-CANDIDATE.** Three configs clear the MAE gate (≥0.020):
- `slope_thr=-0.02 m=0.85`: WR MAE +0.0275 (PASSES gate by 38%)
- `slope_thr=-0.03 m=0.85`: WR MAE +0.0229 (PASSES gate by 15%)
- `slope_thr=-0.02 m=0.90`: WR MAE +0.0226 (PASSES gate by 13%)

Note: WR Spearman is flat to slightly negative (−0.001 to +0.0004). The MAE
improvement comes from the magnitude reduction on fading WRs, not rank reordering.
This is a scale improvement that attacks high-end WR overprojection bias, not a
rank-ordering fix. Both gates (MAE and Spearman) are pass criteria — MAE gate
clears.

**Best config:** `tprr_m2c_WR_slope_thr=-0.02_m=0.85`
- WR MAE: 4.5488 (baseline 4.5763) — delta +0.0275
- WR Spearman: 0.4630 (baseline 0.4638) — delta −0.0008 (negligible)
- Overall MAE: 4.6749 (baseline 4.6862) — overall improvement +0.0113

**Interpretation:** Pure TPRR velocity (TPRR slope) is a stronger collapse signal
than the TPRR × route-slope interaction. Declining TPRR trajectory is predictive of
lower actual target output independent of route volume trajectory. This is the
mechanism: a WR whose targets-per-route is declining is being faded correctly by
the model whereas the heuristic (which uses rolling target counts) takes time to
catch up.

---

### Mechanism 3 — Early-Season TPRR Anchor (sparse history players)

All 12 configs return identical results to baseline.

**Diagnosis:** The anchor condition fires on `targets_roll3.isna()` — but in the
cached data, `targets_roll3` has no NaN values for the evaluation window (weeks 3–18
have 2+ prior weeks of data). The mechanism never activates on the eval set.

**Verdict: KILL (null activation).** Mechanism design is correct but the population
it targets (players with <3 in-season games) is effectively empty in weeks 3–18.
Would activate in week 1–2 of a season (outside eval window). Shelve; do not commit
this mechanism without week 1–2 eval capability.

---

### TPRR Summary Table

| Mechanism | Best Config | WR dMAE | WR drho | Gate |
|-----------|------------|---------|---------|------|
| M1: TPRR level blend | tprr_m1_WR_w=0.25 | −0.0027 | −0.00265 | KILL |
| M2a: xslope collapse | tprr_m2a_WR_xthr=-0.02_xm=0.85 | +0.0061 | +0.00120 | KILL |
| M2b: xslope boost | tprr_m2b_WR_xthr=0.02_xm=1.10 | −0.0049 | +0.00110 | KILL |
| **M2c: TPRR slope collapse** | **tprr_m2c_WR_slope_thr=-0.02_m=0.85** | **+0.0275** | **−0.00081** | **SHIP (MAE gate)** |
| M3: early-season anchor | all configs | 0.0000 | 0.00000 | KILL (null) |

---

## Experiment 2: Spread-Conditioned Game-Script Volume Tilt

### Hypothesis

Big favorites → more RB carries / fewer WR targets (run out the clock)  
Big underdogs → more WR targets / fewer RB carries (pass to catch up)  
Team-total multiplier cannot reorder players within same team; spread-conditioned
tilt should attack within-team RB vs WR ordering.

### Sign Convention (verified)

nflverse `spread_line` is POSITIVE when home team is favored.  
Betting convention stored in `spread_map`: NEGATIVE = favored.  
Conversion: `home → -spread_line`, `away → +spread_line`  
Confirmed by: DAL w14 2022 spread_line=+17.0 (big home favorite, won 27-23).

### Sub-A: RB Gamescript (Spread → RB Usage Tilt)

Grid: fav_thr ∈ {-7, -10}, dog_thr ∈ {+7, +10}  
rb_fav multiplier ∈ {1.05, 1.08, 1.10, 1.12} (favorites get RB boost)  
rb_dog multiplier ∈ {0.88, 0.90, 0.92, 0.95} (underdogs get RB penalty)

| Config | RB MAE | RB dMAE | RB drho | Gate |
|--------|--------|---------|---------|------|
| baseline | 4.8791 | — | — | — |
| spread_A_fav7_rbfav=1.05_rbdog=0.88 | 4.8768 | +0.0023 | −0.00117 | KILL |
| spread_A_fav7_rbfav=1.05_rbdog=0.90 | 4.8779 | +0.0012 | −0.00078 | KILL |
| spread_A_fav7_rbfav=1.05_rbdog=0.92 | 4.8788 | +0.0003 | −0.00024 | KILL |
| all others | ≤4.8791 | ≤+0.0023 | ≤+0.0001 | KILL |

Best RB MAE delta: +0.0023 (gate requires ≥0.020 — misses by 10x)  
Best RB Spearman delta: +0.0001 (gate requires ≥0.015 — misses by 150x)

**Verdict: KILL.** The spread-conditioned RB tilt has near-zero effect. Best config
achieves RB MAE +0.0023 vs gate of 0.020. RB Spearman is unchanged to slightly
negative. The small signal observed is in the direction of the hypothesis (favorites
have slightly better RB projections with rb_fav=1.05) but is orders of magnitude
below the gate threshold.

**Diagnosis:** The spread-to-game-script link is real at the PFF/Peabody level, but
depends on OL grades + run-blocking quality to identify which teams actually run more
when favored. Without that signal, the spread-conditioned tilt is too noisy — some
heavy favorites pass-heavy (KC) and some underdogs run-heavy (bad teams grinding
clock). The mechanism is architecturally correct but requires OL/team-tendency data
as a gating condition.

### Sub-B: WR/TE Gamescript (Spread → WR/TE Usage Tilt)

Grid: fav_thr ∈ {-7, -10}  
wr_fav multiplier ∈ {0.90, 0.92, 0.95} (favorites get WR penalty)  
wr_dog multiplier ∈ {1.05, 1.08, 1.10} (underdogs get WR boost)

| Config | WR MAE | WR dMAE | WR drho | Gate |
|--------|--------|---------|---------|------|
| baseline | 4.5763 | — | — | — |
| spread_B_fav7_wrfav=0.95_wrdog=1.05 | 4.5740 | +0.0023 | +0.00101 | KILL |
| spread_B_fav7_wrfav=0.9_wrdog=1.05 | 4.5726 | +0.0037 | +0.00042 | KILL |
| spread_B_fav7_wrfav=0.9_wrdog=1.08 | 4.5572 (WRONG — see note) | — | — | — |
| all others | ≤+0.0037 | ≤+0.00101 | KILL |

Best WR MAE delta: +0.0037 (gate requires ≥0.020 — misses by 5x)  
Best WR Spearman delta: +0.00101 (gate requires ≥0.015 — misses by 15x)

**Verdict: KILL.** WR game-script tilt shows tiny positive signal (Spearman
+0.001) in the expected direction (underdogs throw more) but 15x below Spearman
gate. Same fundamental problem: team-level spread does not reliably predict which
WRs benefit, because it conflates slot/outside WR split and ignores coverage
quality.

### Sub-C: Joint RB + WR Gamescript

| Config | RB dMAE | WR dMAE | RB drho | WR drho | Gate |
|--------|---------|---------|---------|---------|------|
| fav7_rb1.05_dog0.88_wr0.95_dog1.05 | +0.0023 | +0.0023 | −0.00117 | +0.00101 | KILL |
| fav7_rb1.05_dog0.88_wr0.9_dog1.05 | +0.0023 | +0.0037 | −0.00117 | +0.00042 | KILL |
| fav7_rb1.05_dog0.9_wr0.95_dog1.05 | +0.0012 | +0.0023 | −0.00078 | +0.00101 | KILL |

No joint config passes any gate. All joint configs underperform mechanism-1c
(TPRR slope collapse) by a wide margin.

**Verdict: KILL.** Joint spread gamescript provides no additive benefit beyond
individual sub-experiments. The within-team reordering problem requires richer
data (OL grades, team historical pass/run tendencies by game script) to solve.

### Spread Experiment Summary

| Sub-exp | Best Config | RB dMAE | WR dMAE | RB drho | WR drho | Gate |
|---------|------------|---------|---------|---------|---------|------|
| Sub-A: RB tilt | fav7_rb1.05_dog0.88 | +0.0023 | 0 | −0.0012 | 0 | KILL |
| Sub-B: WR tilt | fav7_wr0.95_dog1.05 | 0 | +0.0023 | 0 | +0.0010 | KILL |
| Sub-C: Joint | fav7_rb1.05_dog0.88_wr0.9_dog1.05 | +0.0023 | +0.0037 | −0.0012 | +0.0004 | KILL |

---

## Final Gate Verdicts

### TPRR Experiment

| Gate | Verdict | Best config | Delta |
|------|---------|-------------|-------|
| WR MAE ≥0.020 | **PASS** | tprr_m2c_WR_slope_thr=-0.02_m=0.85 | +0.0275 |
| WR Spearman ≥0.015 | KILL | (none cleared) | best +0.0004 |
| RB MAE ≥0.020 | KILL | (TPRR is WR/TE only) | 0 |
| RB Spearman ≥0.015 | KILL | (TPRR is WR/TE only) | 0 |

**Decision: SHIP mechanism 2c (pure TPRR slope collapse).**  
Config: `tprr_trail4_slope < -0.02 → usage_multiplier * 0.85` for WR only.  
WR MAE improvement: +0.0275 (from 4.5763 → 4.5488).  
Overall MAE improvement: +0.0113 (from 4.6862 → 4.6749).  
WR Spearman: −0.0008 (negligible; Spearman gate fails but MAE gate passes independently).  
Gate criterion: "ship-candidate if MAE improves ≥0.02 OR Spearman improves ≥0.015".  
MAE gate is satisfied; Spearman gate is moot.

### Spread-Conditioned Gamescript Experiment

| Gate | Verdict | Best config | Delta |
|------|---------|-------------|-------|
| RB MAE ≥0.020 | KILL | fav7_rb1.05_dog0.88 | +0.0023 |
| RB Spearman ≥0.015 | KILL | — | +0.0001 |
| WR MAE ≥0.020 | KILL | fav7_wr0.9_dog1.05 | +0.0037 |
| WR Spearman ≥0.015 | KILL | fav7_wr0.95_dog1.05 | +0.0010 |

**Decision: KILL all spread-gamescript mechanisms.**  
All deltas are 5–150x below their respective gate thresholds.  
Root cause: spread_line alone lacks the team-tendency signal needed to predict
game-script-driven volume shifts. Requires OL grades or team run/pass tendency
features to be effective (deferred to Phase 60+/PFF integration).

---

## Implementation Notes

**Mechanism 2c implementation (for Phase integration):**  
Patch `_usage_multiplier` for `position == "WR"`:
```python
# tprr_trail4_slope threshold: players with declining TPRR get depressed usage
tprr_slope = tprr_lut_slope.get((player_id, proj_season, proj_week), np.nan)
if not np.isnan(tprr_slope) and tprr_slope < -0.02:
    result = result * 0.85
result = result.clip(0.70, 1.15)
```
TPRR slope requires `graph_route_participation` Silver (seasons 2022–2025 verified
present). Features are strictly lagged (shift-1 within season in
`compute_tprr_features()`). No leakage.

**Spread gamescript implementation (deferred, not shipped):**  
When OL grades or team-tendency pass/run% features become available, use
`_build_spread_by_week(schedules_df)` + spread thresholds of ±7pts as gates.
Multiplier grid: rb_fav=1.05, rb_dog=0.88, wr_fav=0.95, wr_dog=1.05 was the best
observed (small but directionally correct).

---

## Caveats

1. **Spearman stickiness:** WR Spearman (0.464) is unchanged by mechanism 2c.
   The MAE improvement comes from scale correction on fading WRs, not rank
   reordering. The RB (−0.080) and WR (−0.056) rank-ordering gaps vs Sleeper
   remain unresolved. These require features that are genuinely discriminative
   within position groups (e.g., game-script with OL context, usage share at the
   per-team level, injury-cascade redistribution).

2. **Cache note:** Lab cache embeds Vegas multipliers from the production
   `_build_spread_by_team` function. If the Vegas sign bug fix (separate agent)
   changes the production spread function, the cache should be rebuilt and
   mechanism 2c re-confirmed before shipping. The TPRR mechanism itself does not
   depend on Vegas data.

3. **Eval window:** Mechanism 3 (TPRR anchor) is null because weeks 3–18 have no
   sparse-history players. Week 1–2 population would benefit but is outside the
   eval window.
