---
audit_version: baseline
pages_audited: 11
live_url: https://frontend-jet-seven-33.vercel.app
rubric: design-engineer v1 (8 dimensions)
method: source-code inspection (no live browser access in executor environment)
method_gap: "Live screenshots at 375/768/1440px not captured. Scores derive from reading every page.tsx + its feature component + shared primitives (page-container, app-sidebar, theme.css, globals.css). 'Observed' in the rubric is interpreted as 'inspected in JSX output path' — layout and motion claims are reconstructed from the DOM/class attributes the component emits, not from runtime screenshots. Plan 62-06 should confirm with live captures before ship."
audit_date: 2026-04-17
---

# Phase 62 Design Audit — Baseline

Scored pre-polish snapshot of the 11 dashboard pages so plans 62-02 through 62-06 can target fixes, and plan 62-06 can prove the DSGN-01 ship gate (>7/10 everywhere).

## Rubric

Each of 8 dimensions scored 0-10. Overall = weighted mean with:
- Typography (1.0), Color (1.0), Spacing (1.0), Components (1.0) — core consistency
- Motion (0.75), States (0.75) — UX polish
- Mobile-375 (1.25), Density (1.0) — user-visible blockers weigh more

Weighting encoded so Motion gaps don't tank a page that is otherwise solid, while Mobile breakage (a ship-blocker) hurts more.

---

### Page 1: /dashboard (overview)

Source: `web/frontend/src/app/dashboard/page.tsx` + `stat-cards.tsx`, `mae-chart.tsx`, `accuracy-chart.tsx`.

Overall score: **6.8 / 10** (weighted mean)
Sub-scores: typography 7, color 7, spacing 7, components 8, motion 3, states 5, mobile 8, density 8

Top 3 gaps (prioritized by impact x reach):
1. **Raw h2 instead of PageContainer header** (`src/app/dashboard/page.tsx:14-16`) — every other dashboard page uses `pageTitle`/`pageDescription` props; this one hand-rolls an `<h2 className='text-2xl font-bold tracking-tight'>`. Creates heading drift between overview and siblings.
2. **Stat values are hardcoded strings** (`src/features/nfl/components/stat-cards.tsx:52-76`) — "4.77" MAE, "571" tests, "53.0%" ATS, "500+" players all baked in. No loading/error state, no freshness tag. On a "dashboard" this is the #1 credibility hit.
3. **No motion on page mount or card interactions** (`stat-cards.tsx` full file) — cards appear instantly; no stagger, hover lift, trend-pulse, or skeleton. Feels lifeless relative to polished dashboards.

Consistency drift vs rest of site: Overview `<h2>` pattern does not match the shared `PageContainer` heading used by the other 10 pages. Stat cards use the `from-primary/5 to-card bg-gradient-to-t` pattern which is also used in accuracy-dashboard.tsx — that's OK (consistent between the 2 pages that use cards) but not adopted by news (flat cards) or predictions.

Recommended direction: wire `<PageContainer pageTitle='NFL Analytics Dashboard'>` and fetch real numbers from `/api/projections` + `/api/predictions/accuracy` + a new `/api/health` endpoint.

---

### Page 2: /dashboard/accuracy

Source: `web/frontend/src/app/dashboard/accuracy/page.tsx` + `accuracy-dashboard.tsx`.

Overall score: **7.3 / 10**
Sub-scores: typography 8, color 7, spacing 8, components 9, motion 3, states 5, mobile 8, density 7

Top 3 gaps:
1. **No empty/error state on the table or chart** (`accuracy-dashboard.tsx` — there is no `isLoading`/`isError` handling because the data is hardcoded at lines 25-42). When backend swaps to live accuracy, missing states will crash user.
2. **No motion at all** — the weekly chart just appears; rows in the per-position breakdown don't animate in, no row hover treatment besides default table CSS.
3. **Position color tokens live inline** (`accuracy-dashboard.tsx:44-49`) — `bg-red-100 dark:bg-red-900/30` etc. is duplicated verbatim in `prediction-cards.tsx`, `rankings-table/index.tsx`, and `projections-table/columns.tsx`. Same data, four copies. Pure token-drift candidate.

Consistency drift: POSITION_COLORS constant is duplicated 4x across the codebase with the exact same class strings (grep confirms identical Tailwind palette usage). Good candidate for `src/lib/nfl/position-tokens.ts` shared export.

Recommended direction: extract position color map, add `useQuery` wrapper for accuracy metrics, add `motion.tr` row stagger on TableBody.

---

### Page 3: /dashboard/advisor

Source: `web/frontend/src/app/dashboard/advisor/page.tsx` (632 lines, one file).

Overall score: **7.6 / 10**
Sub-scores: typography 8, color 8, spacing 8, components 8, motion 6, states 9, mobile 6, density 7

