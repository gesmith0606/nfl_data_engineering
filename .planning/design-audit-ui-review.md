# Frontend Design Audit — UI Review (Retroactive 6-Pillar)

**Audited:** 2026-06-11
**Baseline:** Abstract 6-pillar standards (no UI-SPEC.md exists for this frontend)
**Target:** `web/frontend/` (Next.js 16 App Router, shadcn/ui, built on `next-shadcn-dashboard-starter`)
**Screenshots:** Captured from live deployment `https://frontend-jet-seven-33.vercel.app` (no local dev server running) — 9 captures in `.planning/ui-reviews/design-audit-20260611-083436/` (gitignored)
**Registry audit:** Skipped — no UI-SPEC.md declaring third-party registries (shadcn `components.json` present, official registry only)

---

## Critical Cross-Cutting Finding: Deployment Drift (BLOCKER)

The live Vercel deployment **does not match the current source code.** Evidence:

1. Live `/dashboard/predictions` renders the string `"No predictions available for this week."` — this string **does not exist anywhere in the current codebase** (current code renders `EmptyState` with `"No predictions yet"`, `prediction-cards.tsx:286`).
2. Live predictions page defaults to **2024 / Week 1** with a dead-end empty card. Current source uses `useWeekParams()` (`src/hooks/use-week-params.ts`, Phase 66 HOTFIX-04/05) which resolves the latest populated week with a 3-season walk-back. The deployed build predates this fix.
3. Live mobile projections (375px) show Rank/Team columns and horizontal cutoff. Current source hides those columns below `sm:` (`projections-table/columns.tsx:23-24`, Phase 62-05 DSGN-04). The deployed build predates the mobile adaptation work.

**Impact:** Users receive none of the Phase 62/66/70 UX work (empty states, freshness badges, latest-week defaults, mobile adaptations, design tokens). Every experience-pillar improvement in source is currently theoretical. This mirrors the TD-09 stale-Railway-image incident — the same failure mode now exists on the Vercel side.

**Scoring note:** Pillars are scored against the **source code** (the submitted implementation), with deployment drift counted as a BLOCKER under Experience Design since the shipped experience breaks user task completion.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 2/4 | Developer-facing error copy ("Ensure the API is running on localhost:8000") shipped in 4 production components; mislabeled "Rank" column; page description contradicts data shown |
| 2. Visuals | 3/4 | Strong hierarchy and skeleton fidelity, but the landing page's focal charts render fabricated data; redundant Tier column; low-contrast Range bars |
| 3. Color | 2/4 | 105 raw palette classes across 16 feature files despite a purpose-built `--pos-*` token family; semantic miscue (red "0 Bearish Signals"); hardcoded hex backgrounds |
| 4. Typography | 3/4 | Excellent token discipline (300+ `var(--fs-*)` uses) but 4 active font weights and ~48 residual ad-hoc `text-*` classes coexist with the token scale |
| 5. Spacing | 4/4 | 600+ semantic token uses on a 4px grid, 44px tap targets enforced; only ~20 arbitrary values remain, mostly chart/layout-specific |
| 6. Experience Design | 2/4 | Source-level state handling is excellent, but the deployment is stale (BLOCKER), and the projections/news pages ignore the codebase's own week-resolution and URL-state conventions; hardcoded mutually-inconsistent model metrics |

**Overall: 16/24**

---

## Top 3 Priority Fixes

