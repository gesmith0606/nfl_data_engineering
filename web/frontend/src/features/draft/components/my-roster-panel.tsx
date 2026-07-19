'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Stagger } from '@/lib/motion-primitives'
import type { DraftPlayer } from '@/lib/nfl/types'

interface MyRosterPanelProps {
  roster: DraftPlayer[]
  remainingNeeds: Record<string, number>
  picksCount: number
}

const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE', 'K', 'FLEX', 'BENCH']

function groupByPosition(players: DraftPlayer[]): Record<string, DraftPlayer[]> {
  return players.reduce<Record<string, DraftPlayer[]>>((acc, p) => {
    const pos = p.position
    if (!acc[pos]) acc[pos] = []
    acc[pos].push(p)
    return acc
  }, {})
}

export function MyRosterPanel({ roster, remainingNeeds, picksCount }: MyRosterPanelProps) {
  const grouped = groupByPosition(roster)

  const sortedPositions = [
    ...POSITION_ORDER.filter(p => grouped[p]),
    ...Object.keys(grouped).filter(p => !POSITION_ORDER.includes(p))
  ]

  const needs = Object.entries(remainingNeeds).filter(([, count]) => count > 0)

  return (
    <Card>
      <CardHeader className='pb-[var(--space-2)]'>
        <CardTitle className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
          My Team ({picksCount} pick{picksCount !== 1 ? 's' : ''})
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-[var(--space-3)] pt-0'>
        {roster.length === 0 ? (
          <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            No players drafted yet. Click &apos;Draft&apos; on any player to start.
          </p>
        ) : (
          <Stagger className='space-y-[var(--space-2)]'>
            {sortedPositions.map(pos => (
              <div key={pos}>
                <p className='text-muted-foreground mb-0.5 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold uppercase tracking-wide'>
                  {pos}
                </p>
                <div className='space-y-0.5'>
                  {grouped[pos].map(player => (
                    <div
                      key={player.player_id}
                      className='flex items-center justify-between rounded px-[var(--space-1)] py-0.5'
                    >
                      <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                        {player.player_name}
                      </span>
                      <div className='flex items-center gap-[var(--space-1)]'>
                        {player.team && (
                          <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                            {player.team}
                          </span>
                        )}
                        <span className='text-muted-foreground font-mono text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tabular-nums'>
                          {player.projected_points.toFixed(0)}pt
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </Stagger>
        )}

        {needs.length > 0 && (
          <div className='border-t pt-[var(--space-2)]'>
            <p className='text-muted-foreground mb-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold uppercase tracking-wide'>
              Remaining Needs
            </p>
            <div className='flex flex-wrap gap-[var(--space-1)]'>
              {needs.map(([pos, count]) => (
                <span
                  key={pos}
                  className='bg-muted text-muted-foreground inline-flex items-center rounded px-[var(--space-2)] py-0.5 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
                >
                  {pos} ×{count}
                </span>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
