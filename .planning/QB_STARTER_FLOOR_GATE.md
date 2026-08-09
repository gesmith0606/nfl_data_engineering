# QB Starter-Tier Floor Gate — Lever #3 (2026-08-09)

Implements + gate-evaluates lever #3 from `.planning/CONSENSUS_ERROR_DECOMPOSITION.md`
finding #3: the `<8 pts` QB magnitude band has bias **-6.11** vs actuals (we
badly under-project it) while ESPN's comparable band is roughly balanced
(**+1.48**). The group is dominated by ~15 recurring backup/spot-start QBs
(Winston, Mullens, Browning, Rudolph, ...). Hypothesis: when a backup is
thrust into a starting role, his own rolling-average history is still
backup-level, so the model prices him as a backup instead of a starter.

## Lever implemented

Raise a QB's projection to a starter-tier floor when BOTH:

1. He is listed as the depth-chart **QB1** for the projected week
   (`data/bronze/depth_charts` — leak-free: a snapshot reflects the team's
   plan going into the week, not that week's outcome).
2. His own trailing usage is still backup-level: mean passing yards/game
   over strictly-prior current-season weeks (leak-free by construction — the
   projected week is never included, so no shift bookkeeping is needed) is
   missing, or below **92 yds/game** (= `_STARTER_BASELINES['QB']
   ['passing_yards'] (230) × _ROLE_SCALE['backup'] (0.40)` — reused from
   `projection_engine.py`'s existing backup-tier scale rather than a fresh
   magic number).

Floor value = `haircut (0.8, the one knob) × fantasy_points(_STARTER_BASELINES
['QB'])` = 0.8 × 15.3 = **12.24 pts (half-PPR)**. `_STARTER_BASELINES['QB']`
is the same conservative 100%-role QB stat line the rookie-fallback path
already uses (230 pass yd, 1.4 pass TD, 0.8 INT, 15 rush yd, 0.1 rush TD)
converted to points via `scoring_calculator.calculate_fantasy_points`.
Week 1 is skipped (no strictly-prior current-season weeks exist yet, so the
trailing-usage gate is meaningless — every player, including established
starters, would read as "backup-level"). QB only, floor-raise only (never
lowers a projection).

**New module**: `src/qb_starter_floor.py` —
`compute_starter_tier_floor()`, `get_depth_chart_qb1_ids()`,
`compute_qb_trailing_passing_yards()`, `apply_qb_starter_floor()`,
mirroring the `early_season_prior.py` compute/apply pattern.

Trailing passing yards is computed directly from Bronze `players/weekly`
(not read off a rolling column on the projections DataFrame) for two
reasons discovered during implementation:

- `projection_engine.generate_weekly_projections` returns a fixed
  output-column whitelist (`keep_cols` + `proj_*` + `projected_points` +
  a short flag list) — its internal `passing_yards_std` rolling feature
  does not survive to the caller.
- `backtest_projections.py`'s `build_silver_features` helper reconstructs
  Silver features via `compute_usage_metrics(hist)` **without** passing
  snap-count data, so `snap_pct`/`snap_pct_std` (the column
  `projection_engine._determine_usage_role` itself uses for role
  classification) is entirely NaN in the backtest path, while production's
  real Silver ETL (`silver_player_transformation.py`) does pass snap data.
  Relying on `snap_pct_std` would have made the lever behave completely
  differently in the backtest vs. production. `passing_yards` is a raw
  Bronze column present in both paths, so computing the trailing signal
  directly from it keeps behavior identical between
  `generate_projections.py` and `backtest_projections.py`.

**Wiring** (opt-in, mirrors `--early-season-prior`):
- `scripts/generate_projections.py --qb-starter-floor` /
  `--qb-starter-floor-haircut` (weekly mode only; no-op in `--preseason`).
  Applied after injury adjustments and the early-season-prior blend.
- `scripts/backtest_projections.py --qb-starter-floor` /
  `--qb-starter-floor-haircut` — threads the same lever into
  `run_backtest()`, loading one Bronze depth-chart file per backtested
  season (cached) and reusing the backtest's own multi-season `weekly_df`
  for the trailing-usage computation (no extra I/O).

## Pre-registered gate (written before running the eval)

- **SHIP** if: `<8 pts` QB projection band MAE improves ≥1.0 vs baseline on
  2022-2024 matched pairs (or the band's bias magnitude halves), **AND**
  overall QB gap vs Sleeper does not worsen >0.02, **AND** other positions
  byte-identical.
- **Else HOLD.**

## Method

Canonical eval process (`.planning/CONSENSUS_BENCHMARK_MULTI_SOURCE.md` /
`CONSENSUS_ERROR_DECOMPOSITION.md`), matching the lever-1 precedent:

```bash
# Baseline — reused the matched CSVs already on disk from the 2026-08-09
# decomposition run (same seasons/scoring/mode):
#   output/backtest/consensus_matched_{sleeper,espn}_half_ppr_20260809_035714.csv

# Treated:
./venv/Scripts/python.exe scripts/backtest_projections.py \
    --seasons 2022,2023,2024 --scoring half_ppr --ml --full-features \
    --qb-starter-floor --output-dir output/backtest
# -> output/backtest/backtest_half_ppr_ml_fullfeatures_qbstarterfloor_20260809_150744.csv

./venv/Scripts/python.exe scripts/benchmark_consensus_sources.py \
    --backtest-csv output/backtest/backtest_half_ppr_ml_fullfeatures_qbstarterfloor_20260809_150744.csv \
    --sources espn sleeper --output-dir output/backtest \
    --json-out output/backtest/consensus_benchmark_summary_qbstarterfloor.json
# -> output/backtest/consensus_matched_{sleeper,espn}_half_ppr_20260809_190904.csv

./venv/Scripts/python.exe scripts/decompose_consensus_errors.py \
    --sleeper-csv output/backtest/consensus_matched_sleeper_half_ppr_20260809_190904.csv \
    --espn-csv output/backtest/consensus_matched_espn_half_ppr_20260809_190904.csv
```

Baseline decomposition was regenerated from the same on-disk baseline CSVs
for an apples-to-apples same-day comparison (`decompose_consensus_errors.py`
against the `20260809_035714` matched CSVs).

## Results — `<8 pts` QB magnitude band (the lever's target slice)

`gap = our_mae − source_mae` (negative = we win). Δ = treated − baseline.

| Source | n (base/treat) | our_mae base→treat | Δ MAE | our_bias base→treat | gap base→treat |
|---|---|---|---|---|---|
| ESPN | 87 / 85 | 6.962 → 6.873 | **−0.089** | −6.110 → −6.002 | +1.850 → +1.783 |
| Sleeper | 95 / 91 | 6.904 → 6.840 | **−0.064** | −5.932 → −5.825 | +0.575 → +0.480 |

**Gate check on the primary criterion**: required ≥1.0 pt MAE improvement
(or bias magnitude halving, i.e. reaching ≤3.06 ESPN / ≤2.97 Sleeper).
Measured improvement is **0.06-0.09 pts MAE**, about **6-9% of the
required bar**, and bias magnitude barely moves (reduced by ~0.1-0.11 pts,
nowhere near halved). **Fails badly.**

Note the population itself shrinks slightly (87→85, 95→91): the floor
value (12.24) sits above the 8-pt band boundary, so any flagged player who
was below 8 pts pre-floor and gets raised to 12.24 mechanically exits the
`<8` band into `8-14` — a selection effect, not band-level improvement.

## Results — overall QB gap (regression guard)

| Source | baseline gap | treated gap | Δ |
|---|---|---|---|
| Sleeper | −0.343 | −0.352 | −0.009 (slightly better) |
| ESPN | +0.230 | +0.225 | −0.005 (slightly better) |

**Gate check on the Sleeper guard**: passes comfortably — the overall QB
gap vs Sleeper does not worsen (it improves marginally, well inside the
±0.02 tolerance).

## Results — other positions (regression guard)

RB/WR/TE `magnitude_band`/`week_band`/`season`/`archetype`/
`top_20_contributors` slices are **byte-identical** between baseline and
treated for both sources — every reported `n`/`gap`/`bias` value matches
exactly (verified via diff of the two full `decompose_consensus_errors.py`
outputs). Confirms the lever is correctly scoped to QB rows only, with no
leakage into other positions' projections.

## Verdict: **HOLD**

Both guardrails pass cleanly, but the primary bar fails badly — measured
`<8 pt` band MAE improvement (0.06-0.09 pts) is roughly a **twentieth** of
the required 1.0 pt, and bias magnitude reduction (~0.1 pts) is far short
of halving. Do not flip `--qb-starter-floor` on by default. The flag stays
opt-in/off and merges as inert, evaluable machinery, matching the pattern
established for `--props-blend`, `--vacated-opportunity`, and
`--early-season-prior`.

## Root cause: the depth-chart signal lags the actual role change

Only **9 QB player-weeks** were flagged across all three backtested
seasons (out of 1,250 QB matched player-weeks vs Sleeper — 0.7%). Tracing
a canonical example (Jake Browning, CIN 2023, after Joe Burrow's
season-ending wrist injury) against `data/bronze/depth_charts` explains
why:

| Week | Browning's actual role | Depth chart QB1 for CIN | Browning's trailing pass yds/gm |
|---|---|---|---|
| 11 | First relief appearance (68 yds) | Joe Burrow | 0.0 |
| 12 | Full start (227 yds) | **Joe Burrow** (still) | 34.0 |
| 13 | Full start (354 yds) | **Joe Burrow** (still) | 98.3 |
| 14 | Full start (275 yds) | **Browning** (finally flips) | 162.3 |

nflverse's official team-submitted depth chart did not list Browning as
CIN's QB1 until **week 14** — three weeks after his first meaningful
start and two full starts after Burrow's season ended. By week 14,
Browning's *own* trailing passing yards (162.3) had already climbed above
the 92-yd backup threshold from his two intervening real starts, so gate
(2) no longer qualified him either. **The two leak-free gates only
overlap in a narrow, often-empty window**: depth charts are typically
slow to formally update (players are sometimes left nominally "#1" for a
few weeks after losing the job in practice), and by the time they do
catch up, the new starter's own stats usually have too. This same pattern
recurred for Zach Wilson/NYJ 2023 (Aaron Rodgers stayed listed #1 through
week 2 despite a week-1 season-ending injury) and is the dominant reason
the lever rarely fires: a standalone diagnostic scan of
depth-chart-QB1-AND-backup-level-trailing-usage across all of 2022-2024
(weeks 2-18, before any consensus-population filtering) found only 28
qualifying player-weeks total.

## Caveats / follow-ups

- **The depth-chart lag, not the floor value or the haircut, is the
  binding constraint.** Tuning the 0.8 haircut or the 92-yd threshold
  cannot fix a signal that fires on ~0.7% of QB player-weeks; both knobs
  were left at their designed defaults rather than swept, since the
  bottleneck is recall, not threshold placement.
- **A faster-updating incumbent-injury signal is the natural next
  iteration** — the task's alternate candidate, `data/bronze/injuries`
  (incumbent starter listed Out/IR), likely updates faster than the
  official depth chart and could be combined with (or substituted for)
  the depth-chart gate to catch the role change closer to when it
  actually happens, worth a follow-up experiment before re-registering a
  gate rather than a blind retune of this design.
- **When the lever does fire, the floor itself is directionally right but
  not sized to catch breakout weeks** — e.g. T.Hill week 5 2022 (floored
  to 12.24, actual 34.08) — a floor by construction cannot address
  ceiling-side misses; it only helps when the true outcome lands near or
  below starter-tier expectation (which several of the 9 flagged cases
  did: e.g. M.Willis week 10 2022 actual −0.40, P.Walker week 7 actual
  15.08 vs floored 12.24).

## Files changed

- `src/qb_starter_floor.py` (new) — `compute_starter_tier_floor()`,
  `get_depth_chart_qb1_ids()`, `compute_qb_trailing_passing_yards()`,
  `apply_qb_starter_floor()`, `BACKUP_PASSING_YARDS_THRESHOLD`,
  `DEFAULT_HAIRCUT`, `MIN_WEEK`.
- `scripts/generate_projections.py` — `--qb-starter-floor` /
  `--qb-starter-floor-haircut` CLI flags, weekly-mode wiring after the
  early-season-prior blend.
- `scripts/backtest_projections.py` — same two CLI flags,
  `run_backtest(qb_starter_floor=..., qb_starter_floor_haircut=...)`,
  per-season depth-chart cache, applied after the early-season-prior block
  in the per-week loop, output filename `_qbstarterfloor` tag.
- `tests/test_qb_starter_floor.py` (new) — 25 unit tests covering floor
  computation (baseline reuse, haircut scaling), depth-chart QB1 detection
  (week/position/game-type filtering), trailing-passing-yards computation
  (including an explicit leak-free test — a huge current-week game must
  not leak into the trailing average), and the combined apply function
  (promoted-backup floors, established-starter no-op, never-lowers,
  week-1 no-op, missing-history-counts-as-backup-level). All passing.
- `CLAUDE.md` — one-line command reference under "Gold: Fantasy
  projections" (if not already present, add
  `--qb-starter-floor` alongside `--early-season-prior`).
