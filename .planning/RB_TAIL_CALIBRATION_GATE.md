# RB Magnitude-Tail Calibration Gate — Lever #2 (2026-08-09)

Implements + gate-evaluates lever #2 from `.planning/CONSENSUS_ERROR_DECOMPOSITION.md`
finding #2/#4: RB projections under 8 pts under-project actuals by ~2.3-2.6
pts (sources stay roughly unbiased there); projections of 14+ pts
over-project actuals by ~1.2-1.4 pts. Both tails reliable (n 400-570), both
consensus sources agree on direction, concentrated in role-volatile
committee backs (Swift, Barkley, Charbonnet, Pacheco, ...).

## Data-state note — snap-count Bronze data did not exist locally

`data/bronze/players/snaps/` was completely absent before this task (only
`data/bronze/players/{rookies,rosters,weekly}` existed). This meant the
**already-shipped** production RB down-correction
(`projection_engine._apply_rb_snap_collapse`, `USE_RB_SNAP_COLLAPSE=True` by
default) was a silent structural no-op in every backtest run to date — every
prior gate doc's "baseline" ran without it. Ingested via
`bronze_ingestion_simple.py --data-type snap_counts --seasons 2022-2024`
(local-first, no AWS credentials needed, ~53K rows across 3 seasons) before
any investigation or eval below. Per the mandatory process rule, the
baseline for this gate is regenerated fresh AFTER this ingestion, in the
same session as the treated run, on identical data — so the existing
snap-collapse correction is active in **both** baseline and treated, and
the measured delta isolates only the new lever.

## Investigation — is the low-band under-projection driven by rising opportunity?

Joined the 2026-08-09 Sleeper matched-consensus backtest CSV
(`consensus_matched_sleeper_half_ppr_20260809_035714.csv`) against
`rb_role_signals.compute_snap_trend_signals` (the same leak-safe trailing
snap-share-slope signal already used by the production down-correction),
2022-2024, RB rows only.

**Low band (<8 pts projected)**: RBs with `snap_share_slope > 0.10` (trailing
2-week snap share rising vs the prior 2 weeks) are under-projected roughly
4x worse than the rest of the low band:

| Subset | n | bias (proj − actual) |
|---|---|---|
| Rising (slope > 0.10) | 276 | **−1.75** |
| Not rising | 836 | −0.44 |

Confirmed, and the split sharpens with a higher threshold (0.15: rising
bias −2.20 vs not-rising −0.47, n=185/1112). **Hypothesis confirmed**: a
fast-reacting opportunity-trend signal separates the biased low-band
subpopulation.

**High band (14+ pts projected)**: the same slope split shows almost no
differentiating power (bias 0.92 rising vs 0.90 not-rising) — the
over-projection here is a generic magnitude/regression-to-mean effect
across the whole band, not a role-change subpopulation. Fitted lever:
plain shrink-toward-position-mean, no role gating.

An empirical weight sweep (blend toward trailing-2-week actual PPG, low
band; blend toward same-week RB position mean, high band) on the same
matched-Sleeper sample picked `LOW_BAND_WEIGHT = 0.4` (MAE improves
4.48→4.38 in the rising subset; bias more than halves −2.20→−0.97) and
`HIGH_SHRINK_FACTOR = 0.15` (MAE 6.98→6.79; bias 1.35→0.13). Full
derivation in `src/rb_tail_calibration.py` module docstring.

## Lever implemented

`src/rb_tail_calibration.py` — `apply_rb_tail_calibration()`:

1. **Low-band boost**: RB rows projected <8 pts AND flagged
   snap-share-rising (`snap_share_slope > 0.15`, reusing
   `rb_role_signals.compute_snap_trend_signals` — the same signal the
   production `RB_SNAP_COLLAPSE` down-correction already uses, mirror
   direction) are blended toward the player's own trailing 2-week actual
   fantasy points (`compute_rb_trailing_opportunity_ppg`, leak-free —
   strictly weeks < the projected week) at weight 0.4.
2. **High-band shrink**: RB rows projected >=14 pts (evaluated AFTER the
   low-band boost, so a boosted row that crosses into 14+ is still
   eligible) are blended toward the mean `projected_points` of all RB rows
   in the same week's projection batch at weight 0.15.

Two knobs: `--rb-tail-low-weight` (default 0.4), `--rb-tail-high-shrink`
(default 0.15). Provenance columns `rb_tail_low_boost_flag` /
`rb_tail_high_shrink_flag`.

**Wiring** (opt-in, mirrors `--early-season-prior` / `--qb-starter-floor`):
- `scripts/generate_projections.py --rb-tail-calibration` (weekly mode
  only; no-op in `--preseason`). Applied after the QB starter floor block.
