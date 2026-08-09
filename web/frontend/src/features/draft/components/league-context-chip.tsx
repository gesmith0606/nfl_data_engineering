'use client'

import { Button } from '@/components/ui/button'
import { PLATFORM_ACCENT, PLATFORM_LABELS, isRoomPlatform, scoringLabel } from '../utils/platform-presets'
import { WC_GHOST_BUTTON } from '../utils/broadcast-ui'
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
    <span className='wc-display inline-flex flex-wrap items-center gap-1.5 rounded-full border border-[rgba(145,237,208,0.25)] bg-[rgba(5,7,13,0.6)] px-[var(--space-3)] py-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.04em] text-[#cfd6e4]'>
      <span className='font-semibold text-[var(--wc-mint,#91edd0)]'>{config.n_teams}-team</span>
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
        className={`h-auto p-0 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] ${WC_GHOST_BUTTON}`}
        onClick={onChange}
      >
        Change
      </Button>
    </span>
  )
}
