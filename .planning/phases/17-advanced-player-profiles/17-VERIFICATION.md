---
phase: 17-advanced-player-profiles
verified: 2026-03-14T23:00:00Z
status: passed
score: 15/15 must-haves verified
re_verification: false
---

# Phase 17: Advanced Player Profiles Verification Report

**Phase Goal:** Users can generate NGS, PFR, and QBR-derived player profile metrics with rolling windows for enhanced QB, RB, WR, and TE evaluation
**Verified:** 2026-03-14T23:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | NGS receiving metrics (separation, catch probability, intended air yards) extracted for WR/TE with roll3/roll6 rolling windows | VERIFIED | NGS_RECEIVING_COLS defined at lines 32-40 of player_advanced_analytics.py; ngs_ prefix applied; 72 ngs cols in all output seasons |
| 2 | NGS passing metrics (time-to-throw, aggressiveness, completed air yards) extracted for QB with rolling windows | VERIFIED | NGS_PASSING_COLS at lines 42-50; compute_ngs_passing_profile at line 237; confirmed in output |
| 3 | NGS rushing metrics (RYOE, efficiency) extracted for RB with rolling windows | VERIFIED | NGS_RUSHING_COLS at lines 52-58; compute_ngs_rushing_profile at line 258; confirmed in output |
| 4 | PFR pressure rate per QB computed with rolling windows | VERIFIED | PFR_PRESSURE_COLS at lines 60-67; compute_pfr_pressure_rate at line 284; 40 pfr cols in output |
| 5 | PFR team blitz rate aggregated from defender-level to team-level with rolling windows | VERIFIED | compute_pfr_team_blitz_rate at line 305; groupby team/season/week sum; pfr_def_ prefix; team-level join in script |
| 6 | QBR rolling windows (total QBR, points added) computed for QB-only rows | VERIFIED | compute_qbr_profile at line 353; QBR_COLS includes qbr_total, pts_added; non-QB rows set to NaN at script line 472; confirmed QB has QBR=True, non-QB QBR=False for 2020-2023 |
| 7 | Rolling windows use shift(1), groupby([player_gsis_id, season]), min_periods=3 | VERIFIED | apply_player_rolling at line 89; shift(1).rolling(window, min_periods=3).mean() at line 130; groupby [player_gsis_id, season] confirmed |
| 8 | Running silver_advanced_transformation.py --seasons 2024 produces Parquet at data/silver/players/advanced/season=2024/ | VERIFIED | data/silver/players/advanced/season=2024/advanced_profiles_20260314_183336.parquet exists; 5,597 rows |
| 9 | Output contains NGS, PFR, and QBR columns in one row per player-week via left-join from roster master | VERIFIED | All 6 seasons: 72 ngs cols, 40 pfr cols, 16 qbr cols (2020-2023), 0 dups per season |
| 10 | Players without advanced stats preserved with NaN columns (no silent row drops) | VERIFIED | Row count assertions at lines 208-211, 335-342, 381-388; left merges enforced throughout; 0 duplicates in all seasons |
| 11 | Missing Bronze data for a source logs warning and produces NaN columns for that source | VERIFIED | Warning logged for missing Bronze dirs; script continues gracefully; QBR absent for 2024-2025 with NaN cols as expected |
| 12 | NaN coverage logged at write time per advanced stat column | VERIFIED | log_nan_coverage called at line 492 with all advanced_cols before write |
| 13 | PFR blitz rate (team-level) joined onto players by team+season+week | VERIFIED | blitz_profile joined on [recent_team, season, week] at script lines 366-398; team-level join gives all players on team same values |
| 14 | QBR columns only appear on QB-position rows; non-QB rows have NaN QBR | VERIFIED | master.loc[master["position"] != "QB", all_qbr_cols] = np.nan at line 472; output confirms non-QB QBR=False |
| 15 | Team abbreviation normalization handles LA/LAR and WAS/WSH mismatches | VERIFIED | TEAM_ABBR_NORM = {"LAR": "LA", "WSH": "WAS"} at line 51; _normalize_team applied before each join |

