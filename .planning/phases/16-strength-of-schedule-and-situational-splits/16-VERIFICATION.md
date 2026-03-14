---
phase: 16-strength-of-schedule-and-situational-splits
verified: 2026-03-14T19:10:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 16: Strength of Schedule and Situational Splits Verification Report

**Phase Goal:** Users can see opponent-adjusted team rankings and situational performance splits that account for schedule difficulty and game context
**Verified:** 2026-03-14T19:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running the team CLI produces SOS output with opponent-adjusted EPA and schedule difficulty rankings (1-32) per team per week, using only lagged (week N-1) opponent strength | VERIFIED | `data/silver/teams/sos/season=2024/sos_20260314_145350.parquet` exists; shape (544, 21); 32 teams; `off_sos_rank` and `def_sos_rank` columns present |
| 2 | Week 1 opponent-adjusted EPA equals raw EPA for all teams (no circular dependency) | VERIFIED | Parquet spot-check: `week==1` rows have `off_sos_score` all NaN; `compute_sos_metrics` code path explicitly sets `adj_off_epa = raw_off` and `off_sos_score = NaN` for prior_opps.empty; `TestSOS::test_week1_adj_equals_raw` PASSED |
| 3 | Situational splits at `data/silver/teams/situational/` contain home/away, divisional/non-divisional tags, and game script splits (leading/trailing by 7+) with rolling EPA | VERIFIED | Parquet shape (544, 51); all 12 split columns present (home_off_epa, away_off_epa, home_def_epa, away_def_epa, div_off_epa, nondiv_off_epa, div_def_epa, nondiv_def_epa, leading_off_epa, trailing_off_epa, leading_def_epa, trailing_def_epa); rolling cols confirmed; NaN present for non-applicable situations |
| 4 | Running the same CLI twice on identical input produces identical output (idempotency) | VERIFIED | `TestIdempotency::test_sos_idempotent` and `test_situational_idempotent` both PASSED |

