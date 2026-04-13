'use client'

import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Icons } from '@/components/icons'
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
      <CardHeader className='pb-2'>
        <CardTitle className='text-sm font-semibold'>Recommendations</CardTitle>
      </CardHeader>
      <CardContent className='space-y-2 pt-0'>
        {!sessionId ? (
          <p className='text-muted-foreground text-xs'>
            Initialize a draft to see recommendations.
          </p>
        ) : isLoading ? (
          <div className='flex items-center gap-2 py-4'>
            <Icons.spinner className='text-muted-foreground h-4 w-4 animate-spin' />
            <span className='text-muted-foreground text-xs'>Loading...</span>
          </div>
        ) : isError ? (
          <p className='text-muted-foreground text-xs'>Failed to load recommendations.</p>
        ) : !data || data.recommendations.length === 0 ? (
          <p className='text-muted-foreground text-xs'>No recommendations available.</p>
        ) : (
          <>
            <div className='space-y-1.5'>
              {data.recommendations.map((rec, i) => (
                <div
                  key={rec.player_id}
                  className='flex items-center justify-between rounded-md p-1.5 hover:bg-muted/40'
                >
                  <div className='flex items-center gap-2'>
                    <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                      #{i + 1}
                    </span>
                    <div>
                      <p className='text-sm font-medium leading-tight'>{rec.player_name}</p>
                      <p className='text-muted-foreground text-xs'>
                        {rec.team ?? 'FA'} · {rec.projected_points.toFixed(0)}pt · VORP {rec.vorp.toFixed(1)}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-xs font-semibold ${POSITION_COLORS[rec.position] ?? 'bg-gray-100 text-gray-700'}`}
                  >
                    {rec.position}
                  </span>
                </div>
              ))}
            </div>

            {data.reasoning && (
              <p className='text-muted-foreground border-t pt-2 text-xs italic'>
                {data.reasoning}
              </p>
            )}

            <p className='text-muted-foreground text-xs'>
              Recommendations update after each pick.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
