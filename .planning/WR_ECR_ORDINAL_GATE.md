# WR Weekly-ECR Ordinal Anchor Gate — `--ecr-anchor` (2026-08-18)

Pre-registered BEFORE running any backtest results. Implements + gate-
evaluates the weekly-ECR hypothesis: FantasyPros' weekly expert-consensus
rank (ECR), blended into our WR ordering, fixes our sole remaining ordinal
loss. Context: we beat Sleeper+ESPN on MAE at all 4 positions and win
ordinal at QB/RB/TE; WR ordinal is the last loss. The WR ordering
diagnosis found our swap losses are near-ties in OUR OWN projections
(median |our_diff| 1.21 pts) with real spreads just as wide (~6 pts) —
`--wr-tiebreak`'s target-share-slope tie-break lever HELD at only 16% of
its gate bar (54.8% signal hit rate, barely above the ~53% coinflip
floor). Weekly ECR — the crowd itself, not a proxy signal — is a much
stronger tie-break/anchor candidate for the same near-tie population.

Closest precedent levers: `--wr-tiebreak` (`.planning/WR_TIEBREAK_GATE.md`,
HOLD, near-tie clustering mechanism/EPSILON/NUDGE reused verbatim here) and
`--adp-prior` (`.planning/ADP_EARLY_SEASON_GATE.md`, HOLD, rank/PPG-blend
mechanism + walk-forward-fit-then-sealed-confirm discipline reused here).

## CRITICAL DESIGN CONSTRAINTS (read before any results)

1. **No sealed 2025 exists for this lever.** The ECR archive
   (`.planning/FP_ECR_HISTORY_COVERAGE.md`) stops 2024 — last automated
   scrape 2025-08-08, never resumed. Holdout protocol substitutes for a
   true seal: fit/tune the blend weight and pick the winning mechanism on
   **2022-2023 ONLY**; **2024 is the ONE-SHOT pseudo-sealed confirmation**,
   run once, never iterated on. 2020-2021 may inform priors but are not
   used as tuning/confirmation seasons here (2020 has odd week coverage,
   weeks 6-16 only, and both seasons are outside the tuning window this
   gate uses). **The true forward gate is 2026 in-season data** — our own
   daily FantasyPros rankings captures (`data/external/fantasypros_rankings.json`
   + its archive) — once week 1+ accumulates. This doc's SHIP/HOLD verdict
   is provisional on that basis, exactly like `--adp-prior`'s sealed-2025
   read was provisional on FFC coverage.
2. **Thursday leakage.** ECR `scrape_date` values are Fridays (confirmed:
   100% of the 2020-2024 archive's weekly-position scrapes land on a
   Friday) — AFTER that week's Thursday game, if any. A player whose own
   game already kicked off by the scrape date would leak that game's
   outcome/injury news into "his" week's ECR. The lever applies ECR to a
   player ONLY when his team's kickoff date (joined from Bronze
   `schedules`) is strictly after the scrape date. Since `scrape_date` in
   this archive carries no time-of-day, the comparison is at date
   granularity: `kickoff_date > scrape_date` (this correctly excludes
   Thursday games, which fall a day before the Friday scrape, and would
   also exclude a hypothetical Friday game). Excluded-row counts are
   reported per season BEFORE any result numbers (see Coverage section).
3. **Scoring mismatch.** Weekly ECR is PPR-only; our graded projections
   are half-PPR. For WR rank-ordering the distortion is small but nonzero
   (PPR inflates high-target/low-YPC possession-WR value slightly more
   than half-PPR) — noted as a known limitation, not corrected for.
4. **Coverage.** ECR covers roughly the top-60ish WRs drafted/rostered
   each week (FantasyPros' own weekly-position page depth). Coverage
   against our full graded WR population, and against the near-tie
   subpopulation specifically, is reported before any MAE/ordinal numbers
   (Coverage section) — if the ordinal metric's population sits mostly
   outside ECR coverage, that is flagged explicitly before results are
   read, per `knowledge-vault/concepts/gated-experiment-coverage-check.md`.

## Data — no new ingestion required

`data/silver/fp_ecr/season={2020..2024}/fp_ecr_{season}.parquet` (already
committed by `scripts/ingest_fp_ecr_history.py`, see
`.planning/FP_ECR_HISTORY_COVERAGE.md`). Join key: `gsis_id` — which is
**exactly** this repo's `player_id` format (nflverse gsis convention,
`"00-0033106"`-style; verified against Bronze `schedules.away_qb_id` /
`players/weekly.player_id`). **No name-join required anywhere in this
lever** — the single biggest generalizable fix from the coverage-check
doc's 6th/8th instances (abbreviated-name traps) simply doesn't apply
here, since the DynastyProcess crosswalk already resolved FantasyPros'
names to `gsis_id` at ingestion time. `scoring == "ppr"`, `position ==
"WR"` filter only.

