---
phase: 21-pbp-derived-team-metrics
verified: 2026-03-16T22:42:24Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 21: PBP-Derived Team Metrics Verification Report

**Phase Goal:** Eleven new team-level metrics are computed from PBP data with rolling windows and written as Silver parquet — penalties, opponent-drawn penalties, turnover luck, red zone trip volume, special teams FG/punt/return, 3rd down rates, explosive plays, drive efficiency, sack rates, and time of possession
**Verified:** 2026-03-16T22:42:24Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                    | Status     | Evidence                                                                    |
|----|------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------|
| 1  | Penalty metrics split offensive vs defensive using penalty_team == posteam/defteam       | VERIFIED   | Lines 1323-1333 in team_analytics.py; TestComputePenaltyMetrics passes      |
| 2  | Opponent-drawn penalties are the inverse perspective of team penalty metrics              | VERIFIED   | Lines 1388-1400; TestComputeOppDrawnPenalties passes                        |
| 3  | Turnover luck uses expanding window with shift(1) lag, NOT rolling windows               | VERIFIED   | Line 1518 `.transform(lambda s: s.shift(1).expanding().mean())`; TestComputeTurnoverLuck::test_uses_expanding_not_rolling passes |
| 4  | Red zone trips use drive-level nunique counts                                             | VERIFIED   | Line 674 `drive.nunique()` in compute_red_zone_trips; TestComputeRedZoneTrips::test_trips_count_drives_not_plays passes |
| 5  | 3rd down rates use third_down_converted / (converted + failed)                           | VERIFIED   | Lines 1575, 1594, 1604; TestComputeThirdDownRates passes                    |
| 6  | Explosive plays use 20+ yards for pass and 10+ yards for rush                            | VERIFIED   | Lines 1640-1641 `yards_gained >= 20` and `yards_gained >= 10`; TestComputeExplosivePlays passes |
| 7  | Sack rates use sacks / dropbacks for both offensive and defensive sides                   | VERIFIED   | compute_sack_rates function at line 1693; TestComputeSackRates passes       |
| 8  | FG accuracy is bucketed into <30, 30-39, 40-49, 50+ using kick_distance                 | VERIFIED   | _fg_bucket at line 192; TestComputeFGAccuracy::test_fg_accuracy_buckets passes |
| 9  | Touchbacks detected via proxy (KO: return_yards==0 + no returner; punt: punt_in_endzone==1) | VERIFIED | Lines 308-341 in compute_return_metrics; TestComputeReturnMetrics passes    |
| 10 | Drive efficiency uses drive-level grouping with 3-and-out as <=3 plays + no 1st/TD      | VERIFIED   | Lines 389-460 in compute_drive_efficiency; TestComputeDriveEfficiency passes |
| 11 | compute_pbp_derived_metrics orchestrator calls all 11 functions and merges on (team, season, week) | VERIFIED | Lines 1749-1810; calls all 11 functions; TestPBPDerivedMetricsOrchestrator::test_compute_pbp_derived_metrics passes |
| 12 | Turnover luck columns excluded from apply_team_rolling; rolling applied to all other metrics | VERIFIED | Lines 1797-1801; turnover_cols set filters before apply_team_rolling; test_pbp_derived_rolling asserts fumbles_lost_roll3 NOT in columns |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact                              | Expected                                           | Status     | Details                                                              |
|---------------------------------------|----------------------------------------------------|------------|----------------------------------------------------------------------|
| `src/team_analytics.py`               | 11 compute functions + orchestrator + helpers      | VERIFIED   | All 15 functions present and importable; 501+lines added across sections |
| `tests/test_team_analytics.py`        | Tests for all 11 compute functions + orchestrator  | VERIFIED   | 15 Phase 21 test classes, 80 total tests pass                        |
| `src/config.py`                       | pbp_derived key in SILVER_TEAM_S3_KEYS             | VERIFIED   | `"pbp_derived": "teams/pbp_derived/season={season}/pbp_derived_{ts}.parquet"` at config line |
| `scripts/silver_team_transformation.py` | imports and calls compute_pbp_derived_metrics     | VERIFIED   | Lines 33 (import), 192 (call), 228-232 (save)                       |
| `scripts/check_pipeline_health.py`    | pbp_derived in REQUIRED_SILVER_PREFIXES            | VERIFIED   | Line 61: `"pbp_derived": "teams/pbp_derived/season={season}/"`      |

---

### Key Link Verification

