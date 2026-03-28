---
phase: 32-bronze-odds-ingestion
verified: 2026-03-27T21:47:59Z
status: passed
score: 4/4 success criteria verified
re_verification: false
---

# Phase 32: Bronze Odds Ingestion Verification Report

**Phase Goal:** Historical opening and closing lines exist as validated Bronze Parquet, joinable to every nflverse game
**Verified:** 2026-03-27T21:47:59Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| #  | Truth                                                                                                                        | Status     | Evidence                                                                                                        |
|----|------------------------------------------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------------|
| 1  | Running the odds ingestion script produces Parquet under `data/bronze/odds/season=YYYY/` with opening/closing spread+total   | VERIFIED   | `data/bronze/odds/season=2020/odds_20260327_174221.parquet` — 244 rows, all 14 required columns present         |
| 2  | Every SBRO game row joins to exactly one nflverse game_id — zero orphan rows after merge                                     | VERIFIED   | `game_id.isna().sum() == 0` confirmed on 244-row output; `test_zero_orphans` passes                             |
| 3  | Cross-validation between SBRO closing lines and nflverse spread_line/total_line shows >95% agreement within 1.0 point        | VERIFIED   | End-to-end run: Pearson r=0.997, within-1pt=97.1% (both thresholds cleared); `test_cross_validation_gate` passes|
| 4  | The `odds` data type is registered in the Bronze ingestion registry and passes schema validation                              | VERIFIED   | `DATA_TYPE_SEASON_RANGES["odds"] = (2016, lambda: 2021)`; `validate_season_for_type` returns correct bounds     |

**Score: 4/4 truths verified**

---

### Additional Must-Have Truths (from PLAN 32-01 frontmatter)

| Truth                                                                        | Status   | Evidence                                                                                              |
|------------------------------------------------------------------------------|----------|-------------------------------------------------------------------------------------------------------|
| FinnedAI JSON downloads to data/raw/sbro/ with skip-existing logic           | VERIFIED | `data/raw/sbro/nfl_archive_10Y.json` exists; `download_finnedai(force=False)` skips if file present  |
| All 44 FinnedAI team names map to valid nflverse abbreviations               | VERIFIED | `FINNEDAI_TO_NFLVERSE` has 45 entries (44 + `NewYork: None`); `test_team_mapping_complete` passes    |
| NewYork ambiguity resolves correctly to NYG or NYJ per game                  | VERIFIED | `resolve_newyork()` matches by opponent against nflverse schedule; `test_newyork_disambiguation` passes|
| Corrupt team=0 entries are dropped before processing                         | VERIFIED | `parse_finnedai()` drops entries where `str(home_team) == "0"`; `test_corrupt_entries_dropped` passes |
| Spreads are negated to match nflverse convention (positive = home favored)   | VERIFIED | `df["opening_spread"] = -df["home_open_spread"]` at line 368; `test_sign_convention` passes           |
| Every odds row joins to exactly one nflverse game_id                         | VERIFIED | 244/244 rows have non-null game_id; all in valid format `YYYY_WW_AWAY_HOME`                          |
| Cross-validation passes: Pearson r > 0.95 and >95% within 1.0 point         | VERIFIED | r=0.997, 97.1% within 1pt on 2020 end-to-end run                                                     |
| Parquet output contains all required columns with correct types              | VERIFIED | All 14 columns verified: game_id, season, week, game_type, home_team, away_team, opening_spread, closing_spread, opening_total, closing_total, home_moneyline, away_moneyline, nflverse_spread_line, nflverse_total_line |
| Missing opening lines are NaN, never zero or dropped (D-11)                 | VERIFIED | D-11 comment at lines 184-185; no fill/zero replacement; `opening_spread` null count=0 for 2020 data |
| Postponed games with no final score are excluded (D-12)                      | VERIFIED | Lines 210-217: `home_final` checked for None, NaN, or empty string before including row              |

---

### Required Artifacts

