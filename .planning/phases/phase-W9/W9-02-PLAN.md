---
phase: W9-draft-tool
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - web/frontend/src/lib/nfl/types.ts
  - web/frontend/src/lib/nfl/api.ts
  - web/frontend/src/features/nfl/api/service.ts
  - web/frontend/src/features/nfl/api/queries.ts
  - web/frontend/src/config/nav-config.ts
  - web/frontend/src/features/draft/hooks/use-draft-state.ts
autonomous: true
requirements:
  - DRAFT-FE-01
  - DRAFT-FE-02
  - DRAFT-FE-03

must_haves:
  truths:
    - "TypeScript types exist for all draft API request/response shapes"
    - "API fetch functions exist for all 6 draft endpoints"
    - "React Query options exist for draft board, recommendations, and ADP"
    - "Draft navigation item appears in sidebar"
    - "Draft state hook manages session_id, config, and roster in React state"
  artifacts:
    - path: "web/frontend/src/lib/nfl/types.ts"
      provides: "Draft TypeScript interfaces"
      contains: "DraftBoardResponse"
    - path: "web/frontend/src/lib/nfl/api.ts"
      provides: "Draft API fetch functions"
      contains: "fetchDraftBoard"
    - path: "web/frontend/src/features/draft/hooks/use-draft-state.ts"
      provides: "Client-side draft state management hook"
      contains: "useDraftState"
  key_links:
    - from: "web/frontend/src/features/nfl/api/service.ts"
      to: "web/frontend/src/lib/nfl/api.ts"
      via: "re-export"
      pattern: "fetchDraftBoard"
    - from: "web/frontend/src/features/nfl/api/queries.ts"
      to: "web/frontend/src/features/nfl/api/service.ts"
      via: "queryOptions import"
      pattern: "draftBoardQueryOptions"
---

<objective>
Build the frontend TypeScript types, API layer, query hooks, navigation, and draft state management for the web draft tool.

Purpose: Establish all the client-side contracts and data-fetching infrastructure so the draft UI (Plan 03) can be built against clean interfaces without needing to figure out API shapes or state management.

Output: TypeScript types, API functions, React Query options, sidebar nav entry, and a `useDraftState` hook.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@web/frontend/src/lib/nfl/types.ts
@web/frontend/src/lib/nfl/api.ts
@web/frontend/src/features/nfl/api/service.ts
@web/frontend/src/features/nfl/api/queries.ts
@web/frontend/src/config/nav-config.ts
@web/frontend/CLAUDE.md

<interfaces>
<!-- Existing patterns to follow -->

From web/frontend/src/lib/nfl/api.ts:
```typescript
// Pattern: all API functions use the request<T>() helper
async function request<T>(path: string, init?: RequestInit): Promise<T>

// Pattern: GET endpoints use URLSearchParams
export async function fetchProjections(season, week, scoring, position?): Promise<ProjectionResponse>

// Pattern: no POST endpoints exist yet — draft will be the first
```

From web/frontend/src/features/nfl/api/queries.ts:
```typescript
// Pattern: key factories
export const nflKeys = {
  all: ['nfl'] as const,
  projections: (...) => [...nflKeys.all, 'projections', {...}] as const,
}

// Pattern: queryOptions factory
export const projectionsQueryOptions = (...) => queryOptions({
  queryKey: nflKeys.projections(...),
  queryFn: () => fetchProjections(...)
})
```

From web/frontend/src/config/nav-config.ts:
```typescript
// Pattern: nav items with icon, url, shortcut
{ title: 'Projections', url: '/dashboard/projections', icon: 'target', isActive: false, shortcut: ['p', 'p'], items: [] }
```

From web/frontend/CLAUDE.md:
- React Query for all data fetching
- API layer per feature: api/types.ts -> api/service.ts -> api/queries.ts
- Single quotes, no trailing comma, 2-space indent
- Icons only from @/components/icons
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add draft TypeScript types and API fetch functions</name>
  <files>web/frontend/src/lib/nfl/types.ts, web/frontend/src/lib/nfl/api.ts, web/frontend/src/features/nfl/api/service.ts</files>
  <action>
