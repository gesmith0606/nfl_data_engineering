---
phase: W7-sleeper-integration
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - web/api/services/sleeper_service.py
  - web/api/routers/sleeper.py
  - web/api/models/schemas.py
  - web/api/main.py
  - tests/test_sleeper_service.py
autonomous: true
requirements: [SLP-01, SLP-02, SLP-03, SLP-04, SLP-05]

must_haves:
  truths:
    - "Sleeper username lookup returns user_id and display_name"
    - "League list returns all leagues for a user with roster_positions and scoring settings"
    - "Roster endpoint returns player list with Sleeper IDs mapped to nfl-data-py player names"
    - "Waiver wire endpoint returns free agents not on any roster in the league"
    - "Matchup endpoint returns current week head-to-head matchup"
  artifacts:
    - path: "web/api/services/sleeper_service.py"
      provides: "Sleeper API client with player ID mapping"
      min_lines: 150
    - path: "web/api/routers/sleeper.py"
      provides: "5 REST endpoints for Sleeper data"
      exports: ["router"]
    - path: "tests/test_sleeper_service.py"
      provides: "Unit tests for Sleeper service"
      min_lines: 80
  key_links:
    - from: "web/api/routers/sleeper.py"
      to: "web/api/services/sleeper_service.py"
      via: "service import"
      pattern: "from.*sleeper_service.*import"
    - from: "web/api/main.py"
      to: "web/api/routers/sleeper.py"
      via: "router registration"
      pattern: "include_router.*sleeper"
---

