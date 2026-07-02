/**
 * Position color helpers — single source of truth for NFL position styling.
 *
 * Derives all styling from the `--pos-*` CSS custom properties in
 * `src/styles/tokens.css` (mirrored as `var()` refs in `@/lib/design-tokens`),
 * so position coding stays consistent across all 10 themes x 2 modes.
 *
 * This module retires the 6 duplicated `POSITION_COLORS` / `POS_COLORS` /
 * inline `colorMap` objects that previously hardcoded `bg-red-100 text-red-800
 * dark:...` chains (accuracy-dashboard, rankings-table, multi-compare-table,
 * projections-table, draft-board-table, recommendations-panel).
 *
 * Two consumption shapes:
 *  - `getPositionColor(pos)` (re-exported from design-tokens): a raw
 *    `var(--pos-*)` string for inline `style` (field-view, matchup-view).
 *  - `getPositionBadgeClass(pos)`: a Tailwind class string producing the
 *    tinted-badge look (subtle background + readable text) the old maps had,
 *    built from the same token via `color-mix` so it themes correctly.
 */

import { getPositionColor } from '@/lib/design-tokens';

export { getPositionColor };

/* Tailwind extracts class names STATICALLY from source text — a class built
 * by template interpolation at runtime never reaches the bundle. Every badge
 * class string below must therefore stay a full literal. */
const BADGE_CLASS: Record<string, string> = {
  QB: 'text-[var(--pos-qb)] border-[color-mix(in_oklch,var(--pos-qb)_45%,transparent)] border-l-[3px] border-l-[var(--pos-qb)] bg-[color-mix(in_oklch,var(--pos-qb)_16%,transparent)]',
  RB: 'text-[var(--pos-rb)] border-[color-mix(in_oklch,var(--pos-rb)_45%,transparent)] border-l-[3px] border-l-[var(--pos-rb)] bg-[color-mix(in_oklch,var(--pos-rb)_16%,transparent)]',
  WR: 'text-[var(--pos-wr)] border-[color-mix(in_oklch,var(--pos-wr)_45%,transparent)] border-l-[3px] border-l-[var(--pos-wr)] bg-[color-mix(in_oklch,var(--pos-wr)_16%,transparent)]',
  TE: 'text-[var(--pos-te)] border-[color-mix(in_oklch,var(--pos-te)_45%,transparent)] border-l-[3px] border-l-[var(--pos-te)] bg-[color-mix(in_oklch,var(--pos-te)_16%,transparent)]',
  K: 'text-[var(--pos-k)] border-[color-mix(in_oklch,var(--pos-k)_45%,transparent)] border-l-[3px] border-l-[var(--pos-k)] bg-[color-mix(in_oklch,var(--pos-k)_16%,transparent)]',
  OL: 'text-[var(--pos-ol)] border-[color-mix(in_oklch,var(--pos-ol)_45%,transparent)] border-l-[3px] border-l-[var(--pos-ol)] bg-[color-mix(in_oklch,var(--pos-ol)_16%,transparent)]',
  DE: 'text-[var(--pos-de)] border-[color-mix(in_oklch,var(--pos-de)_45%,transparent)] border-l-[3px] border-l-[var(--pos-de)] bg-[color-mix(in_oklch,var(--pos-de)_16%,transparent)]',
  DT: 'text-[var(--pos-dt)] border-[color-mix(in_oklch,var(--pos-dt)_45%,transparent)] border-l-[3px] border-l-[var(--pos-dt)] bg-[color-mix(in_oklch,var(--pos-dt)_16%,transparent)]',
  LB: 'text-[var(--pos-lb)] border-[color-mix(in_oklch,var(--pos-lb)_45%,transparent)] border-l-[3px] border-l-[var(--pos-lb)] bg-[color-mix(in_oklch,var(--pos-lb)_16%,transparent)]',
  CB: 'text-[var(--pos-cb)] border-[color-mix(in_oklch,var(--pos-cb)_45%,transparent)] border-l-[3px] border-l-[var(--pos-cb)] bg-[color-mix(in_oklch,var(--pos-cb)_16%,transparent)]',
  SS: 'text-[var(--pos-ss)] border-[color-mix(in_oklch,var(--pos-ss)_45%,transparent)] border-l-[3px] border-l-[var(--pos-ss)] bg-[color-mix(in_oklch,var(--pos-ss)_16%,transparent)]',
  FS: 'text-[var(--pos-fs)] border-[color-mix(in_oklch,var(--pos-fs)_45%,transparent)] border-l-[3px] border-l-[var(--pos-fs)] bg-[color-mix(in_oklch,var(--pos-fs)_16%,transparent)]'
};

const BADGE_CLASS_UNKNOWN =
  'text-[var(--pos-unknown)] border-[color-mix(in_oklch,var(--pos-unknown)_45%,transparent)] border-l-[3px] border-l-[var(--pos-unknown)] bg-[color-mix(in_oklch,var(--pos-unknown)_16%,transparent)]';

/* Shared chunky-pill modifiers appended to every position badge: condensed
 * uppercase display type (falls back to --font-sans off worldcup26) + rounded
 * pill geometry. Kept as a static literal so Tailwind extracts the classes. */
const BADGE_SHARED = 'wc-display rounded-md tracking-[0.04em]';

/**
 * Tailwind class string for a position pill/badge.
 *
 * A solid 3px position-color rail runs down the left edge; the remaining
 * border is a 45% mix and the fill a 16% mix of the same token, with condensed
 * uppercase display type. Resolves through `var(--pos-*)`, so it re-themes
 * across all themes/modes.
 */
export function getPositionBadgeClass(position: string): string {
  const base = BADGE_CLASS[position?.toUpperCase()] ?? BADGE_CLASS_UNKNOWN;
  return `${base} ${BADGE_SHARED}`;
}