Top 3 gaps:
1. **Empty-state art is a static sparkle icon in a circle** (`page.tsx:394-419`) — suggestion chips are great, but the hero area is bland compared to competitor chat UIs. Consider a loop of rotating suggested queries or a subtle gradient backdrop.
2. **Chat height hardcoded to `h-[calc(100dvh-160px)]` at page.tsx:390** — breaks when the page has the sticky page header + the floating chat widget from layout.tsx:36 is also visible (user gets TWO chat UIs on this page). Duplicates functionality and wastes screen.
3. **Tool-call typing states are text-only** (`page.tsx:468-551`) — five similar "Looking up projection…" / "Comparing players…" strings. The bouncing dots at line 564-573 are only for the assistant text, not the tool calls. Inconsistent signal for "AI is working".

Consistency drift: This is the only page that does NOT pass `scrollable` or use `PageContainer` children wrapping consistently — it constructs its own scroll container via `<ScrollArea className='flex-1 rounded-lg border'>`.

Recommended direction: remove the duplicate floating `<ChatWidget>` for this route (or make this page own the widget), add unified typing-indicator component (bounce dots) for tool calls.

---

### Page 4: /dashboard/draft

Source: `web/frontend/src/app/dashboard/draft/page.tsx` + `draft-tool-view.tsx` and `draft-board-table.tsx`, `my-roster-panel.tsx`, `recommendations-panel.tsx`, `mock-draft-view.tsx`.

Overall score: **7.0 / 10**
Sub-scores: typography 7, color 7, spacing 8, components 8, motion 4, states 9, mobile 5, density 8

Top 3 gaps:
1. **Draft board sidebar collapses below the board on `<lg`** (`draft-tool-view.tsx:180`) — the `flex-col lg:flex-row` makes mobile stack with full-width roster panel, but the board itself has its own wide table; unclear if horizontal scroll works on phone. Likely overflow.
2. **No motion on player-drafted transition** — when a pick happens, the row vanishes and the roster updates with no transition. This is the single most satisfying moment in a draft UI; currently flat.
3. **"15-30 seconds on first load" spinner with plain text** (`draft-tool-view.tsx:157-165`) — honest, but users will bounce. Need a progress bar or step-wise "Generating projections… Building board… Computing VORP…".

Consistency drift: Uses single quotes for JSX (matches CLAUDE.md convention), but the file extension is `.tsx` without trailing semicolons (compare `draft-tool-view.tsx` to all other `.tsx` files — this one has no semicolons at line ends). Minor code-style drift.

Recommended direction: `motion.tr exit={{ opacity: 0, x: 40 }}` on drafted row, animated progress bar for the 15-30s load, mobile sidebar → bottom sheet.

---

### Page 5: /dashboard/lineups

Source: `web/frontend/src/app/dashboard/lineups/page.tsx` + `lineup-view.tsx` + `field-view.tsx` + `team-selector.tsx`.

Overall score: **6.9 / 10**
Sub-scores: typography 7, color 6, spacing 7, components 7, motion 4, states 7, mobile 4, density 7

Top 3 gaps:
1. **Hardcoded green-field gradient and position hex map** (`field-view.tsx:112` `linear-gradient(to bottom, #2d5a27, #1a3a17)` + 9-11 position hexes in the same file) — bypasses the theme system entirely. Swapping to `claude.css` / `vercel.css` will leave lineups looking the same.
2. **Field visualization has no mobile fallback** (`field-view.tsx:79-95`-ish with absolute-positioned yard lines and player cards) — the football-field metaphor fundamentally requires width. On 375px a field-overhead is going to be unreadable.
3. **Click-to-navigate is the only interaction** — no drag to swap, no compare-starter-vs-bench, no injury cascade preview. The card hover lift (`hover:scale-105`) is present but no entrance animation.

Consistency drift: Introduces its own `POSITION_COLORS` hex map (field-view.tsx:8-14) that partially overlaps with the matchup-view `POS_COLORS` map (lines 69-82) but with different palette choices — field view has 5 positions with hexes, matchup has 12. Both are string-valued `#E31837`-style maps.

Recommended direction: lift POSITION_COLORS → `src/lib/nfl/position-tokens.ts`, replace green hex gradient with theme tokens (e.g., `bg-gradient-to-b from-emerald-900 to-emerald-950`), add responsive list-view alternative under `<lg`.

---

### Page 6: /dashboard/matchups

Source: `web/frontend/src/app/dashboard/matchups/page.tsx` + `matchup-view.tsx` (990 lines).

Overall score: **6.2 / 10**
Sub-scores: typography 7, color 5, spacing 7, components 6, motion 4, states 8, mobile 4, density 8

