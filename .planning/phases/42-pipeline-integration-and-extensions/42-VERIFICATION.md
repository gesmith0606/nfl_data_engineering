---
phase: 42-pipeline-integration-and-extensions
verified: 2026-03-31T01:30:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 42: Pipeline Integration and Extensions Verification Report

**Phase Goal:** Wire QB ML model + RB/WR/TE heuristic fallback into the projection pipeline, CLI, and draft tool with confidence intervals and preseason draft-capital weighting
**Verified:** 2026-03-31
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `generate_ml_projections()` routes QB to ML and RB/WR/TE to heuristic based on ship_gate_report.json | VERIFIED | `_load_ship_gate()` reads JSON; QB inferred SHIP when model files exist; routing confirmed in `generate_ml_projections()` lines 357-591 |
| 2 | Rookies with all-NaN rolling features and players with <3 games fall back to heuristic silently | VERIFIED | `_is_fallback_player()` defined at line 100; both conditions checked; `fallback_mask` applied in ML path |
| 3 | Per-team projected fantasy points exceeding 110% of implied total trigger a log warning | VERIFIED | `check_team_total_coherence()` at line 265; warn-only, no projection adjustment |
| 4 | QB projections include MAPIE-derived floor/ceiling at 80% prediction interval when mapie is installed | VERIFIED | `compute_mapie_intervals()` at line 142; `HAS_MAPIE` guard; graceful degradation to `add_floor_ceiling()` when unavailable |
| 5 | Output DataFrame has identical columns to heuristic output plus `projection_source` column | VERIFIED | `projection_source` tagged in all code paths (lines 357, 383, 558, 573, 591); test `test_output_columns_match_heuristic_plus_source` passes |
| 6 | Running `generate_projections.py` with `--ml` flag produces ML-based projections for QB and heuristic for RB/WR/TE | VERIFIED | `--ml` flag at line 89 of CLI; `from ml_projection_router import generate_ml_projections` at line 194; confirmed in `--help` output |
| 7 | Running `generate_projections.py` without `--ml` produces identical output to current behavior | VERIFIED | `--ml` is opt-in; default code path unchanged; backward-compatible per D-04 |
| 8 | Preseason mode with `--ml` is a no-op (all heuristic) and does not error | VERIFIED | Informational message at line 113: `"Note: --ml is a no-op in preseason mode (all positions use heuristic)"` |
| 9 | Rookies in preseason mode receive a draft capital boost based on draft pick position | VERIFIED | `draft_capital_boost()` at line 824 of projection_engine.py; applied in `generate_preseason_projections()` at line 935; pick 1 → 1.20 multiplier, linear decay to 1.0 at pick 64+ |

