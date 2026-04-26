---
phase: 73-external-projections-comparison
plan: 04
type: execute
wave: 4
depends_on: [73-03]
files_modified:
  - web/frontend/src/lib/nfl/types.ts
  - web/frontend/src/features/nfl/api/types.ts
  - web/frontend/src/features/nfl/api/service.ts
  - web/frontend/src/features/nfl/api/queries.ts
  - web/frontend/src/features/nfl/components/projections-table/index.tsx
  - web/frontend/src/features/nfl/components/projections-table/comparison-columns.tsx
  - web/frontend/src/features/nfl/components/projections-table/comparison-view.tsx
  - web/frontend/src/features/nfl/components/projections-table/comparison-view.test.tsx
autonomous: false
requirements: [EXTP-04, EXTP-05]
must_haves:
  truths:
    - "Projections page renders a tab/toggle 'Comparison' alongside 'Standard' that swaps in the new ProjectionComparisonTable"
    - "ProjectionComparisonTable shows columns Player / Pos / Team / Ours / ESPN / Sleeper / Yahoo / Δ vs Ours / Rank, with delta cells color-coded green (above ours) / red (below) / muted (neutral)"
    - "Position filter, scoring toggle, season/week selectors are shared between the Standard and Comparison views (same filter state)"
    - "Yahoo column shows a tooltip 'via FantasyPros consensus' sourced from response.source_labels.yahoo"
    - "Missing source values render as the em-dash '—' (NOT 'null', '0', or 'N/A')"
    - "data_as_of chip surfaces Silver Parquet freshness via meta.data_as_of (Phase 70 EmptyState/freshness pattern)"
  artifacts:
    - path: "web/frontend/src/lib/nfl/types.ts"
      provides: "ProjectionComparison + ProjectionComparisonRow + SourceLabels TS types mirroring Pydantic"
    - path: "web/frontend/src/features/nfl/api/service.ts"
      provides: "fetchProjectionComparison(season, week, scoring, position?) -> Promise<ProjectionComparison>"
    - path: "web/frontend/src/features/nfl/api/queries.ts"
      provides: "projectionComparisonQueryOptions + nflKeys.projectionComparison key factory"
    - path: "web/frontend/src/features/nfl/components/projections-table/comparison-view.tsx"
      provides: "ProjectionComparisonTable component"
    - path: "web/frontend/src/features/nfl/components/projections-table/comparison-columns.tsx"
      provides: "TanStack column defs for comparison rows"
  key_links:
    - from: "ProjectionsTable (existing)"
      to: "ProjectionComparisonTable (new)"
      via: "Tabs component switching between 'Standard' and 'Comparison' views"
      pattern: "TabsTrigger value=\"comparison\""
    - from: "fetchProjectionComparison"
      to: "GET /api/projections/comparison"
      via: "next URL builder + JSON parse"
      pattern: "/api/projections/comparison|projections/comparison"
    - from: "ProjectionComparisonTable"
      to: "projectionComparisonQueryOptions"
      via: "useQuery from @tanstack/react-query"
      pattern: "useQuery|projectionComparisonQueryOptions"
---

<objective>
Render the comparison endpoint on the existing projections page. Adds a tab toggle so users switch between the existing Standard view and the new Comparison view without losing filter state. The Comparison view is a sortable TanStack table with Δ vs Ours coloring, Yahoo provenance tooltip, em-dash placeholders for missing sources, and a data_as_of freshness chip.

Purpose: Deliver the user-visible payoff of Phase 73 — actual side-by-side comparison + transparency. Reuses 100% of existing filter UI; the only NEW UI surface is the tab toggle + the comparison table itself.
Output: TS types, API service+query, 1 column-defs file, 1 view component, 1 test file, plus extension to the existing ProjectionsTable container.

This plan has a checkpoint (`autonomous: false`) for human visual verification of the comparison view in the browser before shipping — the API is testable but the visual rendering needs eyeballs.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/73-external-projections-comparison/73-CONTEXT.md
@.planning/phases/73-external-projections-comparison/73-03-api-comparison-endpoint-PLAN.md
@web/frontend/CLAUDE.md
@web/frontend/src/features/nfl/components/projections-table/index.tsx
@web/frontend/src/features/nfl/components/projections-table/columns.tsx
@web/frontend/src/features/nfl/api/queries.ts
@web/frontend/src/features/nfl/api/types.ts

<interfaces>
<!-- Types this plan creates and consumes -->