**Step 1 — Append draft types to `web/frontend/src/lib/nfl/types.ts`:**

Add after the existing types (do NOT modify existing types):

```typescript
/** A player on the draft board. */
export interface DraftPlayer {
  player_id: string
  player_name: string
  position: string
  team: string | null
  projected_points: number
  model_rank: number
  adp_rank: number | null
  adp_diff: number | null
  value_tier: 'undervalued' | 'fair_value' | 'overvalued'
  vorp: number
}

/** Full draft board state from the API. */
export interface DraftBoardResponse {
  session_id: string
  players: DraftPlayer[]
  my_roster: DraftPlayer[]
  picks_taken: number
  my_pick_count: number
  remaining_needs: Record<string, number>
  scoring_format: string
  roster_format: string
  n_teams: number
}

/** Request body for recording a draft pick. */
export interface DraftPickRequest {
  session_id: string
  player_id: string
  by_me: boolean
}

/** Response after recording a draft pick. */
export interface DraftPickResponse {
  success: boolean
  player: DraftPlayer | null
  message: string
}

/** A single draft recommendation. */
export interface DraftRecommendation {
  player_id: string
  player_name: string
  position: string
  team: string | null
  projected_points: number
  model_rank: number
  vorp: number
  recommendation_score: number
}

/** Recommendations response. */
export interface DraftRecommendationsResponse {
  recommendations: DraftRecommendation[]
  reasoning: string
  remaining_needs: Record<string, number>
}

/** Request to start a mock draft. */
export interface MockDraftStartRequest {
  scoring?: string
  roster_format?: string
  n_teams?: number
  user_pick?: number
  season?: number
}

/** Response after starting a mock draft. */
export interface MockDraftStartResponse {
  session_id: string
  message: string
}

/** Request to advance one pick in mock draft. */
export interface MockDraftPickRequest {
  session_id: string
}

/** Response after advancing a mock draft pick. */
export interface MockDraftPickResponse {
  pick_number: number
  round_number: number
  is_user_turn: boolean
  player_name: string | null
  position: string | null
  team: string | null
  is_complete: boolean
  draft_grade: string | null
  total_pts: number | null
  total_vorp: number | null
}

/** ADP entry for a player. */
export interface AdpPlayer {
  player_name: string
  position: string
  team: string | null
  adp_rank: number
}

/** ADP response envelope. */
export interface AdpResponse {
  players: AdpPlayer[]
  source: string
  updated_at: string | null
}

/** Draft configuration for starting a new draft. */
export interface DraftConfig {
  scoring: ScoringFormat
  roster_format: 'standard' | 'superflex' | '2qb'
  n_teams: number
  user_pick: number
  season: number
}
```

**Step 2 — Add draft API functions to `web/frontend/src/lib/nfl/api.ts`:**

Add these functions after the existing exports, following the same `request<T>()` pattern:

```typescript
/** Fetch or create a draft board session. */
export async function fetchDraftBoard(
  scoring: ScoringFormat = 'half_ppr',
  rosterFormat: string = 'standard',
  nTeams: number = 12,
  season: number = 2026,
  sessionId?: string
): Promise<DraftBoardResponse> {
  const params = new URLSearchParams({ scoring, roster_format: rosterFormat, n_teams: String(nTeams), season: String(season) })
  if (sessionId) params.set('session_id', sessionId)
  return request<DraftBoardResponse>(`/api/draft/board?${params}`)
}

/** Record a draft pick. */
export async function draftPick(body: DraftPickRequest): Promise<DraftPickResponse> {
  return request<DraftPickResponse>('/api/draft/pick', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

/** Get draft recommendations. */
export async function fetchDraftRecommendations(
  sessionId: string,
  topN: number = 5,
  position?: string
): Promise<DraftRecommendationsResponse> {
  const params = new URLSearchParams({ session_id: sessionId, top_n: String(topN) })
  if (position && position !== 'ALL') params.set('position', position)
  return request<DraftRecommendationsResponse>(`/api/draft/recommendations?${params}`)
}

/** Start a mock draft. */
export async function startMockDraft(body: MockDraftStartRequest): Promise<MockDraftStartResponse> {
  return request<MockDraftStartResponse>('/api/draft/mock/start', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

/** Advance one pick in a mock draft. */
export async function advanceMockDraft(body: MockDraftPickRequest): Promise<MockDraftPickResponse> {
  return request<MockDraftPickResponse>('/api/draft/mock/pick', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

/** Fetch latest ADP data. */
export async function fetchAdp(): Promise<AdpResponse> {
  return request<AdpResponse>('/api/draft/adp')
}
```

