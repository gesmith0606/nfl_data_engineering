---
phase: 79-audit-provenance-version-probe
plan: 03
subsystem: api
tags: [fastapi, pydantic, version-probe, deploy-hardening, provenance]

# Dependency graph
requires:
  - phase: 66-p0-deployment-hotfixes
    provides: Original /api/version endpoint + has_team_events_route / has_player_badges_route diagnostic flags
provides:
  - "GET /api/version returns 7-key VersionResponse shape with FULL 40-character RAILWAY_GIT_COMMIT_SHA"
  - "llm_enrichment_ready: bool field mirroring /api/health logic (ANTHROPIC_API_KEY presence as bool)"
  - "VersionResponse pydantic model registered in OpenAPI schema for typed Phase 84 consumption"
  - "TestVersion test class (4 tests) locking shape, full-SHA, env-fallback, and key-leak guards"
affects:
  - 84-deploy-hardening (DEPLOY-02 polls /api/version asserting git_sha == GITHUB_SHA)
  - 79-04-version-probe-smoke-step (CI workflow consumer)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pydantic response_model on health-tagged endpoints for OpenAPI typing"
    - "Bool-only secret presence reporting (never the value, never a prefix)"
    - "monkeypatch-driven env-var tests for env-dependent endpoints"

key-files:
  created: []
  modified:
    - "web/api/main.py (version_info() upgraded to 7-key VersionResponse, [:8] truncation removed)"
    - "web/api/models/schemas.py (added VersionResponse pydantic model after HealthResponse)"
    - "tests/test_web_api.py (added TestVersion class with 4 contract tests)"

key-decisions:
  - "Drop [:8] truncation from BOTH git_sha AND build_id (D-04 generalized to deployment ID)"
  - "Mirror /api/health bool(os.environ.get('ANTHROPIC_API_KEY')) pattern verbatim -- single source of truth for LLM-readiness probe"
  - "Add response_model=VersionResponse to register the schema in OpenAPI for typed Phase 84 client"
  - "Test 4 includes literal `secret not in resp.text` assertion as T-79-08 information-disclosure regression guard"

patterns-established:
  - "Probe endpoint contract: pydantic response_model + dedicated TestX class with shape assertion"
  - "Secret presence reporting: bool(env.get(KEY)) -- never expose value, prefix, or length"

requirements-completed: [DQ-02]

# Metrics
duration: 3min
completed: 2026-04-28
---

# Phase 79 Plan 03: /api/version Upgrade Summary

**GET /api/version returns 7-key VersionResponse with full 40-char RAILWAY_GIT_COMMIT_SHA and llm_enrichment_ready bool, ready for Phase 84 DEPLOY-02 asymmetry probe.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-28T02:08:43Z
- **Completed:** 2026-04-28T02:11:42Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- `/api/version` now returns the full 40-character `RAILWAY_GIT_COMMIT_SHA` (was `[:8]` truncated). Phase 84's asymmetry probe can do clean equality vs `${{ github.sha }}`.
- `RAILWAY_DEPLOYMENT_ID` truncation also removed for consistency (full ID returned).
- New `llm_enrichment_ready: bool` field mirrors `/api/health` logic exactly: `bool(os.environ.get("ANTHROPIC_API_KEY"))`. Key value is never returned or logged — bool only.
- Existing diagnostic flags (`has_team_events_route`, `has_player_badges_route`) preserved unchanged.
- `VersionResponse` pydantic model registered in OpenAPI schema (`/api/openapi.json` includes `components.schemas.VersionResponse`) for typed Phase 84 consumption.
- 4 TestVersion contract tests pass; full `tests/test_web_api.py` suite (21 tests) green.

## Task Commits

Each task was committed atomically with `--no-verify` (parallel-executor protocol):

1. **Task 1: Add VersionResponse pydantic model** - `ac3ff1d` (feat)
2. **Task 2: Upgrade /api/version endpoint** - `70c2c5c` (feat)
3. **Task 3: Add TestVersion class with 4 contract tests** - `af254a7` (test)

## Files Created/Modified

- `web/api/models/schemas.py` — Added `VersionResponse(BaseModel)` after `HealthResponse` with seven `Field(...)`-described fields. HealthResponse left untouched.
- `web/api/main.py` — Imported `VersionResponse`, replaced `version_info()` body. New endpoint sets `response_model=VersionResponse`, returns full SHA, full deployment ID, `llm_enrichment_ready` bool, and the two preserved diagnostic flags.
- `tests/test_web_api.py` — Added `class TestVersion` after `TestHealth` with 4 tests: shape (7 keys), full-40-char SHA, env-unset fallback to `'unknown'`, and llm_enrichment_ready bool toggle + secret-leak regression guard.

