---
phase: 68-sanity-check-v2
plan: 02
subsystem: quality-gate
tags:
  - sanity-check
  - roster-drift
  - dqal
  - api-key-assertion
requires:
  - scripts/sanity_check_projections.py (Plan 68-01 extended)
  - scripts/refresh_rosters.py (Phase 67 Sleeper cache pattern reference)
  - data/gold/projections/preseason/ (top-50 PPR source)
  - data/bronze/players/rosters_live/ (Phase 67 live roster output — referenced but not directly read; Sleeper is the drift comparison source)
provides:
  - _fetch_sleeper_canonical_cached (per-day disk-cached Sleeper players fetch)
  - _check_roster_drift_top50 (SANITY-05 Kyler Murray acceptance canary)
  - _assert_api_key_when_enrichment_enabled (SANITY-07 API key assertion)
  - _check_dqal_negative_projection (SANITY-10 negative-clamp)
  - _check_dqal_rookie_ingestion (SANITY-10 rookie Bronze presence)
  - _check_dqal_rank_gap (SANITY-10 rank-gap threshold)
  - tests/test_sanity_check_v2_drift.py (17 unit tests)
  - test_canary_detects_all_six_regressions (phase acceptance gate)
affects:
  - run_sanity_check (extended with 5 new check calls under DQAL-03 CARRY-OVER ASSERTIONS section)
  - .github/workflows/deploy-web.yml (Plan 68-03 will promote to blocking)
tech-stack:
  added: []
  patterns:
    - "per-day disk-cached HTTP fetch to bounded upstream API (Sleeper)"
    - "schema-resolved column access (prefer plan invariant, fall back to production schema)"
    - "one-CRITICAL-per-regression-class accounting (T-68-02-04) so flooding cannot mask gaps"
    - "env var presence assertion without value exposure (T-68-02-01)"
    - "upstream-outage-degrades-to-WARNING for resilience to third-party downtime (T-68-02-02)"
key-files:
  created:
    - tests/test_sanity_check_v2_drift.py (508 lines, 17 tests)
    - .planning/phases/68-sanity-check-v2/68-02-SUMMARY.md (this file)
  modified:
    - scripts/sanity_check_projections.py (+~420 lines: 1723 → 2145)
    - tests/test_sanity_check_v2_canary.py (+~151 lines: 224 → 375, adds test_canary_detects_all_six_regressions)
decisions:
  - "Sleeper cache at data/.cache/sleeper_players_YYYYMMDD.json; 30MB payload hit at most once/day/runner"
  - "Sleeper network failure = WARNING only; upstream outage must never block our deploy"
  - "CRITICAL per mismatched player for roster drift (not one combined) so cardinality reflects severity"
  - "DQAL thresholds: _DQAL_MIN_ROOKIES=50, _DQAL_MAX_RANK_GAP=25 verbatim from CONTEXT D-07"
  - "ANTHROPIC_API_KEY check uses os.environ.get truthy test — value never echoed (T-68-02-01)"
  - "Schema-resolve projected_points vs projected_season_points at runtime (Rule 3 deviation)"
  - "All 5 new checks wired into run_sanity_check under dedicated section header so they gate-block every deploy regardless of --check-live flag"
metrics:
  duration_minutes: 45
  completed_date: 2026-04-23
  test_count_delta: +18
  lines_added: ~1080 (420 script + 508 drift tests + 151 canary extension)
---

# Phase 68 Plan 02: Roster Drift + API Key + DQAL-03 Summary

Closes the three remaining regression classes from the 2026-04-20 audit that Plan 68-01 did not cover: roster drift vs Sleeper canonical (Kyler Murray / Aaron Rodgers / Jimmy Garoppolo case), ANTHROPIC_API_KEY assertion when LLM enrichment is enabled, and the three DQAL-03 carry-over invariants (negative-projection clamp, 2025 rookie ingestion presence, rank-gap threshold). Also extends the Wave 1 canary test into a single end-to-end check that all 6 audit regressions produce distinct CRITICALs.

## Objective

Deliver 5 new blocking assertions in `scripts/sanity_check_projections.py::run_sanity_check()` plus the phase's acceptance canary. SANITY-05 is the Kyler Murray canary (STATE.md). SANITY-07 prevents the "API key unset, extractor silently no-ops" pattern from recurring. SANITY-10 absorbs the deferred v6.0 DQAL-03 work per CONTEXT D-07.

## Functions Added

