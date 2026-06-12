# Design Audit — NFL Fantasy Analytics Frontend

**Methodology:** `redesign-existing-projects` skill (`.claude/skills/redesign-skill/SKILL.md`), audit phase only. No code modified.
**Target:** `web/frontend/` — Next.js 16 App Router, Tailwind v4, shadcn/ui, `motion/react`, TanStack Query.
**Live:** https://frontend-jet-seven-33.vercel.app/dashboard (HTTP 200, reachable).
**Date:** 2026-06-11

---

## 1. Overall Verdict — Grade: B+

This is a genuinely above-average dashboard that has already absorbed a serious, deliberate design-system pass (the "Phase 62 DSGN" work). It is **not** a raw shadcn dump: there is a real token layer (`src/styles/tokens.css`) for typography scale, 4px spacing grid, Emil-Kowalski-banded motion durations, and semantic elevation; a token-backed motion primitive library (`src/lib/motion-primitives.tsx`) with `prefers-reduced-motion` pass-through; authentic per-team NFL hex colors; Tabler icons (not the flagged Lucide/Feather default); tabular-nums on every data figure; and the full state matrix (skeleton loaders, empty states, error states, freshness chips) on the flagship feature components. That foundation is what separates this from a C-tier AI build. What holds it back from A-territory is **incomplete migration and template residue**: the active `vercel` theme ships pure `oklch(0 0 0)` black, the position-color tokens it built were never adopted (3+ duplicate hardcoded maps survive), `text-[Npx]` ad-hoc sizing persists alongside the `--fs-micro` token meant to kill it, one feature table bypasses both the data-fetching convention and the motion system, circular spinners still appear in six components the skeleton system was supposed to cover, and the layout is the canonical left-sidebar shadcn shell with stat-card-grid-over-two-charts dashboards. The bones are premium; the finish is 80% applied.

---

## 2. Generic-AI-Pattern Findings (specific)

| # | Pattern | Location | Why it reads as generic |
|---|---------|----------|-------------------------|
| G1 | **Unmodified shadcn-starter shell** | `package.json` name `next-shadcn-dashboard-starter`, author Kiranism; `app/dashboard/layout.tsx` | Left `AppSidebar` + `Header` + `SidebarInset` is the single most common AI dashboard skeleton. Functional, but zero structural differentiation from thousands of forks. |
| G2 | **Stat-card grid over two charts** dashboard | `app/dashboard/page.tsx` + `features/nfl/components/stat-cards.tsx` | `grid-cols-1 md:grid-cols-2 lg:grid-cols-4` of four KPI cards stacked above a 2-col chart row is *the* generic AI dashboard layout. No asymmetry, no hero metric, no editorial hierarchy. |
| G3 | **Pure black in the default theme** | `src/styles/themes/vercel.css` L8 `--primary: oklch(0 0 0)`, L6/L57 `--foreground`/`--background: oklch(0 0 0)` | Skill explicitly blocks `#000`. Dark mode background is literal pure black; light-mode foreground is pure black. No off-black/tinted charcoal. |
| G4 | **Duplicated hardcoded position-color maps** | `accuracy-dashboard.tsx` L44-49; `draft/components/recommendations-panel.tsx`; `draft/components/draft-board-table.tsx` | `tokens.css` L134-176 created `--pos-qb..--pos-fs` *specifically to retire these* ("Consolidation target for the 6 duplicated POSITION_COLORS maps"). The migration never landed — three+ copies of `bg-red-100 text-red-800 dark:...` still exist. |
| G5 | **Ad-hoc pixel font sizes** despite a token for them | 27 occurrences: `text-[10px]`×21, `text-[11px]`×3, `text-[9px]`, `text-[13px]`, `text-[15px]` across rankings/news/matchup/event-badge components | `--fs-micro` (11px) was added expressly to absorb these ("Replaces text-[9px]/text-[10px]/text-[11px], 50 ad-hoc uses in audit"). Still 27 left. Off-grid type sizes are an AI fingerprint. |
| G6 | **Circular spinners** where skeletons exist | `player-detail.tsx` L61-63 `animate-spin`; also `lineup-view`, `player-search`, and 3 draft components | Skill: "Replace generic circular spinners with skeleton loaders that match the layout shape." The skeleton system (used beautifully in `prediction-cards.tsx`) was not extended here. |
| G7 | **Convention bypass / inconsistency** | `projection-comparison-table.tsx` L53-58 raw `useEffect`+`fetch`+`useState` | Every other feature uses TanStack Query (`useQuery` + query-options factories) and the motion primitives. This one table fetches imperatively and animates nothing — inconsistent rhythm, no stagger, manual loading boolean. |
| H1 | **Semantic-color literals instead of tokens** | `projection-comparison-table.tsx` L34-37 `text-green-600/text-red-600`; `accuracy-dashboard.tsx` L92-95 `getMaeRating`; ~14 components total | Delta/rating colors hardcode Tailwind `green-600`/`red-600`/`amber-600` rather than `--destructive` or a semantic success token. Won't re-theme; mixes a green that no theme defines. |
| H2 | **Template residue** | `components/forms/demo-form.tsx` L288 `alert('Form submitted successfully!')` | Skill blocks both `window.alert()` and exclamation-mark success copy. Demo/scaffold file, not NFL feature code, but it ships in the bundle. |
| L1 | **Div-soup at page level** | section landmarks rare: `grep` finds only 2 `<main>`, 2 `<nav>`, 1 `<section>` across all features/app | Page bodies are nested `<div>`s. Skill: use `<main>/<section>/<article>`. |

