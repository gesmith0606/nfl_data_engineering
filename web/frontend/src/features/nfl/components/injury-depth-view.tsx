'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchDepthCharts, fetchInjuryReport } from '@/lib/nfl/api';
import type { InjuryRow } from '@/lib/nfl/types';
import { currentWeekQueryOptions } from '../api/queries';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { FadeIn } from '@/lib/motion-primitives';
import { toolSeason } from '@/lib/nfl/season';

const POS_ORDER = ['QB', 'RB', 'WR', 'TE'] as const;

function statusVariant(status: string): 'destructive' | 'secondary' {
  const out = ['OUT', 'IR', 'PUP', 'NFI', 'SUSPENDED', 'DOUBTFUL'];
  return out.includes(status.toUpperCase()) ? 'destructive' : 'secondary';
}

const injuryColumns: BroadcastColumn<InjuryRow>[] = [
  {
    key: 'player',
    header: 'Player',
    sticky: true,
    accessor: (p) => (
      <>
        <Badge variant='outline' className='mr-2'>
          {p.position}
        </Badge>
        {p.player_name}
        <span className='text-muted-foreground ml-1 text-xs'>{p.team}</span>
      </>
    )
  },
  {
    key: 'status',
    header: 'Status',
    accessor: (p) => (
      <Badge variant={statusVariant(p.injury_status)}>{p.injury_status}</Badge>
    )
  },
  {
    key: 'proj',
    header: 'Proj pts',
    align: 'right',
    accessor: (p) => p.projected_points.toFixed(1),
    cellClassName: 'font-mono'
  }
];

export function InjuryDepthView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = toolSeason(cw?.season);
  const week = cw?.week ?? 1;
  const [team, setTeam] = useState('PHI');

  const injuries = useQuery({
    queryKey: ['nfl', 'injuries', season, week],
    queryFn: () => fetchInjuryReport(season, week),
    retry: false
  });

  const depth = useQuery({
    queryKey: ['nfl', 'depth', season, team],
    queryFn: () => fetchDepthCharts(season, team),
    staleTime: 60 * 60 * 1000,
    retry: false
  });

  const allTeams = useMemo(() => {
    // 32 nflverse team codes — static beats an extra fetch.
    return 'ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS'.split(
      ' '
    );
  }, []);

  const depthByPos = useMemo(() => {
    const grouped: Record<string, { name: string; rank: number }[]> = {};
    for (const e of depth.data?.entries ?? []) {
      (grouped[e.position] ??= []).push({
        name: e.player_name,
        rank: e.depth_rank
      });
    }
    return grouped;
  }, [depth.data]);

  const noWeekly =
    injuries.error != null &&
    'status' in (injuries.error as object) &&
    (injuries.error as unknown as { status: number }).status === 404;

  return (
    <FadeIn>
      <Tabs defaultValue='injuries' className='space-y-4'>
        <TabsList>
          <TabsTrigger value='injuries'>Injury report</TabsTrigger>
          <TabsTrigger value='depth'>Depth charts</TabsTrigger>
        </TabsList>

        <TabsContent value='injuries' className='space-y-4'>
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>
                Fantasy-relevant injuries — week {week}
              </CardTitle>
            </CardHeader>
          </Card>
          <BroadcastTable
            columns={injuryColumns}
            rows={injuries.data?.players ?? []}
            getRowId={(p) => p.player_id}
            isLoading={injuries.isLoading}
            emptyMessage={
              noWeekly
                ? 'The weekly injury slate publishes with weekly projections once the season starts.'
                : 'No fantasy-relevant injuries this week.'
            }
          />
        </TabsContent>

        <TabsContent value='depth'>
          <Card>
            <CardHeader className='flex flex-row items-center justify-between'>
              <CardTitle className='text-base'>
                Depth chart{' '}
                {depth.data?.as_of && (
                  <span className='text-muted-foreground text-xs font-normal'>
                    as of {new Date(depth.data.as_of).toLocaleDateString()}
                  </span>
                )}
              </CardTitle>
              <Select value={team} onValueChange={setTeam}>
                <SelectTrigger className='w-24'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {allTeams.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </CardHeader>
            <CardContent>
              {depth.isLoading ? (
                <div className='flex justify-center py-8'>
                  <Icons.spinner className='text-muted-foreground h-6 w-6 animate-spin' />
                </div>
              ) : (
                <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-4'>
                  {POS_ORDER.map((pos) => (
                    <div key={pos}>
                      <h4 className='text-muted-foreground mb-2 text-xs font-semibold'>
                        {pos}
                      </h4>
                      <ol className='space-y-1 text-sm'>
                        {(depthByPos[pos] ?? [])
                          .sort((a, b) => a.rank - b.rank)
                          .map((p, i) => (
                            <li
                              key={`${p.name}-${i}`}
                              className='flex items-center gap-2'
                            >
                              <span className='text-muted-foreground w-4 text-right font-mono text-xs'>
                                {p.rank}
                              </span>
                              <span
                                className={i === 0 ? 'font-medium' : undefined}
                              >
                                {p.name}
                              </span>
                            </li>
                          ))}
                      </ol>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </FadeIn>
  );
}
