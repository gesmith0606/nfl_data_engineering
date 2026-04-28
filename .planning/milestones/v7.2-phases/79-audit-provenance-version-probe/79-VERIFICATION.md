---
phase: 79-audit-provenance-version-probe
verified: 2026-04-28T22:03:30Z
status: passed
score: 9/9 must-haves verified
requirement_ids: [DQ-01, DQ-02]
verified_count: 9
total_count: 9
overrides_applied: 0
---

# Phase 79: Audit Provenance + Version Probe Verification Report

**Phase Goal:** Every audit-JSON artifact and every running deploy can be traced to the exact code commit that produced it; the live deploy gate can no longer pass against a stale image.

**Verified:** 2026-04-28T22:03:30Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Success Criterion 1: Audit-script JSON outputs include script_sha

**Status: PASS**

All three audit scripts import `get_script_sha` from `src.utils` and embed the return value under the top-level `script_provenance` key in their JSON payloads. Verified by calling the payload builders directly against the live code:

- `audit_event_coverage._build_json_payload(...)` returns keys `['audited_at', 'script_provenance', 'base_url', 'season', 'weeks', 'gate', 'teams_with_events', 'passed', 'per_team']` — confirmed `script_provenance` present with `{sha, dirty, resolved_at}` shape.
- `audit_advisor_tools_evt05._build_payload(...)` returns keys `['audited_at', 'script_provenance', 'base_url', ...]` — confirmed.
- `audit_advisor_tools.write_audit_json(...)` writes a JSON file with `script_provenance` at the top level — confirmed.
- All five `test_audit_script_provenance.py` tests pass (3 payload-builder tests + 2 D-08 forward-only tests).

The `get_script_sha` helper in `src/utils.py` itself: returns a 40-char hex SHA (`ce6f25f89016154e7e2e801fd42e291cd1b18a29`) and `dirty=False` on a clean tracked file; uses `shell=False` and `--` separator on both subprocess invocations; degrades gracefully to `sha='unknown'` for untracked/missing paths. All 6 `test_get_script_sha.py` tests pass.

---

### Success Criterion 2: Railway exposes /api/version returning {git_sha, deployed_at, llm_enrichment_ready}

**Status: PASS**

`GET /api/version` returns HTTP 200 with exactly 7 keys: `{version, git_sha, build_id, deployed_at, llm_enrichment_ready, has_team_events_route, has_player_badges_route}`. Verified by FastAPI TestClient against the live app module.

Key semantics confirmed:
- `git_sha` is the full 40-char `RAILWAY_GIT_COMMIT_SHA` env var value — no `[:8]` truncation. Grep of `web/api/main.py` shows no `[:8]` slice on `RAILWAY_GIT_COMMIT_SHA`.
- When env var unset, `git_sha` returns the literal string `"unknown"`.
- `llm_enrichment_ready` is `bool(os.environ.get("ANTHROPIC_API_KEY"))` — mirrors `/api/health` logic. The API key value never appears in the response body (confirmed by `test_llm_enrichment_ready_reflects_anthropic_key_bool_only`).
- `VersionResponse` pydantic model in `web/api/models/schemas.py` defines the 7-field contract; `version_info()` in `web/api/main.py` returns this model.
- All 4 `tests/test_web_api.py::TestVersion` tests pass.

---

### Success Criterion 3: Asymmetry-detection capability (warn-only probe in deploy-web.yml)

**Status: PASS**

The smoke step `Probe Railway /api/version for SHA match` is present in the `deploy-backend` job of `.github/workflows/deploy-web.yml`, positioned AFTER the 120s redeploy wait step (index 1 of 2 steps in the job). YAML parse + positional check confirmed via Python.

