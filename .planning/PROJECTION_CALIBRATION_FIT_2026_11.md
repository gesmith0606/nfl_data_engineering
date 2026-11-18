# Projection calibration fit and lever audit - 2026-11-16 (PR 3)

Fitted honestly: leave-one-week-out (LOWO) on weeks 1-9 of 2026, scored against ACTUAL
half-PPR points on matched Sleeper-consensus >= 5 rows, never against the blend target.
Decision rule (fixed before looking): change a default only where the LOWO choice beats the
shipped setting in aggregate AND on weeks 6-9 taken alone; small or mixed = no change.

## 1. Lever audit: what fires on real 2026 inputs

Evidence is the Tuesday runner logs (`gh run view --log`, runs of Oct 20 and Oct 27) plus a replay
of weeks 4 and 7 with each engine lever switched off in turn (heuristic board, anchor and shrink
off, so only that lever differs).

| lever | live status | evidence |
|---|---|---|
| RB snap-collapse | **dead until this PR** (0 rows live); now fires on 1-1.5% of rows | looked up its signal at `week == target week`; signal rows exist only where the player has snaps, and the target week has none on a Tuesday. Runner logs have no `RB snap-collapse ... applied` line. Fixed: weeks 4 / 7 replay change 5 / 2 rows (|delta| ~3 pts) |
| WR route-slope collapse | **dead live, now OFF** | `Route participation: 0 rows` on every 2026 run (participation data is not published until after the postseason); runner logs: `route-slope collapse SKIPPED` |
| WR TPRR collapse | **dead live, now OFF** | same input, `TPRR collapse SKIPPED` |
| graph ranking nudge (`ranking_score`) | **no-op live, now OFF** | runner log week 7: `nudged 0 / 376 players`; its own gate was a MISS (WR12 +0.011 vs +0.025 bar; no RB signal); the column stays on the board equal to `projected_points` |
| veteran prior blend | fires | 79% / 27% of rows change (wk 4 / wk 7), mean abs delta 0.47 / 0.40 |
| TD regression | fires | 93% / 95%, 0.74 / 0.62 |
| matchup factor | fires | 87% / 85%, 0.39 / 0.36 |
| usage multiplier | fires | 92% / 94%, 0.45 / 0.39 |
| Sleeper anchor, dispersion shrink, band calibration, consensus fallback, injury layer | fire | per-run log lines (e.g. wk 7: 304 anchored rows, 153 shrunk) |
| opt-in levers (`--props-blend`, `--early-season-prior`, `--adp-prior`, `--qb-starter-floor`, `--rb-tail-calibration`, `--wr-tiebreak`, `--ecr-anchor`, `--wind-adjust`, `--vacated-opportunity`) | off by design | the cron command is `generate_projections.py --ml` with no opt-ins |

**RB snap-collapse: fixed, not deleted - weak evidence, stated plainly.** Backtest (heuristic, no
anchor/shrink) RB MAE vs actuals, lever off / old look-ahead lookup / fixed: 2023-2025 w3-18,
n=3,240 RB rows: 4.4556 / 4.4506 / 4.4506, i.e. -0.0050, 95% CI [-0.028, +0.018] (it fires on
146 rows = 4.5%; on those rows MAE 4.762 -> 4.650). By season: 2023 -0.021, 2024 -0.037, 2025 +0.035.
2026 w2-9 (n=583 RB rows, fires on 21): 4.234 -> 4.207, and on the 21 rows 4.021 -> 3.274.
The fixed and old lookups score identically in the backtest because only RBs who played are scored;
the fix matters live, where the old one never fired. A pooled gain of 0.005-0.01 with a CI that includes
zero and one reversed season does not clear the SHIP bar of `PROJECTION_SIGNALS_GATE_2026_11.md`; it is
kept because it is now correct, tested, near-neutral and the only RB role-loss signal, and should be
re-read at season end (n will roughly double). Deleting it would be equally unevidenced.

