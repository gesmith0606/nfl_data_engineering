---
phase: 33-silver-line-movement-features
verified: 2026-03-28T05:30:00Z
status: passed
score: 8/8 must-haves verified
re_verification: false
---

# Phase 33: Silver Line Movement Features Verification Report

**Phase Goal:** Line movement features exist as Silver per-team-per-week rows ready for feature assembly
**Verified:** 2026-03-28T05:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Silver market_data Parquet contains spread_shift, total_shift, and absolute movement columns per game, reshaped to two rows per game (home/away) with correct sign flips for directional features | VERIFIED | `data/silver/teams/market_data/season=2020/market_data_20260328_004701.parquet` — 488 rows (244 games x 2), all 20 columns present. Sign flip verified programmatically for all 244 games: `home.opening_spread + away.opening_spread = 0` for every game |
| 2  | Movement magnitude buckets (large >2pts, medium 1-2, small <1, none) are populated for every game with opening line data; games without opening lines have NaN (not zeros) | VERIFIED | `spread_magnitude` dtype is `float64`, unique values `[0.0, 1.0, 2.0, 3.0]`. `pd.cut` with `[-0.001, 0.0, 1.0, 2.0, inf]` uses `labels=[0,1,2,3]` with `.astype(float)`. Games missing opening lines naturally produce NaN via `pd.cut` |
| 3  | Steam move flag is computed where timestamp data supports it, and explicitly set to NaN where timestamps are unavailable | VERIFIED | `is_steam_move` column exists. `df['is_steam_move'].isna().all()` returns `True` for all 488 rows. Code sets `float("nan")` explicitly with comment `# Steam move: NaN placeholder (no timestamp data in FinnedAI -- per D-15/D-16)` |
| 4  | `feature_engineering.py` includes opening_spread and opening_total in the pre-game feature set, and closing-line-derived features are documented as retrospective-only | VERIFIED | `_PRE_GAME_CONTEXT` at line 362-374 includes `"opening_spread"` and `"opening_total"`. RETROSPECTIVE comment block at lines 368-372 explicitly lists all excluded features. 9 integration tests in `TestMarketFeatureFiltering` verify correct inclusion and exclusion |
| 5  | spread_shift equals closing_spread minus opening_spread for every game row | VERIFIED | `compute_movement_features()` line 56: `df["spread_shift"] = df["closing_spread"] - df["opening_spread"]`. `TestMovementComputation::test_spread_shift` confirms: input `-3.0` opening, `-3.5` closing -> shift `-0.5` |
| 6  | Per-team reshape produces exactly 2x rows (home + away) with correct sign flips on directional features | VERIFIED | `TestPerTeamReshape::test_row_count_doubles` and `test_away_spread_negated` pass. Real data: 244 games -> 488 rows. Programmatic check across all 244 games confirms directional negation |
| 7  | Magnitude buckets are ordinal integers 0-3 covering none/small/medium/large thresholds | VERIFIED | `TestMagnitudeBuckets` all 5 tests pass: `test_none_bucket` (0.0->0), `test_small_bucket` (0.5->1), `test_medium_bucket` (1.5->2), `test_large_bucket` (2.5->3), `test_magnitude_is_float_not_string` (dtype float64) |
| 8  | market_data registered in SILVER_TEAM_LOCAL_DIRS and SILVER_TEAM_S3_KEYS; feature assembly loop auto-discovers it | VERIFIED | `config.py` line 501: `"market_data": "teams/market_data"` in `SILVER_TEAM_LOCAL_DIRS`. Line 241: `"market_data": "teams/market_data/season={season}/market_data_{ts}.parquet"` in `SILVER_TEAM_S3_KEYS` |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/market_analytics.py` | Line movement computation and per-team reshape | VERIFIED | 151 lines. Exports `compute_movement_features()` and `reshape_to_per_team()`. Contains `KEY_SPREAD_NUMBERS = [3, 7, 10]`, `KEY_TOTAL_NUMBERS = [41, 44, 47]`, PRE-GAME/RETROSPECTIVE comment block, `is_steam_move = float("nan")`, `.astype(float)` on magnitude buckets |
| `scripts/silver_market_transformation.py` | Silver CLI for market data transformation | VERIFIED | 168 lines (>40 minimum). Contains `def run_market_transform(`, imports `from market_analytics import compute_movement_features, reshape_to_per_team`, has `argparse`, `_read_local_odds()`, `_save_local_silver()`, `_try_s3_upload()` |
| `tests/test_market_analytics.py` | Unit tests for all movement features | VERIFIED | 225 lines (>80 minimum). 5 test classes: `TestMovementComputation`, `TestMagnitudeBuckets`, `TestKeyNumberCrossing`, `TestSteamMove`, `TestPerTeamReshape`. 20 tests all pass |
| `src/config.py` | market_data in SILVER_TEAM_LOCAL_DIRS and SILVER_TEAM_S3_KEYS | VERIFIED | Line 501: `"market_data": "teams/market_data"`. Line 241: `"market_data":` key in S3 keys dict |
| `src/feature_engineering.py` | opening_spread/opening_total in _PRE_GAME_CONTEXT | VERIFIED | Lines 367-373: both keys in `_PRE_GAME_CONTEXT` set with RETROSPECTIVE documentation comment |
| `data/silver/teams/market_data/season=2020/market_data_20260328_004701.parquet` | Silver output Parquet for season 2020 | VERIFIED | 488 rows, 20 columns, all required feature columns present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `scripts/silver_market_transformation.py` | `src/market_analytics.py` | `from market_analytics import compute_movement_features, reshape_to_per_team` | WIRED | Line 28 of CLI imports and calls both functions at lines 126 and 130 |
| `scripts/silver_market_transformation.py` | `data/bronze/odds/season=YYYY/` | `pd.read_parquet(files[-1])` | WIRED | `_read_local_odds()` at line 54 reads Bronze parquet. CLI produced 244 games for 2020 confirming successful read |
| `src/config.py` | `src/feature_engineering.py` | `SILVER_TEAM_SOURCES` auto-discovery loop | WIRED | `SILVER_TEAM_LOCAL_DIRS` contains `"market_data"`. The `feature_engineering.py` loop (line 186-198 per PLAN context) iterates `SILVER_TEAM_SOURCES` — `market_data` will be auto-discovered when Parquet exists for a season |
| `src/feature_engineering.py` | `data/silver/teams/market_data/` | `_read_latest_local` in Silver source loop | WIRED | `"market_data": "teams/market_data"` path in `SILVER_TEAM_LOCAL_DIRS` is the subdir passed to `_read_latest_local()`. Left-join on `[team, season, week]` produces NaN for missing seasons |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| LINE-01 | 33-01-PLAN, 33-02-PLAN | Compute spread movement (closing - opening) and total movement per game with nflverse sign convention | SATISFIED | `spread_shift = closing_spread - opening_spread` in `compute_movement_features()`. Away rows negate directional features (nflverse convention). Wired into `feature_engineering.py` via `_PRE_GAME_CONTEXT` and Silver auto-discovery loop |
| LINE-02 | 33-01-PLAN | Categorize movement into direction buckets (large >2pts, medium 1-2, small <1, none) | SATISFIED | `spread_magnitude` and `total_magnitude` use `pd.cut` bins `[-0.001, 0.0, 1.0, 2.0, inf]` with labels `[0,1,2,3]` as float64. Matches spec: none=0, small<1=1, medium 1-2=2, large >2=3. All 5 magnitude bucket tests pass |
| LINE-03 | 33-01-PLAN | Detect steam moves (sharp money indicators) where data supports it; NaN where timestamps unavailable | SATISFIED | `is_steam_move = float("nan")` for all rows. Column always present in Silver output. `TestSteamMove::test_is_steam_move_all_nan` confirms. Intent matches spec: "NaN where timestamps unavailable" |

All 3 requirement IDs from PLAN frontmatter are satisfied. No orphaned requirements — REQUIREMENTS.md maps all three exclusively to Phase 33.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/market_analytics.py` | 27, 52 | "placeholder" in docstrings | Info | Describes `is_steam_move` intentional design per D-15/D-16, not a code stub. No user-visible output is a placeholder |
| `scripts/silver_market_transformation.py` | 6 | "steam move placeholder" in module docstring | Info | Same as above — accurate documentation of intentional design |

No blockers or warnings. The `is_steam_move` NaN is an intentional, documented forward-compatible schema column per D-15/D-16 (no timestamp granularity in FinnedAI data). The column exists in the Silver output and is correctly excluded from `_PRE_GAME_CONTEXT`.

### Human Verification Required

None. All success criteria are programmatically verifiable and confirmed.

### Gaps Summary

No gaps. All 8 observable truths verified, all artifacts exist and are substantive, all key links are wired end-to-end, all 3 requirements are satisfied, full test suite passes (545 tests, 0 failures).

**Commit evidence:**
- `10b8076` — market_analytics module with 20 passing tests
- `d7402ae` — Silver market transformation CLI
- `0e208c4` — config.py market_data registration
- `8e9bcf4` — feature_engineering.py _PRE_GAME_CONTEXT wiring with 9 integration tests

All 4 commits verified present in git history.

---

_Verified: 2026-03-28T05:30:00Z_
_Verifier: Claude (gsd-verifier)_
