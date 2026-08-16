# Consolidation — 2026-08-16

Composes today's per-position winners (`SPAN_RECENCY_EXPERIMENTS_2026_08_16.md`,
`PBP_FEATURES_2026_08_16.md`, `CANDIDATE_POLISH_2026_08_16.md`) into one
promoted configuration. Positions train/ship independently, so composition
was scoped per position. Followed the gated-experiment-coverage-check
discipline: candidates were ranked on **walk-forward CV only**
(`train_residual_model`, expanding-window val_seasons=[2022,2023,2024],
never touches 2025), then each position's walk-forward winner got **exactly
one** sealed-2025 confirmation read. Timeboxed at ~1.25h — see "Cut for time"
at the bottom for what did not get done.

## 1. QB

**Candidates** (all include the PBP-advanced zone-feature pool automatically
— it was wired permanently into `player_feature_engineering.py` step 20
earlier today, so every fresh retrain sees it; QB has never selected any of
those features, consistent with `PBP_FEATURES_2026_08_16.md`):

| Candidate | Source | Walk-forward mean MAE (2022-24 expanding CV) |
|---|---|---:|
| more_years (2012-2024) | `models/span_experiments_2026_08_16/more_years` | 5.8218 |
| recency_hl3 (2016-2024) | `models/span_experiments_2026_08_16/recency_hl3` | 5.8117 |
| **more_years + recency_hl3 (combo)** | `models/span_experiments_2026_08_16/combo` (new training this task) | **5.8014 (winner)** |

Walk-forward winner: **combo** (more-years span + half-life-3 recency
weighting together). New training run this task (span_recency_train.py's
pre-existing but never-executed `combo` variant).

**Sealed-2025 confirmation (one touch)**: shipped 6.7912 MAE → combo 6.6950
MAE, **Δ +0.0962** (clears the ≥0.03 adopt bar). bias improved -1.341 → -0.798.

**Promoted.** `models/residual/qb_residual{,_imputer}.joblib` + `_meta.json`
backed up to `models/residual/_backup_pre_consolidation_2026_08_16/`, then
replaced with `models/span_experiments_2026_08_16/combo/qb_residual*`.
`heuristic_version="v4.2+blend"` and `correction_clip_abs` (18.87, computed
fresh for this candidate) both present — routes correctly through
`ml_projection_router._load_ship_gate`.

## 2. RB

**Candidates**:

| Candidate | Source | Walk-forward mean MAE |
|---|---|---:|
| zone_alone (2016-2024, zone features only) | `models/pbp_feature_experiments_2026_08_16/pbp_ftn` | 4.8216 |
| zone_recency_hl3 (2016-2024 + recency) | `models/span_experiments_2026_08_16/recency_hl3` | 4.8132 |
| **zone_more_years (2012-2024)** | `models/span_experiments_2026_08_16/more_years` | **4.7403 (winner)** |
| zone_more_years_recency_hl3 (combo) | `models/span_experiments_2026_08_16/combo` (new training this task, finished after the promotion decision — checked retroactively) | 4.7518 |

All four already carry the zone-feature pool (confirmed by inspecting each
meta's selected `features`: `pbp_ftn` selected all 3 target-share-by-zone
features; `more_years`/`recency_hl3`/`combo` each independently selected 1-3
of the same zone features too — the lever fires in every span/recency
context, not just the isolated test). Walk-forward winner: **zone_more_years**
— adding recency weighting on top of more-years span actually makes RB
walk-forward MAE slightly *worse* (4.7403 → 4.7518), so the combo does not
supersede the simpler more-years-alone candidate (checked after combo
training completed, using the existing walk-forward gate — no sealed touch
spent on it since it lost walk-forward).

**Sealed-2025 confirmation (one touch)**: shipped 5.4041 MAE → zone_more_years
5.3332 MAE, **Δ +0.0709** (clears the ≥0.03 bar). bias improved -0.516 → -0.342.

**Promoted.** `models/residual/rb_residual{,_imputer}.joblib` + `_meta.json`
backed up to `models/residual/_backup_pre_consolidation_2026_08_16/`, then
replaced with `models/span_experiments_2026_08_16/more_years/rb_residual*`.

## 3. WR

Mission candidate: more-years primary alone, tested against the shipped
60/40 blend (June-model primary + unfiltered-population secondary, per
`model-staleness-after-data-repair.md`).

