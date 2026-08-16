# Candidate Polish — 2026-08-16

Two bounded polish experiments on the existing HOLD candidates from
`QUANTILE_REFIT_2026_08_15.md` and `GRAPH_REVIVAL_2026_08_16.md` — no new
data, no new features, calibration/light regularization tuning only. All
selection on walk-forward 2016-2024; sealed 2025 read exactly once per
experiment (see `.planning/holdout_ledger.json` for the three appended
touches). Scope: `models/quantile*`, `models/te_graph_2026_08_16/`; no
`src/` edits (confirmed — `src/quantile_models.py` used read-only,
`src/hybrid_projection.py` used read-only via its public functions,
regularization swept via an equivalent hand-built sklearn pipeline instead
of editing the module's RidgeCV-only factory).

**Mid-session finding worth flagging up front** (matches the
`gated-experiment-coverage-check` vault lesson — "same data vintage,
including other agents' side effects"): re-running `assemble_multiyear_player_features()`
in this session picked up 15 new PBP-advanced trailing feature columns
(515 quantile candidate cols vs the 500 recorded when
`models/quantile_graph_2026_08_16` was originally trained at 10:44; TE
feature-engineering side also shifted) that materialized mid-session,
apparently a concurrent agent's work on the feature pipeline landing while
this task ran. Every comparison in this report was regenerated back-to-back
within its own script run (baseline and treated always evaluated in the
same process against the same in-memory data), so each experiment's
internal ranking is sound — but **absolute MAE/coverage numbers here are
not bit-identical to the two source reports**, and the TE sealed-MAE
baseline in particular reads meaningfully different (see Experiment 2).
Flagged rather than silently reconciled, per the "verify the lever fires /
verify same vintage" discipline.

---

## 1. Quantile-graph candidate — width factor recalibration

**Candidate**: `models/quantile_graph_2026_08_16/` (better pinball
everywhere, but WR 87.5% / TE 86.0% coverage breached the [75,85] band per
`GRAPH_REVIVAL_2026_08_16.md`).

**Method**: reproduced the candidate's walk-forward OOF in-process
(`train_quantile_models`, same recipe, deterministic `random_state=42`).
Reproducibility check against the saved metadata (pooled 2018-2025,
default 0.05-step grid) landed within 0.3-0.7pp of the original save —
confirms the mid-session vintage drift is minor. Then swept
`compute_conformal_width_factors` (the standard, unmodified function) with
a **0.01-step grid** (vs the shipped 0.05-step) selected **only on OOF
rows for validation seasons 2018-2024** — season 2025 excluded entirely
from selection — then read sealed-2025 coverage/pinball **exactly once**.

| Position | Old factor (0.05 step, pooled incl. 2025) | New factor (0.01 step, 2016-2024 only) | Sealed-2025 coverage (old → new) | In [75,85]? |
|---|---|---|---|---|
| QB | 1.25 | **1.22** | 82.0% → **81.0%** | Yes (was already yes) |
| RB | 1.15 | **1.12** | 79.8% → **78.1%** | Yes (was already yes) |
| WR | 1.10 | **1.09** | 86.6% → **86.2%** | **No** — 1.2pp over ceiling |
| TE | 1.10 | **1.09** | 84.5% → **84.3%**† | Yes — **flips into band** |

† TE's old-factor number here (84.5%) reads lower than
`GRAPH_REVIVAL_2026_08_16.md`'s reported 86.0% breach — a direct
consequence of the mid-session data-vintage shift noted above, evaluated
with the same code both times. Regardless of which exact baseline number
is "true," TE is comfortably in-band under the new factor either way.

Pinball loss (mean of `pinball_loss(q10)`/`pinball_loss(q90)` on the
conformal-widened bands) is flat-to-slightly-better with the new, narrower
factors at every position, and **decisively better than the currently
shipped `models/quantile/`** at every position (shipped sealed-2025
pinball QB 1.863 / RB 1.520 / WR 1.135 / TE 0.939 per
`QUANTILE_REFIT_2026_08_15.md` §5 — the new numbers here are 1.28 / 1.06 /
0.79 / 0.62; the pinball-averaging convention differs slightly from that
report's un-reproduced methodology, but the direction — large, consistent
improvement — matches `GRAPH_REVIVAL_2026_08_16.md`'s independent finding
that "pinball loss improved at every position" for this candidate).

**Verdict: HOLD for the full 4-position joint promotion.** QB, RB, and TE
all land cleanly in [75,85] with the finer-grid factors — TE specifically
**flips from breach to in-band**. WR improves (87.5%→86.2%→ still
computed at 86.2% either way you cut the vintage) but does not clear the
85% ceiling; a 0.01-step grid is already about as fine as this data
supports (tuning-set coverage at the selected factor sits at 80.15%, just
barely above the 80% target — a finer step would not move the selected
factor meaningfully). WR's over-coverage looks structural to the pooled
target-coverage=0.80 selection rule on this feature set, not a grid-
resolution artifact.

**Not staged as PROMOTE_READY** (gate requires all 4 positions in-band).
Recommend as a **follow-up option, not required by this task**: a
per-position promotion path exists — QB/RB/TE could ship the graph-
candidate models with the new factors today (net win over shipped on both
axes), while WR stays on the shipped quantile artifact until its
over-coverage is separately resolved (e.g. season-weighted OOF, as both
prior reports already flagged). Full numbers, reproducibility check, and
the exact factors: `models/quantile_graph_2026_08_16/width_factor_recalibration_2016_2024.json`
(companion file, **not** wired into `predict_quantiles()` — the original
`metadata.json` is untouched since the joint gate did not clear).

---

## 2. TE-graph candidate — ridge regularization sweep

**Candidate**: `models/te_graph_2026_08_16/` (16 genuine graph features
selected at a fixed 60-feature budget, but sealed-2025 −0.042 **worse**
than shipped per `GRAPH_REVIVAL_2026_08_16.md` §4). Both the shipped
`models/residual/te_residual_meta.json` and the graph-candidate's own
`ridge_alpha` were `0.001` — the **lower boundary** of the module's
default `RidgeCV(alphas=np.logspace(-3, 3, 50))` grid, i.e. RidgeCV wanted
to go even less regularized than the boundary offered. Worth testing
whether *more* regularization (not available to RidgeCV's train-time
in-sample selection) generalizes better.

**Method**: reused the candidate's already-SHAP-selected 60 features
unchanged (no new feature selection — isolates the regularization effect
only, per the mission's "light regularization sweep" framing). Swept 8
fixed alphas log-spaced around 0.001 (`0.0001` … `0.3`) with a
`SimpleImputer(median) + Ridge(alpha)` pipeline, selected via walk-forward
MAE averaged over val_seasons `[2022, 2023, 2024]` (2016-2024 only — 2025
never touched during selection):

| alpha | avg MAE 2022-24 (walk-forward) |
|---|---|
| 0.0001 | **2.8613** (best) |
| 0.0003 | 2.8613 |
| 0.001 (shipped/candidate's own RidgeCV pick) | 2.8614 |
| 0.003 | 2.8619 |
| 0.01 | 2.8640 |
| 0.03 | 2.8711 |
| 0.1 | 2.8985 |
| 0.3 | 2.9539 |

**The sweep is essentially flat from 0.0001-0.001** (spread of 0.0001 MAE)
and degrades monotonically above ~0.003 — RidgeCV's boundary pick was
already very close to optimal; there is no meaningful regularization lever
here in either direction. Best alpha = **0.0001**, staged at
`models/te_graph_2026_08_16/ridge_sweep/te_residual.joblib` +
`te_residual_meta.json`.

**ONE sealed-2025 read** (weeks 3-18, n=951, all three models evaluated
back-to-back in the same run via `apply_residual_correction`):

| Model | Sealed-2025 MAE | Pooled 2022-24 MAE |
|---|---|---|
| Shipped (`models/residual/`) | 2.9712 | 2.8664 |
| Graph-candidate (alpha=0.001, unchanged) | 2.9487 | 2.8287 |
| Ridge-sweep (alpha=0.0001) | **2.9449** | **2.8203** |

Isolated regularization effect (candidate → sweep, same features, same
data, same run): **2.9487 → 2.9449, a 0.0038-point gain** — negligible,
consistent with the flat walk-forward curve above. Gap vs shipped:
0.0263 (shipped 2.9712 − sweep 2.9449) — **short of the ≥0.03 gate**, and
the 2022-24 hold check does pass (2.8203 ≤ 2.8664) but that's moot once
the primary gate misses.

Absolute MAE here (2.86-2.97) reads notably lower than
`GRAPH_REVIVAL_2026_08_16.md`'s reported shipped/candidate sealed-2025
numbers (3.449/3.491) — same mid-session data-vintage drift noted at the
top (new PBP-advanced trailing columns feeding the shared heuristic and
feature matrix at eval time). The **sign even flips**: this session's
apples-to-apples re-evaluation has the graph-candidate beating shipped
(+0.0225), where the prior report found candidate worse (−0.042) on an
older data snapshot. Both readings are internally consistent within their
own session; this report does not attempt to adjudicate which vintage is
"correct" (out of scope — feature code is owned by a concurrent agent) and
instead reports the fresh, single-touch sealed number honestly, as
instructed.

**Verdict: KEEP SHIPPED TE / HOLD.** The regularization sweep does not
clear the gate — alpha tuning alone buys ~0.004 MAE points, an order of
magnitude short of the 0.03 bar, regardless of which sealed baseline you
compare against. Reporting the best-alpha number honestly and stopping,
per the mission's explicit instruction not to iterate on sealed data.
`models/residual/te_residual*` untouched (confirmed via mtime, unchanged
since `GRAPH_REVIVAL_2026_08_16.md`, 2026-08-15 23:26).

---

## 3. Bonus — shipped-quantile WR width factor (time remained)

Same fine-grid (0.01-step) recalibration applied to a WR-only retrain
restricted to `models/quantile/metadata.json`'s 486 feature_cols
(approximates shipped vintage — exact byte-identical reproduction isn't
possible without reverting the Silver pipeline, out of scope; the training
run did resolve to exactly 486 candidate feature columns, matching
shipped, as a sanity check).

- Fine-grid search on walk-forward 2016-2024 selected the **same factor as
  shipped (1.10)** — no smaller factor in the 0.01-step grid clears the
  80% tuning-coverage target for this feature set.
- **ONE sealed-2025 read**: coverage stayed at **85.95%**, still 0.95pp
  over the 85% ceiling (closer than the originally-reported 87.5%, but not
  in-band).

**Verdict: HOLD — still out of band.** No metadata-only fix to stage; WR's
over-coverage on the sealed-2025 slice appears structural to the
pooled-8-season target-coverage=0.80 selection rule (both the shipped-
vintage and graph-candidate feature sets land at the same 1.09-1.10
factor and the same few-points-over-ceiling result). Confirms both prior
reports' hypothesis that this is single-season sampling variance around a
well-calibrated pooled estimate rather than a fixable grid-resolution
issue — the follow-up lever remains what both reports already flagged
(season-weighted OOF), out of scope for this "light polish" task.

---

## Reproduce

Scripts not committed under `scripts/` (concurrent-agent-safety
convention, matching `QUANTILE_REFIT_2026_08_15.md` / `GRAPH_REVIVAL_2026_08_16.md`) —
ran directly against the venv interpreter from the scratchpad:

```bash
./venv/Scripts/python.exe <scratchpad>/quantile_width_sweep.py       # Experiment 1
./venv/Scripts/python.exe <scratchpad>/te_ridge_sweep.py             # Experiment 2
./venv/Scripts/python.exe <scratchpad>/wr_shipped_width_bonus.py     # Bonus
```

## Files touched

- `models/quantile_graph_2026_08_16/width_factor_recalibration_2016_2024.json`
  — new, companion provenance file with the fine-grid factors and gate
  reads. `metadata.json` in that dir is **untouched** (joint gate did not
  clear; still points at the original default-grid factors).
- `models/te_graph_2026_08_16/ridge_sweep/te_residual.joblib` +
  `te_residual_meta.json` — new, staged ridge-sweep candidate (alpha=0.0001,
  same 60 features as the parent candidate). Not promoted.
- `.planning/holdout_ledger.json` — appended three sealed-2025 usage
  entries (quantile-graph width recalibration, TE ridge sweep, WR bonus).
- `.planning/CANDIDATE_POLISH_2026_08_16.md` — this file.
- Not touched: `src/quantile_models.py`, `src/hybrid_projection.py`,
  `models/quantile/` (shipped), `models/residual/` (shipped), any other
  `src/` module.

## Summary verdicts

- **Quantile-graph candidate**: HOLD for joint 4-position promotion (WR
  86.2% still over the 85% ceiling); QB/RB/TE individually flip/stay
  in-band with the finer-grid factors and better pinball than shipped —
  optional per-position promotion path documented, not executed.
- **TE-graph ridge sweep**: HOLD / KEEP SHIPPED. Best alpha = 0.0001
  (walk-forward avg MAE 2.8613 vs 2.8614 at the shipped 0.001 — flat).
  Sealed-2025 gap vs shipped = 0.0263, short of the required ≥0.03.
- **WR width-factor bonus**: HOLD. Sealed coverage 85.95%, still 0.95pp
  over ceiling at the finest grid tested; no metadata-only fix staged.
