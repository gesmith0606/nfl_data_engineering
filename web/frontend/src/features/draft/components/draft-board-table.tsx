'use client'

import { useState, useMemo } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Icons } from '@/components/icons'
import { PressScale } from '@/lib/motion-primitives'
import { getPositionBadgeClass } from '@/lib/nfl/position-colors'
import { SUCCESS_BADGE, DANGER_BADGE, deltaTextClass } from '@/lib/nfl/semantic-colors'
import type { DraftPlayer, Position, SortDirection } from '@/lib/nfl/types'

interface DraftBoardTableProps {
  players: DraftPlayer[]
  positionFilter: Position
  onDraft: (playerId: string, byMe?: boolean) => void
  isPicking: boolean
}

type SortKey = 'model_rank' | 'projected_points' | 'adp_rank' | 'adp_diff' | 'vorp'

const VALUE_TIER_COLORS: Record<string, string> = {
  undervalued: SUCCESS_BADGE,
  fair_value: 'bg-muted text-muted-foreground',
  overvalued: DANGER_BADGE
}

function SortableHeader({
  label,
  sortKey,
  currentKey,
  direction,
  onSort
}: {
  label: string
  sortKey: SortKey
  currentKey: SortKey
  direction: SortDirection
  onSort: (key: SortKey) => void
}) {
  const isActive = sortKey === currentKey
  return (
    <TableHead
      className='cursor-pointer select-none whitespace-nowrap'
      onClick={() => onSort(sortKey)}
    >
      <span className='flex items-center gap-[var(--space-1)]'>
        {label}
        {isActive ? (
          direction === 'asc' ? (
            <Icons.chevronUp className='h-[var(--space-3)] w-[var(--space-3)]' />
          ) : (
            <Icons.chevronDown className='h-[var(--space-3)] w-[var(--space-3)]' />
          )
        ) : (
          <Icons.chevronsUpDown className='text-muted-foreground h-[var(--space-3)] w-[var(--space-3)]' />
        )}
      </span>
    </TableHead>
  )
}

