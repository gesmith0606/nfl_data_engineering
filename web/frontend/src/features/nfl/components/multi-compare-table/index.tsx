'use client';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';
import { multiCompareQueryOptions } from '../../api/queries';
import type {
  Position,
  RankingSortBy,
  RankingSource,
  ScoringFormat
} from '../../api/types';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { getPositionBadgeClass } from '@/lib/nfl/position-colors';
import { SUCCESS_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors';

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K'];
const SCORING_OPTIONS: { value: ScoringFormat; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' }
];

const SOURCES: RankingSource[] = ['sleeper', 'espn', 'yahoo'];

const SOURCE_LABEL: Record<RankingSource, string> = {
  sleeper: 'Sleeper',
  espn: 'ESPN',
  yahoo: 'Yahoo'
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

interface MultiCompareTableProps {
  season?: number;
}

interface SortHeaderProps {
  label: string;
  sortKey: RankingSortBy;
  activeSort: RankingSortBy;
  onClick: (k: RankingSortBy) => void;
  align?: 'left' | 'right';
  title?: string;
}

function SortHeader({
  label,
  sortKey,
  activeSort,
  onClick,
  align = 'right',
  title
}: SortHeaderProps) {
  const isActive = activeSort === sortKey;
  return (
    <th
      className={`select-none cursor-pointer py-2 px-2 font-medium text-${align} hover:bg-muted ${
        isActive ? 'text-foreground' : 'text-muted-foreground'
      }`}
      onClick={() => onClick(sortKey)}
      title={title}
    >
      <span className='inline-flex items-center gap-1'>
        {label}
        {isActive && <span className='text-xs'>↓</span>}
      </span>
    </th>
  );
}

/**
 * Side-by-side rankings table: ours vs. Sleeper / ESPN / Yahoo.
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

  return (
    <div className='space-y-4'>
      <Card>
        <CardContent className='flex flex-wrap items-end gap-4 pt-6'>
          <div className='space-y-2'>
            <label className='text-muted-foreground text-xs font-medium'>
              Position
            </label>
            <Tabs value={position} onValueChange={(v) => setPosition(v as Position)}>
              <TabsList>
                {POSITIONS.map((p) => (
                  <TabsTrigger key={p} value={p}>
                    {p}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>

          <div className='space-y-2'>
            <label className='text-muted-foreground text-xs font-medium'>
              Scoring
            </label>
            <Tabs value={scoring} onValueChange={(v) => setScoring(v as ScoringFormat)}>
              <TabsList>
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
              ? 'consensus (mean of Sleeper/ESPN/Yahoo)'
              : sortBy === 'ours'
                ? 'our rank'
                : SOURCE_LABEL[sortBy as RankingSource]}
          </span>
          . Click any column header to re-sort.
        </p>
      )}

      {error && (
        <Card>
          <CardContent className='text-muted-foreground pt-6 text-sm'>
            Couldn’t load rankings. Try again in a moment.
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <Card>
          <CardContent className='space-y-2 pt-6'>
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className='h-10 w-full' />
            ))}
          </CardContent>
        </Card>
      )}

      {!isLoading && data && data.players.length === 0 && (
        <Card>
          <CardContent className='text-muted-foreground pt-6 text-sm'>
            No rows for the current filter combination.
          </CardContent>
        </Card>
      )}

      {!isLoading && data && data.players.length > 0 && (
        <Card>
          <CardContent className='p-0'>
            <div className='overflow-x-auto'>
              <table className='w-full text-sm'>
                <thead className='border-b bg-muted/40'>
                  <tr className='text-left'>
                    <th
                      className='py-2 pl-4 pr-2 font-medium text-muted-foreground'
                      title={`Row position in the current sort order (${
                        sortBy === 'consensus' ? 'consensus' : sortBy
                      }, ${rankBasisLabel}, ${
                        position === 'ALL' ? 'all positions' : position
                      })`}
                    >
                      #
                    </th>
                    <th className='py-2 px-2 font-medium'>Player</th>
                    <th className='py-2 px-2 font-medium'>Pos</th>
                    <SortHeader
                      label='Ours'
                      sortKey='ours'
                      activeSort={sortBy}
                      onClick={setSortBy}
                      title={`Our ${rankBasisLabel} rank — click to sort`}
                    />
                    <th className='py-2 px-2 text-right font-medium text-muted-foreground'>
                      Pts
                    </th>
                    <SortHeader
                      label='Sleeper'
                      sortKey='sleeper'
                      activeSort={sortBy}
                      onClick={setSortBy}
                      title={`Sleeper ${rankBasisLabel} rank — click to sort`}
                    />
                    <SortHeader
                      label='ESPN'
                      sortKey='espn'
                      activeSort={sortBy}
                      onClick={setSortBy}
                      title={`ESPN ${rankBasisLabel} rank — click to sort`}
                    />
                    <SortHeader
                      label='Yahoo*'
                      sortKey='yahoo'
                      activeSort={sortBy}
                      onClick={setSortBy}
                      title={`Yahoo ${rankBasisLabel} rank (via FantasyPros consensus) — click to sort`}
                    />
                    <SortHeader
                      label='Consensus'
                      sortKey='consensus'
                      activeSort={sortBy}
                      onClick={setSortBy}
                      title='Mean of Sleeper / ESPN / Yahoo — click to sort'
                    />
                    <th
                      className='py-2 px-2 text-right font-medium text-muted-foreground'
                      title='Sleeper rank − our rank (positive = we rank lower than Sleeper)'
                    >
                      Δ Slp
                    </th>
                    <th
                      className='py-2 px-2 text-right font-medium text-muted-foreground'
                      title='ESPN rank − our rank'
                    >
                      Δ ESPN
                    </th>
                    <th
                      className='py-2 pl-2 pr-4 text-right font-medium text-muted-foreground'
                      title='Yahoo rank − our rank'
                    >
                      Δ Yah
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.players.map((p) => {
                    const teamColor = p.team ? getTeamColor(p.team) : null;
                    const externalRanks = [p.sleeper_rank, p.espn_rank, p.yahoo_rank].filter(
                      (v): v is number => v !== null && v !== undefined
                    );
                    const consensus =
                      externalRanks.length > 0
                        ? externalRanks.reduce((a, b) => a + b, 0) / externalRanks.length
                        : null;
                    return (
                      <tr
                        key={`${p.player_name}-${p.team}`}
                        className='border-b last:border-0 hover:bg-muted/30'
                      >
                        <td className='py-2 pl-4 pr-2 font-mono text-xs text-muted-foreground'>
                          {p.rank}
                        </td>
                        <td className='py-2 px-2'>
                          <Link
                            href={`/dashboard/players?q=${encodeURIComponent(p.player_name)}`}
                            className='hover:underline'
                          >
                            <div className='flex items-center gap-2'>
                              <span className='font-medium'>{p.player_name}</span>
                              {p.team && (
                                <span
                                  className='text-xs text-muted-foreground'
                                  style={teamColor ? { color: teamColor } : undefined}
                                >
                                  {p.team}
                                </span>
                              )}
                            </div>
                          </Link>
                        </td>
                        <td className='py-2 px-2'>
                          {p.position && (
                            <Badge
                              variant='outline'
                              className={getPositionBadgeClass(p.position)}
                            >
                              {p.position}
                            </Badge>
                          )}
                        </td>
                        <td className='py-2 px-2 text-right font-mono'>
                          {formatRank(p.our_rank)}
                        </td>
                        <td className='py-2 px-2 text-right font-mono text-muted-foreground'>
                          {p.our_projected_points !== null
                            ? p.our_projected_points.toFixed(1)
                            : '—'}
                        </td>
                        <td className='py-2 px-2 text-right font-mono'>
                          {formatRank(p.sleeper_rank)}
                        </td>
                        <td className='py-2 px-2 text-right font-mono'>
                          {formatRank(p.espn_rank)}
                        </td>
                        <td className='py-2 px-2 text-right font-mono'>
                          {formatRank(p.yahoo_rank)}
                        </td>
                        <td className='py-2 px-2 text-right font-mono text-muted-foreground'>
                          {formatRank(consensus)}
                        </td>
                        <td
                          className={`py-2 px-2 text-right font-mono ${diffClass(p.rank_diff_vs_sleeper)}`}
                        >
                          {formatDiff(p.rank_diff_vs_sleeper)}
                        </td>
                        <td
                          className={`py-2 px-2 text-right font-mono ${diffClass(p.rank_diff_vs_espn)}`}
                        >
                          {formatDiff(p.rank_diff_vs_espn)}
                        </td>
                        <td
                          className={`py-2 pl-2 pr-4 text-right font-mono ${diffClass(p.rank_diff_vs_yahoo)}`}
                        >
                          {formatDiff(p.rank_diff_vs_yahoo)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <p className='text-xs text-muted-foreground'>
        Δ columns show <span className='font-mono'>source rank − our rank</span>.{' '}
        Positive = source ranks the player lower than we do (we’re higher on
        them). Yahoo* is served via FantasyPros consensus.
      </p>
    </div>
  );
}
