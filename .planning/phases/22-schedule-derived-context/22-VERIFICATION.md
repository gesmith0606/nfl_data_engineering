---
phase: 22-schedule-derived-context
verified: 2026-03-17T23:10:00Z
status: passed
score: 11/11 must-haves verified
re_verification: false
---

# Phase 22: Schedule-Derived Context Verification Report

**Phase Goal:** Build schedule-derived game context features (weather, rest/travel, coaching) as a Silver layer module.
**Verified:** 2026-03-17T23:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Schedules home/away rows are unpivoted into per-team rows (2x row count) | VERIFIED | 2024: 285 games → 570 rows (32 teams); `_unpivot_schedules` tested with `test_unpivot_doubles_rows` |
| 2 | Dome games have temp=72 and wind=0; outdoor NaN temp/wind produce False flags | VERIFIED | `compute_weather_features` sets `temperature=72.0`, `wind_speed=0.0` for dome; NaN → `fillna(False)`. `test_weather_dome` and `test_weather_nan_flags` pass |
| 3 | Rest days are capped at 14; is_short_rest triggers at <=6; is_post_bye at >=13 | VERIFIED | `clip(upper=14)`, threshold comparisons in `compute_rest_features`. `test_rest_capping`, `test_rest_short`, `test_rest_bye` all pass |
| 4 | Travel distance uses haversine; home games = 0 miles; neutral sites compute for both teams | VERIFIED | `_haversine_miles` with R=3958.8; `is_home and location != "Neutral"` → 0.0; neutral tested in `test_travel_neutral`. 2024 Silver: 0 NaN travel miles |
| 5 | Timezone differential is DST-aware using pytz and actual game date | VERIFIED | `_timezone_diff_hours` uses `pytz.timezone().localize()` at `hour=12`. `test_timezone_diff_dst` (3h NY vs LA) and `test_timezone_diff_arizona` pass |
| 6 | Coaching tenure accumulates across seasons for same coach; resets on change | VERIFIED | `compute_coaching_features` increments `tenure` per week, resets to 1 on coach change. `prior_season_coaches` passed from `run_game_context_transform` across loop iterations |
| 7 | All output columns joinable on [team, season, week] | VERIFIED | 2024 Silver: 0 duplicate `[team, season, week]` rows. E2E test asserts no duplicates |
| 8 | Running silver_game_context_transformation.py produces Silver parquet files for each season | VERIFIED | `data/silver/teams/game_context/season=YYYY/` exists for all 10 seasons 2016-2025 |
| 9 | Output parquet contains all weather, rest, travel, coaching columns | VERIFIED | 2024 Silver: 22 columns including `is_dome`, `temperature`, `wind_speed`, `is_high_wind`, `is_cold`, `surface`, `rest_days`, `opponent_rest`, `is_short_rest`, `is_post_bye`, `rest_advantage`, `travel_miles`, `tz_diff`, `head_coach`, `coaching_change`, `coaching_tenure` |
| 10 | Pipeline health check validates game_context Silver paths | VERIFIED | `scripts/check_pipeline_health.py` line 62: `"game_context": "teams/game_context/season={season}/"` in `REQUIRED_SILVER_PREFIXES` |
| 11 | Script processes 2016-2025 seasons with prior-season coaching context | VERIFIED | `run_game_context_transform` sorts seasons ascending, passes `prior_season_df` across loop iterations. 2024 Silver shows 7 teams with `coaching_change=True` |

