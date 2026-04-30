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

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K'];
const SCORING_OPTIONS: { value: ScoringFormat; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' }
];

const SORT_OPTIONS: { value: RankingSortBy; label: string }[] = [
  { value: 'consensus', label: 'Consensus' },
  { value: 'ours', label: 'Ours' },
  { value: 'sleeper', label: 'Sleeper' },
  { value: 'espn', label: 'ESPN' },
  { value: 'yahoo', label: 'Yahoo' }
];

const SOURCES: RankingSource[] = ['sleeper', 'espn', 'yahoo'];

const POS_COLORS: Record<string, string> = {
  QB: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  RB: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
  WR: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400',
  TE: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  K: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400'
};

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
  if (diff > 5) return 'text-green-600 dark:text-green-400 font-medium'; // we rank higher
  if (diff < -5) return 'text-red-600 dark:text-red-400 font-medium'; // we rank lower
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

/**
 * Side-by-side rankings table: ours vs. Sleeper / ESPN / Yahoo.
 *
 * Each row is one player; rank columns show how each source ranks them.
 * `rank_diff_vs_<source>` columns highlight where we disagree most. Yahoo
 * data is served via FantasyPros consensus (provenance noted under the
 * column header).
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

  return (
    <div className='space-y-4'>
      {/* Controls */}
      <Card>
        <CardContent className='flex flex-wrap items-end gap-4 pt-6'>
          <div className='space-y-2'>
            <label className='text-muted-foreground text-xs font-medium'>
              Sort by
            </label>
            <Tabs value={sortBy} onValueChange={(v) => setSortBy(v as RankingSortBy)}>
              <TabsList>
                {SORT_OPTIONS.map((opt) => (
                  <TabsTrigger key={opt.value} value={opt.value}>
                    {opt.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>

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
                    title={stale ? `${SOURCE_LABEL[src]}: stale or unavailable` : `${SOURCE_LABEL[src]}: live`}
                  >
                    {SOURCE_LABEL[src]} {stale ? '·stale' : '·live'}
                  </Badge>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Empty / error / loading states */}
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

      {/* Table */}
      {!isLoading && data && data.players.length > 0 && (
        <Card>
          <CardContent className='p-0'>
            <div className='overflow-x-auto'>
              <table className='w-full text-sm'>
                <thead className='border-b bg-muted/40'>
                  <tr className='text-left'>
                    <th className='py-2 pl-4 pr-2 font-medium'>#</th>
                    <th className='py-2 px-2 font-medium'>Player</th>
                    <th className='py-2 px-2 font-medium'>Pos</th>
                    <th className='py-2 px-2 text-right font-medium'>Ours</th>
                    <th className='py-2 px-2 text-right font-medium'>Pts</th>
                    <th className='py-2 px-2 text-right font-medium'>Sleeper</th>
                    <th className='py-2 px-2 text-right font-medium'>ESPN</th>
                    <th
                      className='py-2 px-2 text-right font-medium'
                      title='Served via FantasyPros consensus'
                    >
                      Yahoo*
                    </th>
                    <th className='py-2 px-2 text-right font-medium' title='Sleeper rank − our rank'>
                      Δ Slp
                    </th>
                    <th className='py-2 px-2 text-right font-medium' title='ESPN rank − our rank'>
                      Δ ESPN
                    </th>
                    <th className='py-2 pl-2 pr-4 text-right font-medium' title='Yahoo rank − our rank'>
                      Δ Yah
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.players.map((p) => {
                    const teamColor = p.team ? getTeamColor(p.team) : null;
                    return (
                      <tr key={`${p.player_name}-${p.team}`} className='border-b last:border-0 hover:bg-muted/30'>
                        <td className='py-2 pl-4 pr-2 font-mono text-xs'>{p.rank}</td>
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
                            <Badge variant='outline' className={POS_COLORS[p.position] ?? ''}>
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
                        <td className={`py-2 px-2 text-right font-mono ${diffClass(p.rank_diff_vs_sleeper)}`}>
                          {formatDiff(p.rank_diff_vs_sleeper)}
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${diffClass(p.rank_diff_vs_espn)}`}>
                          {formatDiff(p.rank_diff_vs_espn)}
                        </td>
                        <td className={`py-2 pl-2 pr-4 text-right font-mono ${diffClass(p.rank_diff_vs_yahoo)}`}>
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
        Δ columns show <span className='font-mono'>source rank − our rank</span>.
        Positive = source ranks the player lower than we do (we’re higher on
        them). Yahoo* is served via FantasyPros consensus.
      </p>
    </div>
  );
}
