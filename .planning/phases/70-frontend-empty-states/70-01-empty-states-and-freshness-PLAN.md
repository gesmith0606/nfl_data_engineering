---
phase: 70-frontend-empty-states
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - web/frontend/src/components/EmptyState.tsx  # NEW shared component
  - web/frontend/src/lib/format-relative-time.ts  # NEW helper (if no existing utility)
  - web/frontend/src/features/nfl/components/prediction-cards.tsx  # predictions page
  - web/frontend/src/features/nfl/components/lineup-view.tsx  # lineups page
  - web/frontend/src/features/nfl/components/matchup-view.tsx  # matchups page
  - web/frontend/src/features/nfl/components/player-news-panel.tsx  # news page null-safety
  - web/frontend/src/features/nfl/components/news-feed.tsx  # news feed null-safety
  - web/frontend/src/components/__tests__/EmptyState.test.tsx  # NEW component test
autonomous: true
requirements:
  - FE-01
  - FE-02
  - FE-03
  - FE-04
  - FE-05
tags:
  - frontend
  - empty-states
  - defensive-ux
  - freshness
must_haves:
  truths:
    - "When /api/predictions returns [], the predictions page renders an EmptyState card (not a blank screen) with heading 'No predictions yet' or similar, and the dataAsOf chip if meta.data_as_of present"
    - "When /api/lineups returns empty, the lineups page renders an EmptyState card surfacing current season + week context"
    - "When /api/teams/current-week returns 503, the matchups page renders an EmptyState card ('No games this week — showing preseason preview') and below it the existing preseason preview if data is available"
    - "When /api/news/feed returns items with sentiment: null AND summary: null, the news feed renders the headline text only — no dangling sentiment chip with null values"
    - "When /api/news/team-events returns 32 teams all with total_articles=0, the news page renders 'No news yet this week' empty state"
    - "All 4 pages display a dataAsOf chip at top-right of the page header when meta.data_as_of is present in the API response (format: relative time < 7 days, absolute otherwise)"
    - "Shared <EmptyState /> component accepts { icon, title, description, dataAsOf } props; suppresses dataAsOf line when null"
  artifacts:
    - path: "web/frontend/src/components/EmptyState.tsx"
      provides: "Shared empty-state card component (~60 LOC)"
      contains: "export function EmptyState"
    - path: "web/frontend/src/components/__tests__/EmptyState.test.tsx"
      provides: "Unit tests for EmptyState component covering: renders title, renders description, suppresses dataAsOf when null, renders dataAsOf as relative time"
      min_lines: 80
  key_links:
    - from: "/api/predictions returns []"
      to: "prediction-cards.tsx EmptyState render"
      via: "conditional render: predictions.length === 0 ? <EmptyState /> : <PredictionGrid />"
      pattern: "EmptyState"
    - from: "/api/teams/current-week returns 503"
      to: "matchup-view.tsx offseason fallback"
      via: "error boundary + conditional render on 503 status"
      pattern: "503\\|offseason"
    - from: "meta.data_as_of"
      to: "page header chip + EmptyState footer"
      via: "formatRelativeTime helper + Badge component"
      pattern: "data_as_of"
---

<objective>
Add friendly empty states to 4 top-level pages (predictions, lineups, matchups, news) so partial-data, stale-data, and offseason conditions no longer show blank screens or dangling sentiment numbers. Surface `data_as_of` freshness metadata on all 4 pages. Ship a shared `<EmptyState />` component plus page-level integrations + tests.

Purpose: close the 5 FE requirements from the 2026-04-20 audit where predictions/lineups/matchups crashed and news showed sentiment chips over empty article bodies.