**Score:** 15/15 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/player_advanced_analytics.py` | All 6 compute functions + rolling utility + NaN logger | VERIFIED | 400 lines; all 8 functions present (apply_player_rolling, compute_ngs_receiving_profile, compute_ngs_passing_profile, compute_ngs_rushing_profile, compute_pfr_pressure_rate, compute_pfr_team_blitz_rate, compute_qbr_profile, log_nan_coverage) |
| `tests/test_player_advanced_analytics.py` | 28+ unit tests, min_lines=100 | VERIFIED | 469 lines; 28 tests covering all 6 PROF requirements, rolling behavior, missing column handling, NaN logging, row preservation — all passing |
| `src/config.py` | SILVER_PLAYER_S3_KEYS entry for advanced_profiles | VERIFIED | "advanced_profiles" at line 128 |
| `scripts/silver_advanced_transformation.py` | CLI script orchestrating Bronze read, join, merge, rolling, Silver write, min_lines=100 | VERIFIED | 581 lines; full pipeline with argparse, _read_local_bronze, process_season, _save_local_silver |
| `data/silver/players/advanced/season=2024/` | Merged advanced player profile Parquet | VERIFIED | advanced_profiles_20260314_183336.parquet present; 5,597 rows, 72 ngs, 40 pfr, 56 rolling cols |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/player_advanced_analytics.py` | `src/team_analytics.py` | apply_player_rolling mirrors apply_team_rolling pattern | VERIFIED | shift(1).rolling(window, min_periods=3).mean() pattern confirmed at line 130; compute_pfr_team_blitz_rate imports apply_team_rolling for team-level groupby |
| `tests/test_player_advanced_analytics.py` | `src/player_advanced_analytics.py` | pytest imports | VERIFIED | "from player_advanced_analytics import" confirmed; all 28 tests pass |
| `scripts/silver_advanced_transformation.py` | `src/player_advanced_analytics.py` | imports compute functions | VERIFIED | "from player_advanced_analytics import" at line 29; all 7 compute functions imported |
| `scripts/silver_advanced_transformation.py` | `data/bronze/ngs/` | _read_local_bronze for NGS data | VERIFIED | _read_local_bronze("ngs/receiving", season) at line 276, "ngs/passing" at 281, "ngs/rushing" at 286 |
| `scripts/silver_advanced_transformation.py` | `data/bronze/pfr/` | _read_local_bronze for PFR data | VERIFIED | _read_local_bronze("pfr/weekly/pass", season) at line 295; "pfr/weekly/def" at line 366 |
| `scripts/silver_advanced_transformation.py` | `data/bronze/qbr/` | _read_local_bronze for QBR data | VERIFIED | _read_local_bronze("qbr", season, prefix="qbr_weekly_") at line 404 |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PROF-01 | 17-01, 17-02 | NGS WR/TE profile (separation, catch probability, intended air yards) with rolling windows | SATISFIED | compute_ngs_receiving_profile with NGS_RECEIVING_COLS; 72 ngs cols in output including ngs_avg_separation, ngs_catch_percentage, ngs_avg_intended_air_yards |
| PROF-02 | 17-01, 17-02 | NGS QB profile (time-to-throw, aggressiveness, completed air yards) with rolling windows | SATISFIED | compute_ngs_passing_profile with NGS_PASSING_COLS; ngs_avg_time_to_throw, ngs_aggressiveness, ngs_avg_completed_air_yards present in output |
| PROF-03 | 17-01, 17-02 | NGS RB profile (rush yards over expected, efficiency) with rolling windows | SATISFIED | compute_ngs_rushing_profile with NGS_RUSHING_COLS; ngs_rush_yards_over_expected, ngs_efficiency confirmed |
| PROF-04 | 17-01, 17-02 | PFR pressure rate (hits + hurries + sacks / dropbacks) per QB with rolling windows | SATISFIED | compute_pfr_pressure_rate with PFR_PRESSURE_COLS; pfr_times_pressured_pct, pfr_times_sacked, pfr_times_hurried, pfr_times_hit in output |
| PROF-05 | 17-01, 17-02 | PFR blitz rate per defensive team with rolling windows | SATISFIED | compute_pfr_team_blitz_rate aggregates PFR_DEF_BLITZ_COLS; pfr_def_ prefix; team-level join in silver script |
| PROF-06 | 17-01, 17-02 | QBR rolling windows (total QBR, points added) per QB | SATISFIED | compute_qbr_profile with QBR_COLS (qbr_total, pts_added, qb_plays, epa_total); QB-only enforcement at script line 472 |

All 6 PROF requirements satisfied. No orphaned requirements detected — REQUIREMENTS.md maps PROF-01 through PROF-06 to Phase 17, and both plans claim all 6.

---

### Anti-Patterns Found

None. No TODO/FIXME/HACK/PLACEHOLDER comments found. No empty return implementations. No console.log-only handlers.

---

### Human Verification Required

None required. All goal behaviors were verifiable programmatically:

- Output files exist and have correct column counts (verified via pandas read_parquet)
- QB-only QBR enforcement confirmed via DataFrame position filter check
- Rolling window correctness (shift(1), min_periods=3, no cross-season leakage) confirmed via test suite
- Row count preservation confirmed via assertions in the script and duplicate checks on output

---

### Test Suite Results

- `tests/test_player_advanced_analytics.py`: 28/28 passed (1.34s)
- Full suite: 274/274 passed — no regressions introduced by Phase 17

---

### Output Quality Summary

| Season | Rows | NGS Cols | PFR Cols | QBR Cols | Rolling Cols | Duplicates |
|--------|------|----------|----------|----------|-------------|------------|
| 2020 | 5,447 | 72 | 40 | 16 | 64 | 0 |
| 2021 | 5,698 | 72 | 40 | 16 | 64 | 0 |
| 2022 | 5,631 | 72 | 40 | 16 | 64 | 0 |
| 2023 | 5,653 | 72 | 40 | 16 | 64 | 0 |
| 2024 | 5,597 | 72 | 40 | 0 | 56 | 0 |
| 2025 | 19,421 | 72 | 40 | 0 | 56 | 0 |

QBR absent for 2024-2025 as expected per RESEARCH.md (data not available for those seasons).

---

_Verified: 2026-03-14T23:00:00Z_
_Verifier: Claude (gsd-verifier)_
