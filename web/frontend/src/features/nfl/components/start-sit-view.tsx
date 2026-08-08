'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchRosRankings, fetchStartSitCompare } from '@/lib/nfl/api';
import type { RosPlayer } from '@/lib/nfl/types';
import { currentWeekQueryOptions } from '../api/queries';
import { RosPlayerPicker } from './trade-analyzer-view';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import { FadeIn } from '@/lib/motion-primitives';
import { toolSeason } from '@/lib/nfl/season';

export function StartSitView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = toolSeason(cw?.season);
  const week = cw?.week ?? 1;

  const { data: ros } = useQuery({
    queryKey: ['nfl', 'ros', season],
    queryFn: () => fetchRosRankings(season),
    staleTime: 60 * 60 * 1000
  });

  const [picked, setPicked] = useState<RosPlayer[]>([]);
  const ids = useMemo(() => picked.map((p) => p.player_id), [picked]);
  const excluded = useMemo(() => new Set(ids), [ids]);

  const {
    data: cmp,
    isFetching,
    error
  } = useQuery({
    queryKey: ['nfl', 'start-sit', season, week, ids],
    queryFn: () => fetchStartSitCompare(ids, season, week),
    enabled: ids.length >= 2,
    retry: false
  });

  const noWeekly =
    error != null &&
    'status' in (error as object) &&
    (error as unknown as { status: number }).status === 404;

  return (
    <FadeIn className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>
            Who should I start? (week {week})
          </CardTitle>
        </CardHeader>
        <CardContent className='space-y-4'>
          <RosPlayerPicker
            pool={ros?.players ?? []}
            exclude={excluded}
            onPick={(p) =>
              setPicked((s) => (s.length < 4 ? [...s, p] : s))
            }
            placeholder='Add 2-4 players to compare...'
          />
          <div className='flex flex-wrap gap-2'>
            {picked.map((p) => (
              <Badge key={p.player_id} variant='secondary' className='gap-1'>
                {p.player_name}
                <button
                  type='button'
                  aria-label={`Remove ${p.player_name}`}
                  onClick={() =>
                    setPicked((s) =>
                      s.filter((x) => x.player_id !== p.player_id)
                    )
                  }
                >
                  <Icons.close className='h-3 w-3' />
                </button>
              </Badge>
            ))}
          </div>

          {isFetching && (
            <div className='flex justify-center py-6'>
              <Icons.spinner className='text-muted-foreground h-6 w-6 animate-spin' />
            </div>
          )}

          {noWeekly && (
            <p className='text-muted-foreground text-sm'>
              Weekly projections for week {week} aren&apos;t published yet —
              start/sit comparisons go live once the season starts. Rest-of-season
              value is shown in the picker meanwhile.
            </p>
          )}

          {cmp && !isFetching && (
            <div className='space-y-3'>
              <p className='text-sm font-medium text-emerald-500'>
                {cmp.reason}
              </p>
              <div className='overflow-x-auto'>
                <table className='w-full text-sm'>
                  <thead>
                    <tr className='text-muted-foreground border-b text-left text-xs'>
                      <th className='py-2 pr-4'>Player</th>
                      <th className='py-2 pr-4 text-right'>Proj</th>
                      <th className='py-2 pr-4 text-right'>Floor</th>
                      <th className='py-2 pr-4 text-right'>Ceiling</th>
                      <th className='py-2 pr-4 text-right'>Opp rank vs pos</th>
                      <th className='py-2 pr-4 text-right'>ROS pts</th>
                      <th className='py-2'>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cmp.players.map((p) => (
                      <tr
                        key={p.player_id}
                        className={`border-b last:border-0 ${p.recommended ? 'bg-emerald-500/10' : ''}`}
                      >
                        <td className='py-2 pr-4'>
                          <Badge variant='outline' className='mr-2'>
                            {p.position}
                          </Badge>
                          {p.player_name}
                          <span className='text-muted-foreground ml-1 text-xs'>
                            {p.team}
                          </span>
                          {p.recommended && (
                            <Badge className='ml-2' variant='default'>
                              Start
                            </Badge>
                          )}
                        </td>
                        <td className='py-2 pr-4 text-right font-mono'>
                          {p.projected_points.toFixed(1)}
                        </td>
                        <td className='py-2 pr-4 text-right font-mono'>
                          {p.projected_floor?.toFixed(1) ?? '—'}
                        </td>
                        <td className='py-2 pr-4 text-right font-mono'>
                          {p.projected_ceiling?.toFixed(1) ?? '—'}
                        </td>
                        <td className='py-2 pr-4 text-right font-mono'>
                          {p.opp_rank_vs_position ?? '—'}
                        </td>
                        <td className='py-2 pr-4 text-right font-mono'>
                          {p.ros_points?.toFixed(0) ?? '—'}
                        </td>
                        <td className='py-2'>
                          {p.injury_status ? (
                            <Badge variant='destructive'>
                              {p.injury_status}
                            </Badge>
                          ) : (
                            <span className='text-muted-foreground text-xs'>
                              Healthy
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className='text-muted-foreground text-xs'>
                Opp rank vs pos: 1 = toughest defense against that position, 32
                = softest. Recommendation favors projection, with floor as the
                tiebreaker.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </FadeIn>
  );
}
