# Joint Lever Gate — `--early-season-prior` + `--rb-tail-calibration` (2026-08-09)

Combined gate for the two near-miss levers from the same day's individual
gates: `.planning/EARLY_SEASON_PRIOR_GATE.md` (deconfounded verdict: HOLD,
weeks 3-6 overall MAE gap vs Sleeper improves 0.053 of a required 0.10;
ordinal improves 0.037 of a required 0.05) and
`.planning/RB_TAIL_CALIBRATION_GATE.md` (HOLD, RB weeks 3-18 MAE gap vs
Sleeper improves 0.063 of a required 0.08). Question: run both flags
together — do they clear bars jointly (effects mostly orthogonal: early-prior
touches weeks 3-6 all positions, rb-tail touches RB all weeks) and is the
interaction sane (no double-boosting low-band early-season RBs into
overshoot)?

## Pre-registered gate (written before running the eval)

**SHIP-joint** if ALL of:
- (a) weeks 3-6 overall MAE gap vs Sleeper improves ≥0.10, **OR** RB weeks
  3-18 gap improves ≥0.08 — at least one component bar cleared.
- (b) ordinal FP Accuracy Gap overall vs Sleeper improves ≥0.05
  (`scripts/simulate_fp_accuracy.py`).
- (c) no position worsens >0.05 MAE weeks 3-18 or >0.03 ordinal.
- (d) overlap rows (both levers fired on the same row) show no overshoot —
  bias doesn't flip past zero by >1.0.

**Else HOLD**, report numbers.

## Method

Both flags passed together to `run_backtest()`:
`--early-season-prior --rb-tail-calibration`. Order of application inside
`scripts/backtest_projections.py` (confirmed in source, lines ~836-875):
injury adjustments → **early-season-prior blend (weeks 3-6)** → QB
starter-floor (not used here) → **RB tail calibration (low-band
boost / high-band shrink)**. This means RB-tail's band classification
(`<8` / `>=14`) for weeks 3-6 RB rows runs on **already-prior-blended**
`projected_points` — the interaction is real and directional, not just a
population overlap.

Per the mandatory process rule, baseline (no flags) and treated (both
flags) were generated back-to-back this session, `--ml --full-features`,
per-season foreground chunks (2022/2023/2024, ~2 min each):

```bash
# Baseline
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons {2022,2023,2024} \
    --scoring half_ppr --ml --full-features --output-dir output/backtest/joint_mae_baseline

# Treated
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons {2022,2023,2024} \
    --scoring half_ppr --ml --full-features --early-season-prior --rb-tail-calibration \
    --output-dir output/backtest/joint_mae_treated
```

Per-season CSVs concatenated (`pandas.concat`) into one combined
baseline/treated file each, then fed to `scripts/benchmark_consensus_sources.py`
(`--sources espn sleeper`) for the MAE gate, and to
`scripts/simulate_fp_accuracy.py` (heuristic `--vs-consensus` mode, isolated
`output/backtest/joint_ord_{baseline,treated}` dirs, same per-season
foreground pattern) for the ordinal gate.

### Data-confound found and fixed mid-run

The **first** baseline command run this session (season 2022, `--ml
--full-features`, ~19:31-19:33) completed with **zero** injury-report rows
for 2022 (`injury_status` entirely null) — `data/bronze/players/injuries/season=2022/`
had no file yet at that point. A concurrent process (unrelated to this task;
the coordinator flagged another agent working in this repo simultaneously)
ingested `injuries_20260809_193149.parquet` for season 2022 between that run
and the next one. Every subsequent run this session — the treated 2022 MAE
run, and both ordinal-gate 2022 runs (baseline and treated) — picked up the
injury data (3,490 / 3,748 non-null rows respectively, matching 2023/2024's
100% coverage). This was caught by the mandatory no-confound check (Section
0 below originally showed 79 non-zero deltas, up to −3.71 pts, in QB/WR/TE
weeks 7-18 — rows neither lever should touch) before it could bias the
verdict. **Fix**: the 2022 MAE-gate baseline was regenerated fresh
(`output/backtest/joint_mae_baseline_v2/`, immediately after, same session)
and spliced into the combined baseline in place of the stale run. All
numbers below are post-fix. The ordinal-gate baseline needed no fix (it ran
after the injuries file landed).

