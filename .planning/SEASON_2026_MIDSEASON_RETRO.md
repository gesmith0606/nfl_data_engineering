# 2026 midseason retro — measured, weeks 1-6 (written 2026-10-21)

Graded with the official harness (`scripts/weekly_grading_report.py`, half-PPR,
cons>=5 population) for every week 1-6. **No 2026 grading report existed before
this session** — `output/grading/` is in `.gitignore:525`, so the Tuesday cron's
reports only ever lived as CI artifacts and nothing was tracked week to week.
Reports for w1-6 now regenerated locally under `output/grading/season=2026/`.

## Scoreboard (half-PPR, cons>=5, vs Sleeper, MAE against actuals)

| Pooled | n | ours | Sleeper | gap | ours bias |
|---|---|---|---|---|---|
| w1-6 | 972 | 5.603 | 5.431 | **+0.172** | -0.29 |
| w3-6 (canonical window) | 633 | 5.440 | 5.271 | **+0.169** | +0.07 |

Per position, w3-6:

| pos | n | ours MAE | Sleeper | gap | ours rho | Sleeper rho |
|---|---|---|---|---|---|---|
| QB | 113 | 5.91 | 5.28 | **+0.630** | 0.207 | **0.434** |
| RB | 176 | 5.73 | 5.65 | +0.084 | **0.484** | 0.468 |
| WR | 242 | 5.11 | 5.12 | -0.003 | 0.327 | 0.339 |
| TE | 102 | 5.19 | 4.98 | +0.211 | **0.233** | 0.169 |

Per week gap: w1 +0.237, w2 +0.124, w3 +0.037, w4 +0.064, w5 +0.411, w6 +0.183.

Context: the sealed-2025 standing was **-0.086 overall** (we beat Sleeper, QB -0.39).
So 2026 is a **~0.26 MAE regression against consensus, and the QB position flipped
from our best (-0.39) to our worst (+0.63)**. "Disappointing" is the right word and
the headline is QB.

## Root causes (measured, not guessed)

1. **QB: over-dispersed and over-projected.** Our QB sd within a week is 3.81 vs
   Sleeper's 2.78. We over-project 61% of QB rows; 13% of our QB rows miss by
   >10 pts vs Sleeper's 8%. The worst misses are all low-end/fill-in starters
   treated as full starters (Shough 18.3->-0.2, Brissett 21.4->6.9, Winston
   18.1->6.5, Nix 16.2->4.5, Mariota 16.0->5.3). Rank ordering is the real damage:
   rho 0.207 vs 0.434 — start/sit calls depend on ordering, not MAE.
2. **Top-tier inflation across the board** (w3-6 bias by our own projected tier):
   QB 20+ **+3.55**, TE 12-16 **+4.01**, WR 16-20 **+4.28**, RB 12-16 **+2.16**;
   and the low tiers are under-projected (QB <8 -4.13, RB/WR/TE <8 ~-1.2).
   Sleeper's tier biases are far flatter. Our projection distribution is too wide.
   This is the opposite of the week-2 compression the `--early-season-prior` lever
   was built for, and it is a pure calibration defect.
3. **The shipped Sleeper anchor is silently eroding.** Coverage of the
   anchor-eligible WR/RB/TE pool: w3 93% -> w4 91% -> w5 86% -> w6 **79%** -> w7 81%
   (per position w6: WR 80%, RB 76%, TE 79%). The guard only warns below 50%, so a
   load-bearing shipped lever quietly stopped firing on ~1 row in 5. Likely the
   Sleeper->GSIS map going stale against in-season roster churn.