---

## 3. Assessment Against Skill Standards

### Typography — Strong (A-)
- **Wins:** Real type scale in `tokens.css` (`--fs-micro` 11px → `--fs-h1` 32px) with paired line-heights at correct ratios (1.5 body, ~1.12 headings). Body floor is 16px (`--fs-body`). `tabular-nums` applied on every numeric figure (stat cards, prediction spreads, player points, tables) — exactly right for a data product. Medium/SemiBold weights used for hierarchy, not just 400/700. Font is **Geist**, an explicitly skill-endorsed choice (not Inter-everywhere).
- **Gaps:** 27 `text-[Npx]` ad-hoc sizes survive (G5) — the scale isn't fully enforced. Headlines are restrained: largest in-app heading is `--fs-h1` 32px/2.25 line-height; for a dashboard that's defensible, but there is no display-weight moment anywhere — nothing has "presence." 14 fonts are loaded via `next/font` in `font.config.tsx` (one per theme); only Geist is active in the default — dead font payload. Uppercase-tracked micro-labels appear repeatedly (`uppercase tracking-wider` in accuracy-dashboard, player-detail) — the skill nudges away from all-caps-everywhere toward sentence case / small-caps.

### Color & Surfaces — Mixed (B-)
- **Wins:** Authentic NFL team hex (`lib/nfl/team-colors.ts`, all 32 teams + relocation aliases) drives accents — genuinely domain-specific, not a generic palette. Team-color top-borders on prediction/player cards are a tasteful signature. OKLCH throughout. Subtle `from-primary/5 to-card` gradient on stat cards adds depth without the purple "AI gradient." No oversaturated accent screaming.
- **Gaps:** **Pure black** in the default `vercel` theme (G3) — blocked default. Semantic data colors are hardcoded Tailwind literals (`green-600`/`red-600`) rather than tokens (H1), so they neither re-theme nor stay consistent across the 10 themes. Shadows are pure-black `hsl(0 0% 0% / …)` (vercel.css L44-51) — skill wants tinted shadows carrying the surface hue. No noise/grain/texture anywhere — surfaces are flat (acceptable for a dense data tool, but the skill flags it as sterile). Ten selectable themes is impressive but dilutes brand identity — there is no single considered "NFL Analytics" look.

### Spacing — Strong (A-)
- **Wins:** Rigorous 4px grid in `tokens.css` (`--space-1..16`) with *semantic aliases* (`--gap-section`, `--pad-card`, `--gap-row`, `--tap-min`) so intent is documented at call sites. 44px iOS tap targets (`--tap-min`) wired into mobile selects/filters (`prediction-cards.tsx` L210). Related elements grouped tighter than unrelated. Responsive padding (`px-[var(--space-3)] md:px-[var(--space-6)]`).
- **Gaps:** Symmetric vertical padding is the norm (skill: optically increase bottom). No deliberate whitespace-maximization or breathing room — dense throughout, which is correct for tables but leaves the dashboard overview feeling cramped rather than composed. No element overlap / negative-margin layering anywhere — everything sits flat in the grid.

