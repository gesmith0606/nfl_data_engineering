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
import { SUCCESS_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors';
import { useWeekParams } from '@/hooks/use-week-params';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
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
  return value > 0 ? SUCCESS_TEXT : DANGER_TEXT;
}

export interface ProjectionComparisonTableProps {
  /**
   * Optional explicit season/week. Omit to track the same resolved
   * "current" slice as the projections table above it (`useWeekParams`) —
   * the page.tsx call site used to hardcode `season={2025} week={1}`
   * forever, which is what the 2026-08-01 P1 audit's `sleeper: 2026-06-11`
   * frozen-in-time chip was.
   */
  season?: number;
  week?: number;
  scoring?: 'ppr' | 'half_ppr' | 'standard';
  position?: string;
}

export function ProjectionComparisonTable({
  season: seasonProp,
  week: weekProp,
  scoring = 'half_ppr',
  position
}: ProjectionComparisonTableProps) {
  const resolved = useWeekParams();
  const season = seasonProp ?? resolved.season;
  const week = weekProp ?? resolved.week;
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

  if (error) {
    return (
      <div className={`text-sm ${DANGER_TEXT}`}>
        Failed to load comparison: {error}
      </div>
    );
  }

  const emptyMessage = `No comparison data available for ${data?.season ?? season} W${String(
    data?.week ?? week
  ).padStart(2, '0')}. External projection sources will populate after the next refresh cycle.`;

  const columns: BroadcastColumn<ProjectionComparisonRow>[] = [
    {
      key: 'player',
      header: 'Player',
      sticky: true,
      accessor: (row) => row.player_name,
      cellClassName: 'font-medium'
    },
    {
      key: 'position',
      header: 'Pos',
      accessor: (row) => row.position ?? EMPTY_DASH
    },
    {
      key: 'team',
      header: 'Team',
      accessor: (row) => row.team ?? EMPTY_DASH
    },
    {
      key: 'ours',
      header: 'Ours',
      align: 'right',
      accessor: (row) => formatPoints(row.ours),
      renderCell: (row) => <span className='wc-num-hero'>{formatPoints(row.ours)}</span>
    },
    {
      key: 'espn',
      header: 'ESPN',
      align: 'right',
      accessor: (row) => formatPoints(row.espn)
    },
    {
      key: 'sleeper',
      header: 'Sleeper',
      align: 'right',
      accessor: (row) => formatPoints(row.sleeper)
    },
    {
      key: 'yahoo',
      header: (
        <span title={data?.source_labels.yahoo ?? 'Yahoo'}>Yahoo</span>
      ),
      align: 'right',
      accessor: (row) => formatPoints(row.yahoo)
    },
    {
      key: 'delta',
      header: <span title='Avg(externals) − Ours'>Δ</span>,
      align: 'right',
      accessor: (row) => formatDelta(row.delta_vs_ours),
      renderCell: (row) => (
        <span className={deltaClass(row.delta_vs_ours)}>
          {formatDelta(row.delta_vs_ours)}
        </span>
      )
    }
  ];

  return (
    <div className='space-y-2'>
      {data?.fallback && (
        <div className='rounded-md border border-[var(--wc-yellow,#ffd84d)]/25 bg-[rgba(255,216,77,0.06)] px-3 py-2 text-xs text-muted-foreground'>
          No external comparison data for {season} Week {week} yet — showing
          the latest available snapshot ({data.fallback_season} Week{' '}
          {String(data.fallback_week).padStart(2, '0')}) instead.
        </div>
      )}
      {data && <FreshnessChips dataAsOf={data.data_as_of} />}
      <BroadcastTable
        columns={columns}
        rows={data?.rows ?? []}
        getRowId={(row) => row.player_id || row.player_name}
        isLoading={loading}
        emptyMessage={emptyMessage}
      />
    </div>
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
