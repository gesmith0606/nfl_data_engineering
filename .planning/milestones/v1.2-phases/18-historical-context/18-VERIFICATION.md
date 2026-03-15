---
phase: 18-historical-context
verified: 2026-03-15T21:21:41Z
status: passed
score: 16/16 must-haves verified
re_verification: false
---

# Phase 18: Historical Context Verification Report

**Phase Goal:** Build combine/draft historical profiles dimension table in Silver layer
**Verified:** 2026-03-15T21:21:41Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

#### Plan 01 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Speed score computes correctly as (weight * 200) / (forty^4) | VERIFIED | `src/historical_profiles.py:46` — formula `(wt * 200) / (forty ** 4)`; test `TestSpeedScore::test_compute_speed_score` passes |
| 2 | Height strings like '5-11' parse to 71.0 inches; NaN on invalid input | VERIFIED | `parse_height_to_inches` at line 16; tests `test_parse_height_valid` and `test_parse_height_invalid` both pass |
| 3 | Burst score sums vertical + broad_jump | VERIFIED | `src/historical_profiles.py:73` — `result["burst_score"] = result["vertical"] + result["broad_jump"]`; test confirms `36.0 + 120.0 = 156.0` |
| 4 | Position percentiles rank within position group using rank(pct=True) | VERIFIED | `compute_position_percentiles` uses `df.groupby("pos")[col].rank(pct=True)` at line 100; `TestPositionPercentiles::test_percentiles_within_position` passes |
| 5 | Jimmy Johnson chart covers picks 1-262 with linear extrapolation for 225-262 | VERIFIED | 224 hardcoded picks + loop `range(225, 263)` with `max(0.4, round(2.0 - (p - 224) * 0.042, 2))`; `test_completeness` asserts `len(chart) == 262`, `chart[1] == 3000`, `chart[32] == 590`, `chart[262] >= 0.4` |
| 6 | Full outer join on pfr_id preserves all combine and draft rows without row explosion | VERIFIED | `join_combine_draft` separates null-key rows before merge to prevent NaN-NaN cross-product; `test_join_no_explosion` asserts 7 rows from 5+5 with 3 overlapping |
| 7 | Combine dedup resolves duplicate pfr_ids by preferring season==draft_year | VERIFIED | `dedup_combine` sorts by `_match_quality` desc; `test_dedup_keeps_correct_row` confirms correct row retained |
| 8 | Draft value is NaN for undrafted combine attendees | VERIFIED | `test_join_preserves_undrafted` asserts `null_pfr_rows["draft_value"].isna().all()`; Parquet output shows 3,248 rows with NaN draft_value |

#### Plan 02 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 9 | Running silver_historical_transformation.py produces a Parquet file at data/silver/players/historical/ | VERIFIED | `data/silver/players/historical/combine_draft_profiles_20260315_171825.parquet` exists |
| 10 | Output contains combine measurables AND composite scores | VERIFIED | Parquet has columns: `forty`, `bench`, `vertical`, `broad_jump`, `cone`, `shuttle`, `ht`, `wt`, `speed_score`, `bmi`, `burst_score`, `catch_radius`, `height_inches` |
| 11 | Output contains draft capital (pick, round, draft_value from Jimmy Johnson chart) | VERIFIED | Parquet has `pick`, `round`, `draft_value` columns |
| 12 | Output contains position percentile columns for composites | VERIFIED | Parquet has `speed_score_pos_pctl`, `bmi_pos_pctl`, `burst_score_pos_pctl`, `catch_radius_pos_pctl` |
| 13 | Output contains gsis_id for downstream roster linkage | VERIFIED | Parquet has `gsis_id` column |
| 14 | Row count after join equals deduped combine rows + draft-only rows (no explosion) | VERIFIED | Output: 9,892 rows; well within 8,000-12,000 expected range; assertion in `build_combine_draft_profiles` guards against explosion at runtime |
| 15 | Undrafted combine attendees have NaN draft_value; drafted players without combine have NaN measurables | VERIFIED | 3,248 rows with NaN `draft_value`; 1,725 rows with NaN `forty` and non-NaN `draft_value`; `test_join_preserves_drafted_no_combine` confirms NaN `ht` for draft-only players |
| 16 | Match rate and unmatched players logged at INFO/WARNING levels | VERIFIED | `build_combine_draft_profiles` logs match stats at `INFO` (line 334-341) and warnings for combine-only (line 344) and draft-only (line 348) counts |