Properties verified:
- `continue-on-error: true` — warn-only per D-07; does not block deploys at this stage.
- `EXPECTED_SHA: ${{ github.sha }}` — wired to the 40-char commit SHA of the push that triggered the workflow.
- `BUDGET_SECONDS=300` — 5-minute polling budget per D-07.
- `POLL_INTERVAL=15` — 15-second interval.
- Uses `jq -r '.git_sha'` to extract the full SHA and compare to `${EXPECTED_SHA}`.
- Timeout branch emits `::warning::` with structured context (expected SHA, last-seen SHA, HTTP status, attempt count).
- Match branch emits `::notice::`.
- `X-API-Key` header sent when `secrets.RAILWAY_API_KEY` is set; step degrades to unauthenticated polling otherwise.
- Step lives exclusively in `deploy-backend`; `live-gate-blocking` job is unmodified.
- Phase 84 DEPLOY-02 promotion path documented in step comments (remove `continue-on-error: true`, flip timeout branch to `::error:: + exit 1`).

The asymmetry-detection capability is present. Per the task specification, success criterion 3 is the capability ("proves the asymmetry-detection capability"), not a live production curl result — which requires a Railway push outside CI scope. The warn-only probe satisfies the Phase 79 bar; Phase 84 promotes it to fail-on-mismatch.

---

## Observable Truths

| # | Truth | Plan | Status | Evidence |
|---|-------|------|--------|----------|
| 1 | `src.utils` exports `get_script_sha(script_path)` returning `{sha, dirty, resolved_at}` | 79-01 | VERIFIED | `get_script_sha('src/utils.py')` returns `{'sha': '...40chars...', 'dirty': False, 'resolved_at': '...'}` |
| 2 | Clean tracked file returns 40-char SHA and `dirty=False` | 79-01 | VERIFIED | Live call returns 40-char hex SHA, `dirty=False` |
| 3 | Helper uses `shell=False` and `--` separator (no shell injection) | 79-01 | VERIFIED | Lines 309 and 327 of `src/utils.py` confirm `shell=False`; both subprocess calls pass path after `--` |
| 4 | `audit_event_coverage.py` JSON output contains top-level `script_provenance` | 79-02 | VERIFIED | `_build_json_payload(...)` includes key; 5 tests pass |
| 5 | `audit_advisor_tools_evt05.py` JSON output contains top-level `script_provenance` | 79-02 | VERIFIED | `_build_payload(...)` includes key; tests pass |
| 6 | `audit_advisor_tools.py` emits `TOOL-AUDIT.json` sidecar with `script_provenance` | 79-02 | VERIFIED | `write_audit_json(...)` writes JSON with `script_provenance`; wired into `main()` via `args.output.with_suffix(".json")` |
| 7 | `GET /api/version` returns 7-key shape with full SHA and `llm_enrichment_ready` | 79-03 | VERIFIED | TestClient confirms 200, exact key set, 40-char SHA, bool-only API key exposure |
| 8 | Smoke step in `deploy-web.yml` polls `/api/version` for SHA match, warn-only | 79-04 | VERIFIED | Step present at index 1 in `deploy-backend`; `continue-on-error: true`; 300s budget; `EXPECTED_SHA: ${{ github.sha }}` |
| 9 | Historical v7.1 audit JSONs not backfilled (D-08 forward-only) | 79-02 | VERIFIED | Both parametrised D-08 tests pass; files lack `script_provenance` |