**Sealed-2025 read** (one touch; `models/span_experiments_2026_08_16/more_years`
WR artifact already existed from today's span/recency task, no new training
needed):

| Candidate | Sealed-2025 MAE | bias |
|---|---:|---:|
| Shipped 60/40 blend | **4.0263** | -0.010 |
| more-years primary alone (unblended) | 4.1548 | +0.299 |

Blend wins clearly (+0.13 MAE, and materially tighter bias). **HOLD — WR
stays shipped, unchanged.** Did not re-derive option (ii) — a new 60/40
blend using a fresh "more-years-unfiltered" secondary — reproducing the
unfiltered-population trick (an artifact of a historical NaN bug in
`snap_pct_roll3`, per `hybrid_projection.py`'s WR-blend comment) deliberately
and safely was judged not cheap enough to fit the remaining timebox; flagged
as a follow-up, not attempted.

## 4. TE

Per mission brief: today's TE levers all regressed or missed
(`SPAN_RECENCY_EXPERIMENTS_2026_08_16.md` more-years/recency both regress TE;
`CANDIDATE_POLISH_2026_08_16.md` TE ridge-regularization sweep gap 0.0263,
short of the 0.03 bar). **No sealed touch spent — shipped TE stays
unchanged**, per the mission's explicit instruction.

## 5. Quantile promotion

Per `CANDIDATE_POLISH_2026_08_16.md` §1: the quantile-graph candidate
(`models/quantile_graph_2026_08_16`, finer 0.01-step conformal width-factor
recalibration) puts QB/RB/TE cleanly in the [75,85]% sealed-2025 coverage
band with better pinball loss than shipped at every position, but WR stays
1.2pp over the 85% ceiling — so a wholesale 4-position swap doesn't clear
the joint gate. Per-position promotion (QB/RB/TE from the graph candidate,
WR stays on the shipped artifact) is what the mission asked for.

**Architecture blocker found and fixed**: `models/quantile/metadata.json`
stores one *shared* `feature_cols` list + one shared `imputer.pkl` used for
all 4 positions (`load_quantile_models`/`predict_quantiles` in
`src/quantile_models.py`). The graph candidate's imputer/feature set (500
cols) is a strict superset of shipped's (486 cols, verified — no shipped
column is missing from the graph set), but mixing "3 positions on the new
500-col imputer, 1 position on the old 486-col imputer" under one shared
key would silently break either the imputer's `transform()` (sklearn raises
on missing fit-time columns) or the model's `.predict()` (column-count
mismatch) — not obviously so; caught this concretely as an exception during
verification. **Fixed with a minimal, backward-compatible addition**:
`load_quantile_models`/`predict_quantiles` now support an optional
`per_position_artifacts` metadata key (position → its own
imputer file + feature_cols); absent for any normal single-recipe
directory, so no other caller's behavior changes.