Add the new type imports at the top of api.ts:
```typescript
import type { ..., DraftBoardResponse, DraftPickRequest, DraftPickResponse, DraftRecommendationsResponse, MockDraftStartRequest, MockDraftStartResponse, MockDraftPickRequest, MockDraftPickResponse, AdpResponse } from './types'
```

**Step 3 — Add re-exports to `web/frontend/src/features/nfl/api/service.ts`:**

Append to the existing re-export list:
```typescript
export {
  // ... existing exports ...
  fetchDraftBoard,
  draftPick,
  fetchDraftRecommendations,
  startMockDraft,
  advanceMockDraft,
  fetchAdp
} from '@/lib/nfl/api'
```
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx tsc --noEmit 2>&1 | head -30</automated>
  </verify>
  <done>
    - DraftPlayer, DraftBoardResponse, and all draft types added to types.ts
    - 6 API fetch functions added to api.ts following existing request<T>() pattern
    - Re-exports added to service.ts
    - TypeScript compiles without errors
  </done>
</task>

<task type="auto">
  <name>Task 2: Add React Query options, nav config, and draft state hook</name>
  <files>web/frontend/src/features/nfl/api/queries.ts, web/frontend/src/config/nav-config.ts, web/frontend/src/features/draft/hooks/use-draft-state.ts</files>
  <action>
**Step 1 — Add draft query options to `web/frontend/src/features/nfl/api/queries.ts`:**

Add to the `nflKeys` object:
```typescript
draftBoard: (sessionId?: string) => [...nflKeys.all, 'draft-board', sessionId] as const,
draftRecommendations: (sessionId: string, position?: string) => [...nflKeys.all, 'draft-recs', { sessionId, position }] as const,
adp: () => [...nflKeys.all, 'adp'] as const
```

Add query option factories:
```typescript
import { fetchDraftBoard, fetchDraftRecommendations, fetchAdp } from './service'
import type { ScoringFormat } from './types'

export const draftBoardQueryOptions = (
  scoring: ScoringFormat = 'half_ppr',
  rosterFormat: string = 'standard',
  nTeams: number = 12,
  season: number = 2026,
  sessionId?: string
) =>
  queryOptions({
    queryKey: nflKeys.draftBoard(sessionId),
    queryFn: () => fetchDraftBoard(scoring, rosterFormat, nTeams, season, sessionId),
    staleTime: Infinity  // Draft board only changes when we mutate it
  })

export const draftRecommendationsQueryOptions = (
  sessionId: string,
  topN: number = 5,
  position?: string
) =>
  queryOptions({
    queryKey: nflKeys.draftRecommendations(sessionId, position),
    queryFn: () => fetchDraftRecommendations(sessionId, topN, position),
    enabled: !!sessionId
  })

export const adpQueryOptions = () =>
  queryOptions({
    queryKey: nflKeys.adp(),
    queryFn: () => fetchAdp(),
    staleTime: 60 * 60 * 1000  // ADP data rarely changes
  })
```

**Step 2 — Add Draft to sidebar nav in `web/frontend/src/config/nav-config.ts`:**

Add a new nav item after the "News" entry (before "Model Accuracy"):
```typescript
{
  title: 'Draft Tool',
  url: '/dashboard/draft',
  icon: 'clipboardText',
  isActive: false,
  shortcut: ['r', 'r'],
  items: []
}
```

