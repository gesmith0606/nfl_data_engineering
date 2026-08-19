# Draft-Time ADP Early-Season Gate — `--adp-prior` (2026-08-18)

Pre-registered BEFORE running any backtest results. Implements + gate-
evaluates the draft-time-ADP hypothesis: crowd-consensus ADP (Fantasy
Football Calculator, late-Aug/early-Sept snapshot — strictly before week 1)
improves EARLY-SEASON projections (weeks 1-6), where our model is
historically weakest, because trailing-usage features are thin/absent then
and prior-season PPG mispredicts players with changed roles (rookies, team
changes, promoted starters) — exactly the players the drafting crowd prices
in.

Closest precedent lever: `--early-season-prior`
(`.planning/EARLY_SEASON_PRIOR_GATE.md`) — HOLD, deconfounded weeks 3-6 MAE
gap improvement 0.053 (bar 0.10) / ordinal gap improvement 0.037 (bar 0.05).
This gate mirrors its structure, bars, and eval method exactly, extended to
weeks 1-6 and a different signal source.

## Data — new today

`data/adp/history/adp_ffc_{format}_{year}.csv` for `format` in
`{ppr, half_ppr, standard}`, `year` in `{2021..2025}` — FFC's public API,
snapshot_date late Aug/early Sept each year (strictly pre-week-1, so usable
for every in-season week of that season with zero leakage). Columns:
`season, snapshot_date, source, format, player_name, team, position, adp,
high, low, stdev, times_drafted`. `data/adp/history/adp_mfl_season_aggregate_{year}.csv`
also exists (MFL, full-draft-season aggregate) — robustness check only per
the leakage note below, not the primary source.

**Leakage**: FFC snapshot_date is late Aug/early Sept — strictly before
week 1 of that season — so it is valid pre-game information for every week
of the season it was drafted for. MFL's `PERIOD=ALL` aggregates the entire
draft season (including in-season redraft/dynasty startup drafts that occur
after week 1 in some formats) — noisier and a weaker leak-free guarantee,
used only as a cross-check if at all, never as the primary lever input.

## Lever implemented

`proj' = (1-w)*proj + w*adp_implied_ppg` for weeks 1-6 only (no-op
elsewhere), where:

- `adp_implied_ppg` = a per-position log10(ADP) -> realized-season-PPG
  linear mapping (`numpy.polyfit`, degree 1), applied to the CURRENT
  season's ADP snapshot. The mapping is fit **walk-forward on prior seasons
  only**: season S's mapping pools (ADP, realized full-season PPG) pairs
  from every season `2021 <= y < S` that has both a committed ADP snapshot
  and Bronze weekly data — e.g. 2021 ADP + 2021 realized PPG informs 2022's
  mapping; 2021+2022 inform 2023's; 2021+2022+2023 inform 2024's;
  2021-2024 inform the sealed-2025 mapping. Never same-season.
- Realized-season-PPG training labels are gated on >=6 games played in that
  training season (mirrors `early_season_prior.MIN_PRIOR_GAMES` — same bar,
  same rationale: below this the season average is noisier than useful).
- A position's mapping is only fit if the training pool has >=5 pooled
  rows after the games-played gate and the ADP/realized-PPG name join;
  otherwise that position is a structural no-op for the eval season.
