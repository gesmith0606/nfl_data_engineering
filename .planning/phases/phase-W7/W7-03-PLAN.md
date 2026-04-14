---
phase: W7-sleeper-integration
plan: 03
type: execute
wave: 2
depends_on: [W7-01]
files_modified:
  - web/frontend/src/app/api/chat/route.ts
autonomous: true
requirements: [SLP-11, SLP-12, SLP-13]

must_haves:
  truths:
    - "AI advisor can fetch the user's current roster when asked"
    - "AI advisor can list waiver wire options from the user's league"
    - "AI advisor gives personalized start/sit advice using roster context"
  artifacts:
    - path: "web/frontend/src/app/api/chat/route.ts"
      provides: "Two new tools: getMyRoster, getWaiverWire"
      contains: "getMyRoster"
  key_links:
    - from: "web/frontend/src/app/api/chat/route.ts"
      to: "/api/sleeper/roster/{league_id}/{user_id}"
      via: "fastapiGet in tool execute"
      pattern: "fastapiGet.*sleeper.*roster"
    - from: "web/frontend/src/app/api/chat/route.ts"
      to: "/api/sleeper/free-agents/{league_id}"
      via: "fastapiGet in tool execute"
      pattern: "fastapiGet.*sleeper.*free-agents"
---

<objective>
Add two new tools to the AI advisor chat route so it can access the user's Sleeper
roster and league waiver wire. This enables personalized advice like "Drop X, pick up Y
from your waiver wire" and roster-aware start/sit decisions.

Purpose: The AI advisor becomes league-aware, transforming from generic fantasy advice
to personalized team management.

Output: Updated chat route.ts with `getMyRoster` and `getWaiverWire` tools.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/phase-W7/W7-01-SUMMARY.md

@web/frontend/src/app/api/chat/route.ts

<interfaces>
<!-- From W7-01: Backend Sleeper endpoints -->
```
GET /api/sleeper/roster/{league_id}/{user_id}
  Response: {
    players: [{sleeper_id, player_name, position, team, is_starter, projected_points}],
    league_id, user_id
  }

GET /api/sleeper/free-agents/{league_id}?top_n=20
  Response: {
    players: [{sleeper_id, player_name, position, team, is_starter: false, projected_points}],
    league_id
  }
```

<!-- Existing tool pattern in route.ts -->
```typescript
tools: {
  getPlayerProjection: tool({
    description: '...',
    inputSchema: z.object({ ... }),
    execute: async ({ ... }) => {
      const data = await fastapiGet<ResponseType>(`/api/endpoint?${params}`);
      if (!data) return { found: false, message: '...' };
      return { found: true, ...data };
    }
  }),
}
```

<!-- The frontend passes sleeper context from localStorage via message metadata.
     The chat route receives it as part of the request and makes it available to tools. -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add getMyRoster and getWaiverWire tools to AI advisor</name>
  <files>web/frontend/src/app/api/chat/route.ts</files>
  <action>
Modify `web/frontend/src/app/api/chat/route.ts` to add two new tools to the `tools` object:

1. **`getMyRoster` tool:**
   ```typescript
   getMyRoster: tool({
     description: 'Get the user\'s current fantasy roster from their connected Sleeper league. Returns all rostered players with positions, teams, starter/bench status, and projected points. Use this when the user asks about their team, wants start/sit advice, or mentions "my roster/team/players".',
     inputSchema: z.object({
       leagueId: z.string().describe('The Sleeper league ID'),
       userId: z.string().describe('The Sleeper user ID')
     }),
     execute: async ({ leagueId, userId }) => {
       const data = await fastapiGet<{
         players: Array<{
           sleeper_id: string;
           player_name: string;
           position: string;
           team: string | null;
           is_starter: boolean;
           projected_points: number | null;
         }>;
         league_id: string;
         user_id: string;
       }>(`/api/sleeper/roster/${leagueId}/${userId}`);

       if (!data?.players?.length) {
         return { found: false, message: 'Could not load roster. Make sure you\'ve connected your Sleeper league.' };
       }

       const starters = data.players.filter(p => p.is_starter);
       const bench = data.players.filter(p => !p.is_starter);
       const totalPoints = starters.reduce((sum, p) => sum + (p.projected_points ?? 0), 0);

       return {
         found: true,
         starters,
         bench,
         total_projected_points: Math.round(totalPoints * 10) / 10,
         roster_size: data.players.length
       };
     }
   })
   ```

