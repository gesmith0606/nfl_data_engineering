---
phase: SV2-website-news-feed
plan: 03
type: execute
wave: 2
depends_on: [SV2-01]
files_modified:
  - web/api/routers/news.py
  - web/api/services/news_service.py
  - web/api/models/schemas.py
  - web/frontend/src/app/dashboard/news/page.tsx
  - web/frontend/src/features/nfl/api/types.ts
  - web/frontend/src/features/nfl/api/nfl-api.ts
  - web/frontend/src/features/nfl/api/queries.ts
  - web/frontend/src/features/nfl/components/player-news-panel.tsx
  - web/frontend/src/features/nfl/components/news-feed.tsx
  - web/frontend/src/features/nfl/components/team-sentiment-badge.tsx
autonomous: false
requirements: [SV2-09, SV2-10, SV2-11, SV2-12, SV2-13]

must_haves:
  truths:
    - "User can view a dedicated news feed page showing all recent news, most recent first"
    - "User can filter news by All / Player / Team"
    - "Each news item shows source, timestamp, headline, sentiment badge, affected players/teams"
    - "Team sentiment badges appear on predictions page alongside game lines"
    - "Player news panel shows last-updated time and source labels"
  artifacts:
    - path: "web/frontend/src/app/dashboard/news/page.tsx"
      provides: "News feed page"
      min_lines: 40
    - path: "web/frontend/src/features/nfl/components/news-feed.tsx"
      provides: "News feed component with filters"
      min_lines: 80
    - path: "web/frontend/src/features/nfl/components/team-sentiment-badge.tsx"
      provides: "Team sentiment indicator badge"
      min_lines: 30
  key_links:
    - from: "web/frontend/src/app/dashboard/news/page.tsx"
      to: "/api/news/feed"
      via: "React Query fetch"
      pattern: "fetchNewsFeed"
    - from: "web/frontend/src/features/nfl/components/team-sentiment-badge.tsx"
      to: "/api/news/team-sentiment"
      via: "React Query fetch"
      pattern: "fetchTeamSentiment"
---

<objective>
Build the website news feed page and team sentiment display. Users get a dedicated
news page with filters, and team sentiment badges appear on the predictions page.

Purpose: This is the user-facing delivery of sentiment data. Without this, all the
backend sentiment work is invisible. The news feed is the primary engagement surface.

Output: New /dashboard/news page, team sentiment badges, enhanced player news panel.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/sentiment-v2/SV2-01-SUMMARY.md

@web/api/routers/news.py
@web/api/services/news_service.py
@web/api/models/schemas.py
@web/frontend/src/features/nfl/components/player-news-panel.tsx
@web/frontend/src/features/nfl/api/types.ts
@web/frontend/src/lib/nfl/types.ts
@web/frontend/CLAUDE.md

<interfaces>
<!-- Existing API schemas (web/api/models/schemas.py) -->
```python
class NewsItem(BaseModel):
    doc_id: Optional[str] = None
    title: Optional[str] = None
    source: str
    published_at: Optional[str] = None
    sentiment: Optional[float] = None
    confidence: Optional[float] = None
    category: Optional[str] = None
    events: Optional[Dict[str, bool]] = None
    player_id: Optional[str] = None
    player_name: Optional[str] = None
    team: Optional[str] = None
    body_snippet: Optional[str] = None

class Alert(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    alert_type: str
    headline: str
    sentiment: Optional[float] = None
    sentiment_multiplier: Optional[float] = None

class PlayerSentiment(BaseModel):
    player_id: str
    player_name: str
    season: int
    week: int
    sentiment_score: Optional[float] = None
    sentiment_multiplier: Optional[float] = None
```

<!-- Frontend conventions (from CLAUDE.md) -->
- React Query: void prefetchQuery() on server + useSuspenseQuery on client
- API layer: api/types.ts -> api/service.ts -> api/queries.ts
- Icons: only from @/components/icons
- Page headers: use PageContainer props
- Single quotes, no trailing comma
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Backend API endpoints for news feed and team sentiment</name>
  <files>
    web/api/routers/news.py,
    web/api/services/news_service.py,
    web/api/models/schemas.py
  </files>
  <action>
    **New API endpoints** in `web/api/routers/news.py`:

    1. `GET /api/news/feed` — Full news feed (all sources, all players/teams):
       - Query params: `season` (required), `week` (optional — if omitted, return all weeks), `source` (optional filter: "reddit", "rss", "sleeper"), `team` (optional 3-letter code), `player_id` (optional), `limit` (default 50, max 200), `offset` (default 0)
       - Returns `List[NewsItem]` ordered by `published_at` DESC
       - This is the main feed endpoint for the news page

    2. `GET /api/news/team-sentiment` — Team sentiment summary:
       - Query params: `season` (required), `week` (required)
       - Returns list of `TeamSentiment` objects (new schema)
       - Each: team, sentiment_score, sentiment_label ("positive"/"neutral"/"negative"), signal_count, sentiment_multiplier

    **New schema** in `web/api/models/schemas.py`:
    ```python
    class TeamSentiment(BaseModel):
        team: str
        season: int
        week: int
        sentiment_score: float = 0.0
        sentiment_label: str = "neutral"  # positive / neutral / negative
        signal_count: int = 0
        sentiment_multiplier: float = 1.0
    ```

    **Service layer** in `web/api/services/news_service.py`:
    - `get_news_feed(season, week, source, team, player_id, limit, offset)` — reads Silver signals, combines from all sources, sorts by date
    - `get_team_sentiment(season, week)` — reads Gold team sentiment Parquet
    - Both return empty results gracefully when no data exists

    Add "reddit" handling to existing service functions that currently only handle RSS/Sleeper sources.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python -c "from web.api.routers.news import router; print(f'Routes: {len(router.routes)}')"</automated>
  </verify>
  <done>
    - /api/news/feed returns paginated news items from all sources
    - /api/news/team-sentiment returns team sentiment for a given week
    - Both endpoints return empty lists gracefully when no data exists
    - Reddit source is handled alongside RSS and Sleeper
  </done>