### Component Structure — Good (B+)
- **Wins:** Full state matrix on flagship components — `prediction-cards.tsx` has skeleton-shaped loaders (not spinners), distinct 404 / error / empty `EmptyState`s, freshness chips, `edge-shimmer` reward animation, staggered card entrance, team-color split header bar. Token-backed motion primitives (`FadeIn`/`Stagger`/`HoverLift`/`PressScale`/`DataLoadReveal`) with reduced-motion pass-through — this is genuinely high-craft. Custom branded 404 (`app/not-found.tsx`). Em-dash for empty cells. Real, specific copy — **zero** AI clichés found ("elevate/seamless/unleash/delve" scan clean). Active nav state wired via `usePathname` (`app-sidebar.tsx`).
- **Gaps:** Card-in-card nesting risk and uniform card treatment — nearly every surface is a bordered+shadowed `Card`; the skill says cards should exist only when elevation communicates hierarchy. Uniform `--radius` everywhere (no inner/outer radius variation). Spinners in 6 components (G6). One table off-convention (G7). The dashboard overview is the generic four-cards-then-two-charts (G2).

---

## 4. Top 10 Prioritized Upgrade Recommendations

Ordered by skill's fix-priority (color → states → consistency → layout → polish), weighted by impact.

| # | Recommendation | Files | Effort | Expected Impact |
|---|----------------|-------|--------|-----------------|
| 1 | **Kill pure black in the default theme.** Replace `oklch(0 0 0)` foreground/background/primary with off-black (`oklch(0.145 0 0)` dark bg, `~oklch(0.18 0 0)` light fg) and tint shadows toward the surface hue instead of pure-black hsl. | `src/styles/themes/vercel.css` L6,8,16,57 + shadow block L44-51 | **S** | High — removes the single most-cited blocked default; instantly softens the whole UI. Lowest-risk, biggest perceptual win. |
| 2 | **Finish the position-color token migration.** Replace the 3 hardcoded `POSITION_COLORS` maps with the existing `--pos-*` tokens (+ their TS mirror in `design-tokens.ts`). This was the *explicitly planned* but unshipped consolidation. | `accuracy-dashboard.tsx` L44-49; `draft/recommendations-panel.tsx`; `draft/draft-board-table.tsx`; consume `tokens.css` L160-175 | **M** | High — single source of truth, consistent position coding across pages, themes correctly, deletes ~3 duplicate maps. |
| 3 | **Replace circular spinners with shape-matched skeletons.** Port the skeleton pattern already proven in `prediction-cards.tsx` (L260-282) to the components still using `animate-spin`. | `player-detail.tsx` L58-64; `lineup-view.tsx`; `player-search.tsx`; 3 draft components | **M** | High — "makes it feel finished"; eliminates layout jump on load; aligns all loading UX. |
| 4 | **Tokenize semantic data colors.** Introduce `--success`/`--warn` semantic tokens (or reuse `--destructive`) and replace ~14 sites of hardcoded `text-green-600`/`text-red-600`/`amber-600`. | `projection-comparison-table.tsx` L34-37; `accuracy-dashboard.tsx` L92-95; +12 components (grep `text-green-600`) | **M** | Med-High — delta/rating colors finally re-theme and stay consistent across all 10 themes. |
| 5 | **Eliminate the 27 `text-[Npx]` ad-hoc sizes.** Swap to `text-[length:var(--fs-micro)]` / `--fs-xs` etc. — the token already exists for exactly this. | rankings-table, news-feed, matchup-view, EventBadges, multi-compare-table, projections-table/columns (grep `text-\[[0-9]*px\]`) | **S-M** | Med — enforces the type scale; removes off-grid sizes that read as AI. Mechanical find/replace. |
| 6 | **Bring `projection-comparison-table` onto the conventions.** Convert raw `useEffect`+`fetch` to a TanStack `useQuery` + query-options factory, and wrap rows in `Stagger`/`FadeIn`. | `projection-comparison-table.tsx` L53-90 | **M** | Med — fixes the one jarring consistency gap; gains caching, the standard loading/error path, and motion parity. |
| 7 | **Redesign the dashboard overview off the generic template.** Promote one hero metric (e.g. MAE or ATS) to display scale with an inline sparkline; demote the other three to a compact strip; break the rigid 4-up symmetry. | `app/dashboard/page.tsx`; `stat-cards.tsx` L51-85 | **M-L** | High — directly attacks the most generic AI layout (G2); gives the landing view editorial hierarchy and a reason to look. |
| 8 | **Add semantic landmarks.** Wrap page bodies in `<main>`/`<section>`, feature groups in `<article>`, to replace page-level div-soup. | `page-container.tsx`; per-page `app/dashboard/*/page.tsx` | **S** | Med — a11y + SEO + skill compliance; cheap, structural. |
| 9 | **Differentiate surface elevation & radius.** Stop wrapping every block in an identical bordered+shadow Card; reserve elevation for true hierarchy, vary inner vs outer radius, tint card shadows. | `card.tsx` usage across `accuracy-dashboard.tsx`, `player-detail.tsx`, `matchup-view.tsx` | **M** | Med — reduces the "everything is a card" flatness; adds depth the skill calls for. |
| 10 | **Prune dead fonts & purge template residue.** Load only the fonts the shipped themes use (Geist + the few theme-specific ones actually selectable); replace `alert(...)` success in `demo-form.tsx`; confirm/remove the demo form from the bundle. | `components/themes/font.config.tsx` (14 fonts); `components/forms/demo-form.tsx` L288 | **S** | Low-Med — smaller payload, removes blocked `window.alert()` + "!" success copy. |

