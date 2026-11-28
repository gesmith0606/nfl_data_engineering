# Full model assessment — 2026 season to date (written 2026-10-21)

Scope: every model surface, measured on live 2026 data where data exists and
explicitly marked UNASSESSABLE where it does not. Companion to
`SEASON_2026_MIDSEASON_RETRO.md`, which covers the QB regression and the two
calibration levers shipped earlier the same day.

Population unless stated: half-PPR, QB/RB/WR/TE, consensus>=5, weeks 3-6
(the canonical window), n=633 matched player-weeks. Boards read are the
published Gold boards; MAE is always against **actuals**.

## Scoreboard

| surface | 2026 verdict | evidence |
|---|---|---|
| Weekly fantasy MAE | **behind consensus**, +0.093 after this session's levers (was +0.169) | w3-6, n=633 |
| Weekly fantasy ordering | **QB badly behind, others at parity or ahead** | top-N hit rate below |
| Floor/ceiling bands | **BROKEN — 29.8% coverage vs ~80% target**; fixed this session to 83.2% | n=1,757 |
| Graph features | **inert; contributes nothing** | A/B below |
| Game predictions (ATS/O-U) | **MEASURED 2026-10-23: LOSING** — ATS 47.1% / -10.0% ROI, O/U 44.1% / -15.8%, break-even 52.38%; **no CLV evidence** (the "+0.37 CLV" first listed here was the spread edge, retracted 2026-10-24) | 93 settled games |
| PPR / Standard | **UNASSESSABLE — not produced weekly** | only `projections_half_ppr` |
| Kickers / DST | **UNASSESSABLE — not on the weekly board** | positions are QB/RB/WR/TE only |
| Rookies | thin and under-projected; flag stops after week 2 | n=43 flagged rows |

### Top-N hit rate (the start/sit metric), w3-6

| pos | N | baseline | after the shipped QB anchor | Sleeper |
|---|---|---|---|---|
| QB | 12 | **45.8%** | **60.4%** | 64.6% |
| TE | 12 | 56.3% | 56.3% | 52.1% |
| RB | 24 | 70.8% | 70.8% | 68.8% |
| WR | 24 | 57.3% | 57.3% | 56.2% |

This is the most useful number in the whole assessment. QB was picking roughly
half of the correct top 12 while consensus picked two thirds — a far more
practically damaging gap than the +0.63 MAE implied. The shipped QB anchor
recovers most of it (+14.6pp), which is a better justification for that lever
than its 0.035 MAE improvement.

## Finding 1 — floor/ceiling bands were meaningless (FIXED)

Coverage of the published band over 2026 w1-6 (n=1,757, all rows with a live
projection):

| pos | coverage | mean width | below floor | above ceiling |
|---|---|---|---|---|
| QB | 60.9% | 14.6 | 19.0% | 20.1% |
| RB | 32.9% | 6.1 | **40.7%** | 26.4% |
| WR | 24.8% | 4.4 | **45.4%** | 29.8% |
| TE | 20.9% | 3.4 | **51.1%** | 28.1% |
| **all** | **29.8%** | | | |

Two causes:

1. The fallback band is **multiplicative and symmetric** —
   `_FLOOR_CEILING_MULT` gives `floor = pts * (1 - m)`, m = 0.35-0.45. A 4-pt
   TE gets +/-1.4 when its real residual spread is -5.3/+6.5. Width collapses
   exactly where most of the board sits.
2. Fantasy residuals are **asymmetric** — far more actuals fall below the
   floor than above the ceiling, because scoring is right-skewed off a hard
   zero. Only QB was roughly centred.

The band's shape requirement was measured, not assumed: residual spread
correlates with projection size for RB/WR/TE (+0.50/+0.43/+0.45) but not QB
(+0.02), and width/projection falls from ~3.4x in the 0-4pt tier to ~1.2x at
16+. So neither a purely additive nor a purely multiplicative band fits.

**Shipped:** `src/band_calibration.py` — per-position residual-quantile lines
`floor = p + (a_lo + b_lo*p)`, `ceiling = p + (a_hi + b_hi*p)`, refitted from
the season's own completed weeks (leak-free, no pre-trained model), clamped to
`0 <= floor <= p <= ceiling`. Default-ON weekly, `--no-band-calibration` to
opt out. Walk-forward (fit on weeks < W, score week W):