**Score: 9/9 truths verified**

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/utils.py` | `get_script_sha()` helper with 3-key return dict | VERIFIED | Function at line 269; `shell=False` on both subprocess calls; graceful degradation for untracked/missing paths |
| `tests/test_get_script_sha.py` | 6 pytest tests | VERIFIED | 6 tests collected and passing |
| `scripts/audit_event_coverage.py` | Imports `get_script_sha`; `_build_json_payload` embeds `script_provenance` | VERIFIED | Import at line 46; `script_provenance` in return dict at line 195 |
| `scripts/audit_advisor_tools_evt05.py` | Imports `get_script_sha`; `_build_payload` embeds `script_provenance` | VERIFIED | Import at line 48; `script_provenance` in return dict at line 164 |
| `scripts/audit_advisor_tools.py` | Imports `get_script_sha`; `write_audit_json` function; `main()` wires JSON sidecar | VERIFIED | Import at line 42; `write_audit_json` at line 561; `main()` calls at line 681 |
| `tests/test_audit_script_provenance.py` | 5 tests (3 payload + 2 D-08) | VERIFIED | All 5 pass |
| `web/api/models/schemas.py` | `VersionResponse` pydantic model with 7 typed fields | VERIFIED | `class VersionResponse` at line 345 |
| `web/api/main.py` | `version_info()` returns `VersionResponse` with full SHA, no `[:8]` truncation | VERIFIED | No `[:8]` in `version_info()`; `RAILWAY_GIT_COMMIT_SHA` read without truncation |
| `tests/test_web_api.py` | `TestVersion` class with 4 tests | VERIFIED | 4 tests pass |
| `.github/workflows/deploy-web.yml` | Smoke step in `deploy-backend`, warn-only, 5-min budget | VERIFIED | Step at position 1 of 2; `continue-on-error: true`; `BUDGET_SECONDS=300` |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/utils.py::get_script_sha` | `git log -1 --format=%H -- {path}` | `subprocess.run(["git", ...], shell=False)` | WIRED | Line 307-314 |
| `src/utils.py::get_script_sha` | `git diff HEAD -- {path}` | `subprocess.run(["git", "diff", ...], shell=False)` | WIRED | Line 325-332 |
| `scripts/audit_event_coverage.py::_build_json_payload` | `src/utils.py::get_script_sha` | `"script_provenance": get_script_sha(__file__)` | WIRED | Line 195 |
| `scripts/audit_advisor_tools_evt05.py::_build_payload` | `src/utils.py::get_script_sha` | `"script_provenance": get_script_sha(__file__)` | WIRED | Line 164 |
| `scripts/audit_advisor_tools.py::write_audit_json` | `src/utils.py::get_script_sha` | `"script_provenance": get_script_sha(__file__)` | WIRED | Line 586 |
| `scripts/audit_advisor_tools.py::main` | `TOOL-AUDIT.json` sidecar | `args.output.with_suffix(".json")` | WIRED | Line 680-688 |
| `web/api/main.py::version_info` | `RAILWAY_GIT_COMMIT_SHA` env var | `os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown")` (no truncation) | WIRED | Line 135 |
| `web/api/main.py::version_info` | `ANTHROPIC_API_KEY` (bool only) | `bool(os.environ.get("ANTHROPIC_API_KEY"))` | WIRED | Line 132; key value never in response |
| `.github/workflows/deploy-web.yml::deploy-backend` | `Railway /api/version` | `curl` polling loop with `jq -r '.git_sha'` | WIRED | Lines 185-228 |
| `${{ github.sha }}` context | smoke step `EXPECTED_SHA` | `EXPECTED_SHA: ${{ github.sha }}` | WIRED | Line 183 |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `get_script_sha` returns correct shape | `python -c "from src.utils import get_script_sha; r = get_script_sha('src/utils.py'); assert set(r.keys()) == {'sha', 'dirty', 'resolved_at'}"` | SHA `ce6f25f...` (40 chars), `dirty=False` | PASS |
| `audit_event_coverage` payload builder embeds provenance | `python -c "import scripts.audit_event_coverage as m; p = m._build_json_payload(...); assert 'script_provenance' in p"` | `script_provenance` present with correct shape | PASS |
| `audit_advisor_tools_evt05` payload builder embeds provenance | Same pattern | `script_provenance` present | PASS |
| `audit_advisor_tools` JSON sidecar function embeds provenance | `write_audit_json(...)` writes JSON | `script_provenance` in output | PASS |
| `/api/version` returns 7-key shape with full SHA | TestClient GET `/api/version` with 40-char SHA env | 200, 7 keys, `len(git_sha)==40` | PASS |
| `/api/version` never leaks ANTHROPIC_API_KEY value | TestClient with secret set | `llm_enrichment_ready=True`, secret absent from `resp.text` | PASS |
| Smoke step YAML valid and correctly positioned | `yaml.safe_load` + index check | Step at index 1, `continue-on-error: true`, `BUDGET_SECONDS=300` | PASS |
| All 15 new tests pass | `pytest tests/test_get_script_sha.py tests/test_audit_script_provenance.py tests/test_web_api.py::TestVersion` | 6 + 5 + 4 = 15 tests, all pass | PASS |

