# WR Near-Tie Ordinal Tie-Break Gate — Lever from WR_ORDERING_DIAGNOSIS.md Finding #2 (2026-08-09)

Implements + gate-evaluates the WR near-tie tie-break lever proposed in
`.planning/WR_ORDERING_DIAGNOSIS.md` finding #2 (and its addendum): WR pairs
we misorder vs Sleeper are near-ties in OUR OWN projections (median
|our_diff| 1.21 pts vs 3.51 pts typical) while real outcomes on those same
pairs spread just as widely as normal (median |actual_diff| 6.1 vs 5.8) —
these are close calls our engine specifically gets wrong, not
genuinely-unresolvable coin-flip weeks (Sleeper calls the same pairs
correctly with an equally tight projection gap of 1.28). This targets the
**ordinal** FantasyPros-style Accuracy Gap metric
(`scripts/simulate_fp_accuracy.py`) — what FantasyPros' competition scores
— not point MAE.

## Bronze data check (mandatory process rule, before building)

Signal candidates considered: trailing target-share slope (Bronze
`players/weekly`, `target_share` column) and trailing snap-share slope
(Bronze `players/snaps`, mirroring `rb_role_signals.py`).

- `data/bronze/players/weekly/season={2021,2022,2023,2024,2025}/` —
  **present locally**, includes `target_share` directly keyed by
  `player_id` (no display-name join needed, unlike the RB snap-share
  signal). 2021 present means no early-season-prior-style 2022 no-op gap
  exists for this lever (it only needs weeks < projected-week *within* the
  same backtest season, not a prior season).
