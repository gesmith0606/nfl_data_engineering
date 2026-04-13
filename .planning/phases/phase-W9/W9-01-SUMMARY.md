---
phase: W9-draft-tool
plan: 01
subsystem: web-api
tags: [fastapi, draft, api, sessions]
dependency_graph:
  requires: [src/draft_optimizer.py, src/projection_engine.py]
  provides: [web/api/routers/draft.py, draft-api-endpoints]
  affects: [web/api/main.py, web/api/models/schemas.py]
tech_stack:
  added: []
  patterns: [in-memory-session-management, uuid-keyed-sessions, session-eviction]
key_files:
  created:
    - web/api/routers/draft.py
    - tests/test_draft_api.py
  modified:
    - web/api/models/schemas.py
    - web/api/main.py
decisions:
  - Used in-memory dict with UUID hex keys for session management (no database needed)
  - Capped sessions at 100 with oldest-eviction to mitigate DoS (T-W9-02)
  - Mocked projection data in tests to avoid nfl-data-py network dependency
metrics:
  duration: 392s
  completed: "2026-04-13T14:30:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 2
  tests_added: 17
  tests_passing: 17
---

# Phase W9 Plan 01: Draft API Backend Summary

FastAPI router with 6 endpoints wrapping draft_optimizer.py via in-memory UUID sessions, with session eviction cap and 17 passing tests.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add draft Pydantic models and create draft router with all 6 endpoints | d17fa77, 2b3c066 | web/api/routers/draft.py, web/api/models/schemas.py, web/api/main.py |
| 2 | Add draft API tests | 2b3c066 | tests/test_draft_api.py |

## Endpoints Created

| Method | Path | Purpose |
|--------|------|---------|
| GET | /api/draft/board | Get draft board (creates session if needed) |
| POST | /api/draft/pick | Record a draft pick |
| GET | /api/draft/recommendations | Get ranked pick recommendations |
| POST | /api/draft/mock/start | Initialize mock draft simulation |
| POST | /api/draft/mock/pick | Advance one pick in mock draft |
| GET | /api/draft/adp | Get latest ADP data |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed generate_preseason_projections call signature**
- **Found during:** Task 2 (test execution)
- **Issue:** Plan assumed `generate_preseason_projections(season=, scoring_format=)` but actual signature requires `seasonal_df` as first positional arg and uses `target_season=` not `season=`
- **Fix:** Added NFLDataFetcher import, call `fetch_player_seasonal()` for past 2 seasons, pass `seasonal_df` and `target_season` correctly
- **Files modified:** web/api/routers/draft.py
- **Commit:** 2b3c066

**2. [Rule 2 - Missing functionality] Added session eviction cap**
- **Found during:** Task 1 (threat model review)
- **Issue:** Threat T-W9-02 requires DoS mitigation via session cap
- **Fix:** Added `_MAX_SESSIONS = 100` with `_evict_oldest()` called before every session creation
- **Files modified:** web/api/routers/draft.py
- **Commit:** d17fa77

## Decisions Made

1. **In-memory sessions with UUID hex keys** -- Simple, no database dependency. Appropriate for single-process deployment.
2. **Mock data in tests** -- Tests use synthetic 20-player DataFrame to avoid nfl-data-py network calls. All 17 tests run in ~1s.
3. **Session eviction at 100** -- Oldest session evicted when cap reached. Prevents unbounded memory growth from projection generation.

## Known Stubs

None -- all endpoints are fully wired to draft_optimizer.py.

## Self-Check: PASSED
