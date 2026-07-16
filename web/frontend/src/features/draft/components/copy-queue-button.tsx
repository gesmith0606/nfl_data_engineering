'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Icons } from '@/components/icons'

interface CopyQueueButtonProps {
  players: Array<{ player_name: string; position: string }>
  label?: string
}

/**
 * Copy the current recommendation list as a numbered queue. The point:
 * paste/preload it into the platform's pick queue (Sleeper, ESPN, and Yahoo
 * all autopick from your queue first), so even if the timer expires the
 * platform drafts OUR board — not its consensus list. Autodraft insurance.
 */
export function CopyQueueButton({ players, label = 'Copy queue' }: CopyQueueButtonProps) {
  const [copied, setCopied] = useState(false)

  if (players.length === 0) return null

  const handleCopy = async () => {
    const text = players
      .map((p, i) => `${i + 1}. ${p.player_name} (${p.position})`)
      .join('\n')
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard unavailable (permissions / insecure context) — no-op.
    }
  }

  return (
    <Button variant='outline' size='sm' onClick={() => void handleCopy()}>
      <Icons.clipboardText className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
      {copied ? 'Copied ✓' : label}
    </Button>
  )
}
