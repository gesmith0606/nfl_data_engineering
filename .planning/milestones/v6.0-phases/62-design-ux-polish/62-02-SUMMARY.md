---
phase: 62-design-ux-polish
plan: 02
subsystem: design
tags: [design-tokens, css, typescript, typography, motion, spacing, theming, tailwind-v4]

# Dependency graph
requires:
  - phase: 62-01
    provides: AUDIT-BASELINE.md (typography drift inventory, POSITION_COLORS duplication map, motion gap list)
provides:
  - design-token-layer
  - css-typography-scale
  - css-motion-scale
  - ts-motion-constants
  - ts-position-colors
  - docs-design-tokens
affects:
  - 62-03  # consumes --fs-*, --lh-*, --space-*, --gap-*, POSITION_COLOR on pages 1-5 and shared layout
  - 62-04  # consumes MOTION, EASE, STAGGER_STEP in motion-primitives + pages 6-11
  - 62-05  # consumes MOTION primitives when polishing pages 1-5
  - 62-06  # validates token compliance in final audit

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive token layer on top of per-theme color tokens (tokens.css imported after theme.css in globals.css)"
    - "Two-surface token contract: CSS custom properties (:root) + TypeScript as-const mirror, sharing the same names"
    - "Durations in ms on the CSS side, seconds on the TypeScript side (motion library convention)"
    - "Semantic spacing aliases (--gap-stack, --pad-card, ...) layered over raw --space-N to document intent"
    - "Elevation tokens alias existing theme --shadow-* so Neobrutalism/Claude themes remain coherent"

key-files:
  created:
    - web/frontend/src/styles/tokens.css
    - web/frontend/src/lib/design-tokens.ts
    - web/frontend/docs/design-tokens.md
  modified:
    - web/frontend/src/styles/globals.css

key-decisions:
  - "Added --fs-micro (11px / 0.6875rem) beyond the plan's 7-step scale to absorb the 50+ text-[9/10/11px] ad-hoc uses inventoried in AUDIT-BASELINE.md"
  - "Added position color tokens (--pos-qb..fs) beyond the plan's interface contract — AUDIT-BASELINE flagged 6 duplicated POSITION_COLORS maps; 62-03 needs a consolidation target"
  - "Durations locked at Emil bands: 100/150/220/320/480ms — base=220ms chosen over 200ms to keep the 'weighted feel' on hover lifts and badge pulses"
  - "Three easing curves shipped (outStandard, inOutStandard, inStandard) instead of the plan's two — inStandard covers entrances that should settle rather than glide past"
  - "STAGGER_STEP = 40ms so a 10-item list completes under 800ms (10 × 40ms + 480ms slower)"
  - "Elevation aliases chosen over raw --shadow-* so components name USE (raised/overlay/modal) not size — preserves theme personality without code changes"
  - "Semantic spacing aliases (--gap-field/row/stack/section, --pad-card/--pad-card-sm) layered on top of --space-N so component code reads intent rather than magnitude"

patterns-established:
  - "Token layering: theme.css owns colors, tokens.css owns typography/spacing/motion/elevation, globals.css stays behavioral-only"
  - "Names are the contract, values can be tuned — downstream plans reference --fs-body and MOTION.base by name"
  - "No DOM selectors in tokens.css; only :root custom properties so the file is purely additive and zero-risk"

requirements-completed: [DSGN-02]

# Metrics
duration: 10min
completed: 2026-04-17
---

# Phase 62 Plan 02: Design Token Foundation Summary

**Shipped a single-source-of-truth design-token layer (typography, spacing, motion, elevation, NFL position colors) as CSS custom properties plus a typed TypeScript mirror, imported globally with zero visual change — ready for plans 62-03/04/05 to consume by name.**

## Performance

- **Duration:** ~10 min (across two task commits)
- **Started:** 2026-04-17T22:55Z (approximate — task 1 spawned)
- **Completed:** 2026-04-17T23:07Z (final docs commit)
- **Tasks:** 2 / 2
- **Files created:** 3 (tokens.css, design-tokens.ts, design-tokens.md)
- **Files modified:** 1 (globals.css — single-line @import addition)

## Accomplishments

- **`web/frontend/src/styles/tokens.css` (165 lines):** typography scale (8 steps, micro → h1), 4px spacing grid with semantic aliases, motion durations (Emil Kowalski bands), easing curves, elevation aliases, NFL position colors. All defined at `:root` so every theme inherits them.
- **`web/frontend/src/lib/design-tokens.ts` (68 lines):** typed mirror exporting `MOTION`, `EASE`, `STAGGER_STEP`, `TYPE_SCALE`, `SPACE`, `POSITION_COLOR`, plus a safe `getPositionColor()` helper. `as const` everywhere for type narrowing.
- **`web/frontend/docs/design-tokens.md` (~170 lines):** reference sheet with usage tables for typography / spacing / motion / elevation / position colors, plus an explicit "Do not" section listing the forbidden patterns (hardcoded px for typography, inline hex for position colors, magic-number motion durations, raw rgba shadows).
- **`web/frontend/src/styles/globals.css`:** single `@import './tokens.css';` added immediately after `@import './theme.css';` — no other changes.
- **Zero visual regression:** tokens are defined but no component consumes them yet. `grep -r "--fs-body\|--motion-fast" web/frontend/src/styles/` only hits the new `tokens.css`. TypeScript compile clean for `design-tokens.ts`.

