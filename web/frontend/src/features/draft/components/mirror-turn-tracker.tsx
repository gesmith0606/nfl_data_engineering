'use client'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Icons } from '@/components/icons'
import { slotOnClock, nextPickForSlot, pickLabel } from '@/lib/nfl/draft-math'
import { useTurnAlert } from '../hooks/use-turn-alert'
import type { DraftPlatform } from '@/lib/nfl/types'

const PLATFORM_LABEL: Record<DraftPlatform, string> = {
  sleeper: 'Sleeper',
  espn: 'ESPN',
  yahoo: 'Yahoo'
}

interface MirrorTurnTrackerProps {
  platform: DraftPlatform
  picksTaken: number
  nTeams: number
  mySlot: number
  onSlotChange: (slot: number) => void
  onExit: () => void
}

/**
 * Turn tracker for mirror mode (ESPN / Yahoo — no pick auto-sync). As long as
 * every pick is recorded with Draft/Taken, snake math tells us exactly who is
 * on the clock and when your pick lands — with the same chime + notification
 * + tab-flash alerts as the Sleeper auto-sync panel.
 */
export function MirrorTurnTracker({
  platform,
  picksTaken,
  nTeams,
  mySlot,
  onSlotChange,
  onExit
}: MirrorTurnTrackerProps) {
  const nextPickNo = picksTaken + 1
  const onClock = slotOnClock(nextPickNo, nTeams)
  const validSlot = mySlot >= 1 && mySlot <= nTeams
  const isMyTurn = validSlot && onClock === mySlot
  const myNextPickNo = validSlot ? nextPickForSlot(nextPickNo, mySlot, nTeams) : null
  const picksUntil = myNextPickNo != null ? myNextPickNo - nextPickNo : null

  useTurnAlert(
    isMyTurn,
    validSlot,
    `Pick ${pickLabel(nextPickNo, nTeams)} on ${PLATFORM_LABEL[platform]} — the GIQ board has your call ready.`
  )

  return (
    <div
      className={`flex flex-wrap items-center gap-[var(--space-3)] rounded-md border p-[var(--space-3)] ${
        isMyTurn ? 'border-emerald-500 bg-emerald-500/5' : ''
      }`}
    >
      <span className='inline-flex items-center gap-1 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold text-emerald-500'>
        <span className='h-2 w-2 rounded-full bg-emerald-500 animate-pulse' />
        MIRRORING {PLATFORM_LABEL[platform].toUpperCase()}
      </span>
      <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium'>
        {isMyTurn
          ? `🟢 YOU'RE ON THE CLOCK (pick ${pickLabel(nextPickNo, nTeams)})`
          : `Pick ${pickLabel(nextPickNo, nTeams)} · slot ${onClock} on the clock`}
      </span>
      {!isMyTurn && picksUntil != null && (
        <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
          your pick in {picksUntil}
        </span>
      )}
      <label
        htmlFor='mirror-slot'
        className='ml-auto flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
      >
        <span className='text-muted-foreground'>My slot</span>
        <Input
          id='mirror-slot'
          className='w-16'
          inputMode='numeric'
          value={mySlot > 0 ? String(mySlot) : ''}
          onChange={e => onSlotChange(Number(e.target.value) || 0)}
        />
      </label>
      <Button variant='ghost' size='sm' onClick={onExit}>
        <Icons.close className='mr-1 h-[var(--space-4)] w-[var(--space-4)]' />
        Exit mirror
      </Button>
    </div>
  )
}
