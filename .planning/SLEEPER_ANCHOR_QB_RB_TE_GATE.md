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

(Filled in after this doc's initial commit — coverage first, then tuning,
one-shot, guards, shuffle, verdict per position.)
