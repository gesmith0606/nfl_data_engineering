---
phase: W7-sleeper-integration
plan: 02
type: execute
wave: 2
depends_on: [W7-01]
files_modified:
  - web/frontend/src/lib/nfl/types.ts
  - web/frontend/src/lib/nfl/api.ts
  - web/frontend/src/features/nfl/components/sleeper-connect.tsx
  - web/frontend/src/features/nfl/components/my-roster.tsx
  - web/frontend/src/features/nfl/components/waiver-suggestions.tsx
  - web/frontend/src/app/dashboard/my-team/page.tsx
autonomous: false
requirements: [SLP-06, SLP-07, SLP-08, SLP-09, SLP-10]

must_haves:
  truths:
    - "User can enter their Sleeper username and see their leagues"
    - "User can select a league and see their roster with projected points"
    - "User can see start/sit recommendations highlighted on their roster"
    - "User can see waiver wire suggestions for available players"
    - "League context persists in localStorage across page reloads"
  artifacts:
    - path: "web/frontend/src/features/nfl/components/sleeper-connect.tsx"
      provides: "Username input + league selection flow"
      min_lines: 80
    - path: "web/frontend/src/features/nfl/components/my-roster.tsx"
      provides: "Roster display with start/sit highlighting"
      min_lines: 100
    - path: "web/frontend/src/features/nfl/components/waiver-suggestions.tsx"
      provides: "Top available free agents table"
      min_lines: 60
    - path: "web/frontend/src/app/dashboard/my-team/page.tsx"
      provides: "My Team dashboard page"
      min_lines: 50
  key_links:
    - from: "web/frontend/src/features/nfl/components/sleeper-connect.tsx"
      to: "/api/sleeper/user/{username}"
      via: "fetch via nfl/api service"
      pattern: "fetchSleeperUser"
    - from: "web/frontend/src/features/nfl/components/my-roster.tsx"
      to: "/api/sleeper/roster/{league_id}/{user_id}"
      via: "fetch via nfl/api service"
      pattern: "fetchSleeperRoster"
    - from: "web/frontend/src/app/dashboard/my-team/page.tsx"
      to: "sleeper-connect.tsx"
      via: "component composition"
      pattern: "SleeperConnect|MyRoster"
---

<objective>
Build the frontend for Sleeper league integration: a "Connect League" flow where users
enter their Sleeper username, pick a league, and see their roster with projected points,
start/sit recommendations, and waiver wire suggestions. League context stored in
localStorage (no auth needed).

Purpose: The main user-facing value — see YOUR team's projections and get personalized advice.

Output: My Team page at `/dashboard/my-team`, connect flow component, roster display,
waiver suggestions, updated API/types layer.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/phase-W7/W7-01-SUMMARY.md

@web/frontend/src/lib/nfl/types.ts
@web/frontend/src/lib/nfl/api.ts
@web/frontend/src/features/nfl/api/service.ts
@web/frontend/src/features/nfl/api/types.ts
@web/frontend/src/app/dashboard/layout.tsx
@web/frontend/src/app/dashboard/projections/page.tsx
@web/frontend/CLAUDE.md

<interfaces>
<!-- From W7-01: Backend endpoints available -->
```
GET /api/sleeper/user/{username}     -> SleeperUserResponse
GET /api/sleeper/leagues/{user_id}   -> SleeperLeaguesResponse
GET /api/sleeper/roster/{league_id}/{user_id} -> SleeperRosterResponse
GET /api/sleeper/matchup/{league_id}/{week}   -> SleeperMatchupResponse
GET /api/sleeper/free-agents/{league_id}      -> SleeperFreeAgentsResponse
```

<!-- Existing frontend conventions from CLAUDE.md -->
```
- React Query for data fetching (useSuspenseQuery on client)
- API layer: types.ts -> api.ts (service) -> queries.ts
- shadcn/ui components: Card, Table, Input, Button, Badge, ScrollArea
- PageContainer for page headers
- Single quotes, no trailing comma, 2-space indent
```