- `data/bronze/players/snaps/season={2022,2023,2024}/` — present (no 2021,
  per `RB_TAIL_CALIBRATION_GATE.md`'s data-state note), but **not used** —
  the target-share signal made the snap-share join unnecessary (see below).

**Chosen signal uses only already-committed `players/weekly` data — no new
ingestion was required.**

## Signal validation (BEFORE building the lever, per the mandatory gate process)

A fresh baseline backtest (`--vs-consensus --consensus-source sleeper`,
weeks 1-18, 2022-2024, half-PPR, generated this session — see Data section)
was run through `diagnose_wr_ordering.py`'s pairwise swap-analysis machinery
(reused, not reimplemented) to reproduce finding #2's misordered-pair
population: **6,948 swap-loss pairs** (8.69% of 79,939 total WR pairs;
diagnosis doc's original number was 7,132/8.9% — small re-run variance from
`rank(method="first")` tie-breaking on a different day's data pull, not a
discrepancy worth chasing).

Quick check (per task instructions): does a candidate signal side with the
actual winner on this population more than ~52-53%?

| Signal | Population | n | Hit rate |
|---|---|---:|---:|
| target_share slope (2wk vs prior 2wk) | ALL pairs (control) | 63,556 | 51.15% |
| target_share slope (2wk vs prior 2wk) | **SWAP-LOSS (misordered) pairs** | 5,428 | **54.79%** |
| target_share slope (2wk vs prior 2wk) | swap-loss ∩ \|our_diff\|<=1.5 | 3,358 | 54.29% |
| target_share slope (3wk vs prior 3wk) | ALL pairs (control) | 60,183 | 50.57% |
| target_share slope (3wk vs prior 3wk) | SWAP-LOSS (misordered) pairs | 4,938 | 53.28% |

**Result: PASSES the quick check.** The 2wk/2wk window clears the 52-53%
bar (54.79%) on the diagnosed misordered population specifically, while
being barely-above-coinflip (51.15%) on the general pair population — this
is the expected signature of a genuine *tie-break* signal (weak in general,
useful specifically for resolving the close calls the diagnosis
identified), not a magnitude corrector. The 2wk/2wk window beat 3wk/3wk, so
it was kept (matches `rb_role_signals.SNAP_RECENT_N`/`SNAP_PRIOR_N`
defaults). **Proceeded to build.**

## Lever implemented

`src/wr_tiebreak.py` — `apply_wr_tiebreak()`:

Within each week's WR pool, sorted by `projected_points` descending, for
every ADJACENT pair whose projection gap is <= `EPSILON` (1.5 pts, matching
the diagnosis's near-tie population), if the trailing target-share slope
**disagrees** with our current order (the lower-projected player has the
higher slope), nudge the pair apart by `NUDGE` (0.5 pts, <= EPSILON/2) each
— the higher-projected player loses 0.5, the lower-projected player gains
0.5. Pairs where the signal agrees with our order are left untouched (no
upside to touching them; keeps the firing population scoped exactly to the
diagnosed misorder mechanism). `target_share_slope` = mean target_share
weeks [t-2, t-1] minus mean target_share weeks [t-4, t-3], leak-free (only
weeks < the projected week are read).

One knob exposed via CLI could be added later; none is exposed yet (matches
the "minimal" brief — `EPSILON`/`NUDGE`/window are module constants,
consistent with how `qb_starter_floor.py`'s non-haircut constants are
handled).

**Wiring** (opt-in, mirrors `--early-season-prior` / `--rb-tail-calibration`):
- `scripts/generate_projections.py --wr-tiebreak` (weekly mode only; no-op
  in `--preseason` — needs weekly trailing target-share history). Reuses
  `strength_weekly` (already-loaded `players/weekly` frame for the
  defensive-strength table) — **no extra I/O**. Applied after the RB tail
  calibration block.
- `scripts/backtest_projections.py --wr-tiebreak` — threads the lever into
  `run_backtest()`, reusing the backtest's own already-loaded `weekly_df`.

## Pre-registered gate (stated by the task coordinator before any treated numbers were computed)

**SHIP** if ALL of:
1. WR ordinal FP Accuracy Gap vs Sleeper improves >=0.08 (current WR gap
   ~0.35).
2. WR MAE weeks 3-18 doesn't worsen by more than 0.02.
3. QB/RB/TE byte-identical between baseline and treated.
4. Overall (QB+RB+WR+TE) ordinal doesn't worsen.

**Else HOLD.**

## Method

Baseline and treated backtests generated in the same session, immediately
back-to-back, per-season foreground chunks (~1-1.5 min each, well under the
10-min limit) into isolated output dirs, then combined —
`.planning/CONSENSUS_BENCHMARK_MULTI_SOURCE.md` / `RB_TAIL_CALIBRATION_GATE.md`
precedent.

```bash
# Baseline (3x per-season, isolated dirs, then combined):
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022 --weeks 1-18 \
    --scoring half_ppr --vs-consensus --consensus-source sleeper \
    --output-dir output/backtest/wr_tiebreak_baseline_2022
# (repeat for 2023, 2024) -> combined into
#   output/backtest/wr_tiebreak_baseline/backtest_half_ppr_consensus_COMBINED_20260809.csv

# Treated (3x per-season, identical command + --wr-tiebreak):
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022 --weeks 1-18 \
    --scoring half_ppr --vs-consensus --consensus-source sleeper --wr-tiebreak \
    --output-dir output/backtest/wr_tiebreak_treated_2022
# (repeat for 2023, 2024) -> combined into
#   output/backtest/wr_tiebreak_treated/backtest_half_ppr_consensus_COMBINED_20260809.csv

./venv/Scripts/python.exe scripts/simulate_fp_accuracy.py --output-dir output/backtest/wr_tiebreak_baseline
./venv/Scripts/python.exe scripts/simulate_fp_accuracy.py --output-dir output/backtest/wr_tiebreak_treated
./venv/Scripts/python.exe scripts/diagnose_wr_ordering.py --output-dir output/backtest/wr_tiebreak_baseline
./venv/Scripts/python.exe scripts/diagnose_wr_ordering.py --output-dir output/backtest/wr_tiebreak_treated
```

Regenerated fresh this session rather than reused (rule 4 of the mandatory
process — this shared repo had ~20 other backtest CSVs from other agents'
runs the same day; regenerating baseline+treated back-to-back avoids any
risk of a contaminated reused baseline).

## Firing rate (reported before headline numbers, per mandatory process rule)

**Row-level** (WR rows where `wr_tiebreak_flag=True`, weeks 1-18 — note a
flagged "middle" player in a 3-player near-tie chain can net to a zero
point change if nudged both directions, e.g. -0.5 from one adjacent pair
and +0.5 from the other; flag still fires, tested explicitly in
`test_wr_tiebreak.py::test_chained_adjacent_pairs_accumulate`):

| Season | WR rows flagged | WR rows total | Rate |
|---|---:|---:|---:|
| 2022 | 843 | 1,545 | 54.6% |
| 2023 | 967 | 1,621 | 59.7% |
| 2024 | 897 | 1,560 | 57.5% |
| **Total** | **2,707** | **4,726** | **57.3%** |

**Pair-level** (adjacent near-tied pairs with both signals present —
"eligible" — vs. pairs where the signal disagreed with our order —
"fired"; computed from the baseline CSV, which reflects exactly the pairs
`apply_wr_tiebreak` scanned since baseline and treated inputs are otherwise
identical):

| Season | Eligible pairs | Fired pairs | Rate |
|---|---:|---:|---:|
| 2022 | 1,010 | 509 | 50.4% |
| 2023 | 1,119 | 577 | 51.6% |
| 2024 | 1,061 | 527 | 49.7% |
| **Total** | **3,190** | **1,613** | **50.6%** |

Confirmed via row-level merge of baseline vs treated combined CSVs on
`(player_id, season, week)`: **0 of 6,632 non-WR rows changed** (QB/RB/TE
byte-identical); 2,236 of 4,726 WR rows have a nonzero `projected_points`
delta (fewer than the 2,707 flagged rows, entirely explained by the
zero-net chained-pair case above). Firing rate is substantial — over half
of eligible near-tie pairs get touched — so this gate is a real read on the
hypothesis, not a detector-sparsity artifact (contrast with the QB
starter-floor lever's 0.7% firing rate).

## Results

### Criterion 3 — QB/RB/TE byte-identical

Confirmed two independent ways:
1. Row-level merge of the two full combined backtest CSVs: 0 of 6,632
   non-WR rows have a different `projected_points`.
2. `simulate_fp_accuracy.py` ordinal summary — QB/RB/TE `ours` Accuracy Gap
   identical to 5 decimal places in every season, e.g. QB 2022-2024:
   7.20867 both runs; RB 2022-2024: 6.16657 both; TE 2022-2024: 6.33640
   both. QB/RB/TE weeks-3-18 MAE also identical to 4 decimals (QB 6.0404,
   RB 4.6552, TE 3.4835, both runs).

**PASSES cleanly.**

### Criterion 1 — WR ordinal FP Accuracy Gap vs Sleeper (primary bar, >=0.08 improvement required)

`gap = ours − sleeper` Accuracy Gap (lower is better); Δ = treated −
baseline (negative = improvement). Weeks 3-17 (the metric's scoring
window), 2022-2024.

| Season | Baseline ours | Treated ours | Sleeper (unchanged) | Baseline gap | Treated gap | Δ gap |
|---|---:|---:|---:|---:|---:|---:|
| 2022 | 6.54268 | 6.52796 | 6.0827 | 0.45999 | 0.44527 | **−0.01472** |
| 2023 | 6.51658 | 6.49739 | 6.2304 | 0.28614 | 0.26696 | **−0.01918** |
| 2024 | 6.85049 | 6.84532 | 6.5452 | 0.30526 | 0.30009 | **−0.00518** |
| **2022-2024** | **6.63658** | **6.62356** | **6.2861** | **0.35046** | **0.33744** | **−0.01302** |

**Gate check on criterion 1**: required >=0.08 improvement. Measured
**−0.013** — real, right direction, consistent across all three seasons
individually, but only **~16% of the required bar**. **FAILS.**

### Criterion 2 — WR MAE weeks 3-18 (must not worsen by more than 0.02)

| | Baseline | Treated | Δ |
|---|---:|---:|---:|
| WR MAE, weeks 3-18, 2022-2024 (n=4,397) | 4.4433 | 4.4398 | **−0.0035** |

**Gate check on criterion 2**: measured Δ = −0.0035 (a slight improvement,
not a regression). **PASSES comfortably** — confirms the nudge-cap design
(<=0.5 pts, symmetric within a pair) kept the MAE impact negligible as
intended.

### Criterion 4 — Overall (QB+RB+WR+TE) ordinal doesn't worsen

QB/RB/TE are byte-identical (Δ=0 each); WR improves (Δ=−0.013 gap-vs-Sleeper,
equivalently −0.013 in raw `ours` Accuracy Gap). The four-position mean
therefore moves in the improving direction by construction. **PASSES.**

### Supplementary — rank-tier and swap-loss-rate deltas (context, not gate criteria)

**Rank-curve tier (actual-finish tier), WR only, weeks 3-17:**

| Tier | Base gap_diff | Treated gap_diff | Δ |
|---|---:|---:|---:|
| WR1-12 (elite) | 0.630 | 0.608 | −0.022 |
| WR13-30 | 0.171 | 0.127 | −0.044 |
| WR31-50 | 0.217 | 0.207 | −0.010 |
| WR51+ (overranked bust) | 0.510 | 0.523 | +0.013 (slight worsening) |

**Swap-loss rate** (finding #2's misordered-pair population, recomputed on
the treated backtest): 6,948 pairs / 8.69% (baseline) → 7,044 pairs / 8.83%
(treated) — the raw *count* of misordered pairs ticked up slightly even
though the magnitude-weighted ordinal Accuracy Gap improved. This is
consistent with the ~55% signal hit rate: roughly half the eligible pairs
get their order genuinely fixed and about half get pushed the wrong way,
but the metric that matters (Accuracy Gap, which weights by how far the
baseline-value miss is, not just win/loss) shows the fixes landing on
higher-leverage pairs on net (elite tier improves most) while the
worsening concentrates in the already-noisiest tail (WR51+, up
+0.013). This is the clearest evidence the signal is a **genuine but weak**
tie-break — not strong enough to reliably fix ordering, matching its 54.8%
(barely above the ~53% floor) hit rate on the validation population.

## Verdict: **HOLD**

| Criterion | Required | Measured | Result |
|---|---|---|---|
| 1. WR ordinal gap vs Sleeper | >=0.08 improvement | 0.013 (~16% of bar) | **FAIL** |
| 2. WR MAE weeks 3-18 | not worse than +0.02 | −0.0035 (improves) | **PASS** |
| 3. QB/RB/TE byte-identical | — | confirmed 2 ways | **PASS** |
| 4. Overall ordinal doesn't worsen | — | improves | **PASS** |

Per the pre-registered rule (ALL must pass), the composite is **HOLD** —
criterion 1, the primary bar, misses by a wide margin (16% of the required
threshold, the smallest fraction-of-bar reached among the ordinal-gated
levers evaluated this cycle: `--early-season-prior`'s WR-specific weeks-3-6
cut reached 70-140% of a *different*, smaller composite bar; this lever's
whole-season number reached only 16% of its own bar). Do not flip
`--wr-tiebreak` on by default. The flag stays opt-in/off and merges as
inert, evaluable machinery, matching the established pattern for
`--early-season-prior`, `--qb-starter-floor`, and `--rb-tail-calibration`.

## Caveats / follow-ups

- **The signal is real but weak** (54.8% hit rate on the diagnosed
  misordered population, barely clearing the 52-53% floor specified for a
  "usable" signal). A 0.5-pt symmetric nudge on a signal that's right just
  55% of the time nets out to a small, noisy improvement — exactly what
  was measured. Strengthening the underlying signal (e.g. combining
  target-share trend with the snap-share trend already computed by
  `rb_role_signals.compute_snap_trend_signals` — not reused here because
  the display-name join it requires isn't needed for target_share alone,
  but a blended signal might raise the hit rate above the weak 55%) is the
  most promising next step before retrying this gate, rather than retuning
  `EPSILON`/`NUDGE`.
- **Firing on disagreement only is conservative by design** — it never
  touches a near-tie pair the signal already agrees with, so roughly half
  of the near-tie WR population (the "already correctly ordered per this
  signal" half) is left completely alone. A version that also *reinforces*
  agreeing pairs (widens their gap slightly) was considered but rejected
  for this pass — it would touch more rows for a directionally-similar but
  unvalidated effect, and the disagreement-only design keeps the
  intervention scoped exactly to the diagnosis's swap-loss mechanism,
  which is what was actually validated.
- **The 2022 gap number here (0.460) differs from `WR_ORDERING_DIAGNOSIS.md`'s
  reported 0.375 whole-2022-2024 WR gap** — that number is the 2022-2024
  combined figure (0.350 in this session's baseline, matching within
  rounding/re-run noise); the per-season 2022 breakout (0.460) is a new cut
  not previously reported at that granularity. Not a discrepancy, just a
  finer slice.
- Per the diagnosis's own priority ordering, finding #1
  (`--early-season-prior`, already gated HOLD on both MAE and ordinal
  metrics) and finding #2 (this lever) were flagged as likely to
  substantially overlap (both concentrate in weeks 3-6). Both independently
  landed HOLD — worth testing whether *combining* the two levers (early
  season prior lowers the false-confidence in thin-sample early rankings,
  then the tie-break resolves what's left close) clears either gate before
  concluding the whole finding #1/#2 family is dead; not attempted here to
  keep this gate's Δ attributable to a single lever.

## Files changed

- `src/wr_tiebreak.py` (new) — `compute_wr_target_share_slope()`,
  `apply_wr_tiebreak()`, `EPSILON` (1.5), `NUDGE` (0.5), `RECENT_N`/`PRIOR_N`
  (2/2).
- `scripts/generate_projections.py` — `--wr-tiebreak` CLI flag, weekly-mode
  wiring after the RB tail calibration block (reuses `strength_weekly`, no
  extra I/O), preseason no-op note.
- `scripts/backtest_projections.py` — same CLI flag, `run_backtest(wr_tiebreak=...)`,
  applied after the RB tail calibration block in the per-week loop (reuses
  the backtest's own already-loaded `weekly_df`).
- `tests/test_wr_tiebreak.py` (new) — 21 unit tests covering the
  target-share-slope computation (leak-free, window default, position/
  season filtering, missing-column handling) and the combined apply
  function (nudge-on-disagreement, no-nudge-on-agreement, epsilon
  threshold, missing-signal no-op, non-WR no-op, single-WR no-op,
  non-negative clipping, chained-adjacent-pair accumulation). All passing.
  Also re-ran `test_rb_tail_calibration.py`, `test_qb_starter_floor.py`,
  `test_early_season_prior.py`, and the existing tests that import
  `backtest_projections`/`generate_projections`
  (`test_external_projections.py`, `test_unified_evaluation.py`,
  `test_vegas_sign_convention.py`, `test_weekly_grading_report.py`) — 178
  passed, 8 pre-existing skips, 0 failures.
- **Data**: none ingested — the chosen signal (`target_share`, already a
  column on committed `players/weekly` Bronze) needed no new Bronze data.
