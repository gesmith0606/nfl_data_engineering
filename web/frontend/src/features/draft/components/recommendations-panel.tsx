'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Icons } from '@/components/icons'
import { DataLoadReveal, HoverLift, Stagger } from '@/lib/motion-primitives'
import { draftRecommendationsQueryOptions } from '@/features/nfl/api/queries'
import { getPositionBadgeClass } from '@/lib/nfl/position-colors'
import { DANGER_TEXT, WARN_TEXT } from '@/lib/nfl/semantic-colors'
import { computeTierExhaustion } from '../utils/tier-exhaustion'
import { CopyQueueButton } from './copy-queue-button'
import type { DraftPlayer, Position } from '@/lib/nfl/types'

interface RecommendationsPanelProps {
  sessionId: string | null
  positionFilter: Position
  /** Current board pool (undrafted players) — powers the tier-exhaustion cue. */
  players?: DraftPlayer[]
}

/** >70% gone reads urgent, <30% reads safe; the middle band stays neutral. */
function goneProbabilityColor(p: number): string {
  if (p > 0.7) return DANGER_TEXT
  if (p < 0.3) return 'text-muted-foreground'
  return ''
}

export function RecommendationsPanel({ sessionId, positionFilter, players = [] }: RecommendationsPanelProps) {
  const { data, isLoading, isError } = useQuery({
    ...draftRecommendationsQueryOptions(
      sessionId ?? '',
      5,
      positionFilter !== 'ALL' ? positionFilter : undefined
    ),
    enabled: !!sessionId
  })

  const tierWarnings = useMemo(() => computeTierExhaustion(players), [players])

  return (
    <Card>
      <CardHeader className='pb-[var(--space-2)]'>
        <div className='flex items-center justify-between gap-[var(--space-2)]'>
          <CardTitle className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
            Recommendations
          </CardTitle>
          <CopyQueueButton players={data?.recommendations ?? []} />
        </div>
      </CardHeader>
      <CardContent className='space-y-[var(--space-2)] pt-0'>
        {tierWarnings.length > 0 && (
          <div className='space-y-0.5 border-b pb-[var(--space-2)]'>
            {tierWarnings.map(w => (
              <p
                key={w.position}
                className={`text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium ${w.count === 1 ? WARN_TEXT : 'text-muted-foreground'}`}
              >
                {w.position} Tier {w.tier}: {w.count} left
              </p>
            ))}
          </div>
        )}
        {!sessionId ? (
          <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            Initialize a draft to see recommendations.
          </p>
        ) : (
          <DataLoadReveal
            loading={isLoading}
            skeleton={
              <div className='flex items-center gap-[var(--space-2)] py-[var(--space-4)]'>
                <Icons.spinner className='text-muted-foreground h-[var(--space-4)] w-[var(--space-4)] animate-spin' />
                <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  Loading...
                </span>
              </div>
            }
          >
            {isError ? (
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                Failed to load recommendations.
              </p>
            ) : !data || data.recommendations.length === 0 ? (
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                No recommendations available.
              </p>
            ) : (
              <div className='space-y-[var(--space-2)]'>
                <Stagger className='space-y-[var(--space-2)]'>
                  {data.recommendations.map((rec, i) => (
                    <HoverLift key={rec.player_id} lift={1}>
                      <div className='flex items-center justify-between rounded-md p-[var(--space-2)] hover:bg-muted/40 transition-colors duration-[var(--motion-fast)]'>
                        <div className='flex items-center gap-[var(--space-2)]'>
                          <span className='text-muted-foreground font-mono text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tabular-nums'>
                            #{i + 1}
                          </span>
                          <div>
                            <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                              {rec.player_name}
                            </p>
                            <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                              {rec.team ?? 'FA'} · {rec.projected_points.toFixed(0)}pt · VORP{' '}
                              {rec.vorp.toFixed(1)}
                            </p>
                            {rec.gone_probability != null && (
                              <p className={`text-[length:var(--fs-micro)] leading-[var(--lh-micro)] ${goneProbabilityColor(rec.gone_probability)}`}>
                                {Math.round(rec.gone_probability * 100)}% gone by your next pick
                              </p>
                            )}
                          </div>
                        </div>
                        <span
                          className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${getPositionBadgeClass(rec.position)}`}
                        >
                          {rec.position}
                        </span>
                      </div>
                    </HoverLift>
                  ))}
                </Stagger>

                {data.reasoning && (
                  <p className='text-muted-foreground border-t pt-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] italic'>
                    {data.reasoning}
                  </p>
                )}

                <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  Recommendations update after each pick.
                </p>
              </div>
            )}
          </DataLoadReveal>
        )}
      </CardContent>
    </Card>
  )
}