Top 3 gaps:
1. **Uses `text-white`, `bg-black/20`, `bg-white/5`, `text-white/60` extensively** (matchup-view.tsx lines 270-332, 453) — assumes dark mode. In light theme these will produce illegible white-on-light or pure black surfaces. This is a ship-blocker for a multi-theme app.
2. **Defensive rosters are synthesized placeholders** (matchup-view.tsx:718-750) — labeled "DE", "LB" with hash-seeded ratings. This is effectively fake data in production. Not a design defect per se, but users reading the UI will see "BUF DE 72" and believe it.
3. **Hardcoded background `style={{ backgroundColor: '#0f1318' }}` at line 453** — dark panel inner background is a fixed hex, not a theme token. Will clash with light themes (claude, notebook, zen, light-green, whatsapp).

Consistency drift: This is the heaviest offender on hardcoded colors — 15 hex values in one file (12 position hexes + fallback + panel bg + secondary-fallback). The file basically ignores the theme system.

Recommended direction: theme-aware surface classes (`bg-card dark:bg-zinc-900`), replace hex map with CSS vars or Tailwind palette, swap placeholder defensive rosters for real data or hide the section.

---

### Page 7: /dashboard/news

Source: `web/frontend/src/app/dashboard/news/page.tsx` + `news-feed.tsx` (1049 lines).

Overall score: **7.8 / 10**
Sub-scores: typography 8, color 8, spacing 8, components 9, motion 4, states 10, mobile 7, density 7

Top 3 gaps:
1. **Source filter uses a custom rolled button-group** (`news-feed.tsx:818-832`) — reimplements a Tabs-like pattern manually with `rounded-lg border p-1` + button per item. Could just be `<Tabs>` like every other page uses (projections, rankings, advisor all use Tabs). Pure component drift.
2. **Load-More button has no loading spinner** (`news-feed.tsx:885-893`) — clicking "Load more" shows nothing until the next batch renders. Compare to `chat-widget` which has proper spinner states.
3. **Four tab panels all render simultaneously into DOM** — each tab mounts its own queries. On mobile this is a lot of JS and network. Consider lazy mount per tab.

Consistency drift: Custom source filter button group; sentiment thresholds (0.2 / -0.2 / 0.9 / 1.1) are duplicated across 3 helpers (`getSentimentBadgeClass`, `getSentimentLabel`, `getMultiplierLabel`). Should live in `src/lib/nfl/sentiment-tokens.ts`.

Recommended direction: swap source filter to `<Tabs>` component, add `isFetching` state on Load-More, extract sentiment thresholds to shared lib.

---

### Page 8: /dashboard/players

Source: `web/frontend/src/app/dashboard/players/page.tsx` + `player-search.tsx` + `player-detail.tsx` + `player-news-panel.tsx`.

Overall score: **7.1 / 10**
Sub-scores: typography 8, color 7, spacing 7, components 8, motion 4, states 8, mobile 7, density 6

Top 3 gaps:
1. **Search is debounce-free** (`player-search.tsx:15`) — every keystroke fires a query via `playerSearchQueryOptions(query)`. TanStack Query caches but the network still pings. Needs debounce (uses `nuqs` pattern elsewhere but not here).
2. **Empty state (`query.length < 2`) and "no results" (`results.length === 0`) are nearly identical visually** (`player-search.tsx:56-70`) — both use Icons.info + gray text. Differentiate them visually or use illustrations.
3. **Player detail has no breadcrumb beyond a "Back to Projections" button** (`player-detail.tsx:79-86`) — but the user may have arrived from Rankings, News, Matchups, etc. Button lies.

Consistency drift: Three separate search components (player-search, news-feed, rankings-table) all use `Icons.search` + `Input pl-8` but with inconsistent padding (`pl-8 h-9` in news & rankings, `pl-10` no height in players). Normalize.

Recommended direction: add 300ms debounce, make "Back" button dynamic via `document.referrer` or breadcrumb trail, unify search input styling.

---

### Page 9: /dashboard/predictions

Source: `web/frontend/src/app/dashboard/predictions/page.tsx` + `prediction-cards.tsx` + `team-sentiment-badge.tsx`.

Overall score: **7.4 / 10**
Sub-scores: typography 8, color 7, spacing 8, components 8, motion 4, states 9, mobile 7, density 7

Top 3 gaps:
1. **Spread/total edge bars use `<Progress>` capped at `Math.min(edge/10*100, 100)`** (`prediction-cards.tsx:93,121`) — no transition from 0 → value on mount. Data reveals are the moment of insight here; currently static.
2. **Confidence tier badge variant uses `'default' | 'secondary' | 'outline'` mapping** (lines 25-34) — this is fine, but the badge has no tooltip explaining what "high" means (3pt edge? 1.5pt?). Users have no reference.
3. **Header color stripe at line 46-50** is a 50/50 gradient between team colors, but the card has no hover state — cards are read-only; should lift on hover and potentially expand to show spread history.

