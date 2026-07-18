'use client'

import { useEffect, useRef, useState } from 'react'
import { Icons } from '@/components/icons'
import { Button } from '@/components/ui/button'
import { DANGER_TEXT } from '@/lib/nfl/semantic-colors'
import { isAudioMuted, setAudioMuted, playTick } from '../hooks/use-turn-alert'

interface PickClockProps {
  /** Current pick number — the countdown resets whenever this changes. */
  pickNumber: number
  /**
   * Seconds to count down from. `null`/`0` hides the clock entirely — used
   * in live mode when the platform API doesn't provide pick timing.
   */
  timerSeconds: number | null
  /** Room-accent color for the ring/bar (falls back to the theme primary). */
  accentColor?: string
  /** Called once when the countdown reaches zero; fires again after the next reset. */
  onExpire?: () => void
}

const PULSE_THRESHOLD_SECONDS = 10

function formatClock(totalSeconds: number): string {
  const clamped = Math.max(0, totalSeconds)
  const minutes = Math.floor(clamped / 60)
  const seconds = clamped % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

/**
 * Countdown pick clock for mock/manual draft modes. Resets to `timerSeconds`
 * every time `pickNumber` advances. Under 10s it pulses red regardless of
 * room accent (urgency trumps branding) and optionally plays a soft tick —
 * muted by default via the shared draft-audio mute control (use-turn-alert).
 */
export function PickClock({
  pickNumber,
  timerSeconds,
  accentColor = 'var(--primary)',
  onExpire
}: PickClockProps) {
  const [remaining, setRemaining] = useState(timerSeconds ?? 0)
  const [muted, setMuted] = useState(true)
  const expiredRef = useRef(false)

  useEffect(() => {
    setMuted(isAudioMuted())
  }, [])

  // Reset the countdown whenever the pick advances or the room's timer length changes.
  useEffect(() => {
    setRemaining(timerSeconds ?? 0)
    expiredRef.current = false
  }, [pickNumber, timerSeconds])

  useEffect(() => {
    if (!timerSeconds) return
    const id = window.setInterval(() => {
      setRemaining(r => Math.max(0, r - 1))
    }, 1000)
    return () => window.clearInterval(id)
  }, [pickNumber, timerSeconds])

  useEffect(() => {
    if (muted || remaining <= 0 || remaining > PULSE_THRESHOLD_SECONDS) return
    playTick()
  }, [remaining, muted])

  useEffect(() => {
    if (!timerSeconds || remaining > 0 || expiredRef.current) return
    expiredRef.current = true
    onExpire?.()
  }, [remaining, timerSeconds, onExpire])

  if (!timerSeconds) return null

  const isUrgent = remaining <= PULSE_THRESHOLD_SECONDS
  const pct = Math.min(100, Math.max(0, (remaining / timerSeconds) * 100))

  function toggleMute() {
    const next = !muted
    setMuted(next)
    setAudioMuted(next)
  }

  return (
    <div className='flex items-center gap-[var(--space-2)]'>
      <div
        className={`flex items-center gap-[var(--space-2)] rounded-md border px-[var(--space-2)] py-1 ${isUrgent ? 'animate-pulse' : ''}`}
        style={{ borderColor: isUrgent ? undefined : accentColor }}
      >
        <span
          role='timer'
          className={`font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold tabular-nums ${isUrgent ? DANGER_TEXT : ''}`}
          style={isUrgent ? undefined : { color: accentColor }}
        >
          {formatClock(remaining)}
        </span>
        <span className='bg-muted h-1.5 w-16 overflow-hidden rounded-full'>
          <span
            className='block h-full rounded-full transition-[width] duration-1000 ease-linear'
            style={{ width: `${pct}%`, backgroundColor: isUrgent ? 'var(--danger)' : accentColor }}
          />
        </span>
      </div>
      <Button
        variant='ghost'
        size='icon'
        className={`h-7 w-7 ${muted ? 'opacity-40' : ''}`}
        onClick={toggleMute}
        aria-label={muted ? 'Unmute pick clock sound' : 'Mute pick clock sound'}
        title={muted ? 'Unmute pick clock sound' : 'Mute pick clock sound'}
      >
        <Icons.music className='h-[var(--space-4)] w-[var(--space-4)]' />
      </Button>
    </div>
  )
}