## Section 0 — No-confound proof (rows neither lever should touch)

Row-level merge of combined baseline vs treated on `(player_id, season,
week)`, post-fix:

| Slice | n | Non-zero `projected_points` deltas | Max abs delta |
|---|---|---|---|
| QB/WR/TE, weeks 7-18 (neither lever's scope) | 5,703 | **0** | **0.000000** |
| QB/WR/TE, weeks 3-6 (early-prior's scope) | 2,047 | 1,618 (79.0%) | — |
| RB, all weeks 3-18 (both levers' scope) | 2,841 | 1,054 (37.1%) | — |

Byte-identical outside the levers' documented scope, confirmed. `n` matches
exactly between baseline and treated for every downstream table below (no
row loss from either backtest run).

## Section 1 — Firing rates per lever per season (required before headline numbers)

**Early-season-prior** — `prior_season_ppg` notna, weeks 3-6, QB/RB/WR/TE:

| Season | Eligible | Fired | Rate |
|---|---|---|---|
| 2022 | 961 | 758 | 78.9% |
| 2023 | 941 | 730 | 77.6% |
| 2024 | 894 | 717 | 80.2% |
| **Total** | **2,796** | **2,205** | **78.9%** |

**RB-tail low-band boost** — `rb_tail_low_boost_flag`, RB rows, any week 3-18:

| Season | RB rows | Fired | Rate |
|---|---|---|---|
| 2022 | 954 | 62 | 6.5% |
| 2023 | 939 | 72 | 7.7% |
| 2024 | 948 | 69 | 7.3% |
| **Total** | **2,841** | **203** | **7.1%** |

**RB-tail high-band shrink** — `rb_tail_high_shrink_flag`, RB rows, any week 3-18:

| Season | RB rows | Fired | Rate |
|---|---|---|---|
| 2022 | 954 | 132 | 13.8% |
| 2023 | 939 | 104 | 11.1% |
| 2024 | 948 | 160 | 16.9% |
| **Total** | **2,841** | **396** | **13.9%** |

Any RB row touched by rb-tail (low or high): 599/2,841 = **21.1%** —
consistent with the solo rb-tail gate's 21.5% (the tiny drop is the fresh
snap-collapse/data-state draw, not a lever change).

## Section 2 — OVERLAP rows (both levers fired on the same row)

Overlap is only geometrically possible for **RB rows in weeks 3-6** (the
only window where early-season-prior is active) where **both**
`prior_season_ppg` is notna **and** an rb-tail flag (low or high) is set:

| Season | Overlap n |
|---|---|
| 2022 | 35 |
| 2023 | 37 |
| 2024 | 45 |
| **Total** | **117** |

Of RB weeks-3-6 rows (n=749): 575 (76.8%) get the early-prior blend, 147
(19.6%) get an rb-tail adjustment, 117 (15.6%) get **both** — split 21
low-boost-overlap / 96 high-shrink-overlap.

**Overlap bias before/after** (`bias = proj − actual`, matched to baseline
on `(player_id, season, week)`, n=117):

| | Baseline | Treated | Δ |
|---|---:|---:|---:|
| Mean bias | **+0.311** | **−0.748** | −1.059 |
| Median bias | +1.050 | +0.350 | −0.700 |
| Mean projection | 14.09 | 13.03 | −1.06 |
| Mean actual | 13.78 | 13.78 | 0.000 |
| MAE | 6.199 | 6.034 | −0.165 (improves) |

**Overshoot check**: bias crosses zero (over- → under-projecting), but the
new-side magnitude is 0.748, under the 1.0-pt overshoot threshold. **No
overshoot by the pre-registered rule** — though the sign flip is real and
worth flagging as a soft caution (75% of the way to the tolerance), not a
clean "moved toward zero and stopped" result like the solo rb-tail gate's
high-band bias.

Split by which rb-tail signal overlapped:

| Overlap subset | n | Base bias | Treated bias | Base MAE | Treated MAE |
|---|---|---:|---:|---:|---:|
| Low-boost overlap | 21 | −1.217 | +0.052 | 3.736 | 4.212 |
| High-shrink overlap | 96 | +0.645 | −0.923 | 6.738 | 6.432 |

**Interaction finding**: no double-boosting. The low-boost-overlap subset
(RBs the early-prior blend already nudged, that also cross the rb-tail
low-band+rising-snap-share flag) sees bias move from clearly negative
(−1.22, under-projected) to essentially zero (+0.05) — the *opposite* of
compounding under-correction; if anything the two boosts partially offset
because early-season-prior's shrink-toward-prior-season-PPG for a
committee-back candidate often already lifted the projection before
rb-tail's rising-snap-share boost evaluates band membership, so fewer of
these rows are still under 8 pts by the time rb-tail runs. The high-shrink
overlap (RBs whose already-prior-blended projection lands ≥14 pts) is where
the bias sign-flip lives — MAE still improves (6.74→6.43) even as the mean
bias crosses zero, and at n=96 (only 1.4% of the full RB population) this
is not a population-level overshoot risk.

## Section 3 — MAE gate, weeks 3-6 and weeks 3-18, both sources

`gap = our_mae − source_mae`; Δ = treated − baseline (negative = improves).

**Weeks 3-6:**

| Position | vs Sleeper base | vs Sleeper treated | Δ | vs ESPN base | vs ESPN treated | Δ |
|---|---:|---:|---:|---:|---:|---:|
| QB | −0.835 | −0.799 | +0.036 (worse) | +0.001 | +0.034 | +0.033 (worse) |
| RB | +0.313 | +0.268 | −0.045 | +0.228 | +0.199 | −0.030 |
| WR | +0.216 | +0.138 | −0.078 | +0.163 | +0.091 | −0.072 |
| TE | +0.309 | +0.232 | −0.077 | +0.225 | +0.130 | −0.096 |
| **OVERALL** | **+0.067** | **+0.018** | **−0.049** | **+0.160** | **+0.115** | **−0.045** |

**Weeks 3-18:**

| Position | vs Sleeper base | vs Sleeper treated | Δ | vs ESPN base | vs ESPN treated | Δ |
|---|---:|---:|---:|---:|---:|---:|
| QB | −0.385 | −0.375 | +0.010 (worse) | +0.187 | +0.196 | +0.009 (worse) |
| RB | +0.264 | +0.204 | **−0.060** | +0.173 | +0.123 | −0.050 |
| WR | +0.083 | +0.062 | −0.021 | +0.049 | +0.029 | −0.020 |
| TE | +0.180 | +0.159 | −0.021 | +0.190 | +0.164 | −0.026 |
| **OVERALL** | **+0.061** | **+0.035** | **−0.026** | **+0.127** | **+0.103** | **−0.024** |

`n` identical baseline vs treated at every row (1,936/1,850 weeks 3-6;
7,009/6,721 weeks 3-18, Sleeper/ESPN) — no population shift.

## Section 4 — Ordinal gate (FantasyPros-style Accuracy Gap, weeks 3-17)

`gap = ours − source` (2022-2024 pooled), from
`scripts/simulate_fp_accuracy.py` run on the isolated ordinal-gate dirs:

| Position | Base gap (Sleeper) | Treated gap (Sleeper) | Δ | Base gap (ESPN) | Treated gap (ESPN) | Δ |
|---|---:|---:|---:|---:|---:|---:|
| QB | +0.019 | −0.030 | −0.049 | +0.032 | −0.018 | −0.049 |
| RB | +0.251 | +0.221 | −0.030 | +0.259 | +0.229 | −0.030 |
| WR | +0.351 | +0.296 | −0.055 | +0.163 | +0.109 | −0.055 |
| TE | +0.218 | +0.193 | −0.025 | +0.187 | +0.162 | −0.025 |
| **OVERALL (mean)** | **+0.210** | **+0.170** | **−0.040** | **+0.160** | **+0.121** | **−0.040** |

## Gate check

| Criterion | Required | Measured | Result |
|---|---|---|---|
| (a1) weeks 3-6 overall Δ vs Sleeper | ≥0.10 improvement | 0.049 (49% of bar) | FAIL |
| (a2) RB weeks 3-18 Δ vs Sleeper | ≥0.08 improvement | 0.060 (75% of bar) | FAIL |
| **(a) at least one of a1/a2** | — | both fail | **FAIL** |
| (b) ordinal overall Δ vs Sleeper | ≥0.05 improvement | 0.040 (80% of bar) | **FAIL** |
| (c) no position worsens >0.05 MAE (w3-18) | — | max QB +0.010 | PASS |
| (c) no position worsens >0.03 ordinal | — | none worsen (all improve) | PASS |
| (d) overlap rows: no overshoot >1.0 past zero | — | flips to −0.748 (< 1.0) | PASS |

Per the pre-registered rule (ALL required), the composite is **HOLD** —
criteria (a) and (b) both fail; (c) and (d) pass.

## Verdict: **HOLD**

## Interaction finding (the core question this gate was run to answer)

**Effects are close to orthogonal, with a small negative interaction on the
MAE metrics.** Comparing the joint numbers to each lever's solo
deconfounded/gate numbers:

| Metric | Solo lever | Joint | Δ (joint − solo) |
|---|---:|---:|---:|
| Weeks 3-6 overall MAE Δ vs Sleeper | −0.053 (early-prior alone) | −0.049 | +0.004 (slightly worse) |
| RB weeks 3-18 MAE Δ vs Sleeper | −0.063 (rb-tail alone) | −0.060 | +0.003 (slightly worse) |
| Ordinal overall Δ vs Sleeper | −0.037 (early-prior alone) | −0.040 | −0.003 (slightly better) |

The two MAE-facing metrics move slightly **worse** when combined than either
lever alone, not better — a genuine (if small) anti-synergy, not additive
compounding. The mechanism is visible in Section 2: because
`backtest_projections.py` applies early-season-prior before rb-tail
calibration, the prior blend already moves some RB weeks-3-6 projections out
of the `<8`/`≥14` band boundaries before rb-tail's classifier runs, so fewer
rows are left for rb-tail to act on than if it ran on unmodified
projections — the two levers partially cannibalize each other's target
population rather than reinforcing it. The ordinal metric moves marginally
the other way, but by a noise-level amount (0.003). Critically, **there is
no double-boosting / overshoot**: the overlap-row bias check (Section 2)
shows the combination pulling the previously-most-under-projected subset
(low-boost overlap, base bias −1.22) to just above zero (+0.05), not past it
into over-projection, and the only bias-sign-flip (high-shrink overlap)
stays well inside the 1.0-pt overshoot tolerance while MAE still improves.
**The interaction is sane — it just isn't additive enough to rescue either
lever's individual near-miss.**

## Recommendation: do not flip either flag, or the combination, on by default

Running `--early-season-prior --rb-tail-calibration` together does not clear
the joint gate — both primary-bar criteria (a) and (b) fail, at 49-80% of
their respective thresholds, essentially unchanged from (very slightly worse
than) each lever's solo HOLD numbers. There is no synergy case for shipping
the pair where neither ships alone. The combination is also not dangerous
(interaction is sane, no overshoot), so there is no new reason to *avoid*
combining them if a future iteration strengthens one or both levers enough
to clear their solo bars — but that strengthening has to happen at the
lever level (per each gate doc's caveats: role-adjusted prior / higher
coverage for early-prior; longer or role-weighted trailing window for
rb-tail's low band; high-band shrink factor sweep 0.15→0.20-0.25) before a
joint re-gate is worth running again. Both flags remain opt-in/off in
`generate_projections.py` and `scripts/backtest_projections.py`.

## Files

- Backtest CSVs: `output/backtest/joint_mae_{baseline,treated}/`,
  `output/backtest/joint_mae_baseline_v2/` (2022 baseline re-run, spliced
  into the combined baseline after the injury-data confound fix),
  `output/backtest/joint_ord_{baseline,treated}/`.
- Combined per-run CSVs: `*_zzzcombined.csv` in each of the four dirs above
  (3-season `pandas.concat`, filename chosen to sort last so
  `simulate_fp_accuracy.py`'s `files[-1]` glob picks the combined file, not
  an individual season file).
- No source files changed — eval only, per task scope.
