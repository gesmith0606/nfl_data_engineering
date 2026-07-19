import type { DraftStrategy } from '@/lib/nfl/types'

export const DRAFT_STRATEGIES: DraftStrategy[] = ['floor', 'balanced', 'ceiling']

/** Short label for the strategy dial toggle + header chip. */
export const STRATEGY_LABELS: Record<DraftStrategy, string> = {
  floor: 'Safe floor',
  balanced: 'Balanced',
  ceiling: 'Ceiling hunt'
}

/** One-line explanation shown under the dial. */
export const STRATEGY_DESCRIPTIONS: Record<DraftStrategy, string> = {
  floor: 'Prioritizes high-floor players — steadier, lower-variance rosters.',
  balanced: 'Default model ranking — no floor/ceiling tilt.',
  ceiling: 'Prioritizes high-ceiling players — boomier, higher-upside rosters.'
}

export function isDraftStrategy(value: string | undefined): value is DraftStrategy {
  return !!value && (DRAFT_STRATEGIES as string[]).includes(value)
}

/** Narrow to a DraftStrategy, defaulting to 'balanced' for unset/unknown values. */
export function asDraftStrategy(value: string | undefined): DraftStrategy {
  return isDraftStrategy(value) ? value : 'balanced'
}
