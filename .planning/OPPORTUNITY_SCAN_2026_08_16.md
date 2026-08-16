# Opportunity Scan — 2026-08-16

Follow-up to `HYBRID_SHIP_2026_08_15.md` (QB/RB/TE hybrid ship, correction
clamp, WR recovery) and `MODEL_REVIEW_2026_08_15.md` (serve-path integrity
findings). That task changed the error structure this repo has been steering
by for months — `CONSENSUS_ERROR_DECOMPOSITION.md` (2026-08-08) is now
**stale**: it describes a config where RB lost to both sources and QB lost to
ESPN. Neither is true anymore. This report: (1) redecomposes the error
structure under the shipped config, QB/RB/TE only (WR is a concurrent agent's
active workstream — not touched, not re-sliced here), (2) inventories
what's next beyond slice-fixing, ranked by evidence-grounded expected value.

## Method note — reused, did not regenerate, the exact matched population

`HYBRID_SHIP_2026_08_15.md` §7 already produced
`output/backtest/pooled_2022_2024_{sleeper,espn}_matched.csv` (n=7,009 /
n=6,721 — byte-identical population to its own headline table) same-session,
same repo state as what's live now. Rerunning `backtest_projections.py`
would have reproduced the same rows at ~30min cost; instead ran
`scripts/decompose_consensus_errors.py --positions QB RB TE` directly against
those files (sanity-check assertions in the script confirm the gap math
matches `consensus_metrics.compute_mae_gap` exactly). Output:
`output/backtest/decompose_newconfig/decompose_{source}_{QB,RB,TE}_*.csv`.

---

## PART 1 — Fresh error decomposition (QB/RB/TE, new config)

### Headline: the loss structure the old report described is gone

| Position | vs Sleeper (old → new) | vs ESPN (old → new) |
|---|---|---|
| QB | −0.386 win → **−0.861 win** | +0.230 **loss** → **−0.260 win** |
| RB | +0.319 **loss** → **−0.310 win** | +0.221 **loss** → **−0.381 win** |
| TE | −0.195 win → **−0.454 win** | −0.202 win → **−0.453 win** |

Old finding #2 (RB magnitude-band miscalibration, both tails), #3 (QB backup
under-projection), #4 (RB committee-back contributor list) — all were
diagnosing a heuristic-only QB/RB that no longer exists in production. Below
is what the *hybrid* QB/RB/TE actually look like, sliced the same way.

### Every slice tested is now a win for QB/RB/TE vs both sources — with one exception

| Position/Source | Slice | n | gap | reliable |
|---|---|---:|---:|---|
| **QB vs ESPN** | **magnitude &lt;8** | **75** | **+0.152 (loss)** | yes |
| QB vs ESPN | week 13-18 | 465 | −0.170 | yes |
| RB vs ESPN | magnitude 14+ | 477 | −0.076 | yes |
| RB vs Sleeper | week 3-6 | 529 | −0.261 | yes |
| RB vs Sleeper | season 2024 | 607 | −0.119 | yes |
| QB vs ESPN | season 2024 | 421 | −0.009 | yes |
| RB vs ESPN | season 2024 | 628 | −0.184 | yes |
| TE vs Sleeper | magnitude &lt;8 | 451 | −0.595 | yes |
| TE vs ESPN | season 2022 | 289 | −0.585 | yes |