<objective>
Build the Sleeper API backend: a service layer that wraps Sleeper's public REST API
(https://api.sleeper.app/v1/...) and exposes 5 FastAPI endpoints for user lookup,
league listing, roster retrieval with player ID mapping, matchup data, and waiver wire
(free agent) discovery.

Purpose: Backend foundation for the Sleeper integration. All frontend and AI advisor
features depend on these endpoints existing.

Output: `sleeper_service.py` (client + ID mapping), `sleeper.py` (router), updated
`main.py`, tests.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md

@web/api/main.py
@web/api/routers/draft.py
@web/api/services/projection_service.py
@web/api/models/schemas.py

<interfaces>
<!-- Existing router pattern from draft.py -->
```python
from fastapi import APIRouter, HTTPException, Query
router = APIRouter(prefix="/draft", tags=["draft"])
```

<!-- Existing service pattern from projection_service.py -->
```python
# Services are plain Python modules with async/sync functions
# Routers import and call service functions
```

<!-- main.py router registration pattern -->
```python
from .routers import draft, games, lineups, news, players, predictions, projections
app.include_router(draft.router, prefix="/api")
```

<!-- Sleeper public API (no auth required):
GET https://api.sleeper.app/v1/user/{username}
  -> {user_id, username, display_name, avatar}

GET https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{season}
  -> [{league_id, name, roster_positions, scoring_settings, total_rosters, ...}]

GET https://api.sleeper.app/v1/league/{league_id}/rosters
  -> [{roster_id, owner_id, players: ["4046", "6813", ...], starters: [...]}]

GET https://api.sleeper.app/v1/league/{league_id}/matchups/{week}
  -> [{roster_id, matchup_id, players: [...], starters: [...], points: N}]

GET https://api.sleeper.app/v1/players/nfl
  -> {player_id: {full_name, position, team, search_full_name, ...}} (large ~30MB)
-->
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Sleeper service with player ID mapping</name>
  <files>web/api/services/sleeper_service.py, tests/test_sleeper_service.py</files>
  <behavior>
    - Test: lookup_user("testuser") returns SleeperUser with user_id and display_name
    - Test: get_leagues(user_id, season) returns list of SleeperLeague objects
    - Test: get_roster(league_id, user_id) returns list of SleeperRosterPlayer with mapped player_name
    - Test: get_matchup(league_id, week, user_id) returns SleeperMatchup with opponent
    - Test: get_free_agents(league_id) returns players not on any roster
    - Test: player ID mapping loads Sleeper player registry and maps ID to name+position+team
    - Test: mapping cache avoids re-fetching the 30MB player registry on every call
  </behavior>
  <action>
Create `web/api/services/sleeper_service.py` with:

1. **Data classes** (use dataclasses, not Pydantic here since this is the service layer):
   - `SleeperUser(user_id, username, display_name, avatar)`
   - `SleeperLeague(league_id, name, season, total_rosters, roster_positions, scoring_settings)`
   - `SleeperRosterPlayer(sleeper_id, player_name, position, team, is_starter)`
   - `SleeperMatchup(week, user_roster, opponent_roster, user_points, opponent_points)`

2. **Player ID mapping** (`_SleeperPlayerMap` class):
   - Fetch `https://api.sleeper.app/v1/players/nfl` once, cache in module-level variable with TTL of 24 hours
   - Build dict: `{sleeper_id: {full_name, position, team}}`
   - Method `map_ids(sleeper_ids: list[str]) -> list[SleeperRosterPlayer]`
   - Use `full_name` field from Sleeper data (most reliable for matching)

3. **Service functions** (all use `httpx` for HTTP calls):
   - `async def lookup_user(username: str) -> SleeperUser`
   - `async def get_leagues(user_id: str, season: int = 2026) -> list[SleeperLeague]`
   - `async def get_roster(league_id: str, user_id: str) -> list[SleeperRosterPlayer]`
     - Fetches all rosters, finds the one where `owner_id == user_id`
     - Maps player IDs using the player map
     - Marks starters vs bench using `starters` list
   - `async def get_matchup(league_id: str, week: int, user_id: str) -> SleeperMatchup`
     - Fetches rosters to find user's `roster_id`
     - Fetches matchups for that week
     - Finds user's matchup and opponent by matching `matchup_id`
   - `async def get_free_agents(league_id: str, top_n: int = 50) -> list[SleeperRosterPlayer]`
     - Fetches all rosters, collects all rostered player IDs
     - Gets full player map, filters to active NFL players not on any roster
     - Returns top_n by position (QB/RB/WR/TE only)

Use `httpx.AsyncClient` with a 10-second timeout. Handle 404 (user not found) and 429 (rate limit) gracefully with clear error messages.

For tests, mock httpx calls with sample Sleeper API responses. Do NOT call the real Sleeper API in tests.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python -m pytest tests/test_sleeper_service.py -v</automated>
  </verify>
  <done>
    - SleeperService handles all 5 Sleeper API calls with proper error handling
    - Player ID mapping caches the registry with 24h TTL
    - All service functions return typed dataclass objects
    - Tests pass with mocked HTTP responses
  </done>
</task>

<task type="auto">
  <name>Task 2: FastAPI router + schema + main.py registration</name>
  <files>web/api/routers/sleeper.py, web/api/models/schemas.py, web/api/main.py</files>
  <action>
1. **Add Pydantic schemas** to `web/api/models/schemas.py` (append to existing file):
   - `SleeperUserResponse(user_id: str, username: str, display_name: str, avatar: str | None)`
   - `SleeperLeagueResponse(league_id: str, name: str, season: int, total_rosters: int, roster_positions: list[str], scoring_type: str)`
   - `SleeperLeaguesResponse(leagues: list[SleeperLeagueResponse])`
   - `SleeperPlayerResponse(sleeper_id: str, player_name: str, position: str, team: str | None, is_starter: bool, projected_points: float | None = None)`
   - `SleeperRosterResponse(players: list[SleeperPlayerResponse], league_id: str, user_id: str)`
   - `SleeperMatchupResponse(week: int, user_players: list[SleeperPlayerResponse], opponent_players: list[SleeperPlayerResponse], user_points: float | None, opponent_points: float | None)`
   - `SleeperFreeAgentsResponse(players: list[SleeperPlayerResponse], league_id: str)`

2. **Create router** `web/api/routers/sleeper.py`:
   ```
   router = APIRouter(prefix="/sleeper", tags=["sleeper"])
   ```

   Endpoints:
   - `GET /sleeper/user/{username}` -> `SleeperUserResponse`
     - Calls `sleeper_service.lookup_user(username)`
     - 404 if user not found
   - `GET /sleeper/leagues/{user_id}` -> `SleeperLeaguesResponse`
     - Query param: `season: int = 2026`
     - Calls `sleeper_service.get_leagues(user_id, season)`
   - `GET /sleeper/roster/{league_id}/{user_id}` -> `SleeperRosterResponse`
     - Calls `sleeper_service.get_roster(league_id, user_id)`
     - Enriches each player with `projected_points` by name-matching against
       the projection data (call `projection_service` or load from Gold parquet).
       If no match, leave `projected_points` as None.
   - `GET /sleeper/matchup/{league_id}/{week}` -> `SleeperMatchupResponse`
     - Query param: `user_id: str`
     - Calls `sleeper_service.get_matchup(league_id, week, user_id)`
   - `GET /sleeper/free-agents/{league_id}` -> `SleeperFreeAgentsResponse`
     - Query param: `top_n: int = 50`
     - Calls `sleeper_service.get_free_agents(league_id, top_n)`
     - Enriches with projected_points where available

3. **Register in main.py**: Add `sleeper` to the routers import and `app.include_router(sleeper.router, prefix="/api")` following the existing pattern.

Handle all errors with appropriate HTTP status codes (404 for not found, 502 for upstream Sleeper API failures, 429 for rate limits).
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python -c "from web.api.routers.sleeper import router; print(f'Router loaded: {len(router.routes)} routes')" && python -m pytest tests/ -k "sleeper" -v</automated>
  </verify>
  <done>
    - 5 endpoints registered under /api/sleeper/*
    - Roster and free-agent endpoints enrich with projected_points
    - main.py includes the sleeper router
    - All endpoints return proper Pydantic response models
    - Error handling returns 404/502/429 as appropriate
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client -> FastAPI | Untrusted username/IDs from frontend |
| FastAPI -> Sleeper API | External API, may be slow/down/rate-limited |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-W7-01 | Spoofing | /sleeper/user/{username} | accept | Sleeper data is public; no auth needed, no PII beyond display name |
| T-W7-02 | DoS | /sleeper/roster/* | mitigate | Cache player registry with 24h TTL; add 10s timeout on upstream calls |
| T-W7-03 | Info Disclosure | Player map cache | accept | Player names/teams are public NFL data, no secrets |
| T-W7-04 | Tampering | Sleeper API responses | accept | Read-only integration; no writes to Sleeper |
</threat_model>

<verification>
1. `curl http://localhost:8000/api/sleeper/user/testuser` returns user_id
2. `curl http://localhost:8000/api/sleeper/leagues/{user_id}?season=2026` returns league list
3. `curl http://localhost:8000/api/sleeper/roster/{league_id}/{user_id}` returns players with projected_points
4. `curl http://localhost:8000/api/sleeper/free-agents/{league_id}` returns available players
5. All existing tests still pass
</verification>

<success_criteria>
- 5 Sleeper endpoints operational and returning structured JSON
- Player ID mapping resolves Sleeper IDs to player names
- Roster endpoint enriches with projection data
- httpx dependency added to requirements
- Tests pass
</success_criteria>

<output>
After completion, create `.planning/phases/phase-W7/W7-01-SUMMARY.md`
</output>