**Route levers: off.** With them on, the same 2023-2025 backtest scores WR MAE 4.1447 vs 4.1765 off
(-0.032; they fire on 1,965 of 5,033 WR rows = 39%). Production has never received that 0.03: every
historical WR backtest included it. Backtests are now production-faithful (WR 0.03 worse than they
used to read). An in-season WR role source would be worth ~0.03 WR MAE: a snap-share-slope analogue
(snap counts exist in-season) is the obvious candidate and is not evaluated here.

## 2. Replay fidelity (prerequisite for fitting)

The laptop replay was not runner-faithful: 586 assembled feature columns vs the runner's 699 (QB
residual matrix 29% populated vs the model's 85% at training). The runner's ingest chain was
re-run in a sandbox copy of the data with the same Bronze CLIs: NGS and PFR 2026 (the local
Python needed `SSL_CERT_FILE` pointed at certifi's bundle to fetch them; QBR 2026 is empty
upstream, as on the runner), PBP 2026 through week 10, then `silver_advanced_transformation`,
`compute_graph_features --seasons 2025 2026`, and the three team/game-context/quality Silver builds.
Result: **`Assembled player features for season 2026: 1867 rows, 699 columns`** - the runner's width -
and serve-time coverage of the residual matrices: QB .798, RB .858, WR .819, TE .802 against .847 /
.839 / .833 / .815 at training (94% / 102% / 98% / 98%), so the coverage guard stays quiet, as it
should on a healthy runner.

Week 7, startable (>= 5 pt) matched rows (n=140-141), faithful replay vs each published week-7 board:

| board | MAE | QB mean | RB mean | WR mean | TE mean | startable corr with replay | mean abs diff vs replay |
|---|---|---|---|---|---|---|---|
| published cron Oct 20 09:25 (older Sleeper snapshot, pre-Oct-21 code) | 5.089 | 16.17 | 11.77 | 10.29 | 8.10 | 0.725 | 2.05 |
| published rebuild Oct 25 16:51 (the scored one; built after the Oct 20 14:17 Sleeper snapshot, with the Oct 21-22 code) | 5.242 | 16.15 | 10.27 | 9.61 | 6.40 | 0.896 | 1.26 |
| **faithful replay** | **5.060** | 15.52 | 11.57 | 10.34 | 7.57 | 1.000 | 0 |

Per-position mean vs the cron board built on the runner: QB -0.65, RB -0.20, WR +0.05, TE -0.53;
MAE 0.03 apart; 0.18 better than the Oct 25 board. At player level the match is moderate, not close:
r=0.896 against the Oct 25 board, and only r=0.725 against the cron board, which anchored to the Oct 18
Sunday Sleeper snapshot (a week stale; the replay and the Oct 25 board use the Oct 20 Tuesday one) and predates the Oct 21
QB anchor/shrink. The Oct 22 and Oct 25 boards are near-identical to each other (r=0.996) and differ from the cron board (r=0.905 with it, RB/TE means
1.5-1.7 pts lower): they were rebuilt after the Oct 20 14:17 Sleeper snapshot and the Oct 21 anchor/shrink, and I could not tell from the
repo what else differs, so even the published week-7 boards are not one reference. Dispersion cannot be compared against the cron board.

Verdict: feature width and coverage match the runner exactly and the board moments (per-position mean, MAE) are close, but the
player-level reproduction is not tight. **Treated as adequate for fitting magnitudes (k) and, with caution, anchor weights; not a
bit-for-bit reproduction.** The one change shipped is the removal of a shrink on WR (a conservative direction) and it is a one-line revert
if the orchestrator judges the fidelity insufficient. 9 weeks, one season, n=237-542 per position.

## 3. Per-position fit

Boards: faithful replay, weeks 1-9 (n=1,428 matched rows), one board per Sleeper-anchor weight
w in {0, .25, .5, .75, 1} with the shrink off, the shrink applied offline with the production
function for k in 0.50..1.00. Shipped = (w=0.5, k=0.8). The anchor is a RANK blend (our sorted values
reassigned by the blended rank), so w changes order, k changes magnitude.

### 3a. Joint (w, k) per position - the pre-registered fit

LOWO aggregate (delta = chosen - shipped MAE; < 0 better):

