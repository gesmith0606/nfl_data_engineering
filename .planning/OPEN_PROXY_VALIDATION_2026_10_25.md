# The open proxy is not noisy — it is four months early (2026-10-25)

`CLV_PICK_RULE_AUDIT_2026_10_24.md` closed with a new risk: the open side of
`evaluate_line_capture` deviates **2.38 pts** from the same game's nflverse
line, 87% of opens come from 1–2 books, and 15 of 93 settled games fit the
*opposite* sign better — input noise ~8x the +0.3 gate threshold. It named
three candidate causes: a genuine line move, a mixed sign convention, or a
thin-book artifact.

It is the first one, in all 107 cases. There is no convention bug and no
thin-book artifact. The open-proxy values are the market's real price —
recorded a median of **116 days before kickoff**. The loader is doing exactly
what its docstring says; the gate is reading a June futures price as if it
were a Tuesday opener.

That is worse than noise. Noise widens a confidence interval. This biases the
gate in the ship direction so hard that **a model with no betting edge at all
is credited with +2.28 points of mean capture** against a +0.3 threshold.

## 1. Mechanism

`odds_snapshot_loader._derive_open_close` takes the open as the earliest
pre-kickoff snapshot it can find for a game:

```python
first_ts = pre_kick["snapshot_ts"].min()
open_rows = pre_kick[pre_kick["snapshot_ts"] == first_ts]
```

Across all 321 committed snapshot files that minimum is not the opener of the
betting week. Capture is accumulated over a window nobody bets across:

| open-proxy horizon, 272 games | days before kickoff |
|---|---|
| min | 82.0 |
| median | **116.4** |
| mean | 120.8 |
| max | 165.3 |

The close is a real close — median **2.8 hours** before kickoff (max 15.5 h).
So `close − open` is approximately *the entire summer-to-gameday move*.

The capture arithmetic in `evaluate_line_capture` is correct, and both its
inputs are in the same sportsbook convention; `backtest_predictions.py:954`'s
negation to nflverse is correct too (the prior audit established this, and the
close reproduces `spread_line` to 0.23 pts MAD on the settled games, which is
only possible if home/away orientation and sign are right on both sides).
Nothing is mis-signed. The window is wrong.

## 2. Diagnosis per cause

Evidence base: 321 snapshot files (2026-06-12 → 2026-10-24), 108,066
spread-market rows, 272 games, 9 bookmakers, 321 distinct `snapshot_ts`. Of
the 272 games, **107** have an nflverse `spread_line` posted and **93** are
settled. (The other 165 are future fixtures with no nflverse line yet — not
join failures.)

| cause | games | verdict |
|---|---|---|
| (a) genuine large line move | **107 / 107** | all of it, including all 15 sign-crossers |
| (b) mixed sign convention | **0 / 107** | ruled out at book level and structurally |
| (c) thin-book artifact | **0 / 107** | depth is a confound of horizon, not a cause |

### (b) No mixed convention — 1 quote in 45,398

If any book or any snapshot row stored an away-signed or nflverse-signed line
in `home_spread`, that row would sit at roughly −1x the same-snapshot
consensus. Testing every quote where the consensus is at least 2 pts off pick
'em and at least 4 books are present:

| bookmaker | quotes | mean dev from consensus | mean abs dev | fits inverted sign |
|---|---|---|---|---|
| betmgm | 3,905 | −0.030 | 0.078 | 1 |
| betonlineag | 5,486 | +0.002 | 0.066 | 0 |
| betrivers | 5,448 | −0.030 | 0.141 | 0 |
| betus | 5,360 | +0.001 | 0.163 | 0 |
| bovada | 4,339 | −0.032 | 0.158 | 0 |
| draftkings | 5,658 | −0.057 | 0.156 | 0 |
| fanduel | 5,305 | −0.009 | 0.177 | 0 |
| lowvig | 5,486 | −0.001 | 0.062 | 0 |
| mybookieag | 4,411 | −0.042 | 0.119 | 0 |

**1 of 45,398 quotes** fits the inverted sign — a single betmgm price of +1.5
against a −2.5 four-book consensus on 2026-09-20. One stale or fat-fingered
number, not a convention.

This is also true structurally, which matters more than the statistic: open
and close are read from the same column of the same rows of the same files,
selected only by timestamp. No code path can sign-flip one and not the other.
`bronze_odds_api_ingestion.normalize_game` keys `home_spread` off the outcome
whose `name` equals the game's own `home_team`, so a book that listed the
away handicap would have to also mislabel the team.

### (c) Thin books are a confound of horizon, not a cause

The 1–2 book opens do have a bigger error — but they are also measured two
weeks further out:

| open book count | games | MAD vs nflverse | median days before kickoff |
|---|---|---|---|
| 1–2 books | 85 | 2.63 | 107.0 |
| 3+ books | 22 | 1.68 | 93.1 |

Hold the horizon fixed by taking each game's first snapshot inside 7 days
instead, and the gap vanishes and reverses, with both groups now at 8–9 books:

| open book count (at first-ever snapshot) | games | MAD with a ≤7-day open | median books |
|---|---|---|---|
| 1–2 books | 85 | **0.75** | 8 |
| 3+ books | 22 | **0.89** | 9 |

So book depth carries no explanatory power once the horizon is controlled.

The decisive test is corroboration: a thin quote that is stale, an outlier, or
pulled would be contradicted by the next snapshots. Comparing each game's open
against the median consensus over the following N days of snapshots:

| corroboration window | games with a window | dev > 0.5 pt | > 1.0 | > 1.5 | median dev |
|---|---|---|---|---|---|
| 3 days | 92 | 0 | 0 | 0 | **0.00** |
| 7 days | 100 | 1 | 0 | 0 | **0.00** |
| 10 days | 104 | 1 | 0 | 0 | **0.00** |
| 21 days | 106 | 1 | 0 | 0 | **0.00** |

**Zero games** have an open that the following weeks contradict by more than a
point, at any window. The median deviation is exactly zero. These are not bad
quotes — they are the summer market, and it held that level for weeks. The
same point from the other direction: replacing the open with the median of the
first 3 or first 5 snapshots, which would average away a single bad price,
moves the MAD not at all (2.432 → 2.439 / 2.435).

### (a) The sign-crossers are real, every one

All 15 "opposite sign fits better" games have corroborated opens — in 14 of 15
the following-window consensus is *identical* to the open, backed by up to 25
subsequent snapshots:

| wk | away@home | nflverse line | open (sb) | books | days out | corroborating median | n snaps | close (sb) |
|---|---|---|---|---|---|---|---|---|
| 4 | ARI@NYG | −2.5 | −7.0 | 2 | 114 | −7.0 | 23 | +2.5 |
| 6 | CAR@PHI | −3.0 | −6.5 | 2 | 124 | −6.5 | 3 | +3.0 |
| 5 | PHI@JAX | +7.5 | +1.5 | 5 | 121 | +1.5 | 24 | −8.0 |
| 5 | BAL@ATL | +3.5 | +4.5 | 2 | 117 | +4.5 | 7 | −3.0 |
| 4 | IND@WAS | −4.5 | −1.5 | 6 | 114 | −1.5 | 24 | +4.5 |
| 3 | PHI@CHI | −3.5 | −1.5 | 1 | 108 | −1.5 | 24 | +3.5 |
| 5 | DEN@LAC | −3.5 | −2.5 | 2 | 121 | −2.5 | 24 | +3.5 |
| 1 | GB@MIN | +1.5 | +1.5 | 9 | 93 | +1.0 | 24 | −2.0 |
| 6 | DAL@GB | −1.5 | −3.0 | 2 | 82 | −3.0 | 25 | −0.5 |
| 2 | CAR@ATL | −2.5 | −1.5 | 2 | 100 | −1.5 | 24 | +2.5 |
| 6 | NO@NYG | −1.5 | −2.5 | 2 | 117 | −2.5 | 1 | +0.5 |
| 6 | PIT@TB | −2.5 | −1.5 | 2 | 117 | −1.5 | 1 | +2.5 |
| 5 | CHI@GB | −1.5 | −3.0 | 1 | 117 | −3.0 | 7 | +1.5 |
| 3 | LA@DEN | +1.5 | +3.0 | 1 | 107 | +3.0 | 24 | +1.5 |
| 3 | MIN@TB | −1.5 | −1.5 | 2 | 107 | −1.5 | 24 | +1.0 |

wk4 ARI@NYG is the clearest: the Giants were a 7-point home favourite in June
and a 2.5-point dog by week 4 — a real 9.5-point repricing of a team's season.
Nothing to fix. It just is not CLV.

One presentational trap worth naming, since it cost time here: the prior
audit quotes wk1 GB@MIN as `open −1.5, close +2.0` while the brief quotes the
same game as `+1.5 / −2.0`. Both are right — the audit printed open and close
already negated into nflverse sign, the brief printed the raw sportsbook
values. Every table in this document uses the **raw sportsbook sign** for
`open`/`close` and the nflverse sign for `spread_line`, and says so in the
column header. Mixed-convention reporting is how a non-existent sign bug stays
plausible for a day.

## 3. Consequence for ELITE 2.4

### The gate cannot resolve its own threshold

Per-game capture magnitude is the open→close move. Its spread over the 93
settled games:

