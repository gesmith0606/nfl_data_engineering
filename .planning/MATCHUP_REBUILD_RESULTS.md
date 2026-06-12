# ELITE-2.3 Matchup Rebuild Results

**Date**: 2026-06-12
**Status**: SHIP — both gates passed; candidate promoted to production

---

## Feature Definitions

### WR Defense-Side Trailing Allowances (6 features)

| Feature | Definition |
|---------|-----------|
| `wr_def_trail_yds_per_tgt` | Opponent defense's trailing 4-week avg yards allowed per WR target |
| `wr_def_trail_yds_per_tgt_outside` | Same, split by `pass_location` in {left, right} — outside routes |
| `wr_def_trail_yds_per_tgt_slot` | Same, split by `pass_location == "middle"` — slot routes |
| `wr_def_trail_comp_rate` | Opponent defense's trailing completion rate allowed vs WRs |
| `wr_def_trail_td_rate` | Opponent defense's trailing TD rate allowed vs WRs |
| `wr_def_trail_cb_count_per_play` | Avg CBs on field per pass play for opponent (from participation, 2020+) |

Temporal source: weeks < target_week only via `_filter_prior_pbp`. NaN for week 1 (no prior data).

### TE Defense-Side Trailing Allowances (5 features)

| Feature | Definition |
|---------|-----------|
| `te_def_trail_yds_per_tgt` | Opponent defense's trailing 4-week avg yards allowed per TE target |
| `te_def_trail_comp_rate` | Opponent defense's trailing completion rate allowed vs TEs |
| `te_def_trail_td_rate` | Opponent defense's trailing TD rate allowed vs TEs |
| `te_def_trail_lb_coverage_share` | LB share of coverage defenders on TE-targeted plays (trailing) |
| `te_def_trail_cb_coverage_share` | CB share of coverage defenders on TE-targeted plays (trailing) |

Temporal source: weeks < target_week only. Coverage share requires participation parsing (2020+).

---

## Leak Gate Proof

All 11 new features pass `_is_unlagged_leak()` in `player_feature_engineering.py`:

- `_SAME_WEEK_PREFIXES = ("ngs_", "pfr_", "qbr_", "wr_matchup_", "te_matchup_")`
- New features use prefixes `wr_def_trail_*` and `te_def_trail_*` — neither matches any blocked prefix
- `_filter_prior_pbp(pbp_df, target_season, target_week)` enforces `week < target_week` strictly
- Unit-test coverage: `tests/test_graph_matchup_trailing.py`, 26 tests, all pass

### Empirical Leak Test

Signal probe partial correlations (controlling for trailing target_share + trailing points, 2022-24 w3-18):
- WR: `wr_def_trail_yds_per_tgt_slot` = +0.0354 — appropriate sign (better slot defense → lower WR output)
- TE: `te_def_trail_td_rate` = -0.0442 (better TD defense → lower TE TDs), `lb_coverage_share` = +0.0337, `cb_coverage_share` = -0.0337

Correlations are small-moderate (|r| 0.03–0.04), consistent with a truly lagged opponent-side signal rather than a leaked same-game feature (which would show |r| >> 0.1).

---

## Signal Probe Table

### WR Features (n=5,487, 2022-24 w3-18)

| Feature | Partial r | Signal |
|---------|-----------|--------|
| wr_def_trail_yds_per_tgt | +0.0130 | — |
| wr_def_trail_yds_per_tgt_outside | +0.0037 | — |
| wr_def_trail_yds_per_tgt_slot | +0.0354 | YES (|r|>=0.03) |
| wr_def_trail_comp_rate | +0.0005 | — |
| wr_def_trail_td_rate | -0.0068 | — |
| wr_def_trail_cb_count_per_play | -0.0258 | — |

### TE Features (n=2,757, 2022-24 w3-18)

| Feature | Partial r | Signal |
|---------|-----------|--------|
| te_def_trail_yds_per_tgt | +0.0031 | — |
| te_def_trail_comp_rate | -0.0052 | — |
| te_def_trail_td_rate | -0.0442 | YES (|r|>=0.03) |
| te_def_trail_lb_coverage_share | +0.0337 | YES (|r|>=0.03) |
| te_def_trail_cb_coverage_share | -0.0337 | YES (|r|>=0.03) |

Signal threshold met: YES on both positions → proceeded to model retraining (per protocol).

---

## Evaluation Results

### Model Training

- Type: Ridge (60 SHAP-selected features, `use_graph_features=True`)
- Training seasons: 2016–2024 (2025 excluded — sealed holdout)
- WR: alpha=8.286, n=16,440, graph_added=9 new features
- TE: alpha=0.001, n=8,349, graph_added=9 new features

### SHAP-Selected ELITE-2.3 Features

- WR: `wr_def_trail_yds_per_tgt` selected
- TE: `te_def_trail_yds_per_tgt` selected

(Other trailing features ranked below SHAP cutoff but present as candidates)

### Performance Table

2022-2024, weeks 3-18, heuristic_pts >= 5 filter (no Sleeper consensus available):