Output: 1 new shared component, 1 new test file, 4 page-level edits, + optional relative-time helper. Total ~250 LOC across 8 files.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.planning/phases/70-frontend-empty-states/70-CONTEXT.md
@web/frontend/src/hooks/use-week-params.ts
@web/frontend/src/lib/week-context.ts
@web/frontend/src/components/ui/card.tsx
@web/frontend/src/components/ui/badge.tsx
</execution_context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Shared EmptyState component + unit tests</name>
  <files>
    - web/frontend/src/components/EmptyState.tsx (NEW)
    - web/frontend/src/components/__tests__/EmptyState.test.tsx (NEW)
    - web/frontend/src/lib/format-relative-time.ts (NEW, only if no existing utility)
  </files>
  <read_first>
    - web/frontend/src/components/ui/card.tsx
    - web/frontend/src/components/ui/badge.tsx
    - web/frontend/src/hooks/use-week-params.ts (for dataAsOf shape reference)
    - web/frontend/src/lib/api-client.ts (meta shape)
    - `grep -rn "date-fns\|formatDistance\|format(" web/frontend/src/` to check for existing time formatting
  </read_first>
  <action>
Create `web/frontend/src/components/EmptyState.tsx`:

```tsx
import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatRelativeTime } from "@/lib/format-relative-time";

export interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  dataAsOf?: string | Date | null;
}

export function EmptyState({ icon: Icon, title, description, dataAsOf }: EmptyStateProps) {
  return (
    <Card
      className="mx-auto my-8 max-w-md"
      data-testid="empty-state"
      aria-live="polite"
    >
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        {Icon ? <Icon className="h-10 w-10 text-muted-foreground" aria-hidden /> : null}
        <h2 className="text-lg font-semibold">{title}</h2>
        {description ? (
          <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
        ) : null}
        {dataAsOf ? (
          <Badge variant="outline" className="mt-2 text-xs text-muted-foreground">
            Updated {formatRelativeTime(dataAsOf)}
          </Badge>
        ) : null}
      </CardContent>
    </Card>
  );
}
```

Create `web/frontend/src/lib/format-relative-time.ts` **only if** no existing utility found:

```ts
/**
 * Format a timestamp relative to now.
 * - < 1 min: "just now"
 * - < 1 hour: "N min ago"
 * - < 24 hours: "N hours ago"
 * - < 7 days: "N days ago"
 * - >= 7 days: absolute date "MMM D, YYYY"
 */
export function formatRelativeTime(input: string | Date): string {
  const now = Date.now();
  const then = typeof input === "string" ? Date.parse(input) : input.getTime();
  if (Number.isNaN(then)) return "unknown";

  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? "" : "s"} ago`;
  if (diffDay < 7) return `${diffDay} day${diffDay === 1 ? "" : "s"} ago`;

  const d = new Date(then);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
```

Create `web/frontend/src/components/__tests__/EmptyState.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Inbox } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";