## Lever implemented

`src/ecr_anchor.py`:

- `compute_team_kickoff_dates(schedules_df, season) -> DataFrame[week, team,
  kickoff_date]` — REG games only, one row per (week, team) from
  home_team/away_team x gameday.
- `build_ecr_lookup(proj_df, season, week, schedules_df, silver_dir=...) ->
  (lookup_df, stats)` — loads that week's WR ECR rows, resolves each
  player's team from `proj_df.recent_team`, joins kickoff date, applies the
  Thursday-exclusion rule, and returns a `player_id -> ecr_pos_rank`
  lookup plus a stats dict (`n_ecr_wr_rows`, `n_team_resolved`,
  `n_thursday_excluded`, `n_final_matched`, `n_proj_wr_rows`) for the
  coverage report.
- `apply_ecr_anchor(proj_df, lookup_df, mode, weight=None, epsilon=EPSILON,
  nudge=NUDGE, points_col="projected_points") -> proj_df` — dispatches to
  one of two pre-registered mechanisms (below). Non-WR rows, unmatched WR
  rows, and weeks with an empty lookup are returned byte-identical (the
  scoping-proof invariant the gate depends on). New provenance column
  `ecr_anchor_flag` (bool).

### Mechanism (a): rank-blend

`blended_rank = (1 - w) * our_rank + w * ecr_pos_rank` computed only for
ECR-matched WR rows (`our_rank` = 1-based descending rank on
`projected_points` within the full WR pool, ties broken by
`method="first"`). The matched subset's **original** point values are
sorted descending and reassigned to players in ascending-blended-rank
order — i.e., we permute which matched player gets which of the matched
subset's own existing point values, rather than inventing new numbers.
This is the rearrangement-inequality-minimal reassignment: pairing two
same-length sequences in matching sort order minimizes total absolute
movement, so this is the smallest point-mass shuffle that exactly realizes
the blended order — the direct "nudging points minimally to realize the
blended order" mechanism the task specified. Unmatched WR rows and all
non-WR rows are left completely alone (no-match passthrough). Weight `w`
is tuned on a grid `{0.1, 0.2, 0.3, 0.4, 0.5}` on 2022-2023 only.

### Mechanism (b): near-tie-only variant

Reuses `--wr-tiebreak`'s exact clustering mechanism and constants
(`EPSILON=1.5`, `NUDGE=0.5`) — for every ADJACENT pair in the WR pool
(sorted by `projected_points` descending) whose gap is `<= EPSILON`, if
`ecr_pos_rank` DISAGREES with our order (the lower-projected player of the
pair has the *better*, i.e. numerically lower, ECR rank) and BOTH players
in the pair are ECR-matched, nudge apart by `NUDGE` each. No weight grid —
this variant's only free parameters are the already-validated
`EPSILON`/`NUDGE` constants, reused unchanged.

Both are registered; the tuning-set winner (by primary-gate margin) is
carried to the one-shot 2024 confirmation. If neither clears >0 percent
of the bar, no winner is confirmed and the verdict is a scored HOLD (see
Verdict rules).