- `w = scale * schedule[week]`, fixed decaying schedule
  `{1: 0.5, 2: 0.45, 3: 0.4, 4: 0.3, 5: 0.2, 6: 0.1}` — heavier than
  `--early-season-prior`'s weeks-3-6-only schedule because weeks 1-2 have
  ZERO current-season signal (vs. `--early-season-prior`, which starts at
  week 3 because weeks 1-2 lack the "2 weeks of history" the backtest
  harness requires for its own rolling features — the ADP lever has no such
  requirement since it doesn't depend on current-season history at all).
  `scale` defaults to 1.0.
- Applies to QB/RB/WR/TE only. Implied PPG is floored at 0.

**Join**: ADP snapshots carry no `player_id` (FFC exposes name/team/
position only), so the join is `(sleeper_player_map.normalize_name(name),
position)` — the same hardened name-join helper already used by
`src/adp_sources.py` for ADP joins and by the live-draft pick-matching code
(`map_picks_to_projections`), NOT a raw name string. Per the coverage-check
rule ("never join on name alone"), position is part of the key so two
different-position players sharing a normalized name don't collide.

**New module**: `src/adp_prior.py` — `load_adp_snapshot()`,
`compute_realized_season_ppg()`, `fit_adp_ppg_mapping()`,
`compute_adp_implied_ppg()`, `apply_adp_prior()`, mirroring the
`early_season_prior.py` compute/apply pattern.

**Wiring** (opt-in, mirrors `--early-season-prior`):
- `scripts/generate_projections.py --adp-prior` / `--adp-prior-weight`
  (weekly mode only; applied after the early-season-prior blend, before
  the QB starter floor — a role/usage correction, not a news/market
  signal).
- `scripts/backtest_projections.py --adp-prior` / `--adp-prior-weight` —
  threads the lever into `run_backtest()`, with a per-eval-season mapping
  cache built once before the week loop (walk-forward training seasons
  loaded from Bronze weekly data independent of the season the harness
  would otherwise load, since a sealed single-season run needs 2021+
  training history the harness's own `season ∪ {season-1}` window doesn't
  cover).

## Pre-registered gate

**Coverage/firing rate is reported BEFORE any MAE/ordinal numbers below**
(per `knowledge-vault/concepts/gated-experiment-coverage-check.md`): % of
projected QB/RB/WR/TE player-weeks in weeks 1-6 with a non-null
`adp_implied_ppg`, by position and season, plus a changed-rows count
(before-vs-after `projected_points` diff != 0) per season. If any
position's coverage is <60%, that is flagged explicitly and the aggregate
verdict is read with that caveat — a silent join failure must not produce a
vacuous SHIP or HOLD.

**Gates** (same bars as `--early-season-prior`):
- **PRIMARY (MAE)**: weeks 1-6 matched-pair MAE gap vs Sleeper improves by
  >=0.10 pts overall, **OR** per-position (mirrors the precedent's "overall
  or per-position" scoping-rule corollary — per-position wins are not
  discarded just because the overall composite misses, since positions
  train/fit independently here just as in the 2026-08-16 consolidation
  re-gate).
- **SECONDARY (ordinal)**: weeks 1-6 (or nearest supported window, 1-17)
  FantasyPros-style Accuracy Gap vs Sleeper improves by >=0.05 overall.
- **Guard**: full-season (weeks 1-18, or 7-18 as the non-overlapping
  control) overall gap does not worsen by >0.02, and no position's
  full-season gap worsens by >0.05. Weeks 7-18 must be BYTE-IDENTICAL
  between baseline and treated (proof the lever is correctly scoped to
  weeks 1-6 only, no leakage) — same invariant check the early-season-prior
  gate used to catch its 2021-data confound.
- **Deconfounded slices** (coverage-check rule): report weeks-1-6 MAE gap
  split into (a) rows where the lever actually fired (`adp_implied_ppg`
  notna) vs all rows, and (b) a cheap rookie/team-change proxy — players
  with zero prior-season (S-1) games in Bronze weekly history — vs
  established players, since that subgroup is exactly who the hypothesis
  targets.

**Walk-forward**: 2022-2024 (mapping trained on whatever of 2021-2023 is
available before each eval season). **Sealed confirm**: 2025, run ONCE at
the end, mapping trained on 2021-2024, no iterating on the result.

**Baseline discipline**: per the early-season-prior gate's hard-won lesson
(0.098-pt confound from a stale pre-ingestion baseline), baseline and
treated backtests are generated back-to-back in the SAME session, on the
SAME data vintage, no reused CSVs from prior runs.

**Verdict rule**: SHIP if the primary gate clears walk-forward AND holds
direction (same sign, doesn't need to clear the bar) on sealed 2025 AND the
full-season guard passes. HOLD otherwise. Either way `--adp-prior` ships as
inert, evaluable, opt-in machinery (repo pattern) — this doc's verdict only
gates the DEFAULT, never removes the flag.

## Protocol amendment slot

If the log(ADP)->PPG mapping approach proves unworkable (e.g., too little
training signal, degenerate fits), the fallback is a single simpler
variant: use ADP RANK directly as a feature in the blend weight (e.g.
`w = base_w * (1 - normalized_adp_rank)`, no fitted mapping at all) instead
of a regression-derived implied-PPG target. Any such change will be
documented here as a dated amendment BEFORE running on sealed 2025 data —
not applied silently.

---

## Results

*(To be filled in after the walk-forward + sealed runs. Coverage/firing
rate reported first, per the pre-registration above.)*