## Decisions Made

- Used `monkeypatch` (not direct `os.environ` manipulation) in tests so env state cannot leak across tests.
- The two diagnostic route flags continue to use the existing path-matching predicates (`getattr(r, "path", "") == "/team-events"` and `"player-badges" in getattr(r, "path", "")`). Per plan: "preserved unchanged." The current TestClient run shows these resolve to `False` and `True` respectively because the news router prefixes routes with `/news/...`; this is the existing v7.0/v7.1 behavior and is not in scope for Phase 79 to repair.

## Deviations from Plan

None — plan executed exactly as written. The action text in Tasks 1, 2, 3 was followed verbatim, and all stated `<verify>` commands and `<acceptance_criteria>` were exercised and passed.

## Verification Run-Through

| Acceptance Item | Result |
|-----------------|--------|
| `from web.api.models.schemas import VersionResponse` works | PASS |
| `VersionResponse.model_fields` set equals the 7 expected names | PASS (build_id, deployed_at, git_sha, has_player_badges_route, has_team_events_route, llm_enrichment_ready, version) |
| `client.get("/api/version")` returns 200 with exactly 7 keys | PASS (TestVersion.test_version_shape_has_seven_keys) |
| `git_sha` length is 40 when env set | PASS (TestVersion.test_git_sha_is_full_40_chars_when_env_set) |
| `git_sha == "unknown"` when env unset | PASS (TestVersion.test_git_sha_is_unknown_when_env_unset) |
| `llm_enrichment_ready == bool(os.environ.get("ANTHROPIC_API_KEY"))` and key never appears in response | PASS (TestVersion.test_llm_enrichment_ready_reflects_anthropic_key_bool_only — `assert secret not in resp.text` succeeds) |
| `[:8]` slice removed from git_sha + build_id | PASS (`grep -n "RAILWAY_GIT_COMMIT_SHA" web/api/main.py` shows no `[:8]` after env-var read) |
| /api/health response shape unchanged | PASS (TestHealth.test_health_returns_ok still passes) |
| `VersionResponse` appears in `/api/openapi.json` `components.schemas` | PASS |
| All 4 TestVersion tests pass | PASS |
| `pytest tests/test_web_api.py` full suite | PASS — 21 passed in 1.16s |

## ANTHROPIC_API_KEY Leak Guard Outcome

`test_llm_enrichment_ready_reflects_anthropic_key_bool_only` sets `ANTHROPIC_API_KEY="sk-ant-VERY-SECRET-VALUE-NEVER-LEAK"`, makes a real HTTP call against the FastAPI app, and asserts `secret not in resp.text`. Test PASSES. The endpoint reads the key only via `bool(os.environ.get("ANTHROPIC_API_KEY"))` and returns the bool — the value never traverses the response or any log statement. T-79-08 mitigation confirmed.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. The endpoint reads existing Railway env vars (`RAILWAY_GIT_COMMIT_SHA`, `RAILWAY_DEPLOYMENT_ID`, `RAILWAY_GIT_COMMIT_TIMESTAMP`, `ANTHROPIC_API_KEY`) which are already provisioned per v7.0 deploy.

## Next Phase Readiness

- Phase 79-04 (version-probe smoke step) can now consume `/api/version` and assert `git_sha == GITHUB_SHA` — the producer contract is locked by `VersionResponse` + `TestVersion`.
- Phase 84 DEPLOY-02 (promote smoke check from warn-only to fail-on-mismatch) inherits the same shape; the 7-key `VersionResponse` model serves as the typed client contract.
- `llm_enrichment_ready` flag now exposed on /api/version as well as /api/health — Phase 84 / future probes can check LLM-readiness from either endpoint, but the value is bool-only.

## Self-Check: PASSED

- Files exist:
  - `web/api/main.py` — FOUND
  - `web/api/models/schemas.py` — FOUND
  - `tests/test_web_api.py` — FOUND
- Commits exist on `worktree-agent-afcf562b`:
  - `ac3ff1d` (Task 1) — FOUND
  - `70c2c5c` (Task 2) — FOUND
  - `af254a7` (Task 3) — FOUND

---
*Phase: 79-audit-provenance-version-probe*
*Plan: 03 — api-version-upgrade*
*Completed: 2026-04-28*
