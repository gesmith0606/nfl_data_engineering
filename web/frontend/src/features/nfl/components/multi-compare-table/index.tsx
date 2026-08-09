'use client';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { multiCompareQueryOptions } from '../../api/queries';
import type {
  MultiCompareRow,
  Position,
  RankingSortBy,
  RankingSource,
  ScoringFormat
} from '../../api/types';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { getPositionBadgeClass } from '@/lib/nfl/position-colors';
import { SUCCESS_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors';
import { cn } from '@/lib/utils';

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K'];
const SCORING_OPTIONS: { value: ScoringFormat; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' }
];

const SOURCES: RankingSource[] = [
  'sleeper',
  'espn',
  'yahoo',
  'draftsharks',
  'ftn'
];

const SOURCE_LABEL: Record<RankingSource, string> = {
  sleeper: 'Sleeper',
  espn: 'ESPN',
  yahoo: 'Yahoo',
  draftsharks: 'Draft Sharks',
  ftn: 'FTN'
};

function formatRank(v: number | null): string {
  if (v === null || v === undefined) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function diffClass(diff: number | null): string {
  if (diff === null) return 'text-muted-foreground';
  if (diff > 5) return `${SUCCESS_TEXT} font-medium`; // we rank higher
  if (diff < -5) return `${DANGER_TEXT} font-medium`; // we rank lower
  return 'text-muted-foreground';
}

function formatDiff(diff: number | null): string {
  if (diff === null) return '—';
  const v = Math.round(diff);
  if (v === 0) return '±0';
  return v > 0 ? `+${v}` : String(v);
}

function consensusOf(p: MultiCompareRow): number | null {
  const externalRanks = [
    p.sleeper_rank,
    p.espn_rank,
    p.yahoo_rank,
    p.draftsharks_rank,
    p.ftn_rank
  ].filter((v): v is number => v !== null && v !== undefined);
  return externalRanks.length > 0
    ? externalRanks.reduce((a, b) => a + b, 0) / externalRanks.length
    : null;
}

/** Clickable column header — click to re-sort by this source. Same affordance
 *  as the old `SortHeader` <th>, now rendered as a `header` node so it fits
 *  the shared `BroadcastColumn` API (which has no per-column onClick). */
function sortableHeader(
  label: string,
  sortKey: RankingSortBy,
  activeSort: RankingSortBy,
  onSort: (k: RankingSortBy) => void,
  title?: string
) {
  const isActive = activeSort === sortKey;
  return (
    <button
      type='button'
      onClick={() => onSort(sortKey)}
      title={title}
      className={cn(
        'inline-flex select-none items-center gap-1 hover:text-foreground',
        isActive ? 'text-foreground' : 'text-muted-foreground'
      )}
    >
      {label}
      {isActive && <span className='text-xs'>↓</span>}
    </button>
  );
}

function buildColumns(
  sortBy: RankingSortBy,
  onSort: (k: RankingSortBy) => void,
  rankBasisLabel: string,
  position: Position
): BroadcastColumn<MultiCompareRow>[] {
  return [
    {
      key: 'rank',
      header: (
        <span
          title={`Row position in the current sort order (${
            sortBy === 'consensus' ? 'consensus' : sortBy
          }, ${rankBasisLabel}, ${position === 'ALL' ? 'all positions' : position})`}
        >
          #
        </span>
      ),
      accessor: (p) => p.rank,
      cellClassName: 'font-mono text-xs text-muted-foreground',
      width: 'w-10'
    },
    {
      key: 'player',
      header: 'Player',
      sticky: true,
      accessor: (p) => {
        const teamColor = p.team ? getTeamColor(p.team) : null;
        return (
          <Link
            href={`/dashboard/players?q=${encodeURIComponent(p.player_name)}`}
            className='hover:underline'
          >
            <span className='flex items-center gap-2'>
              <span className='font-medium'>{p.player_name}</span>
              {p.team && (
                <span
                  className='text-xs text-muted-foreground'
                  style={teamColor ? { color: teamColor } : undefined}
                >
                  {p.team}
                </span>
              )}
            </span>
          </Link>
        );
      }
    },
    {
      key: 'pos',
      header: 'Pos',
      accessor: (p) =>
        p.position ? (
          <Badge variant='outline' className={getPositionBadgeClass(p.position)}>
            {p.position}
          </Badge>
        ) : null
    },
    {
      key: 'ours',
      header: sortableHeader(
        'Ours',
        'ours',
        sortBy,
        onSort,
        `Our ${rankBasisLabel} rank — click to sort`
      ),
      align: 'right',
      accessor: (p) => formatRank(p.our_rank),
      renderCell: (p) => <span className='wc-num-hero'>{formatRank(p.our_rank)}</span>
    },
    {
      key: 'pts',
      header: 'Pts',
      align: 'right',
      accessor: (p) =>
        p.our_projected_points !== null ? p.our_projected_points.toFixed(1) : '—',
      cellClassName: 'font-mono text-muted-foreground'
    },
    {
      key: 'sleeper',
      header: sortableHeader(
        'Sleeper',
        'sleeper',
        sortBy,
        onSort,
        `Sleeper ${rankBasisLabel} rank — click to sort`
      ),
      align: 'right',
      accessor: (p) => formatRank(p.sleeper_rank),
      cellClassName: 'font-mono'
    },
    {
      key: 'espn',
      header: sortableHeader(
        'ESPN',
        'espn',
        sortBy,
        onSort,
        `ESPN ${rankBasisLabel} rank — click to sort`
      ),
      align: 'right',
      accessor: (p) => formatRank(p.espn_rank),
      cellClassName: 'font-mono'
    },
    {
      key: 'yahoo',
      header: sortableHeader(
        'Yahoo*',
        'yahoo',
        sortBy,
        onSort,
        `Yahoo ${rankBasisLabel} rank (via FantasyPros consensus) — click to sort`
      ),
      align: 'right',
      accessor: (p) => formatRank(p.yahoo_rank),
      cellClassName: 'font-mono'
    },
    {
      key: 'draftsharks',
      header: sortableHeader(
        'Sharks',
        'draftsharks',
        sortBy,
        onSort,
        `Draft Sharks ${rankBasisLabel} rank (site took #1+#2 of 225 in the 2024 FantasyPros draft-accuracy contest) — click to sort`
      ),
      align: 'right',
      accessor: (p) => formatRank(p.draftsharks_rank),
      cellClassName: 'font-mono'
    },
    {
      key: 'ftn',
      header: sortableHeader(
        'FTN',
        'ftn',
        sortBy,
        onSort,
        `Jeff Ratcliffe (FTN) ${rankBasisLabel} rank (#1 multi-year FantasyPros draft accuracy; empty until his ranks drop, typically Jul-Aug) — click to sort`
      ),
      align: 'right',
      accessor: (p) => formatRank(p.ftn_rank),
      cellClassName: 'font-mono'
    },
    {
      key: 'consensus',
      header: sortableHeader(
        'Consensus',
        'consensus',
        sortBy,
        onSort,
        'Mean of Sleeper / ESPN / Yahoo / Draft Sharks / FTN — click to sort'
      ),
      align: 'right',
      accessor: (p) => formatRank(consensusOf(p)),
      cellClassName: 'font-mono text-muted-foreground'
    },
    {
      key: 'diff_sleeper',
      header: (
        <span title='Sleeper rank − our rank (positive = we rank lower than Sleeper)'>
          Δ Slp
        </span>
      ),
      align: 'right',
      accessor: (p) => formatDiff(p.rank_diff_vs_sleeper),
      renderCell: (p) => (
        <span className={cn('font-mono', diffClass(p.rank_diff_vs_sleeper))}>
          {formatDiff(p.rank_diff_vs_sleeper)}
        </span>
      )
    },
    {
      key: 'diff_espn',
      header: <span title='ESPN rank − our rank'>Δ ESPN</span>,
      align: 'right',
      accessor: (p) => formatDiff(p.rank_diff_vs_espn),
      renderCell: (p) => (
        <span className={cn('font-mono', diffClass(p.rank_diff_vs_espn))}>
          {formatDiff(p.rank_diff_vs_espn)}
        </span>
      )
    },
    {
      key: 'diff_yahoo',
      header: <span title='Yahoo rank − our rank'>Δ Yah</span>,
      align: 'right',
      accessor: (p) => formatDiff(p.rank_diff_vs_yahoo),
      renderCell: (p) => (
        <span className={cn('font-mono', diffClass(p.rank_diff_vs_yahoo))}>
          {formatDiff(p.rank_diff_vs_yahoo)}
        </span>
      )
    },
    {
      key: 'diff_draftsharks',
      header: <span title='Draft Sharks rank − our rank'>Δ DS</span>,
      align: 'right',
      accessor: (p) => formatDiff(p.rank_diff_vs_draftsharks),
      renderCell: (p) => (
        <span className={cn('font-mono', diffClass(p.rank_diff_vs_draftsharks))}>
          {formatDiff(p.rank_diff_vs_draftsharks)}
        </span>
      )
    },
    {
      key: 'diff_ftn',
      header: <span title='FTN (Ratcliffe) rank − our rank'>Δ FTN</span>,
      align: 'right',
      accessor: (p) => formatDiff(p.rank_diff_vs_ftn),
      renderCell: (p) => (
        <span className={cn('font-mono', diffClass(p.rank_diff_vs_ftn))}>
          {formatDiff(p.rank_diff_vs_ftn)}
        </span>
      )
    }
  ];
}

interface MultiCompareTableProps {
  season?: number;
}

/**
 * Side-by-side rankings table: ours vs. Sleeper / ESPN / Yahoo — the premium
 * sibling of the flagship broadcast rankings table (rankings-table), sharing
 * its BroadcastTable chrome (sticky Player column, mint hero numeral on our
 * headline rank, yellow condensed headers).
 *
 * **Rank semantics** depend on the position filter:
 *   - ALL filter → ranks are **overall** (Bijan #1, Lamar #16, …)
 *   - Single position filter (QB/RB/…) → ranks are **positional** (QB1, QB2, …)
 *
 * The backend exposes both kinds per row and switches the headline `rank`
 * based on the active filter. The "#" column on the left is the row's
 * position in the currently active sort order — click any column header
 * to sort by that source. Yahoo is served via FantasyPros consensus.
 */
export function MultiCompareTable({ season = 2026 }: MultiCompareTableProps) {
  const [position, setPosition] = useState<Position>('ALL');
  const [scoring, setScoring] = useState<ScoringFormat>('half_ppr');
  const [sortBy, setSortBy] = useState<RankingSortBy>('consensus');

  const { data, isLoading, error } = useQuery(
    multiCompareQueryOptions({
      season,
      scoring,
      position: position === 'ALL' ? null : position,
      sort_by: sortBy,
      sources: SOURCES,
      limit: 100
    })
  );

  const rankBasis = data?.rank_basis ?? 'overall';
  const rankBasisLabel = rankBasis === 'overall' ? 'overall' : 'positional';

  const columns = useMemo(
    () => buildColumns(sortBy, setSortBy, rankBasisLabel, position),
    [sortBy, rankBasisLabel, position]
  );

  return (
    <div className='space-y-4'>
      <Card>
        <CardContent className='flex flex-wrap items-end gap-4 pt-6'>
          <div className='space-y-2'>
            <label htmlFor='position-tabs' className='text-muted-foreground text-xs font-medium'>
              Position
            </label>
            <Tabs value={position} onValueChange={(v) => setPosition(v as Position)}>
              <TabsList id='position-tabs'>
                {POSITIONS.map((p) => (
                  <TabsTrigger key={p} value={p}>
                    {p}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>

          <div className='space-y-2'>
            <label htmlFor='scoring-tabs' className='text-muted-foreground text-xs font-medium'>
              Scoring
            </label>
            <Tabs value={scoring} onValueChange={(v) => setScoring(v as ScoringFormat)}>
              <TabsList id='scoring-tabs'>
                {SCORING_OPTIONS.map((opt) => (
                  <TabsTrigger key={opt.value} value={opt.value}>
                    {opt.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>

          {data && (
            <div className='ml-auto flex items-center gap-2'>
              {SOURCES.map((src) => {
                const stale = data.stale?.[src];
                return (
                  <Badge
                    key={src}
                    variant={stale ? 'destructive' : 'secondary'}
                    className='text-xs'
                    title={
                      stale
                        ? `${SOURCE_LABEL[src]}: stale or unavailable`
                        : `${SOURCE_LABEL[src]}: live`
                    }
                  >
                    {SOURCE_LABEL[src]} {stale ? '·stale' : '·live'}
                  </Badge>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Caption explaining what the user is looking at */}
      {data && data.players.length > 0 && (
        <p className='text-xs text-muted-foreground px-1'>
          Showing <span className='font-medium'>{rankBasisLabel}</span> ranks
          {position === 'ALL'
            ? ' (1..N across all positions). '
            : ` (${position}1, ${position}2, … within position). `}
          Sorted by{' '}
          <span className='font-medium'>
            {sortBy === 'consensus'
              ? 'consensus (mean of Sleeper/ESPN/Yahoo/Draft Sharks/FTN)'
              : sortBy === 'ours'
                ? 'our rank'
                : SOURCE_LABEL[sortBy as RankingSource]}
          </span>
          . Click any column header to re-sort.
        </p>
      )}

      {error ? (
        <Card>
          <CardContent className='text-muted-foreground pt-6 text-sm'>
            Couldn’t load rankings. Try again in a moment.
          </CardContent>
        </Card>
      ) : (
        <BroadcastTable
          columns={columns}
          rows={data?.players ?? []}
          getRowId={(p) => `${p.player_name}-${p.team}`}
          isLoading={isLoading}
          emptyMessage='No rows for the current filter combination.'
          minWidth='min-w-[1320px]'
        />
      )}

      <p className='text-xs text-muted-foreground'>
        Δ columns show <span className='font-mono'>source rank − our rank</span>.{' '}
        Positive = source ranks the player lower than we do (we’re higher on
        them). Yahoo* is served via FantasyPros consensus. Draft Sharks and FTN
        (Jeff Ratcliffe) are the industry’s top-measured preseason rankers by
        FantasyPros draft-accuracy results; FTN stays empty until Ratcliffe
        submits ranks for the season (typically Jul–Aug).
      </p>
    </div>
  );
}
