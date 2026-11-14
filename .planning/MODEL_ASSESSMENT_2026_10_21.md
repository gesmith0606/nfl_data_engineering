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