| week | old | new |
|---|---|---|
| 3 | 29.0% | 82.8% |
| 4 | 34.6% | 84.1% |
| 5 | 30.5% | 82.1% |
| 6 | 27.9% | 83.7% |
| **pooled** | **30.6%** | **83.2%** |

Per position on held-out weeks: QB 85.3%, RB 80.7%, WR 84.3%, TE 83.8%.
Side effect: it also repaired 20 of the 21 anchor-induced band violations
noted in the retro, because it rewrites the band from the final point estimate.

## Finding 2 — graph features contribute nothing (do not invest further)

Three independent reasons, in increasing order of severity:

1. **They were never shipped.** `data/silver/graph_features/` stopped at
   season=2025. The weekly workflow computes them every run, but the commit
   step staged only gold/projections, projections_shadow, bronze weekly,
   bronze snaps and gold/predictions — never `data/silver/graph_features/`.
   Every runner computed 2026 features and threw them away. Same class as
   TD-08/09/10, but the casualty is model *inputs*, so it failed silently.
   **Fixed** (the commit step now stages it; the `.gitignore` allowlist
   already existed).
2. **The ordering nudge can never fire for the week being projected.**
   `ranking_score` merges graph signals on exact `(player_id, season, week)`.
   Week W's graph features derive from week W's play-by-play, which does not
   exist until the games are played. The live week-7 run confirms it:
   `apply_ranking_scores: nudged 0 / 376 players`. So in production this lever
   has always been a structural no-op, independent of finding 1.
3. **Even retrospectively, the signal adds nothing.** With 2026 features
   computed after the fact (56,083 rows, weeks 1-6) the nudge fires on 237 of
   633 eval rows and changes ordering by:

   | pos | rho (points) | rho (graph-nudged) | delta | hit rate |
   |---|---|---|---|---|
   | QB | 0.207 | 0.207 | +0.000 | 45.8% -> 45.8% |
   | TE | 0.233 | 0.233 | +0.000 | 56.3% -> 56.3% |
   | RB | 0.484 | 0.484 | +0.000 | 70.8% -> 70.8% |
   | WR | 0.327 | 0.326 | **-0.001** | 57.3% -> **56.2%** |

Also worth recording: **participation data stops after 2025.** nflverse
returns no participation columns for 2026 (`available: ['game_id','play_id']`),
so the participation-derived features (WR-CB matchup, route participation,
offense/defense edges) cannot be computed for this season at all. That is an
upstream gap, not a pipeline bug, and it is permanent unless another source is
found.

**Recommendation:** treat the graph programme as parked. The commit-gap fix is
worth keeping because it costs nothing and makes future evaluation possible,
but `USE_RANKING_SCORE` earns nothing and is mildly negative for WR — a
candidate for switching off. Every published graph result (UC1/UC2/UC3, the
39->66 feature expansion) was measured on 2016-2025 and has no 2026 support.

## Finding 3 — the measurement loop did not exist (FIXED)

`output/grading/` was gitignored, so the Tuesday cron's grading reports only
ever existed as CI artifacts and the season-to-date table was rebuilt from
nothing each week. **No 2026 grading report existed at all** until this
session generated w1-6 by hand. That is the direct cause of a week-3
regression surfacing in week 7.

**Fixed:** `output/grading/` is now tracked and the weekly workflow stages it.

## Finding 4 — the residual models are not running as designed

The WR residual model logs `No matching features for WR residual model;
returning heuristic` on every week of a 2026 backtest — **including after 2026
graph features were computed**, so this is not (only) the graph gap. The WR/TE
Ridge hybrid is a headline v4.1/v4.3 ship and it is silently degrading to the
heuristic. Not diagnosed further here; it needs its own session.

Related: `projection_source` is `hybrid` on every row of every board. That is
in fact *accurate* about the route taken — the router promotes all four
positions to hybrid — but it says nothing about whether the correction
actually applied, which is why the WR secondary-blend fallback stayed
invisible for two months. **FIXED 2026-10-23**: `apply_residual_correction`
now stamps `residual_correction_applied`, recording the outcome rather than
the intent. Both fallback returns are stamped False.

## Finding 5 — smaller defects