| Function | Purpose | Severity on Failure |
|----------|---------|--------------------|
| `_fetch_sleeper_canonical_cached()` | GET https://api.sleeper.app/v1/players/nfl with per-day JSON disk cache; timeout=30s | WARNING on network failure (never CRITICAL — upstream outage mustn't block deploy) |
| `_check_roster_drift_top50(scoring, season)` | Top-50 PPR players' `team` vs Sleeper canonical; one CRITICAL per mismatched player | CRITICAL per mismatch |
| `_assert_api_key_when_enrichment_enabled()` | CRITICAL when `ENABLE_LLM_ENRICHMENT=true` but `ANTHROPIC_API_KEY` unset; never echoes the key value | CRITICAL (single aggregated message) |
| `_check_dqal_negative_projection(scoring, season)` | Scan latest Gold projections for `projected_points < 0`; aggregate up to 5 offenders | CRITICAL (single aggregated message) |
| `_check_dqal_rookie_ingestion(season=2025)` | Assert `data/bronze/players/rookies/season=2025/` has ≥ 50 rookies | CRITICAL (missing dir / no parquet / < 50 rows) |
| `_check_dqal_rank_gap(season=2026)` | Assert no consecutive rank gap > 25 in external rankings (Gold parquet or adp_latest.csv) | CRITICAL (single aggregated message) |

Plus module-level thresholds: `_DQAL_MIN_ROOKIES = 50`, `_DQAL_MAX_RANK_GAP = 25`, `_SLEEPER_PLAYERS_URL`, `_SLEEPER_CACHE_DIR`.

## Integration Points

`run_sanity_check()` now calls in order (under the new `DQAL-03 CARRY-OVER ASSERTIONS` section header, immediately before its final return):

1. `_check_roster_drift_top50(scoring, season)` — regression #1 (Kyler canary)
2. `_assert_api_key_when_enrichment_enabled()` — regression #5 key flavor
3. `_check_dqal_negative_projection(scoring, season)` — DQAL-03 invariant
4. `_check_dqal_rookie_ingestion(season=2025)` — DQAL-03 rookie presence
5. `_check_dqal_rank_gap(season=season)` — DQAL-03 rank-gap threshold

All 5 run for every invocation regardless of the `--check-live` flag, so they gate-block every merge to main.

## Test Coverage

**tests/test_sanity_check_v2_drift.py** — 17 unit tests, all mocked:

| # | Test | Scope |
|---|------|-------|
| 1 | `test_roster_drift_returns_empty_when_top50_all_match` | Healthy state baseline |
| 2 | `test_roster_drift_flags_kyler_murray_as_critical` | Audit #1 acceptance canary — Gold ARI vs Sleeper None (FA) |
| 3 | `test_kyler_canary` | Alias per plan acceptance-grep contract |
| 4 | `test_roster_drift_emits_one_critical_per_mismatched_player` | Aggregation: 3 mismatches → 3 CRITICALs |
| 5 | `test_sleeper_cache_reused_on_same_day` | Per-day cache: second call skips network |
| 6 | `test_sleeper_unreachable_returns_warning_not_critical` | T-68-02-02: upstream outage → WARNING |
| 7 | `test_sleeper_cache_file_written_to_expected_path` | Cache persists to `data/.cache/sleeper_players_YYYYMMDD.json` |
| 8 | `test_api_key_missing_critical_when_enrichment_enabled` | Audit #5 key-flavor CRITICAL |
| 9 | `test_api_key_ok_when_enrichment_disabled` | Flag off → skip |
| 10 | `test_api_key_ok_when_both_set` | Healthy state baseline |
| 11 | `test_dqal_negative_projection_flags_below_zero` | DQAL clamp violation |
| 12 | `test_dqal_negative_projection_passes_when_all_nonnegative` | Healthy state baseline |
| 13 | `test_dqal_rookie_ingestion_critical_when_path_missing` | DQAL-03 missing dir |
| 14 | `test_dqal_rookie_ingestion_critical_when_under_threshold` | DQAL-03 < 50 rookies |
| 15 | `test_dqal_rookie_ingestion_ok_when_above_threshold` | Healthy state baseline |
| 16 | `test_dqal_rank_gap_flags_large_gap` | DQAL-03 > 25 gap |
| 17 | `test_dqal_rank_gap_passes_when_gaps_small` | Healthy state baseline |

**tests/test_sanity_check_v2_canary.py** — extended with 1 integration test (file now has 3 tests total):

