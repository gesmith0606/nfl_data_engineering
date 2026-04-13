---
phase: W9-draft-tool
plan: 03
type: execute
wave: 2
depends_on: [01, 02]
files_modified:
  - web/frontend/src/app/dashboard/draft/page.tsx
  - web/frontend/src/features/draft/components/draft-board-table.tsx
  - web/frontend/src/features/draft/components/draft-config-dialog.tsx
  - web/frontend/src/features/draft/components/my-roster-panel.tsx
  - web/frontend/src/features/draft/components/recommendations-panel.tsx
  - web/frontend/src/features/draft/components/mock-draft-view.tsx
autonomous: false
requirements:
  - DRAFT-UI-01
  - DRAFT-UI-02
  - DRAFT-UI-03
  - DRAFT-UI-04
  - DRAFT-UI-05
  - DRAFT-UI-06

must_haves:
  truths:
    - "User can visit /dashboard/draft and see a draft board with all players"
    - "User can filter players by position using tabs"
    - "User can sort columns by clicking headers"
    - "User can draft a player by clicking the Draft button"
    - "User can see their drafted roster in a side panel"
    - "User can configure draft settings (teams, pick, scoring, roster format)"
    - "User can start and run a mock draft simulation"
    - "User can see best available recommendations with reasoning"
  artifacts:
    - path: "web/frontend/src/app/dashboard/draft/page.tsx"
      provides: "Draft tool page route"
      contains: "DraftPage"
    - path: "web/frontend/src/features/draft/components/draft-board-table.tsx"
      provides: "Main draft board table with sortable columns"
      contains: "DraftBoardTable"
    - path: "web/frontend/src/features/draft/components/draft-config-dialog.tsx"
      provides: "Configuration dialog for draft settings"
      contains: "DraftConfigDialog"
    - path: "web/frontend/src/features/draft/components/my-roster-panel.tsx"
      provides: "Panel showing user's drafted players"
      contains: "MyRosterPanel"
    - path: "web/frontend/src/features/draft/components/mock-draft-view.tsx"
      provides: "Mock draft simulation UI"
      contains: "MockDraftView"
  key_links:
    - from: "web/frontend/src/app/dashboard/draft/page.tsx"
      to: "web/frontend/src/features/draft/components/draft-board-table.tsx"
      via: "component import"
      pattern: "DraftBoardTable"
    - from: "web/frontend/src/features/draft/components/draft-board-table.tsx"
      to: "web/frontend/src/features/nfl/api/queries.ts"
      via: "useSuspenseQuery with draftBoardQueryOptions"
      pattern: "draftBoardQueryOptions"
---

<objective>
Build the complete draft tool UI: the main draft board page, configuration dialog, roster panel, recommendations, and mock draft view.

Purpose: This is the user-facing deliverable -- an interactive draft tool where users can run snake drafts, see live ADP/VORP rankings, get AI recommendations, and run mock draft simulations. All backend endpoints and frontend infrastructure are ready from Plans 01 and 02.

Output: `/dashboard/draft` page with all interactive draft functionality.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/phase-W9/W9-01-SUMMARY.md
@.planning/phases/phase-W9/W9-02-SUMMARY.md
@web/frontend/CLAUDE.md
@web/frontend/src/app/dashboard/projections/page.tsx
@web/frontend/src/lib/nfl/types.ts
@web/frontend/src/lib/nfl/api.ts
@web/frontend/src/features/nfl/api/queries.ts
@web/frontend/src/features/draft/hooks/use-draft-state.ts
@web/frontend/src/components/layout/page-container.tsx
@web/frontend/src/components/ui/table.tsx
@web/frontend/src/components/ui/dialog.tsx
@web/frontend/src/components/ui/tabs.tsx
@web/frontend/src/components/ui/badge.tsx
@web/frontend/src/components/ui/button.tsx
@web/frontend/src/components/ui/select.tsx
@web/frontend/src/components/ui/card.tsx
@web/frontend/src/lib/nfl/team-colors.ts

<interfaces>
<!-- From Plan 02 outputs -->

