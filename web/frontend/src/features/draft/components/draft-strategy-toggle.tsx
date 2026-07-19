'use client'

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { DRAFT_STRATEGIES, STRATEGY_LABELS, STRATEGY_DESCRIPTIONS, asDraftStrategy } from '../utils/draft-strategy'
import type { DraftStrategy } from '@/lib/nfl/types'

interface DraftStrategyToggleProps {
  value: DraftStrategy | string | undefined
  onChange: (strategy: DraftStrategy) => void
}

/**
 * Shared "Draft strategy" dial (Safe floor / Balanced / Ceiling hunt) used by
 * both the mock draft setup dialog and the manual board's Settings dialog.
 * Re-ranks the pool by floor/ceiling band server-side; only takes effect at
 * session creation (a fresh mock start, or Apply & New Draft on the manual
 * board) per the backend contract.
 */
export function DraftStrategyToggle({ value, onChange }: DraftStrategyToggleProps) {
  const active = asDraftStrategy(value)

  return (
    <div className='space-y-[var(--space-2)]'>
      <label className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
        Draft strategy
      </label>
      <ToggleGroup
        type='single'
        variant='outline'
        value={active}
        onValueChange={v => v && onChange(asDraftStrategy(v))}
        className='w-full'
      >
        {DRAFT_STRATEGIES.map(s => (
          <ToggleGroupItem key={s} value={s} aria-label={`${STRATEGY_LABELS[s]} draft strategy`}>
            {STRATEGY_LABELS[s]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
        {STRATEGY_DESCRIPTIONS[active]}
      </p>
    </div>
  )
}
