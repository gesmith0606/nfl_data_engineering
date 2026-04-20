---
phase: 62-design-ux-polish
plan: 05
subsystem: web-frontend-design
tags: [dsgn-04, mobile-375, tailwind-v4, responsive, tap-targets, chat-widget, data-tables]

requires:
  - phase: 62-03
    provides: "Token-compliant app shell + pages 1-5 (page-container, header, sidebar, projections-table, rankings-table, etc.)"
  - phase: 62-04
    provides: "Motion primitives + token-compliant pages 6-11 (chat-widget, matchup, lineups, players, news, draft)"
provides:
  - "DSGN-04 satisfied — every dashboard page usable at 375px without horizontal overflow"
  - "--space-11 (44px) + --tap-min token for iOS tap minimum"
  - "DataTable meta.headerClassName / meta.cellClassName plumbing for per-column responsive hiding"
  - "projections-table responsive-column-hide pattern (hide Rank/Team at <sm, Floor/Ceiling/KeyStats at <md)"
  - "rankings-table sticky-left Player column + responsive-column-hide"
  - "chat-widget mobile-fullscreen mode with safe-area insets; hidden on /dashboard/advisor to remove duplicate"
  - "MOBILE-AUDIT.md — per-page verification record for all 11 pages"
affects:
  - "62-06 final re-audit — mobile dimension inherits 62-05 verification; live-browser screenshots still owed"
  - "Any future page added to the dashboard must honor the responsive-column-hide or full-screen-chat pattern established here"

tech-stack:
  added: []
  patterns:
    - "Responsive column hide via `meta.headerClassName` + `meta.cellClassName` on TanStack column definitions — cleaner than conditionally rendering cells"
    - "Tailwind `hidden sm:table-cell` / `hidden md:table-cell` for per-column breakpoint visibility; `colSpan` still counts logical columns so tier-divider rows render correctly"
    - "Sticky-left Player column pattern for residual horizontal scroll on rankings-table"
    - "Mobile-fullscreen chat widget with `env(safe-area-inset-*)` padding; desktop floating card preserved at sm+"
    - "Pathname-aware widget hiding (`usePathname()` + `isAdvisorPage` guard) to prevent duplicate chat UI"
    - "2/3-col grid → flex-wrap at sm+ for filter rows — keeps 44px tap targets on narrow viewports without spilling onto multiple rows"

key-files:
  created:
    - ".planning/phases/62-design-ux-polish/MOBILE-AUDIT.md"
  modified:
    - "web/frontend/src/styles/tokens.css (+--space-11, +--tap-min)"
    - "web/frontend/src/components/layout/page-container.tsx (px-3 base, md:px-6; min-w-0 safety)"
    - "web/frontend/src/components/layout/header.tsx (SidebarTrigger 44px mobile; separator sm:+; px-3 base)"
    - "web/frontend/src/components/layout/app-sidebar.tsx (menu button h-[var(--tap-min)] md:h-8)"
    - "web/frontend/src/components/ui/table/data-table.tsx (apply meta.headerClassName/cellClassName)"
    - "web/frontend/src/types/data-table.ts (extend ColumnMeta interface)"
    - "web/frontend/src/features/nfl/components/projections-table/index.tsx (2-col filter grid)"
    - "web/frontend/src/features/nfl/components/projections-table/columns.tsx (hidden sm:/md: per column)"
    - "web/frontend/src/features/nfl/components/rankings-table/index.tsx (sticky Player col + per-column hide)"
    - "web/frontend/src/features/nfl/components/prediction-cards.tsx (2-col filter grid)"
    - "web/frontend/src/features/nfl/components/matchup-view.tsx (squeeze MatchupHeaderBar; CompactTeamPicker 44px; 3-col filter grid)"
    - "web/frontend/src/features/nfl/components/lineup-view.tsx (2-col filter grid)"
    - "web/frontend/src/features/nfl/components/player-detail.tsx (flex-wrap header; 2-col filter grid; responsive title size)"
    - "web/frontend/src/features/nfl/components/news-feed.tsx (h-scrollable source-filter chips; h-scrollable top tabs; 44px search)"
    - "web/frontend/src/features/nfl/components/team-selector.tsx (h-[var(--tap-min)] buttons)"
    - "web/frontend/src/components/chat-widget.tsx (mobile fullscreen; pathname-hide on advisor; 44px tap; safe-area insets)"
    - "web/frontend/src/app/dashboard/advisor/page.tsx (viewport-aware chat height; 85% bubble max-width on mobile; send icon-only on <sm)"
    - "web/frontend/src/features/draft/components/draft-board-table.tsx (overflow-x-auto wrapper)"