1. **Redeploy the frontend and add a deploy-verification gate (BLOCKER)** — The live site predates Phase 62/66/70 work: predictions land on a 2024 W1 dead end, mobile tables overflow, empty states lack guidance. Users see none of the implemented quality. Fix: trigger a fresh Vercel build from `main`, then verify by checking a sentinel string (e.g., `"No predictions yet"`) on the live predictions page; add this check to the sanity-check deploy gate alongside the existing backend checks.
2. **Replace fabricated/hardcoded model metrics with API-driven values (BLOCKER)** — `accuracy-chart.tsx:13-31` ships an invented 18-week MAE/correlation series; `mae-chart.tsx:13-17` hardcodes Phase-53 numbers (overall 4.91); `accuracy-dashboard.tsx:24-36` hardcodes Phase-54 numbers (4.77); `stat-cards.tsx:59-82` hardcodes 4.77 MAE and "571 Tests Passing" (actual: 1379 tests, v4.2 MAE 4.71). Three different MAE values are shown simultaneously on a product whose core pitch is model accuracy. Fix: serve metrics from `/api/projections/accuracy` (or a build-time generated JSON artifact from `backtest_projections.py` output) and delete all four hardcoded constants.
3. **Remove developer-facing error copy from production (BLOCKER)** — `projections-table/index.tsx:139`, `rankings-table/index.tsx:240`, `draft-tool-view.tsx:191` ("Ensure the API is running on localhost:8000") and `player-detail.tsx:72` ("Ensure the API is running") render on a public Vercel site where users cannot run anything on localhost. Fix: route all four through the shared `EmptyState` error variant with the established copy pattern ("…unavailable right now. Please try again in a moment.").

---

## Detailed Findings

### Pillar 1: Copywriting (2/4)

**BLOCKER — Developer error copy in production.** Four components instruct end users to start a local API server:
- `src/features/nfl/components/projections-table/index.tsx:139` — "Failed to load projections. Ensure the API is running on localhost:8000."
- `src/features/nfl/components/rankings-table/index.tsx:240` — "Failed to load rankings. Ensure the API is running."
- `src/features/draft/components/draft-tool-view.tsx:191` — "…Ensure the API is running on localhost:8000."
- `src/features/nfl/components/player-detail.tsx:72` — "Failed to load player details. Ensure the API is running."

These coexist with the correct pattern already in the codebase (`prediction-cards.tsx:294`, `lineup-view.tsx:110`, `news-feed.tsx:918`: "…unavailable right now. Please try again in a moment.") — the fix is consolidation, not invention.

**WARNING — Mislabeled "Rank" column.** `projections-table/columns.tsx:28-37` binds `position_rank` to a header titled "Rank". Live screenshot confirms the confusion: the All-positions view shows rank sequence 1,2,3,4,5,1,1,6,2,7 with no visual cue that rank resets per position. The rankings page solves this correctly with a "Pos Rk" column — reuse that label.

**WARNING — Page description contradicts displayed data.** `/dashboard/projections` is described as "Weekly fantasy point projections with floor/ceiling ranges" (`app/dashboard/projections/page.tsx` via PageContainer), but 2026 Week 1 serves season-long preseason totals (483.1 pts, "4172 pass yds" per the live capture). No mode indicator distinguishes preseason season-long from weekly projections.

**WARNING — Marketing copy drift.** `stat-cards.tsx:66-69` says "571 Tests Passing / Full test suite coverage" — the suite is 1379 tests. A stale brag is worse than no brag. (Also a Pillar 6 data-integrity issue.)

**Positive evidence:** `EmptyState` copy is genuinely good — specific, contextual, action-oriented: `lineup-view.tsx:117` explains *why* data is missing ("This usually means the season has not started…"); `prediction-cards.tsx:287` says when to return ("Check back when games are scheduled"); `my-roster-panel.tsx:44` gives the next action ("Click 'Draft' on any player to start"). `player-search.tsx:69` echoes the query in the no-results message.

### Pillar 2: Visuals (3/4)

**WARNING — Fabricated data is the dashboard's focal point.** The landing page's two charts — the visual anchors of the product — render synthetic data: `accuracy-chart.tsx:13-31` is a hand-authored smooth curve labeled "Weekly Projection Accuracy / MAE trend over the season," and `mae-chart.tsx` shows stale per-position values. Visually polished, substantively hollow.

**WARNING — Redundant Tier column.** Rankings table (live capture) renders an "Elite" group header band *and* an identical "Elite" badge on every row within the group, plus the row band tint — triple encoding of one fact. Drop the per-row badge when grouped.

