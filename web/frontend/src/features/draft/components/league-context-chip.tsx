'use client'

import { Button } from '@/components/ui/button'
import { PLATFORM_ACCENT, PLATFORM_LABELS, isRoomPlatform, scoringLabel } from '../utils/platform-presets'
import type { DraftConfig } from '@/lib/nfl/types'

interface LeagueContextChipProps {
  config: DraftConfig
  onChange: () => void
}

/**
 * Prominent, always-visible summary of the active league context near the
 * toolbar -- e.g. "12-team · Half PPR · ESPN roster · pick #4 — Change".
 * Replaces the old buried session-info text line.
 */
export function LeagueContextChip({ config, onChange }: LeagueContextChipProps) {
  const platform = isRoomPlatform(config.platform) ? config.platform : 'custom'
  return (
    <span className='bg-muted/60 inline-flex flex-wrap items-center gap-1.5 rounded-full border px-[var(--space-3)] py-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
      <span className='font-semibold'>{config.n_teams}-team</span>
      <span aria-hidden>·</span>
      <span>{scoringLabel(config.scoring)}</span>
      <span aria-hidden>·</span>
      <span style={{ color: PLATFORM_ACCENT[platform] }} className='font-semibold'>
        {PLATFORM_LABELS[platform]}
        {platform !== 'custom' ? ' roster' : ''}
      </span>
      <span aria-hidden>·</span>
      <span>pick #{config.user_pick}</span>
      <Button
        variant='link'
        size='sm'
        className='text-primary h-auto p-0 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
        onClick={onChange}
      >
        Change
      </Button>
    </span>
  )
}
