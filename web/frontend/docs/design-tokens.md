# Design Tokens

**Scope:** DSGN-02 (Phase 62-02). Single source of truth for typography, spacing,
motion, elevation, and NFL position colors across all 11 dashboard pages and all
10 themes in `src/styles/themes/`.

**Contract:** Token NAMES listed below are a stability promise — plans 62-03, 62-04,
and 62-05 reference these exact identifiers. Values may be tuned by the design team
but names must not change without a downstream migration.

**Two surfaces, one contract:**

- CSS custom properties in `src/styles/tokens.css` — for Tailwind arbitrary values
  (`text-[length:var(--fs-body)]`) and raw CSS.
- Typed TypeScript constants in `src/lib/design-tokens.ts` — for `motion` library
  props (needs seconds) and inline styles.

---

## Typography

Use `var(--fs-X)` with its paired `var(--lh-X)` for line-height.

| Token                   | Value    | Line-height       | Use case                                        |
| ----------------------- | -------- | ----------------- | ----------------------------------------------- |
| `--fs-micro` / `--lh-micro` | 11px / 16px | tight        | Table sub-captions, badge meta, rank-N labels. Replaces all `text-[9/10/11px]` (50 uses in audit). |
| `--fs-xs` / `--lh-xs`       | 12px / 16px | tight        | Timestamps, source attribution, muted helpers.  |
| `--fs-sm` / `--lh-sm`       | 14px / 20px | comfortable  | Dense-table cells, secondary card body.         |
| `--fs-body` / `--lh-body`   | 16px / 24px | comfortable  | Body copy baseline. Minimum for any reading flow. |
| `--fs-lg` / `--lh-lg`       | 18px / 26px | comfortable  | Card title in dense layouts, sub-heading.       |
| `--fs-h3` / `--lh-h3`       | 20px / 28px | snug         | Section heading inside a page.                  |
| `--fs-h2` / `--lh-h2`       | 24px / 32px | snug         | `PageContainer` page title.                     |
| `--fs-h1` / `--lh-h1`       | 32px / 36px | tight (1.125)| Hero heading (currently unused; reserved).     |

**Rationale:** Body stays at 16px per WCAG. Line-heights follow Emil Kowalski / Impeccable
ratios — 1.5 for reading, 1.1-1.2 for headings. `--fs-micro` added expressly to consolidate
the 50+ `text-[9/10/11px]` ad-hoc values inventoried in `AUDIT-BASELINE.md`.

**TypeScript names:** `TYPE_SCALE` exports `['micro','xs','sm','body','lg','h3','h2','h1']`.

---

## Spacing (4px grid)

| Token        | Value      | Use case                                                    |
| ------------ | ---------- | ----------------------------------------------------------- |
| `--space-1`  | 4px        | icon-to-text gap, tight inline rhythm                       |
| `--space-2`  | 8px        | badge padding, input affix gap                              |
| `--space-3`  | 12px       | row padding in dense tables                                 |
| `--space-4`  | 16px       | default card content padding                                |
| `--space-5`  | 20px       | card gap in grids                                           |
| `--space-6`  | 24px       | major section gap                                           |
| `--space-8`  | 32px       | page gutter on desktop                                      |
| `--space-10` | 40px       | between page header and body on desktop                     |
| `--space-12` | 48px       | meets 44px iOS / 48dp Material touch-target minimum         |

**Semantic aliases — prefer these when choosing intent:**

| Alias              | Resolves to   | Use                                                  |
| ------------------ | ------------- | ---------------------------------------------------- |
| `--gap-field`      | `--space-2`   | Between label and control in a form field.          |
| `--gap-row`        | `--space-3`   | Between rows in a dense list or table.              |
| `--gap-stack`      | `--space-4`   | Default page `space-y` (majority-case).             |
| `--gap-section`    | `--space-6`   | Between major page sections.                        |
| `--pad-card`       | `--space-4`   | Default `CardContent` padding.                      |
| `--pad-card-sm`    | `--space-3`   | Compact cards (advisor suggestion chip).            |

---

## Motion

CSS durations are **ms**; TypeScript constants are **seconds** (motion library convention).

| CSS token          | ms   | `MOTION.` key | Use                                              |
| ------------------ | ---- | ------------- | ------------------------------------------------ |
| `--motion-instant` | 100  | `instant`     | Color / opacity micro-interactions, text hover. |
| `--motion-fast`    | 150  | `fast`        | Button press/release, focus ring.               |
| `--motion-base`    | 220  | `base`        | Hover lift, badge pulse, progress tick.         |
| `--motion-slow`    | 320  | `slow`        | Row reorder (`layout`), sheet entrance.         |
| `--motion-slower`  | 480  | `slower`      | Page-mount stagger finale, tab content swap.    |