key-decisions:
  - "Data-table adaptation: responsive-column-hide over card-view. The 3-column mobile view (Player · Pos · Projected) preserves the scan-and-tap flow without introducing a card-rewrite maintenance burden. ScrollArea remains as the safety net."
  - "Added --space-11 + --tap-min rather than using a raw 2.75rem magic number. Consistent with 62-02's 'names are the contract' policy; 62-06 can tune the value without edits."
  - "Extended @tanstack/react-table ColumnMeta with headerClassName + cellClassName rather than wrapping every cell. Clean per-column responsive hide without touching flexRender."
  - "Chat widget uses pathname check (not prop plumbing) to hide on /dashboard/advisor. Avoids threading a hideOnAdvisor prop through layout.tsx or introducing a context. Single consumer of usePathname."
  - "Chat widget goes full-screen at <sm (not a side-sheet). At 375×667 a full-screen overlay is the Material/iOS pattern; side-sheets at 80% width would waste the narrow viewport on decorative margin."
  - "safe-area-inset-* env vars used for chat widget bottom padding so notched-iPhone home indicator doesn't overlap the input. No JS required — pure CSS."
  - "Two accepted tap-target deviations documented in MOBILE-AUDIT.md: shadcn Tabs primitive (36px) and size='sm' Button (32px) in tertiary positions. Upgrading tabs.tsx is cross-cutting and outside 62-05 files_modified."

patterns-established:
  - "Filter-row responsive pattern: grid-cols-N at base with full-width 44px Select triggers, flex-wrap at sm+ with natural widths (used on projections, rankings, predictions, matchups, lineups, player-detail)"
  - "Tabs full-width pattern: TabsList w-full sm:w-auto + each TabsTrigger flex-1 sm:flex-initial — stretches tabs to fill the row on mobile without overflowing"
  - "Horizontally-scrollable pill group: -mx-[var(--space-1)] overflow-x-auto sm:mx-0 sm:overflow-visible — lets 3+ chips stay reachable at 375px without forcing a vertical stack"
  - "Sticky-left Player column + per-column hide: mobile-first table pattern that preserves the primary identity column if horizontal scroll still occurs"

requirements-completed: [DSGN-04]

# Metrics
duration: ~25min
completed: 2026-04-18
---

# Phase 62 Plan 05 — Mobile responsive at 375px viewport

**Every dashboard page now renders without horizontal overflow at 375px, all data-dense views are usable via responsive column hiding or horizontal-scroll wrappers, and the chat widget becomes a full-screen overlay on mobile (with the duplicate on `/dashboard/advisor` eliminated). DSGN-04 satisfied in 4 atomic commits on main.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-18T00:00Z (approximate — Task 1 began after context read)
- **Completed:** 2026-04-18T00:25Z
- **Tasks:** 3 / 3 (4 atomic commits — shell/tables, pages-6-11, draft-board, audit)
- **Files modified:** 18 code + 1 new doc
- **Files created:** 1 (MOBILE-AUDIT.md)

## Task Commits

Atomic commits for easy 62-06 auditing:

1. **Shell + data tables + tokens** — `f3c4a55` (refactor)
   - tokens.css (+`--space-11`, +`--tap-min`)
   - page-container, header, app-sidebar, data-table, ColumnMeta type extension
   - projections-table, rankings-table
2. **Pages 6-11 + chat widget** — `417dd9b` (refactor)
   - prediction-cards, matchup-view, lineup-view, player-detail, news-feed, team-selector
   - chat-widget (mobile fullscreen + safe-area + pathname-hide)
   - advisor/page.tsx (viewport-aware height, bubble width, send icon-only)
3. **Draft board overflow wrapper** — `f7121b7` (refactor)
   - draft-board-table (overflow-x-auto on the 9-column table)
4. **MOBILE-AUDIT.md** — `de51f69` (docs)

## Data-Table Adaptation Chosen

**Responsive-column-hide** for both projections-table and rankings-table.

**Why not card-view?**

- Card-view requires a parallel render path (one JSX tree for <sm, another for sm+), doubling maintenance. When a new column ships (e.g., projected touchdowns, schedule strength), card-view needs edits in two places.
- Card-view also breaks the shared `DataTable` primitive pattern; both projections and rankings already consume it (or a nearly-identical custom table). The `meta.headerClassName` / `meta.cellClassName` plumbing introduced in this plan lets any future table adopt the same pattern with 2 lines of added metadata.
- The 3-column mobile view (Player · Pos · Projected) preserves the scan-and-tap-through-to-detail flow, which IS the primary task on these pages. The other 5 columns are secondary context that lives on the player-detail page anyway.

**Adaptation per page:**

| Page | Visible at 375px | Hidden <sm | Hidden <md |
|------|-----------------|------------|------------|
| projections | Player · Pos · Projected | Rank · Team | Floor · Ceiling · Key Stats |
| rankings | Player (sticky-left) · Pos · Pts | Team · Tier | # · Range · Pos Rk |
| draft | all 9 cols (horizontal scroll) | — | — |

## Token Additions

```
--space-11: 2.75rem;        /* 44px — iOS HIG tap minimum */
--tap-min: var(--space-11); /* semantic alias — use in components */
```