| pos | weeks | n | shipped | chosen | delta |
|---|---|---|---|---|---|
| QB | 1-9 | 257 | 5.979 | 5.991 | 0.012 |
| QB | 6-9 | 107 | 5.865 | 5.721 | -0.144 |
| RB | 1-9 | 392 | 5.405 | 5.557 | 0.152 |
| RB | 6-9 | 159 | 5.455 | 5.565 | 0.110 |
| WR | 1-9 | 542 | 5.215 | 5.192 | -0.023 |
| WR | 6-9 | 202 | 5.016 | 5.026 | 0.010 |
| TE | 1-9 | 237 | 4.572 | 4.421 | -0.152 |
| TE | 6-9 | 105 | 4.173 | 3.932 | -0.241 |
| ALL | 1-9 | 1428 | 5.298 | 5.308 | 0.010 |
| ALL | 6-9 | 573 | 5.142 | 5.105 | -0.037 |

Every fold:

| pos | held_out | n | chosen | mae_chosen | mae_shipped | delta | rho_chosen | rho_shipped |
|---|---|---|---|---|---|---|---|---|
| QB | 1 | 31 | w=0.0,k=0.85 | 7.911 | 7.003 | 0.908 | 0.008 | 0.214 |
| QB | 2 | 30 | w=0.25,k=0.8 | 7.909 | 8.264 | -0.356 | 0.139 | 0.099 |
| QB | 3 | 29 | w=1.0,k=0.85 | 5.260 | 5.307 | -0.048 | 0.211 | 0.214 |
| QB | 4 | 31 | w=1.0,k=0.8 | 3.509 | 3.822 | -0.313 | 0.578 | 0.565 |
| QB | 5 | 29 | w=1.0,k=0.75 | 6.340 | 5.920 | 0.421 | 0.662 | 0.720 |
| QB | 6 | 26 | w=1.0,k=0.8 | 4.879 | 5.519 | -0.640 | 0.565 | 0.578 |
| QB | 7 | 27 | w=1.0,k=0.8 | 5.025 | 5.083 | -0.058 | 0.471 | 0.471 |
| QB | 8 | 28 | w=1.0,k=0.8 | 6.303 | 6.426 | -0.123 | 0.553 | 0.538 |
| QB | 9 | 26 | w=1.0,k=0.8 | 6.657 | 6.419 | 0.238 | 0.457 | 0.496 |
| RB | 1 | 46 | w=0.0,k=0.75 | 7.614 | 6.793 | 0.821 | 0.400 | 0.551 |
| RB | 2 | 48 | w=0.0,k=0.65 | 3.881 | 3.844 | 0.037 | 0.726 | 0.703 |
| RB | 3 | 48 | w=1.0,k=0.75 | 5.120 | 5.153 | -0.032 | 0.626 | 0.599 |
| RB | 4 | 45 | w=0.25,k=0.9 | 5.945 | 5.842 | 0.103 | 0.560 | 0.532 |
| RB | 5 | 46 | w=0.5,k=0.95 | 5.300 | 5.310 | -0.010 | 0.569 | 0.569 |
| RB | 6 | 37 | w=0.25,k=0.9 | 5.554 | 5.615 | -0.061 | 0.505 | 0.493 |
| RB | 7 | 38 | w=0.25,k=0.9 | 5.193 | 5.153 | 0.040 | 0.463 | 0.482 |
| RB | 8 | 42 | w=0.75,k=1.0 | 6.334 | 5.861 | 0.473 | 0.459 | 0.549 |
| RB | 9 | 42 | w=0.25,k=0.85 | 5.142 | 5.181 | -0.040 | 0.480 | 0.449 |
| WR | 1 | 71 | w=0.5,k=1.0 | 5.335 | 5.315 | 0.019 | 0.349 | 0.349 |
| WR | 2 | 72 | w=0.5,k=1.0 | 5.692 | 5.779 | -0.087 | 0.398 | 0.398 |
| WR | 3 | 71 | w=0.5,k=1.0 | 4.668 | 4.725 | -0.057 | 0.398 | 0.398 |
| WR | 4 | 66 | w=0.5,k=1.0 | 5.419 | 5.430 | -0.011 | 0.297 | 0.297 |
| WR | 5 | 60 | w=0.5,k=1.0 | 5.355 | 5.436 | -0.081 | 0.529 | 0.529 |
| WR | 6 | 54 | w=0.75,k=1.0 | 4.817 | 4.660 | 0.158 | 0.286 | 0.324 |
| WR | 7 | 47 | w=0.5,k=1.0 | 5.680 | 5.771 | -0.091 | 0.529 | 0.529 |
| WR | 8 | 51 | w=0.5,k=1.0 | 4.524 | 4.550 | -0.026 | 0.433 | 0.433 |
| WR | 9 | 50 | w=0.75,k=1.0 | 5.148 | 5.165 | -0.017 | 0.543 | 0.564 |
| TE | 1 | 27 | w=0.0,k=1.0 | 6.269 | 5.940 | 0.329 | -0.227 | -0.224 |
| TE | 2 | 23 | w=0.0,k=1.0 | 4.590 | 4.429 | 0.161 | 0.452 | 0.431 |
| TE | 3 | 25 | w=0.0,k=1.0 | 4.415 | 4.834 | -0.419 | 0.314 | 0.197 |
| TE | 4 | 29 | w=0.0,k=1.0 | 3.280 | 3.752 | -0.472 | 0.650 | 0.542 |
| TE | 5 | 28 | w=0.0,k=1.0 | 5.518 | 5.482 | 0.036 | 0.178 | 0.221 |
| TE | 6 | 24 | w=1.0,k=1.0 | 4.210 | 4.538 | -0.328 | 0.553 | 0.459 |
| TE | 7 | 28 | w=1.0,k=1.0 | 3.190 | 3.691 | -0.501 | 0.629 | 0.545 |
| TE | 8 | 23 | w=1.0,k=1.0 | 4.414 | 4.707 | -0.293 | 0.494 | 0.580 |
| TE | 9 | 30 | w=0.0,k=1.0 | 4.031 | 3.921 | 0.110 | 0.355 | 0.415 |