**Easings:**

| CSS var                  | TS `EASE.` key  | Curve                      | Use                       |
| ------------------------ | --------------- | -------------------------- | ------------------------- |
| `--ease-out-standard`    | `outStandard`   | `cubic-bezier(.2,0,0,1)`  | Exits, reveals (default) |
| `--ease-in-out-standard` | `inOutStandard` | `cubic-bezier(.4,0,.2,1)` | Symmetric motion         |
| `--ease-in-standard`     | `inStandard`    | `cubic-bezier(.4,0,1,1)`  | Entrances that settle    |

**Stagger:** `--motion-stagger-step: 40ms` (TS `STAGGER_STEP = 0.04`). Use as the
per-sibling delay in entrance animations so a 10-item list completes under 800ms.

---

## Elevation

Semantic aliases over theme-defined `--shadow-*` scale. Components should name USE
(raised, overlay, modal) not size — this keeps Neobrutalism (hard borders) and Claude
(soft shadows) visually coherent without code change.

| Token                  | Resolves to      | Use                                    |
| ---------------------- | ---------------- | -------------------------------------- |
| `--elevation-flat`     | `--shadow-2xs`   | Table rows, inputs at rest.           |
| `--elevation-raised`   | `--shadow-sm`    | Cards, chips.                         |
| `--elevation-overlay`  | `--shadow-md`    | Popovers, hover-lifted cards.         |
| `--elevation-modal`    | `--shadow-xl`    | Dialogs, full-screen sheets.          |

---

## Position colors (NFL)

Consolidation target for the 6 duplicated `POSITION_COLORS` maps inventoried in
`AUDIT-BASELINE.md`. Consumers today include `accuracy-dashboard.tsx`, `field-view.tsx`,
`matchup-view.tsx` (`POS_COLORS`), `rankings-table/index.tsx` (`POS_COLORS`),
`draft-board-table.tsx`, `recommendations-panel.tsx`, and
`projections-table/columns.tsx`. **Plan 62-03 will migrate these consumers to import
`POSITION_COLOR` from `@/lib/design-tokens`.**

Offense:

| Position | CSS var     | TS key              |
| -------- | ----------- | ------------------- |
| QB       | `--pos-qb`  | `POSITION_COLOR.QB` |
| RB       | `--pos-rb`  | `POSITION_COLOR.RB` |
| WR       | `--pos-wr`  | `POSITION_COLOR.WR` |
| TE       | `--pos-te`  | `POSITION_COLOR.TE` |
| K        | `--pos-k`   | `POSITION_COLOR.K`  |
| OL       | `--pos-ol`  | `POSITION_COLOR.OL` |

Defense (used in `matchup-view` today):

| Position | CSS var     | TS key              |
| -------- | ----------- | ------------------- |
| DE       | `--pos-de`  | `POSITION_COLOR.DE` |
| DT       | `--pos-dt`  | `POSITION_COLOR.DT` |
| LB       | `--pos-lb`  | `POSITION_COLOR.LB` |
| CB       | `--pos-cb`  | `POSITION_COLOR.CB` |
| SS       | `--pos-ss`  | `POSITION_COLOR.SS` |
| FS       | `--pos-fs`  | `POSITION_COLOR.FS` |

Fallback: `--pos-unknown` (= `var(--muted-foreground)`). Use `getPositionColor()` from
`@/lib/design-tokens` for safe lookup.

All position colors use OKLCH lightness in the 55–65% band so they read against both
light and dark surfaces across the 10 installed themes.

---

## Do not

- **Do not** hardcode pixel values for typography. `className='text-[10px]'` becomes
  `className='text-[length:var(--fs-micro)]'`.
- **Do not** inline hex values for position colors. `#E31837` becomes
  `style={{ color: POSITION_COLOR.QB }}` or `className='text-[color:var(--pos-qb)]'`.
- **Do not** write motion durations as magic numbers. `transition={{ duration: 0.2 }}`
  becomes `transition={{ duration: MOTION.base }}`.
- **Do not** write raw rgba shadow strings. Use an `--elevation-*` alias.
- **Do not** select on DOM elements inside `tokens.css`. Only `:root` custom
  properties live there; behavioral CSS belongs in `globals.css` or component styles.
- **Do not** re-define or override theme color tokens in `tokens.css`. Color semantics
  (background, foreground, primary, ...) are owned by `src/styles/themes/*.css`.

---

## Changelog

- **2026-04-17** — Initial token set shipped (Phase 62-02). Names locked via DSGN-02
  contract; values tuned against `AUDIT-BASELINE.md` typography and color drift.