**Score:** 11/11 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/config.py` | STADIUM_ID_COORDS mapping dict + game_context S3 key | VERIFIED | 42 entries in `STADIUM_ID_COORDS` (verified against Bronze data); `SILVER_TEAM_S3_KEYS["game_context"]` = `"teams/game_context/season={season}/game_context_{ts}.parquet"` |
| `src/game_context.py` | Game context module with all 8 functions | VERIFIED | 341 lines; all 6 public + 2 private functions present and substantive. Imports cleanly from both `src/` and script context |
| `tests/test_game_context.py` | Unit tests, min 200 lines | VERIFIED | 475 lines; 22 tests — all pass in 0.78s |
| `scripts/silver_game_context_transformation.py` | CLI script for Silver transformation | VERIFIED | 220 lines; `_read_local_schedules`, `run_game_context_transform`, `main` all present and substantive |
| `data/silver/teams/game_context/season=2024/` | Silver parquet output for 2024 | VERIFIED | 570 rows, 22 columns, 32 teams, 0 NaN travel miles |
| `data/silver/teams/game_context/season=2016/` | Silver parquet output for 2016 | VERIFIED | 534 rows, 22 columns (33 NaN travel miles expected — legacy OAK/SD team codes pre-relocation) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `src/game_context.py` | `src/config.py` | `from config import STADIUM_ID_COORDS, STADIUM_COORDINATES` | WIRED | Line 18 of game_context.py; both dicts used in `compute_travel_features` |
| `src/game_context.py` | `pytz` | `pytz.timezone().localize()` for DST-aware offsets | WIRED | `import pytz` at line 16; used in `_timezone_diff_hours` |
| `tests/test_game_context.py` | `src/game_context.py` | `from game_context import ...` all compute functions | WIRED | All 8 functions imported in test file; 22/22 tests pass |
| `scripts/silver_game_context_transformation.py` | `src/game_context.py` | `from game_context import compute_game_context` | WIRED | Line 28; called in `run_game_context_transform` with `prior_season_df` |
| `scripts/silver_game_context_transformation.py` | `src/config.py` | `from config import SILVER_TEAM_S3_KEYS` | WIRED | Line 27; used to build `gc_key` in transform loop |
| `scripts/check_pipeline_health.py` | `data/silver/teams/game_context/` | Silver path freshness check | WIRED | Line 62 adds `game_context` to `REQUIRED_SILVER_PREFIXES` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SCHED-01 | 22-01, 22-02 | Weather features (temperature, wind speed, roof type, surface type) from schedules Bronze as Silver columns | SATISFIED | `compute_weather_features` produces `is_dome`, `temperature`, `wind_speed`, `is_high_wind`, `is_cold`, `surface`; present in all 10 Silver seasons |
| SCHED-02 | 22-01, 22-02 | Rest days (days since last game, bye week timing, short week flag) per team/week | SATISFIED | `compute_rest_features` produces `rest_days`, `opponent_rest`, `is_short_rest`, `is_post_bye`, `rest_advantage` with correct thresholds and capping |
| SCHED-03 | 22-01, 22-02 | Travel distance between venues using stadium coordinates lookup | SATISFIED | `compute_travel_features` uses `STADIUM_ID_COORDS` + haversine; 0 for home games, correct non-zero for away; 2024 spot-check: ARI wk1 = 1913.0 miles |
| SCHED-04 | 22-01, 22-02 | Time zone differential for cross-country games | SATISFIED | `_timezone_diff_hours` uses pytz DST-aware localization; ARI wk1 = 3.0h tz_diff confirmed in 2024 data |
| SCHED-05 | 22-01, 22-02 | Head coach per game with coaching change detection flag (mid-season and off-season) | SATISFIED | `compute_coaching_features` detects off-season and mid-season changes, tracks tenure; 7 teams with `coaching_change=True` in 2024 |

No orphaned requirements. REQUIREMENTS.md marks all five SCHED-01 through SCHED-05 as `[x] Complete` for Phase 22.

---

### Anti-Patterns Found

None. No TODO/FIXME/placeholder comments, no stub implementations, no return-null bodies found in any phase 22 files.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No anti-patterns detected | — | — |

**Notable (informational):** 2016 Silver has 33 NaN `travel_miles` rows for `OAK` and `SD` team codes. This is documented as expected behavior — `STADIUM_COORDINATES` uses current team codes (`LV`, `LAC`) and pre-relocation abbreviations have no home coordinate entry. Downstream consumers should handle NaN travel_miles gracefully for these historical seasons.

---

### Human Verification Required

None. All observable truths are verifiable programmatically from the codebase and parquet output.

---

### Gaps Summary

No gaps. All must-haves from both plans verified. The phase goal — building schedule-derived game context features as a Silver layer module — is fully achieved:

- `src/game_context.py` is a complete, non-stub module with all required feature computation logic
- `src/config.py` has a verified 42-entry `STADIUM_ID_COORDS` dict sourced from actual Bronze data
- 22 unit tests covering every feature category all pass
- Silver parquet files for 2016-2025 exist with correct shape (22 columns, 32 teams, ~534-570 rows/season)
- Pipeline health check covers game_context paths
- Full 347-test suite passes with zero regressions

---

_Verified: 2026-03-17T23:10:00Z_
_Verifier: Claude (gsd-verifier)_
