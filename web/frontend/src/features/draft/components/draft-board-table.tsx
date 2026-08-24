'use client';

import { useState, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Icons } from '@/components/icons';
import { PressScale } from '@/lib/motion-primitives';
import { getPositionBadgeClass } from '@/lib/nfl/position-colors';
import { SUCCESS_BADGE, DANGER_BADGE, deltaTextClass } from '@/lib/nfl/semantic-colors';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { WC_CTA_BUTTON, WC_OUTLINE_BUTTON, WC_INPUT, WC_NUM_HERO } from '../utils/broadcast-ui';
import { StackBadge } from './stack-badge';
import type { DraftPlayer, Position, SortDirection, StackHint } from '@/lib/nfl/types';

export type DraftBoardSortKey = 'model_rank' | 'projected_points' | 'adp_rank' | 'adp_diff' | 'vorp';

interface DraftBoardTableProps {
  players: DraftPlayer[];
  positionFilter: Position;
  /** Required unless `readOnly` — the ADP page renders the board without pick controls. */
  onDraft?: (playerId: string, byMe?: boolean) => void;
  isPicking?: boolean;
  /** Stack/overlap hints keyed by player_name; omitted rows simply render no badge. */
  hintsByPlayerName?: Map<string, StackHint[]>;
  /** Hide the Draft/Taken controls (public ADP rankings view). */
  readOnly?: boolean;
  /** Initial sort column; the draft room keeps `model_rank`, the ADP page starts on `adp_rank`. */
  defaultSort?: DraftBoardSortKey;
}

type SortKey = DraftBoardSortKey;

/** A displayed row plus the tier-boundary flag precomputed at sort time — the
 *  BroadcastTable `rowClassName` callback only receives the row, not its
 *  neighbors, so the boundary check has to happen before render. */
type DisplayRow = DraftPlayer & { __tierBoundary: boolean };

const VALUE_TIER_COLORS: Record<string, string> = {
  undervalued: SUCCESS_BADGE,
  fair_value: 'bg-muted text-muted-foreground',
  overvalued: DANGER_BADGE
};

function sortHeader(
  label: string,
  sortKey: SortKey,
  currentKey: SortKey,
  direction: SortDirection,
  onSort: (key: SortKey) => void
) {
  const isActive = sortKey === currentKey;
  return (
    <button
      type='button'
      onClick={() => onSort(sortKey)}
      className='flex items-center gap-[var(--space-1)] select-none'
    >
      {label}
      {isActive ? (
        direction === 'asc' ? (
          <Icons.chevronUp className='h-[var(--space-3)] w-[var(--space-3)]' />
        ) : (
          <Icons.chevronDown className='h-[var(--space-3)] w-[var(--space-3)]' />
        )
      ) : (
        <Icons.chevronsUpDown className='h-[var(--space-3)] w-[var(--space-3)] opacity-50' />
      )}
    </button>
  );
}