---

## Requirements Coverage

| Requirement | Description | Plans | Status | Evidence |
|-------------|-------------|-------|--------|----------|
| DQ-01 | Audit-script JSON outputs capture `script_sha` of the audit script at execution time | 79-01, 79-02 | SATISFIED | `get_script_sha()` helper in `src/utils.py`; all three audit scripts embed `script_provenance: {sha, dirty, resolved_at}` in JSON output; 11 tests verify the contract |
| DQ-02 | Railway exposes `/api/version` returning `{git_sha, deployed_at, llm_enrichment_ready}` so the live gate can assert the running image matches the just-pushed commit | 79-03, 79-04 | SATISFIED | `VersionResponse` model with 7 fields in `schemas.py`; `version_info()` endpoint in `main.py` returns full SHA without truncation; smoke step in `deploy-web.yml` polls and detects asymmetry (warn-only); 4 tests verify endpoint contract |

No orphaned requirements. Both DQ-01 and DQ-02 are fully satisfied. DQ-03 (sanity warning triage) is assigned to Phase 80 and is not in scope for Phase 79.

---

## Anti-Patterns Found

No blockers or warnings found.

- No `TODO`, `FIXME`, or placeholder comments in modified files (`src/utils.py`, the three audit scripts, `web/api/main.py`, `web/api/models/schemas.py`, `.github/workflows/deploy-web.yml`).
- No empty implementations or hardcoded-empty return values.
- `shell=False` enforced on all subprocess calls in `get_script_sha`.
- ANTHROPIC_API_KEY value is never surfaced in `/api/version` response (leak-guard test passes).
- D-08 forward-only invariant holds: v7.1 historical audit JSONs (`event_coverage.json`, `advisor_tools_72.json`) do not contain `script_provenance` and were not modified in place.

---

## Human Verification Required

One item is observable only in a live Railway environment:

**Post-push SHA round-trip**

- Test: Push a commit to `main`, wait for `deploy-web.yml` to complete, observe the `Probe Railway /api/version for SHA match` step in the Actions log.
- Expected: Step emits `::notice title=Railway /api/version SHA match::git_sha=<commit-sha>` within 300 seconds; the displayed SHA matches the `GITHUB_SHA` of the push.
- Why human: Requires a live Railway deployment and a real push to `main`. Cannot be tested via TestClient or YAML parse. The CI smoke step is warn-only (Phase 79 D-07), so a mismatch will surface as a `::warning::` annotation rather than a workflow failure — the operator must check the Actions run page after the first post-Phase-79 push.

This item does not affect the phase status. The asymmetry-detection capability is fully implemented in code; the live round-trip is a production smoke-test that Phase 84 will promote to a hard gate.

---

## Final Verdict

Phase 79 goal is achieved. Every element of the forensic traceability contract is implemented and tested:

1. `get_script_sha()` is a working, shell-injection-safe, gracefully-degrading helper that returns `{sha, dirty, resolved_at}` for any script path.
2. All three current audit scripts (`audit_event_coverage.py`, `audit_advisor_tools_evt05.py`, `audit_advisor_tools.py`) embed `script_provenance` in their JSON output. The D-08 forward-only constraint is enforced — historical v7.1 audit JSONs are untouched.
3. `GET /api/version` returns a 7-key pydantic-validated response with the full 40-char Railway git SHA, a `llm_enrichment_ready` bool that never leaks the underlying key, and the two diagnostic route flags from Phase 66.
4. The `deploy-backend` job in `deploy-web.yml` contains a warn-only smoke step that polls `/api/version` and detects Railway-vs-GitHub SHA asymmetry within a 5-minute budget, with clear `::notice::` / `::warning::` annotations. Phase 84 DEPLOY-02 can promote this to fail-on-mismatch by removing `continue-on-error: true`.
5. 15 new tests cover the complete contract. All pass.

The 3-week silent-freeze failure mode that v7.1 experienced can now be detected on every push.

---

_Verified: 2026-04-28T22:03:30Z_
_Verifier: Claude (gsd-verifier)_