**WARNING — Range mini-bar is illegible.** Rankings "Range" column renders a gray-on-gray pill with tiny flanking numbers (live capture); the filled region's meaning (floor→ceiling within what bounds?) is not decodable and has no legend or tooltip.

**WARNING — Template theme selector dilutes the product.** `header.tsx:32` ships `ThemeSelector` exposing 10 starter-kit themes (`styles/themes/`: neobrutualism, whatsapp, notebook, zen, claude…) on an NFL analytics product. This is template residue presented as a product feature; it also multiplies the QA surface (every raw palette class in Pillar 3 must survive 10 themes × 2 modes).

**Positive evidence:** Clear page-level hierarchy via `PageContainer` (`pageTitle`/`pageDescription`, sticky header); stat cards use container queries for responsive value sizing (`stat-cards.tsx:31`); prediction cards have a strong identity (team-color gradient strip, `prediction-cards.tsx:59-64`); skeletons mirror final layout shape (`projections-table/index.tsx:115-133`, `prediction-cards.tsx:260-282`); icon-only controls carry aria-labels (`chat-widget.tsx:494,539,549`).

### Pillar 3: Color (2/4)

**WARNING — Token system built, migration unfinished.** `styles/tokens.css:134-175` defines an OKLCH `--pos-*` family explicitly created to "consolidate the 6 duplicated POSITION_COLORS maps" — yet duplicates remain in `recommendations-panel.tsx`, `draft-board-table.tsx`, `accuracy-dashboard.tsx`, and an inline `colorMap` in `projections-table/columns.tsx:107-113` (raw `bg-red-100 text-red-800 dark:…` chains). 105 raw palette utility classes survive across 16 feature files (heaviest: `news-feed.tsx` 28, `matchup-view.tsx` 17, `rankings-table/index.tsx` 8, `draft-board-table.tsx` 8). Each one is a theme-break risk across the 10 shipped themes.

**WARNING — Semantic color miscue.** News overview (live capture, `news-feed.tsx`) renders "Bearish Signals **0**" in destructive red and "Neutral **31**" in warning amber. The color encodes the *category label*, not the state — a red zero reads as an alarm when it is good news. Color the value by significance (muted when 0), not by category.

**WARNING — Hardcoded hex outside the token system.** `matchup-view.tsx:680` `backgroundColor: '#0f1318'` (fixed near-black panel regardless of theme) and `:571` `'#333'` fallback; `field-view.tsx:124` field-green gradient (defensible as a "field" metaphor, but still untokenized); `cta-github.tsx:11` `hover:text-[#24292e]`.