2. **`getWaiverWire` tool:**
   ```typescript
   getWaiverWire: tool({
     description: 'Get available free agents (waiver wire) from the user\'s Sleeper league. Returns unrostered players sorted by projected points. Use when user asks about pickups, waiver wire, or available players.',
     inputSchema: z.object({
       leagueId: z.string().describe('The Sleeper league ID'),
       position: z.enum(['ALL', 'QB', 'RB', 'WR', 'TE']).default('ALL').describe('Filter by position, or ALL for all positions')
     }),
     execute: async ({ leagueId, position }) => {
       const params = new URLSearchParams({ top_n: '30' });
       const data = await fastapiGet<{
         players: Array<{
           sleeper_id: string;
           player_name: string;
           position: string;
           team: string | null;
           projected_points: number | null;
         }>;
       }>(`/api/sleeper/free-agents/${leagueId}?${params}`);

       if (!data?.players?.length) {
         return { found: false, message: 'No free agents found or league not connected.' };
       }

       let players = data.players;
       if (position !== 'ALL') {
         players = players.filter(p => p.position === position);
       }

       return {
         found: true,
         players: players.slice(0, 15),
         total_available: data.players.length
       };
     }
   })
   ```

3. **Update SYSTEM_PROMPT** to include Sleeper awareness. Add after the existing rules:
   ```
   - When the user has connected their Sleeper league, use getMyRoster to see their actual team before giving advice.
   - For start/sit decisions with a connected league, always check the user's full roster first.
   - For waiver wire advice, use getWaiverWire to find real available players in their league.
   - When suggesting drops, compare bench players' projections to waiver wire options.
   - The user passes their Sleeper league context (leagueId, userId) — use these with the roster and waiver tools.
   ```

4. **Pass Sleeper context from frontend to chat route:**
   The frontend will send `sleeperContext` as part of the request body (alongside `messages`).
   In the POST handler, extract it:
   ```typescript
   const { messages, sleeperContext }: {
     messages: UIMessage[];
     sleeperContext?: { league_id: string; user_id: string } | null;
   } = await req.json();
   ```
   If `sleeperContext` is present, prepend a system-level context note to the system prompt:
   ```
   The user has connected their Sleeper league (league_id: ${sleeperContext.league_id}, user_id: ${sleeperContext.user_id}). Use these IDs with getMyRoster and getWaiverWire tools.
   ```
   This way the AI knows the IDs to use without the user having to type them.

5. **Update the advisor page** to pass sleeperContext:
   In `web/frontend/src/app/dashboard/advisor/page.tsx`, read `SleeperContext` from
   localStorage and pass it in the `useChat` body option:
   ```typescript
   const sleeperCtx = typeof window !== 'undefined'
     ? JSON.parse(localStorage.getItem('sleeper_context') ?? 'null')
     : null;

   const { messages, input, ... } = useChat({
     body: {
       sleeperContext: sleeperCtx ? { league_id: sleeperCtx.league_id, user_id: sleeperCtx.user_id } : null
     }
   });
   ```
   Note: Check the AI SDK docs for the correct way to pass extra body fields with `useChat`.
   The `body` option merges additional fields into every request.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx tsc --noEmit 2>&1 | head -30</automated>
  </verify>
  <done>
    - getMyRoster tool returns starters, bench, and total projected points
    - getWaiverWire tool returns available players filtered by position
    - System prompt updated with Sleeper-aware instructions
    - Sleeper context passed from frontend localStorage to chat route
    - AI can say "Based on your roster, start X over Y" and "Pick up Z from waivers, drop W"
    - TypeScript compiles without errors
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser -> chat API | sleeperContext from localStorage (user-controlled) |
| chat API -> FastAPI | league_id/user_id forwarded to backend |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-W7-08 | Tampering | sleeperContext in body | accept | IDs are opaque strings used only for read-only Sleeper API calls; tampering yields someone else's public roster |
| T-W7-09 | Info Disclosure | Roster in AI context | accept | Roster data is public Sleeper info; AI does not persist or log it |
</threat_model>

<verification>
1. TypeScript compiles without errors
2. AI advisor with connected league can answer "Who should I start this week?"
3. AI advisor can suggest waiver wire pickups from the user's actual league
4. Without a connected league, AI still works but doesn't use roster tools
</verification>

<success_criteria>
- AI advisor has access to user's roster and waiver wire via two new tools
- Sleeper context automatically passed from localStorage to chat route
- AI gives personalized advice when league is connected
- No regression in existing 4 tools (getPlayerProjection, compareStartSit, searchPlayers, getNewsFeed)
</success_criteria>

<output>
After completion, create `.planning/phases/phase-W7/W7-03-SUMMARY.md`
</output>