Use `clipboardText` icon which maps to `IconClipboardText` already imported in icons.tsx.

**Step 3 — Create `web/frontend/src/features/draft/hooks/use-draft-state.ts`:**

Create directory `web/frontend/src/features/draft/hooks/` if needed.

This hook manages the client-side draft session state using React useState + React Query mutations:

```typescript
'use client'

import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { draftPick, startMockDraft } from '@/features/nfl/api/service'
import { nflKeys } from '@/features/nfl/api/queries'
import type { DraftConfig, DraftPickRequest, MockDraftStartRequest, Position } from '@/lib/nfl/types'

const DEFAULT_CONFIG: DraftConfig = {
  scoring: 'half_ppr',
  roster_format: 'standard',
  n_teams: 12,
  user_pick: 1,
  season: 2026
}

export function useDraftState() {
  const queryClient = useQueryClient()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [config, setConfig] = useState<DraftConfig>(DEFAULT_CONFIG)
  const [positionFilter, setPositionFilter] = useState<Position>('ALL')
  const [mode, setMode] = useState<'manual' | 'mock'>('manual')

  const pickMutation = useMutation({
    mutationFn: (req: DraftPickRequest) => draftPick(req),
    onSuccess: () => {
      // Invalidate board + recommendations after a pick
      queryClient.invalidateQueries({ queryKey: nflKeys.draftBoard(sessionId ?? undefined) })
      if (sessionId) {
        queryClient.invalidateQueries({ queryKey: nflKeys.draftRecommendations(sessionId) })
      }
    }
  })

  const mockStartMutation = useMutation({
    mutationFn: (req: MockDraftStartRequest) => startMockDraft(req),
    onSuccess: (data) => {
      setSessionId(data.session_id)
      setMode('mock')
    }
  })

  const handleDraftPlayer = useCallback((playerId: string, byMe: boolean = true) => {
    if (!sessionId) return
    pickMutation.mutate({ session_id: sessionId, player_id: playerId, by_me: byMe })
  }, [sessionId, pickMutation])

  const handleStartMock = useCallback(() => {
    mockStartMutation.mutate({
      scoring: config.scoring,
      roster_format: config.roster_format,
      n_teams: config.n_teams,
      user_pick: config.user_pick,
      season: config.season
    })
  }, [config, mockStartMutation])

  const resetDraft = useCallback(() => {
    setSessionId(null)
    setMode('manual')
    queryClient.removeQueries({ queryKey: nflKeys.draftBoard() })
  }, [queryClient])

  return {
    sessionId,
    setSessionId,
    config,
    setConfig,
    positionFilter,
    setPositionFilter,
    mode,
    setMode,
    pickMutation,
    mockStartMutation,
    handleDraftPlayer,
    handleStartMock,
    resetDraft
  }
}
```

Export type `DraftConfig` is already in types.ts from Task 1.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx tsc --noEmit 2>&1 | head -30</automated>
  </verify>
  <done>
    - Draft query options added to queries.ts with proper key factories
    - "Draft Tool" appears in sidebar nav config
    - useDraftState hook created with session management, pick mutation, mock start mutation
    - TypeScript compiles without errors
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser -> API | All draft data flows through existing API proxy |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-W9-05 | Info Disclosure | API key in client | accept | Uses existing NEXT_PUBLIC_API_KEY pattern already in production |
</threat_model>

<verification>
1. `npx tsc --noEmit` passes with zero errors
2. Draft types are importable from `@/lib/nfl/types`
3. API functions are importable from `@/lib/nfl/api`
4. Sidebar shows "Draft Tool" nav item
5. useDraftState hook compiles and exports all state/actions
</verification>

<success_criteria>
- All draft TypeScript interfaces defined
- 6 API fetch functions created following existing patterns
- React Query key factories and queryOptions created
- Sidebar navigation includes Draft Tool
- useDraftState hook manages session, config, position filter, and mutations
- TypeScript compiles cleanly
</success_criteria>

<output>
After completion, create `.planning/phases/phase-W9/W9-02-SUMMARY.md`
</output>