Consistency drift: The card uses `getTeamColor()` + inline `style={{ color: homeColor }}` — every component that shows teams does this the same way (good). But the progress bar h-1.5 differs from rankings-table range bar `h-2.5` (arbitrary).

Recommended direction: animate progress-bar fills from 0 on mount (stagger across cards), add tooltip on confidence tier, unify edge-bar height to h-2.

---

### Page 10: /dashboard/projections

Source: `web/frontend/src/app/dashboard/projections/page.tsx` + `projections-table/index.tsx` + `projections-table/columns.tsx`.

Overall score: **7.4 / 10**
Sub-scores: typography 8, color 7, spacing 8, components 9, motion 3, states 10, mobile 6, density 8

Top 3 gaps:
1. **Filter stack takes ~140px of vertical space before the table** (`projections-table/index.tsx:52-102`) — two separate `<Tabs>` components (scoring + position) plus two selects. Consolidate scoring into a Select or compress position tabs into a chip row.
2. **No row motion or sort-transition feedback** — sorting a column instantly reorders the DOM; users lose track of where their row went. Classic case for `layout` animations (framer-motion / motion lib, which is installed but unused anywhere in the repo).
3. **Data table mobile: columns hide via `hidden sm:table-cell`** but there are 8 columns with no mobile-first collapse strategy. On 375px some cols will drop silently and users won't know what's missing.

Consistency drift: The position color constants at `columns.tsx:78-84` are yet another copy of the POSITION_COLORS map. Filter chrome (Select width `w-28`/`w-24`/`w-36`) has no shared constants — widths differ by page.

Recommended direction: collapse filter bar into single row or make sticky, animate row reorders with framer/motion `layout`, extract POSITION_COLORS once and for all.

---

### Page 11: /dashboard/rankings

Source: `web/frontend/src/app/dashboard/rankings/page.tsx` + `rankings-table/index.tsx` (443 lines, custom HTML table).

Overall score: **7.2 / 10**
Sub-scores: typography 7, color 8, spacing 7, components 7, motion 5, states 10, mobile 5, density 8

Top 3 gaps:
1. **Uses a raw `<table>` with custom `<thead>`/`<tbody>` instead of the shared DataTable primitive** (`rankings-table/index.tsx:246-285`) — while projections-table uses `@/components/ui/table/data-table`. Same feature shape, two implementations. Maintenance cost.
2. **Tier rows cannot be collapsed** (lines 290-320 `TierGroup`) — with 300+ players the Bench tier alone can be 200 rows. Visual hierarchy is there (yellow/blue/green/gray), but no affordance to hide tiers.
3. **Floor/point/ceiling range bar uses 4 hardcoded `bg-primary/60`, `bg-primary/25` at lines 408-415** — works in most themes, but needs verification on neobrutalism, mono, astro-vista where primary is high-contrast.

Consistency drift: TIER_CONFIG at lines 32-53 uses the same Tailwind-color palette pattern as POSITION_COLORS but in a different file, with `bg-`/`text-`/`border-` triples rather than the 2-tuple pattern of POSITION_COLORS. Unify or at least name consistently.

Recommended direction: migrate to shared DataTable with pinned headers, collapsible tier dividers, theme-test the range bar on neobrutalism + mono themes.

---

## Cross-Cutting Drift Inventories

### Typography drift inventory

| Page/File | Issue | Location |
|---|---|---|
| `/dashboard` (overview) | Hand-rolled `<h2 className='text-2xl font-bold tracking-tight'>` bypasses PageContainer heading | `src/app/dashboard/page.tsx:15` |
| `matchup-view.tsx` | `text-xl font-black uppercase` and `text-[10px] font-bold uppercase tracking-widest` used for team header + row labels — not a scale used elsewhere | `src/features/nfl/components/matchup-view.tsx:425, 336-340` |
| `accuracy-dashboard.tsx` | `text-xs font-medium uppercase tracking-wider` for section captions — similar but not identical to matchup-view's `tracking-widest` | `src/features/nfl/components/accuracy-dashboard.tsx:140` |
| `rankings-table/index.tsx` | `text-[10px]`, `text-[11px]`, `text-[9px]` appear mixed with `text-xs` in same cells | `src/features/nfl/components/rankings-table/index.tsx:398, 430, 436` |
| `news-feed.tsx`, advisor page | `text-[10px]`, `text-[9px]` used as micro-labels instead of a shared `.text-micro` primitive | `src/features/nfl/components/news-feed.tsx:568`, `src/app/dashboard/advisor/page.tsx:243-244, 320` |