## Task Commits

1. **Task 1 — Author tokens.css + wire globals import** — `55e2c04` (feat)
2. **Task 2 — TypeScript token mirror + docs reference** — `0b06656` (feat)

**Plan metadata commit:** (this summary) — to be recorded as the docs commit below.

## Final Typography Scale (chosen values + rationale)

| Token           | Value              | Line-height   | Rationale                                                                 |
| --------------- | ------------------ | ------------- | ------------------------------------------------------------------------- |
| `--fs-micro`    | 11px / 0.6875rem   | 16px          | **Added beyond plan defaults** to absorb 50+ text-[9/10/11px] ad-hoc uses from AUDIT-BASELINE. |
| `--fs-xs`       | 12px / 0.75rem     | 16px          | Timestamps, source attribution, muted helpers.                           |
| `--fs-sm`       | 14px / 0.875rem    | 20px (1.43)   | Dense-table cells. Ratio follows Impeccable body-text guidance.          |
| `--fs-body`     | 16px / 1rem        | 24px (1.5)    | WCAG body min. Emil Kowalski 1.5 line-height ratio for readability.     |
| `--fs-lg`       | 18px / 1.125rem    | 26px (1.44)   | Card title in dense layouts.                                             |
| `--fs-h3`       | 20px / 1.25rem     | 28px (1.4)    | In-page section heading.                                                 |
| `--fs-h2`       | 24px / 1.5rem      | 32px (1.33)   | PageContainer page title.                                                |
| `--fs-h1`       | 32px / 2rem        | 36px (1.125)  | Hero heading — heading ratio tightened per Impeccable (1.1–1.2).        |

**Rationale summary:** Body locked at 16px for WCAG; reading heights at ~1.5; heading heights tightened to 1.1–1.2 for visual impact; an 8th step (`--fs-micro`) added because the baseline audit found 50+ pixel-literal uses below 12px that needed a named home.

## Final Motion Durations (chosen values)

| Token              | CSS value | TS value (seconds) | Use case                                     |
| ------------------ | --------- | ------------------ | -------------------------------------------- |
| `--motion-instant` | 100ms     | `MOTION.instant` = 0.10 | Color/opacity micro-interactions, text hover |
| `--motion-fast`    | 150ms     | `MOTION.fast` = 0.15    | Button press/release, focus ring             |
| `--motion-base`    | 220ms     | `MOTION.base` = 0.22    | Hover lift, badge pulse, progress tick       |
| `--motion-slow`    | 320ms     | `MOTION.slow` = 0.32    | Row reorder (`layout`), sheet entrance       |
| `--motion-slower`  | 480ms     | `MOTION.slower` = 0.48  | Page-mount stagger finale, tab content swap  |

**Stagger:** `--motion-stagger-step: 40ms` / `STAGGER_STEP = 0.04` — keeps a 10-item list under 800ms of total entrance time.

**Easings shipped:**