export function DraftBoardTable({ players, positionFilter, onDraft, isPicking }: DraftBoardTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('model_rank')
  const [sortDir, setSortDir] = useState<SortDirection>('asc')
  const [search, setSearch] = useState('')

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const filtered = useMemo(() => {
    let result = players
    if (positionFilter !== 'ALL') {
      result = result.filter(p => p.position === positionFilter)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(p => p.player_name.toLowerCase().includes(q))
    }
    return [...result].sort((a, b) => {
      const aVal = a[sortKey]
      const bVal = b[sortKey]
      if (aVal === null || aVal === undefined) return 1
      if (bVal === null || bVal === undefined) return -1
      const cmp = (aVal as number) - (bVal as number)
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [players, positionFilter, search, sortKey, sortDir])

  const displayed = filtered.slice(0, 200)

  function adpDiffColor(diff: number | null): string {
    if (diff === null) return 'text-muted-foreground'
    return deltaTextClass(diff)
  }

  return (
    <div className='space-y-[var(--space-3)]'>
      {/* Search bar */}
      <div className='relative'>
        <label htmlFor='player-search' className='sr-only'>
          Search players
        </label>
        <Icons.search className='text-muted-foreground absolute left-[var(--space-3)] top-1/2 h-[var(--space-4)] w-[var(--space-4)] -translate-y-1/2' />
        <input
          id='player-search'
          type='text'
          placeholder='Search players...'
          value={search}
          onChange={e => setSearch(e.target.value)}
          className='border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex h-9 w-full rounded-md border px-[var(--space-3)] py-[var(--space-1)] pl-[var(--space-10)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] shadow-sm transition-colors file:border-0 file:bg-transparent file:text-[length:var(--fs-sm)] file:font-medium focus-visible:outline-none focus-visible:ring-1 disabled:cursor-not-allowed disabled:opacity-50'
        />
      </div>

      {/* Count */}
      <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
        Showing {displayed.length} of {filtered.length} available players
      </p>

      {/* Mobile (Phase 62-05 DSGN-04): wrap the 9-column table in a horizontal
       *  scroll container so the draft board remains usable at 375px without
       *  overflowing the page gutter. */}
      <div className='rounded-md border overflow-x-auto'>
        <Table>
          <TableHeader>
            <TableRow>
              <SortableHeader
                label='Rank'
                sortKey='model_rank'
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
              <TableHead>Player</TableHead>
              <TableHead>Team</TableHead>
              <SortableHeader
                label='Pts'
                sortKey='projected_points'
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
              <SortableHeader
                label='ADP'
                sortKey='adp_rank'
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
              <SortableHeader
                label='Value'
                sortKey='adp_diff'
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
              <SortableHeader
                label='VORP'
                sortKey='vorp'
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
              <TableHead>Tier</TableHead>
              <TableHead className='w-32' />
            </TableRow>
          </TableHeader>
          <TableBody>
            {displayed.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={9}
                  className='text-muted-foreground py-[var(--space-12)] text-center text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'
                >
                  No players match your filter.
                </TableCell>
              </TableRow>
            ) : (
              displayed.map((player, i) => {
                // Subtle divider between draft tiers — only meaningful while
                // sorted by rank, where tiers group into contiguous runs.
                const prevTier = i > 0 ? displayed[i - 1].tier : undefined
                const isTierBoundary =
                  sortKey === 'model_rank' &&
                  player.tier != null &&
                  prevTier != null &&
                  player.tier !== prevTier
                return (
                  <TableRow
                    key={player.player_id}
                    className={`hover:bg-muted/40 transition-colors duration-[var(--motion-fast)] ${isTierBoundary ? 'border-t-2' : ''}`}
                  >
                    <TableCell className='font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums'>
                      {player.model_rank}
                    </TableCell>
                    <TableCell>
                      <div className='flex items-center gap-[var(--space-2)]'>
                        <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                          {player.player_name}
                        </span>
                        <span
                          className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${getPositionBadgeClass(player.position)}`}
                        >
                          {player.position}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                      {player.team ?? '—'}
                    </TableCell>
                    <TableCell className='font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums'>
                      {player.projected_points != null ? player.projected_points.toFixed(1) : '—'}
                    </TableCell>
                    <TableCell className='font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums'>
                      {player.adp_rank !== null ? player.adp_rank.toFixed(0) : '—'}
                    </TableCell>
                    <TableCell
                      className={`font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums ${adpDiffColor(player.adp_diff)}`}
                    >
                      {player.adp_diff !== null
                        ? (player.adp_diff > 0 ? '+' : '') + player.adp_diff.toFixed(1)
                        : '—'}
                    </TableCell>
                    <TableCell className='font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums'>
                      {player.vorp != null ? player.vorp.toFixed(1) : '—'}
                    </TableCell>
                    <TableCell>
                      <div className='flex items-center gap-[var(--space-1)]'>
                        {player.tier != null && (
                          <span
                            className='bg-muted text-foreground inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold'
                            title={`Tier ${player.tier}`}
                          >
                            {`T${player.tier}`}
                          </span>
                        )}
                        <span
                          className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${VALUE_TIER_COLORS[player.value_tier] ?? VALUE_TIER_COLORS['fair_value']}`}
                        >
                          {player.value_tier === 'undervalued'
                            ? 'Value'
                            : player.value_tier === 'overvalued'
                              ? 'Reach'
                              : 'Fair'}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className='flex items-center gap-[var(--space-1)]'>
                        <PressScale>
                          <Button
                            variant='outline'
                            size='sm'
                            onClick={() => onDraft(player.player_id)}
                            disabled={isPicking}
                          >
                            Draft
                          </Button>
                        </PressScale>
                        <PressScale>
                          <Button
                            variant='ghost'
                            size='sm'
                            title='Mark as drafted by another team'
                            onClick={() => onDraft(player.player_id, false)}
                            disabled={isPicking}
                          >
                            Taken
                          </Button>
                        </PressScale>
                      </span>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
