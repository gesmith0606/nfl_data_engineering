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