export function DraftBoardTable({
  players,
  positionFilter,
  onDraft,
  isPicking = false,
  hintsByPlayerName,
  readOnly = false,
  defaultSort = 'model_rank'
}: DraftBoardTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>(defaultSort);
  const [sortDir, setSortDir] = useState<SortDirection>('asc');
  const [search, setSearch] = useState('');

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  const filtered = useMemo(() => {
    let result = players;
    if (positionFilter !== 'ALL') {
      result = result.filter((p) => p.position === positionFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter((p) => p.player_name.toLowerCase().includes(q));
    }
    return [...result].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      const cmp = (aVal as number) - (bVal as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [players, positionFilter, search, sortKey, sortDir]);

  const displayed: DisplayRow[] = useMemo(() => {
    const sliced = filtered.slice(0, 200);
    return sliced.map((player, i) => {
      // Subtle divider between draft tiers — only meaningful while sorted by
      // rank, where tiers group into contiguous runs.
      const prevTier = i > 0 ? sliced[i - 1].tier : undefined;
      const isTierBoundary =
        sortKey === 'model_rank' &&
        player.tier != null &&
        prevTier != null &&
        player.tier !== prevTier;
      return { ...player, __tierBoundary: isTierBoundary };
    });
  }, [filtered, sortKey]);

  function adpDiffColor(diff: number | null): string {
    if (diff === null) return 'text-muted-foreground';
    return deltaTextClass(diff);
  }

  /**
   * Rookie-capital picks can push |adp_diff| into the hundreds, which reads
   * as a data glitch rather than signal. Cap the DISPLAYED magnitude at 99
   * ("99+"/"-99+"); sort/comparison logic upstream keeps using the raw value.
   */
  function formatAdpDiff(diff: number | null): string {
    if (diff === null) return '—';
    if (Math.abs(diff) > 99) return `${diff > 0 ? '+' : '-'}99+`;
    return (diff > 0 ? '+' : '') + diff.toFixed(1);
  }

  const columns: BroadcastColumn<DisplayRow>[] = [
    {
      key: 'rank',
      header: sortHeader('Rank', 'model_rank', sortKey, sortDir, handleSort),
      align: 'right',
      width: 'w-16',
      cellClassName: 'font-mono tabular-nums',
      accessor: (p) => p.model_rank
    },
    {
      key: 'player',
      header: 'Player',
      sticky: true,
      accessor: (p) => (
        <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
          <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
            {p.player_name}
          </span>
          <span
            className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${getPositionBadgeClass(p.position)}`}
          >
            {p.position}
          </span>
          {hintsByPlayerName?.get(p.player_name)?.map((hint, hi) => (
            <StackBadge key={`${hint.kind}-${hint.rostered_player_name}-${hi}`} hint={hint} />
          ))}
        </div>
      )
    },
    {
      key: 'team',
      header: 'Team',
      cellClassName: 'text-muted-foreground',
      accessor: (p) => p.team ?? '—'
    },
    {
      key: 'pts',
      header: sortHeader('Pts', 'projected_points', sortKey, sortDir, handleSort),
      align: 'right',
      cellClassName: WC_NUM_HERO,
      accessor: (p) => (p.projected_points != null ? p.projected_points.toFixed(1) : '—')
    },
    {
      key: 'adp',
      header: sortHeader('ADP', 'adp_rank', sortKey, sortDir, handleSort),
      align: 'right',
      cellClassName: 'font-mono tabular-nums',
      accessor: (p) => (p.adp_rank !== null ? p.adp_rank.toFixed(0) : '—')
    },
    {
      key: 'value',
      header: sortHeader('Value', 'adp_diff', sortKey, sortDir, handleSort),
      align: 'right',
      accessor: (p) => (
        <span className={`font-mono tabular-nums ${adpDiffColor(p.adp_diff)}`}>
          {formatAdpDiff(p.adp_diff)}
        </span>
      )
    },
    {
      key: 'vorp',
      header: sortHeader('VORP', 'vorp', sortKey, sortDir, handleSort),
      align: 'right',
      cellClassName: 'font-mono tabular-nums',
      accessor: (p) => (p.vorp != null ? p.vorp.toFixed(1) : '—')
    },
    {
      key: 'tier',
      header: 'Tier',
      accessor: (p) => (
        <div className='flex items-center gap-[var(--space-1)]'>
          {p.tier != null && (
            <span
              className='bg-muted text-foreground inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold'
              title={`Tier ${p.tier}`}
            >
              {`T${p.tier}`}
            </span>
          )}
          <span
            className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${VALUE_TIER_COLORS[p.value_tier] ?? VALUE_TIER_COLORS['fair_value']}`}
          >
            {p.value_tier === 'undervalued' ? 'Value' : p.value_tier === 'overvalued' ? 'Reach' : 'Fair'}
          </span>
        </div>
      )
    },
    ...(readOnly
      ? []
      : ([
          {
      key: 'actions',
      header: '',
      width: 'w-32',
      accessor: (p) => (
        <span className='flex items-center gap-[var(--space-1)]'>
          <PressScale>
            <Button
              variant='outline'
              size='sm'
              className={WC_CTA_BUTTON}
              onClick={() => onDraft?.(p.player_id)}
              disabled={isPicking}
            >
              Draft
            </Button>
          </PressScale>
          <PressScale>
            <Button
              variant='ghost'
              size='sm'
              className={WC_OUTLINE_BUTTON}
              title='Mark as drafted by another team'
              onClick={() => onDraft?.(p.player_id, false)}
              disabled={isPicking}
            >
              Taken
            </Button>
          </PressScale>
        </span>
      )
          }
        ] as BroadcastColumn<DisplayRow>[]))
  ];

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
          onChange={(e) => setSearch(e.target.value)}
          className={`ring-offset-background flex h-9 w-full rounded-md border px-[var(--space-3)] py-[var(--space-1)] pl-[var(--space-10)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] shadow-sm transition-colors file:border-0 file:bg-transparent file:text-[length:var(--fs-sm)] file:font-medium focus-visible:outline-none focus-visible:ring-1 disabled:cursor-not-allowed disabled:opacity-50 ${WC_INPUT}`}
        />
      </div>

      {/* Count */}
      <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
        Showing {displayed.length} of {filtered.length} {readOnly ? 'players' : 'available players'}
      </p>

      {/* Mobile (Phase 62-05 DSGN-04): BroadcastTable's own wrapper pans
       *  horizontally with a sticky player column, so the 9-column board
       *  stays usable at 375px without overflowing the page gutter. */}
      <BroadcastTable
        columns={columns}
        rows={displayed}
        getRowId={(p) => p.player_id}
        emptyMessage='No players match your filter.'
        rowClassName={(p) => (p.__tierBoundary ? 'border-t-2' : '')}
        minWidth='min-w-[760px]'
      />
    </div>
  );
}
