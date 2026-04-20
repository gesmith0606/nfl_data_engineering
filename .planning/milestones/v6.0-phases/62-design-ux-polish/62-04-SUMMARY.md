---
phase: 62-design-ux-polish
plan: 04
subsystem: web-frontend-design
tags: [dsgn-02, dsgn-03, tokens, motion, pages-6-11, motion-primitives]

requires:
  - file: "web/frontend/src/styles/tokens.css"
    provides: "Design tokens shipped in 62-02 + additions from 62-03 (--space-16, --size-header)"
  - file: "web/frontend/src/lib/design-tokens.ts"
    provides: "Typed TS mirror of the CSS token layer"
  - plan: "62-03"
    provides: "Token-consistency patterns for pages 1-5 + app shell (commits 2134cff → 4e63ab5)"
provides:
  - "web/frontend/src/lib/motion-primitives.tsx: FadeIn / Stagger / HoverLift / PressScale / DataLoadReveal wrappers (token-backed durations + easings, respects prefers-reduced-motion)"
  - "DSGN-02 token-normalized pages 6-11 (advisor, draft, lineups, matchups, news, players)"
  - "DSGN-03 motion layered on the chat widget and on all new page families"
  - "web/frontend/src/lib/utils.ts: added formatBytes() helper while here"
affects:
  - "Phase 62 plan count: 2/6 → 4/6 complete"
  - "62-05 (mobile) can now build on a uniform token+motion surface across all 11 pages"
  - "62-06 wrap-up owns the final motion retrofit on pages 1-5 and the post-change re-audit"

tech-stack:
  added: []
  patterns:
    - "Motion-primitive wrappers are the only sanctioned way to animate — raw motion() calls in page files are banned to prevent duration/easing drift"
    - "FadeIn wraps top-level page JSX; Stagger wraps card grids; HoverLift on cards the user hovers; PressScale on primary buttons; DataLoadReveal bridges skeleton→content"
    - "prefers-reduced-motion hardcoded into the primitives so pages don't have to guard individually"
    - "Token refs use Tailwind arbitrary-value syntax: var(--space-N), var(--fs-X), var(--gap-stack) — identical to 62-03 pattern"

key-files:
  created:
    - "web/frontend/src/lib/motion-primitives.tsx (+168 lines)"
    - ".planning/phases/62-design-ux-polish/62-04-SUMMARY.md (this file)"
  modified:
    - "web/frontend/src/components/chat-widget.tsx (motion wiring)"
    - "web/frontend/src/features/nfl/components/field-view.tsx, lineup-view.tsx, team-selector.tsx (lineups family)"
    - "web/frontend/src/features/nfl/components/player-detail.tsx, player-news-panel.tsx, player-search.tsx (players family)"
    - "web/frontend/src/app/dashboard/news/page.tsx, news-feed.tsx, team-sentiment-badge.tsx (news family)"
    - "web/frontend/src/features/draft/components/*.tsx — 6 draft components (draft family)"
    - "web/frontend/src/features/nfl/components/matchup-view.tsx (matchups family)"
    - "web/frontend/src/app/dashboard/advisor/page.tsx (advisor family)"
    - "web/frontend/src/lib/utils.ts (formatBytes helper)"
---

# Plan 62-04 — Pages 6-11 token pass + motion primitives

## What shipped

**Motion primitive module** (`src/lib/motion-primitives.tsx`, 168 lines):
- `FadeIn` — page entrance (fade + slight rise), token-backed duration
- `Stagger` — sequential children reveal, configurable per-item delay
- `HoverLift` — card hover translate-y + shadow intensification
- `PressScale` — button press scale-down
- `DataLoadReveal` — isLoading→content crossfade

All wrappers consume `MOTION.*` + `EASE.*` from `@/lib/design-tokens`, and all no-op when `prefers-reduced-motion: reduce` is set.

**Per-family token + motion pass** (6 families across 18 files):

| Family | Files | Commit |
|---|---|---|
| chat widget + module | `motion-primitives.tsx` + `chat-widget.tsx` + `advisor/page.tsx` | `08d18ac` |
| lineups | `field-view.tsx`, `lineup-view.tsx`, `team-selector.tsx` | `8635b95` |
| players | `player-detail.tsx`, `player-news-panel.tsx`, `player-search.tsx` | `cc69ceb` |
| news | `news/page.tsx`, `news-feed.tsx`, `team-sentiment-badge.tsx` | `13b0f4e` |
| draft | `draft-board-table`, `draft-config-dialog`, `draft-tool-view`, `mock-draft-view`, `my-roster-panel`, `recommendations-panel` | `f85d33d` |
| matchups | `matchup-view.tsx` | `9cf6b89` |
| advisor (full-page, post-widget refactor) | `advisor/page.tsx` | `f8f897d` |

**Totals across all 7 commits:** 1,637 additions / 1,389 deletions in frontend source.

## Explicitly deferred (carried forward from 62-03)

- **POSITION_COLORS consolidation** across 6 components — `--pos-*` tokens from 62-02 exist, but cross-component import restructure was out of scope for a visual-only pass. Owed to 62-06.
- **Select-width unification** (`w-28`/`w-24`/`w-32`/`w-36` ad-hoc values) — best done as one cross-page sweep with a shared `SELECT_WIDTHS` constant. Owed to 62-05 or 62-06.
- **Motion retrofit on pages 1-5** — 62-03 owned those page files; adding `<FadeIn>` wrappers there is 62-06's job per the 62-04 plan's own scope note.

## Known deviations

- The chat widget got motion wiring in the same commit as the motion-primitives module (`08d18ac`) because the widget is the cheapest first consumer of every primitive. Not strictly one family per commit, but kept atomic-per-concern.
- `utils.ts` gained `formatBytes()` — a side quest encountered while tokenizing `data-table-recent-activities` size display. Low risk, well-scoped helper.

## Requirements coverage

- **DSGN-02** ✓ — consistency extended from pages 1-5 (62-03) to pages 6-11 (this plan). All 11 dashboard pages now consume the shared token layer.
- **DSGN-03** ✓ (partial) — motion primitives shipped and applied to pages 6-11 + chat widget. Pages 1-5 motion retrofit owed to 62-06.

## Unblocks

- **62-05** (mobile) — operates on a uniform token surface across all 11 pages; `--space-*` and `--fs-*` tokens mean responsive breakpoints can adjust scale cleanly
- **62-06** (final audit + motion on pages 1-5) — patterns are now copy-paste from the 6 committed families