API contract from Wave 3 (mirror in TS):
```typescript
export interface ProjectionComparisonRow {
  player_id: string;
  player_name: string;
  position: string;
  team: string;
  ours: number | null;
  espn: number | null;
  sleeper: number | null;
  yahoo: number | null;
  delta_vs_ours: number | null;
  position_rank_ours: number | null;
}

export interface ProjectionMeta {
  season: number;
  week: number;
  data_as_of: string | null;
  source_path: string | null;
}

export interface ProjectionComparison {
  season: number;
  week: number;
  scoring_format: string;
  rows: ProjectionComparisonRow[];
  sources_present: string[];
  source_labels: Record<string, string>;   // e.g. { yahoo: "yahoo_proxy_fp" }
  generated_at: string;
  meta: ProjectionMeta | null;
}
```

Existing patterns to mirror (from web/frontend/CLAUDE.md):
- React Query: `useQuery(...)` for client components; key factory in `nflKeys`
- Icons: only from `@/components/icons`
- Formatting: single quotes, JSX single quotes, no trailing commas
- Forms: NOT applicable here
- Use `PageContainer` props (no manual headers)

Existing ProjectionsTable layout (from index.tsx) currently has Card filters → position tabs → table; we add a NEW tab control above (or alongside) the position tabs that toggles between Standard and Comparison view.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: TS types + API service + React Query options</name>
  <files>
    web/frontend/src/lib/nfl/types.ts,
    web/frontend/src/features/nfl/api/types.ts,
    web/frontend/src/features/nfl/api/service.ts,
    web/frontend/src/features/nfl/api/queries.ts
  </files>
  <behavior>
    - Add `ProjectionComparison`, `ProjectionComparisonRow` TS interfaces to `web/frontend/src/lib/nfl/types.ts` (mirror Pydantic schema exactly; use `number | null` for nullable floats, `Record<string, string>` for source_labels)
    - Re-export from `web/frontend/src/features/nfl/api/types.ts`
    - Add `fetchProjectionComparison(season, week, scoring, position?, limit?) -> Promise<ProjectionComparison>` to `service.ts`. Use the existing fetch helper pattern (look at `fetchProjections` in service.ts and mirror error handling: 404 → throw with `.status = 404`).
    - Add `nflKeys.projectionComparison(season, week, scoring, position?)` key factory + `projectionComparisonQueryOptions(season, week, scoring, position?)` to `queries.ts`. Mirror `projectionsQueryOptions` shape exactly.
    - Apply `retry: (failureCount, error) => error?.status === 404 ? false : failureCount < 2` (same as predictionsQueryOptions) so the query doesn't hammer 404s.
    - No new component yet — this task is pure type/data plumbing.
  </behavior>
  <action>
    1. Read `web/frontend/src/lib/nfl/types.ts` to find the right spot for the new interfaces. Add them adjacent to the existing `PlayerProjection` / `ProjectionResponse` types.
    2. Read `web/frontend/src/features/nfl/api/service.ts` to find the `fetchProjections` implementation. Mirror its style for `fetchProjectionComparison`. URL: `${API_BASE}/api/projections/comparison?season=${season}&week=${week}&scoring=${scoring}${position ? `&position=${position}` : ''}${limit ? `&limit=${limit}` : ''}`. Default limit not passed = backend default (50).
    3. Add the type re-export to `web/frontend/src/features/nfl/api/types.ts` (the file is currently a single re-export block).
    4. Add `nflKeys.projectionComparison` AFTER `nflKeys.projections` in `queries.ts`. Add `projectionComparisonQueryOptions` export below `projectionsQueryOptions`.
    5. Sanity check via TS compiler: `cd web/frontend && npx tsc --noEmit` — clean (no new errors introduced).
    6. Frontend tests: not required for pure type/service plumbing in this codebase. Skip Vitest for this task — Task 3 covers component-level vitest coverage.
  </action>
  <verify>
    <automated>cd web/frontend && npx tsc --noEmit 2>&1 | tee /tmp/tsc-73-04-task1.log && ! grep -E "error TS" /tmp/tsc-73-04-task1.log</automated>
  </verify>
  <done>
    - 2 new TS interfaces added to lib/nfl/types.ts
    - Re-exported via features/nfl/api/types.ts
    - `fetchProjectionComparison` + `projectionComparisonQueryOptions` + `nflKeys.projectionComparison` exist
    - `npx tsc --noEmit` clean (no new TS errors)
    - Single quotes, JSX single quotes, no trailing commas (per web/frontend/CLAUDE.md)
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: ProjectionComparisonTable component + column defs + Vitest coverage</name>
  <files>
    web/frontend/src/features/nfl/components/projections-table/comparison-columns.tsx,
    web/frontend/src/features/nfl/components/projections-table/comparison-view.tsx,
    web/frontend/src/features/nfl/components/projections-table/comparison-view.test.tsx
  </files>
  <behavior>
    - `comparison-columns.tsx` exports `comparisonColumns: ColumnDef<ProjectionComparisonRow>[]` with these columns (in order):
       1. position_rank_ours — "Rank" header, muted tabular-nums, "—" if null. Hidden below sm: breakpoint (mirror existing columns.tsx mobile pattern).
       2. player_name — "Player" header, Link to `/dashboard/players/${player_id}`, font-medium hover:underline, truncate on mobile.
       3. team — "Team" header, getTeamColor dot + monospace abbr (mirror existing). Hidden below sm.
       4. position — "Pos" header, Badge with position colorMap (mirror existing).
       5. ours — "Ours" header, font-bold tabular-nums, em-dash if null.
       6. espn — "ESPN" header, tabular-nums, em-dash if null. Hidden below md.
       7. sleeper — "Sleeper" header, tabular-nums, em-dash if null. Hidden below md.
       8. yahoo — "Yahoo" header, tabular-nums, em-dash if null. Header has tooltip via shadcn `Tooltip` reading `source_labels.yahoo` — but tooltip needs context, so we render the tooltip on the column header static text rather than per-cell. Use a small InfoIcon next to the header text. Hidden below md.
       9. delta_vs_ours — "Δ vs Ours" header, color-coded: green-600 if > 0.5, red-600 if < -0.5, muted otherwise; em-dash if null. Sortable. Hidden below sm.
    - `comparison-view.tsx` exports `ProjectionComparisonTable({ season, week, scoring, position })` — a thin container that calls `useQuery(projectionComparisonQueryOptions(...))`, renders DataTable with `comparisonColumns` + DataTableToolbar, displays a Skeleton on loading, error Card on error (mirror the existing index.tsx error pattern), and an EmptyState when `data?.rows.length === 0` (per Phase 70 pattern: text "No comparison data yet for Week N" with a freshness hint if `meta?.data_as_of` is null).
    - Render a small chip near the table header showing `data_as_of` freshness when present (`Updated <relative time>`), using the existing `formatRelativeTime` helper from `@/lib/format-relative-time`.
    - Render a small caption row above the table listing the sources present, e.g. "Comparing 4 sources: Ours, ESPN, Sleeper, Yahoo (via FantasyPros)" — pulled from `data.sources_present` + `data.source_labels`.
    - Vitest tests in `comparison-view.test.tsx` (use the existing `EventBadges.test.tsx` as the structural reference):
       - `renders em-dash for null source values` — mock query response with one row where espn=null
       - `colors delta green when greater than 0.5` — mock row, assert class includes 'text-green-600' (or similar)
       - `colors delta red when less than -0.5` — mock row, assert class includes 'text-red-600'
       - `renders Yahoo via FantasyPros caption when source_labels.yahoo present` — assert caption text
       - `shows EmptyState when rows is empty` — mock empty response, assert EmptyState rendered
  </behavior>
  <action>
    1. Read `web/frontend/src/features/nfl/components/projections-table/columns.tsx` to mirror the existing column-def patterns (mobile hide classes, position colorMap, getTeamColor, Link wrapping for player_name).
    2. Create `comparison-columns.tsx` with the 9 columns. Reuse `HIDE_BELOW_SM` / `HIDE_BELOW_MD` constants. Em-dash literal: `—` (U+2014, single character).
    3. For the Yahoo tooltip on the column header, use shadcn `Tooltip` + `TooltipTrigger` + `TooltipContent`. Wrap a small Info icon (from `@/components/icons`) next to the "Yahoo" text. Tooltip text: derived from a prop or context — for simplicity, hardcode "via FantasyPros consensus" inside the column def IF source_labels.yahoo is present (we can't pass props into static column defs cleanly; either make column defs a function `getComparisonColumns(sourceLabels)` that closes over the labels OR show the tooltip unconditionally since yahoo is always proxy in v1). Choose the function approach: `export function getComparisonColumns(sourceLabels: Record<string, string>): ColumnDef<ProjectionComparisonRow>[]`.
    4. Create `comparison-view.tsx` per the Behavior block. Use `useQuery(projectionComparisonQueryOptions(...))`. Use `useDataTable` hook (mirror existing index.tsx pattern). Use `getComparisonColumns(data?.source_labels ?? {})` so columns rebuild when labels change.
    5. Create `comparison-view.test.tsx`. Use Vitest + React Testing Library (mirror `EventBadges.test.tsx` structure). Mock `useQuery` via `vi.mock('@tanstack/react-query', ...)` OR wrap in `QueryClientProvider` with a stubbed query function (prefer the latter — closer to real behavior).
    6. EmptyState: import the existing `<EmptyState />` from `@/components/empty-state` (per Phase 70). If it accepts a `description` prop, pass `Updated unknown` guard from TD-05 (NOT this phase's responsibility — just don't pass empty string).
    7. Run `cd web/frontend && npx vitest run comparison-view --reporter=verbose` — 5 tests pass.
    8. Run `cd web/frontend && npx tsc --noEmit` — clean.
  </action>
  <verify>
    <automated>cd web/frontend && npx vitest run comparison-view && npx tsc --noEmit</automated>
  </verify>
  <done>
    - 3 new files under `projections-table/` (column defs + view + test)
    - 5 Vitest tests pass
    - tsc clean
    - Em-dash for nulls (not "null"/"0"/"N/A")
    - Yahoo header has via-FantasyPros tooltip when source_labels.yahoo present
    - delta_vs_ours color-coded green/red/muted
    - EmptyState rendered when rows empty
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire ProjectionComparisonTable into existing ProjectionsTable container with Standard/Comparison tab toggle</name>
  <files>
    web/frontend/src/features/nfl/components/projections-table/index.tsx
  </files>
  <behavior>
    - Existing `ProjectionsTable` component gains a `view` state (`'standard' | 'comparison'`) defaulting to `'standard'`
    - A new `<Tabs value={view} onValueChange={...}>` rendered ABOVE the position tabs (right under the season/week/scoring Card filters), with two `TabsTrigger`: "Standard" + "Comparison"
    - When `view === 'standard'`: render the existing DataTable (today's behavior — unchanged)
    - When `view === 'comparison'`: render `<ProjectionComparisonTable season={season} week={week} scoring={scoring} position={position === 'ALL' ? undefined : position} />`
    - Both views share the season/week/scoring/position state — switching the toggle does NOT reset filters
    - Position tabs remain rendered for both views (filter is reused)
    - No regression to existing standard view (existing data flow + tests pass)
  </behavior>
  <action>
    1. Edit `web/frontend/src/features/nfl/components/projections-table/index.tsx`:
       - Import `ProjectionComparisonTable` from `./comparison-view`
       - Add `const [view, setView] = useState<'standard' | 'comparison'>('standard');`
       - Add a new `<Tabs value={view} onValueChange={(v) => setView(v as 'standard' | 'comparison')}>` block immediately after the Card filters, before the position tabs. Use the same shadcn TabsList / TabsTrigger styling as the existing scoring tabs.
       - Wrap the existing DataTable JSX (lines 114-147 region) in a conditional: `{view === 'standard' ? (<existing DataTable>) : (<ProjectionComparisonTable season={season} week={week} scoring={scoring} position={position === 'ALL' ? undefined : position} />)}`
       - Keep the loading/error states applicable to the standard view only — comparison-view manages its own loading/error states internally.
    2. Verify position tab still renders in both modes (above the conditional).
    3. Smoke test: `cd web/frontend && npx tsc --noEmit` clean.
    4. Smoke test: `cd web/frontend && npx vitest run --reporter=verbose` — all existing frontend tests still pass; new comparison-view tests still pass.
  </action>
  <verify>
    <automated>cd web/frontend && npx tsc --noEmit && npx vitest run</automated>
  </verify>
  <done>
    - Tab toggle Standard/Comparison rendered on projections page
    - Filters shared between views (season/week/scoring/position)
    - Standard view unchanged (no regression)
    - Comparison view renders the new ProjectionComparisonTable
    - tsc clean; all vitest tests pass
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4: Human visual verification of comparison view</name>
  <what-built>
    - GET /api/projections/comparison endpoint live (Wave 3)
    - Comparison TS types + service + query
    - ProjectionComparisonTable component with 9 columns, em-dash placeholders, Yahoo tooltip, color-coded deltas, EmptyState fallback
    - Tab toggle on existing /dashboard/projections page
  </what-built>
  <how-to-verify>
    1. Start the backend: `./web/run_dev.sh` (default port 8000)
    2. Start the frontend dev server: `cd web/frontend && npm run dev` (default port 3000)
    3. Run a manual ingestion to seed Bronze: at minimum
       - `python scripts/ingest_external_projections_espn.py --season 2025 --week 1`
       - `python scripts/ingest_external_projections_sleeper.py --season 2025 --week 1` (skip if Sleeper offseason returns empty; that's fine — D-06)
       - `python scripts/ingest_external_projections_yahoo.py --season 2025 --week 1`
       - `python scripts/silver_external_projections_transformation.py --season 2025 --week 1 --scoring half_ppr`
       (If running offseason and external APIs are sparse, use the fixtures from Wave 3 — copy `tests/fixtures/silver_external_projections/season=2025/week=1/external_projections_sample.parquet` into `data/silver/external_projections/season=2025/week=1/`)
    4. Open http://localhost:3000/dashboard/projections in a browser
    5. VERIFY each of these:
       - [ ] The "Standard" / "Comparison" tab toggle is visible above the position tabs
       - [ ] Clicking "Comparison" swaps the table without losing the season/week/scoring/position filter state
       - [ ] The comparison table shows columns: Rank, Player, Team, Pos, Ours, ESPN, Sleeper, Yahoo, Δ vs Ours
       - [ ] Cells with missing source values render `—` (em-dash), NOT "null", "0", or "undefined"
       - [ ] Hovering the Yahoo column header shows tooltip "via FantasyPros consensus" (if Yahoo source is present in the data)
       - [ ] Δ vs Ours cells are color-coded: green for positive deltas > 0.5, red for negative < -0.5, muted otherwise
       - [ ] Mobile breakpoint (resize to <640px or use Chrome DevTools 375px iPhone preview): the table hides ESPN/Sleeper/Yahoo/Δ columns and shows just Player + Pos + Ours + Yahoo (or however the HIDE_BELOW_SM/MD classes resolve)
       - [ ] Switching back to "Standard" tab restores the original ProjectionsTable view
       - [ ] If Silver Parquet is missing for the selected (season, week), an EmptyState renders (not a blank screen or error toast)
       - [ ] data_as_of chip shows the freshness of the underlying Silver Parquet
    6. Capture a screenshot of the desktop comparison view + a mobile-width comparison view for the SUMMARY.md
  </how-to-verify>
  <resume-signal>Type "approved" with screenshots attached, OR describe issues for revision</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| API JSON → React | Untrusted (from our API; trust low because of D-06 partial-data semantics) |
| URL query params (frontend) | User-controlled |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-73-04-01 | Tampering | Null source values | mitigate | TS type uses `number \| null` explicitly; column cells check `value == null` and render em-dash (no toString of null) |
| T-73-04-02 | Spoofing | Yahoo proxy provenance hidden from user | mitigate | Yahoo column header tooltip shows "via FantasyPros consensus" when source_labels.yahoo present; sources_present caption above table lists provenance |
| T-73-04-03 | Information Disclosure | source_labels expose internal label | accept | source_labels values (e.g. "yahoo_proxy_fp") are not sensitive — they're informational provenance strings |
| T-73-04-04 | Tampering | XSS via player_name | mitigate | React auto-escapes JSX text content; no `dangerouslySetInnerHTML` used |
| T-73-04-05 | Denial of Service | Massive comparison response | mitigate | Backend caps `limit` at 500 (Wave 3); frontend default limit not passed (backend default 50) |
</threat_model>

<verification>
- `cd web/frontend && npx tsc --noEmit` clean
- `cd web/frontend && npx vitest run` — all tests pass (5 new + existing)
- Backend tests still green: `python -m pytest tests/web/ -v`
- Human visual verification approved (Task 4)
- No regressions on the existing /dashboard/projections page (standard view)
</verification>

<success_criteria>
- [x] Comparison view renders on /dashboard/projections via tab toggle
- [x] Em-dash for missing source values
- [x] Yahoo column has via-FantasyPros tooltip
- [x] Δ vs Ours color-coded green/red/muted
- [x] EmptyState when no Silver data
- [x] data_as_of chip surfaces freshness
- [x] Mobile breakpoint handled (HIDE_BELOW_SM/MD classes applied)
- [x] Filter state shared between Standard and Comparison views
- [x] Vitest + tsc clean; no regressions
- [x] Human checkpoint approved
</success_criteria>

<output>
After completion, create `.planning/phases/73-external-projections-comparison/73-04-SUMMARY.md` summarizing: TS types added, components created, screenshots captured, requirements covered (EXTP-04 + freshness hook for EXTP-05).
</output>