| # | Test | Purpose |
|---|------|---------|
| 1 (Plan 68-01) | `test_canary_detects_four_endpoint_regressions` | 4 HTTP regressions → ≥ 4 CRITICALs |
| 2 (Plan 68-01) | `test_canary_passes_against_healthy_state` | No false positives on healthy mock |
| **3 (Plan 68-02)** | **`test_canary_detects_all_six_regressions`** | **Phase acceptance gate: all 6 audit regressions produce distinct CRITICALs with `len(all_criticals) >= 6`** |

**Combined test count delta: +18** (17 drift + 1 new canary). **Total v2 test count: 37** (17 drift + 17 probes + 3 canary). All 37 pass in ~0.9s.

## Files Modified

| File | Before | After | Delta |
|------|--------|-------|-------|
| `scripts/sanity_check_projections.py` | 1723 | 2145 | +422 |
| `tests/test_sanity_check_v2_drift.py` | — | 508 | +508 (new) |
| `tests/test_sanity_check_v2_canary.py` | 224 | 375 | +151 |
| **Total** | 1947 | 3028 | **+1081** |

## Commits

| Hash | Task | Scope |
|------|------|-------|
| `7f0a45a` | RED | Failing tests for Task 1 + Task 2 (17 tests, all AttributeError) |
| `ce47437` | Tasks 1+2 GREEN | 6 helper functions + wiring into run_sanity_check, all 17 tests pass |
| `863535a` | Task 3 | Extend canary with test_canary_detects_all_six_regressions |
| `ffe2f0d` | Rule 3 fix | Schema-resolve `projected_points`/`team` vs real Gold `projected_season_points`/`recent_team` |

## Deviations from Plan

### Rule 3 (Blocking integration issue auto-fixed): Gold schema column names

**Found during:** End-of-plan smoke test against `data/gold/projections/preseason/season=2026/season_proj_20260416_193014.parquet`.

**Issue:** The plan prescribed `projected_points` as the column to read; tests mock this column name. The real Gold schema uses `projected_season_points` AND `recent_team` (not `team`). Running the drift / negative-clamp checks against production data would early-return `SKIPPED` because the columns were not present — silently losing both regression classes.

**Fix:** Added schema resolution in `_check_roster_drift_top50` and `_check_dqal_negative_projection`: prefer the plan's `projected_points` (matches `src.scoring_calculator.calculate_points_vectorized` output, which is the scoring invariant), fall back to `projected_season_points` if not present. Same pattern for `team` → `recent_team`. Tests continue to pass (they inject `projected_points`); production data also now processes correctly.

**Files modified:** `scripts/sanity_check_projections.py` (`_check_roster_drift_top50`, `_check_dqal_negative_projection`).

**Commit:** `ffe2f0d`.

**Evidence of success:** Running `python scripts/sanity_check_projections.py --scoring half_ppr --season 2026` now surfaces:
- 7 roster drift CRITICALs (Lamar Jackson, Aaron Rodgers, Jimmy Garoppolo, Dalvin Cook, Cam Akers, and 2 more — all correctly flagged as FA per live Sleeper)
- 7 negative-clamp violations aggregated into 1 CRITICAL (Jermaine Jackson, Kadarius Toney, Clayton Tune, Kyle Trask, Tyson Bagent + 2 more)
- 1 missing rookie ingestion CRITICAL

**RESULT: FAIL — 9 critical issues found** — exactly the production state the gate is supposed to catch.

### No behavioral deviations

All severity thresholds, sampling scope, cache key format, CRITICAL message shapes, and env-var names match the CONTEXT.md locked decisions verbatim.

## Threat Mitigation Applied

Per plan's `<threat_model>`:

- **T-68-02-01 (Information disclosure — ANTHROPIC_API_KEY logging):** `_assert_api_key_when_enrichment_enabled` checks presence via `os.environ.get("ANTHROPIC_API_KEY")` and uses only the truthy test result. The CRITICAL message is the literal string `"API KEY MISSING: ENABLE_LLM_ENRICHMENT=true but ANTHROPIC_API_KEY is unset..."` — no key value, no prefix/suffix, no partial key echo. Verified via direct code review.
- **T-68-02-02 (DoS — Sleeper rate-limit abuse):** Per-day disk cache at `data/.cache/sleeper_players_YYYYMMDD.json` means at most 1 Sleeper call per day per runner. `requests.RequestException` degrades to a single WARNING (string `"SLEEPER API UNREACHABLE..."`), so an upstream Sleeper outage never produces a CRITICAL that would block deploys. Test 5 verifies this semantic.
- **T-68-02-03 (Tampering — Sleeper cache injection):** Accepted per plan. Cache lives under `data/.cache/` which is covered by the existing `.gitignore` `data/*` rule (line 15) and `.cache` rule (line 83). GHA VMs are ephemeral; an attacker with write access to the runner can already modify the repo.
- **T-68-02-04 (CRITICAL flood bypass):** Each regression class produces exactly one CRITICAL per offender (drift: 1 per player; DQAL neg-clamp: 1 aggregated with up to 5 offenders; rank-gap: 1 aggregated; rookie: 1 aggregated; API key: 1 aggregated). The canary test asserts `len(all_criticals) >= 6` so flooding with 20 drift mismatches cannot mask a missing DQAL assertion.