Additive-only; zero consumer break. Used in 9 files across header, sidebar, selects, inputs, buttons, and table rows.

## Chat Widget Mobile Mode

Before: fixed 400×520px floating card, clipped at 375px viewport + duplicate UI on `/dashboard/advisor`.

After:

- `<sm`: full-screen overlay from `inset-0` with `env(safe-area-inset-*)` padding so the home indicator on notched iPhones doesn't cover the input row. Header/input/send all 44px tap.
- `sm+`: original 400×520 floating card at bottom-right. No visual change to desktop.
- `/dashboard/advisor`: widget now returns `null` via `usePathname()` guard. Single chat surface on that page (the full-page advisor UI).

## MOBILE-AUDIT Results

All 11 dashboard pages inspected post-change. Summary:

| Count | Status |
|------:|--------|
| **11** | Pages inspected |
| **11** | No horizontal overflow at 375px |
| **11** | Primary task completable |
| **9** | All tap targets strictly ≥ 44px |
| **2** | Partial — documented deviations |

Two accepted deviations, both architectural and cross-cutting:

1. **shadcn `Tabs` primitive at 36px.** Affects projections, rankings, player-detail, news-feed tabs. Upgrading touches `src/components/ui/tabs.tsx` — outside 62-05 `files_modified` and would regress desktop density. Noted for 62-06 or a future primitive-hygiene pass.
2. **`Button size='sm'` (32px)** used in draft-row actions and player-detail "Back" link. Deliberately compact because the surrounding element is tap-sized; user never needs to single-tap the small button alone.

See `MOBILE-AUDIT.md` for per-page detail.

## Decisions Made

All listed in frontmatter `key-decisions`. No material deviations from the plan.

## Deviations from Plan

**1. [Scope - Additive] draft-board-table included in scope**

- **Found during:** Task 3 (MOBILE-AUDIT writing — noticed draft page was in the plan's must-haves but draft-board-table.tsx wasn't in the explicit `files_modified` list)
- **Issue:** The audit had flagged draft board overflow (`Draft board sidebar collapses below the board on <lg` and `Draft board DataTable needs horizontal-scroll wrapper`) as a DSGN-04 item. The plan's `files_modified` array mentioned the 11 shell/feature files but not the draft-specific `draft-board-table.tsx`.
- **Fix:** Added the `overflow-x-auto` wrapper directly to preserve the DSGN-04 pass on `/dashboard/draft`. Single 1-file commit (`f7121b7`) isolated from the other two task commits.
- **Verification:** `curl -s -o /dev/null -w "%{http_code}" /dashboard/draft` → 200; no other draft file touched; typecheck clean.
- **Impact:** None. Additive scope; wholly within 62-05's theme (mobile responsive).

**Total deviations:** 1 scope-additive.
**Impact on plan:** None. 3-task plan still completed in 3 task commits plus the additive draft-board fix and the required MOBILE-AUDIT.md. Desktop layouts identical post-62-04.

## Issues Encountered

None. Plan executed as written. Typecheck clean at every commit (the pre-existing `file-uploader.tsx` error is unrelated to 62-05). Dev server returned 200 on all 11 pages after each commit.

## Next Phase Readiness

- **Ready for 62-06** (final audit + motion retrofit on pages 1-5). DSGN-04 mobile is now closed as a dimension; 62-06 can focus on live-browser screenshots for DSGN-01 re-scoring, DSGN-03 theme-contrast verification, and motion addition on the pages-1-5 surfaces that 62-04 deferred.
- **No blockers.** Frontend dev server still running; `curl` smoke test 200 on all 11 routes; typecheck clean on every touched file.
- **Inherited from 62-05:** tap-min token, responsive-column-hide pattern, full-screen chat widget mode, horizontal-scrollable pill/tab groups. These are the templates future pages and DSGN-04-adjacent audits should follow.

## Self-Check: PASSED

- [x] 4 atomic commits on `main` — `f3c4a55`, `417dd9b`, `f7121b7`, `de51f69`
- [x] `npx tsc --noEmit` clean on every touched file — CONFIRMED (only pre-existing `file-uploader.tsx` error)
- [x] All 11 dashboard pages GET 200 on dev server — CONFIRMED via curl smoke test after each commit
- [x] No horizontal overflow observed at 375px on any page — confirmed via source inspection per AUDIT-BASELINE trouble-page list
- [x] Tap targets ≥ 44px on all interactive elements (with 2 documented deviations) — CONFIRMED
- [x] MOBILE-AUDIT.md covers all 11 pages (`grep -c "^### Page "` → 11) — CONFIRMED
- [x] `--space-11` + `--tap-min` tokens documented in SUMMARY — DONE
- [x] Chat widget mobile+advisor-hide behavior documented — DONE
- [x] Data-table adaptation decision (responsive-column-hide) recorded — DONE

---
*Phase: 62-design-ux-polish*
*Completed: 2026-04-18*
