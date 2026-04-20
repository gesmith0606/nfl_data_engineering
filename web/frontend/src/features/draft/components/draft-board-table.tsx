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
import type { DraftPlayer, Position, SortDirection } from '@/lib/nfl/types'

interface DraftBoardTableProps {
  players: DraftPlayer[]
  positionFilter: Position
  onDraft: (playerId: string) => void
  isPicking: boolean
}

type SortKey = 'model_rank' | 'projected_points' | 'adp_rank' | 'adp_diff' | 'vorp'

const POSITION_COLORS: Record<string, string> = {
  QB: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  RB: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  WR: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  TE: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  K: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300'
}

const VALUE_TIER_COLORS: Record<string, string> = {
  undervalued: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  fair_value: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  overvalued: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
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
    if (diff > 0) return 'text-green-600 dark:text-green-400'
    if (diff < 0) return 'text-red-600 dark:text-red-400'
    return 'text-muted-foreground'
  }

  return (
    <div className='space-y-[var(--space-3)]'>
      {/* Search bar */}
      <div className='relative'>
        <Icons.search className='text-muted-foreground absolute left-[var(--space-3)] top-1/2 h-[var(--space-4)] w-[var(--space-4)] -translate-y-1/2' />
        <input
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
              <TableHead className='w-20' />
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
              displayed.map(player => (
                <TableRow
                  key={player.player_id}
                  className='hover:bg-muted/40 transition-colors duration-[var(--motion-fast)]'
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
                        className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${POSITION_COLORS[player.position] ?? 'bg-gray-100 text-gray-700'}`}
                      >
                        {player.position}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                    {player.team ?? '—'}
                  </TableCell>
                  <TableCell className='font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums'>
                    {player.projected_points.toFixed(1)}
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
                    {player.vorp.toFixed(1)}
                  </TableCell>
                  <TableCell>
                    <span
                      className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${VALUE_TIER_COLORS[player.value_tier] ?? VALUE_TIER_COLORS['fair_value']}`}
                    >
                      {player.value_tier === 'undervalued'
                        ? 'Value'
                        : player.value_tier === 'overvalued'
                          ? 'Reach'
                          : 'Fair'}
                    </span>
                  </TableCell>
                  <TableCell>
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
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