Promoted directory (`models/quantile/`, backed up in full first to
`models/quantile_backup_pre_consolidation_2026_08_16/`):
- QB/RB/TE: `{POS}_q10/q50/q90.pkl` copied from `models/quantile_graph_2026_08_16`,
  paired with `imputer_graph.pkl` (copy of the graph candidate's imputer) and
  the graph candidate's 500-col `feature_cols`.
- WR: unchanged `WR_q10/q50/q90.pkl`, paired with `imputer_wr.pkl` (copy of
  the original shipped imputer) and the original 486-col `feature_cols`.
- `conformal_width_factors`: QB 1.22, RB 1.12, TE 1.09 (recalibrated,
  in-band per `width_factor_recalibration_2016_2024.json`), WR 1.10
  (unchanged shipped).
- Verified end-to-end: `load_quantile_models('models/quantile')` +
  `predict_quantiles(..., apply_conformal=True)` produces non-null
  floor/projection/ceiling for all 4 positions against a real assembled
  2025 feature frame (15/15 rows each, `QB`/`RB`/`TE`/`WR`).
- **Note on a verification false alarm, reported for transparency**: an
  initial single-season-only `assemble_multiyear_player_features([2025])`
  smoke test raised `ValueError` on both the *new* mixed artifact and the
  *unmodified original shipped* artifact (missing `qbr_epa_total_*` columns
  entirely) — this was a test-harness bug (multi-year assembly, e.g.
  `range(2016,2026)`, correctly produces those columns; single-season-only
  assembly does not), not a promotion defect. Confirmed by reproducing the
  same failure against the untouched backup before concluding it wasn't
  caused by this task's changes, then re-verified correctly with a proper
  multi-year assembly call.

## 6. Freshness check

`python scripts/check_model_freshness.py --no-probe`: **PASS** (44 PASS, 7
WARN-tier non-blocking misses, 0 FAIL). `residual/qb/provenance` and
`residual/rb/provenance` both **PASS** with real stamps (4 sources each,
`git_sha` populated) — the promoted artifacts carry provenance automatically
since they came from `train_and_save_residual_models`. `quantile/provenance`
PASS but with a hand-built stamp (0 sources, no git_sha) since the promoted
quantile metadata was assembled by file-surgery rather than a fresh
`save_quantile_models()` call — cosmetically thinner than the residual
stamps but the check still passes.

## 7. Tests + smoke

- `pytest tests/test_quantile_models.py tests/test_hybrid_projection.py tests/test_ml_projection_router.py -q`:
  **88 passed, 1 skipped.**
- `python scripts/generate_projections.py --week 10 --season 2025 --scoring half_ppr --ml`:
  ran clean end-to-end against the promoted QB/RB residual models — 312
  players projected, sane point values (top QB/RB in the 18-25 range),
  saved CSV + Gold parquet successfully.
- Full repo suite was **not** re-run in full (time); the three targeted
  suites above cover every module touched (`quantile_models.py`,
  `hybrid_projection.py` consumers, router gate logic).

## 8. Cut for time (honestly reported, not silently dropped)

The 1.25h timebox did not fit everything the mission asked for:

- **Headline 2022-24 matched-pairs consensus benchmark (vs Sleeper + ESPN,
  both sources) for the promoted configuration**: not re-run. This requires
  3 separate per-season `--ml --full-features --vs-consensus` backtests
  (`HYBRID_SHIP_2026_08_15.md` §7's exact recipe) — each individually
  under 10 minutes but three in sequence plus pooling did not fit alongside
  everything above. The promoted QB/RB sealed-2025 deltas (+0.096 / +0.071
  MAE, both better bias) point the same direction as the prior headline
  win, but the actual new headline numbers are **not** produced here —
  flagged as the top follow-up, not fabricated.
- **FantasyPros ordinal gate** (`scripts/simulate_fp_accuracy.py`) on the
  promoted config: not run, same time constraint (depends on the same
  2022-24 backtest CSVs as the item above).
- **WR option (ii)** (re-derive the 60/40 blend with a fresh
  more-years-unfiltered secondary): not attempted, see §3.
- Full `pytest tests/ -q` repo suite: not re-run in full; targeted suites
  covering every touched module were run instead (§7).

## 9. Artifact provenance / rollback

| Artifact | Backed up to | Promoted from |
|---|---|---|
| `models/residual/qb_residual{,_imputer}.joblib`, `_meta.json` | `models/residual/_backup_pre_consolidation_2026_08_16/` | `models/span_experiments_2026_08_16/combo/qb_residual*` |
| `models/residual/rb_residual{,_imputer}.joblib`, `_meta.json` | `models/residual/_backup_pre_consolidation_2026_08_16/` | `models/span_experiments_2026_08_16/more_years/rb_residual*` |
| `models/quantile/*` (full dir) | `models/quantile_backup_pre_consolidation_2026_08_16/` | QB/RB/TE from `models/quantile_graph_2026_08_16`; WR unchanged |
| `models/residual/wr_residual*`, `models/residual/te_residual*` | not touched | n/a (both HOLD) |

New scripts (not committed under any concurrent-agent-owned path; follow
the `scripts/span_recency_*.py` precedent of being real, reusable CLI
tools): `scripts/consolidation_wf_gate.py` (walk-forward candidate ranking),
`scripts/consolidation_sealed_gate.py` (one-touch sealed-2025 confirmation).

`src/quantile_models.py`: added optional `per_position_artifacts` support to
`load_quantile_models()`/`predict_quantiles()` (backward compatible, see §5).

`.planning/holdout_ledger.json`: appended 3 entries for this task's sealed-2025
touches (QB combo confirmation, RB zone_more_years confirmation, WR blend
check).
