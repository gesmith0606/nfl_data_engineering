'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
      <CardHeader className='pb-2'>
        <CardTitle className='text-sm font-semibold'>
          My Team ({picksCount} pick{picksCount !== 1 ? 's' : ''})
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-3 pt-0'>
        {roster.length === 0 ? (
          <p className='text-muted-foreground text-xs'>
            No players drafted yet. Click &apos;Draft&apos; on any player to start.
          </p>
        ) : (
          <div className='space-y-2'>
            {sortedPositions.map(pos => (
              <div key={pos}>
                <p className='text-muted-foreground mb-0.5 text-xs font-semibold uppercase tracking-wide'>
                  {pos}
                </p>
                <div className='space-y-0.5'>
                  {grouped[pos].map(player => (
                    <div
                      key={player.player_id}
                      className='flex items-center justify-between rounded px-1 py-0.5'
                    >
                      <span className='text-sm font-medium'>{player.player_name}</span>
                      <div className='flex items-center gap-1'>
                        {player.team && (
                          <span className='text-muted-foreground text-xs'>{player.team}</span>
                        )}
                        <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                          {player.projected_points.toFixed(0)}pt
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {needs.length > 0 && (
          <div className='border-t pt-2'>
            <p className='text-muted-foreground mb-1 text-xs font-semibold uppercase tracking-wide'>
              Remaining Needs
            </p>
            <div className='flex flex-wrap gap-1'>
              {needs.map(([pos, count]) => (
                <span
                  key={pos}
                  className='bg-muted text-muted-foreground inline-flex items-center rounded px-1.5 py-0.5 text-xs'
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
