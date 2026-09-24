# 2026 Weeks 1-2 retrospective (written 2026-09-23)

Graded our published weekly Gold boards (half-PPR) against actuals and Sleeper's
final weekly projections. "Relevant" = either source projected >= 5 and the player
played. Official harness (`weekly_grading_report.py`, consensus-gap metric) agrees.

## Scoreboard

| Pooled wk1+2 (n=370) | MAE | bias | Spearman |
|---|---|---|---|
| Ours (final board) | 5.75 | -0.52 | 0.446 |
| Sleeper | 5.56 | +0.35 | 0.544 |
| 50/50 blend | **5.53** | | |

| Position | Ours MAE | Sleeper MAE | Blend MAE | Ours rho | Sleeper rho |
|---|---|---|---|---|---|
| QB | **7.31** | 7.54 | 7.31 | **0.224** | 0.192 |
| RB | 5.56 | 5.21 | **5.19** | 0.566 | 0.644 |
| WR | 5.46 | 5.23 | 5.26 | 0.281 | 0.424 |
| TE | 5.18 | **4.86** | 4.91 | 0.042 | 0.269 |

Harness consensus gap (positive = we lose): wk1 +0.237 (QB -0.30 win), wk2 +0.124 (RB -0.19 win).

## Root-caused defects (fixed in this PR)

1. **Shipped Sleeper WR anchor never fired in 2026.** `sleeper_anchor_flag` was False
   on all 608/357/359 rows of the wk1-3 boards. Two stacked bugs:
   - `weekly-external-projections.yml` merged every artifact into
     `data/bronze/external_projections/`; upload-artifact roots each artifact at the
     source folder's contents, so files landed at `season=2026/...` with no
     `sleeper/` level — where neither the anchor nor Silver consolidation reads.
   - The live single-week Sleeper ingest never built the sleeper->GSIS map (only
     `--historical` did), so `player_id` held raw Sleeper ids; the anchor joins on GSIS.
   Fix: per-source restore step + regression test; `build_full_gsis_map()` (nflverse
   ids -> roster crosswalk -> registry) on the live path; 2026 files moved and
   re-mapped (19,517 rows); Silver external projections rebuilt for wk1-3. Anchor
   now matches 94% of WR / 96% RB / 90% TE rows on the wk3 board.
   Guard: `generate_projections.py` emits a `::warning::` when the anchor matches
   < 50% of its position's rows.
2. **Silver external projections frozen at week 1** (same root cause) — the weekly
   grading report and source-comparison surfaces were grading against nothing.
3. **Grading report read the derived display board** for wk1 (`*_derived` sorts after
   `projections_*`) and crashed on `projected_points`. Now excluded.
4. **Rookies never joined in the lineup/waiver tools** ("no model proj" for Price etc.):
   2026 rookies have no `sleeper_id` in Bronze rosters and no `gsis_id` in the registry,
   and weekly Gold names are abbreviated. `ours_by_sleeper_id(full_names=...)` now
   falls back on the full name from Bronze weekly actuals / rosters.

## Model findings (not changed here — decisions/gates)

- **RB and TE anchors: approve shipping.** Both passed every pre-registered gate
  (`SLEEPER_ANCHOR_QB_RB_TE_GATE.md`, SHIP-PENDING-USER). Live 2026 confirms the
  direction: blend beats ours by 0.37 MAE at RB and 0.27 at TE. QB stays unanchored
  (blend = ours; our QB already beats Sleeper) — matches the QB HOLD.
- **Early-season compression.** Week 2 bias -1.27 overall (QB -2.8, TE -1.9, WR -1.4);
  stars most under-projected (WR 12-16 tier -5.2, RB 16+ -2.8). This is what the
  `--early-season-prior` lever (weeks 3-6, HOLD) targets — run it in shadow for
  weeks 3-6 and grade live rather than re-litigating the backtest.
- **Rookies projected flat.** Week 1 board had no row for 2026 rookies; week 2 had all
  of them at 3.1-3.4 (the 25% "unknown" fallback) — Price was SEA's RB1. By week 3
  usage carried them (8-10 pts). The starter/backup depth-chart tiers never engaged;
  investigate the rookie depth-chart join, or let the (now-working) anchor cover rookies.
  **Root-caused (branch `fix/rookie-weekly-tiers`):** weekly mode had no depth-chart join;
  `_determine_usage_role` read `snap_pct_std`/`target_share_std`, which share the stat
  columns' `shift(1)` window and so are NaN on every fallback row -> always "unknown". Week 1:
  the prior-season seed only carries players with a prior-season row. Fix wires the
  pre-week depth chart into the tier + injects Week-1 starter/backup rookies. Live wk1+2
  rookie-fallback set (n=72): MAE 4.01 -> 3.93 (wk1 5.13 -> 4.01, wk2 3.11 -> 3.87); the
  starter tier over-projects rookie starters (~9.2 vs 6.7 actual) and Sleeper beats both
  (MAE ~3.0) — a rookie-starter scale or anchoring rookies is the next lever.
- **Week-1 backup QBs.** The prior-season seed projected ~20 non-starting QBs as starters
  (Fields 18.1, Winston 16.3, a retired Rivers 13.8). Gate the week-1 seed on the current
  depth chart QB1 before next season.

## Process learnings

- A default that prints "ON" is not evidence it ran — assert on output flags/coverage.
- Every cross-source join (Sleeper <-> GSIS) needs a coverage number in the logs.
- Sleeper's `injury_status` carries the last game's ruling (DJ Moore "Out" after leaving
  Week 2) — check the practice report / news date before benching.
- Hand-maintained ESPN/Yahoo roster files drift; re-pull from the sites each Tuesday
  (`docs/WEEKLY_WAIVER_RUNBOOK.md`).
