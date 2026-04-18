---
phase: 62-design-ux-polish
plan: 01
subsystem: design
tags: [audit, design, baseline, ux, mobile, motion]
requires: []
provides:
  - audit-baseline
  - priority-targets-62-02
  - priority-targets-62-03
  - priority-targets-62-04
  - priority-targets-62-05
  - priority-targets-62-06
affects:
  - .planning/phases/62-design-ux-polish/AUDIT-BASELINE.md
tech-stack:
  added: []
  patterns: []
key-files:
  created:
    - .planning/phases/62-design-ux-polish/AUDIT-BASELINE.md
  modified: []
decisions:
  - "Scoring rubric weighted Mobile (1.25) and Typo/Color/Spacing/Components/Density (1.0) higher than Motion/States (0.75); mobile breakage is a ship blocker, motion is polish"
  - "Source-only audit used (no browser/screenshot tool in executor); plan 62-06 must confirm with live captures before DSGN-01 gate"
  - "POSITION_COLORS duplicated 6x across repo — target for 62-02 token consolidation into src/lib/nfl/position-tokens.ts"
  - "motion ^11.18.2 installed but never imported — all 11 pages are Motion-gap candidates for 62-04"
metrics:
  duration: "5 min"
  tasks_completed: 2
  files_created: 1
  files_modified: 0
  completed_date: "2026-04-17"
---

# Phase 62 Plan 01: Design Audit Baseline — Summary

Produced a scored pre-polish snapshot of all 11 dashboard pages so the rest of phase 62 has a measurable before/after and plan 62-06 can prove the DSGN-01 ship gate (>7/10 everywhere).

## One-Liner

Source-derived design audit of 11 dashboard pages scoring 8 dimensions (typography, color, spacing, components, motion, states, mobile, density) with page-by-page gap lists and downstream targets for plans 62-02 through 62-06.

## Results

**Pages audited:** 11 / 11

**Mean baseline score:** 7.06 / 10 (median 7.1)

**Score distribution:**

| Score | Page |
|-------|------|
| 7.8 | `/dashboard/news` |
| 7.6 | `/dashboard/advisor` |
| 7.4 | `/dashboard/projections` |
| 7.4 | `/dashboard/predictions` |
| 7.3 | `/dashboard/accuracy` |
| 7.2 | `/dashboard/rankings` |
| 7.1 | `/dashboard/players` |
| 7.0 | `/dashboard/draft` |
| 6.9 | `/dashboard/lineups` |
| 6.8 | `/dashboard` (overview) |
| 6.2 | `/dashboard/matchups` |

**Pages below 7 (DSGN-01 gap):** 3 — `/dashboard` (overview), `/dashboard/lineups`, `/dashboard/matchups`

## Drift Counts by DSGN Requirement

| Category | Count | Notes |
|----------|-------|-------|
| **DSGN-02: Typography drift** | 50 | Uses of `text-[9px]`/`text-[10px]`/`text-[11px]` across src — collapse to 1-2 tokens |
| **DSGN-02: POSITION_COLORS duplicates** | 6 files | accuracy-dashboard, prediction-cards, rankings-table, projections-table/columns, matchup-view, field-view |
| **DSGN-02: Hardcoded hex values in matchup-view** | 15 | 12 position hexes + panel bg + secondary fallback + fallback |
| **DSGN-02: Hardcoded hex in field-view** | 7 | 5 position hexes + 2-color field gradient |
| **DSGN-02: Tailwind palette usage (off-token)** | 66 | `bg-(red|green|...)-{100-900}` across src/features — prefer semantic tokens |
| **DSGN-02: Dark-only color utilities in matchup-view** | ~30 | `text-white`, `bg-white/5`, `bg-black/20` assume dark theme |
| **DSGN-02: Filter Select width inconsistencies** | 6 files | w-24/w-28/w-32/w-36 mix |
| **DSGN-03: Pages with zero content motion** | 11 / 11 | `motion` v11.18.2 installed but zero imports across src |
| **DSGN-03: Tailwind animate-* uses** | 30 | Only spin/bounce/pulse on spinners + skeletons + 3 dots; no entrance/exit on content |
| **DSGN-04: High-severity mobile-at-375 issues** | 4 pages | lineups (field), matchups (white text + header), draft (board overflow), projections (8 cols) |
| **DSGN-04: Medium-severity mobile issues** | 4 pages | advisor (chat height + duplicate widget), news (filter overflow), players, rankings |
| **DSGN-04: Touch-target violations** | Multiple | `text-[10px] px-1.5 py-0` badges, `size='sm'` buttons (~32px, fails 44px iOS min) |

