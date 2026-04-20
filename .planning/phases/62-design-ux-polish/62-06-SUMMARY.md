---
phase: 62-design-ux-polish
plan: 06
subsystem: web-frontend-design
tags: [dsgn-01, dsgn-03, ship-gate, motion, audit-final, edge-shimmer]

requires:
  - plan: "62-04"
    provides: "motion-primitives.tsx (FadeIn, Stagger, HoverLift, PressScale, DataLoadReveal)"
  - file: ".planning/phases/62-design-ux-polish/AUDIT-BASELINE.md"
    provides: "62-01 baseline scores (11 pages, mean 7.06, 3 pages < 7)"
provides:
  - ".planning/phases/62-design-ux-polish/AUDIT-FINAL.md (11 pages re-scored, mean 7.80, zero pages < 7)"
  - "Motion primitives retrofit on pages 1-5 (overview, accuracy, projections, rankings, predictions)"
  - "Prediction edge reveal — badge FadeIn on |edge| >= 1.5, CSS shimmer glint on |edge| >= 3.0"
affects:
  - "Phase 62 SHIP gate: closed (all 11 pages > 7.0 overall)"
  - "DSGN-01, DSGN-02, DSGN-03, DSGN-04 — all four requirements PASS"

tech-stack:
  added: []
  patterns:
    - "FadeIn wraps page-level JSX inside <Suspense> so SSR + streaming still work"
    - "Stagger step=0.04-0.05 for card grids so reveal feels tasteful not gimmicky"
    - "HoverLift lift=3 on prediction + overview cards only (tables skipped to avoid 200 animating rows)"
    - "Edge shimmer via @keyframes edge-shimmer in globals.css — CSS animation, token-backed duration, prefers-reduced-motion honored"

key-files:
  created:
    - ".planning/phases/62-design-ux-polish/AUDIT-FINAL.md"
    - ".planning/phases/62-design-ux-polish/62-06-SUMMARY.md (this file)"
  modified:
    - "web/frontend/src/app/dashboard/page.tsx (FadeIn)"
    - "web/frontend/src/app/dashboard/accuracy/page.tsx (FadeIn)"
    - "web/frontend/src/app/dashboard/projections/page.tsx (FadeIn)"
    - "web/frontend/src/app/dashboard/rankings/page.tsx (FadeIn)"
    - "web/frontend/src/app/dashboard/predictions/page.tsx (FadeIn)"
    - "web/frontend/src/features/nfl/components/stat-cards.tsx (Stagger + HoverLift)"
    - "web/frontend/src/features/nfl/components/prediction-cards.tsx (Stagger + HoverLift + edge shimmer)"
    - "web/frontend/src/styles/globals.css (@keyframes edge-shimmer)"
---

# Plan 62-06 — Phase 62 SHIP gate

## Verdict: SHIP ✓

Every one of the 11 dashboard pages scores > 7.0 overall on the re-audit. Mean jumped 7.06 → 7.80. Pages previously < 7 (dashboard, matchups, lineups) all now ≥ 7.3. DSGN-01, DSGN-02, DSGN-03, DSGN-04 all satisfied.

## Audit delta (from AUDIT-FINAL.md)

| Page | Baseline | Final | Δ |
|------|---------:|------:|--:|
| /dashboard | 6.8 | 8.0 | +1.2 |
| /dashboard/matchups | 6.2 | 7.3 | +1.1 |
| /dashboard/lineups | 6.9 | 7.5 | +0.6 |
| /dashboard/accuracy | 7.3 | 7.8 | +0.5 |
| /dashboard/advisor | 7.6 | 8.1 | +0.5 |
| /dashboard/draft | 7.0 | 7.5 | +0.5 |
| /dashboard/news | 7.8 | 8.2 | +0.4 |
| /dashboard/players | 7.1 | 7.7 | +0.6 |
| /dashboard/predictions | 7.4 | 8.0 | +0.6 |
| /dashboard/projections | 7.4 | 7.9 | +0.5 |
| /dashboard/rankings | 7.2 | 7.8 | +0.6 |
| **Mean** | **7.06** | **7.80** | **+0.74** |

## Browser UAT (Playwright, 2026-04-20)

Driven by the orchestrator on `http://127.0.0.1:3000` against the local dev stack:

- **Desktop 1440×900** — `/dashboard`, `/predictions?week=17`, `/projections` all render clean, stat cards stagger in, prediction cards hover-lift, 200-row projections table loads instantly
- **Mobile 375×667** — zero horizontal overflow on every page tested, filter controls stack vertically, prediction cards go full-width with edge badges intact, projections table hides lower-priority columns (Player / Pos / Projected visible)
- **Edge reveal** — 4 `.edge-shimmer` elements confirmed on W17 predictions (LA-ARI -3.4, NYJ-BUF -3.7, GB-MIN +4.1, ATL-WAS +4.2 — all |edge| ≥ 3.0)
- **Advisor button** persists across all routes in both viewports

## Documented waivers (from AUDIT-FINAL.md, not SHIP-blocking)

1. **matchups Color = 6** — hardcoded hex inside `matchup-view.tsx` is fine on the default `vercel` theme, only degrades on non-default themes (neobrutalism, mono, light-green). Accepted for SHIP; becomes a real issue if those themes become user-selectable. Catalogued for 62.1.
2. **overview States = 6** — stat values hardcoded (MAE 4.77, Tests 571, ATS 53.0%, Players 500+). Data-wiring concern, not design. Tracked in the existing website-sentiment-integration work.

## Commits

| Task | Commit | Description |
| ---- | ------ | ----------- |
| 1    | `dbb9423` | Motion primitives on pages 1-5 + prediction edge reveal |
| 2    | `3a79df8` | AUDIT-FINAL.md with per-page deltas |
| 3 (docs) | (this commit) | SUMMARY close-out after Playwright UAT |

## Requirements coverage

- **DSGN-01** ✓ — every page > 7/10 (AUDIT-FINAL.md scores)
- **DSGN-02** ✓ — token consistency across all 11 pages (62-02 + 62-03 + 62-04)
- **DSGN-03** ✓ — motion primitives on every page + prediction edge shimmer (this plan closes the loop on pages 1-5)
- **DSGN-04** ✓ — 375px mobile verified (62-05 MOBILE-AUDIT + this plan's Playwright walk)

## What's next

Phase 62 ships. Open follow-up backlog:
- 62.1 (candidate) — `matchup-view.tsx` theme-safe color pass (waiver #1)
- 66/67 polish phase — BroadcastChannel wiring on usePersistentChat clear (63-05 known gap)
- Ongoing — overview stat values data-wiring (not a design concern)
