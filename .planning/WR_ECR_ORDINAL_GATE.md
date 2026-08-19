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

Baseline and treated backtests generated back-to-back in this session
(2026-08-18), same data vintage, no reused CSVs:
`output/backtest/ecr_gate_baseline_2022_2023/backtest_half_ppr_consensus_20260818_223317.csv`
(tuning set) and
`output/backtest/ecr_gate_baseline_2024/backtest_half_ppr_consensus_20260818_223455.csv`
(confirmation set), both `--weeks 1-18 --scoring half_ppr --vs-consensus
--consensus-source sleeper`. All `--ecr-anchor` configurations were applied
**post-hoc** to these baseline CSVs via direct calls to
`ecr_anchor.apply_ecr_anchor_{blend,near_tie}` per (season, week) — this is
mathematically identical to threading `--ecr-anchor` through the live CLI
(nothing else touches `projected_points` after that point in either
baseline run: no other opt-in lever was enabled, and `ranking_score`
explicitly does not modify `projected_points`). **Verified, not assumed**:
a live `--ecr-anchor` CLI run (smoke test, 2023 weeks 5-6, both modes) and
a full weekly `generate_projections.py --ecr-anchor` run were exercised
end-to-end before the grid search — see "Files changed."

### 1. Coverage / firing rate (BEFORE any result numbers, per pre-registration)

**WR-population ECR match rate**, tuning set and confirmation set:

| Season | WR rows | ECR WR rows (raw) | Team-resolved | Thursday/unresolved-excluded | Final matched | Match rate |
|---|---:|---:|---:|---:|---:|---:|
| 2022 | 1,545 | 2,739 | 1,448 | 119 | 1,329 | **86.0%** |
| 2023 | 1,621 | 2,738 | 1,520 | 131 | 1,389 | **85.7%** |
| 2024 | 1,560 | 2,446 | 1,336 | 126 | 1,210 | **77.6%** |

All three seasons clear the pre-registered 60% coverage flag comfortably —
no coverage-population caveat needed (contrast with `--adp-prior`'s
20-51% WR/TE coverage, which required exactly this flag). "Team-resolved"
< "ECR WR rows" reflects bye weeks / players not on a scheduled roster
that week; "Thursday/unresolved-excluded" is the leakage rule firing
(Thursday-game teams, plus the small number of rows whose team had no
resolvable kickoff at all — treated identically, per module docstring, as
not-provably-leak-free).

**Near-tie (`<=1.5pt` adjacent WR pair) ECR-match coverage** — the exact
subpopulation mechanism (b) targets, and the subpopulation mechanism (a)'s
reordering most affects:

| Season | Near-tie pairs | Both-members-matched | Rate |
|---|---:|---:|---:|
| 2022 | 1,515 | 1,202 | **79.3%** |
| 2023 | 1,594 | 1,253 | **78.6%** |
| 2024 | 1,537 | 1,038 | **67.5%** |

The ordinal metric's population is well inside ECR coverage in every
season — the opposite failure mode from the `--adp-prior` gate; no
"population mostly outside coverage" caveat applies here.

### 2. 2022-2023 tuning grid (primary gate)