---

## 5. Blocked Defaults Currently In Use

Items the skill explicitly names as blocked/anti-patterns, found present in this codebase:

1. **Pure `#000` background/foreground** — `vercel.css` (active default theme) `oklch(0 0 0)` for `--background` (dark), `--foreground` (light), `--primary`. (Skill: "Pure #000000 background → replace with off-black/charcoal/tinted dark.")
2. **Generic pure-black `box-shadow`** — `vercel.css` L44-51, all `--shadow-*` use `hsl(0 0% 0% / …)`. (Skill: "Tint shadows to match the background hue.")
3. **Circular spinners over skeleton loaders** — 6 components use `animate-spin` / `Icons.spinner` (G6). (Skill: "Replace generic circular spinners with skeleton loaders that match the layout shape.")
4. **`window.alert()` for feedback** — `components/forms/demo-form.tsx` L288. (Skill: "Do not use `window.alert()`.")
5. **Exclamation mark in success message** — same line, `'Form submitted successfully!'`. (Skill: "Exclamation marks in success messages. Remove them.")
6. **Three equal card columns as a feature row** — dashboard KPI grid resolves to a 4-up equal-card row (`stat-cards.tsx`), and prediction/news grids use `lg:grid-cols-3` equal cards (G2). (Skill: "Three equal card columns as feature row — the most generic AI layout.")
7. **Dashboard always has a left sidebar** — `app/dashboard/layout.tsx` `AppSidebar`. (Skill: "Try top navigation, a floating command menu, or collapsible panel instead." — partially mitigated: a kbar command menu *does* exist.)
8. **Generic card look (border + shadow + background) used uniformly** — near-universal `Card` wrapping. (Skill: "Cards should exist only when elevation communicates hierarchy.")
9. **Title Case / all-caps subheaders** — repeated `uppercase tracking-wider` micro-labels. (Skill: nudges toward sentence case / small-caps.)

**Notably NOT present (credit where due):** no purple/blue AI gradient; no Lucide/Feather icons (Tabler instead); no Inter-everywhere (Geist); no AI-cliché copy; no Lorem Ipsum; no fake round-number data; custom 404 exists; `100dvh` used (not `100vh`); favicon present; active-nav state wired; `prefers-reduced-motion` honored throughout.

---

*Audit only — no application code was modified. Recommendations are scoped for a follow-up `redesign-existing-projects` apply pass, in the fix-priority order above.*