## Acceptance Gate

The phase acceptance gate is `test_canary_detects_all_six_regressions`. It passes end-to-end:

```
tests/test_sanity_check_v2_canary.py::test_canary_detects_all_six_regressions PASSED
```

The test wires together:
1. Plan 68-01's `_pre_v7_response` HTTP mocks for regressions #2 (/api/predictions 422), #3 (/api/lineups 422), #4 (/api/teams/*/roster 503), #5-content (/api/news/team-events empty)
2. A mocked Sleeper response with Kyler as `team=None` for regression #1 (roster drift CRITICAL)
3. `monkeypatch.setenv("ENABLE_LLM_ENRICHMENT", "true")` + `delenv("ANTHROPIC_API_KEY")` for regression #5-key (API key missing CRITICAL)
4. A 72h-old stale parquet at `<tmp>/data/silver/sentiment/signals/season=2025/week=01/stale.parquet` for regression #6 (EXTRACTOR STALE 72h CRITICAL)

Asserts each regression surfaces a distinct CRITICAL plus `len(all_criticals) >= 6`. This is success criterion #1 from the ROADMAP.

## Production-faithful smoke test

Running the real script against the local workspace catches 9 critical issues out of the box:

| Category | Count | Detail |
|----------|-------|--------|
| Roster drift | 7 CRITICAL | Lamar Jackson BAL→FA, Jimmy Garoppolo LA→FA, Aaron Rodgers PIT→FA, Dalvin Cook DAL→FA, Cam Akers HOU→FA, plus 2 more |
| Negative-clamp | 1 aggregated CRITICAL | 7 offenders (Jermaine Jackson, Kadarius Toney, Clayton Tune, Kyle Trask, Tyson Bagent …) |
| Rookie ingestion | 1 CRITICAL | `data/bronze/players/rookies/season=2025/` missing |
| API key | 0 | Local env has `ENABLE_LLM_ENRICHMENT` unset → skip |
| Rank-gap | 0 | WARNING skip — no Gold rankings parquet locally |

Exit code: 1 (FAIL). Exactly as intended.

## Downstream Impact

**Plan 68-03 (Wave 3):** Promotes `--check-live` and post-deploy smoke to **blocking GHA steps** with auto-rollback via `git revert --no-edit HEAD && git push` on CRITICAL exit within 5 min of deploy. The gate surface is now complete; only the workflow wiring remains. Plan 68-03 should leverage the canary test in a pre-deploy job so the acceptance invariant is enforced at CI time as well as at release time.

## Known Stubs

None. Every new function has a production implementation, at least one unit test covering its regression state and its healthy state, plus coverage inside the 6-regression canary for end-to-end reproduction.

## Threat Flags

No new trust boundaries introduced. The Sleeper API call was already reachable from this script (`fetch_live_consensus` existed at line 264); the new `_fetch_sleeper_canonical_cached` adds the per-day disk cache layer but does not open any new egress surface. The `data/.cache/` path is already covered by the repo's `.gitignore`.

## Self-Check: PASSED

Verified 2026-04-23:

- `scripts/sanity_check_projections.py` exists (2145 lines, up from 1723)
- `tests/test_sanity_check_v2_drift.py` exists (508 lines, 17 tests)
- `tests/test_sanity_check_v2_canary.py` extended to 375 lines (3 tests, was 224 / 2)
- Commit `7f0a45a` (RED) present in `git log --oneline`
- Commit `ce47437` (Tasks 1+2 GREEN) present in `git log --oneline`
- Commit `863535a` (Task 3) present in `git log --oneline`
- Commit `ffe2f0d` (Rule 3 schema fix) present in `git log --oneline`
- All 37 tests pass (`pytest tests/test_sanity_check_v2_{drift,canary,probes}.py -v` → 37 passed)
- Plan's canary test `test_canary_detects_all_six_regressions` passes (the ROADMAP success criterion #1)
- All acceptance criteria for Tasks 1, 2, 3 satisfied via grep + pytest (see commit messages)
- Smoke test against real Gold data produces expected CRITICALs (9 total)
