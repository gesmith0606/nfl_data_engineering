'use client'

import { SUCCESS_BADGE, WARN_BADGE } from '@/lib/nfl/semantic-colors'
import type { StackHint } from '@/lib/nfl/types'

interface StackBadgeProps {
  hint: StackHint
}

/**
 * Mint "STACK +0.51 w/ Goff" pill for a positive correlation (stack_bonus),
 * or an amber "overlap" pill warning of shared-ceiling risk with an already
 * rostered player (shared_ceiling_warning). Reuses the shared success/warn
 * badge tokens rather than inventing a new "mint" color.
 */
export function StackBadge({ hint }: StackBadgeProps) {
  if (hint.kind === 'stack_bonus') {
    const bonus = hint.rho >= 0 ? `+${hint.rho.toFixed(2)}` : hint.rho.toFixed(2)
    return (
      <span
        className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${SUCCESS_BADGE}`}
        title={`Correlates with ${hint.rostered_player_name} over ${hint.n_games} games`}
      >
        STACK {bonus} w/ {hint.rostered_player_name}
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${WARN_BADGE}`}
      title={`Shared-ceiling risk with ${hint.rostered_player_name} over ${hint.n_games} games`}
    >
      overlap w/ {hint.rostered_player_name}
    </span>
  )
}
