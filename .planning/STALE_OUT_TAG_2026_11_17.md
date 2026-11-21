# Stale Sleeper "Out" tag on the Tuesday board - 2026-11-17

The Tuesday cron zeroed every player Sleeper tags `Out`. That tag is the LAST game's ruling, so the
2026 week-11 board had Brock Bowers (consensus TE2, 12.1) at 0 and the deploy gate
(`WEEKLY STAR RANK (TE): 'Brock Bowers' ... TE#71`) failed, the same shape as weeks 8, 9 and 10
(Warren, Lamar, Evans). This documents what the data says about those tags and the rule that
follows from it.

## 1. Validation (done before any code)

Two populations, because the Tuesday board's own zeros only exist for weeks 9-10 (the live-Sleeper
fallback shipped after week 7; the week-8 Tuesday board is not in the repo):

* **A - official week W-1 status Out** (the population the brief named): skill players (QB/RB/WR/TE)
  officially Out in week W-1, weeks W = 2..10, split by the EARLIEST consensus snapshot captured for
  week W (the Sunday capture - exactly what a Tuesday build can see). n = 184.
* **B - the rows the Tuesday boards actually zeroed**: skill rows with `injury_multiplier == 0` on the
  Tuesday builds that survive (week 9 20261103_202429, week 10 20261110_203619; no official week-W
  report exists on a Tuesday, so every zero is a live Sleeper tag). n = 40.

Outcome = a player-weekly row in week W; points = half-PPR actual. "Consensus" = Sleeper half-PPR.

| population | group | n | played week W | mean actual (zeros incl.) | mean consensus |
|---|---|---|---|---|---|
| A | consensus >= 5 | 71 | 26 (37%) | 3.58 | 10.89 |
| A | consensus < 5 / no row | 113 | 21 (19%) | 0.71 | 1.06 |
| B | consensus >= 5 | 22 | 10 (45%) | 5.41 | 11.06 |
| B | consensus < 5 / no row | 18 | 2 (11%) | 0.19 | 1.33 |
| A+B, deduplicated | consensus >= 5 | **86** | **33 (38%, 95% CI 29-49%)** | **4.2** | **10.9** |

Roster designations (IR/PUP/NFI/Sus) cannot appear in either population: the official report does not
list them and the Tuesday zeros cannot be split by tag after the fact. The rule keeps them at zero by
construction rather than by evidence (see 2).

What does and does not separate the 38% who played from the 62% who did not (consensus >= 5, A):

| cut | n | played |
|---|---|---|
| out streak 1 / 2 / 3 / 4+ games | 42 / 21 / 6 / 2 | 26% / 52% / 50% / 50% |
| practice status on the W-1 report: DNP / limited / full | 61 / 8 / 2 | 33% / 50% / 100% |
| position QB / RB / WR / TE | 14 / 26 / 27 / 4 | 36% / 19% / 48% / 75% |
| played last week (W-1 stat line) yes / no | 9 / 77 | 33% / 39% |

None of these is a usable discriminator at this sample size (the streak cut runs the opposite way to the
intuition, positions overlap, n is single digits in most cells). A single multiplier is what the data
supports; no per-position or per-streak parameters are fitted.

### What each candidate projection costs against actuals (A+B, consensus >= 5, n = 86)

| projection for a stale-Out, consensus >= 5 player | MAE | RMSE | mean error |
|---|---|---|---|
| zero (shipped) | 4.12 | 9.05 | -4.12 |
| 0.35 x consensus | 5.55 | 8.03 | -0.30 |
| **0.40 x consensus** | 5.79 | 8.05 | +0.24 |
| 0.50 x consensus (= Doubtful) | 6.32 | 8.21 | +1.34 |
| **full consensus (keep the projection)** | **9.50** | **11.06** | **+6.79** |

MSE-optimal multiplier on the consensus: 0.35 (bootstrap 95% CI 0.20-0.53). Population A alone 0.32,
population B alone 0.42.