| open definition | mean abs move | sd(move) | SE at n=100 | SE at n=150 | min detectable effect, 80% power, n=100 |
|---|---|---|---|---|---|
| **current (first-ever snapshot)** | 2.33 | **3.20** | **0.320** | 0.261 | **0.896** |
| ≤30 days | 1.91 | 2.84 | 0.283 | 0.231 | 0.794 |
| ≤14 days | 1.38 | 2.17 | 0.217 | 0.177 | 0.606 |
| ≤7 days | 0.76 | 1.32 | 0.132 | 0.108 | 0.370 |
| ≤3 days | 0.34 | 0.55 | 0.055 | 0.045 | 0.153 |

The standard error of the mean at n=100 is **0.320 pts — larger than the whole
+0.3 threshold**. A printed +0.3 would carry a 95% interval of roughly
[−0.33, +0.93]. The kill criterion is equally blind: a genuine +0.3 edge would
print at or below zero a substantial share of the time at n=150. On variance
alone the gate is underpowered by about 3x.

### Worse: it is biased toward ship, and cannot fail

Variance is not the main problem. `backtest_predictions.py:961` assigns the
pick side *against the open proxy*:

```python
has_open & (joined["predicted_margin"] > -joined["open_spread"])
```

So the harness pretends we bet in June at the June price, using a model run in
October. Any model that is merely better informed than a four-month-old line
will systematically pick the side the market later moved toward — and be paid
for the market's own learning.

Simulated against the real 93 settled games with a model that has **zero
genuine edge** — it knows the week-of consensus line and nothing the close
does not already know, so it cannot possibly beat the close — plus noise of sd
`s` (4,000 draws each):

| model noise sd | mean capture, current open | mean capture, ≤7-day open |
|---|---|---|
| 0 (knows the week-of line exactly) | **+2.277** | +0.707 |
| 1 pt | +2.182 [+2.07, +2.27] | +0.551 [+0.45, +0.64] |
| 2 pt | +1.960 [+1.74, +2.14] | +0.426 [+0.27, +0.56] |
| 3 pt | +1.716 [+1.38, +2.00] | +0.349 [+0.16, +0.51] |
| 5 pt | +1.310 [+0.84, +1.73] | +0.243 [+0.01, +0.44] |
| 8 pt | +0.923 [+0.36, +1.42] | +0.163 [−0.10, +0.38] |

A model with **no edge and 8 points of error** — worse than reading the line
off the board — clears the +0.3 gate at +0.92. The gate as wired is not a test
the model can fail. Had week 10 been ruled on it, it would have shipped.

Note the ≤7-day column: narrowing the window shrinks the bias 3x but does not
remove it (+0.35 at a realistic 3-pt model error, still above threshold). The
bias is a property of **assigning the pick against the open** rather than
against the line we actually bet, and it needs the pick rule fixed, not only
the window.

### What is *not* established here

- The sign bias of the open proxy itself is small: mean signed error **+0.18
  pts** on the settled games, and always-home capture is −0.105. The proxy
  does not lean home or away in aggregate. The ship bias above comes from the
  pick-side assignment interacting with the horizon, not from a skewed proxy.
- **No actual capture number was computed.** Only week 7's board is committed
  (`predictions_20261020_092514.parquet`); weeks 1–6 would need regenerating,
  which this audit did not do. The simulation bounds what the metric *can*
  print; it does not predict what it *will* print.
- nflverse `spread_line` is used as the week-of reference. Its provenance and
  exact timing are not documented, so it is a proxy, not ground truth — it
  just happens to match our own close to 0.23 pts. The horizon conclusion does
  not rest on it: `sd(close − open) = 3.20` is computed from our snapshots
  alone.
- The simulation's "zero-edge model" is `spread_line + noise`. A real model is
  not that. It is a bound, not a forecast.

## 4. No code was changed

`src/odds_snapshot_loader.py` has no bug. It documents its open as "the first
snapshot captured for each game" and that is precisely what it returns; the
sign-convention warning in its module docstring is accurate and load-bearing.
The defect is that the gate and `backtest_predictions.py` treat that value as
a betting-week opener. Those are policy and harness decisions, not loader
decisions, and `backtest_predictions.py` is owned elsewhere this session.

One candidate defect was checked and rejected rather than "hardened": the
loader counts `n_books_open` as `open_rows[line_col].notna().sum()`, i.e. rows
rather than distinct bookmakers, which would inflate on a duplicate
(game, snapshot, bookmaker) row. There are **0 such duplicates in 108,066
rows**, 321 distinct `snapshot_ts` across 321 files, and **0 games** where the
open row count differs from the distinct book count. Fixing it would be a
change with no test that could fail for the right reason on real data, which
is the trap this body of work keeps falling into. Left alone.

Consequently there is no new test either: the brief made that conditional on
finding a bug, and no assertion written today would have failed before a
change that is not needed.

