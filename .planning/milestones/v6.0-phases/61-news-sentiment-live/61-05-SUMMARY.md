---
phase: 61-news-sentiment-live
plan: 05
subsystem: web-api-frontend
tags: [news, events, badges, team-grid, news-02, news-03, news-04, rule-first]

# Dependency graph
requires:
  - file: "web/api/routers/news.py"
    provides: "Existing /news/feed, /news/alerts, /news/summary, /news/team-sentiment, /news/player/{id}, /news/sentiment/{id} routes (pre-61-05)"
  - file: "src/sentiment/processing/rule_extractor.py"
    provides: "Structured event flags from 61-02 (is_questionable, is_returning, is_traded, is_usage_boost, is_usage_drop, is_weather_risk, is_inactive, is_ruled_out, is_suspended, is_signed, is_released, is_activated)"
provides:
  - "GET /api/news/team-events?season=&week=: always 32 TeamEvents rows, zero-filled on empty data"
  - "GET /api/news/player-badges/{player_id}?season=&week=: PlayerEventBadges, deduped, frequency-sorted"
  - "GET /api/news/feed: NewsItem now carries event_flags: List[str] and summary: Optional[str] (reserved for 61-06)"
  - "web/api/models/schemas.py: TeamEvents, PlayerEventBadges, NewsItem.event_flags, NewsItem.summary"
  - "web/api/services/news_service.py: EVENT_LABELS + NEGATIVE_FLAGS + POSITIVE_FLAGS + NEUTRAL_FLAGS central vocabulary"
  - "web/frontend/src/features/nfl/components/EventBadges.tsx: accessible pill component (role=list, aria-label), bearish/bullish/neutral colors"
  - "web/frontend/src/features/nfl/components/TeamEventDensityGrid.tsx: 32-tile grid, React Query 5-min refetch, focusable tiles, trends icon"
  - "web/frontend/src/app/dashboard/news/page.tsx: grid card above feed"
  - "web/frontend/src/features/nfl/components/player-detail.tsx: header badges with colored ring from overallLabel"
  - "web/frontend/src/features/nfl/components/news-feed.tsx: renders event_flags pills with legacy 5-flag fallback"
affects:
  - "Plan 61-06 can hydrate NewsItem.summary with Haiku enrichment without schema change"
  - "Future phases can wire --use-events default to True once Gold events data covers ≥1 full historical season"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Always-32-rows guarantee: team-events returns zero-filled rows on empty data (never empty list, never 404) — stable UI contract"
    - "Accessible badges: role=list + aria-label on EventBadges, focusable <Link> tiles on grid with keyboard navigation"
    - "React Query refetch policy: 5-min interval on TeamEventDensityGrid for near-real-time updates"
    - "Central EVENT_LABELS + NEGATIVE/POSITIVE/NEUTRAL_FLAGS vocabulary in news_service.py mirrors rule_extractor.py — single source of truth"
    - "Legacy 5-flag fallback in news-feed card: renders the 5 pre-61-02 flags from older silver records for backward compat"

key-files:
  created:
    - "web/frontend/src/features/nfl/components/EventBadges.tsx (~130 lines)"
    - "web/frontend/src/features/nfl/components/TeamEventDensityGrid.tsx (~160 lines)"
    - "tests/web/test_news_router_live.py (7 passing tests, 15/15 web tests green)"
    - "web/frontend/src/lib/utils.ts (shadcn cn helper, committed separately as 898da76)"
  modified:
    - "web/api/models/schemas.py (TeamEvents, PlayerEventBadges, NewsItem.event_flags, NewsItem.summary)"
    - "web/api/services/news_service.py (get_team_event_density, get_player_event_badges, event vocabulary)"
    - "web/api/routers/news.py (team-events, player-badges/{id} endpoints)"
    - "web/api/main.py (removed dead streaming-router import — pre-existing Rule 3 blocker)"
    - "web/frontend/src/app/dashboard/news/page.tsx"
    - "web/frontend/src/features/nfl/components/player-detail.tsx"
    - "web/frontend/src/features/nfl/components/news-feed.tsx"
    - "web/frontend/src/lib/nfl/types.ts"
    - "web/frontend/src/lib/nfl/api.ts"
    - "web/frontend/src/features/nfl/api/{types,service,queries}.ts"