**The proposal "keep his projection when consensus >= threshold" is not supported.** It is wrong by
+6.8 points a player (the zero is wrong by -4.1) and is 2.3x worse than the zero on MAE. The data supports a
play-probability discount of ~0.4, which is unbiased and cuts RMSE 11% against the zero. It does NOT beat
the zero on MAE, because the outcome is bimodal and the majority of these players do not play: the median
outcome is 0. So the choice between the discount and the zero is a choice of objective, stated below.

## 2. The rule

A Sleeper tag becomes `Out (unconfirmed)` at multiplier **0.4** instead of 0 when ALL of:

1. the row came from Sleeper's live tag, not the official report (official verdicts never change);
2. the tag is a per-game `OUT`, not a roster designation (IR, PUP, NFI, Sus stay zero);
3. the official report has fewer than 40 graded rows for the target week. Every 2026 snapshot from
   Saturday morning carries 121-181 graded rows (Friday's report); Tuesday to Friday carries 0-15, so
   the 40 sits in an empty gap;
4. Sleeper's consensus for the week still projects the player >= 5 (below it 11-19% played and the zero
   costs 0.2-0.7 pts a player);
5. the player is QB/RB/WR/TE (the consensus frame the rule reads carries no K or DST).

`Doubtful` (0.5) and `Questionable` (0.85) tags are untouched; the 0.4 sits next to the 0.5 already used
for Doubtful. The board gets a boolean `injury_unconfirmed` and the status text `Out (unconfirmed)`
(`injury_status` is VARCHAR(30) in the DB; the frontend renders any non-Active string as injured).
`sunday_projection_refresh` can undo a 0.4 and re-apply the official verdict; it cannot do that for a zero
(its "asymmetry" case), so this also stops a cleared player from being stuck at 0 on that path.

The consensus is the week's Sleeper Bronze snapshot the Sleeper anchor already loads
(`_load_sleeper_week`); no new loader. Behaviour on Friday evening onward is unchanged: the Saturday and
Sunday builds, which the 169-of-169 check was measured on, have >= 120 graded rows and never soften.

## 3. Limits, stated plainly

* The Tuesday boards with live-tag zeros are two weeks (n = 22 with consensus >= 5). Population A
  (n = 71) is a proxy: "officially Out last week" is not the same set as "tagged Out on Tuesday" (it misses
  players hurt in the game itself and includes players whose tag Sleeper had already cleared). The two
  agree within noise (37% vs 45% played) which is why the multiplier is a pooled 0.4 and not a tuned one.
* Wednesday to Friday-morning builds also soften (fewer than 40 graded rows). The only evidence is from
  Tuesday builds; a tag updated by Thursday's practice report may be more reliable than a Tuesday one. The
  automated cron is Tuesday-only, so this is a manual-rebuild exposure.
* Floors and ceilings on a softened row scale with the point (0.4x), so the band understates the real
  spread (0 to full). Not changed here.
* MAE is the scorecard's metric and the zero wins it on this subgroup. Softening ~10 rows a week at 0.4
  instead of 0 costs ~1.7 pts MAE on those rows (~0.07 on the 260 consensus >= 5 board rows) on a
  Tuesday board. The graded board is the Saturday/Sunday build, which the rule does not touch, so the
  scorecard is unaffected; the cost lands only on the Tuesday-to-Friday view.

## 4. Week-11 rebuild and the deploy gate

Replay: the runner's ingest and Silver chain re-run in a sandbox copy of the data with the Tuesday state
(week-11 consensus = the Sunday snapshot only, committed Bronze from the 09:13 UTC cron, 2,099 x 699 feature
matrix, `generate_projections.py --ml`), the live Sleeper registry fetched once (public, unauthenticated) and
shared by both builds so they differ only by the rule. Fidelity check: the unmodified code reproduces the CI
failure exactly (`TE#71`) and 15 of the 17 skill rows the cron zeroed. The other two (C.Tate, O.Cooper) were
tagged at 09:20 UTC and cleared by the ~21:00 UTC fetch (496 live designations then vs 560 at the cron).

