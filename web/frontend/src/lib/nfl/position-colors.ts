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
  QB: 'text-[var(--pos-qb)] border-[color-mix(in_oklch,var(--pos-qb)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-qb)_14%,transparent)]',
  RB: 'text-[var(--pos-rb)] border-[color-mix(in_oklch,var(--pos-rb)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-rb)_14%,transparent)]',
  WR: 'text-[var(--pos-wr)] border-[color-mix(in_oklch,var(--pos-wr)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-wr)_14%,transparent)]',
  TE: 'text-[var(--pos-te)] border-[color-mix(in_oklch,var(--pos-te)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-te)_14%,transparent)]',
  K: 'text-[var(--pos-k)] border-[color-mix(in_oklch,var(--pos-k)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-k)_14%,transparent)]',
  OL: 'text-[var(--pos-ol)] border-[color-mix(in_oklch,var(--pos-ol)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-ol)_14%,transparent)]',
  DE: 'text-[var(--pos-de)] border-[color-mix(in_oklch,var(--pos-de)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-de)_14%,transparent)]',
  DT: 'text-[var(--pos-dt)] border-[color-mix(in_oklch,var(--pos-dt)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-dt)_14%,transparent)]',
  LB: 'text-[var(--pos-lb)] border-[color-mix(in_oklch,var(--pos-lb)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-lb)_14%,transparent)]',
  CB: 'text-[var(--pos-cb)] border-[color-mix(in_oklch,var(--pos-cb)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-cb)_14%,transparent)]',
  SS: 'text-[var(--pos-ss)] border-[color-mix(in_oklch,var(--pos-ss)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-ss)_14%,transparent)]',
  FS: 'text-[var(--pos-fs)] border-[color-mix(in_oklch,var(--pos-fs)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-fs)_14%,transparent)]'
};

const BADGE_CLASS_UNKNOWN =
  'text-[var(--pos-unknown)] border-[color-mix(in_oklch,var(--pos-unknown)_45%,transparent)] bg-[color-mix(in_oklch,var(--pos-unknown)_14%,transparent)]';

/**
 * Tailwind class string for a position pill/badge.
 *
 * Background is a 14% mix of the position token over the surface (the
 * tinted-chip look); text uses the token directly and the border a 45% mix.
 * Resolves through `var(--pos-*)`, so it re-themes across all themes/modes.
 */
export function getPositionBadgeClass(position: string): string {
  return BADGE_CLASS[position?.toUpperCase()] ?? BADGE_CLASS_UNKNOWN;
}
