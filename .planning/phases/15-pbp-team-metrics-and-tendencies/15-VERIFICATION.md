---
phase: 15-pbp-team-metrics-and-tendencies
verified: 2026-03-13T00:00:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 15: PBP Team Metrics and Tendencies — Verification Report

**Phase Goal:** Users can generate PBP-derived team performance and tendency metrics with rolling windows for any season 2016-2025 via a new Silver team CLI
**Verified:** 2026-03-13
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Rolling windows in player_analytics.py group by (player_id, season) not player_id alone | VERIFIED | Line 213: `df.groupby(['player_id', 'season'])[col]` |
| 2 | New Silver team output paths are registered in config.py and follow existing naming convention | VERIFIED | Lines 122-125 of config.py: SILVER_TEAM_S3_KEYS with pbp_metrics and tendencies entries |
| 3 | team_analytics.py exists with shared utility functions for play filtering and rolling window application | VERIFIED | 535-line module; _filter_valid_plays (L20), apply_team_rolling (L65) both present and substantive |
| 4 | Team EPA per play is computed for offense and defense with pass/rush splits | VERIFIED | compute_team_epa (L134) returns off_epa_per_play, off_pass_epa, off_rush_epa, def_epa_per_play |
| 5 | Team success rate is computed for offense and defense | VERIFIED | compute_team_success_rate (L190) returns off_success_rate, def_success_rate |
| 6 | Team CPOE is aggregated as mean of non-null play-level CPOE values | VERIFIED | compute_team_cpoe (L221) filters NaN cpoe before groupby mean |
| 7 | Red zone TD rate uses drive-based denominator (unique drives entering red zone) | VERIFIED | compute_red_zone_metrics (L247) uses nunique(drive) as denominator |
| 8 | All PBP metrics have roll3, roll6, and STD rolling columns via apply_team_rolling | VERIFIED | compute_pbp_metrics (L301) calls apply_team_rolling at L339; TestPBPRolling confirms rolling cols |
| 9 | Pace (plays per game) is computed per team-week with rolling windows | VERIFIED | compute_pace (L356) counts pass+run plays; compute_tendency_metrics calls apply_team_rolling (L526) |
| 10 | PROE uses xpass column: actual_pass_rate - mean(xpass) per game | VERIFIED | compute_proe (L375): pass_plays/total_plays - mean_xpass; NaN excluded by pandas mean() |
| 11 | 4th down aggressiveness has go rate and success rate columns with rolling windows | VERIFIED | compute_fourth_down_aggressiveness (L402); go_rate and success_rate both present; receives raw PBP |
| 12 | CLI script produces Parquet output at correct paths with timestamped filenames | VERIFIED | silver_team_transformation.py L163-169 calls _save_local_silver for both tables; --help confirmed |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact | Min Lines | Actual Lines | Status | Key Evidence |
|----------|-----------|-------------|--------|--------------|
| `src/team_analytics.py` | 250 | 535 | VERIFIED | All 12 required functions defined (L20-L526) |
| `src/config.py` | — | 285 | VERIFIED | SILVER_TEAM_S3_KEYS at L122 with pbp_metrics + tendencies |
| `src/player_analytics.py` | — | 417 | VERIFIED | groupby(['player_id', 'season']) at L213, L221 |
| `tests/test_player_analytics.py` | — | 262 | VERIFIED | TestRollingSeasonFix at L156; 3 regression tests passing |
| `tests/test_team_analytics.py` | 200 | 737 | VERIFIED | TestEPA L105, TestSuccessRate L149, TestCPOE L177, TestRedZone L199, TestPace L505, TestPROE L550, TestFourthDown L597, TestEarlyDownRunRate L655 |
| `scripts/silver_team_transformation.py` | 80 | 225 | VERIFIED | Imports compute_pbp_metrics, compute_tendency_metrics; to_parquet at L69, L163-169 |
| `docs/NFL_DATA_DICTIONARY.md` | — | 1273 | VERIFIED | "pbp_metrics" sections at L1066, L1106; tendencies schema at L1117-1121 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| src/team_analytics.py | src/config.py | import SILVER_TEAM_S3_KEYS | PARTIAL | team_analytics.py does NOT import SILVER_TEAM_S3_KEYS — the CLI script uses the paths directly. The config constant exists; the silver_team_transformation.py script does not import it but constructs paths inline. This does not break functionality — the CLI writes files correctly. |
| src/team_analytics.py:compute_pbp_metrics | src/team_analytics.py:apply_team_rolling | function call after raw metric computation | VERIFIED | L339: `result = apply_team_rolling(merged, stat_cols)` |
| src/team_analytics.py:compute_pbp_metrics | src/team_analytics.py:_filter_valid_plays | function call at start of pipeline | VERIFIED | L316: `valid = _filter_valid_plays(pbp_df)` |
| scripts/silver_team_transformation.py | src/team_analytics.py | from team_analytics import | VERIFIED | L27: `from team_analytics import compute_pbp_metrics, compute_tendency_metrics` |
| scripts/silver_team_transformation.py | data/silver/teams/ | to_parquet with timestamped filename | VERIFIED | L69, L163-169: _save_local_silver writes timestamped parquet under data/silver/ |
| src/team_analytics.py:compute_tendency_metrics | src/team_analytics.py:apply_team_rolling | function call after raw metric computation | VERIFIED | L526: `result = apply_team_rolling(merged, stat_cols)` |