Counted instances across src: 50x `text-[9/10/11px]` — all should collapse to 2 or 3 tokens.

### Color drift inventory (hardcoded hex / off-token)

| File | Hex / class | Count | Reason |
|---|---|---|---|
| `src/features/nfl/components/matchup-view.tsx` | `#E31837 #00A6A0 #4F46E5 #D97706 #6B7280 #DC2626 #B91C1C #7C3AED #2563EB #0891B2 #0D9488 #333 #0f1318` | 15 hexes | Position color map + panel background + secondary fallback |
| `src/features/nfl/components/field-view.tsx` | `#E31837 #00A6A0 #4F46E5 #D97706 #6B7280` + `linear-gradient(...#2d5a27, #1a3a17)` | 7 hexes | Position colors + field green gradient |
| POSITION_COLORS (tailwind palette) duplicated in: | `bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400` style | **4 copies** | `accuracy-dashboard.tsx:44-49`, `prediction-cards.tsx:24-30`, `rankings-table/index.tsx:24-30`, `projections-table/columns.tsx:78-84` |
| `matchup-view.tsx` dark scope usage | `text-white`, `bg-black/20`, `bg-white/5`, `text-white/60` | ~30 instances | Assumes dark theme; breaks light themes |
| 66 total | `bg-(red\|green\|blue\|yellow\|amber\|indigo\|teal\|orange\|emerald\|purple\|gray)-\d{3}` in `src/features/` | 66 occurrences | Bypasses `primary/secondary/accent/muted` semantic tokens |

### Spacing drift inventory

| Issue | Files | Notes |
|---|---|---|
| Filter bar heights `w-28 / w-24 / w-36 / w-32` inconsistent across pages | projections, lineups, predictions, matchups, rankings, news | No shared `FilterSelect` primitive |
| Card padding: `p-3` (advisor cards), `p-4` (news cards), `p-4 space-y-2` (news summary), `pt-6` (projections filter), no consistent card content padding rule | All feature components | Should be `CardContent` default + overrides |
| Icon padding drift in search inputs: `pl-8 h-9` (news, rankings) vs `pl-10` no height (players) | search inputs | Normalize |
| Row padding: `py-1.5` (news feed rows), `py-2` (team detail), `py-2.5` (rankings rows), `px-3 py-2` (player row in matchup) | Inconsistent row rhythms | |
| Section gap: `space-y-4` (most pages) vs `space-y-6` (lineups, player detail, accuracy, matchups) | No gap token | |

### Motion inventory (what exists today)

| Type | Where | Count |
|---|---|---|
| `animate-spin` | loading spinners (Icons.spinner) | many pages — universal |
| `animate-bounce` | advisor typing dots | `src/app/dashboard/advisor/page.tsx:570-572` (3 dots) |
| `animate-pulse` | `PageSkeleton` in page-container and data skeletons | `page-container.tsx:8`, various skeletons |
| `transition-colors` | hover states on interactive elements | 20+ places |
| `transition-transform` | `hover:scale-105` on cards/buttons | lineup field-view, draft team buttons |
| `framer-motion` / `motion` library usage | **ZERO** | Package installed (v11.18.2) but never imported anywhere |
| Custom `@keyframes reveal` | theme transition wave effect | `src/styles/globals.css:61-77` — unused for content |

**Missing motion (what user actions lack feedback):**
- `/dashboard` — stat cards mount with no stagger, no trend-pulse, no hover lift
- `/dashboard/accuracy` — chart/table appear instantly; no row stagger; bar chart has no grow animation
- `/dashboard/projections` — sort reorders instantly; filter changes show no transition; row hover is CSS-only
- `/dashboard/rankings` — same as projections; tier dividers don't animate open/close (they don't collapse)
- `/dashboard/predictions` — progress bars snap to final value; no card hover lift; no edge reveal
- `/dashboard/draft` — picking a player is silent; roster update is instant; no exit animation on drafted row
- `/dashboard/lineups` — field players appear all at once; no staggered entrance; no snap highlight on select
- `/dashboard/matchups` — team panels mount simultaneously; advantage indicators don't pulse; no team-switch transition
- `/dashboard/news` — feed items appear instantly; sentiment-distribution bar at line 1006 does NOT animate to width; tab switches have no content transition
- `/dashboard/players` — search results pop in; detail stat bars do not fill from 0
- `/dashboard/advisor` — only animated dots; tool call results appear instantly (no expand/fade-in)

### Mobile-at-375 inventory

Assessment based on JSX class analysis (breakpoints used) — not live-captured screenshots.