**Score:** 9/9 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/ml_projection_router.py` | ML/heuristic routing, MAPIE intervals, team constraints | VERIFIED | 623 lines; substantive; all 5 key functions present |
| `tests/test_ml_projection_router.py` | Unit tests for routing, fallback, coherence, MAPIE | VERIFIED | 429 lines (> 100 min); 17 passed, 1 skipped (MAPIE — expected when mapie not installed) |
| `scripts/generate_projections.py` | `--ml` flag routing to `ml_projection_router` | VERIFIED | `--ml` argument added; conditional import and call of `generate_ml_projections` |
| `src/projection_engine.py` | `draft_capital_boost` function; `historical_df` param | VERIFIED | `draft_capital_boost()` at line 824; `historical_df` optional param at line 847; applied at line 935 |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/ml_projection_router.py` | `models/player/ship_gate_report.json` | `_load_ship_gate` reads JSON at runtime | VERIFIED | Pattern `ship_gate_report.json` at line 67 |
| `src/ml_projection_router.py` | `src/player_model_training.py` | `load_player_model`, `predict_player_stats` | VERIFIED | `from player_model_training import` confirmed in imports |
| `src/ml_projection_router.py` | `src/projection_engine.py` | `generate_weekly_projections` for heuristic fallback | VERIFIED | `from projection_engine import` confirmed in imports |
| `src/ml_projection_router.py` | `src/scoring_calculator.py` | `calculate_fantasy_points_df` for ML stat→points | VERIFIED | `from scoring_calculator import` confirmed in imports |
| `scripts/generate_projections.py` | `src/ml_projection_router.py` | Conditional import when `--ml` flag set | VERIFIED | `from ml_projection_router import generate_ml_projections` at line 194 |
| `src/projection_engine.py` | `historical_df` (Silver historical) | `draft_capital_boost` called inside `generate_preseason_projections` | VERIFIED | Join on `gsis_id` at line 920; multiplier applied at line 935 |
| `scripts/draft_assistant.py` | ML projection output | `--projections-file` CSV loading (no code changes) | VERIFIED | `--projections-file` argument at line 773; CSV loaded at line 838; output schema unchanged |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PIPE-02 | 42-01 | Team-total constraint ensuring player share projections sum to ~100% per team | SATISFIED | `check_team_total_coherence()` warns when team totals exceed 110% of implied total; called inside `generate_ml_projections()` |
| PIPE-03 | 42-01, 42-02 | Weekly pipeline wiring into `generate_projections.py` and `draft_assistant.py` | SATISFIED | `--ml` flag wires router into CLI; draft tool unchanged and compatible via `--projections-file` |
| PIPE-04 | 42-01 | Heuristic fallback preserved for rookies, thin-data players, and positions where ML doesn't beat baseline | SATISFIED | `_is_fallback_player()` handles all-NaN rolling + <3 games; RB/WR/TE routed to heuristic via ship gate |
| EXTD-01 | 42-02 | Preseason projection mode using prior-season aggregates + draft capital when no current-season data exists | SATISFIED | `draft_capital_boost()` in `projection_engine.py`; `generate_preseason_projections()` accepts `historical_df` and applies boost for rookies |
| EXTD-02 | 42-01 | ML-derived confidence intervals (MAPIE) for player-specific floor/ceiling bands | SATISFIED | `compute_mapie_intervals()` exported; `HAS_MAPIE` guard; graceful degradation to heuristic `add_floor_ceiling()` when mapie not installed |

No orphaned requirements. All 5 phase requirements (PIPE-02, PIPE-03, PIPE-04, EXTD-01, EXTD-02) are claimed by plans and verified in codebase.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/ml_projection_router.py` | 167, 178, 489, 578 | `return None` | INFO | All are intentional graceful-degradation paths (MAPIE unavailable, no data for position). None flow to user-visible output without a caller-side guard. Not stubs. |

No blocker or warning-level anti-patterns found. No TODO/FIXME/placeholder comments in any modified file.

---

## Test Results

- **Router test suite:** 17 passed, 1 skipped (`test_returns_intervals_when_mapie_available` skipped because mapie is not installed in venv — expected and by design per MAPIE optional-dependency contract)
- **Full suite:** 655 passed, 1 skipped, 0 failures (up from 571 baseline; no regressions)
- **Commits verified:** `473896b` (Plan 01), `0a15fb6`, `3be3856` (Plan 02) — all present in git log

---

## Human Verification Required

### 1. End-to-end weekly projection with `--ml` flag

**Test:** Run `python scripts/generate_projections.py --week 1 --season 2025 --scoring half_ppr --ml` with valid Silver data present.
**Expected:** QB rows show `projection_source=ml` with `projected_floor`/`projected_ceiling` columns; RB/WR/TE rows show `projection_source=heuristic`; no errors or stack traces.
**Why human:** Requires real Silver parquet data and QB model files at `models/player/qb/` to exercise the full runtime path; the test suite mocks all I/O.

### 2. Preseason draft capital boost magnitude

**Test:** Run `python scripts/generate_projections.py --preseason --season 2026 --scoring half_ppr` with Silver historical data containing a pick-1 QB rookie.
**Expected:** That QB's `projected_season_points` is approximately 20% higher than without the draft capital boost; undrafted rookies show no boost.
**Why human:** Integration of historical parquet loading with actual draft pick data; unit tests cover the math but not the Silver data join in the CLI.

---

## Gaps Summary

No gaps. All 9 observable truths verified, all 4 artifacts substantive and wired, all 7 key links confirmed, all 5 requirements satisfied. The 1 skipped test is expected behavior (MAPIE not installed), not a deficiency. The phase goal is fully achieved.

---

_Verified: 2026-03-31_
_Verifier: Claude (gsd-verifier)_
