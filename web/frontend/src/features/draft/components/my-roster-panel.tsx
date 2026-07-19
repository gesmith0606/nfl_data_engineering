'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Stagger } from '@/lib/motion-primitives'
import { SUCCESS_TEXT, WARN_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors'
import type { DraftPlayer, RosterRisk } from '@/lib/nfl/types'

interface MyRosterPanelProps {
  roster: DraftPlayer[]
  remainingNeeds: Record<string, number>
  picksCount: number
  /** Aggregate floor/ceiling exposure of the roster; omitted/null hides the meter. */
  rosterRisk?: RosterRisk | null
}

const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE', 'K', 'FLEX', 'BENCH']

const VOLATILITY_STEADY_MAX = 0.35
const VOLATILITY_BALANCED_MAX = 0.55

/* Bar-fill classes are kept as full literals (not built via string
 * interpolation) so Tailwind's static class-name scanner picks them up --
 * see the same note in lib/nfl/position-colors.ts. */
function volatilityLabel(index: number): { label: string; textClass: string; barClass: string } {
  if (index > VOLATILITY_BALANCED_MAX) {
    return { label: 'Volatile roster — high ceiling, low floor', textClass: DANGER_TEXT, barClass: 'bg-[var(--danger)]' }
  }
  if (index >= VOLATILITY_STEADY_MAX) {
    return { label: 'Balanced roster', textClass: WARN_TEXT, barClass: 'bg-[var(--warn)]' }
  }
  return { label: 'Steady roster', textClass: SUCCESS_TEXT, barClass: 'bg-[var(--success)]' }
}

function groupByPosition(players: DraftPlayer[]): Record<string, DraftPlayer[]> {
  return players.reduce<Record<string, DraftPlayer[]>>((acc, p) => {
    const pos = p.position
    if (!acc[pos]) acc[pos] = []
    acc[pos].push(p)
    return acc
  }, {})
}

export function MyRosterPanel({ roster, remainingNeeds, picksCount, rosterRisk }: MyRosterPanelProps) {
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
                          {player.projected_points != null ? `${player.projected_points.toFixed(0)}pt` : '—'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </Stagger>
        )}

        {rosterRisk && (
          <div className='border-t pt-[var(--space-2)]'>
            <p className='text-muted-foreground mb-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold uppercase tracking-wide'>
              Roster Risk
            </p>
            <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              Floor {rosterRisk.floor_sum.toFixed(0)} · Ceiling {rosterRisk.ceiling_sum.toFixed(0)}
            </p>
            {rosterRisk.volatility_index != null && (
              <div className='mt-[var(--space-1)]'>
                {(() => {
                  const { label, textClass, barClass } = volatilityLabel(rosterRisk.volatility_index)
                  const pct = Math.min(100, Math.max(0, rosterRisk.volatility_index * 100))
                  return (
                    <>
                      <span className='bg-muted block h-1.5 w-full overflow-hidden rounded-full'>
                        <span className={`block h-full rounded-full ${barClass}`} style={{ width: `${pct}%` }} />
                      </span>
                      <p className={`mt-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] ${textClass}`}>
                        {label}
                      </p>
                    </>
                  )
                })()}
              </div>
            )}
          </div>
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
