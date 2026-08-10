# Phase 61-03 Event Adjustments Backtest

Generated: 2026-08-10T02:16:34Z  |  Seasons: [2024]  |  Scoring: half_ppr  |  Weeks with events data: 0/16

Production baseline at time of Phase 61 planning: **5.05 MAE** (2022-2024 half_ppr, per MEMORY.md).

Ship rule (D-03): treatment MAE may not exceed baseline MAE by more than **0.05** fantasy points on any position.


## Per-position aggregate

| Position | Baseline MAE | Treatment MAE | Delta | Verdict |
|----------|-------------:|--------------:|------:|---------|
| QB | 6.522 | 6.522 | +0.000 | PASS |

## Per-(season, week, position)

| Season | Week | Position | n | Baseline MAE | Treatment MAE | Delta | Verdict |
|-------:|-----:|----------|--:|-------------:|--------------:|------:|---------|
| 2024 | 3 | QB | 33 | 7.125 | 7.125 | +0.000 | PASS |
| 2024 | 4 | QB | 31 | 6.313 | 6.313 | +0.000 | PASS |
| 2024 | 5 | QB | 29 | 5.599 | 5.599 | +0.000 | PASS |
| 2024 | 6 | QB | 24 | 5.735 | 5.735 | +0.000 | PASS |
| 2024 | 7 | QB | 23 | 6.302 | 6.302 | +0.000 | PASS |
| 2024 | 8 | QB | 30 | 6.501 | 6.501 | +0.000 | PASS |
| 2024 | 9 | QB | 28 | 4.924 | 4.924 | +0.000 | PASS |
| 2024 | 10 | QB | 25 | 6.760 | 6.760 | +0.000 | PASS |
| 2024 | 11 | QB | 24 | 7.016 | 7.016 | +0.000 | PASS |
| 2024 | 12 | QB | 22 | 5.350 | 5.350 | +0.000 | PASS |
| 2024 | 13 | QB | 26 | 6.069 | 6.069 | +0.000 | PASS |
| 2024 | 14 | QB | 26 | 4.923 | 4.923 | +0.000 | PASS |
| 2024 | 15 | QB | 29 | 9.050 | 9.050 | +0.000 | PASS |
| 2024 | 16 | QB | 31 | 5.686 | 5.686 | +0.000 | PASS |
| 2024 | 17 | QB | 30 | 7.806 | 7.806 | +0.000 | PASS |
| 2024 | 18 | QB | 33 | 8.286 | 8.286 | +0.000 | PASS |

## Final verdict

`verdict=NO_DATA`


Zero weeks had Gold sentiment/event data for the backtest window, so treatment equals baseline by construction — this is **not** a real pass. Keep ``--use-events`` opt-in; do not default to True on the strength of this run.


> **Note:** Zero weeks had Gold sentiment/event data for the backtest window. Treatment equals baseline by construction, so ``verdict=NO_DATA`` — this is a lever-firing-rate problem, not a hypothesis rejection or a ship signal (see gated-experiment-coverage-check.md). This reflects the data pipeline state at time of backtest — sentiment Gold Parquet is only populated for 2025 W1 as of Phase 61-02. Re-run the backtest after the sentiment pipeline has produced Gold data for 2022-2024 before relying on the verdict for a ship decision.