Joint choice flips between w=0 and w=1 from fold to fold for TE and QB (w is not identified):
no change from this fit.

### 3b. k only, anchor fixed at the shipped 0.5

| pos | weeks | n | shipped | chosen | delta |
|---|---|---|---|---|---|
| QB | 1-9 | 257 | 5.979 | 6.011 | 0.032 |
| QB | 6-9 | 107 | 5.865 | 5.884 | 0.019 |
| RB | 1-9 | 392 | 5.405 | 5.397 | -0.008 |
| RB | 6-9 | 159 | 5.455 | 5.455 | -0.000 |
| WR | 1-9 | 542 | 5.215 | 5.173 | -0.043 |
| WR | 6-9 | 202 | 5.016 | 4.973 | -0.042 |
| TE | 1-9 | 237 | 4.572 | 4.562 | -0.010 |
| TE | 6-9 | 105 | 4.173 | 4.142 | -0.031 |
| ALL | 1-9 | 1428 | 5.298 | 5.284 | -0.014 |
| ALL | 6-9 | 573 | 5.142 | 5.125 | -0.017 |

Every fold:

| pos | held_out | n | chosen | mae_chosen | mae_shipped | delta | rho_chosen | rho_shipped |
|---|---|---|---|---|---|---|---|---|
| QB | 1 | 31 | w=0.5,k=0.8 | 7.003 | 7.003 | 0.000 | 0.214 | 0.214 |
| QB | 2 | 30 | w=0.5,k=0.85 | 8.325 | 8.264 | 0.060 | 0.099 | 0.099 |
| QB | 3 | 29 | w=0.5,k=0.8 | 5.307 | 5.307 | 0.000 | 0.214 | 0.214 |
| QB | 4 | 31 | w=0.5,k=0.8 | 3.822 | 3.822 | 0.000 | 0.565 | 0.565 |
| QB | 5 | 29 | w=0.5,k=0.7 | 6.071 | 5.920 | 0.152 | 0.720 | 0.720 |
| QB | 6 | 26 | w=0.5,k=0.8 | 5.519 | 5.519 | 0.000 | 0.578 | 0.578 |
| QB | 7 | 27 | w=0.5,k=0.75 | 5.122 | 5.083 | 0.039 | 0.471 | 0.471 |
| QB | 8 | 28 | w=0.5,k=0.75 | 6.460 | 6.426 | 0.035 | 0.538 | 0.538 |
| QB | 9 | 26 | w=0.5,k=0.8 | 6.419 | 6.419 | 0.000 | 0.496 | 0.496 |
| RB | 1 | 46 | w=0.5,k=0.95 | 6.746 | 6.793 | -0.047 | 0.551 | 0.551 |
| RB | 2 | 48 | w=0.5,k=0.95 | 3.742 | 3.844 | -0.102 | 0.703 | 0.703 |
| RB | 3 | 48 | w=0.5,k=0.9 | 5.087 | 5.153 | -0.066 | 0.599 | 0.599 |
| RB | 4 | 45 | w=0.5,k=1.0 | 6.007 | 5.842 | 0.164 | 0.532 | 0.532 |
| RB | 5 | 46 | w=0.5,k=0.95 | 5.300 | 5.310 | -0.010 | 0.569 | 0.569 |
| RB | 6 | 37 | w=0.5,k=0.95 | 5.566 | 5.615 | -0.048 | 0.493 | 0.493 |
| RB | 7 | 38 | w=0.5,k=1.0 | 5.233 | 5.153 | 0.080 | 0.482 | 0.482 |
| RB | 8 | 42 | w=0.5,k=1.0 | 5.869 | 5.861 | 0.008 | 0.549 | 0.549 |
| RB | 9 | 42 | w=0.5,k=0.95 | 5.144 | 5.181 | -0.037 | 0.449 | 0.449 |
| WR | 1 | 71 | w=0.5,k=1.0 | 5.335 | 5.315 | 0.019 | 0.349 | 0.349 |
| WR | 2 | 72 | w=0.5,k=1.0 | 5.692 | 5.779 | -0.087 | 0.398 | 0.398 |
| WR | 3 | 71 | w=0.5,k=1.0 | 4.668 | 4.725 | -0.057 | 0.398 | 0.398 |
| WR | 4 | 66 | w=0.5,k=1.0 | 5.419 | 5.430 | -0.011 | 0.297 | 0.297 |
| WR | 5 | 60 | w=0.5,k=1.0 | 5.355 | 5.436 | -0.081 | 0.529 | 0.529 |
| WR | 6 | 54 | w=0.5,k=1.0 | 4.711 | 4.660 | 0.052 | 0.324 | 0.324 |
| WR | 7 | 47 | w=0.5,k=1.0 | 5.680 | 5.771 | -0.091 | 0.529 | 0.529 |
| WR | 8 | 51 | w=0.5,k=1.0 | 4.524 | 4.550 | -0.026 | 0.433 | 0.433 |
| WR | 9 | 50 | w=0.5,k=1.0 | 5.049 | 5.165 | -0.116 | 0.564 | 0.564 |
| TE | 1 | 27 | w=0.5,k=1.0 | 6.089 | 5.940 | 0.149 | -0.224 | -0.224 |
| TE | 2 | 23 | w=0.5,k=0.95 | 4.307 | 4.429 | -0.122 | 0.431 | 0.431 |
| TE | 3 | 25 | w=0.5,k=1.0 | 4.815 | 4.834 | -0.019 | 0.197 | 0.197 |
| TE | 4 | 29 | w=0.5,k=1.0 | 3.799 | 3.752 | 0.046 | 0.542 | 0.542 |
| TE | 5 | 28 | w=0.5,k=0.95 | 5.437 | 5.482 | -0.045 | 0.221 | 0.221 |
| TE | 6 | 24 | w=0.5,k=1.0 | 4.513 | 4.538 | -0.025 | 0.459 | 0.459 |
| TE | 7 | 28 | w=0.5,k=1.0 | 3.679 | 3.691 | -0.012 | 0.545 | 0.545 |
| TE | 8 | 23 | w=0.5,k=0.95 | 4.648 | 4.707 | -0.060 | 0.580 | 0.580 |
| TE | 9 | 30 | w=0.5,k=1.0 | 3.890 | 3.921 | -0.031 | 0.413 | 0.415 |