- ~~**Anchor coverage erosion**~~ **NOT A DEFECT — corrected 2026-10-23.**
  Raw coverage did fall 93% -> 79% over w3-6, but that is Sleeper's published
  slate shrinking (401 skill rows in w3 to 337 by w6) while our board holds
  ~340. Coverage over rows projected >= 5 pts held at ~**99%**: just 15
  unmatched startables across five weeks, and every one was verified **absent
  from Sleeper's feed** that week, not mis-joined. The real defect was the
  guard's denominator. Fixed: startable-pool coverage is now reported and
  warned on below 90%. See `ANCHOR_COVERAGE_2026_10_23.md`. The claim above
  that "a load-bearing lever quietly stopped firing on one row in five" was
  wrong.
- **Bye-week rows carry non-zero projections** — **FIXED 2026-10-23.** The
  injury invariant covered `injury_multiplier == 0` but not bye rows (a player
  on bye is Active, just not playing). A bye invariant now runs alongside it,
  after every blend that can revive a row, and zeroes the band as well as the
  points. Live w7: 16 bye rows re-zeroed, all 51 now at 0.00.
- **Abbreviated-name collisions are real**: the w6 board carries two distinct
  `J.Daniels` QBs (00-0039910 at 25.22, 00-0041251 at 20.16), plus
  `K.Johnson`, `K.Williams`, `M.Evans` and `T.Johnson` pairs across positions.
  Distinct `player_id`s, so no duplicate-row bug — but the lineup/waiver tools
  join on names in places, and a backup projected at 20.16 is also a symptom
  of the depth-chart gating gap. Relatedly **FIXED 2026-10-23**: the weekly
  sanity checker's "WEEKLY STAR MISSING" warnings were a name-format mismatch
  (consensus "Drake Maye" vs our board's "D.Maye"), firing for every star
  every week. An abbreviation-tolerant fallback key takes w7 from 11 warnings
  to **0** while keeping distinct players distinct.
- **A team-level sanity check fires on every team every week** —
  **FIXED 2026-10-23.** It compared a team's *summed fantasy points* against
  its *implied game score*. `projection_engine._IMPLIED_TO_FANTASY_MULT`
  (half-PPR 3.36) already held the calibrated conversion; the check simply
  never applied it. Now converts the implied total into a fantasy budget
  first, and takes `scoring_format`. Live w7 warnings: **32 -> 0**, while a
  genuinely inflated team still trips it.
- **`ranking_score` pre-injury leak**: the w6 board had Lamar Jackson at
  `projected_points` 0.00 and `ranking_score` 18.53 (rank 13 among QBs).
  Already fixed upstream by 248e0c81, which placed the injury invariant before
  `apply_ranking_scores`; recorded here because the published boards still
  carry it.

## Shipped this session

| change | effect |
|---|---|
| QB Sleeper anchor (w=0.5) | QB hit rate 45.8% -> 60.4%, rho 0.207 -> 0.350, MAE -0.035 |
| Dispersion shrink (k=0.8) | MAE -0.050; confined to the >=5pt pool so board totals stay flat |
| **Band calibration** | **coverage 29.8% -> 83.2%** |
| Graph features staged in CI | makes graph evaluation possible at all |
| Grading reports tracked | makes regressions visible in week 3, not week 7 |

Combined MAE: 5.440 -> 5.364, gap to Sleeper +0.169 -> +0.093.

## Ranked next steps

1. **Diagnose the WR/TE residual fallback** (finding 4) — a shipped model is
   not running. Highest value, entirely unknown cost.
2. ~~**Get game predictions evaluated.**~~ **DONE 2026-10-23 — and it is
   losing.** Rebuilt the 2026 team-side Silver chain (none of it existed),
   generated weeks 1-6 and backtested: **ATS 41-46-6 (47.1%, -10.0% ROI), O/U
   41-52 (44.1%, -15.8%)** against a 52.38% break-even. ~~CLV is the one
   positive: +0.37 mean, 52.7% beating the close, ordered by tier (low 41.3%,
   medium 68.0%, high 59.1%) — our numbers anticipate line movement while our
   side selection loses.~~ **RETRACTED 2026-10-24: that was the spread edge
   (`predicted_margin - spread_line`, closing line only), i.e. a home lean, not
   CLV; home/favourites covered 39 of 87 this season. The 2026 O/U record also
   reproduces from the Vegas total line alone** — see
   `CLV_PICK_RULE_AUDIT_2026_10_24.md`. n=93 is small (~5.2pp SE) and the predictions were
   generated retrospectively, so this is *no evidence of edge* rather than
   proof of a broken model. **Getting here first required fixing the harness,
   which reported 75.7% O/U accuracy and +44.6% ROI by scoring 179 unplayed
   fixtures as wins** (`NaN > x` is `False`, not `NaN`). See
   `PREDICTION_BACKTEST_PHANTOM_GAMES.md`. Still open: ~~understand positive CLV
   alongside losing picks~~ (premise false); re-add `--check-predictions` to the sanity gate.
3. **Fix the anchor coverage erosion** — restores a lever already paid for.
4. **Decide the graph programme.** On this evidence, park it.
5. ~~TE anchor weight 0.5 -> 0.75~~ **REJECTED 2026-10-22.** The -0.18 figure
   came from a sweep that double-applied the anchor; measured properly it is
   4.75 -> 4.80 matched MAE (hit rate 0.542 -> 0.563). A wash, not a win.
6. `--early-season-prior`: live verdict is ship for QB/WR/TE, not RB
   (-0.053 overall); its window is weeks 3-6, so it is next-season value.
7. Bye-week zeroing, the units-bug sanity check, and `projection_source`
   being uninformative.

## Week 7 forward check (graded 2026-10-27)

First unseen week for the three levers shipped 2026-10-22 (PR #134). Graded
board: `data/gold/projections/season=2026/week=7/projections_half_ppr_20261022_221655.parquet`
(commit `0d919e74`). It is the file the harness picked (lexically last in the
directory) and it carries all three levers: QB `sleeper_anchor_flag` 29/35,
`dispersion_shrink_flag` 164, `band_calibration_flag` 341. Actuals ingested
2026-10-27, all 28 teams / 14 games present. Half-PPR, consensus>=5.

**Timing caveat.** The board was written at 22:16 ET Thursday, after NE @ CHI
kicked off (20:15). The engine reads weeks 1-6 only, so no week-7 outcome can
leak in; the exposure is that the 24 NE/CHI rows saw an injury report from
after their kickoff. Every headline number is shown both ways below.

### Scoreboard (the shipped board)

| metric | w3-6 with levers | w7, all rows | w7, excl. NE/CHI | Sleeper w7 (all / excl.) |
|---|---|---|---|---|
| matched n | 633 | 140 | 128 | |
| overall MAE gap vs Sleeper | +0.093 | **+0.127** | **+0.102** | |
| QB MAE gap | (5.582 MAE) | -0.091 (5.434) | -0.037 (5.517) | |
| RB / WR / TE gap | | +0.408 / +0.100 / +0.004 | +0.317 / +0.109 / -0.063 | |
| QB Spearman | 0.350 | 0.512 | 0.428 | 0.498 / 0.431 |
| QB top-12 hit rate | 60.4% | 58.3% | 58.3% | 50.0% / 58.3% |
| band coverage (live proj with an actual) | 83.2% | **79.7%** (n=271) | 80.8% (n=250) | |
| coverage QB / RB / WR / TE | 85 / 81 / 84 / 84 | 70.0 / 80.3 / 81.0 / 81.4 | 67.9 / 81.7 / 82.2 / 83.6 | |
| below floor / above ceiling | | 8.1% / 12.2% | 7.6% / 11.6% | |

Harness output: `output/grading/season=2026/week=07_report.md`. Its cumulative
w3-7 table (overall gap +0.161, QB +0.491) grades the boards that were
*served*: w3-6 are pre-lever boards (no flag columns), so that table is not a
lever measurement.

### Counterfactuals (shadow boards)

Re-ran the generator (`--ml`, as the cron does) into
`projections_shadow/w7*`: a control with all levers on, then
`--no-sleeper-anchor`, `--no-dispersion-shrink`, `--no-band-calibration`. The
CLI has no QB-only anchor switch (`--no-sleeper-anchor` drops all four
positions), so the QB-anchor counterfactual is the control board with its QB
rows swapped for the no-anchor board's QB rows. That is valid because the
anchor, the shrink and the band fit all work per position pool; nothing was
hand-rolled.

Lever effect = MAE with the lever minus MAE without it (negative = lever
helps), paired bootstrap SE over the 140 matched rows:

| lever | all rows | excl. NE/CHI | SE (all rows) | w3-6 claim |
|---|---|---|---|---|
| Sleeper anchor, all 4 positions | -0.041 | -0.043 | 0.081 | (RB/TE/WR shipped earlier) |
| QB anchor only, overall MAE | **+0.027** | **+0.065** | 0.026 | -0.035 |
| QB anchor only, QB MAE | **+0.138** | **+0.185** | 0.132 | -0.326 (5.908 -> 5.582) |
| QB anchor, QB Spearman / top-12 | 0.454 vs 0.460 off; 50.0% vs 58.3% off | 0.351 vs 0.359; 50.0% vs 66.7% | | +0.143 rho / +14.6pp |
| Dispersion shrink, overall | **+0.029** | +0.014 | 0.044 | -0.050 |
| Dispersion shrink, QB / RB / WR / TE gap | +0.120 / -0.087 / +0.079 / +0.016 | | QB 0.079 | |
| Band calibration, coverage | 81.2% vs 28.9% off | 83.1% vs 30.1% off | | 29.8% -> 83.2% |
| Band calibration, MAE | 0.000 (touches bands only) | | | |

**Caveat on the counterfactuals: the control does not reproduce the shipped
board.** The control's overall gap is +0.178 against the shipped board's
+0.127, QB +0.142 against -0.091. Three things drifted between 2026-10-22 and
the rerun: (1) the local injury report now runs to 2026-10-24, which zeroes
about 16 more players who were Active on the shipped board (M.Evans, R.Rice,
T.Warren, D.Montgomery...); board total falls 2119.7 -> 1887.0. (2) b9e41c20
(bye-week zeroing and others) landed after the board was made. (3) The local
run's hybrid models ran with most features imputed (QB lgb 2/20, WR ridge 6/60,
"No usage data for season 2026") where CI's week-8 run had 20/20 and 60/60.
That puts the QB level about 1.1 pts lower (mean of QB rows >=5 pts: 14.87
against 15.98). So the lever deltas are measured against a degraded replica.
They are the right tool for comparing levers with each other, but they are not
a precise replay of production.

### Verdicts

- **Band calibration: held up.** 79.7% overall (80.8% excluding NE/CHI)
  against the ~80% target, down from 83.2% walk-forward, which is the expected
  shrinkage on the first unseen week. One weak spot: **QB covered only 70%**
  (n of about 30), and the misses lean high (12% above the ceiling against 8%
  below the floor). Watch it for two more weeks before widening QB.
- **QB Sleeper anchor: didn't hold up on week 7. Too noisy to call, and the
  direction is wrong.** The shipped board's QB numbers look good (gap -0.091,
  rho 0.512, beat Sleeper's top-12), but the counterfactual says the anchor did
  not cause them. The same board without the QB anchor was better on all three
  QB metrics: MAE -0.138, rho +0.006, top-12 +1 QB. Excluding NE/CHI it was
  better again (+2 QBs). The effect is about one SE on n=27, so this is not
  evidence of harm. It is the first contradiction of the w3-6 result, though,
  and Sleeper's own week-7 QB top-12 (50%) was worse than ours unanchored. Keep
  shipping it, and re-grade the QB-only splice after weeks 8-9.
- **Dispersion shrink: didn't hold up on week 7, within noise.** +0.029 overall
  against the claimed -0.050 (SE 0.044). It helped RB (-0.087) and hurt WR
  (+0.079) and QB (+0.120). The w3-6 gain was pooled across positions; if the
  WR/QB pattern repeats in week 8, the per-position k needs revisiting.
- **The anchor overall (all four positions) still helps**: -0.041, carried by
  RB and TE. WR's anchor was slightly negative this week.

### Week-8 board (first fully clean forward test): NOT PUBLISHED

The 2026-10-27 09:21 UTC weekly-pipeline run (40480134979) built a week-8
board from main with all three levers active: QB anchor 28/36 rows (startable
coverage 93%), dispersion shrink on 154 rows, band calibration on all four
positions, hybrid models at full feature coverage. **The sanity gate then
failed it and the commit step was skipped**, so there is no week-8 board on
main or locally. Issue #162 is open. The failures: `Lamar Jackson` at 0.00 pts
(QB#30) and `Tyler Warren` at TE#70. Both are on the engine's "returning from a
missed game" list, and at 09:28 Tuesday there were 0 official week-8 injury
verdicts against 559 live Sleeper designations. The likely cause is a stale
last-game Out tag zeroing them. Unverified: the board artifact was not
inspected. No concurrent session has written a pre-lever week-8 board, because
nothing exists there at all. A clean week-8 board still needs to be generated
before Thursday's kickoff, or the week-8 forward test is lost.
