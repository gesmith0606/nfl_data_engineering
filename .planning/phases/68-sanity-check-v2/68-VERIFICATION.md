---
phase: 68
phase_name: Sanity-Check v2
status: human_needed
verified: 2026-04-23
must_haves_total: 6
must_haves_verified: 5
commits:
  - e78f6ab  # CONTEXT
  - d6d89fb  # plans
  - e5af7d9  # 68-01 task 1
  - f799fe2  # 68-01 task 2
  - 325d3e7  # 68-01 task 3
  - 120d8df  # 68-01 SUMMARY
  - 7f0a45a  # 68-02 RED
  - ce47437  # 68-02 GREEN tasks 1+2
  - 863535a  # 68-02 task 3 canary
  - ffe2f0d  # 68-02 schema-resolve fix
  - f696840  # 68-02 SUMMARY
  - 03797d0  # 68-03 task 1
  - e674a3e  # 68-03 task 2
  - b28e84a  # 68-03 task 3
  - 8e98bfd  # 68-03 SUMMARY
test_count_delta: "+57 tests (17 probes + 17 drift + 3 canary + 20 workflow)"
---

# Phase 68 Verification — Sanity-Check v2

## Overall Status: `human_needed`

5 of 6 ROADMAP success criteria are **passed** with code evidence. 1 criterion (SANITY-08+09 end-to-end rollback) is **human_needed** — the workflow invariants are asserted by 20 structural tests and manual YAML inspection, but the full rollback chain has not yet fired in a real failed deploy (and doing so would require deliberately shipping a broken commit).

---

## Success Criterion 1: Canary replays all 6 audit regressions — ✅ passed

**ROADMAP wording:** Re-running the v2 sanity gate against the pre-v7.0 production deploy state would exit non-zero with CRITICAL findings identifying: Kyler Murray roster drift, empty event_flags, 422 on /api/predictions, 422 on /api/lineups, 503 on /api/teams/{team}/roster, stalled news extractor.

**Evidence:**
- `tests/test_sanity_check_v2_canary.py::test_canary_detects_all_six_regressions` — **PASSES**
- Asserts `len(all_criticals) >= 6` with distinct CRITICALs for each regression class
- Extended in plan 68-02 (commit `863535a`) to cover drift + extractor CRITICAL freshness beyond the 4 endpoint regressions from 68-01

**Production smoke (not just fixtures):** Running `python scripts/sanity_check_projections.py --scoring half_ppr --season 2026` against real Gold data surfaces **9 CRITICALs** (7 roster drift cases including Lamar Jackson, Aaron Rodgers, Jimmy Garoppolo; 1 aggregated negative-clamp with 7 offenders; 1 missing rookie ingestion path). Exit code 1. The gate catches real drift, not just synthetic fixtures.

---

## Success Criterion 2: Live endpoint probes — ✅ passed

**ROADMAP wording:** `--check-live` probes /api/predictions, /api/lineups, /api/teams/{team}/roster for sampled top-N teams and fails on non-200 or empty-payload-when-data-expected.

**Evidence — scripts/sanity_check_projections.py (extended 1211 → 2145 lines):**
- `_probe_predictions_endpoint` — CRITICAL on HTTP 422 (lines in 68-01 SUMMARY)
- `_probe_lineups_endpoint` — CRITICAL on HTTP 422
- `_probe_team_rosters_sampled` — CRITICAL on HTTP 503, top-10 sample
- `_top_n_teams_by_snap_count` — 3-tier fallback (Silver team_metrics → Bronze snaps → hardcoded top-10)
- 5-second timeout per probe (constant `_PROBE_TIMEOUT_SECONDS`)

**Test coverage:** `tests/test_sanity_check_v2_probes.py` — 17 tests covering 200/empty/422/503/timeout/network-failure scenarios.

---

## Success Criterion 3: News content validator — ✅ passed

**ROADMAP wording:** `--check-live` validates /api/news/team-events CONTENT (total_articles > 0 for ≥N of 32 teams), not just `len == 32`.

**Evidence:**
- `_validate_team_events_content` — CRITICAL when < 17 of 32 teams have `total_articles > 0`; WARN 17-19; PASS ≥ 20
- Matches SENT-01 threshold from Phase 69 (≥ 20 of 32) so the gate enforces the Phase 69 delivery contract
- Tests in `test_sanity_check_v2_probes.py` cover empty/partial/full payloads

---

## Success Criterion 4: API key + extractor freshness assertions — ✅ passed

**ROADMAP wording:** Gate asserts `ANTHROPIC_API_KEY` is set when `ENABLE_LLM_ENRICHMENT=true`; latest Silver sentiment within 48h.

**Evidence:**
- `_assert_api_key_when_enrichment_enabled` — checks `os.environ.get("ANTHROPIC_API_KEY")` presence only; NEVER echoes value; CRITICAL message is literal string `"ANTHROPIC_API_KEY is unset"` (no partial keys)
- `_check_extractor_freshness` — CRITICAL on > 48h staleness; WARN 24-48h; PASS < 24h
- Tests cover both missing-key and enrichment-disabled-so-key-unnecessary paths

**Test evidence:** 6 tests in `test_sanity_check_v2_drift.py` covering API key + extractor freshness permutations.

