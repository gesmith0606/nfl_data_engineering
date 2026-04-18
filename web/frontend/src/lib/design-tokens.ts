/**
 * Design tokens — TypeScript mirror of `src/styles/tokens.css`.
 *
 * Contract: NAMES here match CSS custom-property names in tokens.css.
 * Consumers (motion.div, inline styles, chart libs that require numbers)
 * read from these constants; CSS consumers read `var(--motion-fast)` etc.
 *
 * Durations are in SECONDS (motion / framer-motion convention). Divide
 * the CSS ms value by 1000.
 */

export const MOTION = {
  instant: 0.1,
  fast: 0.15,
  base: 0.22,
  slow: 0.32,
  slower: 0.48
} as const;

export type MotionDuration = keyof typeof MOTION;

/** Cubic-bezier easing curves expressed as 4-tuples for motion's `ease` prop. */
export const EASE = {
  outStandard: [0.2, 0, 0, 1] as const,
  inOutStandard: [0.4, 0, 0.2, 1] as const,
  inStandard: [0.4, 0, 1, 1] as const
};

/** Stagger step between sibling entrances (seconds). Matches --motion-stagger-step. */
export const STAGGER_STEP = 0.04;

export const TYPE_SCALE = ['micro', 'xs', 'sm', 'body', 'lg', 'h3', 'h2', 'h1'] as const;
export type TypeScale = (typeof TYPE_SCALE)[number];

export const SPACE = [1, 2, 3, 4, 5, 6, 8, 10, 12] as const;
export type Space = (typeof SPACE)[number];

/**
 * Position color tokens — mirror of --pos-* CSS vars.
 * Each value is the CSS var reference (use with `style={{ color: POSITION_COLOR.QB }}`
 * or resolved to a Tailwind arbitrary value via `text-[var(--pos-qb)]`).
 *
 * Consolidation target for the 6 duplicated POSITION_COLORS maps inventoried
 * in AUDIT-BASELINE.md (accuracy-dashboard, field-view, matchup-view,
 * rankings-table, draft-board-table, recommendations-panel, projections-table).
 * Plan 62-03 will migrate those consumers.
 */
export const POSITION_COLOR = {
  QB: 'var(--pos-qb)',
  RB: 'var(--pos-rb)',
  WR: 'var(--pos-wr)',
  TE: 'var(--pos-te)',
  K: 'var(--pos-k)',
  OL: 'var(--pos-ol)',
  DE: 'var(--pos-de)',
  DT: 'var(--pos-dt)',
  LB: 'var(--pos-lb)',
  CB: 'var(--pos-cb)',
  SS: 'var(--pos-ss)',
  FS: 'var(--pos-fs)'
} as const;

export type Position = keyof typeof POSITION_COLOR;

/** Safe lookup: returns `var(--pos-unknown)` if the position is not mapped. */
export function getPositionColor(position: string): string {
  return (POSITION_COLOR as Record<string, string>)[position] ?? 'var(--pos-unknown)';
}
