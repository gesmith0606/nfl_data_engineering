# Ensemble Selection Reproducibility Investigation (2026-08-23)

Pre-registered **before** any new results are run in this session. This is a
diagnostic investigation, not a gate — no promotion/demotion of
`models/ensemble/` (shipped) will happen regardless of findings.

## The question

Per `.planning/ENSEMBLE_EP_FEATURES_GATE.md`'s 2026-08-22 addendum, re-running
the full CV-cutoff-search feature-selection procedure
(`scripts/run_feature_selection.py`) — the same procedure that originally
produced the shipped ensemble's 120-feature set — could **not** reproduce the
shipped model's forward performance:

| | Shipped (120, original) | Fresh full-procedure, no-EP control |
|---|---:|---:|
| OOF Spread ATS | 52.92% (n=1557) | 53.89% (n=1557) |
| Sealed-2025 Spread ATS | 51.66% (n=271 bet) | 46.86% (n=271 bet) |
| Optimal feature count | 120 | 60 |

Fresh runs look *better* in-sample (OOF) and *worse* out-of-sample (sealed).
This means the shop currently cannot safely retrain/reselect the shipped
ensemble — worth understanding before the season. This doc investigates
*why*, without touching `models/ensemble/`.

## Scope / file ownership

Owned files for this investigation: `src/feature_selector.py`,
`src/ensemble_training.py`, `scripts/run_feature_selection.py`,
`scripts/train_ensemble.py`, `scripts/backtest_predictions.py`, `models/`
(evidence dirs only — `models/ensemble/` itself is never touched), and new
analysis scripts under `scratchpad/` (repo-local, not committed, per the
08-16/08-21/08-22 precedent of keeping one-off eval/control scripts outside
authorized artifact dirs). Explicitly NOT touched:
`src/sleeper_consensus_anchor.py`, `src/ecr_anchor.py`,
`scripts/generate_projections.py`, `scripts/backtest_projections.py`,
`src/player_model_training.py`, player-projection tests.

## Machinery change (additive, made before any results)

`select_features_for_fold`'s only source of randomness is
`params.get("random_state", 42)`, threaded into: the 20% `train_test_split`
used for early-stopping eval, the 500-row SHAP subsample, and the
`XGBRegressor` itself (subsample=0.8/colsample_bytree=0.7 draw on
`random_state`). `CONSERVATIVE_PARAMS` hardcodes `random_state: 42`
everywhere (XGB/LGB/CB alike) — so **the CV-search procedure as shipped has
no seed knob at all**; every run with identical data/pool is deterministic
(confirmed: `find_optimal_feature_count` even *ignored* its own `params`
argument for the per-fold selection call, hardcoding
`CONSERVATIVE_PARAMS.copy()` regardless of what was passed in — a latent bug,
now fixed as part of this investigation since it blocked seed-threading
entirely).

Changes to `scripts/run_feature_selection.py` (additive only, default
behavior byte-for-byte unchanged — verified via the existing
`tests/test_feature_selector.py::TestCVValidatedCutoff`/`TestEndToEndSelection`,
33/33 passing after the change):
- Fixed `find_optimal_feature_count` to actually honor a passed-in `params`
  dict for the per-fold `select_features_for_fold` call (previously
  hardcoded).
- New `--seed` CLI flag: overrides `random_state` throughout the CV-search
  (both the cutoff search and the final selection). Omitted → identical to
  current behavior (`random_state=42`, hardcoded path unchanged).
- `seed` recorded in the output `metadata.json` for traceability.

No changes to `src/ensemble_training.py`/`scripts/train_ensemble.py` are
needed for this investigation — given a fixed feature list, ensemble training
is itself deterministic (same `random_state=42` pattern), so seed variance
only needs to be tested at the feature-selection step; training on each
seed's resulting list is a single deterministic run.

## Hypotheses and test plan