**Note on PARTIAL link:** The plan's key_links specified `team_analytics.py` importing `SILVER_TEAM_S3_KEYS` from `config.py`. In practice, `team_analytics.py` is a pure analytics module with no path concerns — the CLI script handles path construction directly. This is a better design than the plan anticipated. The config key exists, the paths are correct, and the CLI writes to the right locations. No functional gap.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PBP-01 | 15-02 | Team EPA per play (offense + defense, pass/rush splits) with rolling windows | SATISFIED | compute_team_epa returns off_epa_per_play, off_pass_epa, off_rush_epa, def_epa_per_play; rolling applied via compute_pbp_metrics |
| PBP-02 | 15-02 | Team success rate (offense + defense) with rolling windows | SATISFIED | compute_team_success_rate returns off_success_rate, def_success_rate; rolling applied |
| PBP-03 | 15-02 | Team CPOE aggregate with rolling windows | SATISFIED | compute_team_cpoe; NaN-excluded mean; TestCPOE::test_cpoe_nan_excluded passes |
| PBP-04 | 15-02 | Red zone efficiency (offense + defense) with rolling windows | SATISFIED | compute_red_zone_metrics; drive-based TD rate; TestRedZone and TestRedZoneZeroTrips pass |
| PBP-05 | 15-01 | Rolling window groupby must use (entity, season) not entity alone | SATISFIED | player_analytics.py L213: groupby(['player_id', 'season']); TestRollingSeasonFix passes |
| TEND-01 | 15-03 | Pace (plays per game) per team with rolling windows | SATISFIED | compute_pace; TestPace::test_pace_columns confirms rolling cols |
| TEND-02 | 15-03 | Pass Rate Over Expected (PROE) per team with rolling windows | SATISFIED | compute_proe; xpass NaN excluded from mean; TestPROE::test_proe_xpass_nan_excluded_from_mean passes |
| TEND-03 | 15-03 | 4th down aggressiveness index (go rate, success rate) with rolling windows | SATISFIED | compute_fourth_down_aggressiveness; TestFourthDown::test_zero_attempts_gives_nan confirms NaN edge case |
| TEND-04 | 15-03 | Early-down run rate with rolling windows | SATISFIED | compute_early_down_run_rate; TestEarlyDownRunRate::test_early_down_uses_down_le_2 passes |
| INFRA-01 | 15-01 | New Silver tables registered in config.py | SATISFIED | SILVER_TEAM_S3_KEYS at config.py L122 with pbp_metrics and tendencies |
| INFRA-02 | 15-03 | Silver team transformation CLI script | SATISFIED | scripts/silver_team_transformation.py; --help confirmed; mirrors player transformation pattern |
| INFRA-03 | 15-03 | Silver output follows season/week partition with timestamped filenames | SATISFIED | _save_local_silver constructs `teams/pbp_metrics/season={season}/pbp_metrics_{ts}.parquet`; to_parquet called |

**Orphaned requirements:** None. All 12 requirement IDs declared across the three plans are accounted for and verified.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TODO/FIXME/placeholder comments found | — | — |
| — | — | No stub implementations (return None/empty) found | — | — |
| — | — | No empty handlers found | — | — |

No anti-patterns detected in any phase 15 artifacts.

---

### Human Verification Required

No items require human verification. All behavioral contracts are verifiable programmatically through the test suite (225 passing tests confirmed).

---

### Test Suite Results

| Suite | Tests | Result |
|-------|-------|--------|
| tests/test_team_analytics.py | 36 | 36 PASSED |
| tests/test_player_analytics.py | 12 | 12 PASSED |
| Full suite (tests/) | 225 | 225 PASSED |

---

### Gaps Summary

No gaps. All 12 must-have truths are verified, all artifacts exist and are substantive, all key links are wired, all 12 requirement IDs are satisfied, and the full test suite passes with 225 tests.

The one PARTIAL key link (team_analytics.py not importing SILVER_TEAM_S3_KEYS from config.py) reflects a better design choice than the plan anticipated — the analytics module correctly has no path dependencies. The CLI script constructs paths correctly and the config constant exists for health-check and download_latest_parquet() consumers as required by INFRA-01.

---

_Verified: 2026-03-13_
_Verifier: Claude (gsd-verifier)_
