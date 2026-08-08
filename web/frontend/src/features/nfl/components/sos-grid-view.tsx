'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSosGrid } from '@/lib/nfl/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Icons } from '@/components/icons';
import { FadeIn } from '@/lib/motion-primitives';

const POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const;

/** Rank 1 = toughest defense (bad matchup) → red; 32 = softest → green. */
function cellClass(rank: number): string {
  if (rank >= 25) return 'bg-emerald-500/25';
  if (rank >= 17) return 'bg-emerald-500/10';
  if (rank >= 9) return 'bg-amber-500/10';
  return 'bg-red-500/20';
}

export function SosGridView() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['nfl', 'sos'],
    queryFn: () => fetchSosGrid(),
    staleTime: 60 * 60 * 1000,
    retry: false
  });

  const rows = useMemo(() => {
    if (!data) return [];
    const byTeam = new Map<
      string,
      Partial<Record<(typeof POSITIONS)[number], { rank: number; pts: number }>>
    >();
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
        <CardContent>
          {isLoading && (
            <div className='flex justify-center py-8'>
              <Icons.spinner className='text-muted-foreground h-6 w-6 animate-spin' />
            </div>
          )}
          {error != null && (
            <p className='text-muted-foreground text-sm'>
              Defense-vs-position data isn&apos;t available yet for this
              season.
            </p>
          )}
          {rows.length > 0 && (
            <div className='overflow-x-auto'>
              <table className='w-full text-sm'>
                <thead>
                  <tr className='text-muted-foreground border-b text-left text-xs'>
                    <th className='py-2 pr-4'>Defense</th>
                    {POSITIONS.map((p) => (
                      <th key={p} className='py-2 pr-4 text-right'>
                        vs {p}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(([team, cells]) => (
                    <tr key={team} className='border-b last:border-0'>
                      <td className='py-1.5 pr-4 font-medium'>{team}</td>
                      {POSITIONS.map((p) => {
                        const cell = cells[p];
                        return (
                          <td key={p} className='py-1 pr-4 text-right'>
                            {cell ? (
                              <span
                                className={`inline-block min-w-16 rounded px-2 py-0.5 font-mono ${cellClass(cell.rank)}`}
                                title={`${cell.pts.toFixed(1)} avg fantasy pts allowed to ${p}`}
                              >
                                {cell.rank}
                                <span className='text-muted-foreground ml-1 text-xs'>
                                  {cell.pts.toFixed(1)}
                                </span>
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className='text-muted-foreground mt-3 text-xs'>
            Green = favorable matchup for the offense (defense allows many
            fantasy points to that position). Cell shows league rank and
            average fantasy points allowed per game.
          </p>
        </CardContent>
      </Card>
    </FadeIn>
  );
}