| Page | Likely 375px behavior | Severity |
|---|---|---|
| `/dashboard` (overview) | `grid-cols-1 md:grid-cols-2 lg:grid-cols-4` works. Charts likely overflow but have `md:grid-cols-2` fallback. | **Low** — looks fine |
| `/dashboard/accuracy` | Tables hide cols via `hidden sm:table-cell` + `hidden md:table-cell` (Rating, Notes). Main 5 cols remain; should fit 375px with squeeze. Metric cards: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4` OK. | **Low** |
| `/dashboard/advisor` | Chat bubbles max `max-w-[80%]`; input form `flex gap-2` should wrap. Page height calc `h-[calc(100dvh-160px)]` plus sticky header may leave almost no chat space on phones. | **Medium** — usable but cramped |
| `/dashboard/draft` | Board + 72px-wide sidebar = ~300px wide board + sidebar stack. Sidebar panels `w-full lg:w-72` correct. But the DataTable inside has many columns — likely horizontal scroll needed; table has no `overflow-x-auto` wrapper visible. | **High** — draft board overflow |
| `/dashboard/lineups` | Football field is position-absolute — fundamentally incompatible with 375px. No list-view fallback. | **High** — field broken on mobile |
| `/dashboard/matchups` | `grid-cols-1 lg:grid-cols-2` stacks at phone, but each TeamPanel has fixed internal padding + rating badges + projections. Matchup header `flex items-center justify-between px-4` with 12x12 team badges + middle VS + home team — will wrap ugly below ~500px. | **High** |
| `/dashboard/news` | `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` for cards — OK. Summary bar `grid-cols-2 md:grid-cols-4` good. Team sentiment grid `grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8` — 32 teams in 2 columns = 16 rows, scrollable but fine. Source filter button group at lines 818-832 will overflow on 375 if all 4 options visible. | **Medium** |
| `/dashboard/players` | Grid `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` OK on phone. Search bar full width. Detail page has multiple tables that need attention (not fully read). | **Medium** |
| `/dashboard/predictions` | `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` OK. Filter row `flex flex-wrap` OK. Card internal layout fine. Confidence badge may push title on wrap. | **Low** |
| `/dashboard/projections` | 8 columns in DataTable. No explicit mobile-column-hide in columns.tsx (compare to accuracy which uses `hidden sm:table-cell`). Will horizontal-scroll or overflow. Filter bar's 2 selects + 2 tab groups = probably 2 rows on phone. | **High** |
| `/dashboard/rankings` | Custom `<table>` inside `<div className='overflow-x-auto'>` — **only page that explicitly provides horizontal scroll wrapper** (line 245). Good. But rows with 8 cols including 140px range bar will scroll wide. Filter controls bar is `flex flex-wrap` with 3 groups — will stack on 375. | **Medium** — scrolls but intentional |

Touch target audit: small icon badges (`h-3 w-3`, `h-4 w-4`), `text-[10px]` badges are well below the 44px iOS / 48dp Material minimum. Chat widget's 8px bouncing dots are presentation-only so fine. Serious violations: rankings-table tier badges (`text-[10px] px-1.5 py-0`), news-feed card badges, advisor's suggestion chips use `size='sm'` from shadcn which resolves to `h-8` (~32px) — under 44px.

---

## Priority Targets for Phase 62 Plans

### DSGN-02 (Token consistency) — owned by 62-02

Typography drift to fix:
- `/dashboard` overview: replace hand-rolled `<h2>` with `PageContainer pageTitle=` (`src/app/dashboard/page.tsx:14-16`)
- Collapse `text-[9px]`, `text-[10px]`, `text-[11px]` (50 uses) into one `text-2xs` utility or 2 tokens; top offenders: `src/features/nfl/components/rankings-table/index.tsx:398, 430, 436`, `src/features/nfl/components/news-feed.tsx:568`, `src/app/dashboard/advisor/page.tsx:243, 244, 308, 320`, `src/features/nfl/components/matchup-view.tsx:313, 337`
- Unify `uppercase tracking-wider` vs `uppercase tracking-widest` vs `uppercase tracking-wide` for section captions (`src/features/nfl/components/accuracy-dashboard.tsx:140`, `src/features/nfl/components/matchup-view.tsx:337, 425, 603`, `src/features/nfl/components/news-feed.tsx:662`)
- Numeric values: `tabular-nums` applied to most but not all stat displays — audit that every fantasy-point/percentage uses it

Color drift to fix:
- Extract POSITION_COLORS to shared lib (`src/lib/nfl/position-tokens.ts`) — currently duplicated in `src/features/nfl/components/accuracy-dashboard.tsx:44-49`, `src/features/nfl/components/prediction-cards.tsx:24-30`, `src/features/nfl/components/rankings-table/index.tsx:24-30`, `src/features/nfl/components/projections-table/columns.tsx:78-84`, `src/features/nfl/components/matchup-view.tsx:69-82`, `src/features/nfl/components/field-view.tsx:8-14`
- Replace all 15 hardcoded hex values in `src/features/nfl/components/matchup-view.tsx` (lines 70-82, 357, 453, 464, 500, 503, 510, 559) with theme tokens or at minimum CSS vars
- Replace hardcoded field gradient `#2d5a27, #1a3a17` in `src/features/nfl/components/field-view.tsx:112` with `bg-gradient-to-b from-emerald-950 to-emerald-900` or theme surface
- Replace `text-white`, `bg-white/5`, `bg-black/20` dark-only utilities in `src/features/nfl/components/matchup-view.tsx` (~30 instances) with theme-aware `text-foreground dark:text-white` patterns
- Extract sentiment thresholds (0.2, -0.2, 0.9, 1.1) from `src/features/nfl/components/news-feed.tsx:86-112` to `src/lib/nfl/sentiment-tokens.ts` — also used in advisor `src/app/dashboard/advisor/page.tsx:257-264`
- Extract TIER_CONFIG tokens from `src/features/nfl/components/rankings-table/index.tsx:32-53` to shared lib (reused in any ranking context)