| From                          | To                                    | Via                                          | Status   | Details                                                         |
|-------------------------------|---------------------------------------|----------------------------------------------|----------|-----------------------------------------------------------------|
| `src/team_analytics.py`       | `tests/test_team_analytics.py`        | import each compute function                 | WIRED    | Lines 35-45 import all 11 functions; 15 test classes exercise them |
| `src/team_analytics.py`       | `scripts/silver_team_transformation.py` | import compute_pbp_derived_metrics          | WIRED    | Line 33: `compute_pbp_derived_metrics` in import list           |
| `src/config.py`               | `scripts/silver_team_transformation.py` | SILVER_TEAM_S3_KEYS["pbp_derived"]          | WIRED    | Line 229: `SILVER_TEAM_S3_KEYS["pbp_derived"].format(...)`      |
| `scripts/check_pipeline_health.py` | `teams/pbp_derived/`             | REQUIRED_SILVER_PREFIXES freshness check     | WIRED    | Line 61: entry maps to `teams/pbp_derived/season={season}/`     |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                                  | Status    | Evidence                                                               |
|-------------|-------------|------------------------------------------------------------------------------|-----------|------------------------------------------------------------------------|
| PBP-01      | 21-01       | Team penalty rates with off/def split and rolling windows                     | SATISFIED | compute_penalty_metrics; TestComputePenaltyMetrics passes              |
| PBP-02      | 21-01       | Opponent-drawn penalty rates with rolling windows                             | SATISFIED | compute_opp_drawn_penalties; TestComputeOppDrawnPenalties passes       |
| PBP-03      | 21-01       | Turnover luck metrics with regression-to-mean indicator                       | SATISFIED | compute_turnover_luck; is_turnover_lucky flag; expanding window        |
| PBP-04      | 21-01       | Red zone trip volume (drive-level counts per team/game)                       | SATISFIED | compute_red_zone_trips; drive nunique; TestComputeRedZoneTrips passes  |
| PBP-05      | 21-02       | Special teams FG accuracy by distance bucket with rolling windows             | SATISFIED | compute_fg_accuracy; _fg_bucket; TestComputeFGAccuracy passes          |
| PBP-06      | 21-02       | Special teams punt/kick return averages and touchback rates                   | SATISFIED | compute_return_metrics; proxy touchback detection; test passes         |
| PBP-07      | 21-01       | 3rd down conversion rates (off/def) with rolling windows                     | SATISFIED | compute_third_down_rates; formula verified; test passes                |
| PBP-08      | 21-01       | Explosive play rates (20+ yd pass, 10+ yd rush) off/def with rolling windows | SATISFIED | compute_explosive_plays; thresholds verified; test passes              |
| PBP-09      | 21-02       | Drive efficiency (3-and-out rate, avg drive length, drives/game)              | SATISFIED | compute_drive_efficiency; drive-level groupby; test passes             |
| PBP-10      | 21-01       | Team sack rates (OL + defensive pass rush) with rolling windows               | SATISFIED | compute_sack_rates; off_sack_rate and def_sack_rate computed           |
| PBP-11      | 21-02       | Time of possession per team with rolling windows                              | SATISFIED | compute_top; _parse_top_seconds; M:SS string parsing verified          |
| INTEG-02    | 21-03       | All new features use rolling windows (3-game, 6-game, STD) with shift(1) lag | SATISFIED | apply_team_rolling applied in orchestrator; turnover cols excluded correctly; test_pbp_derived_rolling verifies shift(1) produces NaN for week 1 |

All 12 requirements satisfied. No orphaned requirements found.

---

### Anti-Patterns Found

| File                    | Lines    | Pattern                                     | Severity | Impact                                                                        |
|-------------------------|----------|---------------------------------------------|----------|-------------------------------------------------------------------------------|
| `src/team_analytics.py` | 136, 1248 | Duplicate `_filter_st_plays` definition    | Warning  | Python uses the last definition (line 1248). Both are functionally identical. No behavioral impact. Plan 02 added it as an auto-fix before Plan 01 ran; Plan 01 then added its own copy. Tests confirm correct behavior throughout. |

No blocker anti-patterns. The duplicate helper is a code smell but does not affect correctness or test outcomes.

---

### Human Verification Required

None. All truths are verifiable programmatically through function imports, source pattern checks, and the 325-test suite (all passing).

---

### Gaps Summary

None. All 12 must-have truths are verified, all 5 artifacts exist and are substantive, all 4 key links are wired, and all 12 requirements are satisfied. The full test suite passes with 325 tests (including 80 in test_team_analytics.py) and zero regressions.

The one note for awareness: `_filter_st_plays` appears twice in `src/team_analytics.py` (lines 136 and 1248) due to out-of-order plan execution. Python uses the last definition. This does not affect correctness and can be cleaned up in a future tech-debt pass.

---

_Verified: 2026-03-16T22:42:24Z_
_Verifier: Claude (gsd-verifier)_
