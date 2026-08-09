'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSosGrid } from '@/lib/nfl/api';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { FadeIn } from '@/lib/motion-primitives';
import { cn } from '@/lib/utils';

const POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const;

type SosCells = Partial<
  Record<(typeof POSITIONS)[number], { rank: number; pts: number }>
>;
type SosRow = [team: string, cells: SosCells];

/** Rank 1 = toughest defense (bad matchup) → danger; 32 = softest → success.
 *  Two green bands preserve the old "strong vs mild" favorable distinction,
 *  now derived from the --success/--warn/--danger tokens instead of raw
 *  emerald/amber/red literals so it re-themes with the rest of the app. */
function cellClass(rank: number): string {
  if (rank >= 25)
    return 'text-[var(--success)] bg-[color-mix(in_oklch,var(--success)_22%,transparent)]';
  if (rank >= 17)
    return 'text-[var(--success)] bg-[color-mix(in_oklch,var(--success)_10%,transparent)]';
  if (rank >= 9)
    return 'text-[var(--warn)] bg-[color-mix(in_oklch,var(--warn)_12%,transparent)]';
  return 'text-[var(--danger)] bg-[color-mix(in_oklch,var(--danger)_16%,transparent)]';
}

const sosColumns: BroadcastColumn<SosRow>[] = [
  {
    key: 'team',
    header: 'Defense',
    sticky: true,
    accessor: ([team]) => team,
    cellClassName: 'font-medium'
  },
  ...POSITIONS.map<BroadcastColumn<SosRow>>((p) => ({
    key: p,
    header: `vs ${p}`,
    align: 'right',
    accessor: ([, cells]) => cells[p]?.rank ?? '—',
    renderCell: ([, cells]) => {
      const cell = cells[p];
      if (!cell) return <span className='text-muted-foreground'>—</span>;
      return (
        <span
          className={cn(
            'inline-block min-w-16 rounded px-2 py-0.5 font-mono',
            cellClass(cell.rank)
          )}
          title={`${cell.pts.toFixed(1)} avg fantasy pts allowed to ${p}`}
        >
          {cell.rank}
          <span className='text-muted-foreground ml-1 text-xs'>
            {cell.pts.toFixed(1)}
          </span>
        </span>
      );
    }
  }))
];

export function SosGridView() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['nfl', 'sos'],
    queryFn: () => fetchSosGrid(),
    staleTime: 60 * 60 * 1000,
    retry: false
  });

  const rows = useMemo<SosRow[]>(() => {
    if (!data) return [];
    const byTeam = new Map<string, SosCells>();
    for (const c of data.cells) {
      const pos = c.position as (typeof POSITIONS)[number];
      if (!POSITIONS.includes(pos)) continue;
      if (!byTeam.has(c.team)) byTeam.set(c.team, {});
      byTeam.get(c.team)![pos] = { rank: c.rank, pts: c.avg_pts_allowed };
    }
    return [...byTeam.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [data]);

  return (
    <FadeIn>
      <div className='space-y-4'>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>
              Defense vs position{' '}
              {data && (
                <span className='text-muted-foreground text-xs font-normal'>
                  {data.season} · through week {data.week} · rank 1 = toughest,
                  32 = softest
                </span>
              )}
            </CardTitle>
          </CardHeader>
        </Card>

        <BroadcastTable
          columns={sosColumns}
          rows={rows}
          getRowId={([team]) => team}
          isLoading={isLoading}
          emptyMessage={
            error != null
              ? "Defense-vs-position data isn't available yet for this season."
              : 'No defense-vs-position data available.'
          }
        />

        <p className='text-muted-foreground text-xs'>
          Green = favorable matchup for the offense (defense allows many
          fantasy points to that position). Cell shows league rank and
          average fantasy points allowed per game.
        </p>
      </div>
    </FadeIn>
  );
}