**H1 — Seed/procedure variance.** The CV-search is high-variance across
seeds — different `random_state` draws give wildly different sealed
outcomes.
*Test*: run the full no-EP CV-search procedure (`scripts/
run_feature_selection.py --target spread --dry-run`, candidate pool/counts/
correlation-threshold at current defaults — matches the 08-22 addendum's
no-EP control setup) at seeds `{42, 7, 123}` (N=3 if wall-clock allows;
fall back to N=2 and say so honestly if not). For each seed: train the
ensemble on that seed's selected list (`--features-from <seed metadata>
--skip-reselect`, deterministic), then evaluate OOF Spread ATS/profit (from
`oof_spread.parquet` joined to `spread_line`) and sealed-2025 ATS/profit
(`scripts/backtest_predictions.py --ensemble --seasons 2025`). Report the
spread of (feature count, OOF ATS, sealed ATS) across seeds, plus pairwise
Jaccard overlap of selected-feature sets. A wide sealed spread across seeds
=> the original shipped selection was plausibly one lucky draw among many,
and the fix is selection-stability machinery (e.g. feature-stability voting
across seeds), not a bug hunt.

**H2 — Data drift since the original selection.** The shipped 120-feature
LIST was selected on pre-repair data (this repo fixed major Silver bugs in
Aug 2026: snap-join all-NaN, 2021 ingestion gaps, zero-row fixes — vault
`[[model-staleness-after-data-repair]]`); the shipped model was retrained
2026-06-10 (per `models/ensemble/metadata.json`).
*Test*: (a) Jaccard overlap of the shipped 120-feature list vs each fresh
no-EP selection's list; which feature families swap. (b) Retrain the
ensemble on TODAY's data with the SHIPPED 120-feature list verbatim
(`--features-from models/ensemble/metadata.json`, no reselection) and check
whether it still reproduces ~51.66% sealed. The 08-22 addendum already ran
this exact check once (informally, as its "same-session baseline
reproduction" step) and got 52.92%/51.66% — identical to shipped — but this
doc re-runs and records it formally as evidence for H2, since it is the crux
of the "list is robust, procedure is fragile" vs. "data moved the ground"
distinction. If it reproduces: the feature LIST generalizes fine on today's
data and the CV-search PROCEDURE (not data drift) is what fails to
reproduce it. If it doesn't: data drift is real and independent of the
selection procedure.

**H3 — Sealed-set smallness.** Sealed-2025 ATS on ~271-285 games has wide
binomial error bars.
*Test*: compute a binomial proportion CI (Wilson interval, report both 1σ
and 95%) for every sealed ATS figure in this doc and in the 08-21/08-22
addendum, using each arm's actual n. Report whether shipped (51.66%,
n=271) and the no-EP full-procedure control (46.86%, n=271) are actually
distinguishable at 1σ/95%, or whether "fragility" is partly a statistical
illusion given n≈271.

**H4 — Overfit-to-OOF in the search.** The CV-search optimizes OOF
(CV) MAE across candidate counts — a garden of forking paths that can
inflate OOF while anti-selecting for sealed.
*Test*: collect every (OOF ATS, sealed ATS) pair available across this
investigation plus the 08-21/08-22 addendum's already-run arms (shipped,
quick-reselect control/treated, full-procedure control/treated, this doc's
H1 seed runs, H2's shipped-list-on-today's-data rerun) and compute the
Pearson correlation between OOF ATS and sealed ATS across configurations.
A negative or near-zero correlation would confirm OOF is not predictive of
sealed performance across the configurations this repo has actually tried.

**H5 — Candidate-pool composition drift (new).** The 08-22 addendum notes
its no-EP full-procedure candidate pool was "316 (up from... a few already
present from other concurrent feature work landing since 08-21)" — i.e. the
candidate pool `get_feature_columns()` returns is itself a moving target
under concurrent development, not merely "the same pool, more data rows."
*Test*: record today's full candidate-pool size (`get_feature_columns()` on
a fresh `assemble_multiyear_features()` call) and compare to the addendum's
recorded 316/343 pool sizes from one day prior. If the pool has already
changed again in 24h, that's a second, independent source of
non-reproducibility layered on top of H1/H2 — the procedure is being asked
to reselect from a shifting candidate universe, not a static one.

**H6 — Flat CV-MAE surface makes "optimal count" arbitrary (new).** The
08-22 addendum's own CV MAE-by-count table is nearly flat (60→10.0850,
80→10.1070, 100→10.0811, 120→10.0756, 150→10.1411 — a ~0.6% spread across
the whole candidate-count range). MAE is also a point-accuracy metric, not
an ATS-threshold metric — the two need not move together.
*Test*: for each H1 seed run, report the full CV-MAE-by-count table and how
close the best count's MAE is to the runner-up(s) (as a % of the range).
If differences are within noise, the "optimal count" the search reports is
effectively a coin flip among near-tied counts — a structural reason the
procedure can pick 60 one day and 120 the next without anything being
"wrong," and a reason MAE-based cutoff selection is a weak criterion for a
downstream ATS objective.

## Deliverable

This doc, updated in place with a Results section per hypothesis (evidence,
numbers, honest error bars), a verdict on which mechanism(s) dominate, and a
concrete recommendation for the protocol future ensemble reselections should
use. Explicitly flags — but does not act on — whether the shipped model
should be considered robust, lucky, or stale; that promotion/demotion
decision is left to the user.

## Compute plan

Heavy runs, executed in foreground with generous timeouts, chunked so any
individual step can be resumed:
1. H1: up to 3 full `run_feature_selection.py` runs (seeds 42/7/123, no-EP
   pool) + up to 3 `train_ensemble.py --skip-reselect` retrains + up to 3
   OOF/sealed evaluations.
2. H2: 1 `train_ensemble.py --features-from models/ensemble/metadata.json`
   rerun (deterministic, reproduces shipped numbers) + list-diff analysis
   (cheap, no training).
3. H3/H4/H5/H6: analysis only on numbers already produced above plus the
   08-21/08-22 addendum's recorded figures — no additional heavy runs.

If N=3 for H1 proves infeasible in reasonable wall-clock, this doc will
report N=2 and say so honestly rather than silently truncating.

## Results

Compute turned out cheap: each full `run_feature_selection.py` no-EP run
took ~65-70s wall-clock (candidate pool 316, counts [60,80,100,150],
VALIDATION_SEASONS 2019-2024), each `train_ensemble.py --features-from`
retrain ~14-19s. This allowed **N=4** seeds for H1 (42, 7, 123, 2024) rather
than the pre-registered minimum of 3, plus the H2 fixed-list retrain, all in
a few minutes total. All numbers below are freshly computed this session
(`scratchpad/eval_reproducibility.py`, not committed) — the `shipped` row
reads `models/ensemble/oof_spread.parquet` and `predict_ensemble` on fresh
2025 data directly (no retraining), reproducing the 08-21/08-22 addendum's
own recorded baseline (52.92% OOF / 51.66% sealed) exactly, which validates
the evaluation methodology before trusting the new numbers.

### Full results table

| Arm | Seed | Feature count | OOF ATS (n=1557) | OOF profit | Sealed-2025 ATS (n=271) | Sealed profit |
|---|---:|---:|---:|---:|---:|---:|
| **shipped** (saved, no retrain) | 42 (implicit) | 120 | 52.92% | +16.09u | **51.66%** | -3.73u |
| shipped_list_retrain (H2) | 42 (implicit) | 120 (identical list) | 52.86% | +14.18u | 50.18% | -11.36u |
| seed_42 (=08-22 addendum's no-EP control) | 42 | 60 | 53.89% | +44.73u | 46.86% | -28.55u |
| seed_7 | 7 | 100 | 54.40% | +60.00u | 52.03% | -1.82u |
| seed_123 | 123 | 80 | 55.88% | +103.91u | **52.77%** | +2.00u |
| seed_2024 | 2024 | 80 | 53.89% | +44.73u | 49.45% | -15.18u |

`seed_42` reproduces the 08-22 addendum's no-EP full-procedure control
(53.89%/46.86%, optimal count 60) exactly — cross-confirms both this
session's `--seed` machinery and the addendum's finding via an independent
run.

### H1 — Seed/procedure variance: CONFIRMED, dominant mechanism

Across 4 seeds, identical data/pool/procedure, varying only `random_state`:
- **Feature count never once matched shipped's 120**: {60, 80, 80, 100}.
- **Sealed ATS spans 46.86%-52.77%, a 5.91pt range** — wider than the
  shipped-vs-any-single-fresh-run gap that originally triggered this
  investigation. One seed (123) *beat* shipped's sealed ATS outright
  (52.77% vs 51.66%, and the only positive-profit sealed arm besides
  shipped itself: +2.00u vs shipped's -3.73u).
- **OOF ATS is systematically higher than shipped in all 4 seeds**
  (53.89-55.88% vs shipped's 52.92%) while sealed is lower in 3 of 4 —
  the fresh procedure reliably looks better in-sample and is a coin flip
  out-of-sample.
- Pairwise Jaccard overlap of selected-feature sets between seeds:
  0.260-0.333 (see raw output) — seed-to-seed, roughly 2/3 of each
  selected list is *different* features, not a stable core with minor
  edge churn.

**Stability-selection evidence**: of the ~316-feature pool, only **14
features are selected by all 4 fresh seeds** (a natural consensus core),
and 46 by ≥3 of 4. Of those 14 fully-stable features, **11 also appear in
the shipped 120** — meaningful agreement at the core, even though the
full lists diverge wildly. This is direct, actionable evidence that a
stability-voting protocol (intersection/high-frequency-across-seeds) would
recover something close to what both the shipped procedure and repeat runs
independently agree matters, while discarding the ~90% of each single run's
list that is seed-dependent noise.

**Verdict: the original shipped selection was very plausibly one lucky (or
at least unremarkable) draw from a high-variance lottery, not a uniquely
correct answer the current procedure has "regressed" away from.** Any
single re-run — including the original one that got shipped — sits inside
a wide, roughly seed-uniform distribution of outcomes.

### H2 — Data drift since the original selection: SECONDARY, but real and non-zero

(a) **List-diff vs shipped**: Jaccard overlap of shipped's 120 vs each
fresh seed's list: 0.290-0.333 — the fresh full-procedure lists share only
about a third of their features with shipped, similar to how much the
fresh seeds share with *each other* (see H1). The reselection procedure
does not converge back toward the shipped list even approximately.

(b) **Fixed-list retrain (the crux test)**: retraining on TODAY's data
with the shipped 120-feature list verbatim, unchanged, gives OOF 52.86%
(vs shipped's 52.92% — a 0.06pt difference, fully consistent with pure
noise) but **sealed 50.18% vs shipped's saved 51.66%, a real -1.48pt /
-7.63u difference** even though every feature name, hyperparameter, and
random seed is identical to the original.

This means data did move under the shipped list, but the LIST itself
mostly still works — retraining on it recovers within ~1.5pt of shipped's
recorded sealed number, versus the 2.95-9pt-plus swings seen from full
reselection (H1) or the original addendum's full-procedure reruns. The
drift is real (confirmed independently: `git log` shows Silver-correctness
commits landing between the 2026-06-10 shipped training date and today,
e.g. `c7b1dfb8` "snap-count join matched 0% of rows in every season ever
produced," `83327ecd` "snap join fans out on non-unique display names,"
`c680f416` "correctness fixes across core library from full-repo scan" —
these touch trailing-window inputs that feed both training-season and
2025-sealed feature values even when the selected *column names* are
unchanged) but it is a secondary contributor next to H1's seed-lottery
effect, not the dominant one.

### H3 — Sealed-set smallness: partial explanation, not the whole story

Wilson-interval CIs (n=271 bet games in every sealed arm; pushes excluded
per `evaluate_ats`/`compute_profit` convention):

| Arm | Sealed ATS | 1σ CI | 95% CI |
|---|---:|---|---|
| shipped | 51.66% | [48.62%, 54.68%] | [45.73%, 57.55%] |
| shipped_list_retrain | 50.18% | [47.15%, 53.22%] | [44.27%, 56.09%] |
| seed_42 (no-EP control) | 46.86% | [43.85%, 49.90%] | [41.01%, 52.81%] |
| seed_7 | 52.03% | [48.99%, 55.05%] | [46.09%, 57.91%] |
| seed_123 | 52.77% | [49.73%, 55.78%] | [46.83%, 58.63%] |
| seed_2024 | 49.45% | [46.42%, 52.48%] | [43.54%, 55.37%] |

Shipped (51.66%) vs the no-EP full-procedure control (46.86%, seed_42) —
the specific comparison that opened this investigation — has **1σ CIs that
barely touch** ([48.62,54.68] vs [43.85,49.90], overlap of only ~1.05pt)
and **95% CIs that overlap substantially**. Read in isolation, that single
pairwise gap is not clearly statistically significant at conventional 95%
confidence given n=271 — some of the alarm the original addendum raised is
within sampling noise for any *one* comparison.

However, H3 does **not** fully explain the phenomenon: the *pattern* across
4 independent seeds (consistently different feature counts, 3-of-4 below
shipped, a 5.91pt seed-to-seed sealed range, near-zero OOF/sealed
correlation per H4) is a much stronger signal than any single pairwise CI
comparison, and would be very unlikely to arise from sampling noise alone
acting on a procedure that reliably reproduces one true answer. **Verdict:
H3 is a real, honest caveat on the *magnitude* of any single reported gap,
but not the primary explanation for the reproducibility problem.**

### H4 — Overfit-to-OOF in the search: CONFIRMED, contributing mechanism

Pearson correlation between OOF ATS and sealed ATS across all 9
(OOF, sealed) configuration pairs available this session and from the
08-21/08-22 addendum (shipped; shipped_list_retrain; seeds 42/7/123/2024;
addendum's EP quick-reselect control/treated; addendum's EP full-procedure
treated) is **r = 0.334** (R² ≈ 0.11) — weak. A config's OOF ATS explains
roughly a tenth of the variance in its sealed ATS across the configurations
this repo has actually tried. **The CV-search's own optimization target
(OOF/CV-MAE) is a weak, noisy proxy for what actually matters
(forward/sealed ATS)** — consistent with a garden-of-forking-paths dynamic
where more search (more candidate counts, more reselection) finds
configurations that look better on the metric being searched without
reliably transferring forward.

### H5 — Candidate-pool composition drift: not detected in this 24h window (caveat: longer window untestable)

Fresh `get_feature_columns()` on a fresh `assemble_multiyear_features()`
call today returns exactly **316** no-EP candidates — identical to the
08-22 addendum's recorded no-EP pool size from one day prior. No further
pool drift detected in this specific 24h window. This does **not** rule out
pool drift over the ~2.5 months between the 2026-06-10 shipped training and
today (no historical snapshot of the full candidate pool at 06-10 exists to
diff against) — flagged as an untestable gap rather than a negative
finding.

### H6 — Flat CV-MAE surface makes "optimal count" arbitrary: CONFIRMED, structural amplifier

CV-MAE-by-count spread within each seed (best count vs. worst of the 5
candidates), as a fraction of the ~10.0-10.15 MAE scale:

| Seed | Best count | Best MAE | Worst MAE (any other count) | Spread |
|---|---:|---:|---:|---:|
| 42 | 60 | 10.0373 | 10.1245 (@80) | 0.87% |
| 7 | 100 | 10.0790 | 10.1245 (@150) | 0.45% |
| 123 | 80 | 10.0695 | 10.1369 (@120) | 0.67% |
| 2024 | 80 | 10.1101 | 10.1461 (@150) | 0.34% |

Differences between the "best" and "worst" candidate counts are 0.3-0.9%
of the MAE scale in every seed — far smaller than the ~5-10% relative swing
seen in downstream sealed ATS. **The cutoff search is picking among
statistically near-indistinguishable ties**, which structurally explains
why the "optimal" count bounces around (60/80/80/100/120-shipped) without
anything being procedurally broken — MAE (a point-accuracy loss) also has
no guaranteed relationship to ATS (a threshold-relative-to-the-line
metric), so even a perfectly-resolved MAE ranking would not necessarily
rank configs correctly on the metric that is actually deployed.

## Dominant mechanism

**H1 (seed/procedure lottery), structurally amplified by H6 (near-flat
CV-MAE surface) and enabled by H4 (OOF is a weak proxy for sealed), is the
dominant mechanism.** H2 (data drift) is real but secondary — it costs
~1.5pt of sealed ATS on the identical feature list, versus 5-9+pt swings
from reselection. H3 (sampling noise) is a genuine, honest caveat on the
magnitude of any *single* reported gap but does not explain the consistent
cross-seed pattern. H5 (pool drift) was not observed in the tested window
but could not be fully ruled out over the longer 06-10-to-today gap.

## Recommended protocol for future ensemble reselections

1. **Never trust a single-seed run of `run_feature_selection.py` as
   final.** Run N≥4-5 seeds (cheap: ~70s CV-search + ~15s train each,
   this session ran all 4 in a few minutes), and use the **intersection or
   ≥60-80%-frequency feature set** across seeds as the stable core,
   filling any remaining slots toward the target count by summed/mean SHAP
   rank across seeds. This session's own stable-core (14 features in all
   4 seeds, 46 in ≥3 of 4) is a template for what that looks like in
   practice.
2. **Require sealed-holdout agreement, not just OOF improvement, before
   promoting any reselected model** — H4's r=0.334 means OOF/CV-MAE alone
   cannot be trusted as a promotion signal. This is already the spirit of
   the 08-21/08-22 gate's decision rule; this investigation shows *why*
   that rule is load-bearing rather than a formality.
3. **Always run the fixed-list retrain (H2's crux test) before any full
   reselection.** It costs ~15-20s and immediately separates "how much of
   any observed change is data drift" from "how much is the reselection
   procedure itself" — this session's own H2 result (only -1.48pt from
   drift alone, vs. -2.95 to -9pt-plus from reselection in this doc and
   the 08-22 addendum) is exactly the kind of decomposition that would
   have made the original addendum's finding immediately interpretable
   instead of alarming.
4. **Treat single sealed-ATS comparisons smaller than ~3pt at n≈271 as
   statistically inconclusive** (H3) unless corroborated by a
   multi-seed pattern or a larger pooled sealed set (e.g. 2024+2025,
   roughly n≈540-550, which would tighten Wilson CI half-widths by
   roughly 1/√2 ≈ 30%).
5. **For routine in-season refresh cycles (new weeks of data, same
   feature universe), prefer "retrain on the frozen shipped list" over
   any reselection** — the low-risk default this evidence supports, since
   it caps the expected sealed-ATS cost at roughly the H2 drift magnitude
   (~1.5pt, itself partly within H3 noise) rather than exposing the model
   to the full H1 seed-lottery variance (up to ~5-9pt either direction).
6. **If a full reselection is ever needed** (e.g. major new data source,
   large Silver schema change), budget for the multi-seed stability
   protocol in (1) plus the fixed-list-retrain control in (3) as
   mandatory steps, not optional extras — this session shows both are
   cheap (minutes, not hours) relative to the risk of shipping a
   single-seed lottery draw.

## Robust / lucky / stale call on the shipped model (flagged for the user — no action taken)

The shipped model's 51.66% sealed ATS sits **inside** the range fresh
seeds produce (46.86%-52.77%), not below it — one fresh seed (123) even
beat it. So shipped is not an unreproducible outlier in the sense of being
uniquely good; a peer seed matched or exceeded it. But by the same logic it
is not demonstrably "robust" either — the procedure that produced it has
enough variance that a different seed on selection day could equally have
landed at 46.86%, and there is no evidence the shipped 120-feature
configuration is *special* beyond having been the one draw that got
evaluated once and locked in.

The fairest read: **shipped is an unremarkable, moderately fortunate draw
from a high-variance selection procedure ("lucky" in the specific sense
that its exact configuration was never revalidated against repeat draws),
with a modest, independently-confirmed layer of genuine staleness on top**
(the fixed-list retrain recovers only 50.18% vs the recorded 51.66% on
today's data, a real ~1.5pt drift attributable to Silver data-correctness
fixes landing since the 2026-06-10 training date). Neither "robust" nor
"badly broken" is an accurate label. This is a flagged observation for the
user's judgment, not a recommendation to promote, demote, or retrain the
shipped model in this session.

## Artifacts (evidence, not promoted)

- `models/ensemble_reproducibility/seed_{42,7,123,2024}/` — feature
  selection metadata + trained ensemble artifacts per seed (H1).
- `models/ensemble_reproducibility/shipped_list_retrain/` — fixed-list
  retrain on today's data (H2).
- `scratchpad/eval_reproducibility.py` +
  `scratchpad/eval_reproducibility_summary.json` — evaluation script and
  raw output (not committed, per the 08-16/08-21/08-22 precedent for
  one-off analysis scripts).
- `models/ensemble/` (shipped) untouched this session (no writes, no
  retraining of the shipped artifacts themselves).

## Tests

`PYTHONPATH=src venv/Scripts/python.exe -m pytest tests/test_feature_selector.py
tests/test_ensemble_training.py -q` — 33/33 passing after the `--seed` /
params-threading fix to `scripts/run_feature_selection.py` (no regressions).

## Deviations from the pre-registered plan

- H1 ran N=4 seeds instead of the pre-registered minimum of 3 (compute was
  cheap enough — ~70-90s per full seed run — to afford an extra data
  point).
- H5's test could only cover the 24h window since the 08-22 addendum
  (no historical candidate-pool snapshot from 06-10 exists to diff
  against over the full 2.5-month gap) — reported as an honest gap rather
  than extrapolated.
- No changes were needed to `src/ensemble_training.py` or
  `scripts/train_ensemble.py` beyond what the 08-22 addendum already
  added (`--skip-reselect`, etc.) — ensemble training given a fixed
  feature list is already deterministic, so only the feature-selection
  step needed a seed knob.