---

## Success Criterion 5: GHA blocking gate + auto-rollback — ⚠ human_needed

**ROADMAP wording:** GHA deploy job invokes `--check-live` as BLOCKING; post-deploy smoke promoted to blocking with automatic rollback on failure.

**Evidence — `.github/workflows/deploy-web.yml` (179 → 297 lines):**
- Workflow-level `permissions: contents: write, actions: read` added (enables rollback push)
- `post-deploy-smoke` renamed → `live-gate-blocking` with `needs: [deploy-frontend, deploy-backend]`, no `continue-on-error`
- Runs `python scripts/sanity_check_projections.py --check-live --scoring half_ppr --season 2026`
- New `auto-rollback` job: `needs: live-gate-blocking`, `if: always() && needs.live-gate-blocking.result == 'failure'`
- 5-minute window via DEPLOY_TIMESTAMP artifact (`ELAPSED` check against 300s)
- `git revert --no-edit HEAD` + `git push origin main` (bot identity: github-actions[bot])
- Audit commit format: `revert: auto-rollback after sanity-check failure on <sha>`
- `grep "--force" .github/workflows/deploy-web.yml` returns **0 matches** — no force-push

**Structural tests:** `tests/test_deploy_workflow_v2.py` — 20 tests asserting invariants:
- `test_auto_rollback_pushes_non_force` — CRITICAL security invariant (forbids `--force` / `--force-with-lease`)
- `test_live_gate_blocking_no_continue_on_error`
- `test_auto_rollback_has_five_minute_window` (asserts `300` + `ELAPSED` present)
- `test_auto_rollback_audit_commit_message` (asserts commit format)
- `test_auto_rollback_uses_github_actions_bot`
- `test_quality_gate_records_deploy_metadata`
- + 14 more

**Why `human_needed`:** The workflow invariants are asserted, but the end-to-end "revert commit actually lands on main and Railway rolls back" pathway has not fired in production. Proving it works requires either:
1. Deliberately pushing a broken commit to trigger the live gate and observing auto-revert (hazardous in solo ops)
2. Waiting for the first real regression to test the gate naturally
3. Dry-run testing in a fork/branch with a mock Railway

**Recommendation:** Accept as `human_needed` for v7.0; monitor first real deploy failure. If the rollback fires correctly, flip to `passed` in a follow-up. If it fails, open a hotfix issue.

---

## Success Criterion 6: DQAL-03 carry-overs — ✅ passed

**ROADMAP wording:** DQAL-03 carry-overs (negative-projection clamp, 2025 rookie ingestion presence, rank-gap threshold) asserted by the sanity gate.

**Evidence:**
- `_check_dqal_negative_projection` — CRITICAL when any Gold row has `projected_points < 0`; aggregates up to 5 offenders per finding
- `_check_dqal_rookie_ingestion` — CRITICAL if `data/bronze/players/rookies/season=2025/` missing OR < 50 rookies
- `_check_dqal_rank_gap` — CRITICAL on any consecutive rank gap > 25 in latest external rankings
- Constants `_DQAL_MIN_ROOKIES=50`, `_DQAL_MAX_RANK_GAP=25` match CONTEXT.md

**Production smoke:** The gate already surfaces 2 real DQAL CRITICALs on current 2026 Gold data (7 negative-projection offenders + missing rookies path) — absorbed DQAL-03 items are now live-asserted, not deferred.

**Test coverage:** 11 tests in `test_sanity_check_v2_drift.py` covering each DQAL check's schema-healthy and regression-state fixtures.

---

## Human Verification Items

```yaml
human_verification:
  - criterion: 5
    description: "Confirm auto-rollback fires correctly on first real failed deploy"
    when: "Next time a commit breaks the live gate post-deploy"
    check: "Observe 'live-gate-blocking' fails → 'auto-rollback' job runs within 5 min → git log shows 'revert: auto-rollback after sanity-check failure on <sha>' commit → Railway redeploys previous green"
    fallback: "If rollback fails, open hotfix issue; the blocking step still blocked the bad deploy (partial SANITY-08/09 delivery)"
```

---

## Code Artifacts

| File | Change | Lines |
|------|--------|-------|
| `scripts/sanity_check_projections.py` | Extended | 1211 → 2145 (+934) |
| `.github/workflows/deploy-web.yml` | Modified | 179 → 297 (+118) |
| `tests/test_sanity_check_v2_probes.py` | NEW | 423 lines, 17 tests |
| `tests/test_sanity_check_v2_drift.py` | NEW | 508 lines, 17 tests |
| `tests/test_sanity_check_v2_canary.py` | NEW | 375 lines, 3 tests |
| `tests/test_deploy_workflow_v2.py` | NEW | 202 lines, 20 tests |

**Test suite:** 57 new tests pass in < 1 second. Broader `pytest -k sanity` shows no regressions.

---

## Phase 68 Closure Note

The v2 sanity gate is structurally complete. The meta-issue from the 2026-04-20 audit — "the gate exited 0 through all 6 regressions" — is resolved at the code layer. The only remaining verification is the live proof of auto-rollback on a real failure, which is inherently deferred to first-regression observation.

Ready to advance to Phase 69 (Sentiment Backfill).
