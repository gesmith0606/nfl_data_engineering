# Waiver ranking: what was tested, what held up (2026-11-16)

Plan item: make the waiver list better at picking players. Judged the only way
this repo trusts — by what the listed names went on to score — never by
agreement with Sleeper. Reproduce with `python scripts/backtest_ranking.py
--league mantis --extra-root <checkout with the newest data>`.

## Setup

Mantis, weeks 2-6 as the fit window (120 listed names = top 6 per position per
week), weeks 7 and 9 held out (48 names, windows clipped at week 9, so shorter).
Every variant lists six per position, so the position mix never moves and
nothing can win by listing more quarterbacks (the trap `src/recommendation_backtest.py`
documents). A variant is *kept* only if it beats today's blend in **both** the
fit window and the held-out weeks.

## Result: nothing beats the blend in both

| variant | fit (wk 2-6) | vs blend | held-out (wk 7, 9) | vs blend |
|---|---|---|---|---|
| tool blend (today) | 25.29 | — | 12.40 | — |
| Sleeper's projection alone | 25.70 | +0.40 | 11.23 | −1.16 |
| consensus as base, ours averaged in only within 2x | 24.92 | −0.37 | 11.42 | −0.97 |
| weekly points x games played in the window (byes) | 26.03 | +0.74 | 11.11 | −1.29 |
| bye-aware, consensus base | 25.49 | +0.20 | 11.61 | −0.78 |
| blend + snap-share jump (+15 pts, ≥30%) boost 2 / 4 | 24.24 / 23.71 | −1.05 / −1.59 | 12.39 / 10.68 | −0.01 / −1.71 |
| blend + sentiment usage_boost | 25.29 | 0 | 12.40 | 0 |
| hindsight best (ceiling) | 40.32 | +15.0 | 19.91 | +7.5 |

A least-squares combination of Sleeper, ours, a missing-ours flag, last week's
points and snap share, scored leave-one-week-out on weeks 2-6, reaches 26.0 in
the fit window (+0.7) and 12.2 held out (−0.2). The information available on a
Tuesday (two projections, last week's box score, snap share) is worth well under
a point of four-week points; the other 14 points between the board and hindsight
are things that happen after the claim is filed.

**So the plan's acceptance bar — listed names averaging 2.0 more four-week
points than 25.3 — is not reachable from this information, and nothing here
claims it.** The one place it appears to be reachable is a trap:

- A *pooled* top-24 list reads 26.8-29.1 simply because the pool is not six per
  position (TE premium, Sleeper favouring WR/RB/TE). That is mix, not skill.
- Adding today's FantasyCalc dynasty value to the blend lifts the same
  measure to 29.0-29.2 (fit) and 14.3-15.6 (held out). **Look-ahead**: the
  weekly archive of dynasty values only starts in 2026-W43, so past weeks have
  only today's value, and today's value already contains the weeks that followed
  (a free agent who broke out in week 5 is worth more in November). It is shown
  in the backtest to size the trade-off and flagged as not evidence.

## Role-change flags

| flag | testable? | result |
|---|---|---|
| last week's snap-share jump | yes (Bronze snaps) | **lowers** four-week points at every weight |
| starter ahead Out / on IR | no point-in-time data: depth charts are archived on 5 days of 2026, and the official injury report for the week is not out by Tuesday | not kept |
| expected points minus actual (ffopportunity) | no: the dataset ends in 2025 | not kept |
| Sleeper trending adds | no: only the live endpoint exists | recorded by `waiver_wire.py` from now on (`adds_48h` in every record); fit it after ~6 weeks |
| sentiment `usage_boost` | exists for 6 name-weeks before week 9 | untestable |

All four ship in `src/waiver_rank.FLAG_BOOSTS` **at zero**, so a boost is a
number someone changes after the scorecard says so.

## What does change, and why

The ranking changes in structure, not in what it claims to predict better:

1. One list per league, ordered by the **gain to my best lineup over the next four
   weeks, byes included** (not by one-week blend), with dynasty value in points
   added in a dynasty league. A claim that does not crack my lineup scores zero
   and falls back to dynasty value, then blend — so the order is never arbitrary.
2. The claims file is the top targets by that score, each with its drop, and in a
   dynasty league it is allowed to offer an asset the redraft verdict calls "no
   help" this week.
3. Inputs the report used to guess are printed as unknown at the top.

The dynasty-value weight (`--dyn-points`, default 0.04 four-week points per
FantasyCalc unit) is a **decision for George**, not a fit — see the PR.