**Score:** 4/4 truths verified (each truth maps to multiple must-have checks — full breakdown below)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/config.py` | TEAM_DIVISIONS dict + SILVER_TEAM_S3_KEYS sos/situational entries | VERIFIED | TEAM_DIVISIONS has 32 teams across 8 divisions (4 each); SILVER_TEAM_S3_KEYS['sos'] and ['situational'] entries present at lines 137-138 |
| `src/team_analytics.py` | `_build_opponent_schedule()` and `compute_sos_metrics()` functions | VERIFIED | Both functions implemented at lines 545-695; substantive implementation (not stubs); imported and called from CLI |
| `src/team_analytics.py` | `compute_situational_splits()` function | VERIFIED | Function implemented at lines 703-846; 12 split columns, game-script threshold logic, divisional lookup, rolling windows; imported and called from CLI |
| `scripts/silver_team_transformation.py` | CLI wiring for SOS + situational compute and save | VERIFIED | Both `compute_sos_metrics` and `compute_situational_splits` imported at lines 30-31; called at lines 168 and 179; saved to disk at lines 202-212 |
| `tests/test_team_analytics.py` | TestConfigSOS, TestSOS, TestSituational, TestIdempotency test classes | VERIFIED | All 4 classes present; 21 tests; all 21 PASSED |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `team_analytics.py:compute_sos_metrics` | `team_analytics.py:compute_team_epa` | calls `compute_team_epa(valid)` internally | WIRED | Line 596: `team_epa = compute_team_epa(valid)` |
| `team_analytics.py:compute_sos_metrics` | `team_analytics.py:apply_team_rolling` | applies rolling windows to SOS stat columns | WIRED | Line 686: `result = apply_team_rolling(result, stat_cols)` |
| `team_analytics.py:compute_sos_metrics` | `team_analytics.py:_build_opponent_schedule` | extracts opponent schedule from PBP | WIRED | Line 599: `schedule = _build_opponent_schedule(valid)` |
| `team_analytics.py:compute_situational_splits` | `src/config.py:TEAM_DIVISIONS` | imports and uses for divisional tagging | WIRED | Line 17: `from config import TEAM_DIVISIONS`; lines 745-751: used to tag `is_divisional` |
| `team_analytics.py:compute_situational_splits` | `team_analytics.py:apply_team_rolling` | applies rolling windows to situational split columns | WIRED | Line 837: `result = apply_team_rolling(result, split_cols)` |
| `scripts/silver_team_transformation.py` | `team_analytics.py:compute_sos_metrics` | import and call in `run_silver_team_transform` | WIRED | Lines 30, 168 |
| `scripts/silver_team_transformation.py` | `team_analytics.py:compute_situational_splits` | import and call in `run_silver_team_transform` | WIRED | Lines 31, 179 |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SOS-01 | 16-01-PLAN.md | Opponent-adjusted EPA using lagged opponent strength (through week N-1 only) | SATISFIED | `compute_sos_metrics` iterates `prior_opps = group[group["week"] < week]`; week 1 test passes; parquet output confirmed |
| SOS-02 | 16-01-PLAN.md | Schedule difficulty rankings (1-32) per team per week | SATISFIED | `off_sos_rank` and `def_sos_rank` computed via `rank(ascending=False, method="min")`; `TestSOS::test_sos_ranking` PASSED |
| SIT-01 | 16-02-PLAN.md | Home/away performance splits with rolling windows | SATISFIED | `home_off_epa`, `away_off_epa`, `home_def_epa`, `away_def_epa` present in parquet; `TestSituational::test_home_away_split` PASSED |
| SIT-02 | 16-02-PLAN.md | Divisional vs non-divisional game tags and performance splits | SATISFIED | `div_off_epa`, `nondiv_off_epa`, `div_def_epa`, `nondiv_def_epa` present; `TestSituational::test_divisional_tagging` PASSED |
| SIT-03 | 16-02-PLAN.md | Game script splits (leading/trailing by 7+) with rolling EPA | SATISFIED | `leading_off_epa`, `trailing_off_epa`, `leading_def_epa`, `trailing_def_epa` present; 7-point threshold enforced; neutral plays excluded; `TestSituational::test_game_script_leading`, `test_game_script_trailing`, `test_neutral_excluded` all PASSED |

No orphaned requirements. REQUIREMENTS.md traceability table marks all 5 IDs as Complete under Phase 16.

---

### Anti-Patterns Found

No anti-patterns detected in modified files:
- `src/config.py`: no TODOs, no stubs
- `src/team_analytics.py`: no TODOs, no placeholder returns, no empty implementations
- `scripts/silver_team_transformation.py`: no TODOs, full save logic wired

---

### Human Verification Required

None. All observable truths were verified programmatically:
- Test suite execution confirms behavioral correctness
- Parquet file inspection confirms actual output schema and values
- Code review confirms no stubs or wiring gaps

---

### Regression Check

Full test suite result: **246 tests PASSED** (0 failures). No regressions introduced by Phase 16 changes. Warnings are pre-existing NumPy deprecation notices from the pandas version in use — not introduced by this phase.

---

### Commit Verification

All 4 task commits documented in summaries exist in git history:
- `bba83a2` — test(16-01): add failing SOS tests and config entries
- `2df11ee` — feat(16-01): implement SOS computation with opponent-adjusted EPA
- `794acb1` — feat(16-02): add situational EPA splits with home/away, divisional, game script
- `c1fcae9` — feat(16-02): wire SOS and situational splits into Silver team CLI

---

## Gaps Summary

No gaps. All 12 must-haves from the two plan frontmatters are verified. All 5 requirement IDs are satisfied. All 21 phase-specific tests pass. Full suite regression clean.

---

_Verified: 2026-03-14T19:10:00Z_
_Verifier: Claude (gsd-verifier)_
