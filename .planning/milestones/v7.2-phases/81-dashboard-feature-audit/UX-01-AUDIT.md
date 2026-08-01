# Phase 81 — Dashboard Feature Audit (UX-01 / UX-02)

**Date:** 2026-08-01 (draft-season launch week)
**Method:** Live production walk of every dashboard route at desktop width via
browser automation against https://frontend-jet-seven-33.vercel.app, with
DOM-level checks (horizontal scroll, unresolved Suspense markers, error/empty
copy, spinner/skeleton counts) plus console + network inspection on failures.
Backend freshness verified green before the walk (`overall_stale: false`).

## Verdict matrix (desktop)

| Route | Verdict | Notes |
|-------|---------|-------|
| /dashboard (Home Hub) | ✅ PASS | Broadcast redesign live; real metrics (MAE 4.63, picks, charts). One visual defect: scorebug away/home team abbreviations rendered in dark team colors are near-illegible on the near-black panel (e.g. "KC @ …"). |
| /dashboard/projections | ⚠️ PASS w/ defects | Table renders (1000 rows, paginated). D1: preseason fallback serves SEASON-scale points labeled "Week 1" — misleading during preseason. D2: Multi-Source Comparison block pinned to a `sleeper: 2026-06-11` snapshot with "—" for most sources despite silver externals being fresh (07-28). |
| /dashboard/predictions | ✅ PASS | Correct week walk-back to 2025 W18; edges + "Updated about 6 hours ago"; skeletons resolve. Slow first paint (~6–9 s). |
| /dashboard/news | ✅ PASS | Live top stories, sentiment pulse, "Updated just now". |
| /dashboard/leagues | ✅ PASS | Proper 3-step connect wizard empty state; correct League Sync FAQ infobar. |
| /dashboard/draft | ❌ **CRASH (P0)** | Whole route white-screens ("Application error") for every fresh visitor. `TypeError: … reading 'timer_seconds'` — GET /api/draft/platforms envelope + all-null `custom` preset vs flat-record frontend contract. **Fix: PR #73** (envelope unwrap + per-field preset normalization + /dashboard error boundary + verbatim-response regression tests). Live since ~07-19; survived the deploy-web live gate because client crashes still serve HTTP 200. |
| /dashboard/games (Scores) | ❌ **VOID (P1)** | Header renders; content = single unresolved React `<template>` (Suspense never resolves). Backing API healthy (200 in 0.12 s). No console errors. |
| /dashboard/rankings | ❌ **VOID (P1)** | Same unresolved-Suspense signature. API healthy (0.58 s). Top-nav item. |
| /dashboard/players | ❌ **VOID (P1)** | Same signature; no search input in DOM. API healthy (0.10 s). |
| /dashboard/lineups | ❌ **VOID (P1)** | Same signature. API healthy (0.78 s). |
| /dashboard/matchups | ❌ **VOID (P1)** | Same signature (515 chars of body text, all shell). |

**Net: 5 of 11 routes fail closed in production** — 1 crash (fixed in PR #73)
and 4 (5 counting matchups) suspended-forever voids sharing one signature.

## Systemic findings

1. **Suspended-forever routes (P1).** games / rankings / players / lineups /
   matchups render only the PageContainer header plus an unresolved
   `<template>` Suspense marker. Their backing APIs return 200 in <1 s and
   the console is clean, so the suspension is a frontend data-layer issue
   (likely `useSuspenseQuery` promises that never settle, or the redesign's
   layout change breaking these non-migrated feature modules). Working and
   broken pages share identical page.tsx structure — the discriminator is
   inside the feature components. Needs local repro (`next build && next
   start`) to diagnose; page structure alone does not explain it.
2. **Starter-template infobar residue (P2).** Every route that does not set
   its own infobar shows the shadcn-starter "Documentation / Getting Started /
   Installation Guide" panel in production. Leagues (League Sync FAQ) shows
   the correct pattern to follow.
3. **Live gate blind spot (process).** Both failure classes serve HTTP 200
   with a valid shell, so `sanity_check_projections.py --check-live` cannot
   see them. Candidate: hydrated-content sentinel (string rendered only by
   client JS) per key route.
4. **EmptyState coverage (UX-01 original scope)** cannot be fully judged on
   the void routes until finding #1 is fixed; the working routes (predictions,
   news, leagues, projections) all have correct EmptyState/skeleton behavior.

## UX-02 (375 px mobile) — partial

Live 375 px emulation was unreliable in this session (display-scaling kept
the CSS viewport at desktop width despite window resize), so UX-02 is
recorded as **source-audited only**: Phase 62 responsive column-hiding and
the mobile tabbar/app-shell are present in source (`mobile-tabbar.tsx`,
`sm:` column classes), and no `overflow-x` offenders were detected at
desktop DOM level on any working route. A true device-width pass (real
device or DevTools emulation) remains open — fold it into the post-fix
verification of finding #1.

## Remediation tracking

- P0 draft crash → **PR #73** (this audit, same day)
- P1 suspended routes + P2 infobar residue → remediation branch (agent brief
  issued 2026-08-01; see PR referencing this doc)
- Projections labeling + comparison staleness + scorebug contrast → same
  remediation lane, second commit/PR
- Live-gate sentinel → follow-up; pairs with DEPLOY-hardening backlog
