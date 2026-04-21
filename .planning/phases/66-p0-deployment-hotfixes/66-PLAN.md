# Phase 66: P0 Deployment Hotfixes — Plan

**Created:** 2026-04-21
**Status:** Executing inline (direct implementation per autonomous scope decision)

## Plan 66-01: Dockerfile bundles missing Bronze data + cache bust

**Requirements:** HOTFIX-02, HOTFIX-03

**Tasks:**
1. Add `COPY data/bronze/schedules/ ./data/bronze/schedules/` to `web/Dockerfile`
2. Add `COPY data/bronze/players/rosters/ ./data/bronze/players/rosters/` to `web/Dockerfile`
3. Bump `CACHE_BUST` ARG from `2026-04-19-01` → `2026-04-21-01` to force Railway re-build

**Verification:** Local `docker build web` succeeds; resulting image contains both new paths (spot-check via `docker run --rm <tag> ls -la /app/data/bronze/schedules/`).

## Plan 66-02: Backend graceful defaulting + `/api/health` LLM-ready flag

**Requirements:** HOTFIX-06, HOTFIX-01 (verification side)

**Tasks:**
1. `/api/predictions`: make `season`/`week` optional; when absent, resolve via `latest_week_service` (new or reuse) and include `meta.data_as_of`
2. `/api/lineups`: same defaulting; empty team returns list of available teams with empty `lineup: []`
3. `/api/teams/{team}/roster`: extend 64-02 offseason fallback to apply when `season`/`week` are absent (not just offseason)
4. `/api/health`: add `llm_enrichment_ready: bool(os.environ.get("ANTHROPIC_API_KEY"))` to response payload (never returns/logs the key)
5. Tests: one new test per endpoint for the no-params path; one test confirming `/api/health` reports ready flag correctly

**Verification:** `pytest tests/web/ -v` passes; manual curl against local uvicorn confirms 200+payload for no-param requests.

## Plan 66-03: Frontend latest-week resolution + nuqs binding

**Requirements:** HOTFIX-04, HOTFIX-05

**Tasks:**
1. `prediction-cards.tsx:170-171`: replace `useState(2024)` + `useState(1)` with nuqs-bound defaults resolved from `/api/projections/latest-week` via existing `resolveDefaultWeek()` helper
2. `lineup-view.tsx:20-21`: same replacement for hardcoded 2026/1
3. Both pages: fall through to Suspense skeleton while latest-week resolves
4. Lineups team filter: empty + "Select a team" CTA when team is null (preserves existing `enabled: !!team` semantics)

**Verification:** `pnpm build` in `web/frontend/` succeeds; smoke-test URLs `…/dashboard/predictions` and `…/dashboard/lineups` in browser render without manual filter manipulation.

## Plan 66-04: HOTFIX-01 user handoff

**Requirements:** HOTFIX-01

**Tasks:**
1. Document the Railway dashboard steps in VERIFICATION.md human-validation section
2. Provide post-set verification curl: `curl https://nfldataengineering-production.up.railway.app/api/health | jq .llm_enrichment_ready` should return `true`

**Verification:** human-validation item — user sets the env var; verifies flag flips on Railway.

## Execution Order

66-01 → 66-02 → 66-03 (sequential, each commits before next starts)
66-04 is a VERIFICATION.md artifact, not a code change — handled inline with verification.

## Success Criteria (from ROADMAP.md)

1. `curl /api/predictions?season=2025&week=18` returns 200 with non-empty payload
2. `curl /api/lineups?season=2025&week=18` returns 200 with well-shaped payload
3. `curl /api/teams/ARI/roster` returns 200 (not 503) with populated roster
4. Same three endpoints also return 200 with **no query string** (graceful defaulting)
5. `ANTHROPIC_API_KEY` set in Railway and reflected by `/api/health` `llm_enrichment_ready: true`
6. Predictions/lineups pages render data in the browser (no blank, no 422 in console)