**Positive evidence:** Theme color architecture is sound (OKLCH semantic tokens per theme, `--chart-1..5` used in charts); primary accent is used sparingly (12 occurrences in feature code — no accent overuse); team colors centralized in `lib/nfl/team-colors` and applied via inline style by design (32 dynamic brand colors don't belong in utility classes).

### Pillar 4: Typography (3/4)

**Evidence:** Token scale (`--fs-micro` through `--fs-h1`, `tokens.css:26-57`) is the dominant pattern — 307 `var(--fs-*)` references in feature/app/component code, with line-height always paired. The scale itself is disciplined (8 sizes, WCAG-conscious 16px body floor, documented intent per size).

**WARNING — Dual systems still coexist.** 48 ad-hoc Tailwind size classes remain in feature/app code (30 `text-sm`, 15 `text-xs`, plus `text-lg/xl/2xl`) alongside their token equivalents — same rendered size today, but two sources of truth that can drift if the token values are tuned (which `tokens.css:13` explicitly anticipates: "Values may be tuned").

**WARNING — Weight proliferation.** Four active weights in feature code (79 `font-medium`, 50 `font-semibold`, 33 `font-bold`, 1 `font-extrabold`). Bold + semibold + medium within dense tables (e.g., `columns.tsx:34` medium rank, `:55` medium name, `:128` bold projected points) mostly works, but exceeds the ≤2-weight guideline and there is no documented rule for when each applies.

**Positive evidence:** `tabular-nums`/`font-mono` consistently applied to numeric columns (`columns.tsx:34,110,128`; `prediction-cards.tsx:110,142`) — correct for data-dense tables.

### Pillar 5: Spacing (4/4)

**Evidence:** The 4px-grid token system (`tokens.css:66-94`) is the real spacing language of the codebase: 167× `--space-2`, 134× `--space-3`, 103× `--space-4`, 41× `--gap-stack`, 13× `--gap-section`, with *semantic* aliases so intent is documented. `--tap-min` (44px, WCAG 2.5.5) is enforced on mobile selects (`prediction-cards.tsx:210,223,236`), table row hit areas (`columns.tsx:52`), and the sidebar trigger (`header.tsx:16`).

**Minor (no score impact):** ~20 arbitrary bracket values remain (`[10px]`, `[15px]`, `[600px]`, `[8rem]` …), concentrated in chart/visualization components where fixed dimensions are defensible; residual raw classes (`py-2`, `px-2`, `gap-2`) all land on the 4px grid, so visual rhythm is unbroken.

### Pillar 6: Experience Design (2/4)

**BLOCKER — Deployment drift (see top section).** The implemented experience is not the shipped experience. Live predictions = 2024 W1 dead end with no recovery action; live mobile tables overflow; live empty states lack freshness/context. Until redeployed, every improvement below is unrealized.

**BLOCKER — Hardcoded, mutually contradictory model metrics.** Three different overall MAE values are presented as current across surfaces a user can see in one session: 4.91 (`mae-chart.tsx:17`), 4.77 (`stat-cards.tsx:59`, `accuracy-dashboard.tsx:26`), and an invented weekly series ending ~4.5 (`accuracy-chart.tsx`). Actual v4.2 production is 4.71. For an accuracy-led product, displaying conflicting invented numbers breaks the core trust loop.

**WARNING — Inconsistent week/season defaults.** `projections-table/index.tsx:31-32` hardcodes `useState(2026)` / `useState(1)` and `app/dashboard/news/page.tsx:35` hardcodes `useState(2025)` — both bypass `useWeekParams()` (the documented HOTFIX-04/05 pattern used by predictions and lineups) and bypass the codebase's own nuqs URL-state convention (frontend CLAUDE.md). Consequences: projections/news selections are not bookmarkable, and news lands on a season-old week by default.

**WARNING — No retry affordance on errors.** Error states (`EmptyState` variants and the inline error cards) tell users to "try again in a moment" but render no Retry button; recovery requires a full page reload. React Query's `refetch` is one prop away.

**Positive evidence (what keeps this at 2, not 1):**
- Loading: skeletons on every data surface, shaped like the final layout (`prediction-cards.tsx:260-282`, `projections-table/index.tsx:115-133`, `page-container.tsx:6-19`).
- Empty: shared `EmptyState` (`components/EmptyState.tsx`) with `aria-live='polite'`, optional freshness badge ("Updated 2 days ago"), adopted across 5 surfaces; distinguishes 404-empty from error (`prediction-cards.tsx:188,283-303`).
- Defaults: `useWeekParams` resolves latest populated week with 3-season walk-back and per-source resolution (predictions vs projections golds) — thoughtful offseason handling.
- Mobile: 2-column filter grids below `sm:` (`prediction-cards.tsx:208`), column hiding strategy documented in-code (`columns.tsx:10-22`), 44px tap targets.
- Accessibility: aria-labels on icon buttons, `aria-label` on edge badges (`prediction-cards.tsx:91`), keyboard shortcuts via kbar.

---

## Prioritized Remediation List

| # | Severity | Item | Files |
|---|----------|------|-------|
| 1 | BLOCKER | Redeploy frontend to Vercel; add live-sentinel check to the deploy sanity gate so frontend staleness is detected like TD-09 backend staleness | Vercel project config; `scripts/` sanity checker |
| 2 | BLOCKER | Replace 4 hardcoded/fabricated metric sources with API- or artifact-driven values; one source of truth for MAE | `stat-cards.tsx:57-82`, `mae-chart.tsx:13-17`, `accuracy-chart.tsx:13-31`, `accuracy-dashboard.tsx:24-36` |
| 3 | BLOCKER | Replace "localhost:8000" developer error copy with shared `EmptyState` error variant + add Retry button wired to React Query `refetch` | `projections-table/index.tsx:139`, `rankings-table/index.tsx:240`, `draft-tool-view.tsx:191`, `player-detail.tsx:72` |
| 4 | WARNING | Migrate projections table and news page to `useWeekParams`/nuqs URL state; retitle "Rank" → "Pos Rk"; add a "Preseason (season-long)" mode indicator when week data is season totals | `projections-table/index.tsx:31-32`, `app/dashboard/news/page.tsx:35`, `projections-table/columns.tsx:31` |
| 5 | WARNING | Finish color consolidation: migrate 4 remaining POSITION_COLORS/colorMap duplicates to `--pos-*` tokens; sweep the 105 raw palette classes (start with `news-feed.tsx`, `matchup-view.tsx`); fix red "0 Bearish Signals" semantic miscue; tokenize `#0f1318`/`#333` | `columns.tsx:107-113`, `recommendations-panel.tsx`, `draft-board-table.tsx`, `accuracy-dashboard.tsx`, `news-feed.tsx`, `matchup-view.tsx:571,680` |
| 6 | WARNING | Decide on the theme selector: either remove the 10 template themes (keep light/dark) or commit to QA-ing every raw color against all themes | `header.tsx:32`, `styles/themes/*` |
| 7 | WARNING | De-duplicate rankings Tier encoding (drop per-row badge inside tier groups); add legend/tooltip to the Range mini-bar | `rankings-table/index.tsx` |
| 8 | LOW | Converge residual ad-hoc `text-sm`/`text-xs` onto `var(--fs-*)`; document a 2-3 weight usage rule; retire `font-extrabold` one-off | feature-wide |
| 9 | LOW | Remove unused template residue (demo-form, file-uploader, kanban, org-switcher paths) to shrink surface area | `components/forms/demo-form.tsx`, `components/file-uploader.tsx`, `components/ui/kanban.tsx`, `components/org-switcher.tsx` |

---

## Files Audited

**Read in full:** `app/page.tsx`, `app/dashboard/layout.tsx`, `app/dashboard/page.tsx`, `app/dashboard/predictions/page.tsx`, `config/nav-config.ts`, `styles/tokens.css`, `components/EmptyState.tsx`, `components/layout/header.tsx`, `components/layout/page-container.tsx`, `hooks/use-week-params.ts`, `features/nfl/components/stat-cards.tsx`, `features/nfl/components/prediction-cards.tsx`, `features/nfl/components/projections-table/index.tsx`, `features/nfl/components/projections-table/columns.tsx`

**Read in part / grep-audited:** `accuracy-chart.tsx`, `mae-chart.tsx`, `accuracy-dashboard.tsx`, `matchup-view.tsx`, `field-view.tsx`, `player-detail.tsx`, `news-feed.tsx`, `rankings-table/index.tsx`, `draft-tool-view.tsx`, `recommendations-panel.tsx`, `draft-board-table.tsx`, `my-roster-panel.tsx`, `player-search.tsx`, `player-news-panel.tsx`, `lineup-view.tsx`, `chat-widget.tsx`, `app/dashboard/news/page.tsx`, `app/dashboard/advisor/page.tsx`, plus repo-wide greps across `src/features`, `src/app`, `src/components`

**Screenshots (live deployment, 2026-06-11):** dashboard (1440/375), projections (1440/375), predictions, accuracy, news, lineups, rankings — `.planning/ui-reviews/design-audit-20260611-083436/`