**WR: k 0.8 -> 1.0 (no shrink)** wins in aggregate (-0.043) and on weeks 6-9 (-0.042), better in 7 of 9 folds,
Spearman unchanged (k is monotone within a position). Paired bootstrap on rows (4,000 draws): weeks 1-9 CI
[-0.085, -0.002]; weeks 6-9 CI [-0.112, +0.025] - the effect is small and the later-weeks CI includes zero, so
this is the weakest change that still meets the stated rule; it is a one-line revert
(`SHRINK_FACTOR_BY_POSITION`). QB 0.8 stays (k=1.0 is +0.052 worse), RB (-0.008 / 0.000) and TE (-0.010 / -0.031) are small and mixed.

### 3c. w only, shrink fixed at the shipped 0.8

| pos | weeks | n | shipped | chosen | delta |
|---|---|---|---|---|---|
| QB | 1-9 | 257 | 5.979 | 5.969 | -0.011 |
| QB | 6-9 | 107 | 5.865 | 5.721 | -0.144 |
| RB | 1-9 | 392 | 5.405 | 5.500 | 0.095 |
| RB | 6-9 | 159 | 5.455 | 5.534 | 0.079 |
| WR | 1-9 | 542 | 5.215 | 5.231 | 0.015 |
| WR | 6-9 | 202 | 5.016 | 5.016 | 0.000 |
| TE | 1-9 | 237 | 4.572 | 4.490 | -0.082 |
| TE | 6-9 | 105 | 4.173 | 3.990 | -0.183 |
| ALL | 1-9 | 1428 | 5.298 | 5.315 | 0.017 |
| ALL | 6-9 | 573 | 5.142 | 5.103 | -0.039 |