4. **Game predictions produced nothing for w1-6.** Known and already fixed
   (workflow comment, issue #105, predictions step added 2026-10-18) — week 7 is the
   first real output. But: there is no 2026 ATS/CLV evidence at all, and the sanity
   gate still omits `--check-predictions`, so a bad predictions file won't be caught.

## Levers, ranked by measured out-of-sample value

**SHIPPED 2026-10-21** (user-approved): levers 1 and 2 below. Numbers in this
section were re-measured with the REAL production mechanisms after two
corrections to the first pass — see "Corrections" below. MAE is against
**actuals**, so these are real gains, not the Sleeper-gap circularity the
anchor gate doc warns about.

Replayed on the published 2026 w3-6 boards (n=633, half-PPR, cons>=5):

| variant | pooled MAE | vs base | QB MAE | QB rho | gap vs Sleeper |
|---|---|---|---|---|---|
| baseline (what we shipped through w6) | 5.440 | — | 5.908 | 0.207 | +0.169 |
| QB Sleeper anchor, blend w=0.5 | 5.405 | **-0.035** | 5.711 | **0.350** | +0.134 |
| dispersion shrink k=0.8 | 5.390 | **-0.050** | 5.730 | 0.208 | +0.119 |
| **both (shipped)** | **5.364** | **-0.076** | **5.582** | **0.350** | **+0.093** |
| Sleeper | 5.271 | | 5.278 | 0.434 | — |

Together they close **45% of the consensus deficit**. Neither needs new data
or a retrain.

1. **QB Sleeper anchor, blend w=0.5 — SHIPPED.** Added to
   `sleeper_consensus_anchor.SHIPPED_DEFAULT_CONFIGS`, so it is default-ON in
   weekly mode and in the backtest's default evaluation path. Its value is the
   **ordering** (QB rho 0.207 -> 0.350), which is what start/sit turns on; the
   MAE gain is modest because a rank-blend permutes our own point values
   rather than pulling them toward Sleeper's. The weight sweep is monotone to
   w=1.0 (QB MAE 5.444, rho 0.433 — adopting Sleeper's QB ordering outright),
   so w=0.5 deliberately keeps half our own signal; **there is more on the
   table here** if we want it. Shipped on live evidence against a historical
   HOLD, exactly as RB+TE were on 2026-09-23. Caveat: n=113 over 4 weeks.
2. **Dispersion shrink k=0.8 — SHIPPED.** New `src/dispersion_shrink.py`,
   default-ON weekly (`--no-dispersion-shrink` to opt out), runs last among
   the stages that touch `projected_points`. Pulls each position's rows toward
   that position's own startable-pool mean. Leak-free (the centre comes from
   the same batch), and monotone within a position, so `position_rank` is
   untouched by construction. Per-week fitted k was stable (0.65/0.75/0.70/
   0.75), so 0.8 is a conservative fixed prior, and a walk-forward pass
   agrees with it.
   - **Confined to the >=5pt startable pool** (`MIN_SHRINK_PTS`). Adjusting
     every live row scores marginally better (5.346 vs 5.364) but inflates the
     board's total projected points **+11.2%**, because the shrink pulls the
     sub-5 bench UP and that tail is most of the board. The retro measured
     nothing below 5 pts, and those are exactly the rows `waiver_wire.py` /
     `stream_dst_k.py` discriminate between, so the 0.018 MAE was not worth
     the distortion. With the floor, board totals are flat (-0.0%).
   - Translates `projected_floor`/`projected_ceiling` by the same delta, so
     the band keeps its WIDTH (and the conformal coverage property) and still
     brackets the point estimate.
3. **Raise the TE anchor weight 0.5 -> 0.75 — REJECTED 2026-10-22.** The
   sweep quoted in the first version of this doc (w=0.5 5.06, w=0.75 5.01,
   w=1.0 4.98 vs 5.19) was **invalid**: it point-blended on top of published
   boards that already carried the shipped TE rank-blend at 0.5, so it
   measured a second, different transform stacked on the first — not a change
   to the shipped weight. Re-measured properly by changing the weight through
   the CLI and re-running the backtest: matched TE MAE **4.75 at w=0.5 vs
   4.80 at w=0.75** (hit rate 0.542 -> 0.563, rho 0.227 -> 0.231). Slightly
   worse on MAE, slightly better on ordering, all noise at n=102. No case to
   ship.
4. **Fix the anchor coverage erosion** (finding 3) — restores a lever already
   approved and paid for, pure engineering, no gate needed.
5. **`--early-season-prior` graded live: SHIP for QB/WR/TE, not RB.** The
   shadow boards have been running since w3. Shadow vs production, w3-6
   (n=633): overall **-0.053** (QB -0.118, WR -0.076, TE -0.081, RB **+0.036**).
   Real but small, and its window is weeks 3-6, so the value is next season.
6. **Persist the grading report.** Un-gitignore `output/grading/` (or commit
   the JSON) so the cumulative table survives and a regression like this
   surfaces in week 3 instead of week 7. The RB/TE anchor ship note said
   "watch the grading report through week 10" — nothing was watching.

## Corrections to the first pass of this retro

Both found while implementing, both material:

1. **The anchor's `blend` mode is a RANK-blend with minimal reassignment, not
   a point-wise blend.** It permutes our own point values among a position's
   pool according to blended ranks; it does not average our points with
   Sleeper's. The first pass simulated a point blend and so overstated the QB
   anchor at -0.079 overall; the real mechanism gives **-0.035** (and the
   combined lever -0.076, not -0.122). The ordering gain is real either way.
2. **The shrink's centre must come from our own board**, not from the filtered
   eval set the study used. Re-measured with the production-faithful centre it
   is -0.050 (vs -0.064 as first measured, before the >=5pt floor). The
   dependence was small, but the first framing was not reproducible in
   production.

## Verification on week 7 (2026-10-21)

Shadow board at
`data/gold/projections_shadow/calibrated_2026_10_21/season=2026/week=7/`
(not published — the live board is untouched). Both levers fire: the QB anchor
matched 29/35 QB rows, the shrink calibrated 158 rows across all four
positions (QB sd 2.35 -> 1.88, WR 2.52 -> 2.01). Board total 2069.0 -> 2069.1.
Verified against a levers-off control generated from the same day's data:

- no negative points, no NaNs, no duplicate player_ids, `position_rank` 1..n;
- all 8 injury-zeroed rows still 0 (the levers resurrect nothing);
- 31 bye-week rows carry small non-zero projections (0.8-1.74) — **identical
  in the control**, so pre-existing and not caused by these levers, but it
  does contradict the documented "bye week -> all stats zeroed" invariant and
  is worth a look;
- QB top-of-board compressed and reordered as intended (B.Young 20.3 -> 16.7,
  D.Maye now QB1 at 18.1).

### Pre-existing bug found during verification (NOT fixed here)

On the `--ml` path the shipped Sleeper anchor leaves **21 rows with
`projected_points` outside their own `projected_floor`/`projected_ceiling`**
(e.g. C.Sutton floor 2.83 / point 7.12 / ceiling 6.29). Cause: the ML router
attaches the band *before* the anchor runs, and the anchor's rank
reassignment hands a player a different point value without moving his band.
Reproduced with the dispersion shrink switched off — **21 violations, the
identical row set** — so it is the anchor, not the new lever, and it affects
the already-shipped WR/RB/TE anchors (the violations are 9 RB / 7 TE / 5 WR,
no QB). The 2026-10-20 live board shows 0 violations because it came from a
different path that recomputed the band afterwards. Fix would be to re-align
or re-derive floor/ceiling after the anchor stage.

## What is NOT the problem

- **Board coverage is fine**: 96.5-97.2% of cons>=5 players who played were on our
  board (w1-6). Only 11 missing players scored >=12 (Daniels wk5 30.3 the worst).
- **RB is no longer the deficit** (+0.084, and we beat Sleeper on rho). The 2026-06
  "RB +0.26 is our last gap" framing is stale; QB replaced it.
- Week 5 was hard for everyone (ours 5.89, Sleeper 5.48) — not solely our failure.

## Honesty notes

- Levers 1/3 blend toward Sleeper while Sleeper is also our benchmark. The MAE
  numbers here are against **actuals**, so the gains are real; the *gap-vs-Sleeper*
  column is the circular one and should not be quoted as the win.
- n=113 QB rows over 4 weeks is thin. The pre-registered way to ship is a shadow
  board for w7+ graded weekly, not a one-shot replay — but the replay is strong
  enough (and the lever cheap/reversible enough) to run in production now.
