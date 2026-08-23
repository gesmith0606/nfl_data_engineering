# Historical-Sleeper Weekly Consensus Anchor Gate — `--consensus-anchor-src sleeper` (2026-08-22)

Pre-registered BEFORE running any backtest results. Implements + gate-
evaluates the Sleeper-consensus-anchor hypothesis: historical weekly
Sleeper projections — which we already possess as our own grading
benchmark — blended into our WR (primary) / QB, RB, TE (exploratory
secondary) ordering, using the same mechanism family as `--ecr-anchor`
(`.planning/WR_ECR_ORDINAL_GATE.md`, which proved a rank-blend of an
independent weekly consensus source produces a large ordinal effect, 4.4x
its gate bar on the primary metric, though it ultimately HELD on a
shuffle-test design mismatch specific to its mechanism shape).

## Rationale

Sleeper is a SECOND, independent consensus source vs FantasyPros' ECR:
full population coverage (not ECR's top-60ish depth), longer/cleaner
archive (2022-2025 vs ECR's 2020-2024 with 2025 gaps), and exactly matching
scoring format (Sleeper's Bronze backfill is 100% `half_ppr`, verified
below — no PPR/half-PPR scoring mismatch, unlike the ECR gate's
constraint #3).

## CRITICAL DESIGN CONSTRAINTS (read before any results)

1. **Grading circularity — the central risk of this specific lever.**
   This lever blends OUR ranking directly toward Sleeper's OWN ranking,
   and Sleeper is also the source we grade "beat the consensus" claims
   against everywhere else in this repo (`weekly_grading_report.py`, the
   website's consensus comparison, `CONSENSUS_BENCHMARK_MULTI_SOURCE.md`).
   Any metric that compares "ours" to Sleeper's own numbers — matched-MAE
   vs Sleeper, or a raw rank-correlation with Sleeper — mechanically
   improves as blend weight increases, independent of whether the blend
   predicts anything real. **This is convergence to the benchmark, not
   model improvement**, and is reported as such, never as the primary gate
   metric.

   The PRIMARY metric is therefore the realized-outcome ordinal accuracy —
   `scripts/simulate_fp_accuracy.py`'s FantasyPros-style Accuracy Gap
   methodology, applied to OUR ranking alone: each player-week's rank is
   converted to a baseline point value via a rank-slot lookup table built
   **purely from actual realized points** (pooled across the sample), and
   the gap is `|baseline_points(our_rank) - actual_points|`. This number
   depends on Sleeper only insofar as blending toward Sleeper's order
   changes what rank a player lands at in OUR OWN ranking — it is never a
   direct comparison to Sleeper's projection or Sleeper's own rank. A
   "ours' gap − Sleeper's own gap" delta is additionally reported for
   context, **explicitly labeled convergence, not improvement** (as blend
   weight → 1, ours' rank order → Sleeper's rank order exactly, so this
   delta mechanically → 0 regardless of whether the blend helps).

   Guard metric (MAE) is likewise graded against actual_points directly
   (`mean(|projected - actual|)`), never against Sleeper's projected
   values — not circular.

2. **As-of / leak-safety (gate-0 check, done BEFORE any coverage or
   result number — this doc's version of the ELITE_MODELS_PLAN.md
   "Validity check (gate 0)").** Cross-referenced the 2022 injury report
   (`data/bronze/players/injuries/season=2022/`) against that week's
   Sleeper Bronze payload for every skill-position player marked `Out` in
   week 5, 2022 (n=30 QB/RB/WR/TE): **0/30 appear in the Sleeper payload at
   all** — they are omitted entirely rather than projected at ~0, which is
   the pre-registered signature ELITE_MODELS_PLAN.md's gate 0 called for.
   Stronger, individually-diagnostic corroboration: **Dak Prescott** (real
   thumb injury, out weeks 2-6 2022) is **absent from the Sleeper payload
   for weeks 3, 4, 5, 6** and **present** (with a nonzero projection) in
   weeks 1, 2 is also absent (pre-injury he'd have been present; he was hurt
   week 1 and missed the rest), and reappears week 7 (23.21 pts) and week 8
   (21.65 pts) — exactly tracking his real-world return. This is the
   expected fingerprint of a point-in-time, pre-game snapshot (the endpoint
   knows he's out before that week's games, the same way our own
   injury-adjustment pipeline does), not a retroactively-revised one.
   **Limitation, not a proven guarantee**: the exact intra-week capture
   time (Tuesday? Sunday morning?) is unknown, and this endpoint's behavior
   for BACKFILL requests (this repo hit it well after the fact, in 2026,
   for 2022-2025 weeks) is not independently documented by Sleeper — the
   evidence above is strong circumstantial confirmation, not a vendor
   guarantee. No Thursday-exclusion rule is applied (unlike `--ecr-anchor`'s
   FP-ECR archive, scraped on a fixed weekly cadence after some games have
   already kicked off) because there is no equivalent fixed-cadence
   after-the-fact scrape date recorded in this data to exclude against —
   documented as an accepted, evidence-backed limitation.

3. **Scoring format.** Verified directly: every sampled season/week
   (2022 w5, 2023 w5, 2024 w5, 2025 w5) of Bronze
   `data/bronze/external_projections/sleeper/` carries
   `scoring_format == "half_ppr"` exclusively — matches this repo's
   grading format exactly. No PPR/half-PPR correction needed (contrast
   `--ecr-anchor` constraint #3).

4. **Join key.** Bronze Sleeper rows already carry `player_id` resolved to
   this repo's `gsis_id` convention at ingestion time
   (`scripts/ingest_external_projections_sleeper.py`'s
   `nfl_data_py.import_ids()` + `PlayerNameResolver` fallback strategy).
   Verified directly against Bronze `players/weekly.player_id` in the
   gate-0 check above (the join worked with zero special-casing). No
   name-join anywhere in this module.

5. **Protocol deviation from the `--ecr-anchor` precedent.** That gate
   tuned on 2022-2023 and one-shot-confirmed on 2024 because no sealed 2025
   ECR archive exists (FP-ECR scraping stopped Aug 2025). Sleeper's
   archive has full 18-week coverage for **2022, 2023, 2024, AND 2025**
   (verified: `data/bronze/external_projections/sleeper/season={2022..
   2025}/week={01..18}/` all present; `data/bronze/players/weekly/
   season=2025/` actuals also present), and this specific lever family
   (blend-toward-historical-Sleeper) has never been run or tuned against
   2025 data before this session. Per the task's "prefer the longest clean
   holdout" instruction: **tune on 2022-2023-2024 pooled, seal-confirm
   once on 2025** — a genuinely clean one-shot rather than the ECR gate's
   "provisional pending 2026" position.

## Data — no new ingestion required

`data/bronze/external_projections/sleeper/season={2022..2025}/week={01..
18}/sleeper_*.parquet` (already committed, Phase 1.1 historical backfill —
see `.planning/ELITE_MODELS_PLAN.md` §1.1). Columns used: `player_id`,
`position`, `projected_points`, `scoring_format`.

## Lever implemented

`src/sleeper_consensus_anchor.py` (new module, does not import or modify
`src/ecr_anchor.py` — mirrors its design, does not depend on it):

- `build_sleeper_lookup(proj_df, season, week, position, bronze_dir=...) ->
  (lookup_df, stats)` — loads that week's Sleeper rows at `position`, ranks
  them by Sleeper's own `projected_points` descending
  (`sleeper_pos_rank`), joins to `proj_df` by `player_id`. `stats`:
  `n_proj_pos_rows`, `n_sleeper_pos_rows`, `n_final_matched` (the
  coverage-report denominators).
- `apply_consensus_anchor(proj_df, lookup_df, position, mode, weight=None,
  epsilon=EPSILON, nudge=NUDGE, points_col="projected_points") -> proj_df`
  — dispatches to one of two pre-registered mechanisms (both reused
  verbatim in shape from `ecr_anchor.py`, generalized to accept any
  `position` rather than hardcoded WR). Rows outside `position` and
  unmatched rows are returned byte-identical (the scoping-proof invariant).
  New provenance column `sleeper_anchor_flag` (bool).

### Mechanism (a): rank-blend

`blended_rank = (1-w)*our_rank + w*sleeper_pos_rank` for Sleeper-matched
rows at `position` only; the matched subset's own point values are sorted
descending and reassigned to players in ascending-blended-rank order
(rearrangement-inequality-minimal reassignment, identical technique to
`ecr_anchor.apply_ecr_anchor_blend`). Weight `w` tuned on a grid
`{0.1, 0.2, 0.3, 0.4, 0.5}` on 2022-2024 pooled, WR primary.

### Mechanism (b): near-tie-only variant

Reuses `wr_tiebreak.py`/`ecr_anchor.py`'s exact adjacent-pair clustering
constants (`EPSILON=1.5`, `NUDGE=0.5`) — for every adjacent pair at
`position` (sorted by `projected_points` descending) whose gap is
`<= EPSILON`, if `sleeper_pos_rank` disagrees with our order and both
members are Sleeper-matched, nudge apart by `NUDGE` each.

Both are registered; the tuning-set winner (by primary-gate margin) is
carried to the 2025 one-shot confirmation.

**Wiring** (opt-in, mirrors `--ecr-anchor`):
- `scripts/generate_projections.py --consensus-anchor-src sleeper
  [--consensus-anchor-position {QB,RB,WR,TE}] [--consensus-anchor-mode
  {near_tie,blend}] [--consensus-anchor-weight W]` (weekly mode only;
  explicit no-op note printed in `--preseason`).
- `scripts/backtest_projections.py --consensus-anchor-src sleeper
  [--consensus-anchor-position ...] [--consensus-anchor-mode ...]
  [--consensus-anchor-weight ...]` — threads the lever into
  `run_backtest()`, applied in the per-week loop right after the
  `--ecr-anchor` block, before `--wind-adjust`. No training/fitting step
  needed — Sleeper's historical projection is same-week pre-game public
  information (per the gate-0 leak-safety check), not a regression target
  fit on prior data, so every eval season reads its own year's Sleeper
  data directly.

## Pre-registered gate

**Coverage/firing rate is reported BEFORE any Accuracy-Gap/MAE numbers**
(per `knowledge-vault/concepts/gated-experiment-coverage-check.md`):
- Sleeper-match rate among the graded WR population, per season
  (2022-2025), and for QB/RB/TE (exploratory secondaries).
- Sleeper-match rate specifically among the near-tie subpopulation
  (adjacent WR pairs `<=1.5pt` apart in our own projections).
- If any season's overall WR match rate is `<60%`, flagged explicitly
  before results are read (mirrors `--ecr-anchor`/`--adp-prior` convention).

**Gates** (WR primary; QB/RB/TE reported as exploratory, same thresholds,
non-blocking for the WR verdict):
- **PRIMARY**: WR realized-outcome ordinal Accuracy Gap for OUR ranking
  alone (weeks 3-17, rank-slot baseline table built from actual points,
  `scripts/simulate_fp_accuracy.py` methodology) improves (decreases) by
  `>=0.05` on the 2022-2024 pooled tuning set, AND is directionally
  positive with `>=50%` of the tuning-set per-season-average effect
  retained on the 2025 one-shot confirmation.
- **GUARD**:
  - WR MAE (vs actual_points, not vs Sleeper) does not regress by more
    than `0.02` anywhere (tuning set or 2025 confirmation).
  - Positions/rows outside the anchored `position` are byte-identical
    between baseline and treated (full row-level diff).
  - Player-weeks with no Sleeper match show exactly `0.000`
    projected-points delta (scoping-proof invariant).
  - Per-season sign consistency required across 2022/2023/2024 for the
    tuning-set winner — reject if sign flips between any two seasons.

**Convergence report (NOT a gate; context only, per constraint #1)**:
- "Ours' Accuracy Gap − Sleeper's own Accuracy Gap" delta, baseline vs
  treated, explicitly labeled convergence.
- Raw rank agreement (Spearman) between our treated ranking and Sleeper's
  ranking, baseline vs treated — also labeled convergence.

**Sanity/leak test — REDESIGNED per
`knowledge-vault/concepts/shuffle-test-must-match-mechanism-shape.md`**
(mandatory per task instructions, used from day one rather than the
single-shuffle-collapse design the `--ecr-anchor` gate pre-registered and
then found didn't fit its blend mechanism after the fact):
- **near_tie (disagreement-gated mechanism)**: single shuffle of
  `sleeper_pos_rank` within each (season, week) group; expect the measured
  effect to **collapse toward ~0** (this mechanism only fires on
  disagreement, so randomizing turns roughly half the firings into
  no-op agreements).
- **blend (full-reorder/weighted mechanism)**: build a **K=100
  shuffled-delta null** (100 independent shuffles of `sleeper_pos_rank`
  within each (season, week) group, rerun the winning weight each time,
  recompute the primary metric) and test the TRUE-signal primary-metric
  improvement against that null via a **one-sided empirical p-value**
  (fraction of null draws at least as good as the true effect); require
  `p < 0.05`. This is the "no better than a w-weighted random reordering"
  null the vault note prescribes for full-reorder mechanisms, replacing
  the ECR gate's mismatched single-shuffle-collapse expectation for this
  mechanism shape.

## Verdict rules

- **SHIP-PENDING-USER** (default framing for any lever in this family,
  matching `--ecr-anchor`/`--wr-tiebreak`/`--adp-prior` precedent) only if
  the primary gate clears on 2022-2024 tuning AND the 2025 one-shot
  confirms AND the guard passes AND the shape-appropriate shuffle test
  passes. Machinery lands as opt-in regardless of verdict; no
  `generate_projections.py`/`backtest_projections.py` DEFAULT changes in
  this session even on SHIP-PENDING-USER (matches every prior lever in
  this family — changing shipped model behavior 3 weeks before the draft
  is a user decision).
- **HOLD** otherwise (primary misses on tuning, fails to hold on the 2025
  one-shot, guard fails, or the shape-appropriate shuffle test fails).
  Machinery still lands as inert, evaluable, opt-in.

## Protocol amendment slot

Any change to the above (e.g. if the shuffle-null harness needs
adjustment once run against real per-week backtest loops rather than the
synthetic test fixture) will be documented here, dated, BEFORE running the
2022-2024 tuning grid — not applied silently.

---

## Results

_(appended after pre-registration commit — see below)_