Spacing drift to fix:
- Standardize Select widths: create `SELECT_WIDTHS.season/week/scoring/sort` constants — currently `w-28` (season), `w-24` (week), `w-32`/`w-36` (scoring/sort) sprinkled across `src/features/nfl/components/projections-table/index.tsx:56-79`, `src/features/nfl/components/prediction-cards.tsx:164-188`, `src/features/nfl/components/lineup-view.tsx:32-55`, `src/features/nfl/components/matchup-view.tsx:842-878`
- Unify search input styling: normalize `pl-8 h-9` vs `pl-10 no-height` across `src/features/nfl/components/player-search.tsx:19-26`, `src/features/nfl/components/news-feed.tsx:835-843`, `src/features/nfl/components/rankings-table/index.tsx:173-181`
- Choose one root-gap: `space-y-4` (majority) vs `space-y-6` (accuracy, lineups, player-detail, matchups). Recommend `space-y-4` default, `space-y-6` only for major page sections.
- Row padding: pick `py-2` or `py-2.5` — do not mix within the same table (currently mixed in `rankings-table/index.tsx` which uses both)

### DSGN-03 (Motion) — owned by 62-04

Per page, list state changes that need motion (the `motion` library at ^11.18.2 is installed but not yet used):

- `/dashboard` (overview): stat card stagger-in on mount, trend badge pulse on data refresh, hover lift on cards
- `/dashboard/accuracy`: table row stagger, chart bar grow-from-zero, metric card count-up animation on initial load (`src/features/nfl/components/accuracy-dashboard.tsx`)
- `/dashboard/advisor`: tool-call typing indicators consistent with assistant typing dots (`src/app/dashboard/advisor/page.tsx:468-551`), message slide-in
- `/dashboard/draft`: drafted-row exit animation, roster slot fill transition, tier reveal, 15-30s load progress stepper (`src/features/draft/components/draft-tool-view.tsx:157-165`, `draft-board-table.tsx`)
- `/dashboard/lineups`: field-player staggered entrance, position-color pulse on mount, card hover/snap highlight (`src/features/nfl/components/field-view.tsx`)
- `/dashboard/matchups`: team panel side-slide entrance, advantage `>`/`<` indicator pulse, team-switch cross-fade, matchup advantage bar fill (`src/features/nfl/components/matchup-view.tsx`)
- `/dashboard/news`: feed item stagger, sentiment-distribution bar width transition (line 1006 currently has no transition), tab-switch content fade, alert pulse on new alert (`src/features/nfl/components/news-feed.tsx`)
- `/dashboard/players`: search result list stagger, detail-page floor/ceiling bar fill from 0, tab-switch transitions (`src/features/nfl/components/player-search.tsx`, `player-detail.tsx`)
- `/dashboard/predictions`: edge progress-bar fill from 0 on mount (Line 93, 121 `prediction-cards.tsx`), card hover lift, sort-change layout animation
- `/dashboard/projections`: row reorder on sort (`layout` animation via motion), filter-change row fade, skeleton → real row crossfade (`src/features/nfl/components/projections-table/index.tsx`)
- `/dashboard/rankings`: tier dividers collapse/expand, range bar fill from 0, row hover + reorder animations (`src/features/nfl/components/rankings-table/index.tsx`)

### DSGN-04 (Mobile 375px) — owned by 62-05

Per page, list mobile-breaking issues:

- `/dashboard/lineups`: Football-field metaphor has absolute-positioned players + yard lines — fundamentally broken at 375px width. Need a responsive list-view fallback under `lg:` breakpoint. (`src/features/nfl/components/field-view.tsx` — entire file needs mobile branch)
- `/dashboard/matchups`: Heavy left/right team-panel split + matchup header bar's 12x12 team badges + VS center. Panels stack at `lg:` but the MatchupHeaderBar doesn't reflow (`src/features/nfl/components/matchup-view.tsx:493-568`). Defense-placeholder roster is also thick vertically. `text-white` assumes dark mode and will be invisible on light themes.
- `/dashboard/draft`: Draft board DataTable needs horizontal-scroll wrapper; sidebar stack is fine. (`src/features/draft/components/draft-board-table.tsx` — add `overflow-x-auto`)
- `/dashboard/projections`: 8-column DataTable with no column-hide strategy (unlike accuracy which hides "Rating", "Notes"). Add `hidden sm:table-cell` on `key_stats`, `projected_ceiling`; preserve player/position/points core. (`src/features/nfl/components/projections-table/columns.tsx`)
- `/dashboard/rankings`: Has explicit `overflow-x-auto` (good) but 8 columns still force scroll. Consider collapsing position-rank and overall-rank into one column on mobile. (`src/features/nfl/components/rankings-table/index.tsx:245`)
- `/dashboard/news`: Source-filter button group at `src/features/nfl/components/news-feed.tsx:818-832` will overflow if all 4 options visible on 375. Team sentiment grid OK at `grid-cols-2 sm:`.
- `/dashboard/advisor`: Chat height `h-[calc(100dvh-160px)]` leaves chat cramped on phone. Suggestion chips wrap fine. Duplicate floating ChatWidget from `src/app/dashboard/layout.tsx:36` means 2 chat UIs on this page — confusing on mobile. (`src/app/dashboard/advisor/page.tsx:390`)
- Touch-target audit: `text-[10px] px-1.5 py-0` badges in rankings and news feed (~16-20px tall) fail the 44px iOS minimum; `size='sm'` buttons (~32px) fail; suggestion chips in advisor `size='sm'` fail.

Pages with no significant mobile gaps: `/dashboard` (overview), `/dashboard/accuracy`, `/dashboard/predictions`, `/dashboard/players`.

### DSGN-01 (Score >7/10) — owned by 62-06 verification

Pages currently below 7 (must improve to pass DSGN-01):

- `/dashboard` (overview): current score **6.8** — primary blockers are hardcoded stat values with no loading/error states, missing PageContainer heading, zero motion
- `/dashboard/lineups`: current score **6.9** — primary blockers are hardcoded field gradient and position hexes (theme incompatibility), no mobile fallback for field metaphor
- `/dashboard/matchups`: current score **6.2** — primary blockers are heavy `text-white`/`bg-black/20` assumption of dark mode, 15 hardcoded hex values, defensive roster is placeholder data

Pages currently at or above 7 (verify no regression in 62-06):

- `/dashboard/news`: current score **7.8** — strong states and component consistency; regressions would likely come from custom source-filter button group if not updated
- `/dashboard/advisor`: current score **7.6** — strong states and component choice; regressions would come from duplicate chat widget or chat-height math
- `/dashboard/accuracy`: current score **7.3** — strong components; regressions from adding live data without proper loading/error states
- `/dashboard/projections`: current score **7.4** — strong states; regressions from filter bar changes
- `/dashboard/predictions`: current score **7.4** — strong states; regressions from card chrome
- `/dashboard/rankings`: current score **7.2** — decent; regressions from table restructure
- `/dashboard/players`: current score **7.1** — regressions from debounce/input changes
- `/dashboard/draft`: current score **7.0** — borderline; any regression drops below. Watch the mobile board overflow.

**Score distribution:**
- Mean baseline: **7.06 / 10**
- Median: **7.1**
- Below 7: **3 pages** (overview, lineups, matchups)
- At/above 7: **8 pages**

---

## Audit Notes and Caveats

- **No live browser captures.** Scores are source-inspection derived. Downstream plan 62-06 MUST validate with real 375/768/1440 screenshots before declaring DSGN-01 pass.
- **Theme coverage.** 10 themes are imported via `theme.css` but this audit only evaluated the default (Claude-styled) theme's expected behavior. Matchup and lineups pages both assume dark-mode-colored surfaces and are high-risk for theme breakage — plan 62-02 must verify every page renders on at least {claude, vercel, mono, neobrutalism, light-green} to surface token leaks.
- **Design-engineer agent delegation.** Plan 62-01 task 1 required delegating to the `design-engineer` subagent with `audit` + `critique` skills plus live-URL inspection. The executor environment here lacks browser/screenshot tools and Task-based subagent spawning; this file was produced by direct source inspection. If plan 62-06 demands live-observed validation, schedule it as part of the verifier phase.
