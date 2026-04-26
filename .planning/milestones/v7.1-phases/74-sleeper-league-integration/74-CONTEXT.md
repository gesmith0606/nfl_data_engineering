# Phase 74: Sleeper League Integration - Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Let users connect their Sleeper account → import rosters → get personalized advice. Username-only auth (no OAuth); cookie session; new `/dashboard/leagues` route; new advisor tool `getUserRoster`. Existing 12 advisor tools work transparently against user-scoped roster context when auth is active.
</domain>

<decisions>
## Implementation Decisions

### Auth Model
- Username-based: user enters Sleeper username → backend resolves to user_id via `https://api.sleeper.app/v1/user/{username}` → fetches leagues for current season.
- Cookie-based session: Next.js sets `sleeper_user_id` HttpOnly cookie (7-day expiry). Frontend reads via Next.js `cookies()` helper. NO server-side session DB — `user_id` IS the session.
- Multi-user persistence deferred to v8.0 (per CONTEXT carry-over).

### Backend
- New module `web/api/routers/sleeper_user.py` with:
  - `POST /api/sleeper/user/login` — accepts `{username}`, returns `{user_id, display_name, leagues: [...]}`
  - `GET /api/sleeper/leagues/{user_id}` — query param `season` (default current year), returns league list
  - `GET /api/sleeper/rosters/{league_id}` — returns rosters with `is_user_roster: bool` flag for the authenticated user
- All endpoints use `src/sleeper_http.fetch_sleeper_json` (D-01 LOCKED from Phase 73). No direct `import requests`.
- Sleeper public-API endpoints used:
  - `/v1/user/{username}` → user object (user_id, display_name, avatar)
  - `/v1/user/{user_id}/leagues/nfl/{season}` → array of leagues
  - `/v1/league/{league_id}/rosters` → array of rosters
  - `/v1/players/nfl` → cached player registry (already used by sentiment; can share)
- D-06 fail-open: any Sleeper outage returns `{"leagues": []}` or `{"rosters": []}` rather than 5xx.

### Frontend
- New route `/dashboard/leagues` — primary surface for the integration.
- Login form (Card with username input + button) on first visit; on success, cookie set → leagues list + roster display.
- League selector: dropdown or list of cards; clicking shows the user's roster (starters + bench).
- React Query caching: `leagueKeys.all/list/detail/roster` factory pattern (per `web/frontend/CLAUDE.md` conventions).
- No auth wall on other dashboard pages — Sleeper auth is opt-in. Logged-out users see "Connect your Sleeper league" CTA on the leagues page only.

### Advisor Tool
- New tool `getUserRoster({league_id})` added to the existing toolset in `web/api/services/advisor_service.py` (or wherever tools live).
- Returns `{user_id, league_id, league_name, starters: List[PlayerSlot], bench: List[Player], format: str}`.
- When SLEEP auth is active AND advisor receives a start/sit-style query, the advisor automatically calls `getUserRoster` first to ground the answer in the user's actual lineup. Tool description in the system prompt mentions this behavior.

### Claude's Discretion
- Specific UI layout for league selector (dropdown vs grid) — pick what reads best.
- Exact cookie name + size — within the auth model spec.
- Helper function names in `sleeper_user.py`.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/sleeper_http.py` — Phase 73 D-01 shared helper. ALL Sleeper HTTP calls flow through this.
- `src/config.py` — has `sleeper_players_url`, `sleeper_projections_url`. Add `sleeper_user_url`, `sleeper_leagues_url`, `sleeper_rosters_url`.
- `web/api/main.py` — register the new router.
- `web/api/services/advisor_service.py` — existing advisor toolset (find file via grep).
- `web/frontend/src/app/dashboard/` — existing pattern for new dashboard routes.
- `web/frontend/src/components/ui/` — shadcn primitives (Card, Input, Button, etc.).

### Established Patterns
- Pydantic v2 models in `web/api/models/schemas.py`.
- D-06 fail-open everywhere.
- React Query + key factories per feature.
- Bronze immutable, Silver additive (this phase touches neither — pure API + frontend).

### Integration Points
- New router registered in `web/api/main.py` (alongside news, projections, etc.).
- New advisor tool registered in advisor_service.py tool registry.
- New frontend route at `web/frontend/src/app/dashboard/leagues/page.tsx`.
- Cookie auth via Next.js `cookies()` helper from `next/headers`.

</code_context>

<specifics>
## Specific Ideas

- The `is_user_roster` flag on the rosters endpoint lets the frontend highlight the authenticated user's roster among all rosters in their league.
- League list returned from `/login` lets the user pick which league to bind to (if they're in multiple) — selection persists in another cookie or local state.
- Advisor tool surfaces both starter slots (QB, RB1, RB2, WR1, WR2, TE, FLEX, K, DEF) and bench so start/sit recommendations have the full context.

</specifics>

<deferred>
## Deferred Ideas

- OAuth flow with refresh tokens — v8.0.
- Multi-user persistent sessions (database-backed) — v8.0.
- ESPN / Yahoo league integration — future milestone (each platform has different API + auth).
- Live draft assistant integration — future milestone.
- Push notifications for roster moves — future milestone.

</deferred>
