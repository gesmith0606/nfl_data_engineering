'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Icons } from '@/components/icons'
import { syncPickLog } from '@/features/nfl/api/service'
import { nflKeys } from '@/features/nfl/api/queries'
import { PressScale } from '@/lib/motion-primitives'
import type { DraftSyncLogResponse } from '@/lib/nfl/types'

interface PasteSyncPanelProps {
  sessionId: string | null
  /** Snake slot for attributing synced picks to the user's roster. */
  mySlot?: number
}

/**
 * Paste-sync — ESPN's better-than-mirror-mode path. ESPN has no live draft
 * API, but its draft room shows a copyable pick history: select it, paste it
 * here, and every recognized pick is applied to the board in one shot instead
 * of one Taken click per pick. Re-pasting the full history is safe.
 */
export function PasteSyncPanel({ sessionId, mySlot }: PasteSyncPanelProps) {
  const [text, setText] = useState('')
  const [result, setResult] = useState<DraftSyncLogResponse | null>(null)
  const queryClient = useQueryClient()

  const syncMutation = useMutation({
    mutationFn: () =>
      syncPickLog({
        session_id: sessionId ?? '',
        text,
        my_slot: mySlot
      }),
    onSuccess: data => {
      setResult(data)
      setText('')
      queryClient.invalidateQueries({
        queryKey: nflKeys.draftBoard(sessionId ?? undefined)
      })
      if (sessionId) {
        queryClient.invalidateQueries({
          queryKey: nflKeys.draftRecommendations(sessionId)
        })
      }
    }
  })

  if (!sessionId) return null

  return (
    <div className='rounded-md border p-[var(--space-3)] space-y-[var(--space-2)]'>
      <div className='flex items-center gap-[var(--space-2)]'>
        <Icons.clipboardText className='h-[var(--space-4)] w-[var(--space-4)]' />
        <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold'>
          Paste-sync pick history
        </p>
      </div>
      <p className='text-muted-foreground text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
        Copy the pick history from your draft room (ESPN: Pick History tab —
        select all, copy) and paste it here. One paste catches the whole board
        up; re-pasting the full history is safe.
      </p>
      <Textarea
        placeholder={'R1, P1  Bijan Robinson, RB\nR1, P2  Jahmyr Gibbs, RB\n…'}
        rows={4}
        value={text}
        onChange={e => setText(e.target.value)}
      />
      <div className='flex items-center gap-[var(--space-2)]'>
        <PressScale>
          <Button
            size='sm'
            disabled={!text.trim() || syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
          >
            {syncMutation.isPending ? 'Syncing…' : 'Sync picks'}
          </Button>
        </PressScale>
        {result && (
          <span className='text-muted-foreground text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
            {result.applied} applied
            {result.my_picks_applied > 0 ? ` (${result.my_picks_applied} yours)` : ''}
            {result.already_drafted > 0 ? ` · ${result.already_drafted} already on board` : ''}
            {result.unmatched_lines.length > 0
              ? ` · ${result.unmatched_lines.length} lines unrecognized`
              : ''}
            {' · '}
            {result.picks_taken} total picks
          </span>
        )}
        {syncMutation.isError && (
          <span className='text-destructive text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
            Sync failed — try again.
          </span>
        )}
      </div>
      {result && result.unmatched_lines.length > 0 && (
        <p className='text-muted-foreground text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
          Unrecognized: {result.unmatched_lines.slice(0, 5).join(' · ')}
          {result.unmatched_lines.length > 5 ? ' …' : ''}
        </p>
      )}
    </div>
  )
}
