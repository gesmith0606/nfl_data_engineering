---
phase: 70-frontend-empty-states
plan: 01
subsystem: frontend
tags: [frontend, empty-states, defensive-ux, freshness, sentiment-null-safety]
dependency_graph:
  requires:
    - phase-63: data_as_of meta pattern (useWeekParams dataAsOf)
    - phase-66: server-side graceful defaulting (200 + empty array on offseason)
  provides:
    - shared <EmptyState /> component (single source of truth)
    - formatRelativeTime helper (relative <7d, absolute otherwise)
    - sentiment chip null-safety contract (requires both number + summary)
  affects:
    - predictions, lineups, matchups, news pages
    - NewsCard + NewsItemRow rendering
tech_stack:
  added:
    - vitest@4.1.5 (devDependency) — component test harness
    - @vitejs/plugin-react@6 — React JSX transform for vitest
    - @testing-library/react@16 + @testing-library/jest-dom@6 + @testing-library/dom@10
    - jsdom@29 — DOM environment for vitest
  patterns:
    - shared component + page-level integration (avoids 4 near-duplicates)
    - freshness chip via useWeekParams / dataUpdatedAt (cache-time)
key_files:
  created:
    - web/frontend/src/components/EmptyState.tsx
    - web/frontend/src/components/__tests__/EmptyState.test.tsx
    - web/frontend/src/lib/format-relative-time.ts
    - web/frontend/src/test/setup.ts
    - web/frontend/vitest.config.ts
  modified:
    - web/frontend/src/features/nfl/components/prediction-cards.tsx
    - web/frontend/src/features/nfl/components/lineup-view.tsx
    - web/frontend/src/features/nfl/components/matchup-view.tsx
    - web/frontend/src/features/nfl/components/news-feed.tsx
    - web/frontend/src/features/nfl/components/player-news-panel.tsx
    - web/frontend/package.json (test scripts + dev deps — ignored by .gitignore, not tracked)
    - web/frontend/tsconfig.json (vitest/globals types — ignored by .gitignore, not tracked)
decisions:
  - Installed vitest + RTL stack (plan required it; frontend had no test harness).
  - Used @tabler/icons-react via @/components/icons (project CLAUDE.md convention) instead of lucide-react.
  - Used date-fns formatDistanceToNow (already in deps) for relative times.
  - Sourced dataAsOf from useWeekParams for predictions/lineups, from generated_at for matchups, from dataUpdatedAt for news.
  - Suppressed sentiment chip when EITHER sentiment OR summary is missing (not just sentiment === null).
metrics:
  duration_sec: 583
  tasks_completed: 3
  files_created: 5
  files_modified: 5
  test_delta: +10
  completed_date: 2026-04-24
---

# Phase 70 Plan 01: Empty States & Freshness Summary

**One-liner:** Shared `<EmptyState />` card with `dataAsOf` chip rolled out to all 4 top-level pages (predictions, lineups, matchups, news), plus sentiment-chip null-safety so dangling sentiment numbers over empty article bodies stop rendering.

## Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Shared EmptyState + 10 unit tests | `0214732` | EmptyState.tsx, EmptyState.test.tsx, format-relative-time.ts, vitest.config.ts, test/setup.ts |
| 2 | Predictions + Lineups EmptyState integration | `567900c` | prediction-cards.tsx, lineup-view.tsx |
| 3 | Matchups 503 + News null-safety | `ccf388a` | matchup-view.tsx, news-feed.tsx, player-news-panel.tsx |

## Acceptance Criteria — Must-Haves (all satisfied)

- **FE-01 Predictions**: `predictions.length === 0` + 404 + fetch error all render `<EmptyState title="No predictions yet" />` with `dataAsOf` chip.
- **FE-02 Lineups**: empty-offense payload and fetch error both render `<EmptyState />`; dataAsOf chip in header.
- **FE-03 Matchups**: `ApiError.status === 503` renders friendly card ("No games this week", NOT styled destructive) while keeping the team picker below it so users can still pick a team and see the preseason preview.
- **FE-04 News null-safety**: `hasValidSentiment` gate requires BOTH `typeof sentiment === 'number'` AND `summary` non-empty-trimmed-string; otherwise the sentiment chip (`NewsCard` + `NewsItemRow`) is omitted entirely. Empty feed + error states render `<EmptyState />`.
- **FE-05 Freshness chips**: All 4 pages surface `data_as_of` as a muted outline `<Badge>` in the header; `<EmptyState />` also shows it in its footer. When the source value is null/undefined, the chip is silently omitted (no "Unknown" placeholder).