- `--ease-out-standard` / `EASE.outStandard = [0.2, 0, 0, 1]` — default for exits and reveals
- `--ease-in-out-standard` / `EASE.inOutStandard = [0.4, 0, 0.2, 1]` — symmetric motion
- `--ease-in-standard` / `EASE.inStandard = [0.4, 0, 1, 1]` — entrances that settle (added beyond the plan's two; 62-04 will use this for card entrances)

## Confirmation: globals.css imports tokens.css

Lines 1-9 of `web/frontend/src/styles/globals.css`:

```css
@import 'tailwindcss';

@import 'tw-animate-css';

@custom-variant dark (&:is(.dark *));

@import './theme.css';
@import './tokens.css';
```

`@import './tokens.css';` appears on the line immediately after `@import './theme.css';`, exactly as the plan specified. No existing imports were reordered or removed. Token custom properties are therefore available on `:root` for every page and every installed theme.

## Downstream Plans That Will Consume These Tokens

| Plan   | Consumes                                                                                                             | Mechanism                                                                                                              |
| ------ | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **62-03** (wave 2) | `--fs-*` / `--lh-*` (typography), `--space-*` + `--gap-*` / `--pad-card` (spacing), `POSITION_COLOR` (TS) | Token normalization pass on pages 1-5 + shared layout (page-container, header, sidebar, Heading). Migrates the 6 duplicated POSITION_COLORS maps. |
| **62-04** (wave 2) | `MOTION`, `EASE`, `STAGGER_STEP` (TS)                                                                               | Builds `src/lib/motion-primitives.ts` (FadeIn, Stagger, HoverLift, PressScale, DataLoadReveal) — imports MOTION + EASE directly from `@/lib/design-tokens`. Applies primitives to pages 6-11. |
| **62-05** (wave 3) | Motion primitives from 62-04 + token-aware layouts from 62-03                                                        | Final polish pass on pages 1-5 (motion + audit rescore).                                                               |
| **62-06** (wave 4) | All tokens (validation only)                                                                                         | Final design audit — confirms tokens are consumed everywhere and no ad-hoc literals remain above threshold.           |

## Decisions Made

- **Added beyond the interface contract** — `--fs-micro`, the 12 `--pos-*` entries, a third `inStandard` easing, semantic `--gap-*` / `--pad-card-*` aliases, `--motion-stagger-step`, and `--elevation-*` aliases. The plan explicitly allowed values to be tuned while freezing NAMES; these additions are all _new_ tokens that do not break the contract and close real gaps documented in `AUDIT-BASELINE.md` (50 ad-hoc micro-text uses, 6 duplicated POSITION_COLORS maps).
- **Durations in ms on CSS side / seconds on TS side** — matches the `motion` library convention (seconds) without losing ergonomics in CSS transitions (ms). Docs call this out explicitly.
- **No visual change, no behavioral CSS** — `tokens.css` contains only `:root` custom properties; every consumer is a downstream plan. Verified via `grep -r "--fs-body|--motion-fast" web/frontend/src/styles/` returning only `tokens.css`.
- **Root `.gitignore` narrow un-ignore** — the Python-template `lib/` rule was swallowing `web/frontend/src/lib/`, so `!web/frontend/src/lib/` was added to make the new `design-tokens.ts` trackable. Pre-existing untracked frontend `lib/` files were logged to `deferred-items.md` (not a 62-02 concern).

## Deviations from Plan

None that alter the interface contract. The plan explicitly permitted value-tuning and allowed additive extensions where `AUDIT-BASELINE.md` demanded them. Every name in the plan's interface contract (§Context) is present and unchanged:

- `--fs-xs` / `--lh-xs` through `--fs-h1` / `--lh-h1` — all present with original names
- `--space-1` through `--space-12` — all present
- `--motion-instant` through `--motion-slower` — all present
- `--ease-out-standard`, `--ease-in-out-standard` — both present
- `--elevation-flat`, `--elevation-raised`, `--elevation-overlay`, `--elevation-modal` — all present
- `MOTION`, `EASE`, `TYPE_SCALE`, `SPACE` — all exported

The executor of 62-03/04/05 can write against these names immediately.

## Issues Encountered

- **`.gitignore` was swallowing `web/frontend/src/lib/`.** The repo root `.gitignore` carries a Python-template `lib/` rule that was hiding `src/lib/design-tokens.ts` from Git. Resolved via a narrow un-ignore (`!web/frontend/src/lib/`) that only exposes the frontend source directory. Logged to `deferred-items.md` because other pre-existing frontend `lib/` files (untracked) will need a follow-up sweep in a separate chore.

## Next Phase Readiness

- **Ready for 62-03** (wave 2, token consumption on pages 1-5 + layout primitives). All CSS vars and TS exports referenced by 62-03 exist on `main`.
- **Ready for 62-04** (wave 2, motion primitives + pages 6-11). `MOTION`, `EASE`, `STAGGER_STEP` are importable from `@/lib/design-tokens`.
- **No blockers.** Tokens compile under `tsconfig.json` with zero errors against `src/lib/design-tokens.ts`.
- **Zero visual risk** on the live site — tokens defined, nothing consumes them yet. Safe to deploy whenever the build pipeline next runs.

## Self-Check: PASSED

- [x] `web/frontend/src/styles/tokens.css` — FOUND
- [x] `web/frontend/src/lib/design-tokens.ts` — FOUND
- [x] `web/frontend/docs/design-tokens.md` — FOUND
- [x] `web/frontend/src/styles/globals.css` contains `@import './tokens.css';` — CONFIRMED
- [x] Commit `55e2c04` — FOUND (`feat(62-02): add design tokens.css and wire globals import`)
- [x] Commit `0b06656` — FOUND (`feat(62-02): add TypeScript token mirror and docs reference`)
- [x] `--fs-body`, `--motion-fast`, `--space-4` all grep-match in `tokens.css` — CONFIRMED
- [x] `MOTION`, `EASE`, `TYPE_SCALE`, `SPACE`, `POSITION_COLOR` exported from `design-tokens.ts` — CONFIRMED
- [x] TypeScript compile clean against `design-tokens.ts` — CONFIRMED (0 errors in file)
- [x] `grep -r "--fs-body|--motion-fast" web/frontend/src/styles/` returns only `tokens.css` — CONFIRMED (no unintended consumers)

---
*Phase: 62-design-ux-polish*
*Completed: 2026-04-17*
