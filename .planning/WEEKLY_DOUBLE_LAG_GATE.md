# Weekly double lag + bye-week drop — diagnosis and gate (2026-09-23)

**Verdict: SHIP default-on.** Week W is now projected from games 1..W-1. Before
this fix the most recent game never counted. Players coming off a bye also
stay on the board now; before, they dropped off it. Both fixes can be turned
off: `--no-fresh-rolling` and `--no-bye-returns` restore the old behaviour in
`generate_projections.py` and `backtest_projections.py`, and the engine takes
`fresh_rolling=False` / `include_bye_returns=False`.

## 1. Diagnosis (confirmed)

Silver usage rows (`scripts/silver_player_transformation.py` ->
`player_analytics.compute_rolling_averages`) hold `*_roll3`, `*_roll6` and
`*_std` columns built with `groupby(player, season).shift(1)`. So the week-k
row describes games **before** k. That is the right, leak-free convention for
a row that is paired with game k's outcome.

`projection_engine.generate_weekly_projections(week=W)` then selects the
**week W-1** row (`silver_df["week"] == week - 1`). Its rolling columns stop
at game **W-2**. The lag is applied twice.

| Path | Row used for week W | Rolling columns cover |
|---|---|---|
| Live `generate_projections.py` (heuristic and `--ml` baseline) | Silver W-1 | games 1..W-2 |
| `backtest_projections.py` (`build_silver_features(weeks < W)` then the same engine) | W-1 | games 1..W-2 (same lag as live) |
| Residual training (`assemble_player_features` -> `compute_production_heuristic`, target = the same row's actual) | Silver **W** | games 1..**W-1** |
| `--ml` residual features: backtest with `--full-features` | W (exists historically) | 1..W-1 |
| `--ml` residual features: live, and backtest without `--full-features` | latest = W-1 (no week-W row yet) | 1..W-2 |

The backtest therefore matched production, and every gate measured the
double-lagged system. The residual models, however, were **trained on the
fresh lag**. Their targets were `actual − heuristic(week-W row)`. At serving
time they were added to a heuristic that was one game staler. This fix makes
the served heuristic baseline match training. It does not move away from
training, so no retrain is needed.

`veteran_prior.count_games_in_lookback` had the double lag written into its
docstring ("rolling averages cover weeks 1 through W-2"). No one had flagged
it as a bug.

**Concrete example: Ja'Marr Chase, 2025, projecting week 8.** His targets by
game were 1:5, 2:16, 3:6, 4:8, 5:10, 6:12, **7:23**.

| Source | targets_roll3 | targets_std | Games used |
|---|---|---|---|
| Production Silver week-7 row | 10.00 | 9.50 | std = games 1-6 |
| Backtest harness week-7 row | 10.00 | 9.50 | games 1-6 |
| `--fresh-rolling` (week-7 row advanced) | 15.00 | 11.43 | roll3 = games 5-7, std = games 1-7 |
| Training row (Silver week 8) | 15.00 | 11.43 | games 1-7 |

His 23-target week 7 did not count toward week 8. This also explains why
**nobody had in-season history in week 2**: every week-1 row's shift(1)
columns are NaN.

**Second bug found on the way: players coming off a bye vanish.** Silver has
a row only for games played. A player whose team was on bye in W-1 has no
W-1 row, so he gets no week-W projection at all. On the committed 2025 week-10
Gold board, the teams on bye in week 9 (CLE, NYJ, PHI, TB) have **zero rows**:
no Hurts, Barkley, Mayfield or others. The backtest's inner join on actuals
hid this. It drops 546 of 8,212 player-weeks (6.6%) over 2024-25 weeks 3-18,
including Lamar Jackson, Bijan Robinson, Josh Jacobs and CeeDee Lamb. In
2026 it would start with the week-6 board.

## 2. Fix

- `projection_engine.advance_rolling_features(target_df, silver_df)`
  recomputes each `<stat>_roll<N>` / `<stat>_std` column (for stats in
  `ROLLING_STAT_COLS`) over the player's same-season rows with
  `week <= feature-row week`. The result equals what the shift(1) transform
  gives a week-W row, so it uses games 1..W-1 and **never game W**. Tests pin
  both: the advanced week-4 value equals Silver's week-5 value, and adding a
  week-W row to `silver_df` leaves the projection unchanged. The week-1
  prior-season seed is advanced through its final regular-season game, and
  POST rows are excluded.
- `projection_engine.bye_return_feature_rows` adds each player's latest row
  when he played his team's most recent game and that game was before W-1.
  So a player off a bye is added. A player who missed his team's W-1 game
  (injury) stays excluded, exactly as before.
- The veteran-prior blend's game count follows the same window
  (`fresh_rolling` -> `week < W`).
- The flags are passed through `generate_ml_projections`, the backtest and
  the CLI. The engine logs
  `Week W fresh rolling: n/N feature rows now include their own game` and
  `added n player(s) whose team was on bye`, so the logs show the fix
  actually ran.

## 3. Pre-registered bar

Taken from the task: **SHIP default-on only if the standard backtest improves
overall MAE and no position gets worse by more than 0.05.** This is a bug fix
with no parameters, so there was nothing to tune and no data was peeked.

## 4. Backtest results

Setup: `backtest_projections.py --seasons 2024,2025 --scoring half_ppr
--vs-consensus`, weeks 3-18, shipped Sleeper anchor on, injuries applied.
Every run covers the same 7,666 player-weeks. Spearman is the mean of the
per-week values.

### Fresh rolling alone (population unchanged)

**`--ml`, the production path:**

| Pos | n | MAE before | MAE after | Δ | Bias before -> after | Spearman before -> after |
|---|---|---|---|---|---|---|
| ALL | 7,666 | 4.317 | **4.284** | −0.034 | −0.97 -> −0.88 | .658 -> .668 |
| QB | 866 | 6.523 | 6.396 | −0.127 | −1.60 -> −1.36 | .311 -> .330 |
| RB | 2,084 | 4.480 | 4.468 | −0.012 (2024 −0.034, 2025 +0.006) | −0.73 -> −0.64 | .677 -> .684 |
| WR | 3,203 | 4.018 | 3.996 | −0.022 | −0.84 -> −0.78 | .595 -> .600 |
| TE | 1,513 | 3.465 | 3.431 | −0.035 | −1.23 -> −1.13 | .583 -> .575 |

Both seasons improve overall: 2024 −0.038, 2025 −0.030. Weeks 3-6 improve
by −0.043 and weeks 7-18 by −0.030.

**Heuristic engine (no `--ml`):**

| Pos | MAE before -> after | Δ |
|---|---|---|
| ALL | 4.255 -> **4.232** | −0.023 |
| QB | 6.533 -> 6.403 | −0.130 |
| RB | 4.394 -> 4.381 | −0.014 |
| WR | 3.984 -> 3.974 | −0.010 |
| TE | 3.331 -> 3.328 | −0.003 |

Spearman .665 -> .673. Bias −0.64 -> −0.55.

**Consensus gap vs Sleeper.** Same 4,787 matched player-weeks (consensus
≥ 5); negative means we win.

| Engine | Overall | QB | RB | WR | TE | Our Spearman |
|---|---|---|---|---|---|---|
| `--ml` before | −0.06 | −0.22 | +0.03 | −0.11 | +0.13 | .487 |
| `--ml` after | **−0.09** | −0.32 | +0.04 | −0.13 | +0.06 | .497 |
| heuristic before | −0.06 | −0.23 | +0.04 | −0.10 | +0.07 | .489 |
| heuristic after | **−0.08** | −0.33 | +0.05 | −0.11 | +0.06 | .502 |

**Gate: PASS on both engines.** Overall MAE improves. The worst
single-position change is RB 2025 on `--ml` at +0.006, far below the 0.05 bar.

### Bye returns (on top of fresh rolling, `--ml`)

- **546 player-weeks added**, 6.6% of the final board. Their MAE is 3.77,
  with a bias of −0.6.
- On the 527 added rows that match consensus, we score **3.816 MAE vs
  Sleeper's 3.805** (parity). Before the fix these players had no projection
  at all.
- The rows that were already on the board move by only +0.003 MAE
  (4.2838 -> 4.2869), through the cross-sectional usage percentile and the
  anchor. The largest per-position change is RB +0.004.
- Final default configuration: consensus-matched n = 5,119, ours 5.24 vs
  Sleeper 5.32 (−0.08), Spearman .504.

## 5. Live 2026

Boards were regenerated locally with `--ml` and the shipped defaults, from
2026 Silver built with `silver_player_transformation.py --seasons 2026`. None
were committed. Half-PPR actuals = `fantasy_points + 0.5 * receptions`.

**Week 2.** Population: players who played and whom either board projected
at ≥ 5 (n = 176).

| Pos | n | MAE before -> after | Bias before -> after | Spearman before -> after | Sleeper MAE / Spearman |
|---|---|---|---|---|---|
| ALL | 176 | 5.599 -> **5.336** | −0.93 -> +0.04 | .439 -> .522 | 5.347 / .551 |
| QB | 33 | 7.600 -> 7.545 | −2.55 -> −0.34 | .304 -> .240 | 7.701 / .090 |
| RB | 48 | 3.822 -> 3.636 | +0.15 -> +1.61 | .506 -> .590 | 4.058 / .547 |
| WR | 73 | 5.739 -> 5.334 | −0.40 -> −0.00 | .318 -> .474 | 5.232 / .514 |
| TE | 22 | 6.006 -> 5.739 | −2.66 -> −2.67 | −.029 -> .236 | 5.336 / .175 |

Week 2 is the largest possible effect, because the old path had no in-season
history at all. After the fix our week-2 MAE is level with Sleeper's. It also
removes most of the week-2 "early-season compression" (bias −1.27) that
`SEASON_2026_WEEKS_1_2_RETRO.md` reported.

**Week 1.** Neutral: MAE 6.361 -> 6.363, n = 178. The prior-season seed and
the depth gate dominate that week.

**Week 3 board** (`--ml` + anchor, the production path). The "heuristic only"
column is the same comparison without `--ml` and without the anchor.

| Player | Before | After | Heuristic only | Note |
|---|---|---|---|---|
| Emanuel Wilson (SEA RB, 21 carries in wk2) | 2.85 | 3.83 | 3.06 -> 7.09 | proj carries 4.95 -> 11.45 |
| Adonai Mitchell (NYJ WR, 33% target share in wk2) | 7.08 | 7.97 | 8.02 -> 10.11 | proj targets 4.29 -> 7.79 |
| Ja'Marr Chase | 11.30 | 14.05 | | |
| Jahmyr Gibbs | 19.64 | 22.40 | | |
| Amon-Ra St. Brown | 13.55 | 16.20 | | |
| Josh Allen | 23.11 | 25.61 | | |
| Jaxon Smith-Njigba | 14.92 | 16.64 | | |
| Bijan Robinson | 19.06 | 17.75 | | |
| Saquon Barkley | 13.56 | 9.91 | | |
| Justin Herbert | 18.93 | 15.61 | | |

Wilson's and Mitchell's usage now reaches the engine. In production, the rank
anchor and the residual still hold Wilson down. That is a separate lever: the
lag fix makes the most recent game count, but it does not add extra weight
for a sudden role change.

## 6. What is NOT changed (follow-ups)

1. **Live residual features are still one game stale.** In live mode the
   hybrid path finds no week-W feature row and falls back to the W-1 row. That
   row covers games 1..W-2, while training used 1..W-1. The backtest without
   `--full-features` takes the same fallback, so the numbers above are
   production-faithful. Fixing it needs a week-W feature assembly across
   every Silver source; advancing only the usage columns would mix lag
   conventions inside one feature vector.
2. **The residual-training heuristic** (`compute_heuristic_baseline` on
   week-W rows) still counts veteran-prior games as `week < W-1`, while its
   rolling columns cover 1..W-1. This inconsistency is small and only matters
   early in the season. Align it at the next residual retrain
   (`train_residual_models.py`).
3. **Heuristic constants were tuned under the double lag.** This includes
   `POSITION_RECENCY_WEIGHTS`, the bias corrections and the ceiling
   shrinkage. Bias is still −0.55 on the heuristic and −0.88 on `--ml`, so
   re-tuning under the fresh lag could gain more.
4. **Local-run warnings (all in the pre-fix runs too):**
   - `RB snap-collapse correction failed ... cannot convert the series`.
     PR #122 fixes this: duplicated week partitions after the snap
     re-ingest.
   - The 2026 Silver snap join matched only 52% of rows, with a fan-out
     warning. This probably has the same duplicate-partition root cause.
   - No 2026 route-participation data.

   All of these warnings appear in both the before and after runs, so the
   comparisons above are unaffected.