describe("EmptyState", () => {
  it("renders title", () => {
    render(<EmptyState title="No predictions yet" />);
    expect(screen.getByText("No predictions yet")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(<EmptyState title="Nothing here" description="Games start Week 1" />);
    expect(screen.getByText("Games start Week 1")).toBeInTheDocument();
  });

  it("renders icon when provided", () => {
    const { container } = render(<EmptyState title="Empty" icon={Inbox} />);
    // Icon renders as an svg inside the card
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("suppresses dataAsOf badge when null", () => {
    render(<EmptyState title="Nothing" dataAsOf={null} />);
    expect(screen.queryByText(/Updated/)).not.toBeInTheDocument();
  });

  it("suppresses dataAsOf badge when undefined", () => {
    render(<EmptyState title="Nothing" />);
    expect(screen.queryByText(/Updated/)).not.toBeInTheDocument();
  });

  it("renders dataAsOf as relative time when recent", () => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    render(<EmptyState title="Nothing" dataAsOf={oneHourAgo} />);
    expect(screen.getByText(/Updated 1 hour ago/)).toBeInTheDocument();
  });

  it("renders dataAsOf as absolute date when > 7 days", () => {
    const tenDaysAgo = new Date(Date.now() - 10 * 86400 * 1000).toISOString();
    render(<EmptyState title="Nothing" dataAsOf={tenDaysAgo} />);
    expect(screen.getByText(/Updated \w+ \d+, \d{4}/)).toBeInTheDocument();
  });

  it("has aria-live polite for screen readers", () => {
    render(<EmptyState title="Nothing" />);
    expect(screen.getByTestId("empty-state")).toHaveAttribute("aria-live", "polite");
  });
});
```
  </action>
  <verify>
    <automated>cd web/frontend && npx vitest run src/components/__tests__/EmptyState.test.tsx 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `test -f web/frontend/src/components/EmptyState.tsx` succeeds
    - `test -f web/frontend/src/components/__tests__/EmptyState.test.tsx` succeeds
    - `grep -c "^describe\|^it(\|^  it(" web/frontend/src/components/__tests__/EmptyState.test.tsx` returns at least 8 (one per test case above)
    - `grep -n "export function EmptyState\|export interface EmptyStateProps" web/frontend/src/components/EmptyState.tsx` returns 2 lines
    - `grep -n "dataAsOf" web/frontend/src/components/EmptyState.tsx` returns at least 2 lines (prop + conditional render)
    - Vitest run for EmptyState exits 0 with all tests passing
    - TypeScript compile: `cd web/frontend && npx tsc --noEmit` exits 0 (no new type errors)
  </acceptance_criteria>
  <done>Shared EmptyState component exists, 8 unit tests pass, TypeScript compiles cleanly.</done>
</task>

<task type="auto">
  <name>Task 2: Predictions + Lineups pages use EmptyState (FE-01, FE-02, FE-05 partial)</name>
  <files>
    - web/frontend/src/features/nfl/components/prediction-cards.tsx
    - web/frontend/src/features/nfl/components/lineup-view.tsx
  </files>
  <read_first>
    - web/frontend/src/features/nfl/components/prediction-cards.tsx (current state; Phase 66 edited this)
    - web/frontend/src/features/nfl/components/lineup-view.tsx (current state; Phase 66 edited this)
    - web/frontend/src/components/EmptyState.tsx (the component being integrated, from Task 1)
  </read_first>
  <action>
**Predictions page (prediction-cards.tsx):**

Wrap the existing predictions list in a conditional render. When the API returns `[]` (empty array), render:

```tsx
import { CalendarX } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";

// inside the component, after data fetch:
if (predictions.length === 0) {
  return (
    <EmptyState
      icon={CalendarX}
      title="No predictions yet"
      description={`Predictions for Week ${week} season ${season} are not available. Check back when games are scheduled.`}
      dataAsOf={meta?.data_as_of ?? null}
    />
  );
}
```

At the page header (top of the populated state view), also surface the dataAsOf chip:

```tsx
{meta?.data_as_of ? (
  <Badge variant="outline" className="text-xs text-muted-foreground">
    Updated {formatRelativeTime(meta.data_as_of)}
  </Badge>
) : null}
```

**Lineups page (lineup-view.tsx):**

Same pattern. When the `lineups` prop/state is empty OR when `/api/lineups` returns an empty payload:

```tsx
import { Inbox } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";

if (!lineups || lineups.length === 0) {
  return (
    <EmptyState
      icon={Inbox}
      title="No lineups yet"
      description={`Lineup data for Week ${week} of ${season} is not available. This usually means the season hasn't started or this week's games are upcoming.`}
      dataAsOf={meta?.data_as_of ?? null}
    />
  );
}
```

Also surface `meta.data_as_of` at the top of the populated view.

**Preserve existing Phase 66 graceful defaulting.** These changes augment — do NOT replace — the 422 handling Phase 66 added. The existing code already assumes 200 with empty array is valid; this plan adds the visible empty-state render.
  </action>
  <verify>
    <automated>cd web/frontend && grep -n "EmptyState" src/features/nfl/components/prediction-cards.tsx src/features/nfl/components/lineup-view.tsx | tee /tmp/fe_integrations.txt && [ $(wc -l < /tmp/fe_integrations.txt) -ge 4 ] && npx tsc --noEmit 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "import.*EmptyState" web/frontend/src/features/nfl/components/prediction-cards.tsx` returns exactly 1 line
    - `grep -n "import.*EmptyState" web/frontend/src/features/nfl/components/lineup-view.tsx` returns exactly 1 line
    - `grep -n "<EmptyState" web/frontend/src/features/nfl/components/prediction-cards.tsx` returns at least 1 line
    - `grep -n "<EmptyState" web/frontend/src/features/nfl/components/lineup-view.tsx` returns at least 1 line
    - `grep -n "data_as_of\|dataAsOf" web/frontend/src/features/nfl/components/prediction-cards.tsx` returns at least 1 line
    - `grep -n "data_as_of\|dataAsOf" web/frontend/src/features/nfl/components/lineup-view.tsx` returns at least 1 line
    - `cd web/frontend && npx tsc --noEmit` exits 0
    - No regressions in existing tests: `cd web/frontend && npx vitest run src/features/nfl/components/__tests__/` exits 0 (if test dir exists)
  </acceptance_criteria>
  <done>Predictions and Lineups pages render EmptyState when data is empty; both surface dataAsOf chip; TypeScript clean.</done>
</task>

<task type="auto">
  <name>Task 3: Matchups page 503 handling + news page null-safety (FE-03, FE-04, FE-05 complete)</name>
  <files>
    - web/frontend/src/features/nfl/components/matchup-view.tsx
    - web/frontend/src/features/nfl/components/player-news-panel.tsx
    - web/frontend/src/features/nfl/components/news-feed.tsx
  </files>
  <read_first>
    - web/frontend/src/features/nfl/components/matchup-view.tsx
    - web/frontend/src/features/nfl/components/player-news-panel.tsx
    - web/frontend/src/features/nfl/components/news-feed.tsx
    - web/frontend/src/lib/api-client.ts (to confirm error shape for 503)
  </read_first>
  <action>
**Matchups page (matchup-view.tsx):**

When the `/api/teams/current-week` fetch returns 503 (offseason fallback) OR when the matchups payload is empty, render:

```tsx
import { CalendarOff } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";

// In the error boundary / catch block:
if (error?.status === 503 || (matchups && matchups.length === 0)) {
  return (
    <>
      <EmptyState
        icon={CalendarOff}
        title="No games this week"
        description="The season hasn't started yet — showing preseason preview below."
        dataAsOf={meta?.data_as_of ?? null}
      />
      {preseasonPreview ? <PreseasonPreview data={preseasonPreview} /> : null}
    </>
  );
}
```

Do NOT treat 503 as an error (no red styling, no error toast). It's an expected offseason state.

**News page (player-news-panel.tsx + news-feed.tsx):**

**player-news-panel.tsx** — if all 32 teams have `total_articles === 0`:

```tsx
import { Newspaper } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";

const anyTeamHasArticles = teams.some(t => t.total_articles > 0);

if (!anyTeamHasArticles) {
  return (
    <EmptyState
      icon={Newspaper}
      title="No news yet this week"
      description="News articles are still being aggregated. Check back in a few hours."
      dataAsOf={meta?.data_as_of ?? null}
    />
  );
}
```

**news-feed.tsx** — null-safety on individual items:

For each news item, render the headline always. Render the sentiment chip ONLY when `item.sentiment` is a valid number AND `item.summary` is a non-empty string. Prevent dangling sentiment numbers over empty article bodies:

```tsx
const hasValidSentiment =
  typeof item.sentiment === "number" &&
  !Number.isNaN(item.sentiment) &&
  typeof item.summary === "string" &&
  item.summary.length > 0;

return (
  <article>
    <h3>{item.headline}</h3>
    {hasValidSentiment ? (
      <SentimentChip score={item.sentiment} summary={item.summary} />
    ) : null}
    {item.event_flags && item.event_flags.length > 0 ? (
      <EventBadges flags={item.event_flags} />
    ) : null}
  </article>
);
```

Also: at top of news page, show the dataAsOf badge same pattern as Task 2.
  </action>
  <verify>
    <automated>cd web/frontend && grep -n "EmptyState\|hasValidSentiment" src/features/nfl/components/matchup-view.tsx src/features/nfl/components/player-news-panel.tsx src/features/nfl/components/news-feed.tsx | tee /tmp/fe3_integrations.txt && [ $(wc -l < /tmp/fe3_integrations.txt) -ge 4 ] && npx tsc --noEmit 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "<EmptyState" web/frontend/src/features/nfl/components/matchup-view.tsx` returns at least 1 line
    - `grep -n "<EmptyState" web/frontend/src/features/nfl/components/player-news-panel.tsx` returns at least 1 line
    - `grep -n "hasValidSentiment\|sentiment === null" web/frontend/src/features/nfl/components/news-feed.tsx` returns at least 1 line
    - `grep -n "503\|offseason" web/frontend/src/features/nfl/components/matchup-view.tsx` returns at least 1 line (offseason 503 handled)
    - `grep -n "data_as_of\|dataAsOf" web/frontend/src/features/nfl/components/matchup-view.tsx` returns at least 1 line
    - `grep -n "data_as_of\|dataAsOf" web/frontend/src/features/nfl/components/player-news-panel.tsx` returns at least 1 line
    - `cd web/frontend && npx tsc --noEmit` exits 0
    - No regressions in existing frontend tests: `cd web/frontend && npx vitest run` exits 0 (overall)
  </acceptance_criteria>
  <done>Matchups renders offseason empty state on 503; news page renders empty state when no articles; individual news items never show dangling sentiment chips over empty summaries.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Frontend → Backend API | Phase 66 server-side defaulting means frontend always receives well-shaped JSON on 200; only 503 for /api/teams/current-week is explicitly handled |
| Backend `meta.data_as_of` → Frontend display | Server-provided timestamp; treated as display-only (no business logic depends on it) |
| Props → EmptyState | All props typed; no user-controlled HTML injected |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-70-01 | Tampering | XSS via meta.data_as_of timestamp rendering | mitigate | React escapes all text content; `formatRelativeTime` produces plain strings; no `dangerouslySetInnerHTML` anywhere in this plan. |
| T-70-02 | Information disclosure | data_as_of timestamp revealing backend infrastructure | accept | Same exposure as Phase 63; ISO timestamp + relative time is not a sensitive signal. |
| T-70-03 | Denial of service | Malformed data_as_of crashing formatRelativeTime | mitigate | `formatRelativeTime` checks `Number.isNaN(then)` and returns "unknown" string; never throws. |
</threat_model>

<verification>
```bash
cd web/frontend
npx tsc --noEmit
npx vitest run
cd -
# Build check (catches JSX + import regressions):
cd web/frontend && npx next build 2>&1 | tail -10
```

Expected: TypeScript clean, all vitest tests pass (new EmptyState tests + existing regression tests), Next.js build succeeds.
</verification>

<success_criteria>
- Shared `<EmptyState />` component exists at `web/frontend/src/components/EmptyState.tsx`
- 8 unit tests in `web/frontend/src/components/__tests__/EmptyState.test.tsx` all pass
- Predictions page renders EmptyState when `/api/predictions` returns `[]`
- Lineups page renders EmptyState when lineups empty
- Matchups page renders offseason EmptyState on 503 from `/api/teams/current-week`; preseason preview rendered below if available
- News page renders empty state when all 32 teams have `total_articles === 0`
- News feed never shows dangling sentiment chips (requires `sentiment` number AND non-empty `summary`)
- All 4 pages surface `meta.data_as_of` as a freshness chip in the page header
- `EmptyState` shows the dataAsOf footer only when value is not null/undefined
- TypeScript compiles cleanly across the frontend (no new type errors)
- Existing frontend tests pass (no regressions)
- Next.js build succeeds
</success_criteria>

<output>
After completion, create `.planning/phases/70-frontend-empty-states/70-01-SUMMARY.md` covering:
- 8 files modified (component + helper + tests + 4 page integrations + 1 news feed null-safety)
- Test count delta (+8 EmptyState tests minimum)
- Screenshots or visual description of each empty state (optional; useful for user acceptance)
- Confirmation that TypeScript and Vitest pass, and `next build` succeeds
- Deferred follow-ups if any
</output>
