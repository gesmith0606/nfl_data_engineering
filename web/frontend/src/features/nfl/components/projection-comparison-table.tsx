'use client';

/**
 * Phase 73 EXTP-04: Multi-source projection comparison table.
 *
 * Renders ours vs ESPN vs Sleeper vs Yahoo (FantasyPros consensus proxy)
 * side-by-side. Empty cells render as em-dash; the Yahoo column header
 * carries a tooltip with "via FantasyPros consensus" provenance per
 * CONTEXT D-03.
 *
 * Per CONTEXT D-06 (fail-open): if the API returns an empty `rows` array,
 * the table renders an EmptyState placeholder rather than crashing.
 */

import { useEffect, useState } from 'react';
import { fetchProjectionsComparison } from '@/lib/nfl/api';
import type { ProjectionComparison, ProjectionComparisonRow } from '@/lib/nfl/types';

const EMPTY_DASH = '—';

function formatPoints(value: number | null): string {
  return value == null ? EMPTY_DASH : value.toFixed(1);
}

function formatDelta(value: number | null): string {
  if (value == null) return EMPTY_DASH;
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}`;
}

function deltaClass(value: number | null): string {
  if (value == null) return 'text-muted-foreground';
  if (Math.abs(value) < 0.5) return 'text-muted-foreground';
  return value > 0
    ? 'text-green-600 dark:text-green-400'
    : 'text-red-600 dark:text-red-400';
}

export interface ProjectionComparisonTableProps {
  season: number;
  week: number;
  scoring?: 'ppr' | 'half_ppr' | 'standard';
  position?: string;
}

export function ProjectionComparisonTable({
  season,
  week,
  scoring = 'half_ppr',
  position
}: ProjectionComparisonTableProps) {
  const [data, setData] = useState<ProjectionComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchProjectionsComparison(season, week, scoring as never, position)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message ?? e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, scoring, position]);

  if (loading) {
    return (
      <div className='text-sm text-muted-foreground'>
        Loading multi-source comparison…
      </div>
    );
  }

  if (error) {
    return (
      <div className='text-sm text-red-600 dark:text-red-400'>
        Failed to load comparison: {error}
      </div>
    );
  }

  if (!data || data.rows.length === 0) {
    return (
      <div className='rounded-md border p-6 text-center text-sm text-muted-foreground'>
        No comparison data available for {data?.season ?? season} W
        {String(data?.week ?? week).padStart(2, '0')}. External projection sources
        will populate after the next refresh cycle.
      </div>
    );
  }

  return (
    <div className='space-y-2'>
      <FreshnessChips dataAsOf={data.data_as_of} />
      <div className='overflow-x-auto'>
        <table className='w-full text-sm'>
          <thead>
            <tr className='border-b text-left'>
              <th className='py-2 pr-4'>Player</th>
              <th className='py-2 pr-4'>Pos</th>
              <th className='py-2 pr-4'>Team</th>
              <th className='py-2 pr-2 text-right'>Ours</th>
              <th className='py-2 pr-2 text-right'>ESPN</th>
              <th className='py-2 pr-2 text-right'>Sleeper</th>
              <th
                className='py-2 pr-2 text-right'
                title={data.source_labels.yahoo ?? 'Yahoo'}
              >
                Yahoo
              </th>
              <th className='py-2 pr-2 text-right' title='Avg(externals) − Ours'>
                Δ
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <ComparisonRow key={row.player_id || row.player_name} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ComparisonRow({ row }: { row: ProjectionComparisonRow }) {
  return (
    <tr className='border-b hover:bg-muted/50'>
      <td className='py-2 pr-4 font-medium'>{row.player_name}</td>
      <td className='py-2 pr-4'>{row.position ?? EMPTY_DASH}</td>
      <td className='py-2 pr-4'>{row.team ?? EMPTY_DASH}</td>
      <td className='py-2 pr-2 text-right'>{formatPoints(row.ours)}</td>
      <td className='py-2 pr-2 text-right'>{formatPoints(row.espn)}</td>
      <td className='py-2 pr-2 text-right'>{formatPoints(row.sleeper)}</td>
      <td className='py-2 pr-2 text-right'>{formatPoints(row.yahoo)}</td>
      <td className={`py-2 pr-2 text-right ${deltaClass(row.delta_vs_ours)}`}>
        {formatDelta(row.delta_vs_ours)}
      </td>
    </tr>
  );
}

function FreshnessChips({ dataAsOf }: { dataAsOf: Record<string, string> }) {
  const entries = Object.entries(dataAsOf);
  if (entries.length === 0) return null;
  return (
    <div className='flex flex-wrap gap-2 text-xs text-muted-foreground'>
      {entries.map(([source, ts]) => (
        <span
          key={source}
          className='rounded-full border px-2 py-0.5'
          title={`${source}: ${ts}`}
        >
          {source}: {ts.split('T')[0]}
        </span>
      ))}
    </div>
  );
}
