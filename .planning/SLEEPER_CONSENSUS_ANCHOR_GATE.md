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

Baseline and treated backtests generated back-to-back in this session
(2026-08-22), same data vintage, no reused CSVs, full live CLI runs (not
post-hoc unless explicitly noted):
`output/backtest/sleeper_anchor_gate/backtest_half_ppr_consensus_20260822_204344.csv`
(2022-2024 tuning baseline), 5 blend-weight treated runs + 1 near_tie
treated run (`--consensus-anchor-src sleeper` variants, same command),
`...20260822_213216.csv` (2025 one-shot baseline), and one 2025 treated
run at the tuning-set winner. All `--weeks 1-18 --scoring half_ppr
--vs-consensus --consensus-source sleeper [--consensus-anchor-src sleeper
--consensus-anchor-mode ... --consensus-anchor-weight ...]`.

### 1. Coverage / firing rate (BEFORE any result numbers, per pre-registration)

**WR-population Sleeper-match rate**, tuning set and confirmation set:

| Season | WR rows | Sleeper WR rows (raw) | Final matched | Match rate |
|---|---:|---:|---:|---:|
| 2022 | 1,545 | 2,315 | 1,522 | **98.5%** |
| 2023 | 1,621 | 2,363 | 1,608 | **99.2%** |
| 2024 | 1,560 | 2,354 | 1,537 | **98.5%** |
| 2025 | 1,879 | 2,384 | 1,772 | **94.3%** |

