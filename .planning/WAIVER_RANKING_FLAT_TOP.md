# Where the waiver-tier ranking loses to the box score

**Date:** 2026-10-28 · **Data:** 2026 weeks 2-7, Mantis + La Liga, 12 room-weeks
**Reproduce:** `python scripts/backtest_recommendations.py --league mantis --top-k 5`

`backtest_recommendations.py` scored the board's waiver-tier ordering at TIED WITH THE BOX
SCORE — it clears a shuffled null comfortably but has no measurable edge over ranking the same
tier by last week's points. This is the follow-up: *where* does it lose?

## It does not lose. It loses only at the very top.

Lift over the tier average, by how deep the pick goes, both rooms:

| top-k | board (mantis / la_liga) | box score | edge |
|------:|---|---|---|
| 1  | +4.55 / +3.27 | +4.86 / +4.42 | **-0.31 / -1.15** |
| 3  | +3.15 / +3.24 | +3.20 / +3.18 | -0.05 / +0.06 |
| 5  | +2.57 / +2.64 | +2.78 / +2.49 | -0.21 / +0.15 |
| 10 | +2.44 / +2.40 | +1.93 / +2.04 | **+0.51 / +0.36** |
| 20 | +1.98 / +1.83 | +1.54 / +1.41 | **+0.44 / +0.42** |
| 40 | +1.18 / +1.06 | +0.80 / +0.68 | **+0.38 / +0.38** |

Same sign in both rooms at every depth. Across the whole tier the board's ordering also
correlates with outcomes better than the box score does (mean within-position Spearman **0.462
vs 0.375**). The modelling works. The top-5 — the only slice a waiver report reads — is where
it stops working.

## Mechanism: the board's ordering is FLAT at the top of the tier

Mean projected vs mean actual, by rank inside the waiver tier:

| rank in tier | projected | actual | over by |
|---|---|---|---|
| 1-5    | 9.48 | 7.39 | **+2.09** |
| 6-10   | 8.19 | 7.14 | +1.05 |
| 11-20  | 5.67 | 4.48 | +1.19 |
| 21-40  | 3.63 | 3.00 | +0.63 |
| 41+    | 1.78 | 1.31 | +0.46 |

The separation the board claims against the separation that materialises:

| step | board says | reality | |
|---|---|---|---|
| ranks 1-5 vs 6-10  | +1.12 | **+0.37** | mantis +1.30 -> +0.25 · la_liga +0.94 -> +0.49 |
| ranks 6-10 vs 11-20 | +1.94 | **+1.88** | mantis +2.52 -> +2.66 · la_liga +1.45 -> +1.20 |

**One step down the tier the board is near-perfectly calibrated; at the top it claims three
times the gap that exists.** The top five of a position's waiver tier are, in truth, barely
distinguishable from ranks 6-10 — and the board presents them as a clear ordering. Replicates
in both rooms independently.

This is over-extrapolation at the extreme, not a bias: the projection is a product of a rolling
average, a usage multiplier, a matchup factor and a Vegas multiplier, and the top of any slice
is where favourable values of all four compound. **The shipped per-position dispersion shrink
(2026-10-21, k=0.8) does not address it** — shrinking toward a positional mean is monotone, so
it corrects the +2.09 magnitude while leaving the ordering, which is the part that fails, exactly
as it was.

## What is NOT the explanation

- **Not a position.** Mantis loses at WR (-1.42 at k=5) and La Liga *gains* at WR (+1.34);
  Mantis QB -0.45 against La Liga QB -2.75. Per-position splits at k=5 are ~30 player-weeks of
  a spiky distribution and do not replicate. An earlier read of this analysis called WR the
  hole; the second room refuted it.
- **Not inactive players.** Board picks played 85% of the time against the box score's 84%.
  The Huntley failure mode is real but it is not what costs the top-5 its edge.
- **Not the board restating the box score.** They share only **1.6 of 5** picks per position.
  These are genuinely different rankings that happen to score the same.

## Directional, NOT established: blending the two

Ranking by `0.5 x pct_rank(projected) + 0.5 x pct_rank(prior points)`:

```
                      mean lift (k=5, 12 room-weeks)
  box score only              +2.67
  50/50 blend                 +2.99
  board only                  +2.61
  blend minus board   +0.38  se 0.41  MDE 1.15  wins 6/12
  blend minus box     +0.35  se 0.33  MDE 0.93  wins 6/12
```

Both edges sit **below the MDE and win half the weeks**. Settling an effect this size needs
~107 room-weeks, about **3 seasons across these two rooms**. Do not ship it on this evidence —
that is the ELITE 2.4 mistake with the sign flipped. Recorded so the weight is already written
down when the sample arrives.

## What this changes today

The board's #1 waiver-tier name is **not** meaningfully better than its #5-10. The practical
read is to treat the top ~10 as one undifferentiated candidate set and break the tie on things
the board does not model — role change, snap trend, the week's news — which is what runbook
Step 3c already does by hand. It is an argument against ever auto-picking the top name, and
evidence that the manual shortlist step is load-bearing rather than ceremonial.