From web/frontend/src/features/draft/hooks/use-draft-state.ts:
```typescript
export function useDraftState(): {
  sessionId: string | null
  setSessionId: (id: string | null) => void
  config: DraftConfig
  setConfig: (config: DraftConfig) => void
  positionFilter: Position
  setPositionFilter: (pos: Position) => void
  mode: 'manual' | 'mock'
  setMode: (mode: 'manual' | 'mock') => void
  pickMutation: UseMutationResult<DraftPickResponse, Error, DraftPickRequest>
  mockStartMutation: UseMutationResult<MockDraftStartResponse, Error, MockDraftStartRequest>
  handleDraftPlayer: (playerId: string, byMe?: boolean) => void
  handleStartMock: () => void
  resetDraft: () => void
}
```

From web/frontend/src/lib/nfl/types.ts:
```typescript
interface DraftPlayer { player_id, player_name, position, team, projected_points, model_rank, adp_rank, adp_diff, value_tier, vorp }
interface DraftBoardResponse { session_id, players, my_roster, picks_taken, my_pick_count, remaining_needs, scoring_format, roster_format, n_teams }
interface DraftRecommendationsResponse { recommendations, reasoning, remaining_needs }
interface MockDraftPickResponse { pick_number, round_number, is_user_turn, player_name, position, team, is_complete, draft_grade, total_pts, total_vorp }
interface DraftConfig { scoring, roster_format, n_teams, user_pick, season }
```