| Artifact                               | Expected                                         | Status     | Details                                                              |
|----------------------------------------|--------------------------------------------------|------------|----------------------------------------------------------------------|
| `scripts/bronze_odds_ingestion.py`     | Full pipeline: download, parse, map, join, validate, write | VERIFIED | 761 lines (min 200); all 10 required functions present; wired in test suite and runnable |
| `tests/test_bronze_odds.py`            | 11+ unit/integration tests                       | VERIFIED   | 405 lines, 13 test functions, 0 skipped tests                        |
| `src/config.py`                        | odds in DATA_TYPE_SEASON_RANGES                  | VERIFIED   | Line 364: `"odds": (2016, lambda: 2021)` present                    |
| `data/bronze/odds/season=2020/`        | Sample Parquet from end-to-end run               | VERIFIED   | `odds_20260327_174221.parquet` — 244 rows, 14 columns, 0 null game_ids |

---

### Key Link Verification

| From                                | To                                     | Via                              | Status  | Details                                                                      |
|-------------------------------------|----------------------------------------|----------------------------------|---------|------------------------------------------------------------------------------|
| `scripts/bronze_odds_ingestion.py`  | `data/raw/sbro/nfl_archive_10Y.json`  | `requests.get` download          | WIRED   | `requests.get` at line ~120; file present at `data/raw/sbro/`               |
| `scripts/bronze_odds_ingestion.py`  | nfl_data_py schedules                  | `nfl.import_schedules` for game_id join | WIRED | `sched = nfl.import_schedules([season])` at line 402                    |
| `scripts/bronze_odds_ingestion.py`  | `data/bronze/odds/season=YYYY/`        | `df.to_parquet` output           | WIRED   | `out_df.to_parquet(out_path, index=False)` at line 617; file produced       |
| `src/config.py`                     | `scripts/bronze_odds_ingestion.py`     | `validate_season_for_type('odds', season)` in main() | WIRED | Line 658: `validate_season_for_type("odds", args.season)` |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                                          | Status    | Evidence                                                                                      |
|-------------|-------------|--------------------------------------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------|
| ODDS-01     | 32-01       | Download and parse SBRO/FinnedAI archives into Parquet with opening/closing spreads and totals (2016-2021) | SATISFIED | `download_finnedai()`, `parse_finnedai()`, `align_spreads()`, `write_parquet()` all implemented and verified; 2020 Parquet output confirmed |
| ODDS-02     | 32-01       | Map SBRO team names to nflverse game_id with validated team name mapping dictionary  | SATISFIED | 45-entry `FINNEDAI_TO_NFLVERSE` dict; `resolve_newyork()`; `join_to_nflverse()` — zero orphans on 2020 run |
| ODDS-03     | 32-02       | Register 'odds' as a Bronze data type with schema validation in the ingestion registry | SATISFIED | `DATA_TYPE_SEASON_RANGES["odds"] = (2016, lambda: 2021)` at config.py line 364; `validate_odds_schema()` implemented; `test_config_registration` and `test_validate_season_for_type_odds` both pass |

No orphaned requirements — all three ODDS-01, ODDS-02, ODDS-03 are claimed by plans and verified in code.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | — |

No TODO/FIXME comments, no empty return stubs, no placeholder implementations, no skipped tests found in `scripts/bronze_odds_ingestion.py`, `tests/test_bronze_odds.py`, or `src/config.py`.

Note: `tests/test_infrastructure.py` was updated to expect 17 data types (up from 16) — correctly reflects the new odds registration.

---

### Human Verification Required

No items require human verification. All behaviors are programmatically verifiable:
- Parquet schema and row counts are machine-readable
- Cross-validation thresholds are numerical
- Zero orphan tolerance is measurable
- Registry bounds are unit-tested

---

### Test Suite Health

| Suite scope | Count | Status |
|-------------|-------|--------|
| `tests/test_bronze_odds.py` | 13 tests | 13 passed, 0 skipped, 0 failed |
| Full `tests/` suite | 516 tests | 516 passed, 0 failed |

Baseline before phase 32: 503 tests. Net additions: +13 tests (all new odds coverage).

---

### Gaps Summary

None. All success criteria, artifacts, key links, and requirements are fully satisfied.

---

_Verified: 2026-03-27T21:47:59Z_
_Verifier: Claude (gsd-verifier)_