Every fold:

| pos | held_out | n | chosen | mae_chosen | mae_shipped | delta | rho_chosen | rho_shipped |
|---|---|---|---|---|---|---|---|---|
| QB | 1 | 31 | w=0.0,k=0.8 | 7.819 | 7.003 | 0.816 | 0.008 | 0.214 |
| QB | 2 | 30 | w=0.25,k=0.8 | 7.909 | 8.264 | -0.356 | 0.139 | 0.099 |
| QB | 3 | 29 | w=1.0,k=0.8 | 5.234 | 5.307 | -0.073 | 0.211 | 0.214 |
| QB | 4 | 31 | w=1.0,k=0.8 | 3.509 | 3.822 | -0.313 | 0.578 | 0.565 |
| QB | 5 | 29 | w=1.0,k=0.8 | 6.263 | 5.920 | 0.343 | 0.662 | 0.720 |
| QB | 6 | 26 | w=1.0,k=0.8 | 4.879 | 5.519 | -0.640 | 0.565 | 0.578 |
| QB | 7 | 27 | w=1.0,k=0.8 | 5.025 | 5.083 | -0.058 | 0.471 | 0.471 |
| QB | 8 | 28 | w=1.0,k=0.8 | 6.303 | 6.426 | -0.123 | 0.553 | 0.538 |
| QB | 9 | 26 | w=1.0,k=0.8 | 6.657 | 6.419 | 0.238 | 0.457 | 0.496 |
| RB | 1 | 46 | w=0.0,k=0.8 | 7.619 | 6.793 | 0.826 | 0.400 | 0.551 |
| RB | 2 | 48 | w=0.25,k=0.8 | 3.760 | 3.844 | -0.084 | 0.721 | 0.703 |
| RB | 3 | 48 | w=0.25,k=0.8 | 5.110 | 5.153 | -0.043 | 0.634 | 0.599 |
| RB | 4 | 45 | w=0.25,k=0.8 | 5.930 | 5.842 | 0.087 | 0.560 | 0.532 |
| RB | 5 | 46 | w=0.25,k=0.8 | 5.070 | 5.310 | -0.240 | 0.607 | 0.569 |
| RB | 6 | 37 | w=0.25,k=0.8 | 5.529 | 5.615 | -0.086 | 0.505 | 0.493 |
| RB | 7 | 38 | w=0.25,k=0.8 | 5.133 | 5.153 | -0.019 | 0.461 | 0.482 |
| RB | 8 | 42 | w=0.75,k=0.8 | 6.289 | 5.861 | 0.428 | 0.459 | 0.549 |
| RB | 9 | 42 | w=1.0,k=0.8 | 5.145 | 5.181 | -0.036 | 0.474 | 0.449 |
| WR | 1 | 71 | w=0.5,k=0.8 | 5.315 | 5.315 | 0.000 | 0.349 | 0.349 |
| WR | 2 | 72 | w=0.25,k=0.8 | 5.823 | 5.779 | 0.044 | 0.346 | 0.398 |
| WR | 3 | 71 | w=0.5,k=0.8 | 4.725 | 4.725 | 0.000 | 0.398 | 0.398 |
| WR | 4 | 66 | w=0.25,k=0.8 | 5.508 | 5.430 | 0.078 | 0.273 | 0.297 |
| WR | 5 | 60 | w=0.5,k=0.8 | 5.436 | 5.436 | 0.000 | 0.529 | 0.529 |
| WR | 6 | 54 | w=0.5,k=0.8 | 4.660 | 4.660 | 0.000 | 0.324 | 0.324 |
| WR | 7 | 47 | w=0.5,k=0.8 | 5.771 | 5.771 | 0.000 | 0.529 | 0.529 |
| WR | 8 | 51 | w=0.5,k=0.8 | 4.550 | 4.550 | 0.000 | 0.433 | 0.433 |
| WR | 9 | 50 | w=0.5,k=0.8 | 5.165 | 5.165 | 0.000 | 0.564 | 0.564 |
| TE | 1 | 27 | w=0.0,k=0.8 | 6.110 | 5.940 | 0.169 | -0.227 | -0.224 |
| TE | 2 | 23 | w=0.0,k=0.8 | 4.722 | 4.429 | 0.293 | 0.452 | 0.431 |
| TE | 3 | 25 | w=0.0,k=0.8 | 4.533 | 4.834 | -0.302 | 0.314 | 0.197 |
| TE | 4 | 29 | w=0.25,k=0.8 | 3.527 | 3.752 | -0.226 | 0.624 | 0.542 |
| TE | 5 | 28 | w=0.0,k=0.8 | 5.575 | 5.482 | 0.093 | 0.178 | 0.221 |
| TE | 6 | 24 | w=1.0,k=0.8 | 4.247 | 4.538 | -0.290 | 0.553 | 0.459 |
| TE | 7 | 28 | w=1.0,k=0.8 | 3.254 | 3.691 | -0.438 | 0.629 | 0.545 |
| TE | 8 | 23 | w=0.0,k=0.8 | 4.508 | 4.707 | -0.199 | 0.477 | 0.580 |
| TE | 9 | 30 | w=0.0,k=0.8 | 4.075 | 3.921 | 0.154 | 0.355 | 0.415 |

RB is worse (+0.095), WR flat, and QB/TE look better only through choices that flip between w=0 and
w=1.0 by fold (QB weeks 1-9 -0.011; TE -0.082 / -0.183). In-sample the TE and QB curves are U-shaped in w
(w=0 and w=1 both beat 0.5), which is a property of the rank blend rather than a usable setting.
**No anchor-weight change anywhere.** Worth a look next season with more weeks: TE w=0 or w=1.

## 4. Changes made
- WR dispersion shrink off by default (`SHRINK_FACTOR_BY_POSITION`); `--dispersion-shrink-k` keeps its meaning (one k for all).
- RB snap-collapse reads the pre-week signal (fix), WR route-slope and TPRR collapses and the graph ranking nudge switched off.
- No anchor weight changed.