| player | pos | consensus 14:13 | published 09:20 | replay before | replay after | rank before -> after |
|---|---|---|---|---|---|---|
| B.Bowers | TE | 12.14 | 0.00 (TE#71) | 0.00 | 3.12 | TE#71 -> TE#39 |
| K.Walker | RB | 17.13 | 0.00 (RB#75) | 0.00 | 7.05 | RB#75 -> RB#36 |
| G.Smith | QB | 15.45 | 0.00 (QB#31) | 0.00 | 5.64 | QB#31 -> QB#28 |
| M.Evans | WR | 11.52 | 0.00 (WR#112) | 0.00 | 4.42 | WR#115 -> WR#65 |
| D.Smith | WR | 10.40 | 0.00 (WR#110) | 0.00 | 4.58 | WR#114 -> WR#63 |
| L.McConkey | WR | 9.98 | 0.00 (WR#114) | 0.00 | 3.99 | WR#116 -> WR#72 |
| J.Waddle | WR | 9.15 | 0.00 (WR#117) | 0.00 | 3.24 | WR#120 -> WR#80 |
| C.Tate | WR | 10.00 | 0.00 (WR#113) | 10.49 | 10.48 | tag cleared before the replay registry |
| O.Cooper | WR | 8.24 | 0.00 (WR#111) | 10.32 | 10.31 | tag cleared before the replay registry |
| C.Beck | QB | 9.19 | 0.00, status Active (QB#32) | 0.00 | 7.83 | not an injury row (see below) |

Also released (consensus >= 5, no ranks quoted above): W.Marks (RB) 5.0, D.Wicks (WR) 2.9, J.Addison (WR) 3.1.
Five skill rows stay at zero (no consensus row or consensus < 5: J.Ferguson, J.Jennings, S.Darnold, D.Maye, C.Bell).

**Gate: still FAIL.** `python scripts/sanity_check_projections.py --check-weekly --scoring half_ppr --season 2026`
on the rebuilt board: before `Brock Bowers ... TE#71`, after `TE#39` (window: top-20, cutoff 4.46 pts). Bowers's
healthy number on our board is 7.8 (TE#9; consensus has him TE2 at 12.1); 0.4x of that is 3.1. Clearing the window
would need ~0.58x, above the upper end of the fitted interval (0.53), so no multiplier the data supports passes
this check for him. **A data-honest board and this check disagree for any star Sleeper has tagged Out whom our
healthy projection ranks outside the TE/WR top 20; the fix is in the check, not in the board.** The check
already downgrades a star we project at 0 to a warning when the consensus snapshot is stale; the same exemption
keyed on `injury_unconfirmed` (or on a zero produced by a Sleeper-only Out tag) would be the narrow change, and
this PR adds the column for it. `scripts/sanity_check_projections.py` is not edited here.

### Why the discount is applied to the finished board

The first version scaled the row at the injury step. The Sleeper anchor is a value-conserving rank reassignment, so a
row discounted before it is handed the value at its consensus rank: the week-11 replay came out at 0.65x of
consensus on average (Bowers 4.16, Walker 11.98), not 0.4x. The rule now releases the player at the injury step (he runs through every
blend as the healthy player the consensus treats him as) and `apply_unconfirmed_out_discount` prices the play
probability on the finished number, after the injury invariant and before the ranks are recomputed. The floor drops to 0
and the ceiling stays at his healthy ceiling.

### Side effect to know about (pre-existing mechanism)

218 of 373 board rows move (mean |delta| 0.14 pts on skill rows; skill total 1,893 -> 1,962 of which ~50 is the ten
released players). That is the same value-conserving anchor: today a zeroed star is handed a mid-board value by the
anchor and re-zeroed afterwards by the injury invariant (12 such rows on the before build, 2 on the after), which
takes that value out of circulation and pushes everyone below him down a slot. C.Beck's 0.00 -> 7.83 is the same
mechanism acting on a row that was never injury-related (status Active, no basis in the engine, consensus 9.2; the
consensus-fallback in PR #169 is the fix for rows like that). Excluding sidelined rows from the anchor's pool would
remove the distortion at its source; not done here.

### Switching it off

`UNCONFIRMED_OUT_MULTIPLIER = 0.0` keeps the column and the `Out (unconfirmed)` label and restores the zero (the
scorecard's MAE prefers the zero on this subgroup; see section 1). Removing the `soften_unconfirmed_outs` call
in `generate_projections.py` restores the old behaviour entirely.