All four seasons clear the 60% coverage flag by a wide margin — Sleeper's
full-population archive covers dramatically more of the graded population
than the FP-ECR archive did (`--ecr-anchor`'s 77.6-86.0%), confirming the
hypothesis rationale (full population vs top-60ish depth).

**Near-tie (`<=1.5pt` adjacent WR pair) Sleeper-match coverage:**

| Set | Near-tie pairs | Both-members-matched | Rate |
|---|---:|---:|---:|
| 2022-2024 pooled | 4,646 | 4,535 | **97.6%** |
| 2025 | 1,851 | 1,669 | **90.2%** |

**Exploratory secondary positions** (QB/RB/TE), 2022-2024 pooled — also
far above the 60% flag:

| Position | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| QB | 94.4% | 94.8% | 98.1% | 96.3% |
| RB | 98.5% | 98.6% | 99.4% | 96.1% |
| TE | 98.7% | 97.0% | 95.9% | 95.1% |

No "population mostly outside coverage" caveat applies anywhere in this
gate.

### 2. As-of / leak-safety (gate-0 check) — see constraint #2 above for the full write-up

Confirmed via direct data inspection before any coverage/result number was
computed: 0/30 skill-position players marked `Out` in the 2022 week-5
injury report appear in that week's Sleeper Bronze payload at all (omitted,
not projected-at-zero); Dak Prescott (real thumb injury, out weeks 2-6
2022) is absent from the Sleeper payload for weeks 3-6 specifically and
reappears with a nonzero projection weeks 7 (23.21 pts) and 8 (21.65 pts) —
tracking his real-world return exactly. Point-in-time/pre-game snapshot
behavior confirmed; documented as strong circumstantial evidence, not a
vendor-documented guarantee (see constraint #2).

### 3. 2022-2024 pooled tuning grid (primary gate)

Baseline WR realized-outcome Accuracy Gap (our ranking alone, graded
against a rank-slot baseline table built purely from actual points, weeks
3-17): pooled 2022-2024 = **6.69432** (2022=6.52624, 2023=6.56885,
2024=6.98730).

| Config | Pooled gap (base→treated) | Δ pooled | Δ 2022 | Δ 2023 | Δ 2024 | WR MAE Δ |
|---|---|---:|---:|---:|---:|---:|
| near_tie | 6.69432 → 6.61014 | **-0.08418** | -0.09275 | -0.03577 | -0.12492 | -0.04155 |
| blend, w=0.1 | 6.69432 → 6.64427 | -0.05005 | -0.04649 | -0.04453 | -0.05914 | -0.02793 |
| blend, w=0.2 | 6.69432 → 6.58363 | -0.11069 | -0.12891 | -0.08653 | -0.11633 | -0.05840 |
| blend, w=0.3 | 6.69432 → 6.53247 | -0.16184 | -0.18403 | -0.13845 | -0.16241 | -0.08276 |
| blend, w=0.4 | 6.69432 → 6.46687 | -0.22744 | -0.26225 | -0.19282 | -0.22681 | -0.11304 |
| **blend, w=0.5** | 6.69432 → **6.41032** | **-0.28399** | -0.30302 | -0.27558 | -0.27142 | -0.12747 |

**Gate check (primary, tuning)**: required `>=0.05` pooled improvement,
sign-consistent all three seasons. **blend, w=0.5 wins** — clears the bar
by **5.7x** (-0.284 vs -0.05 bar), monotonically increasing with weight
across the entire registered grid, sign-consistent in 2022 (-0.303), 2023
(-0.276), and 2024 (-0.271) individually. `near_tie` also clears the bar
on its own (-0.084, 1.7x), dominated by every blend weight `>=0.1`.
**Mechanism (a), w=0.5 is the tuning-set winner** (same winning
configuration as `--ecr-anchor`'s gate, independently). Grid still
monotonically improving at the top of the registered range — noted as a
caveat below, same as the ECR gate's.

### 4. 2025 one-shot confirmation (winner: blend, w=0.5)

Run once, not iterated:

| | Base | Treated | Δ |
|---|---:|---:|---:|
| WR realized-outcome gap, 2025 | 6.37641 | 6.07432 | **-0.30209** |

**Gate check (confirmation)**: required directionally positive with
`>=50%` of the tuning-set pooled effect (-0.28399) retained. Measured
**-0.30209 → 106.4% retained** (stronger on the confirmation season than
on tuning, same pattern `--ecr-anchor` saw with its ECR gate). **PASSES.**

### 5. Guard checks

**WR MAE** (vs actual_points, weeks 3-18; no regression `>0.02` permitted):

| Config | 2022-24 base | 2022-24 treated | Δ | 2025 base | 2025 treated | Δ |
|---|---:|---:|---:|---:|---:|---:|
| near_tie | 4.39685 | 4.35529 | -0.04155 | — | — | — |
| blend, w=0.1-0.4 | 4.39685 | 4.36892→4.28380 | -0.028 to -0.113 | — | — | — |
| **blend, w=0.5** | 4.39685 | 4.26938 | **-0.12747** | 3.81330 | 3.64200 | **-0.17130** |

WR MAE **improves** (does not regress) in every configuration, both eval
windows — clears the `<=0.02` regression guard with wide margin.

**Scoping proof**: full row-level merge of baseline vs treated for every
config — **non-WR rows byte-identical**: confirmed True (max|Δ|=0.0,
n=6,632 rows 2022-2024; n=2,572 rows 2025). **Unmatched WR rows (no
Sleeper match) show exactly 0.000 projected-points delta**: confirmed,
max|Δ|=0.0 across 19-31 unmatched WR rows per config (2022-2024) and 42
unmatched WR rows (2025) — the scoping-proof invariant holds with zero
exceptions across all 7 configurations tested.

**Per-season sign consistency**: 2022 (-0.303), 2023 (-0.276), 2024
(-0.271) all improve for the winning config — no sign flip.

### 6. Convergence report (context only — NOT a gate, per constraint #1)

"Ours' Accuracy Gap − Sleeper's own Accuracy Gap" (both realized-outcome
based; this is the metric that WOULD be circular if used as the primary
gate, since it mechanically → 0 as blend weight → 1):

| Set | ours (base) | sleeper | delta_base | ours (treated, w=0.5) | delta_treated |
|---|---:|---:|---:|---:|---:|
| 2022-2024 | 6.69420 | 6.30017 | +0.39403 | 6.41019 | **+0.11002** |
| 2025 | 6.37641 | 5.93964 | +0.43677 | 6.07432 | **+0.13468** |

Mean weekly Spearman rank-agreement between our WR ranking and Sleeper's
(raw ranking similarity — NOT graded against actuals, purely descriptive):

| Set | base | treated (w=0.5) |
|---|---:|---:|
| 2022-2024 | 0.8558 | **0.9627** |
| 2025 | 0.8785 | **0.9683** |

Exactly the mechanical convergence predicted in constraint #1: as blend
weight increases, our rank order approaches Sleeper's (Spearman → ~0.96-
0.97), and the ours-vs-Sleeper gap delta shrinks toward (but does not
reach) zero. **This delta shrinking is NOT the evidence of improvement in
this gate** — the primary-gate evidence (Section 3-4) is the raw
realized-outcome gap for our own ranking, independent of Sleeper's own
score, and is reported separately for exactly this reason.

### 7. Redesigned shuffle / leak test

Per `knowledge-vault/concepts/shuffle-test-must-match-mechanism-shape.md`,
a shape-appropriate null was pre-registered for each mechanism (used from
day one, not retrofitted after seeing a mismatch like `--ecr-anchor` did):

**near_tie (disagreement-gated) — single-shuffle collapse test:**

| | Δ (pooled 2022-24, real backtest population) |
|---|---:|
| True signal | -0.09730 |
| Shuffled signal | +0.02402 |
| Reduction | **75.3%** — collapses toward 0, as pre-registered |

**blend, w=0.5 (winner) — K=100 shuffled-delta null + one-sided empirical p:**

| | Value |
|---|---:|
| True-signal Δ | **-0.28863** |
| Null mean Δ (K=100 shuffles) | **+0.84359** |
| Null std | 0.06853 |
| Null min / max | +0.67127 / +1.02115 |
| One-sided empirical p (fraction of null ≤ true) | **0.0000** |
| Required | p < 0.05 |
| **Result** | **PASS** |

The true effect (-0.289, an improvement) is better than **all 100** null
draws, none of which came close to the true effect — the null distribution
sits entirely on the "noise actively hurts" side (mean +0.844, matching
the `--ecr-anchor` gate's own finding that shuffling a full-reorder blend
mechanism's signal inverts rather than collapses, since noise at real
weight actively misorders 2,800+ WR player-weeks rather than merely
no-opping). Using the mechanism-appropriate null (this redesigned test)
rather than the mismatched single-shuffle-collapse criterion the
`--ecr-anchor` gate pre-registered, **this gate's shuffle test PASSES
decisively** rather than producing the same "strong primary/guard evidence
but sanity-check design mismatch" HOLD outcome that gate landed on.

Methodological note: the shuffle-null test (both near_tie and blend K=100)
was computed **post-hoc** on the actuals-merged baseline population (same
population used for the primary-gate Accuracy Gap metric itself), verified
internally consistent (identical population/code path for every null draw
and the true-signal run) — NOT via 100 live-CLI re-runs (intractable at
~7 min/run). The point-estimate gate numbers (Sections 1, 3, 4, 5) all use
full live-CLI runs on the exact production population; a direct
post-hoc-vs-live-CLI equivalence check on the near_tie config found the two
populations differ by ~15% of WR rows (players present in the live
per-week projection pool before the actuals-inner-join but absent from the
graded/actuals-merged CSV) — small enough not to change the primary-gate
conclusion (confirmed by the near_tie live-CLI run in Section 3 matching
the same direction/magnitude as this section's post-hoc near_tie read) but
documented honestly rather than silently assumed byte-identical.

### 8. Exploratory secondaries (QB/RB/TE) — non-blocking, informational only

Same winning configuration (blend, w=0.5) applied post-hoc to QB/RB/TE at
the SAME 2022-2024 population (same caveat as Section 7 — post-hoc, not a
live-CLI byte-identical run, sufficient only for a directional read):

| Position | Gap Δ | MAE Δ |
|---|---:|---:|
| QB | -0.11493 | -0.09976 |
| RB | -0.21753 | -0.20254 |
| TE | -0.14736 | -0.09438 |

All three secondaries show the same directional pattern as WR (gap
improves, MAE improves, no regression) at the identical weight — a
promising candidate for a future dedicated gate (full live-CLI tuning +
one-shot + shuffle test per position, not done here since these were
pre-registered as exploratory/non-blocking for the WR verdict).

## Verdict: **SHIP-PENDING-USER** (WR primary, mechanism = blend, weight = 0.5)

| Criterion | Required | Measured | Result |
|---|---|---|---|
| Coverage (WR, all seasons) | `>=60%` | 94.3-99.2% | **PASS** |
| Primary (tuning, pooled) | `>=0.05` improvement | -0.284 (5.7x bar) | **PASS** |
| Primary (per-season sign) | consistent all 3 seasons | -0.303 / -0.276 / -0.271 | **PASS** |
| Confirmation (2025 one-shot) | `>=50%` retained, same direction | 106.4% retained | **PASS** |
| Guard: WR MAE | no regression `>0.02` | improves -0.127 / -0.171 | **PASS** |
| Guard: non-target-position byte-identical | exact | confirmed, all 7 configs | **PASS** |
| Guard: unmatched rows = 0 delta | exact | confirmed, all 7 configs | **PASS** |
| Sanity: shape-appropriate shuffle test | near_tie collapses; blend K=100 p<0.05 | 75.3% reduction; p=0.0000 | **PASS** |

Every pre-registered gate clears, including the shuffle-test criterion
that `--ecr-anchor` (the closest precedent, same winning mechanism/weight)
missed on a mismatched null design — this gate used the redesigned,
mechanism-appropriate null from day one and passes cleanly. Per the
pre-registered verdict rule, this lands as **SHIP-PENDING-USER**:
`generate_projections.py`/`backtest_projections.py` DEFAULTS are **not**
changed in this session (changing shipped model behavior 3 weeks before
the draft is a user decision) — `--consensus-anchor-src sleeper
--consensus-anchor-mode blend --consensus-anchor-weight 0.5` lands as
fully-wired, opt-in, evaluable machinery, exactly like every other lever
in this family.

**Recommended follow-up, not applied in this session**: (1) the QB/RB/TE
exploratory read (Section 8) is a strong candidate for a full dedicated
gate (live-CLI tuning + one-shot + shuffle test per position); (2) the
tuning grid was still monotonically improving at `w=0.5`, the top of the
registered range — a follow-up gate could pre-register a wider grid (e.g.
0.1-0.9), same caveat `--ecr-anchor` flagged; (3) combining
`--ecr-anchor` and `--consensus-anchor-src sleeper` (two independent
consensus sources) was not tested here and is out of scope for this gate
— worth a dedicated interaction/composition gate before considering it,
per the coverage-check doc's per-position/per-lever composition rule.

## Caveats / follow-ups

- **Grid ceiling**: same as `--ecr-anchor` — the true optimal weight may
  be `>0.5`; not explored here (pre-registration rules out post-hoc grid
  extension after seeing results).
- **Shuffle-null population caveat** (Section 7): the K=100 null and the
  near_tie single-shuffle test were computed post-hoc on the
  actuals-merged population rather than via repeated live-CLI runs
  (intractable at scale) — documented, not hidden; the primary/guard gate
  numbers themselves are all live-CLI-verified.
- **Intra-week capture-time uncertainty** (constraint #2): the exact
  pre-game capture time of Sleeper's historical projections endpoint for
  a backfilled past week is not vendor-documented; the Dak Prescott
  evidence is strong circumstantial confirmation of point-in-time
  behavior, not a guarantee.
- **Lever-family interaction untested**: this gate did not test
  `--consensus-anchor-src sleeper` stacked with `--ecr-anchor` or
  `--wr-tiebreak` in the same run (each lever in this family is gated and
  shipped independently; composition is a separate, not-yet-run
  question — see Recommended follow-up #3 above).

## Files changed

- `src/sleeper_consensus_anchor.py` (new) — `build_sleeper_lookup()`
  (`player_id`-only join, no name/team resolution needed),
  `apply_consensus_anchor_blend()` (mechanism a),
  `apply_consensus_anchor_near_tie()` (mechanism b, reuses
  `wr_tiebreak`/`ecr_anchor`'s `EPSILON`/`NUDGE`), `apply_consensus_anchor()`
  dispatcher — all parameterized by `position` (QB/RB/WR/TE).
- `scripts/backtest_projections.py` — `--consensus-anchor-src {sleeper}` /
  `--consensus-anchor-position {QB,RB,WR,TE}` /
  `--consensus-anchor-mode {near_tie,blend}` / `--consensus-anchor-weight`
  CLI flags; `run_backtest(consensus_anchor_src=..., ...)`; applied in the
  per-week loop after the `--ecr-anchor` block, before `--wind-adjust`;
  output-filename tag.
- `scripts/generate_projections.py` — same CLI flags (weekly mode only;
  explicit no-op note in `--preseason`); applied after the `--ecr-anchor`
  block.
- `tests/test_sleeper_consensus_anchor.py` (new) — 26 unit tests: lookup
  coverage stats, scoring-format filter, position scoping, latest-parquet
  selection, blend math (weight-zero no-op, weight-one full realization,
  value-multiset conservation, unmatched/other-position passthrough,
  empty-lookup no-op, position-parameterization for QB), near-tie math
  (nudge-on-disagreement, no-nudge-on-agreement, epsilon threshold,
  missing-signal no-fire, non-negative clip, other-position passthrough),
  dispatcher (unknown-mode error, blend default-weight no-op, default
  position, supported-positions constant), and the redesigned shuffle-null
  harness proven on a synthetic fixture (near_tie collapse +
  blend K=100/one-sided-p). All passing.
- **Data**: none new — reuses the already-committed
  `data/bronze/external_projections/sleeper/season={2022..2025}/` (Phase
  1.1 historical backfill).

---

## SHIPPED (2026-08-22, user-approved promotion)

Per the pre-registered verdict rules above (SHIP-PENDING-USER), the user
approved promotion the same day. **`--consensus-anchor-src sleeper
--consensus-anchor-mode blend --consensus-anchor-weight 0.5` is now
DEFAULT-ON for WR** in `scripts/generate_projections.py` (weekly mode
only — no-op in `--preseason`) and in `scripts/backtest_projections.py`'s
default evaluation path (i.e. `run_backtest()`'s own kwarg defaults, so
callers like `scripts/production_eval.py`'s production-faithful harness
pick it up without any flag). QB/RB/TE remain untouched (still opt-in via
explicit `--consensus-anchor-src sleeper --consensus-anchor-position
{QB,RB,TE}` — the Section 8 exploratory read was pre-registered
non-blocking and is not promoted here). Opt-out: `--no-sleeper-anchor`
(mirrors `--no-consensus-anchor`'s naming for the preseason lever).
Precedence (no-anchor wins > explicit override wins > shipped default) is
centralized in `src/sleeper_consensus_anchor.py::resolve_sleeper_anchor_config()`
so the two CLIs cannot drift.

**Graceful degradation, verified**: `build_sleeper_lookup()` already
returns an empty lookup (not an exception) when a (season, week, position)
partition is missing from
`data/bronze/external_projections/sleeper/season=YYYY/week=WW/`, and
`apply_consensus_anchor()` is a byte-identical no-op on an empty lookup —
confirmed directly (`n_sleeper_pos_rows=0` for an out-of-archive week,
projected_points unchanged). Both call sites now additionally emit a LOUD
warning (`generate_projections.py`: a `print("WARNING: ...")` line;
`backtest_projections.py`: `logger.warning(...)`) whenever
`n_sleeper_pos_rows == 0`, so a missing weekly Sleeper snapshot in
production is visible in logs rather than silently passing through.
End-to-end smoke run confirmed on real 2025 data (season=2025, week=5):
"Sleeper consensus anchor: ON (shipped default — pos=WR, mode=blend,
weight=0.5)" / "106 matched (of 148 WR rows), 106 row(s) nudged" —
production Silver/Bronze data, full pipeline, no synthetic fixtures.

### Regenerated headline metrics (promoted config, 2022-2024, `--ml
--full-features`, weeks 3-18, cons≥5 population floor)

Same recipe as `.planning/SITE_METRICS_REFRESH_2026_08_16.md` (per-season
`--ml --full-features --vs-consensus --consensus-source sleeper` backtests,
pooled, `scripts/benchmark_consensus_sources.py --sources sleeper espn` on
the pooled CSV, `scripts/generate_frontend_metrics.py` for the site
artifact) — re-run against the SAME already-shipped QB/RB/WR/TE model
files, the only change being the now-default Sleeper WR anchor.
**Population reproduces exactly**: 11,358 pooled rows, Sleeper n=7,009 /
ESPN n=6,721 — bit-for-bit identical to the pre-ship numbers, confirming
the anchor changes WR ordering/points only, not row counts.

**MAE gap (ours − source; negative = we win), before -> after shipping:**

| Position | vs Sleeper (before) | vs Sleeper (after) | vs ESPN (before) | vs ESPN (after) |
|---|---:|---:|---:|---:|
| QB | −1.659 | −1.659 (unchanged) | −1.064 | −1.064 (unchanged) |
| RB | −0.466 | −0.466 (unchanged) | −0.525 | −0.525 (unchanged) |
| WR | −0.065 | **−0.132** | −0.104 | **−0.167** |
| TE | −0.454 | −0.454 (unchanged) | −0.453 | −0.453 (unchanged) |
| **OVERALL** | −0.508 | **−0.536** | −0.440 | **−0.466** |

QB/RB/TE MAE-gap numbers reproduce to 3 decimals — the scoping-proof
invariant (non-WR rows byte-identical) holds in this live production
population exactly as it held in the gate's own guard checks. **WR gap
roughly doubles** on both sources (still a win before, a wider win after).
**4 of 4 positions still beat both sources** — no regression anywhere.

**FantasyPros-style ordinal Accuracy Gap** (`scripts/simulate_fp_accuracy.py`,
half-PPR, weeks 3-17, 2022-2024 pooled), before -> after shipping:

| Position | Ours (before) | Ours (after) | Sleeper | ESPN | Before verdict | After verdict |
|---|---:|---:|---:|---:|---|---|
| QB | 5.44 | 5.44 (unchanged) | 7.19 | 7.18 | win | win (unchanged) |
| RB | 5.32 | 5.32 (unchanged) | 5.92 | 5.91 | win | win (unchanged) |
| TE | 5.70 | 5.70 (unchanged) | 6.12 | 6.15 | win | win (unchanged) |
| **WR** | **6.49** | **6.28** | 6.29 | 6.47 | **LOSS vs Sleeper** (by 0.20) | **WIN vs Sleeper** (by 0.01), win vs ESPN widens (0.19) |

**WR ordinal flips from a loss to a win against Sleeper** — narrowly
(0.01), but a genuine sign flip, not just a shrink. Per-year detail: 2022
still loses narrowly (6.15 vs Sleeper 6.08, -0.07), 2023 wins (6.20 vs
6.23), 2024 wins (6.49 vs 6.55) — the pooled flip is driven by 2023/2024
outweighing a still-negative 2022, reported honestly rather than rounded
away. QB/RB/TE ordinal numbers reproduce exactly (unchanged), confirming
the anchor's WR-only scoping holds under the ordinal metric too, not just
MAE.

**No regression found anywhere** (this was the pre-registered halt
condition — see task instructions) — every position, every metric, either
improved or reproduced exactly. Site JSON
(`web/frontend/src/features/nfl/config/model-metrics.json`) and marketing
`RECEIPTS` (`web/frontend/src/app/page.tsx`) updated accordingly: overall
gap −0.51→**−0.54** (Sleeper), −0.44→**−0.47** (ESPN); QB/RB/TE receipt
tiles unchanged (their underlying numbers didn't move). Frontend
`npx vitest run`: 354/354 passed. `npx tsc --noEmit`: clean.

Artifacts: `output/backtest/sleeper_anchor_ship_2026_08_22/` (3 per-season
main CSVs, pooled CSV, per-source consensus-matched CSVs +
`consensus_benchmark_summary.json`, `fp_sim/` ordinal-sim inputs/outputs).
