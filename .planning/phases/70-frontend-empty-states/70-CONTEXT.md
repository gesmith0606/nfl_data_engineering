# Phase 70: Frontend Empty/Error States - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Add defensive UX to 4 top-level pages (predictions, lineups, matchups, news) so partial-data, stale-data, and offseason conditions render **friendly minimal-card empty states** instead of crashing, blanking, or showing dangling sentiment numbers. Surface `data_as_of` metadata from backend `meta` on all 4 pages, matching the Phase 63 freshness indicator pattern.

Out of scope: backend API changes (Phase 66 already added graceful defaulting); sentiment content itself (Phase 69); new UI illustrations or design system extensions; frontend routing changes.

</domain>

<decisions>
## Implementation Decisions

### Empty State Design (FE-01..04 user UX)
- **Minimal card style** — centered shadcn Card containing:
  - Lucide icon (CalendarX / Inbox / ChartOff / Newspaper — page-appropriate)
  - Bold heading (e.g. "No predictions yet")
  - Subtext with context ("Games start Week 1 — September 2025" or "No games this week")
  - `data_as_of` chip at bottom ("• Updated 2 days ago")
- Single shared component `<EmptyState />` — avoid 4 near-duplicate implementations
- ~30 LOC per page integration + ~60 LOC shared component

### data_as_of Surfacing (FE-05)
- All 4 pages surface freshness when `meta.data_as_of` is present in API response
- Shown as small muted-text chip at page header (top-right) AND inside the empty state
- Format: relative time ("2 days ago", "just now") for < 7 days; absolute date for older
- Use existing pattern from Phase 63 (grep for `dataAsOf` in `hooks/use-week-params.ts` and `lib/week-context.ts`)
- If `meta.data_as_of` is missing (backend doesn't provide), suppress the chip silently — do NOT show "Unknown"

### Matchups Page 503 Handling (FE-03)
- `/api/teams/current-week` returning 503 renders: "No games this week — showing preseason preview"
- Below the empty state, still show the existing preseason matchup preview (if data available) — graceful degradation
- 503 is expected during offseason; do NOT treat as an error (no error toast, no red styling)

### News Page Null-Safety (FE-04)
- If `/api/news/team-events` returns all 32 teams with `total_articles === 0` OR all events `event_flags: []` — render empty state
- If `/api/news/feed` returns items but they have `sentiment: null` AND `summary: null` — render the headline text only, skip the sentiment chip (no dangling numbers)
- Do NOT show the sentiment rating chip unless `sentiment` is a valid number AND `summary` is a non-empty string

### Testing Approach
- Frontend tests use Vitest + React Testing Library (existing pattern in web/frontend/)
- Mock API responses for each empty/populated state
- No need for E2E tests (unit tests on the component + page integrations suffice)

### Claude's Discretion
- Exact icon choice per page (Lucide has many — pick something semantically appropriate)
- Exact empty-state heading copy (keep concise, < 5 words)
- Relative-vs-absolute time formatting threshold (7 days is a reasonable default; user may fine-tune later)
- Whether to use `date-fns` or a lightweight custom helper for relative time (repo convention — use what's already imported if any; else lightweight custom)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `web/frontend/src/hooks/use-week-params.ts` — has `dataAsOf` handling pattern from Phase 63
- `web/frontend/src/lib/week-context.ts` — context provider for week/freshness
- `web/frontend/src/components/ui/card.tsx` — shadcn Card
- `web/frontend/src/components/ui/badge.tsx` — for data_as_of chip
- Lucide icons imported via `lucide-react` (already in deps)
- Phase 63 established `data_as_of` backend meta pattern; frontend consumption varies by page

### Established Patterns
- Next.js App Router with Server Components + Client Components
- Features live under `web/frontend/src/features/nfl/components/`
- Pages (routes) live under `web/frontend/src/app/`
- API client: `web/frontend/src/lib/api-client.ts`
- Tailwind CSS with design tokens (`web/frontend/src/styles/tokens.css`)
- Phase 66 introduced server-side graceful defaulting — the frontend can trust a 200 response with an empty array (no 422 handling required)

### Integration Points
- Predictions page: `web/frontend/src/features/nfl/components/prediction-cards.tsx` (Phase 66 edited)
- Lineups page: `web/frontend/src/features/nfl/components/lineup-view.tsx` (Phase 66 edited)
- Matchups page: `web/frontend/src/features/nfl/components/matchup-view.tsx`
- News page: `web/frontend/src/features/nfl/components/player-news-panel.tsx` + `news-feed.tsx`

</code_context>

<specifics>
## Specific Ideas

- The empty-state component should live at `web/frontend/src/components/EmptyState.tsx` (or under `src/features/nfl/components/` — planner picks based on reusability)
- The component accepts props: `{ icon?: LucideIcon; title: string; description?: string; dataAsOf?: string | Date | null }`
- When `dataAsOf` is null/undefined, the "Updated X ago" line is omitted cleanly
- Each of the 4 pages should have at least 1 new test file or extended existing test asserting the empty state renders with expected copy

</specifics>

<deferred>
## Deferred Ideas

- Animated/interactive empty states (e.g., subtle fade-in) — out of scope; static cards only
- Rich illustrations — user explicitly rejected in favor of minimal cards
- Skeleton loading states — separate UX concern; existing loading spinners retained
- Internationalization of empty state copy — not needed; project is English-only

</deferred>