</task>

<task type="auto">
  <name>Task 2: Frontend news page, feed component, and team sentiment badges</name>
  <files>
    web/frontend/src/app/dashboard/news/page.tsx,
    web/frontend/src/features/nfl/components/news-feed.tsx,
    web/frontend/src/features/nfl/components/team-sentiment-badge.tsx,
    web/frontend/src/features/nfl/api/types.ts,
    web/frontend/src/features/nfl/api/nfl-api.ts,
    web/frontend/src/features/nfl/api/queries.ts,
    web/frontend/src/features/nfl/components/player-news-panel.tsx
  </files>
  <action>
    **TypeScript types** (`api/types.ts`):
    Add `TeamSentiment` and `NewsFeedResponse` types matching the new API schemas.

    **API functions** (`api/nfl-api.ts`):
    - `fetchNewsFeed(season, week?, source?, team?, limit?, offset?)` -> calls `/api/news/feed`
    - `fetchTeamSentiment(season, week)` -> calls `/api/news/team-sentiment`

    **Query options** (`api/queries.ts`):
    - `newsFeedQueryOptions(season, week, source, team)` using key factory pattern
    - `teamSentimentQueryOptions(season, week)` using key factory pattern

    **News feed component** (`components/news-feed.tsx`):
    - Main feed display component used by the news page
    - Renders a list of news cards, each showing: source label, relative timestamp, headline, sentiment badge (colored dot + label), affected player/team name
    - Filter row at top: "All | Player News | Team News" toggle + optional search input
    - "Load more" button at bottom (pagination via offset)
    - Empty state: "No news available for this week"
    - Use existing `Card`, `Badge`, `Skeleton` from shadcn/ui
    - Source labels reuse the existing `SOURCE_LABELS` map from player-news-panel.tsx (extract to shared constant)
    - Follow single-quote, no trailing comma convention

    **Team sentiment badge** (`components/team-sentiment-badge.tsx`):
    - Small badge component: shows team abbreviation + colored sentiment indicator
    - Green for positive (score > 0.1), yellow for neutral, red for negative (score < -0.1)
    - Shows signal count as tooltip
    - Used on the predictions page next to each team in game cards

    **News page** (`app/dashboard/news/page.tsx`):
    - Full page at `/dashboard/news`
    - Uses `PageContainer` with pageTitle="News Feed", pageDescription="Latest NFL news and sentiment signals"
    - Season/week selector at top (reuse pattern from projections page)
    - Renders `NewsFeed` component
    - Server-side prefetch with `HydrationBoundary` + `dehydrate`

    **Enhanced player news panel** (`components/player-news-panel.tsx`):
    - Add "Last updated: X hours ago" below the panel title
    - Add Reddit to SOURCE_LABELS (already present, verify)
    - Add link icon for items with a URL -> opens original article

    Follow existing frontend conventions:
    - Single quotes, no trailing comma
    - Icons from @/components/icons only
    - React Query with key factories
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx tsc --noEmit 2>&1 | head -20</automated>
  </verify>
  <done>
    - /dashboard/news page renders with news feed and filters
    - Team sentiment badges display on predictions page
    - Player news panel shows last-updated time
    - TypeScript compiles without errors
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Visual verification of news feed and sentiment UI</name>
  <files>web/frontend/src/app/dashboard/news/page.tsx</files>
  <action>
    Verify the news feed page and team sentiment badges render correctly in the browser.
  </action>
  <what-built>
    News feed page at /dashboard/news with filtering (All/Player/Team), team sentiment
    badges on predictions page, and enhanced player news panel with last-updated time.
  </what-built>
  <how-to-verify>
    1. Start dev servers: `cd web && ./run_dev.sh` and `cd web/frontend && npm run dev`
    2. Visit http://localhost:3000/dashboard/news — verify news feed renders (may be empty if no data ingested)
    3. Check filter toggles work (All / Player / Team)
    4. Visit http://localhost:3000/dashboard/predictions — check for team sentiment badges
    5. Visit any player detail page — verify "Last updated" appears in news panel
    6. Check browser console for errors
  </how-to-verify>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx tsc --noEmit 2>&1 | head -5</automated>
  </verify>
  <done>User confirms news feed page, team sentiment badges, and player news panel look correct</done>
  <resume-signal>Type "approved" or describe any visual/functional issues</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| API -> Frontend | News data displayed to user |
| User input -> API | Search/filter params |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-SV2-07 | Injection | Search filter | mitigate | Query params validated by FastAPI/Pydantic, no raw SQL |
| T-SV2-08 | Info Disclosure | Body snippet | accept | Body text already truncated to 200 chars in schemas.py |
</threat_model>

<verification>
1. TypeScript compiles: `cd web/frontend && npx tsc --noEmit`
2. API endpoints respond: `curl http://localhost:8000/api/news/feed?season=2025`
3. Team sentiment endpoint: `curl http://localhost:8000/api/news/team-sentiment?season=2025&week=1`
4. News page loads in browser without console errors
</verification>

<success_criteria>
- News feed page accessible at /dashboard/news with working filters
- Team sentiment badges visible on predictions page
- Player news panel shows last-updated time
- Empty states handled gracefully (no data yet = "No news available")
- TypeScript compiles without errors
</success_criteria>

<output>
After completion, create `.planning/phases/sentiment-v2/SV2-03-SUMMARY.md`
</output>