**Score:** 16/16 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/historical_profiles.py` | Pure compute functions for combine/draft dimension table | VERIFIED | 360 lines; exports all 8 functions with type hints and Google-style docstrings |
| `tests/test_historical_profiles.py` | Unit tests for all compute functions (min 100 lines) | VERIFIED | 261 lines; 15 tests, all passing |
| `src/config.py` | SILVER_PLAYER_S3_KEYS entry for historical_profiles | VERIFIED | Line 129: `"historical_profiles": "players/historical/combine_draft_profiles_{ts}.parquet"` |
| `scripts/silver_historical_transformation.py` | CLI script for combine/draft dimension table generation (min 80 lines) | VERIFIED | 151 lines |
| `data/silver/players/historical/` | Output Parquet file with combine+draft profiles | VERIFIED | `combine_draft_profiles_20260315_171825.parquet` — 9,892 rows, 63 columns |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/historical_profiles.py` | `src/config.py` | import for S3 key template | VERIFIED | `scripts/silver_historical_transformation.py` imports both; `config.py` has `historical_profiles` key used at script line 111 |
| `tests/test_historical_profiles.py` | `src/historical_profiles.py` | import all compute functions | VERIFIED | Lines 12-21 import all 8 functions: `parse_height_to_inches`, `compute_speed_score`, `compute_composite_scores`, `compute_position_percentiles`, `build_jimmy_johnson_chart`, `dedup_combine`, `join_combine_draft`, `build_combine_draft_profiles` |
| `scripts/silver_historical_transformation.py` | `src/historical_profiles.py` | import build_combine_draft_profiles | VERIFIED | Line 27: `from historical_profiles import build_combine_draft_profiles` |
| `scripts/silver_historical_transformation.py` | `data/bronze/combine/` | local Bronze read | VERIFIED | `_read_local_bronze("combine")` at line 92; pattern `data/bronze/combine/season=*/*.parquet` |
| `scripts/silver_historical_transformation.py` | `data/bronze/draft_picks/` | local Bronze read | VERIFIED | `_read_local_bronze("draft_picks")` at line 98; pattern `data/bronze/draft_picks/season=*/*.parquet` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| HIST-01 | 18-01-PLAN.md, 18-02-PLAN.md | Combine measurables (speed score, burst score, catch radius) linked to player IDs via name+draft year join | SATISFIED | `src/historical_profiles.py` computes `speed_score`, `burst_score`, `catch_radius`; linked via `pfr_id` join; Parquet output contains all measurables with `pfr_id` and `gsis_id` linkage |
| HIST-02 | 18-01-PLAN.md, 18-02-PLAN.md | Draft capital (pick value via trade chart) linked to player IDs | SATISFIED | `build_jimmy_johnson_chart()` produces 262-pick chart; `draft_value` column in output; `pick` and `round` columns present; all linked via `pfr_id` |

No orphaned requirements: REQUIREMENTS.md shows both HIST-01 and HIST-02 mapped to Phase 18, both claimed by plans 18-01 and 18-02. Both verified with implementation evidence.

---

### Anti-Patterns Found

No blockers or warnings found.

Scan of `src/historical_profiles.py`, `tests/test_historical_profiles.py`, `scripts/silver_historical_transformation.py`:
- No TODO/FIXME/PLACEHOLDER/HACK comments
- No `return null` or `return {}` stub patterns
- No console.log-only implementations
- No empty handlers
- The NaN-NaN cross-product fix in `join_combine_draft` (separating null keys before outer merge) is substantive and correct, not a workaround

---

### Human Verification Required

None. All critical behaviors verified programmatically:
- Formula correctness verified via unit tests with known numeric values
- Row count bounds verified against actual Parquet output (9,892 rows, within 8,000-12,000)
- Column presence verified against actual Parquet output
- NaN handling verified via unit tests and actual output counts

---

### Test Suite Status

- `tests/test_historical_profiles.py`: 15/15 passing
- Full suite: 289/289 passing, no regressions

---

### Summary

Phase 18 goal fully achieved. The combine/draft historical profiles dimension table is operational in the Silver layer:

- `src/historical_profiles.py` provides 8 pure compute functions covering all required transformations (speed score, BMI, burst score, catch radius, position percentiles, Jimmy Johnson chart, combine dedup, full outer join)
- `scripts/silver_historical_transformation.py` wires Bronze-to-Silver reading and writing for the dimension table
- The Parquet output at `data/silver/players/historical/` has 9,892 player rows, 63 columns, no row explosion, correct NaN semantics for undrafted/no-combine players, and `gsis_id` for downstream roster linkage
- HIST-01 and HIST-02 are fully satisfied with direct implementation evidence
- 15 new unit tests cover all compute functions; 289 total tests pass with no regressions

---

_Verified: 2026-03-15T21:21:41Z_
_Verifier: Claude (gsd-verifier)_