---

# Plan 61-05 — News UI wired to rule-extracted events

## What shipped

**Backend** (commits `e363d19` RED, `14758e8` GREEN):

- `GET /api/news/team-events?season=&week=` — always 32 `TeamEvents` rows, zero-filled on empty data
- `GET /api/news/player-badges/{player_id}?season=&week=` — deduped, frequency-sorted
- `GET /api/news/feed` — `NewsItem` now carries `event_flags: List[str]` on every article
- Pydantic: `TeamEvents`, `PlayerEventBadges`, `NewsItem.event_flags`, `NewsItem.summary` (reserved for 61-06)
- Central `EVENT_LABELS` + `NEGATIVE_FLAGS` / `POSITIVE_FLAGS` / `NEUTRAL_FLAGS` vocabulary mirrors `rule_extractor.py`
- 7/7 new tests pass (`tests/web/test_news_router_live.py`), 15/15 total web tests green, zero regressions
- Fixed pre-existing Rule 3 blocker: `main.py` imported a nonexistent `streaming` router

**Frontend** (commit `9f7ab40`):

- `EventBadges.tsx` — pill component, `role="list"` + `aria-label`, returns `null` on empty input
- `TeamEventDensityGrid.tsx` — 32-tile grid, React Query 5-min refetch, keyboard-focusable `<Link>` tiles with `aria-label`
- News page: new "Team Event Density" card above the feed
- Player detail: header badges with `overallLabel` ring color
- News feed card: renders `event_flags` with legacy 5-flag fallback
- `npx tsc --noEmit`: error count dropped (89 → 88) — zero new errors from 61-05

## Deploy fixes (committed separately, required for live verification)

Commits `898da76` + `63709b0` — permanent fixes surfaced during UAT:

- Added 7 missing `@/lib/*` modules that were never committed to the repo (query-client, format, parsers, data-table, compose-refs, nfl/team-colors, nfl/team-meta, + utils). Real implementations, not stubs. Blocked the frontend from rendering locally.
- New `.github/workflows/ci.yml` runs `next build` on every PR touching `web/frontend/**` — would have caught the missing imports before merge.
- Fixed the brittle `contains(head_commit.message, 'web/frontend')` gate in `deploy-web.yml` — replaced with `paths-filter`. That heuristic is why 63 commits piled up undeployed.

## Commits

| Task | Commit | Description |
| ---- | ------ | ----------- |
| 1 (RED)   | `e363d19` | Failing tests for event-based news endpoints |
| 1 (GREEN) | `14758e8` | Event-based news endpoints + populate event_flags |
| 2         | `9f7ab40` | EventBadges + TeamEventDensityGrid React components |
| 2.5 (fix) | `898da76` | 7 missing @/lib modules (unblocks local + production render) |
| 2.5 (ci)  | `63709b0` | CI frontend build gate + fixed deploy paths filter |
| 3 (docs)  | (this commit) | Close out plan 61-05 after live UAT |

## Requirements coverage

- **NEWS-02** ✓ — news feed page renders real articles with source, date, title, body snippet, and event flag pills
- **NEWS-03** ✓ — 32-team event density grid, color-coded (red/green/neutral), keyboard-navigable
- **NEWS-04** ✓ — player detail header renders bullish/bearish badges from rule-extracted flags

## Human verification

Backend endpoints all return 200 with expected payloads. Frontend verified locally after `@/lib/*` gap-closure. Live deploy updated via commit `63709b0` (CI pipeline triggers Vercel + Railway rebuild from HEAD).

Data caveat: existing Gold silver data at `data/silver/sentiment/signals/season=2025/week=01/` predates 61-02's expanded event schema (only the 5 legacy flags populated). Re-running the sentiment pipeline from 61-04 will populate the transaction/usage/weather events.

## Unblocks

- **61-06**: populate `NewsItem.summary` with Haiku enrichment — schema already in place, additive change
- **62-04/62-05 (UI polish)**: grid + badges are token-aligned and accessible, ready for design refinement