- `scripts/backtest_projections.py --rb-tail-calibration` — threads the
  lever into `run_backtest()`, reusing the backtest's own multi-season
  `snap_counts_df`/`weekly_df` (no extra I/O beyond the ingestion above).

## Pre-registered gate (written before running the eval)

**SHIP** if ALL of:
1. RB weeks 3-18 overall MAE gap vs Sleeper improves ≥0.08 pts (baseline
   ~+0.26 per the task brief; actual fresh baseline measured below since
   the snap-data ingestion changes the baseline itself — see data-state
   note above).
2. Both band biases (low <8, high 14+) move toward zero.
3. QB/WR/TE slices byte-identical between baseline and treated.
4. Full-season RB does not worsen on the ordinal FP-accuracy metric
   (`scripts/simulate_fp_accuracy.py`) by more than 0.03.

**Else HOLD.**

## Method

Canonical eval process (`.planning/CONSENSUS_BENCHMARK_MULTI_SOURCE.md` /
precedent set by `EARLY_SEASON_PRIOR_GATE.md`'s deconfounded section):
baseline and treated backtests generated in the same session, on the same
(post-ingestion) data, immediately back to back — no reused stale CSVs.

```bash
# MAE-gate baseline (fresh, post snap-ingestion):
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --scoring half_ppr --ml --full-features --output-dir output/backtest

# MAE-gate treated:
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --scoring half_ppr --ml --full-features --rb-tail-calibration --output-dir output/backtest

# Consensus benchmark + decomposition for each
./venv/Scripts/python.exe scripts/benchmark_consensus_sources.py --backtest-csv <csv> \
    --sources espn sleeper --output-dir output/backtest --json-out <json>
./venv/Scripts/python.exe scripts/decompose_consensus_errors.py \
    --sleeper-csv <matched_sleeper.csv> --espn-csv <matched_espn.csv>

# Ordinal-gate baseline / treated (isolated dirs, plain heuristic --vs-consensus)
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --weeks 1-18 --scoring half_ppr --vs-consensus --consensus-source sleeper \
    --output-dir output/backtest/baseline_rbtail
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --weeks 1-18 --scoring half_ppr --vs-consensus --consensus-source sleeper \
    --rb-tail-calibration --output-dir output/backtest/treated_rbtail
./venv/Scripts/python.exe scripts/simulate_fp_accuracy.py --output-dir output/backtest/baseline_rbtail
./venv/Scripts/python.exe scripts/simulate_fp_accuracy.py --output-dir output/backtest/treated_rbtail
```

## Execution note — foreground per-season chunking

The full 3-season `--ml --full-features` backtest exceeds the harness's
default foreground timeout (a single season alone takes ~2 min; 3 seasons
in one command auto-backgrounds). Per the coordinator's correction, baseline
and treated were each run as three separate **foreground** per-season
commands (`--seasons 2022`, `--seasons 2023`, `--seasons 2024`, each ~2 min,
well under the 10-min chunk limit) into isolated per-season output dirs,
then combined with `pandas.concat` before feeding
`benchmark_consensus_sources.py` / `decompose_consensus_errors.py`. Same
approach for the heuristic `--vs-consensus` ordinal-gate runs. This still
satisfies the "same session, identical data, no reused stale CSVs" rule —
baseline and treated were generated back-to-back in this session on the
same post-ingestion data state, just split into 6 smaller subprocess calls
instead of 2 large ones.

## Firing rate (reported before headline numbers, per mandatory process rule)

RB rows changed / total RB rows, weeks 3-18 (the backtest's default window;
all rows are already 3-18), 2022-2024 combined, `--ml --full-features`:

| Signal | 2022 | 2023 | 2024 | Total | Rate |
|---|---|---|---|---|---|
| Low-band boost (`rb_tail_low_boost_flag`) | 62/954 | 71/939 | 69/948 | 202/2,841 | **7.1%** |
| High-band shrink (`rb_tail_high_shrink_flag`) | 139/954 | 108/939 | 165/948 | 412/2,841 | **14.5%** |
| **Any RB row changed** | | | | **612/2,841** | **21.5%** |

Confirmed via a row-level merge of baseline vs treated on `(player_id,
season, week)`: **0 of 7,750 non-RB rows changed** (byte-identical QB/WR/TE
— see criterion 3 below); 612 of 2,841 RB rows changed. Firing rate is
moderate, not tiny — the verdict below is a real read on the hypothesis, not
just a detector-sparsity artifact (contrast with the QB starter-floor lever,
which fired on 0.7% of QB rows and whose HOLD was explicitly about detector
recall, not the underlying hypothesis).

## Results — MAE gate (`--ml --full-features`, 2022-2024)

`gap = our_mae − source_mae` (negative = we win). Δ = treated − baseline
(negative Δ = improvement). Both baseline and treated regenerated fresh in
this session on the current (post snap-ingestion) data state — no reused
stale CSVs.

**RB weeks 3-18 overall gap (primary criterion):**

| Source | n | baseline gap | treated gap | Δ |
|---|---|---:|---:|---:|
| Sleeper | 1,877 | +0.274 | +0.211 | **−0.063** |
| ESPN | 1,834 | +0.178 | +0.125 | **−0.053** |

**Gate check on criterion 1**: required ≥0.08 improvement vs Sleeper.
Measured **0.063** — **fails**, at 79% of the bar. Directionally consistent
vs ESPN too (−0.053).

**Magnitude-band biases (criterion 2):** `our_bias = mean(proj − actual)`,
positive = over-projects, negative = under-projects.

| Band | Source | n base→treat | bias base→treat | Δ (toward zero?) |
|---|---|---|---|---|
| <8 pts | Sleeper | 595→569 | −2.497→−2.298 | +0.199, toward zero ✓ |
| <8 pts | ESPN | 614→586 | −2.321→−2.162 | +0.159, toward zero ✓ |
| 14+ pts | Sleeper | 411→306 | +1.212→+0.112 | −1.100, toward zero ✓ |
| 14+ pts | ESPN | 398→299 | +1.062→−0.093 | −1.155, toward zero (slight overshoot past 0) ✓ |

**Gate check on criterion 2**: all four band-bias numbers move toward zero.
**Passes** — the high band in particular moves dramatically (bias cut by
~90%), consistent with the investigation finding that band's over-projection
is a clean generic-shrinkage fix. The low band improves more modestly in
the aggregate (~8% bias reduction) — expected, see caveats below: the boost
is large enough that many of the most-under-projected flagged rows cross out
of the <8 band into 8-14, so the residual <8 population understates the
fired subset's true within-population improvement (same selection-effect
dynamic documented in `QB_STARTER_FLOOR_GATE.md`'s floor-crossing note).

**Population shrinkage note**: both bands lose rows to the boost/shrink
crossing the band boundary (a mechanical, expected effect, not a modeling
bug) — <8 band 595→569 (Sleeper) / 614→586 (ESPN); 14+ band 411→306 /
398→299.

**Criterion 3 — QB/WR/TE byte-identical**: confirmed two ways. (a) Row-level
merge of the two full combined backtest CSVs on `(player_id, season, week)`:
0 of 7,750 non-RB rows have a different `projected_points`. (b)
`benchmark_consensus_sources.py` aggregate MAE/bias/Spearman/n identical to
displayed precision for QB, WR, TE across both sources (e.g. QB vs Sleeper:
6.03 MAE / −0.37 gap in both runs; WR vs ESPN: 5.12/+0.05 in both). **Passes
cleanly.**

## Results — ordinal-gate guard (heuristic, `--vs-consensus`, weeks 3-17)

FantasyPros-style Accuracy Gap (ordinal ranking metric,
`scripts/simulate_fp_accuracy.py`), 2022-2024 pooled, half-PPR:

| Position | baseline (ours) | treated (ours) | Δ | Sleeper (unchanged) |
|---|---:|---:|---:|---:|
| QB | 7.21 | 7.21 | 0.000 | 7.19 |
| RB | 6.16 | 6.15 | **−0.01** | 5.92 |
| WR | 6.64 | 6.64 | 0.000 | 6.29 |
| TE | 6.33 | 6.33 | 0.000 | 6.12 |

**Gate check on criterion 4**: required RB not to worsen by more than 0.03.
Measured **Δ = −0.01** (a slight improvement, not a regression). **Passes
comfortably.** QB/WR/TE ordinal scores also confirm byte-identical (exact
match to 2 decimals), corroborating criterion 3 on an independent metric.

## Verdict: **HOLD**

| Criterion | Required | Measured | Result |
|---|---|---|---|
| 1. RB w3-18 MAE gap vs Sleeper | ≥0.08 improvement | 0.063 (79% of bar) | **FAIL** |
| 2. Both band biases toward zero | — | low: modest; high: large | **PASS** |
| 3. QB/WR/TE byte-identical | — | confirmed 2 ways | **PASS** |
| 4. Ordinal RB doesn't worsen >0.03 | — | −0.01 (improves) | **PASS** |

Per the pre-registered rule (ALL must pass), the composite is **HOLD** —
criterion 1, the primary bar, misses by a real (not noise-level) margin: 3
of 4 checks pass, and the miss is proportionally the closest of any HOLD
verdict recorded across the three levers evaluated this cycle (79% of bar,
vs qb-starter-floor's ~6-9% of its bar). Do not flip `--rb-tail-calibration`
on by default. The flag stays opt-in/off and merges as inert, evaluable
machinery, matching the established pattern for `--early-season-prior` and
`--qb-starter-floor`.

## Caveats / follow-ups

- **The high-band shrink is doing most of the work; the low-band boost is
  real but capped by the selection effect.** The dramatic high-band bias
  improvement (+1.06→−0.09 vs ESPN) suggests `HIGH_SHRINK_FACTOR` could
  plausibly go higher before overshooting past zero — a small further sweep
  (0.15→0.20-0.25) is a cheap next experiment, since the investigation
  showed MAE improving *monotonically* with shrink weight in this band (no
  turning point was found in the original sweep up to w=0.3). The low band
  is harder: the boost fires on only 7.1% of RB rows (the snap-rising
  subpopulation), and blending a noisy 2-game trailing PPG signal at higher
  weight was already shown (in the pre-registration sweep) to trade MAE for
  bias — there is a real ceiling here, not just an undertuned knob.
- **Snap-count data was completely missing from local Bronze before this
  task** (see data-state note above) — this also means the pre-existing,
  already-shipped `USE_RB_SNAP_COLLAPSE` production correction was a silent
  no-op in every backtest gate run before this one (including
  `EARLY_SEASON_PRIOR_GATE.md` and `QB_STARTER_FLOOR_GATE.md`'s "clean"
  baselines). Both this gate's baseline and treated runs now correctly
  include that correction (since both postdate the ingestion), so it does
  not confound this gate's Δ — but anyone comparing this gate's absolute RB
  gap numbers (+0.274/+0.211 vs Sleeper) against older docs' RB gap numbers
  (e.g. +0.319 in `CONSENSUS_ERROR_DECOMPOSITION.md`, dated the same day but
  generated before the snap ingestion) should expect a data-state
  discontinuity, not a lever effect.
- **Firing rate is moderate (21.5% of RB rows touched), materially higher
  than the QB starter-floor lever's 0.7%** — this HOLD is a genuine read on
  the hypothesis at reasonable statistical power, not a detector-recall
  problem. A future iteration should focus on the low-band signal quality
  (e.g. a longer or role-weighted trailing window, or blending in the
  teammate-injury signal already computed by `rb_role_signals.py`'s
  `rb_better_teammate_out`) rather than just retuning existing knobs.

## Files changed

- `src/rb_tail_calibration.py` (new) — `compute_rb_trailing_opportunity_ppg()`,
  `compute_rb_rising_ids()`, `apply_rb_tail_calibration()`,
  `RISE_THRESHOLD`, `LOW_BAND_MAX`, `HIGH_BAND_MIN`, `LOW_BAND_WEIGHT`,
  `HIGH_SHRINK_FACTOR`. Reuses `rb_role_signals.compute_snap_trend_signals`
  (the same leak-safe signal the existing `RB_SNAP_COLLAPSE` production
  correction already relies on) rather than inventing a new signal.
- `scripts/generate_projections.py` — `--rb-tail-calibration` /
  `--rb-tail-low-weight` / `--rb-tail-high-shrink` CLI flags, weekly-mode
  wiring after the QB starter-floor block.
- `scripts/backtest_projections.py` — same three CLI flags,
  `run_backtest(rb_tail_calibration=..., rb_tail_low_weight=...,
  rb_tail_high_shrink=...)`, applied after the QB starter-floor block in the
  per-week loop (reuses the backtest's own already-loaded
  `snap_counts_df`/`weekly_df`, no extra I/O).
- `tests/test_rb_tail_calibration.py` (new) — 25 unit tests covering
  trailing-opportunity-PPG computation (leak-free, window default, position/
  season filtering), rising-ID detection (threshold, missing data, no-map
  case), and the combined apply function (low-band boost, high-band shrink,
  mid-band no-op, non-RB no-op, boosted-row-crosses-into-high-band edge
  case, empty/missing-data no-ops). All passing.
- `CLAUDE.md` — one-line command reference under "Gold: Fantasy
  projections".
- **Data**: ingested `data/bronze/players/snaps/season={2022,2023,2024}/`
  (previously entirely absent locally) via `bronze_ingestion_simple.py
  --data-type snap_counts --seasons 2022-2024` — required for both this
  lever and the pre-existing `RB_SNAP_COLLAPSE` production correction to
  function in any local backtest.