Baseline WR ordinal Accuracy Gap (`ours - sleeper`, weeks 3-17, lower is
better), measured this session: **2022 = 0.43523**, **2023 = 0.31762**,
pooled 2022-2023 = **0.37643**. For reference, `WR_TIEBREAK_GATE.md`
(2026-08-09) measured 2022 = 0.45999, 2023 = 0.28614 on the same
season/window/pipeline — both this session's numbers are within
~0.02-0.03 of that prior run (same direction of day-to-day variance that
doc itself flagged, ~0.01-0.09, attributed to `rank(method="first")`
tie-breaking on a different day's data pull). Not a material discrepancy;
noted for anyone cross-referencing exact figures across sessions.

| Config | Pooled 2022-23 gap (base→treated) | Δ pooled | Δ 2022 | Δ 2023 | WR rows flagged | WR rows point-changed |
|---|---|---:|---:|---:|---:|---:|
| near_tie (mechanism b) | 0.37643 → 0.30749 | **-0.06894** | -0.09457 | -0.04331 | 1,980 | 1,678 |
| blend, w=0.1 | 0.37643 → 0.33221 | -0.04421 | -0.04456 | -0.04387 | 2,718 | 1,698 |
| blend, w=0.2 | 0.37643 → 0.29029 | -0.08614 | -0.09850 | -0.07377 | 2,718 | 2,167 |
| blend, w=0.3 | 0.37643 → 0.26243 | -0.11400 | -0.11579 | -0.11220 | 2,718 | 2,344 |
| blend, w=0.4 | 0.37643 → 0.22158 | -0.15485 | -0.14019 | -0.16950 | 2,718 | 2,454 |
| **blend, w=0.5** | 0.37643 → **0.15610** | **-0.22033** | -0.22893 | -0.21172 | 2,718 | 2,480 |

**Gate check (primary, tuning)**: required `>=0.05` pooled improvement,
sign-consistent both seasons. **blend, w=0.5 wins** — clears the bar by
**4.4x** (-0.220 vs -0.05 bar), monotonically increasing with weight
across the entire registered grid (0.1→0.5), sign-consistent in both 2022
(-0.229) and 2023 (-0.212) individually. **near_tie (mechanism b)** also
clears the bar on its own (-0.069, 1.4x), consistent with `--wr-tiebreak`'s
directionally-similar-but-weaker lever, but is dominated by every blend
weight `>=0.2`. **Mechanism (a), w=0.5 is the tuning-set winner.**

Note the grid is monotonically improving through the top of the registered
0.1-0.5 range — the true optimum may lie above 0.5; per pre-registration
the grid was not extended post-hoc after seeing this pattern (see
Caveats).

### 3. 2024 one-shot confirmation (winner: blend, w=0.5)

Run once, not iterated:

| | Base | Treated | Δ |
|---|---:|---:|---:|
| WR ordinal gap, 2024 | 0.40833 | 0.13439 | **-0.27394** |

**Gate check (confirmation)**: required directionally positive with
`>=50%` of the tuning-set per-season-average effect (-0.22033) retained.
Measured **-0.27394 → 124.3% retained** (stronger on the confirmation
season than on tuning). **PASSES.**

### 4. Guard checks

**MAE** (weeks 3-18; no regression permitted):

| Position | 2022-23 base | 2022-23 treated | Δ | 2024 base | 2024 treated | Δ |
|---|---:|---:|---:|---:|---:|---:|
| QB | 5.84928 | 5.84928 | 0.000000 | 6.42490 | 6.42490 | 0.000000 |
| RB | 4.63156 | 4.63156 | 0.000000 | 4.70233 | 4.70233 | 0.000000 |
| TE | 3.49117 | 3.49117 | 0.000000 | 3.46798 | 3.46798 | 0.000000 |
| WR | 4.32102 | 4.21853 | **-0.1025** | 4.55428 | 4.40946 | **-0.1448** |

WR MAE **improves** (does not regress) in both runs — clears the `<=0.02`
regression guard with room to spare. QB/RB/TE are **byte-identical to 6
decimal places** in both runs (also confirmed via row-level diff, next
line).

**Scoping proof**: full row-level merge of baseline vs treated —
**non-WR rows byte-identical**: confirmed True (n=4,424 rows, 2022-2023;
n=2,208 rows, 2024). **Unmatched WR rows (no ECR match) show exactly
0.000 projected-points delta**: confirmed, max `|Δ|` = 0.0 across 448
unmatched WR rows (2022-2023) and 409 unmatched WR rows (2024) — the
scoping-proof invariant holds with zero exceptions.

### 5. Deconfounded slices

- **Matched vs all**: 100% of the WR-population effect is concentrated in
  ECR-matched rows by construction (unmatched = exactly 0.0, above) — no
  leakage into the untouched 14-22% of the WR population.
- **Per-season sign consistency**: 2022 (-0.229) and 2023 (-0.212) both
  improve for the winning config — no sign flip.
- **Independent corroboration** (not pre-registered, run to understand the
  unusually large effect size): on the ECR-matched WR subset only
  (n=2,718, 2022-2023 pooled), pure ECR ordering itself (no blending —
  `ecr_pos_rank` used directly as the ranking) scores an Accuracy Gap of
  **5.851** vs Sleeper's **5.873** on that same subset — i.e., **ECR
  alone already narrowly beats Sleeper** on this metric — while our own
  baseline heuristic scores **6.174** on the identical subset (both
  external sources clearly beat our own ranking there). This explains the
  large effect size mechanically: blending toward ECR at w=0.5 is
  partially "borrowing" a source that independently already out-ranks
  Sleeper on this population, not an artifact of the reordering mechanism
  itself.

### 6. Shuffle / leak test

Pre-registered expectation: "the measured ordinal-gap effect must
collapse to approximately 0" when `ecr_pos_rank` is randomized within
each (season, week) group (same matched players, ranks reassigned via a
fixed-seed `numpy.random.default_rng(42).shuffle`).

| Mechanism | True-signal Δ (pooled 2022-23) | Shuffled-signal Δ | Result |
|---|---:|---:|---|
| near_tie (mechanism b) | -0.06894 | **-0.00592** (91% reduction) | **Collapses to ~0, as pre-registered.** |
| **blend, w=0.5 (winner)** | -0.22033 | **+0.92000** (inverts, does NOT collapse) | **Does not satisfy the literal pre-registered criterion.** |

**This is reported exactly as measured, including the miss.** The winning
mechanism's shuffle test did not collapse toward zero — it flipped to a
large regression, ~4.2x the magnitude of the true effect in the opposite
direction. Mechanism (b)'s shuffle test, run for comparison, collapsed
cleanly (91% reduction), confirming the shuffle-test methodology itself
works correctly in this codebase.

**Interpretation** (not a retroactive excuse — offered for the record):
mechanism (a) unconditionally reorders every ECR-matched WR every week
(2,718/2,718 rows flagged regardless of whether the signal agrees or
disagrees with our order), unlike mechanism (b)'s disagreement-gated
small nudge. At `w=0.5`, half the ranking information driving that
reorder becomes pure noise when shuffled — for a lever that reassigns
100% of the matched population's point values every week, injecting
50%-weight noise is not neutral, it actively misorders, which is
consistent with (not contradictory to) "the true effect is driven by real
signal content." A leak (e.g. some channel secretly informed by
`actual_points`) would be expected to persist near its original magnitude
under this shuffle, not invert — the inversion itself is evidence against
a leak explanation. That said, **the pre-registered criterion as literally
written was not satisfied**, and this doc does not retroactively loosen
it.

