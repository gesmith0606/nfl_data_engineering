# Why the WR residual model "fell back to the heuristic" every week (2026-10-22)

Follow-up to `MODEL_ASSESSMENT_2026_10_21.md` finding 4, which recorded that
`WARNING: No matching features for WR residual model; returning heuristic`
fired on every 2026 week and guessed it might be the graph-feature gap. It is
not. The diagnosis below replaces that guess.

## Correction to the assessment's framing

Two things the assessment got wrong:

1. **It is WR only.** TE is unaffected — CI logs
   `TE (ridge): 60/60 features available` with no fallback. The assessment
   said "WR/TE residual model".
2. **It was never a full fallback.** The primary WR model ran fine the whole
   time; what failed was a *secondary* model inside a blend, and the result
   was a partial dilution, not a reversion to the heuristic.

## Root cause

The CI log for week 7 (run 39399905562) shows the two calls back to back:

```
INFO  WR (ridge): 60/60 features available after graph enrichment; 0 imputed
WARN  No matching features for WR residual model; returning heuristic
INFO  TE (ridge): 60/60 features available after graph enrichment; 0 imputed
```

60/60 available, then a fallback one line later. `apply_residual_correction`
is called **twice** for WR: once by the router (succeeds) and once
recursively by itself, for the secondary-model blend added in
`WR_GAP_FIX_2026_08_16.md`:

```python
blend_dir = meta.get("blend_secondary_dir")       # models/residual_wr_secondary
blend_weight = meta.get("blend_weight")           # 0.4
if blend_dir and blend_weight:
    secondary_result = apply_residual_correction(..., model_dir=blend_dir)
    blended = primary * (1 - w) + secondary * w
```

The chain:

1. `models/residual_wr_secondary/` contains `wr_residual.joblib` **and nothing
   else** — the `wr_residual_meta.json` was never committed.
2. `load_residual_model` tolerates a missing meta by design
   (`meta: Dict = {}`; it only raises when the *artifact* is absent), so it
   returns the model with empty metadata.
3. `features = meta.get("features", [])` is therefore `[]`, so
   `available = []`, so the function logs the warning and returns
   `heuristic_projections` — the **uncorrected** heuristic.
4. The caller treats that as a legitimate secondary prediction and blends it.

So every WR projection since 2026-08-16 was

```
0.6 * primary_corrected + 0.4 * raw_heuristic
```

— the WR Ridge hybrid running at 60% strength, reported in the logs as a
successful blend (`WR: blended with secondary model ... at weight=0.40`).
**The WR_GAP_FIX_2026_08_16 blend never ran as designed**, so whatever that
gate measured is not what production did.

The secondary's feature list is recoverable from the artifact itself
(`pipe.feature_names_in_`, 60 features matching the primary's recipe), which
is how variant C below was built.

## Measured impact: real bug, benign effect

Three configurations through the real backtest path, 2026 w3-6, half-PPR,
`--ml --vs-consensus`. Provenance was checked per run: A logged the fallback
on all four weeks, B logged none (proving the primary alone is healthy).

| variant | WR MAE (n=488) | matched MAE (n=237) | rho | top-24 hit |
|---|---|---|---|---|
| **A — as shipped** (0.6 primary + 0.4 raw heuristic) | **3.88** | 5.13 | 0.321 | 0.542 |
| **B — primary only** (blend keys removed) | 3.92 | 5.15 | 0.311 | **0.552** |
| **C — correct blend** (secondary meta reconstructed) | 3.96 | **5.12** | 0.311 | 0.552 |

**The bug was slightly helping.** The accidental dilution toward the raw
heuristic scored the best full-set MAE of the three (3.88 vs 3.92/3.96) and
the worst hit rate (0.542 vs 0.552). Every difference is inside noise at
n=237-488, and the ordering of the three flips depending on which metric you
pick. There is no accuracy case for any of them over the others.

That is consistent with the rest of this season's evidence: the residual
correction contributes little on top of a strong heuristic, so reverting 40%
of it toward the heuristic costs nothing measurable.

## What shipped

Two changes, neither of which is an accuracy play — do not quote them as one.

1. **A guard against silent dilution** (`_secondary_blend_is_usable`). A
   fallback is not a prediction: `apply_residual_correction` returns the
   untouched heuristic when it cannot run, and the return value alone cannot
   express that. The blend branch now verifies the secondary is actually
   usable (artifact present, meta carries a feature list, at least one feature
   satisfiable) and otherwise keeps the primary correction alone, logging a
   `::warning::` that names the weight that *would* have been reverted. This
   is a correctness property and applies to any future blend, at any position.
2. **The dangling blend keys removed** from `wr_residual_meta.json`, with the
   reason recorded in the file as `blend_disabled_2026_10_22`. Variant B was
   chosen over C because it is the only configuration whose provenance is
   verifiable — C requires a meta reconstructed from the artifact, guessing
   the training population and clip, for no measurable gain.

Tests: `tests/test_secondary_blend_guard.py` (11 cases) pins the shipped
failure state, the usable case, graph-feature satisfiability, and the
behavioural contract that an unusable secondary leaves the primary correction
byte-identical.

## Incidental: Silver player features have the same staging gap

The fallback reproduced locally for a *different* reason worth recording:
`data/silver/players/usage/` stopped at season=2025, so
`assemble_player_features(2026)` returned **0 rows, 0 columns** (2025 returns
4,085 x 700) and the whole ML path degraded locally. The weekly workflow
computes Silver player features every run; the commit step never staged
`data/silver/players/`, exactly as it never staged
`data/silver/graph_features/`. CI is unaffected (it computes Silver and
projects in the same job), but the repo and the HF prod clone carry none of
it, and neither does any local run.

Generated locally via `silver_player_transformation.py --seasons 2026`
(1,196 x 445 for weeks 2-6, fewer columns than CI because the advanced
profiles were not regenerated). **Not committed here** — a full season of
Silver player features is a different size question from graph features and
deserves its own decision rather than being smuggled into this fix.

## Still open

- Whether to stage `data/silver/players/` weekly (size vs prod parity).
- `projection_source` reads `hybrid` on every row even when a position ran
  heuristic-only, which is why this bug was invisible on the boards. Fixing
  the label would have surfaced it in week 1.
- The `WR_GAP_FIX_2026_08_16` gate conclusion should be marked as never
  having been in effect.