## Verification

```
cd web/frontend
npx tsc --noEmit       → exit 0, no output (clean)
npx vitest run         → 10 pass / 0 fail (Task 1's EmptyState suite)
npx next build         → 18 pages compiled, TypeScript finished in 6.1s
```

All three gates green.

## Test Delta

+10 new tests in `src/components/__tests__/EmptyState.test.tsx` covering:
- title renders
- description renders when provided / omitted when not
- icon renders (Tabler SVG)
- `dataAsOf` null suppresses badge
- `dataAsOf` undefined suppresses badge
- recent (1h) renders "Updated ... hour ago"
- older (10d) renders absolute date "Updated Mon Day, YYYY"
- aria-live="polite" present
- within-minute renders "Updated just now"

## Deviations from Plan

### Rule 3 — Auto-fix blocking

**1. Installed vitest + @testing-library/* + jsdom**
- Found during: Task 1 startup.
- Issue: Plan mandated `npx vitest run` in acceptance criteria and 8 unit tests as a must-have artifact, but the frontend had no test harness at all (no vitest, no RTL, no jsdom in package.json).
- Fix: Added as devDependencies (`npm install --save-dev vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/dom`), plus created `vitest.config.ts` + `src/test/setup.ts`, plus added `test` / `test:watch` scripts.
- Commit: `0214732`

**2. Used @tabler/icons-react (via @/components/icons) instead of lucide-react**
- Found during: Task 1 component implementation.
- Issue: Plan specified `icon?: LucideIcon` but the project forbids direct `@tabler/icons-react` imports and explicitly only allows `@/components/icons` imports (per `web/frontend/CLAUDE.md` Critical Conventions: *"only import from @/components/icons, never from @tabler/icons-react directly"*). Installing lucide-react would have duplicated an icon library.
- Fix: Typed the icon prop as `Icon` from `@/components/icons` (Tabler `IconProps`). Tests use `Icons.news` from the registry.
- Commit: `0214732`

### Rule 2 — Auto-add missing critical functionality

**3. Strengthened sentiment null-safety**
- Found during: Task 3.
- Issue: Plan said "sentiment === null AND summary === null" but the audit finding was about *any* rendering of a sentiment chip without underlying rationale. The existing `news-feed.tsx` showed a "neutral" chip any time sentiment was missing (rendered `getSentimentLabel(null) === 'Neutral'`).
- Fix: `hasValidSentiment` = `typeof sentiment === 'number' && !Number.isNaN(sentiment) && typeof summary === 'string' && summary.trim().length > 0`. Stricter than plan's OR-of-nulls check; matches audit intent.
- Commit: `ccf388a`

## Known Stubs

None. All four empty states render real copy with real freshness when available, and omit the freshness chip cleanly when not.

## Threat Flags

None introduced. STRIDE mitigations from the plan's threat register (T-70-01 XSS on data_as_of, T-70-03 DoS from malformed timestamp) are implemented via:
- React text-node escaping (no `dangerouslySetInnerHTML`).
- `formatRelativeTime` returns `'unknown'` on `Number.isNaN(Date.parse(input))` — never throws.

## Deferred Follow-ups

- Package.json / tsconfig.json changes are on disk but NOT committed — the root `.gitignore` ignores `*.json` globally. Future CI that installs via `npm install` will fetch the new vitest stack from `node_modules` recreation; if anyone clones fresh they'll need the same `npm install ...` run. Recommend a follow-up phase to carve `!web/frontend/package.json` + `!web/frontend/tsconfig.json` + `!web/frontend/package-lock.json` out of the top-level ignore rule so the frontend's config becomes tracked alongside its source.
- The sentiment-chip gate in `news-feed.tsx` / `player-news-panel.tsx` uses `summary.trim().length > 0`; future phases could extend this to check `Math.abs(sentiment) >= 0.1` so chips don't render for indistinguishable-from-neutral scores.

## Self-Check: PASSED

Verified:
- `test -f web/frontend/src/components/EmptyState.tsx` → FOUND
- `test -f web/frontend/src/components/__tests__/EmptyState.test.tsx` → FOUND
- `test -f web/frontend/src/lib/format-relative-time.ts` → FOUND
- `test -f web/frontend/vitest.config.ts` → FOUND
- `test -f web/frontend/src/test/setup.ts` → FOUND
- Commit `0214732` in git log → FOUND
- Commit `567900c` in git log → FOUND
- Commit `ccf388a` in git log → FOUND