From web/frontend/src/features/nfl/api/queries.ts:
```typescript
draftBoardQueryOptions(scoring, rosterFormat, nTeams, season, sessionId?)
draftRecommendationsQueryOptions(sessionId, topN, position?)
adpQueryOptions()
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Build draft page, board table, config dialog, and roster panel</name>
  <files>web/frontend/src/app/dashboard/draft/page.tsx, web/frontend/src/features/draft/components/draft-board-table.tsx, web/frontend/src/features/draft/components/draft-config-dialog.tsx, web/frontend/src/features/draft/components/my-roster-panel.tsx, web/frontend/src/features/draft/components/recommendations-panel.tsx</files>
  <action>
**1. Create `web/frontend/src/app/dashboard/draft/page.tsx`:**

Follow the pattern from projections/page.tsx. Use PageContainer with `pageTitle='Draft Tool'` and `pageDescription='Interactive draft board with ADP, VORP, and AI recommendations'`. Wrap content in Suspense. The page should render a `DraftToolView` client component that orchestrates everything.

Create a `'use client'` component inline or in a separate file. This component:
- Calls `useDraftState()` to get session, config, mutations
- On mount (useEffect), if no sessionId, calls `fetchDraftBoard(config.scoring, config.roster_format, config.n_teams, config.season)` to initialize a session, then stores the session_id via setSessionId
- Renders a two-column layout (desktop): left = draft board table (70%), right = roster + recommendations (30%)
- Above the table: position filter Tabs (ALL, QB, RB, WR, TE, K) + "Settings" Button that opens DraftConfigDialog + "Mock Draft" Button + "Reset" Button
- Below the board on mobile: roster panel collapses into an expandable section

**2. Create `web/frontend/src/features/draft/components/draft-board-table.tsx`:**

`'use client'` component. Props: `{ players: DraftPlayer[], positionFilter: Position, onDraft: (playerId: string) => void, isPicking: boolean }`.

Render a table using shadcn Table component with these columns:
- **Rank** — `model_rank` (sortable)
- **Player** — `player_name` with position Badge colored by position (QB=red, RB=blue, WR=green, TE=orange, K=gray)
- **Team** — `team` abbreviation
- **Pts** — `projected_points` formatted to 1 decimal (sortable)
- **ADP** — `adp_rank` or "--" if null (sortable)
- **Value** — `adp_diff` with color: green if positive (undervalued), red if negative (overvalued), gray if null
- **VORP** — `vorp` formatted to 1 decimal (sortable)
- **Tier** — Badge showing value_tier: "undervalued" green, "fair_value" gray, "overvalued" red
- **Action** — Button "Draft" (variant="outline", size="sm") calling `onDraft(player.player_id)`. Disabled when isPicking.

Implement client-side sorting with useState: `sortKey` and `sortDir`. Click column header to toggle. Filter by positionFilter before rendering. Use the existing team-colors.ts for team badge coloring if desired.

Limit display to 200 rows for performance. Show a count like "Showing 200 of 450 available players".

**3. Create `web/frontend/src/features/draft/components/draft-config-dialog.tsx`:**

`'use client'` component. Props: `{ config: DraftConfig, onConfigChange: (config: DraftConfig) => void, onStartMock: () => void, open: boolean, onOpenChange: (open: boolean) => void }`.

Use shadcn Dialog component. Contains:
- **Teams**: Select with options 8, 10, 12, 14
- **My Pick**: Select with options 1 through n_teams
- **Scoring**: Select with PPR, Half-PPR, Standard
- **Roster Format**: Select with standard, superflex, 2qb
- **Season**: Select with 2025, 2026
- "Apply & New Draft" Button — applies config, resets session, closes dialog
- "Start Mock Draft" Button — calls onStartMock, closes dialog

**4. Create `web/frontend/src/features/draft/components/my-roster-panel.tsx`:**

`'use client'` component. Props: `{ roster: DraftPlayer[], remainingNeeds: Record<string, number>, picksCount: number }`.

Uses shadcn Card. Shows:
- Header: "My Team ({picksCount} picks)"
- List of drafted players grouped by position, showing name, team, projected_points
- Footer: "Remaining needs: QB x1, RB x2, ..." from remainingNeeds (only slots with count > 0)
- Empty state: "No players drafted yet. Click 'Draft' on any player to start."

**5. Create `web/frontend/src/features/draft/components/recommendations-panel.tsx`:**

`'use client'` component. Props: `{ sessionId: string | null, positionFilter: Position }`.

Uses `useQuery(draftRecommendationsQueryOptions(sessionId, 5, positionFilter))` (only when sessionId is set). Renders a Card with:
- Header: "Recommendations"
- List of top 5 recommended players with recommendation_score, position Badge, projected_points
- Reasoning string displayed as muted text below the list
- Loading skeleton when fetching
- "Pick recommendations update after each draft pick" helper text

All components follow single quotes, no trailing comma, 2-space indent per CLAUDE.md conventions.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx tsc --noEmit 2>&1 | head -30</automated>
  </verify>
  <done>
    - /dashboard/draft page renders with PageContainer
    - Draft board table shows all players with sortable columns
    - Position filter tabs work (ALL/QB/RB/WR/TE/K)
    - Draft button on each row calls the pick mutation
    - Config dialog allows changing teams/pick/scoring/roster format
    - My Team panel shows drafted players grouped by position
    - Recommendations panel shows top picks with reasoning
    - TypeScript compiles without errors
  </done>
</task>

<task type="auto">
  <name>Task 2: Build mock draft simulation view</name>
  <files>web/frontend/src/features/draft/components/mock-draft-view.tsx</files>
  <action>
Create `web/frontend/src/features/draft/components/mock-draft-view.tsx`:

`'use client'` component. Props: `{ sessionId: string, config: DraftConfig, onReset: () => void }`.

This component manages the mock draft flow where the AI simulates opponent picks and the user watches / picks on their turn.

**State:**
- `picks: MockDraftPickResponse[]` — all picks made so far
- `isRunning: boolean` — whether the simulation is advancing
- `isComplete: boolean` — draft finished
- `draftGrade: string | null`
- `totalPts: number | null`
- `totalVorp: number | null`

**Mock Draft Mutation:**
```typescript
const advanceMutation = useMutation({
  mutationFn: () => advanceMockDraft({ session_id: sessionId }),
  onSuccess: (data) => {
    setPicks(prev => [...prev, data])
    if (data.is_complete) {
      setIsComplete(true)
      setDraftGrade(data.draft_grade)
      setTotalPts(data.total_pts)
      setTotalVorp(data.total_vorp)
      setIsRunning(false)
    }
  }
})
```

**UI Layout:**

1. **Controls bar**: "Advance Pick" Button (advances one pick at a time), "Auto-Run" Button (runs all picks automatically with 300ms delay between each using setInterval), "Reset" Button. Auto-run sets isRunning=true and uses useEffect with setInterval to call advanceMutation.mutate() every 300ms until isComplete.

2. **Draft Log table**: Shows all picks in a scrollable table:
   - Pick # | Round | Team (YOU or OPP) | Player | Position
   - User's picks highlighted with a colored background (bg-primary/10)
   - Auto-scroll to latest pick using `useRef` on the container + `scrollIntoView`

3. **Results Card** (shown when isComplete):
   - Draft Grade with large letter (A/B/C/D) styled with color (A=green, B=blue, C=yellow, D=red)
   - Total Projected Points
   - Total VORP
   - "Your Roster" list showing all drafted players
   - "Run Again" Button calling onReset

4. **Pick counter**: "Pick {currentPick} of {totalPicks}" progress indicator

The mock draft view replaces the normal board view when mode is 'mock'. The parent DraftToolView component should conditionally render either the board or mock view based on `mode` from useDraftState.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx tsc --noEmit 2>&1 | head -30</automated>
  </verify>
  <done>
    - Mock draft view renders when mock mode activated
    - Advance Pick button advances one pick per click
    - Auto-Run button simulates all picks with visual progress
    - Draft log shows all picks with user picks highlighted
    - Results card shows grade, points, VORP when complete
    - Reset returns to manual draft mode
    - TypeScript compiles without errors
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Visual verification of complete draft tool</name>
  <action>Human verifies the draft tool works end-to-end</action>
  <what-built>Complete draft tool with interactive board, configuration, mock draft simulation, recommendations, and roster tracking. Backend wraps existing draft_optimizer.py engine.</what-built>
  <how-to-verify>
    1. Start the backend: `cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && uvicorn web.api.main:app --reload --port 8000`
    2. Start the frontend: `cd web/frontend && npm run dev`
    3. Visit http://localhost:3000/dashboard/draft
    4. Verify the draft board loads with players showing Rank, Name, Team, Pts, ADP, Value, VORP, Tier columns
    5. Click position filter tabs (QB, RB, WR, TE) — table should filter
    6. Click column headers — table should sort
    7. Click "Draft" on a player — player should appear in My Team panel, disappear from board
    8. Check Recommendations panel updates after each pick
    9. Click Settings — verify config dialog with teams/pick/scoring options
    10. Click "Mock Draft" — verify mock draft view appears
    11. Click "Advance Pick" or "Auto-Run" — watch picks progress through the draft
    12. After mock completes, verify grade (A-D), total points, and roster display
    13. Click "Reset" — verify return to manual draft mode
    14. Check sidebar shows "Draft Tool" navigation item
  </how-to-verify>
  <resume-signal>Type "approved" or describe issues to fix</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| user -> draft UI | User clicks Draft/Config buttons; all actions go through mutations |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-W9-06 | Denial of Service | auto-run mock | mitigate | 300ms delay between picks prevents API flooding; disable button while running |
| T-W9-07 | Tampering | draft picks | accept | Single-user app; no multi-user draft state to tamper with |
</threat_model>

<verification>
1. `npx tsc --noEmit` passes
2. `/dashboard/draft` page loads and shows draft board
3. Position filters, sorting, drafting all work interactively
4. Mock draft runs to completion with grade
5. Config dialog changes are reflected in new draft sessions
6. Mobile layout degrades gracefully (single column)
</verification>

<success_criteria>
- Complete interactive draft tool at /dashboard/draft
- Draft board with sortable columns and position filters
- Click-to-draft with instant roster panel update
- AI recommendations with reasoning text
- Configuration dialog for teams/pick/scoring/roster
- Mock draft simulation with auto-run and results
- Mobile-responsive layout
- Sidebar navigation entry
</success_criteria>

<output>
After completion, create `.planning/phases/phase-W9/W9-03-SUMMARY.md`
</output>