## Deviations from Plan

**1. [Methodology - Tool Limitation] Source-code audit instead of live-browser audit**
- **Found during:** Task 1 (initial delegation step)
- **Issue:** Plan 62-01 Task 1 specifies delegating to the `design-engineer` subagent with `audit` + `critique` skills AND inspecting the live URL at `https://frontend-jet-seven-33.vercel.app`. The executor environment does not have (a) a Task/subagent-spawn tool to dispatch the agent, nor (b) a browser/screenshot tool for live capture.
- **Fix:** Produced the audit via direct source inspection — read every `page.tsx` + its feature component(s) + shared primitives (`page-container`, `app-sidebar`, `theme.css`, `globals.css`) + tailwind class grep for drift (`bg-*-\d{3}`, `#hex`, `text-[9/10/11px]`, `animate-*`, `motion` imports). Called out the limitation explicitly in the AUDIT-BASELINE.md front-matter (`method_gap` field) and the Audit Notes section so plan 62-06 knows to validate with real screenshots before declaring DSGN-01 pass.
- **Files modified:** `.planning/phases/62-design-ux-polish/AUDIT-BASELINE.md`
- **Commit:** 62f5377

No other deviations — plan executed as specified otherwise (all 11 pages scored, rubric applied, drift inventories catalogued, Priority Targets section populated per DSGN requirement with file-level citations).

## Auth Gates

None. Plan is read-only and does not touch any external service.

## Known Stubs

None — AUDIT-BASELINE.md is complete for its purpose.

## Threat Flags

None introduced. Plan is a documentation-only artifact with no security surface change.

## Key Findings for Downstream Plans

1. **`motion` library is installed but unused** — every one of the 11 pages has zero content motion. Plan 62-04 has a greenfield target; no regression risk.
2. **POSITION_COLORS is the single highest-leverage refactor** — duplicated 6 times across features. Extracting to `src/lib/nfl/position-tokens.ts` touches 6 files and fixes a large chunk of DSGN-02.
3. **`matchup-view.tsx` is the theme-incompatibility hotspot** — 15 hardcoded hex + 30 `text-white`/`bg-white/5` instances. This single file drags the page to 6.2 and blocks DSGN-02 for light themes.
4. **`/dashboard/lineups` needs a mobile fallback**, not a tweak — the football-field metaphor is fundamentally 2D-absolute-positioned, not responsive. Plan 62-05 needs a list-view alternative under `lg:`.
5. **`/dashboard` (overview) has hardcoded hero numbers** — MAE "4.77", Tests "571", ATS "53.0%", Players "500+" are string literals. Plan 62-02/06 should either wire live data or add a data-freshness note.

## Self-Check: PASSED

Verification:
- File exists: `.planning/phases/62-design-ux-polish/AUDIT-BASELINE.md` — FOUND
- `grep -c "^### Page " ...` = 11 — FOUND (all 11 pages scored)
- `## Priority Targets for Phase 62 Plans` section — FOUND
- `### DSGN-01`, `### DSGN-02`, `### DSGN-03`, `### DSGN-04` subsections — FOUND
- Commit `62f5377` — FOUND in git log
- No unexpected deletions in commit — VERIFIED
