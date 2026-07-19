'use client'

import { useQuery } from '@tanstack/react-query'
import { Icons } from '@/components/icons'
import { DataLoadReveal, Stagger } from '@/lib/motion-primitives'
import { sleepersQueryOptions } from '@/features/nfl/api/queries'
import { normalizeSleepers } from '@/lib/nfl/api'
import { getPositionBadgeClass } from '@/lib/nfl/position-colors'
import { SUCCESS_TEXT } from '@/lib/nfl/semantic-colors'

interface SleepersPanelProps {
  sessionId: string | null
}

/**
 * Model-vs-ADP sleeper edges (GET /api/draft/sleepers — a parallel backend
 * lane that may 404 today). Degrades to the same empty state as "no edges
 * right now" on any error, per the graceful-degradation contract.
 */
export function SleepersPanel({ sessionId }: SleepersPanelProps) {
  const { data, isLoading, isError } = useQuery(sleepersQueryOptions(sessionId ?? '', 20))
  const sleepers = isError ? [] : normalizeSleepers(data)

  if (!sessionId) {
    return (
      <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
        Initialize a draft to see sleepers.
      </p>
    )
  }

  return (
    <DataLoadReveal
      loading={isLoading}
      skeleton={
        <div className='flex items-center gap-[var(--space-2)] py-[var(--space-6)]'>
          <Icons.spinner className='text-muted-foreground h-[var(--space-5)] w-[var(--space-5)] animate-spin' />
          <span className='text-muted-foreground text-[length:var(--fs-sm)]'>Loading sleepers...</span>
        </div>
      }
    >
      {sleepers.length === 0 ? (
        <p className='text-muted-foreground py-[var(--space-6)] text-center text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
          No sleeper edges right now.
        </p>
      ) : (
        <Stagger className='space-y-[var(--space-2)]'>
          {sleepers.map((s, i) => (
            <div
              key={`${s.player_name}-${i}`}
              className='rounded-md border p-[var(--space-3)] space-y-1'
            >
              <div className='flex items-center justify-between gap-[var(--space-2)]'>
                <div className='flex items-center gap-[var(--space-2)]'>
                  <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                    {s.player_name}
                  </span>
                  <span
                    className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${getPositionBadgeClass(s.position)}`}
                  >
                    {s.position}
                  </span>
                  {s.team && (
                    <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                      {s.team}
                    </span>
                  )}
                </div>
                <span className='text-muted-foreground font-mono text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tabular-nums'>
                  Rank {s.model_rank}
                  {s.adp_rank != null ? ` · ADP ${s.adp_rank}` : ''}
                  {s.adp_gap != null && (
                    <span className={`ml-1 ${SUCCESS_TEXT}`}>
                      (+{s.adp_gap} gap)
                    </span>
                  )}
                </span>
              </div>
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                {s.reason}
              </p>
            </div>
          ))}
        </Stagger>
      )}
    </DataLoadReveal>
  )
}
