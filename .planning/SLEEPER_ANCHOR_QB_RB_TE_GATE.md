# Sleeper Consensus Anchor — QB/RB/TE Per-Position Gates (2026-08-23)

Pre-registered BEFORE running any tuning/one-shot/shuffle results. This is
the dedicated follow-up gate flagged as "Recommended follow-up #1" in
`.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md` (the WR gate, SHIPPED
2026-08-22): that gate's Section 8 found QB/RB/TE moved the same direction
as WR at the same post-hoc weight (w=0.5) but explicitly scoped that
finding as exploratory/non-blocking, "a strong candidate for a future
dedicated gate (live-CLI tuning + one-shot + shuffle test per position)."
This doc is that dedicated gate.

## Why this is harder than the WR gate

QB/RB/TE are not underperforming positions looking for a lever — they
**already win** the realized-outcome ordinal Accuracy Gap against Sleeper
consensus (QB 5.44 vs Sleeper 7.19, RB 5.32 vs 5.92, TE 5.70 vs 6.12 —
`.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md`'s post-ship headline table).
WR's gate was improvement on a **loss**; this gate is improvement on a
**win**, so:

- The bar for shipping is not "does it help" alone — it must help
  **without compromising what already works**. QB's MAE edge vs Sleeper
  (−1.659, the single largest per-position MAE-gap in the product) is
  treated as this repo's headline number and is asymmetrically protected
  below.
- Each position gates **independently** — a position can ship alone, HOLD
  alone, or (unlike the WR-primary/QB-RB-TE-secondary structure of the
  parent gate) any combination can result. No position's verdict is
  contingent on another's.

## Prior-peek disclosure (read before interpreting any tuning number)

`.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md` Section 8 already looked at
2025 indirectly: its exploratory QB/RB/TE table was computed on the
**2022-2024 pooled** population only (not 2025) — re-reading that section
confirms it never touched a 2025 row. However, the parent gate's WR
primary-metric confirmation (Section 4) **did** run against 2025 at
`w=0.5`, and the WR/QB/RB/TE mechanism code path is shared — the same
`apply_consensus_anchor_blend()` function, same `w=0.5` point, was
therefore *exercised* against 2025 data in that prior session, just never
scored for QB/RB/TE. This is a narrow, disclosed prior peek: **one prior
observation, at exactly one weight (0.5), on one metric (WR's own gap, not
QB/RB/TE's)**, no iteration, no QB/RB/TE-specific 2025 number was ever
computed or seen before this gate's own one-shot below. Per the task's
instruction, 2025 here is treated as **quasi-sealed with this caveat**
stated plainly rather than silently assumed pristine. The tuning grid
below (2022-2024) is unaffected — genuinely never observed before this
session for QB/RB/TE at any weight other than the single incidental 0.5
point noted above (which Section 8 did report, disclosed already, and is
superseded by this gate's own live/grid-verified 0.5 point below).

## Mechanism family (fixed, not re-explored)

Same family that shipped for WR — **mechanism (a), rank-blend**
(`apply_consensus_anchor_blend`), grid `{0.1, 0.2, 0.3, 0.4, 0.5}`, tuned
per-position independently on 2022-2024 pooled. **Near-tie
(`apply_consensus_anchor_near_tie`) is registered as a secondary
candidate** — computed once per position at the shipped constants
(`EPSILON=1.5`, `NUDGE=0.5`) for comparison, not grid-searched (matches how
the WR gate treated it: near_tie was a single configuration, blend was the
5-point grid).

## Data / leak-safety / scoring format

Identical to the parent gate — no new checks needed (same Bronze source,
same join key, same gate-0 as-of verification already performed and does
not vary by position beyond the coverage numbers below):
`data/bronze/external_projections/sleeper/season={2022..2025}/week={01..
18}/`, `player_id`-keyed, half-PPR only, point-in-time pre-game snapshot
(Dak Prescott fingerprint, parent gate constraint #2).

## Wiring — per-position independent enablement (verified, extended)

**Verified gap**: the existing `--consensus-anchor-src`/`--consensus-
anchor-position` flags are a **single-position override** — passing
`--consensus-anchor-position QB` replaces the entire resolved config
(src/position/mode/weight), which would silently turn the shipped WR
anchor **off** while testing QB. That is fine for isolated exploration
(what the parent gate's Section 8 did, post-hoc) but is NOT sufficient for
this gate's guard requirement ("other positions byte-identical, **including
WR** — regression-prove the shipped WR path is untouched") — that guard
requires running WR-anchored-as-shipped **and** the candidate position's
anchor **simultaneously**, so a real row-level diff against the
production-faithful baseline is possible.

**Fix (backward-compatible, additive-only, both CLIs)**: a new,
independent **second anchor slot** —
`--consensus-anchor-extra-position {QB,RB,TE,WR}` /
`--consensus-anchor-extra-mode {blend,near_tie}` (default `blend`) /
`--consensus-anchor-extra-weight` (default `0.5`) — applied via a second,
separate `build_sleeper_lookup()` + `apply_consensus_anchor()` call
**after** the existing primary anchor block (which continues to resolve
the shipped WR default exactly as before when no flag is passed). Because
`apply_consensus_anchor_blend`/`_near_tie` already scope strictly to their
own `position` argument and only ever touch `sleeper_anchor_flag`/
`projected_points` for rows at that position (proven in the parent gate's
own guard checks), the two calls compose without cross-contamination by
construction — no changes to `src/sleeper_consensus_anchor.py` itself are
needed, only additive CLI plumbing in `scripts/generate_projections.py`
and `scripts/backtest_projections.py`. The extra slot is gated off entirely
when the primary anchor is disabled (`--no-sleeper-anchor` still kills the
whole Sleeper-anchor family, extra slot included) — existing
`--consensus-anchor-src`/`-position`/`-mode`/`-weight` behavior,
`resolve_sleeper_anchor_config()`, and every existing test/flag are
unchanged. This is exactly the "extend backward-compatibly" instruction:
zero behavior change for any caller that doesn't pass the new flags.

## Methodology deviation (pre-registered, not applied after seeing results)

Per-position, per-weight live-CLI backtest runs cost ~8-11 min each on this
machine (verified from the parent gate's own run timestamps). A full
live-CLI grid identical in shape to the WR gate's (baseline + 5 blend
weights + 1 near_tie, per position, times tuning-set AND 2025-one-shot)
would be 3 positions x 7 configs x 2 eval windows = 42 live-CLI runs
(~5-6 hours of sequential compute) — the parent gate's own Section 7/8
already established the precedent that **post-hoc reapplication of the
identical production mechanism code on a live-CLI-generated population**
is an accepted, disclosed substitute for exploration/grid-search once the
live-CLI population itself is real (used there for the K=100 shuffle null
and the QB/RB/TE exploratory read). This gate extends that same disclosed
shortcut to the **grid search step only**, given 3x the position scope:

1. Two live-CLI baseline backtests are generated fresh this session (not
   reused from the parent gate's now-stale pre-ship files): 2022-2024
   pooled and 2025, **default settings, no new flags** — i.e., the
   current shipped production path (WR blend w=0.5 already applied, QB/RB/
   TE untouched). This is the actual guard-comparison baseline.
2. The 5-point blend grid (and the single near_tie point) per position is
   computed by grouping that baseline population by `(season, week)` and
   calling the exact same `build_sleeper_lookup()` / `apply_consensus_
   anchor()` functions in-process — byte-identical mechanism code to what
   the CLI would run, only skipping the ~8-11 min of Silver-data
   refetching/heuristic-recomputation that doesn't depend on the anchor
   weight at all.
3. The **winning weight per position** is confirmed with a real live-CLI
   run using the new `--consensus-anchor-extra-position` flag, both on the
   2022-2024 tuning set and the 2025 one-shot — so the number that actually
   gates ship/hold is live-CLI-verified, exactly matching the rigor the WR
   gate applied to ITS primary/guard numbers (Sections 3-5 there were
   "full live-CLI runs... not post-hoc unless explicitly noted"). Only the
   exploratory grid points (the 4 losing weights + near_tie, per position)
   rely on the post-hoc shortcut.
4. The K=100 shuffled-delta null (below) is computed post-hoc on the same
   population, identical to the parent gate's Section 7 design.

This is disclosed here, before any grid is run, not discovered as a
convenient rationalization afterward.

## Gates (per position, independent)

- **PRIMARY**: realized-outcome ordinal Accuracy Gap for OUR ranking alone
  (`scripts/simulate_fp_accuracy.py::score_sources({"ours": ...})` — the
  isolation-metric design from
  `grading-circularity-blend-toward-benchmark.md`, never a comparison
  against Sleeper's own gap) improves (decreases) by `>=0.05` on the
  2022-2024 pooled tuning set, AND is directionally positive with `>=50%`
  of the tuning-set pooled effect retained on the 2025 one-shot.
- **GUARD — MAE, asymmetric by design (pre-registered before any number is
  seen)**:
  - **QB: `<=0.00` tolerated** — i.e. QB MAE (vs `actual_points`, never vs
    Sleeper) must not regress **at all**, even by a rounding whisker. QB's
    −1.659 MAE edge is this product's single largest per-position
    MAE-vs-consensus margin and is explicitly the headline number the
    task says must not be put at risk.
  - **RB / TE: `<=0.02` tolerated** — same bar the WR gate used.
- **GUARD — scoping**: rows outside the anchored position (all positions
  other than the one under test, **explicitly including WR** — this is
  the regression-proof that the shipped WR path is untouched by the new
  extra-position wiring) are byte-identical between the production
  baseline and the treated run, full row-level diff, `max|Δ|=0.0`.
- **GUARD — unmatched rows**: player-weeks at the target position with no
  Sleeper match show exactly `0.000` projected-points delta.
- **GUARD — per-season sign consistency**: the tuning-set winning weight
  must not flip sign between any two of 2022/2023/2024 individually.
- **GUARD — sanity**: K=100 shuffled-delta null (shuffle `sleeper_pos_rank`
  within each `(season, week)` group, rerun the winning weight, recompute
  the primary metric, 100 draws) + one-sided empirical p-value against the
  true-signal delta; require `p < 0.05` — the full-reorder/blend-shape
  null per `shuffle-test-must-match-mechanism-shape.md` (not the
  disagreement-gated collapse test, which only applies to `near_tie`).

## Coverage / firing report (reported BEFORE any result number, this session)

Live-computed this session (not reused from the parent gate's Section 1
table, though expected to land in the same range) — see Results below.
Flag threshold: any season's match rate `<60%` is called out explicitly
before reading further (mirrors every prior gate in this family). QB's
population is smaller than WR/RB (roughly one starter/team/week) so its
match rate is checked with extra scrutiny per the task's instruction, not
assumed to inherit WR's ~95-99% just because the archive is the same
source.

## Verdict rules (per position, independent)

- **SHIP-PENDING-USER**: primary gate clears on 2022-2024 tuning AND the
  2025 one-shot retains `>=50%` AND the position's MAE guard (asymmetric
  per above) passes AND the scoping/unmatched/sign-consistency guards pass
  AND the shuffle-null p-value passes. Machinery lands as opt-in
  regardless of verdict (no `generate_projections.py`/
  `backtest_projections.py` DEFAULT changes in this session for ANY
  position, including ones that clear every gate — matches the WR gate's
  own verdict-rule text and the "3 weeks before the draft" reasoning: a
  production-default change is a user decision, made separately, same as
  WR's own promotion was).
- **HOLD**: otherwise (primary misses on tuning, fails to hold `>=50%` on
  2025, either MAE guard fails, scoping/unmatched/sign-consistency guard
  fails, or the shuffle-null p-value `>= 0.05`).

## Protocol amendment slot

Any change to the above will be documented here, dated, BEFORE running the
affected grid/one-shot — not applied silently after seeing a result.

---

## Results

All numbers below computed 2026-08-23, same session, no reused stale
artifacts: two fresh live-CLI baseline backtests (current production
config — WR shipped anchor already applied via the existing default path,
QB/RB/TE untouched), `output/backtest/sleeper_anchor_qbrbte_gate/
backtest_half_ppr_consensus_consanchorsleeperWRblend_20260823_145353.csv`
(2022-2024 pooled, n=11,358) and `..._145113.csv` (2025, n=4,451), both
`--seasons ... --weeks 1-18 --scoring half_ppr --vs-consensus
--consensus-source sleeper`, no other flags.

### 1. Coverage / firing rate (BEFORE any result number)

**Sleeper-match rate**, live-computed against the baseline population
above (`build_sleeper_lookup` called per (season, week) exactly as the CLI
does):

| Position | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| QB | 94.4% | 94.8% | 98.1% | 96.3% |
| RB | 98.5% | 98.6% | 99.4% | 96.1% |
| TE | 98.7% | 97.0% | 95.9% | 95.0% |

All 12 season/position cells clear the 60% flag by a wide margin — no
"population mostly outside coverage" caveat anywhere, including QB (the
smallest population, checked with extra scrutiny per the task
instruction — 94.4-98.1% is materially the same range as RB/TE, not a
weaker case).

**Near-tie (`<=1.5pt` adjacent same-position pair) both-members-matched
rate**, pooled 2022-2024 / 2025:

| Position | 2022-2024 pooled | 2025 |
|---|---:|---:|
| QB | 95.5% (1,149/1,203) | 94.7% (376/397) |
| RB | 97.8% (2,864/2,927) | 93.1% (1,096/1,177) |
| TE | 95.1% (1,990/2,093) | 91.9% (791/861) |

### 2. Methodology note actually used (as pre-registered)

The 5-point blend grid + near_tie point per position was computed via the
disclosed post-hoc shortcut (in-process reapplication of
`build_sleeper_lookup`/`apply_consensus_anchor`, byte-identical function
calls to production, grouped by `(season, week)` on the live-CLI baseline
population — no Silver refetch). The **winning weight per position was
then live-CLI-confirmed** (`--consensus-anchor-extra-position` on top of
the unmodified shipped-WR-default run) for both the 2022-2024 tuning set
and the 2025 one-shot — 6 live-CLI runs total, ~8-11 min each. **The
live-CLI numbers are authoritative for every gate/guard decision below**;
the post-hoc grid numbers are reported for weight selection and
transparency only.

### 3. 2022-2024 pooled tuning grid (post-hoc, weight selection only)

Baseline realized-outcome ordinal Accuracy Gap (isolation metric — OUR
ranking alone, `score_sources({"ours": ...})`, weeks 3-17, pooled
2022-2024): **QB 7.20865, RB 6.16707, TE 6.25795**.

| Weight | QB Δ gap | RB Δ gap | TE Δ gap |
|---|---:|---:|---:|
| 0.1 | -0.01477 | -0.04492 | -0.02098 |
| 0.2 | -0.05011 | -0.09469 | -0.07501 |
| 0.3 | -0.10803 | -0.14640 | -0.12265 |
| **0.4** | **-0.13554 (best)** | -0.18415 | -0.12927 |
| 0.5 | -0.11414 | **-0.21349 (best)** | **-0.14442 (best)** |
| near_tie | -0.05662 | -0.03996 | -0.02413 |

**Winning weight selected as the single best pooled-margin point in the
registered grid** (family convention, matches how the parent WR gate
selected its winner): **QB w=0.4** (non-monotonic — w=0.5 is *worse* than
w=0.4 for QB, unlike WR/RB/TE's monotonic-through-0.5 pattern, flagged
here rather than silently smoothed over), **RB w=0.5**, **TE w=0.5** (both
monotonically increasing through the top of the registered grid, same
caveat the WR gate flagged about its own grid ceiling).

**Post-hoc per-season sign check (weight-selection stage only, superseded
by Section 4's live-CLI numbers)**: QB and RB signs are consistent
2022/2023/2024 at their winning weights. **TE shows a sign flip at its own
post-hoc winning weight** — 2024 delta is **positive** at both w=0.4
(+0.00146) and w=0.5 (+0.00336), versus negative at w<=0.3 (e.g. -0.05323
at w=0.3) — flagged here immediately, not discovered later and explained
away. Section 4 resolves this with the live-CLI-authoritative number.

### 4. Live-CLI confirmation (authoritative for every gate/guard decision)

6 live-CLI runs: winning weight per position, both eval windows, on top of
the unmodified shipped-WR-default path (`--consensus-anchor-extra-position
{QB,RB,TE} --consensus-anchor-extra-mode blend --consensus-anchor-extra-weight
{0.4,0.5,0.5}`).

**QB (w=0.4):**

| | Pooled gap Δ | 2022 Δ | 2023 Δ | 2024 Δ | MAE Δ |
|---|---:|---:|---:|---:|---:|
| 2022-2024 tuning | **-0.11268** | -0.03257 | -0.12523 | -0.18023 | -0.03504 |
| 2025 one-shot | **-0.01668** | — | — | — | -0.07224 |

Retention: `0.01668 / 0.11268 = 14.8%` (required `>=50%`). **Per-season
sign consistent** (all three negative). MAE improves both windows (clears
the strict QB `<=0.00` bar trivially — it's an improvement, not even a
flat result).

**RB (w=0.5):**

| | Pooled gap Δ | 2022 Δ | 2023 Δ | 2024 Δ | MAE Δ |
|---|---:|---:|---:|---:|---:|
| 2022-2024 tuning | **-0.20391** | -0.28582 | -0.13489 | -0.19102 | -0.18607 |
| 2025 one-shot | **-0.44420** | — | — | — | -0.23454 |

Retention: `0.44420 / 0.20391 = 217.8%` (stronger on the confirmation
season than tuning — same pattern the parent WR gate and `--ecr-anchor`
both saw). Per-season sign consistent (all three negative). MAE improves
both windows, clears the `<=0.02` RB bar by a wide margin (improves,
doesn't even use the tolerance).

**TE (w=0.5):**

| | Pooled gap Δ | 2022 Δ | 2023 Δ | 2024 Δ | MAE Δ |
|---|---:|---:|---:|---:|---:|
| 2022-2024 tuning | **-0.14504** | -0.16745 | -0.23460 | -0.03307 | -0.08369 |
| 2025 one-shot | **-0.20280** | — | — | — | -0.03708 |

Retention: `0.20280 / 0.14504 = 139.8%`. **Per-season sign consistent, all
three negative** — the authoritative live-CLI 2024 delta is **-0.03307**,
reversing the sign the post-hoc grid showed at this same weight
(Section 3: +0.00336). Both values are tiny relative to the ~6.15 metric
scale (<=0.5%) and the two computations use very slightly different
populations (post-hoc n=957 vs live-CLI-confirmed n=941 — a ~1.7% row-count
difference, the same "post-hoc population differs modestly from a true
live-CLI population" phenomenon the parent WR gate's Section 7 already
documented for its own shuffle-null computation). Per this doc's
pre-registered methodology ("the live-CLI numbers are authoritative for
every gate/guard decision"), the sign-consistency guard is evaluated on
the **-0.03307** value and **passes**. MAE improves both windows, clears
the `<=0.02` TE bar with room to spare.

### 5. Guard: scoping (byte-identical outside target position, incl. WR explicitly)

Full row-level merge, baseline vs each live-CLI-confirmed treated run:

| Run | Rows outside target position | max\|Δ\| | Unmatched target-position rows | max\|Δ\| |
|---|---:|---:|---:|---:|
| QB w=0.4, 2022-24 | all non-QB rows | 0.000000 | 60 | 0.000000 |
| QB w=0.4, 2025 | all non-QB rows | 0.000000 | 17 | 0.000000 |
| RB w=0.5, 2022-24 | all non-RB rows | 0.000000 | 35 | 0.000000 |
| RB w=0.5, 2025 | all non-RB rows | 0.000000 | 48 | 0.000000 |
| TE w=0.5, 2022-24 | all non-TE rows | 0.000000 | 61 | 0.000000 |
| TE w=0.5, 2025 | all non-TE rows | 0.000000 | 44 | 0.000000 |

**WR-specific explicit proof** (the task's named regression requirement —
"regression-prove the shipped WR path is untouched"), isolated from the
"all other positions" check above: baseline vs the RB-extra-anchor
2022-2024 confirmation run, WR rows only — **4,726 WR rows compared,
max\|Δ projected_points\|=0.0, `sleeper_anchor_flag` identical row-for-row,
4,667 WR rows fired the shipped anchor in BOTH runs** (same count, same
rows). The shipped WR path is provably untouched by the new extra-position
wiring, on real production data, not just a unit-test fixture (which
`tests/test_sleeper_anchor_extra_position.py::TestWRByteIdenticalRegression`
also covers at the module level).

### 6. Guard: K=100 shuffled-delta null + one-sided empirical p

Post-hoc on the 2022-2024 baseline population (same disclosed design as
the parent gate's Section 7), at each position's live-CLI-confirmed
winning weight:

| Position (weight) | True Δ | Null mean | Null std | Null min/max | One-sided p | Required | Result |
|---|---:|---:|---:|---:|---:|---|---|
| QB (0.4) | -0.13554 | +0.41817 | 0.09763 | +0.17053 / +0.58529 | **0.0000** | p<0.05 | PASS |
| RB (0.5) | -0.21349 | +1.13940 | 0.09936 | +0.87218 / +1.35997 | **0.0000** | p<0.05 | PASS |
| TE (0.5) | -0.14442 | +0.80379 | 0.10551 | +0.57366 / +1.03671 | **0.0000** | p<0.05 | PASS |

All three true effects beat all 100 null draws by a wide margin — the null
distribution sits entirely on the "noise actively hurts" side, exactly the
full-reorder/blend-mechanism signature the parent gate established.
**All three positions pass the shuffle-null sanity check**, including QB
(whose eventual verdict below is HOLD for an unrelated reason — the
shuffle test is not what stops QB).

### 7. Verdicts (per position, independent)

| Position | Coverage | Tuning (>=0.05) | Sign consistency | MAE guard | 2025 retention (>=50%) | Scoping | Shuffle p<0.05 | **Verdict** |
|---|---|---|---|---|---|---|---|---|
| **QB** (w=0.4) | PASS | PASS (-0.113, 2.3x) | PASS | PASS (improves, QB's strict <=0.00 bar) | **FAIL (14.8%)** | PASS | PASS | **HOLD** |
| **RB** (w=0.5) | PASS | PASS (-0.204, 4.1x) | PASS | PASS (improves, well within <=0.02) | PASS (217.8%) | PASS | PASS | **SHIP-PENDING-USER** |
| **TE** (w=0.5) | PASS | PASS (-0.145, 2.9x) | PASS (live-CLI-authoritative; see Section 4 discrepancy note) | PASS (improves, well within <=0.02) | PASS (139.8%) | PASS | PASS | **SHIP-PENDING-USER** |

**QB HOLDs on a single, clean, disclosed criterion**: the pre-registered
2025 one-shot confirmation requires `>=50%` of the tuning-set effect to
retain, and QB retains only 14.8% — most of QB's tuning-set improvement
was specific to 2022-2024 and did not generalize to the sealed 2025
season, even though coverage, the guard, sign-consistency, and the
shuffle-null all pass cleanly. This is precisely the outcome the task's
framing anticipated as the higher bar for "improvement on an existing
win": QB's crown-jewel −1.659 MAE edge is not put at risk (the MAE guard
result is a genuine improvement, not a near-miss), but the ordinal
improvement case itself is not strong enough, out of sample, to justify
opt-in machinery being recommended for production use. **RB and TE both
clear every pre-registered gate** and land as SHIP-PENDING-USER, following
the task's rule that machinery lands as opt-in regardless of verdict — no
`generate_projections.py`/`backtest_projections.py` DEFAULT changes for
any of the three positions in this session (a production-default change
remains a user decision, same as WR's own promotion was a separate,
explicit step after this kind of gate).

## Caveats / follow-ups

- **QB's tuning-vs-2025 gap** deserves a closer look before any future
  QB-specific gate: retention this low (14.8%) with clean guards/coverage
  suggests either the 2022-2024 QB tuning grid overfit weight selection to
  those three years' specific slate composition, or 2025's QB population
  behaves differently in some way not yet diagnosed — worth investigating
  before re-attempting a QB anchor gate, not simply re-running the same
  grid again.
- **TE's post-hoc/live-CLI 2024 sign discrepancy** (Section 4) is small in
  magnitude and resolved in favor of the live-CLI-authoritative number per
  this doc's own pre-registered methodology, but is disclosed rather than
  smoothed over — a follow-up could re-run the post-hoc grid harness with
  the exact live-CLI row ordering to close this gap for future gates in
  this family.
- **Grid ceiling**: RB and TE's post-hoc grids were still monotonically
  improving at w=0.5, the top of the registered range (same caveat the
  parent WR gate flagged) — QB's grid, notably, is NOT monotonic (peaks at
  0.4, worse at 0.5), so this caveat does not apply uniformly across
  positions and should not be assumed to generalize.
- **Lever-family interaction untested**: RB and TE's anchors were only
  ever tested stacked with the shipped WR anchor (the realistic production
  scenario) — not with `--ecr-anchor` or any other lever in this family.
  Same out-of-scope note as the parent gate.

## Files changed

- `src/sleeper_consensus_anchor.py` — **unchanged** (already
  position-parameterized; no code changes needed for this gate).
- `scripts/generate_projections.py` / `scripts/backtest_projections.py` —
  new, additive-only `--consensus-anchor-extra-position` /
  `--consensus-anchor-extra-mode` / `--consensus-anchor-extra-weight` CLI
  flags and a second `apply_consensus_anchor()` call site in the per-week
  loop (both scripts), gated off entirely when `--no-sleeper-anchor` is
  passed or the flag is omitted (`None` default — existing behavior for
  every current caller is unchanged, verified via
  `tests/test_sleeper_anchor_cli_defaults.py`'s pre-existing suite passing
  unmodified). `run_backtest()` gains matching kwargs with `None`/no-op
  defaults.
- `tests/test_sleeper_anchor_extra_position.py` (new) — 9 tests: WR
  byte-identical regression proof (with-and-without the extra QB call,
  order-of-application independence), extra-slot composability/scoping
  invariants, and CLI-wiring/signature existence checks for both scripts.
- **Data**: none new — reuses the already-committed
  `data/bronze/external_projections/sleeper/season={2022..2025}/`.
- **Artifacts**: `output/backtest/sleeper_anchor_qbrbte_gate/` — 2 baseline
  + 6 live-CLI-confirmation backtest CSVs (this session, fresh, not
  reused from the parent gate's now-stale pre-ship files).