**The only losing slice found anywhere in QB/RB/TE, either source, any cut
(magnitude/week/season/archetype) is QB &lt;8-projected-points vs ESPN**
(n=75, gap +0.152, our_bias −3.98 vs ESPN's +3.47 — we still badly
under-project this backup/spot-starter bucket, ESPN still over-projects it
the other way). This is the direct descendant of old finding #3
("backup QB thrust into a starting role") — the QB retrain closed **92%** of
it (+1.850 → +0.152 magnitude) but did not fully close it. Same slice vs
Sleeper is no longer separately reliable-loss (Sleeper's own bias moved), so
this is now a single, small, ESPN-specific residual of a mechanism that used
to be a top-3 systemic problem. Not worth a dedicated lever at n=75 and
+0.15 gap — flag and monitor, don't build for it.

### Where the win is thinnest (ranked, reliable slices only)

1. **QB vs ESPN, &lt;8pt magnitude** — the one loss above.
2. **RB vs ESPN, 14+ magnitude** (−0.076, n=477) — RB's old high-end
   over-projection tail (finding #2) is now barely positive; residual
   correction clamp + retrain compressed it almost to parity but didn't
   overshoot into a wide win the way the low/mid bands did.
3. **QB vs ESPN, week 13-18** (−0.170, n=465) and **QB vs ESPN, season 2024**
   (−0.009, n=421, essentially a coin flip) — both point at the same
   season, see the cross-position pattern below.
4. **RB vs Sleeper/ESPN, season 2024** (−0.119 / −0.184) — thinnest RB
   season margin at both sources.

### Cross-position pattern (new, not in the old report): 2024 is the thinnest-margin season everywhere

| Position | Source | 2022 gap | 2023 gap | 2024 gap |
|---|---|---:|---:|---:|
| QB | Sleeper | −1.575 | −0.806 | **−0.219** |
| QB | ESPN | −0.362 | −0.425 | **−0.009** |
| RB | Sleeper | −0.409 | −0.395 | **−0.119** |
| RB | ESPN | −0.447 | −0.519 | **−0.184** |
| TE | Sleeper | −0.541 | −0.361 | −0.459 |
| TE | ESPN | −0.585 | −0.394 | −0.391 |

QB and RB show a **clean monotonic decay** toward 2024 at both sources (TE is
mixed — 2024 is thinnest vs Sleeper but not vs ESPN). This is the single
most interesting *new* pattern the redecomposition surfaced — it wasn't
visible in the old heuristic-only report because RB/QB weren't hybrid then.
**Open question, not yet diagnosed**: training data for the shipped QB/RB
residuals runs 2016–2024 inclusive (`HYBRID_SHIP_2026_08_15.md` §9
provenance table), so 2024 is partially in-sample for the *residual model*
even though `backtest_projections.py`'s walk-forward heuristic layer never
sees future data — worth a dedicated check (does the residual model's own
CV fold structure leak 2024 into itself, or is 2024 genuinely a harder year
for reasons visible in the data — e.g. the snap_pct/NGS join-bug fix dated
this same week touched exactly this seasons' input quality)? **Do not
action this as a lever yet** — flag for the next retrain-hygiene pass to
confirm whether the shrinking margin is walk-forward-real or a CV-fold
artifact before reading anything causal into it.

### Archetype splits — old contradictions resolved, no new lever

- QB rushing-share vs ESPN: Low −0.232, Mid −0.236, High −0.312 — still
  weakest at Low (pocket passers), same *direction* as old finding #5, but
  now a win at every tier instead of Low being a loss. No action needed —
  the old asymmetry shrank in place rather than flipping.
- RB receiving-share: old finding #6 was an inconclusive Sleeper/ESPN
  contradiction (pass-catchers worst per Sleeper, pure runners worst per
  ESPN). New numbers: Sleeper Low −0.388 (still worst) vs High −0.130 (still
  best); ESPN Low −0.422 (still worst) vs High −0.258. **The contradiction
  is gone** — both sources now agree Low (pure-runner) RBs are our weakest
  tier, though still a clear win. Consistent, low-priority signal; not
  reliable enough on its own to justify a new feature.

### Top contributors — no more systemic multi-player pattern

Old finding #3 had ~15 different backup QBs repeating the same
under-projection direction across two source files — a real systemic
pattern despite no single player clearing n≥50. **That pattern is gone.**
The new top-20 contributor lists (QB/RB/TE, both sources) are dominated by
single-game or few-game outliers (T.McKee n=1 gap +11.8, J.Stidham n=2 gap
+5.9-8.5, Z.White n=6 gap +2.7-4.0) with no repeating cross-source
signature — consistent with the retrain having absorbed the systemic part of
the old problem, leaving only irreducible small-sample noise.

**Bottom line for Part 1**: QB/RB/TE no longer have a slice-fixing backlog
worth building for. The one reliable loss (QB &lt;8pt vs ESPN) is 92% smaller
than its predecessor and too small-n to spend model-engineering effort on.
The next real lever is not "which slice do we still lose" (answer: almost
none) — it's Part 2.

---

## PART 2 — Ranked opportunity inventory

Each candidate: EV (order-of-magnitude, grounded in data pulled this
session), cost, evidence. WR-specific items are out of scope (owned by the
concurrent agent) but noted where a shared mechanism (PBP/graph, quantile)
also touches WR.

### 1. Weekly props-blend — backfill the historical archive (cheap, high evidence-per-dollar)

**EV: unknown-but-cheap-to-find-out. Cost: ~$29-99 one-time/monthly, no
engineering.** `PROP_IMPLIED_DECISION.md` pre-registered a full backtest
plan in June (2023 w5–18 + 2024, SHIP if WR/RB MAE gap improves ≥0.05 or
Spearman gap narrows ≥0.02) but it was **never run** — confirmed this
session: `data/bronze/odds_api/props/` (the weekly per-player prop archive)
does not exist locally at all; only `data/bronze/odds_api/snapshots/
season=2026` (live-forward captures) and `data/bronze/dk/season_props`
(preseason futures, different product) exist. The historical Odds API tier
that would backfill 2023–2024 for a real backtest was never purchased
(`ODDS_API_KEY` blocked, per the decision memo). **This is the one
candidate on this list that is currently blocked purely on a small
purchase, not on engineering or waiting for the season** — buying the
$29/mo historical tier for one month turns an "eval once Sunday snapshots
accumulate" (STATE.md open thread #4, i.e. wait until October) into
something testable *this week* against 2023-2024. Gate: reuse the
pre-registered one verbatim, no redesign needed.

### 2. Ensemble game-model + player-aggregate features (untested architecture idea, moderate cost)

**EV: plausible, order 0.5-1.5pt ATS based on adjacent evidence. Cost:
moderate — one feature-engineering + retrain + backtest cycle, same shape
as the health-check already run.** `ENSEMBLE_HEALTH_2026_08_15.md`
confirmed the shipped 120-feature game ensemble reads **only**
`SILVER_TEAM_LOCAL_DIRS` — it has never once joined `players/usage` or
`players/advanced` into game-level features; it is architecturally isolated
from the fantasy pipeline's repaired data. The same report also shows this
isn't hypothetical: a routine **value refresh** (not even a new feature) of
`teams/player_quality` — which already IS a partial player-aggregate
signal (skill/def/QB injury impact) — moved the sealed-2025 spread ATS by
+0.8pt on 271 games, just from updated injury values. If a value refresh of
one existing aggregate feature moves ATS by 0.8pt, genuinely new
player-aggregate features (team-level rolling target-share concentration,
weighted-injury replacement drop-off, aggregate route/snap continuity — all
derivable from the already-repaired `players/usage`/`players/advanced`
Silver, no new ingestion needed) are a real, cheap-to-test hypothesis with
room to move a 52.9%-ATS model that currently has zero player-level signal
feeding it at all. Pre-registerable gate (mirrors the existing house style):
retrain with player-aggregate features added to the 120-feature SHAP pool;
redeploy only if OOF ATS improves ≥0.5pt over shipped **and** sealed-2025
holdout does not degrade.

### 3. PBP bronze + graph feature pipeline (highest structural leverage, highest cost)

**EV: real but diffuse — likely small direct MAE (TE already wins by
−0.45/−0.46; graph features are a small slice of 60), but high leverage on
quantile-interval quality and free-unlocks Bayesian. Cost: high — new Bronze
ingestion (~100-400MB/season × up to 10 seasons) + Silver graph_features
regen + retrain cycle for every family that selected graph features.**
Quantified this session (Neo4j confirmed down locally — "graph features
disabled" — and no local `data/silver/graph_features` fallback either, so
every true graph-module feature live-probes as dead):

| Model | Selected features | Graph-pattern features selected | Live NaN rate on those |
|---|---:|---:|---:|
| QB residual (shipped) | 20 | 0 true graph (1 team-PBP `off_rz_*`, 0% NaN — healthy) | n/a |
| RB residual (shipped) | 20 | 0 true graph (1 team-PBP `off_rz_*`, 0% NaN — healthy) | n/a |
| **TE residual (shipped, in-scope)** | 60 | 0 true graph; 13/60 features ≥50% NaN (all NGS-family, not graph) | 78-91% |
| WR residual (shipped, **other agent's scope**) | 60 | **11/60**, incl. its own top pick `qb_wr_chemistry_epa_roll3` | **100%** |
| Quantile (shipped, conformal bands) | 486 | **58/486** graph-pattern; **183/486 (38%) total ≥50% NaN or missing** (graph + NGS + PFR + FTN combined) | mostly 100% |
| Bayesian (unshipped, all 4 pos) | 60 each | 9-15/60 each, mostly `rz_*`/chemistry | mostly 100% |

Good news: **QB and RB — the two positions this session's hybrid ship
touched — selected zero dead graph features.** Their 20-feature SHAP sets
are clean (the one graph-pattern feature each selected, `off_rz_*`, comes
from the *team*-level PBP-derived Silver path, which **is** populated
locally, 0% NaN — a different, healthier pipeline than the true
per-player graph modules). The dead-feature problem is concentrated in the
60-feature TE/WR/bayesian sets and the 486-feature quantile set. Given QB/RB
are clean and TE already wins comfortably, this is not an urgent fix for
accuracy — its real value is (a) unblocking a legitimate Bayesian
reactivation decision (currently can't even evaluate Bayesian on real
signal) and (b) quantile/conformal interval quality, which is the newest
production-serving surface (`QUANTILE_REFIT_2026_08_15.md`, just fixed from
crashing) and therefore has the least accumulated validation. Gate:
mirror the TE gate from `HYBRID_SHIP_2026_08_15.md` §6 (redeploy only if a
graph-repaired retrain beats current shipped on both sealed-2025 and
2022-24) for TE; for quantile, gate on p10-p90 coverage staying in
[0.75, 0.85] and pinball loss improving, matching `QUANTILE_REFIT_2026_08_15.md`'s
own gate shape.

**Caveat pulled from the same probe, not a separate action item**: NGS-family
features are 75-91% NaN across *every* family (QB/RB/WR/TE residual,
all 4 Bayesian, quantile) — a much bigger blast radius than graph features,
but likely genuine NFL data sparsity (NGS only covers players who clear a
per-week qualification threshold — attempts/routes/carries), not a pipeline
bug analogous to the PBP gap. Recommend a cheap diagnostic (compare our NaN
rate against nfl_data_py's own documented NGS qualification thresholds)
before treating this as a project — it may not be fixable at all, and is
therefore not ranked as its own opportunity here.

### 4. K/DST (product-completeness, not an accuracy-competition lever)

**EV: real for product completeness, ~zero for the FantasyPros competition
metric this quarter's work has been chasing. Cost: moderate — comparable in
shape to the existing kicker build.** Confirmed: kickers are fully built
(`src/kicker_analytics.py`, `src/kicker_projection.py`,
`scripts/backtest_kicker_projections.py`, `--include-kickers`) and shipped.
**DST has no ingestion, analytics, or projection module anywhere in `src/`**
— every `DST` reference in the codebase is roster-slot bookkeeping
(`ROSTER_CONFIGS`) or pass-through of *external* Sleeper/ESPN DST rankings,
never our own model. Building it (team defensive box-score ingestion —
sacks/INTs/fumbles/safeties/def-and-ST TDs/points-and-yards-allowed tiers —
plus a scoring + projection module) is realistic, similar order of effort
to the kicker build. **But**: `FP_ACCURACY_SIMULATION.md` confirms
FantasyPros' own "Overall" competition score explicitly **excludes K/DST
"for consistency reasons"** — so this does not move the metric Part 1/the
ordinal work below is optimizing for. Its value is that every real
default-format league roster has a DST slot our draft/lineup tools
currently cannot fill with a first-party projection (falls back to
whatever external source is wired in). Rank below #1-3 on pure model-EV
grounds; revisit if/when product roadmap prioritizes full-roster
first-party coverage over accuracy-competition standing.

### 5. Ordinal-specific optimization (FP rank-vs-points calibration) — largely already solved

**EV: low remaining — the QB/RB/TE hybrid ship already captured most of
this. Cost: n/a, already spent.** Two independent pieces of evidence:
(a) `HYBRID_SHIP_2026_08_15.md` §7 reran the exact FantasyPros ordinal
simulation (`scripts/simulate_fp_accuracy.py`) under the new config: QB/RB/TE
all **flip from losing to beating both sources** (QB 7.21→6.59 vs
Sleeper 7.19/ESPN 7.18; RB 6.18→5.43 vs 5.92/5.91; TE 6.33→5.70 vs
6.12/6.15) — this is new since the stale `FP_ACCURACY_SIMULATION.md`
(2026-08-08) which showed us losing at every position. (b)
`RANK_ORDERING_EXPERIMENTS.md` already ran a disciplined mechanism sweep in
June (TPRR level/interaction/slope, spread-conditioned game-script) — one
mechanism shipped (TPRR-slope collapse, confirmed live in
`src/projection_engine.py`), every other mechanism was KILLed with a
consistent diagnosis: **within-team reordering (which RB/WR gets the
touches) needs OL-grade or team-tendency data we don't have** — explicitly
deferred to the PFF ~Nov decision, not fixable with data already in hand.
Remaining ordinal gap is WR-only (other agent's scope). Not worth new
model-engineering effort here until either PFF lands or WR's specific gap
is separately tackled.

### 6. Bayesian reactivation — deprioritize

**EV: low. Cost: retrain required regardless of any decision.**
`MODEL_REVIEW_2026_08_15.md` finding #14 already flagged Bayesian as
"stalest in repo, unwired." This session's probe adds: 9-15/60 selected
features per position are ≥50% (mostly 100%) NaN — worse dead-feature ratio
than the shipped residual families, and it has never served a real request
(`--conformal-bands` uses the newly-fixed quantile path, not Bayesian).
Recommend formally marking research-only rather than budgeting a
reactivation project — there's no current product surface that needs a
posterior distribution instead of the quantile interval it already gets.

### 7. Weekly-report/product-side items — out of scope, tracked elsewhere

Billing go-live, in-season gates (line-capture w10, props eval once Sunday
snapshots land), PFF ~Nov decision — all already tracked in
`.planning/STATE.md` open threads 1/4 and are ops/product timing items, not
model-improvement candidates this scan can rank. Not duplicated here.

---

## Top-3 recommendation

1. **Buy the Odds API historical props tier for one month and run the
   already-pre-registered weekly props-blend backtest** (candidate #1).
   Cheapest possible way to convert "wait for the season" into "know this
   week." Gate: `PROP_IMPLIED_DECISION.md`'s own — SHIP if WR/RB MAE gap
   improves ≥0.05 or Spearman gap narrows ≥0.02 at either position, no
   QB/TE regression.
2. **Add player-aggregate (repaired usage/advanced) features to the game
   ensemble's SHAP candidate pool and retrain** (candidate #2). Never
   attempted; the architecture has been player-blind since inception; a
   routine refresh of an existing partial player-aggregate feature already
   moved ATS 0.8pt, suggesting real headroom on a 52.9%-ATS model. Gate:
   redeploy only if OOF ATS improves ≥0.5pt over shipped and sealed-2025
   holdout does not degrade (same shape as the gate `ENSEMBLE_HEALTH_
   2026_08_15.md` already used and rejected the no-op retrain against).
3. **Ingest PBP bronze + regenerate Silver graph_features, then retrain TE
   (in-scope) and refit the quantile model** (candidate #3, scoped down from
   the full "22/66-feature" ask to the two families where it's cheap to
   validate — TE already has a gate template, quantile already has a gate
   template). Skip WR (other agent) and Bayesian (deprioritized, #6) in this
   pass. Gate: TE — beat shipped on both sealed-2025 and 2022-24 pooled MAE
   (mirrors `HYBRID_SHIP_2026_08_15.md` §6); quantile — p10-p90 coverage
   stays in [0.75, 0.85] per position and pinball loss improves (mirrors
   `QUANTILE_REFIT_2026_08_15.md`'s own gate).

Not recommended for this cycle: DST (product-completeness, not an accuracy
lever — #4), further ordinal-specific mechanism search (already swept,
blocked on PFF data — #5), Bayesian reactivation (no consumer, worse
dead-feature ratio than what's already shipped — #6).