## Verdict: **HOLD** (on the pre-registered shuffle-test criterion, despite the primary/guard gates passing decisively)

| Criterion | Required | Measured | Result |
|---|---|---|---|
| Primary (tuning, pooled) | `>=0.05` improvement | -0.220 (4.4x bar) | **PASS** |
| Primary (per-season sign) | consistent both seasons | -0.229 / -0.212 | **PASS** |
| Confirmation (2024 one-shot) | `>=50%` retained, same direction | 124.3% retained | **PASS** |
| Guard: WR MAE | no regression `>0.02` | improves -0.10/-0.14 | **PASS** |
| Guard: non-WR byte-identical | exact | confirmed 2 ways | **PASS** |
| Guard: unmatched rows = 0 delta | exact | confirmed, max\|Δ\|=0.0 | **PASS** |
| Sanity: shuffle test collapses | effect → ~0 | **inverts to +0.92** | **FAIL** |

Per the pre-registered verdict rule ("SHIP only if... AND the shuffle test
collapses"), the shuffle-test criterion is not met for the winning
mechanism as literally specified, so the composite verdict is **HOLD** —
this doc does not loosen its own bar after seeing an inconvenient result,
even though the primary/guard evidence is unusually strong (this is the
opposite failure shape from every other HOLD in this repo's lever family,
which all missed on a weak primary signal; here the primary signal is
strong and the sanity check is what's in question). `--ecr-anchor` ships
as inert, opt-in, evaluable machinery (both modes wired), matching the
established pattern.

**Recommended follow-up, not applied in this session** (per pre-registered
process — no post-hoc protocol changes after seeing results): redesign
the shuffle-collapse bar for full-reorder mechanisms like blend (e.g.
compare against a null distribution of many random shuffles rather than a
single fixed seed, or gate the "collapses" criterion at a bound scaled to
how much of the population is reordered vs disagreement-gated) before
re-running this specific gate. The independent corroboration in section 5
(ECR itself already beats Sleeper on the matched subset) and mechanism
(b)'s clean shuffle-collapse are both reasons a future re-gate is likely
to find real signal here — this is flagged as a promising re-test
candidate, not a dead end, unlike a typical near-zero-firing-rate HOLD.

## Caveats / follow-ups

- **Grid ceiling**: the tuning grid's benefit was still increasing at
  `w=0.5`, the top of the registered range — the true optimal weight may
  be higher. Not explored here (would be post-hoc grid extension after
  seeing results, which the pre-registration explicitly rules out); a
  follow-up gate could pre-register a wider grid (e.g. 0.1-0.9).
  Related: at high weight this lever increasingly resembles "replace our
  WR ranking with FantasyPros' own ECR ordering (for matched players)"
  rather than a modest correction — worth naming explicitly for anyone
  reading `w=0.5` as a small nudge.
  - **2026 forward gate remains the true test** (constraint #1): all
  numbers above are 2022-2024 historical. No sealed 2025 exists for this
  lever. The genuine out-of-sample read is 2026 in-season, once our own
  daily FantasyPros rankings captures (`data/external/fantasypros_rankings.json`
  + archive) accumulate enough weeks — `--ecr-anchor` is not wired to
  that source yet (production note in the CLI help text).
- **Scoring mismatch** (constraint #3): ECR is PPR-only, our grading is
  half-PPR — not corrected for; plausibly contributes a small amount of
  noise to the (already very PPR-favorable) high-w blend result, not
  explored further here.

## Files changed

- `src/ecr_anchor.py` (new) — `compute_team_kickoff_dates()`,
  `build_ecr_lookup()` (Thursday-exclusion join + coverage stats),
  `apply_ecr_anchor_blend()` (mechanism a), `apply_ecr_anchor_near_tie()`
  (mechanism b, reuses `wr_tiebreak.EPSILON`/`NUDGE`), `apply_ecr_anchor()`
  dispatcher.
- `scripts/backtest_projections.py` — `--ecr-anchor` /
  `--ecr-anchor-mode {near_tie,blend}` / `--ecr-anchor-weight` CLI flags;
  `run_backtest(ecr_anchor=..., ecr_anchor_mode=..., ecr_anchor_weight=...)`;
  applied in the per-week loop after the WR tiebreak block, before wind
  adjust; output-filename tag.
- `scripts/generate_projections.py` — same CLI flags (weekly mode only;
  explicit no-op note in `--preseason`); applied after the WR tiebreak
  block; production-note print about the archive having no 2026 data.
- `tests/test_ecr_anchor.py` (new) — 22 unit tests: kickoff-date
  computation, Thursday-exclusion (incl. unresolved-team treated as
  excluded), coverage-denominator scoping, blend math (weight-zero no-op,
  weight-one full realization, value-multiset conservation, unmatched/
  non-WR passthrough, empty-lookup no-op), near-tie math (nudge-on-
  disagreement, no-nudge-on-agreement, epsilon threshold, missing-signal
  no-fire, non-negative clip), dispatcher (unknown-mode error, blend
  default-weight no-op), and a shuffle-collapse sanity test on a synthetic
  6-pair fixture. All passing (see Tests section below for the full-suite
  re-run).
- **Data**: none new — reuses the already-committed
  `data/silver/fp_ecr/season={2020..2024}/` (local-only, GPL-3.0/
  FP-scraped provenance, never committed — see
  `.planning/FP_ECR_HISTORY_COVERAGE.md`).