**Wiring** (opt-in, mirrors `--wr-tiebreak` / `--adp-prior`):
- `scripts/generate_projections.py --ecr-anchor [--ecr-anchor-mode
  {near_tie,blend}] [--ecr-anchor-weight W]` (weekly mode only). Applied
  after `--wr-tiebreak`, before `--wind-adjust` — same "role/usage and
  ordering corrections grouped together" family. **Production note**: the
  ECR archive has no current-season (2026) data (see constraint #1), so
  this flag is a structural no-op in live `generate_projections.py` runs
  until the 2026 forward-capture archive is wired as an alternate ECR
  source — documented here, not silently hidden.
- `scripts/backtest_projections.py --ecr-anchor [--ecr-anchor-mode ...]
  [--ecr-anchor-weight ...]` — threads the lever into `run_backtest()`,
  applied in the per-week loop right after the WR tiebreak block. No
  training/fitting step is needed (unlike `--adp-prior`'s walk-forward
  mapping) — ECR is a same-week piece of pre-game public information once
  the Thursday-exclusion rule is applied, not a historical regression
  target, so every eval season (2022, 2023, 2024) reads its own year's ECR
  data directly.

## Pre-registered gate

**Coverage/firing rate is reported BEFORE any MAE/ordinal numbers below**
(per `knowledge-vault/concepts/gated-experiment-coverage-check.md`):
- ECR-match rate among graded WR population, per season (before Thursday
  exclusion, and after).
- Thursday-exclusion count and rate, per season (how many player-weeks
  were dropped by the leakage rule).
- ECR-match rate specifically among the near-tie subpopulation (adjacent
  WR pairs `<=1.5pt` apart in our own projections — the exact subpopulation
  mechanism (b) targets, and the subpopulation mechanism (a)'s reordering
  most affects).
- If any season's overall WR match rate is <60%, that is flagged
  explicitly before reading results (mirrors the `--adp-prior` gate's
  identical <60% flag convention).

**Gates**:
- **PRIMARY**: WR FP-style ordinal Accuracy Gap (vs Sleeper, weeks 3-17,
  `scripts/simulate_fp_accuracy.py` machinery reused as-is) improves by
  `>=0.05` on the 2022-2023 tuning set (pooled), AND is directionally
  positive with `>=50%` of the tuning-set per-season-average effect
  retained on the 2024 one-shot confirmation.
- **GUARD**:
  - WR MAE vs Sleeper does not regress by more than `0.02` anywhere
    (tuning set or 2024 confirmation).
  - QB/RB/TE are byte-identical between baseline and treated (lever is
    WR-only) — verified both by full row-level diff and by
    `simulate_fp_accuracy.py`'s per-position summary matching to 5
    decimals.
  - Player-weeks with no ECR match (Thursday-excluded or plain no-match)
    show exactly `0.000` projected-points delta — the scoping proof (same
    invariant the `--adp-prior` gate used for its weeks-7-18 check, here
    applied to the match/no-match boundary instead of a week boundary
    since this lever has no week restriction of its own).

**Deconfounded slices** (coverage-check rule):
- Effect on ECR-matched rows vs all WR rows.
- Effect on near-tie pairs vs all pairs.
- Per-season effect, 2022 vs 2023 reported separately — **reject the
  tuning-set winner if sign flips between the two seasons** (same
  cross-season-consistency bar the consolidation re-gate applied on
  2026-08-16).

**Sanity/leak test**: shuffle test — randomize `ecr_pos_rank` within each
(season, week) group (same set of matched players, ranks reassigned at
random) and rerun the winning mechanism. The measured ordinal-gap effect
must collapse to approximately 0 (mirrors the hybrid-ship leak
verification's shuffle-collapse check) — this is the confirmation that any
measured effect is coming from the ECR *signal*, not from the mechanical
act of reordering/nudging points regardless of what's being reordered by.

## Verdict rules

- **SHIP** (as the default for WR) only if the primary gate clears on the
  2022-2023 tuning set AND the 2024 one-shot confirms (direction +
  retained-effect bar above) AND the guard passes AND the shuffle test
  collapses. If SHIP: do **NOT** change `generate_projections.py`/
  `backtest_projections.py` defaults in this session — mark
  **SHIP-PENDING-USER** (changing shipped model behavior 3 weeks before
  the draft is a user decision; the repo's live site metrics would need
  regeneration). The flag lands ON, opt-in, evaluable either way.
- **HOLD** otherwise (primary gate misses on tuning, or fails to hold on
  the 2024 one-shot, or guard fails, or the shuffle test doesn't
  collapse). Machinery still lands as inert, evaluable, opt-in — matching
  every other lever in this family (`--wr-tiebreak`, `--adp-prior`,
  `--rb-tail-calibration`, `--qb-starter-floor`, `--wind-adjust`, all
  HOLD, all shipped as opt-in flags).

## Protocol amendment slot

If neither mechanism as specified turns out to be implementable cleanly
against the real data shape (e.g., `pos_rank` ties break the rearrangement
assignment in some pathological way), any change will be documented here
as a dated amendment BEFORE running the 2022-2023 tuning grid — not
applied silently.

---

## Results

*(filled in after the pre-registration commit, per the task's execution
order — coverage/firing report first, then tuning, then the one-shot
2024 confirmation, then the shuffle test)*