<!-- localStorage pattern for league context -->
```typescript
interface SleeperContext {
  username: string
  user_id: string
  league_id: string
  league_name: string
}
// Save: localStorage.setItem('sleeper_context', JSON.stringify(ctx))
// Load: JSON.parse(localStorage.getItem('sleeper_context') ?? 'null')
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Types, API layer, and Connect League flow</name>
  <files>web/frontend/src/lib/nfl/types.ts, web/frontend/src/lib/nfl/api.ts, web/frontend/src/features/nfl/api/types.ts, web/frontend/src/features/nfl/api/service.ts, web/frontend/src/features/nfl/components/sleeper-connect.tsx</files>
  <action>
1. **Add Sleeper types** to `web/frontend/src/lib/nfl/types.ts` (append):
   ```typescript
   export interface SleeperUser {
     user_id: string
     username: string
     display_name: string
     avatar: string | null
   }
   export interface SleeperLeague {
     league_id: string
     name: string
     season: number
     total_rosters: number
     roster_positions: string[]
     scoring_type: string
   }
   export interface SleeperPlayer {
     sleeper_id: string
     player_name: string
     position: string
     team: string | null
     is_starter: boolean
     projected_points: number | null
   }
   export interface SleeperContext {
     username: string
     user_id: string
     league_id: string
     league_name: string
   }
   ```

2. **Add API functions** to `web/frontend/src/lib/nfl/api.ts` (append):
   - `fetchSleeperUser(username: string): Promise<SleeperUser>`
     - GET `/api/sleeper/user/${username}`
   - `fetchSleeperLeagues(userId: string, season?: number): Promise<{leagues: SleeperLeague[]}>`
     - GET `/api/sleeper/leagues/${userId}?season=${season}`
   - `fetchSleeperRoster(leagueId: string, userId: string): Promise<{players: SleeperPlayer[], league_id: string, user_id: string}>`
     - GET `/api/sleeper/roster/${leagueId}/${userId}`
   - `fetchSleeperFreeAgents(leagueId: string, topN?: number): Promise<{players: SleeperPlayer[], league_id: string}>`
     - GET `/api/sleeper/free-agents/${leagueId}?top_n=${topN}`

3. **Re-export** the new types from `features/nfl/api/types.ts` and functions from `features/nfl/api/service.ts`.

4. **Create `sleeper-connect.tsx`** component:
   - State machine: `idle` -> `loading_user` -> `select_league` -> `connected`
   - **Idle state:** Input field for Sleeper username + "Connect" button
   - **Loading state:** Spinner while fetching user and leagues
   - **Select league state:** Card list of leagues showing name, roster count, scoring type. Click to select.
   - **Connected state:** Shows "Connected as {display_name} in {league_name}" with a "Disconnect" button
   - On connect: save `SleeperContext` to `localStorage` key `sleeper_context`
   - On disconnect: remove from localStorage, reset to idle
   - On mount: check localStorage for existing context and auto-set to connected state
   - Use shadcn Input, Button, Card components. Follow existing component patterns.
   - Handle errors: show inline error message if username not found or API fails
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx tsc --noEmit 2>&1 | head -30</automated>
  </verify>
  <done>
    - Sleeper types exported from lib/nfl/types.ts
    - 4 API functions added to lib/nfl/api.ts
    - SleeperConnect component handles the full connect/disconnect flow
    - localStorage persists league context
    - TypeScript compiles without errors
  </done>
</task>

<task type="auto">
  <name>Task 2: My Team page with roster, start/sit, and waiver wire</name>
  <files>web/frontend/src/features/nfl/components/my-roster.tsx, web/frontend/src/features/nfl/components/waiver-suggestions.tsx, web/frontend/src/app/dashboard/my-team/page.tsx</files>
  <action>
1. **Create `my-roster.tsx`** component:
   - Props: `leagueId: string, userId: string`
   - Fetches roster from `/api/sleeper/roster/{leagueId}/{userId}`
   - Displays as a table/card grid grouped by position (QB, RB, WR, TE, K, BENCH)
   - Each player row shows: name, team, position, projected_points, start/sit badge
   - **Start/sit logic** (client-side):
     - Players in `starters` list get green "START" badge
     - Bench players with higher projected_points than a starter at same position get
       amber "CONSIDER STARTING" badge
     - Injured players (if projection is 0 or null) get red "SIT" badge
   - Show total projected points at the top (sum of starters only)
   - Use shadcn Table with Badge components for status indicators
   - Loading skeleton while fetching

2. **Create `waiver-suggestions.tsx`** component:
   - Props: `leagueId: string`
   - Fetches free agents from `/api/sleeper/free-agents/{leagueId}?top_n=20`
   - Shows top 20 available players sorted by projected_points descending
   - Columns: Rank, Name, Position, Team, Projected Points
   - Use shadcn Table. Highlight top 5 with a subtle background color.
   - If no projection data, show player name/position/team without points

3. **Create `/dashboard/my-team/page.tsx`**:
   - `'use client'` page
   - Uses `PageContainer` with pageTitle="My Team" and pageDescription="Your Sleeper league roster and recommendations"
   - Reads `SleeperContext` from localStorage on mount
   - **If not connected:** Show `SleeperConnect` component prominently (centered card with instructions)
   - **If connected:** Show:
     - `SleeperConnect` in compact mode at the top (shows connected status, disconnect button)
     - `MyRoster` component with the league/user context
     - `WaiverSuggestions` component below the roster
   - Add navigation entry for "My Team" in the dashboard sidebar/nav (check layout.tsx for nav pattern)
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx tsc --noEmit 2>&1 | head -30</automated>
  </verify>
  <done>
    - /dashboard/my-team page renders with connect flow
    - Connected users see roster with start/sit highlighting
    - Waiver suggestions show top available players
    - Total projected points displayed for starters
    - Navigation updated with My Team link
    - TypeScript compiles without errors
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Visual verification of Sleeper integration</name>
  <action>
Human verifies the complete Sleeper integration frontend: connect flow, roster display with start/sit recommendations, and waiver wire suggestions.
  </action>
  <verify>
    1. Start dev servers: `cd web && ./run_dev.sh` (backend) and `cd web/frontend && npm run dev` (frontend)
    2. Navigate to http://localhost:3000/dashboard/my-team
    3. Verify the "Connect League" flow appears
    4. Enter a real Sleeper username (or test username if you have one)
    5. Verify leagues are listed and selectable
    6. After selecting a league, verify:
       a. Roster displays with player names, positions, projected points
       b. Starters have green START badges
       c. Total projected points shown at top
       d. Waiver wire suggestions appear below roster
    7. Refresh the page -- verify league context persists (localStorage)
    8. Click "Disconnect" -- verify it returns to the connect flow
  </verify>
  <done>User approves the visual and functional behavior of the Sleeper integration</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| localStorage | User-controlled storage; league context could be tampered |
| browser -> FastAPI | Sleeper IDs from localStorage used in API calls |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-W7-05 | Tampering | localStorage | accept | Only stores public Sleeper context (username, league_id); no secrets or auth tokens |
| T-W7-06 | Info Disclosure | Roster data | accept | All Sleeper data is publicly available via their API; no private data exposed |
| T-W7-07 | Spoofing | League ID in URL | accept | Read-only access to public data; spoofing yields someone else's public roster |
</threat_model>

<verification>
1. TypeScript compiles without errors
2. My Team page accessible at /dashboard/my-team
3. Connect flow works end-to-end (username -> leagues -> roster)
4. localStorage persists across refreshes
5. Start/sit badges appear correctly based on projections
</verification>

<success_criteria>
- User can connect Sleeper account by username (no OAuth needed)
- Roster displays with projected points and start/sit recommendations
- Waiver wire shows top available players
- Context persists in localStorage
- Page is accessible from dashboard navigation
</success_criteria>

<output>
After completion, create `.planning/phases/phase-W7/W7-02-SUMMARY.md`
</output>