## 5. Proposed rule — not implemented, because it can invalidate the gate

Two changes are needed and both alter what ELITE 2.4 means, so they are the
user's call.

**(i) Move the open to the betting week.** The week-7 board was generated
2026-10-20, with the week's first kickoff on 10-22 — picks are made roughly
2–5 days out. An open proxy should be the price available then.

**Sample cost: zero.** The capture cron runs about twice a day, so every
settled game has deep coverage near kickoff:

| horizon | settled games with ≥1 snapshot | with ≥2 | median snapshots in window | median books | MAD vs nflverse |
|---|---|---|---|---|---|
| ≤14 days | 93 / 93 | 93 / 93 | 28 | 5 | 1.38 |
| ≤7 days | **93 / 93** | 93 / 93 | 16 | 8 | **0.80** |
| ≤5 days | 93 / 93 | 93 / 93 | 12 | 9 | 0.59 |
| ≤3 days | 93 / 93 | 93 / 93 | 8 | 9 | 0.44 |

No horizon down to 1 day loses a single game. n is set by the schedule —
**150 regular-season games through week 10** — so the n≥100 and n≥150 bars are
met at any horizon. A minimum-book-depth rule is therefore unnecessary: at
≤7 days the median open already has 8 of 9 books, and depth was never the
problem. Recommended: **≤7 days**, as the widest window that is still the
betting week.

**(ii) The pick must be the pick we made.** Capture has to compare the line we
actually took against the close, with the pick decided from the same board we
published. Keeping `predicted_margin > -open_spread` with any window leaves
the ship bias in place (+0.35 at ≤7 days on a 3-pt-error no-edge model). This
is the change that matters; the window alone is not sufficient.

**The threshold then has to be restated, and it is not obviously satisfiable.**
+0.3 was presumably written against a wide window. Inside 7 days the *entire*
mean absolute move is 0.76 pts, so +0.3 mean capture means harvesting 39% of
all available movement — a demanding but coherent bar, resolvable at
MDE 0.370 (n=100) / 0.302 (n=150), i.e. right at the edge. Inside 3 days the
mean move is 0.34 and +0.3 would require capturing ~90% of it, which is not a
real target. **A +0.3 threshold and a window wide enough to contain 0.3 points
of movement cannot both hold at n≈150.** Either the threshold drops to roughly
+0.15 with a ≤7-day window, or the gate slips past week 10 to accumulate n.
That tradeoff is the decision to take, and it is not taken here.

## Ranked follow-ups

1. **Do not rule on ELITE 2.4 at week 10 as currently wired.** A no-edge model
   scores +2.28 against a +0.3 bar. A ship verdict would carry no information
   and a kill verdict is nearly unreachable. This supersedes the "validate the
   open proxy" item in `CLV_PICK_RULE_AUDIT_2026_10_24.md` — it is validated,
   and it fails.
2. **Fix the pick side before the window** (`backtest_predictions.py:954-970`,
   owned elsewhere): capture must be measured on the line the published board
   was priced against, not on a line back-fitted from the open. The window fix
   alone leaves a ship bias above threshold.
3. **Add a horizon argument to the open proxy** (`load_open_close_lines`, e.g.
   `open_within_days: float | None`) once (2) is settled, defaulting to the
   current behaviour so nothing changes silently. Zero sample loss at 7 days;
   MAD 2.38 → 0.80.
4. **Restate the gate** — threshold, window, and n together, since the three
   are not independent. +0.3 at n≥150 is only coherent with a ≥7-day window,
   and only just.
5. **Record what the current proxy is good for.** A corroborated,
   9-book-median, 116-days-out line is a genuine artefact: a summer futures
   price. It is a legitimate *feature* (preseason market prior, market-drift
   target) and a legitimate thing to study. It is not an opener.

## Method notes

- Everything here reads the committed Bronze snapshots directly
  (`data/bronze/odds_api/snapshots/season=2026/`, 321 files) and the committed
  schedule (`data/bronze/schedules/season=2026/`). No regeneration, no model,
  no network.
- Per-book sign testing deliberately restricts to consensus |line| ≥ 2 and ≥ 4
  books, because near pick 'em an inverted sign is indistinguishable from a
  normal quote. That is why it is stated as "1 of 45,398" rather than over all
  108,066 rows.
- The corroboration threshold (1.0 pt) was checked at 0.5 / 1.5 / 2.0 and over
  3 / 7 / 10 / 21-day windows. The count is 0 in every cell but one. The
  conclusion does not depend on the cut.
- A merge on `(home, away)` leaves 165 of 272 games without a `spread_line`.
  Those are unplayed fixtures nflverse has not priced, not join failures — all
  93 settled games match. Mistaking that for a join failure was this audit's
  one wrong turn, caught by noticing the settled count was unaffected.
