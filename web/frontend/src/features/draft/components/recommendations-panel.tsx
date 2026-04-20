'use client'

import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Icons } from '@/components/icons'
import { DataLoadReveal, HoverLift, Stagger } from '@/lib/motion-primitives'
import { draftRecommendationsQueryOptions } from '@/features/nfl/api/queries'
import type { Position } from '@/lib/nfl/types'

interface RecommendationsPanelProps {
  sessionId: string | null
  positionFilter: Position
}

const POSITION_COLORS: Record<string, string> = {
  QB: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  RB: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  WR: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  TE: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  K: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300'
}

export function RecommendationsPanel({ sessionId, positionFilter }: RecommendationsPanelProps) {
  const { data, isLoading, isError } = useQuery({
    ...draftRecommendationsQueryOptions(
      sessionId ?? '',
      5,
      positionFilter !== 'ALL' ? positionFilter : undefined
    ),
    enabled: !!sessionId
  })

  return (
    <Card>
      <CardHeader className='pb-[var(--space-2)]'>
        <CardTitle className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
          Recommendations
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-[var(--space-2)] pt-0'>
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
                          </div>
                        </div>
                        <span
                          className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${POSITION_COLORS[rec.position] ?? 'bg-gray-100 text-gray-700'}`}
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