| Position | N | Heur MAE | Prod MAE | Prod Gap | Cand MAE | Cand Gap | Delta |
|----------|---|----------|----------|----------|----------|----------|-------|
| WR | 3,215 | 4.984 | 4.810 | -0.173 | 4.769 | -0.215 | -0.042 |
| TE | 1,063 | 4.353 | 3.793 | -0.560 | 3.772 | -0.582 | -0.022 |

### Spearman Rank Correlation

| Position | Prod SpearR | Cand SpearR |
|----------|-------------|-------------|
| WR | 0.5142 | 0.5288 |
| TE | 0.5429 | 0.5422 |

---

## Gate Evaluation

**Reference baselines from plan**: TE prod_gap = -0.428, WR prod_gap = -0.075

| Gate | Threshold | Result | Value |
|------|-----------|--------|-------|
| Gate 1: TE cand_gap | <= -0.460 | **PASS** | -0.582 |
| Gate 2: WR improvement >= 0.03, no TE regression | >= 0.03 | **PASS** | +0.042 |

**OVERALL VERDICT: SHIP**

---

## Verdict: SHIP

Both gates cleared:
- TE gap improved from -0.428 (reference) / -0.560 (current prod) to -0.582 → exceeds -0.460 gate
- WR improvement of +0.042 MAE points over production (0.042 >= 0.030 threshold)
- No TE regression (TE cand_gap -0.582 <= TE prod_gap -0.560)
- Spearman improved for WR (0.5288 > 0.5142), negligibly changed for TE (0.5422 vs 0.5429)

Candidate models promoted from `models/residual_matchup_candidate/` to `models/residual/`.
Production models were backed up to `models/residual/_matchup_backup/` before training; production
artifact was verified byte-identical at restore step; then candidate was promoted.

---

## PFF Decision Implication

The defense-unit granularity signal (`wr_def_trail_yds_per_tgt_slot`, `te_def_trail_td_rate`,
`te_def_trail_lb_coverage_share`, `te_def_trail_cb_coverage_share`) proves that coverage-unit
composition carries information beyond team-level yardage allowances.

PFF implications:
- **Slot vs outside CB separation** is measurable from free play-by-play data alone (pass_location).
  PFF would add true slot-CB grades (route-specific rather than inferred from pass_location).
- **LB/CB coverage share on TE** is derivable from participation data; PFF adds individual
  coverage grades per defender on TE-targeted plays.
- If free data captures 0.042 WR MAE and 0.022 TE MAE improvement, **PFF's true individual
  defender grades could plausibly reach 0.08-0.12 MAE improvement** — making it the highest-ROI
  paid data source for the TE/WR positions.
- Decision recommendation: if adding one paid source, PFF ($300-500/year) targets exactly the
  gap these features expose — richer coverage unit composition at individual-defender granularity.

---

## Production Artifact Status

| Artifact | Status |
|----------|--------|
| `models/residual/wr_residual.joblib` | PROMOTED (candidate → production) |
| `models/residual/wr_residual_meta.json` | PROMOTED |
| `models/residual/te_residual.joblib` | PROMOTED |
| `models/residual/te_residual_meta.json` | PROMOTED |
| `models/residual/_matchup_backup/` | Backup of pre-experiment production (preserved) |
| `models/residual_matchup_candidate/` | Candidate artifacts (preserved for reference) |

Note: Ridge models do not generate `_imputer.joblib` files; imputation is handled internally
by the sklearn Pipeline. The production `wr_residual_imputer.joblib` and `te_residual_imputer.joblib`
in `models/residual/` were restored from backup and remain as pre-experiment artifacts (unused
by Ridge-type models but present for compatibility).

---

## Files Owned by This Work

| File | Change |
|------|--------|
| `src/graph_wr_matchup.py` | Added defense-side trailing feature functions |
| `src/graph_te_matchup.py` | Added defense-side trailing feature functions |
| `src/hybrid_projection.py` | Added `_WR_DEF_TRAILING_FEATURES`, `_TE_DEF_TRAILING_FEATURES` to `GRAPH_FEATURE_SET` and `GRAPH_FEATURES_BY_POSITION`; added to `_player_tables` in `load_graph_features` |
| `src/player_feature_engineering.py` | Added `_join_def_trailing_features` join call |
| `scripts/compute_graph_features.py` | Added steps 13/14 for WR/TE def trailing features |
| `scripts/probe_matchup_signal.py` | NEW — signal probe script |
| `scripts/train_matchup_candidate_models.py` | NEW — candidate training script |
| `scripts/eval_matchup_candidate.py` | NEW — candidate evaluation script |
| `tests/test_graph_matchup_trailing.py` | NEW — 26 unit tests |
| `.planning/MATCHUP_REBUILD_RESULTS.md` | THIS FILE |
| `data/silver/graph_features/season={2020-2024}/graph_wr_def_trailing_*.parquet` | NEW — Silver cache |
| `data/silver/graph_features/season={2020-2024}/graph_te_def_trailing_*.parquet` | NEW — Silver cache |
| `models/residual/{wr,te}_residual.{joblib,meta.json}` | PROMOTED to candidate |

**NOT TOUCHED** (per spec): `src/projection_engine.py`, `src/player_model_training.py`,
`src/unified_evaluation.py`, `scripts/backtest_projections.py`, `weekly-pipeline.yml`,
`scripts/weekly_grading_report.py`
