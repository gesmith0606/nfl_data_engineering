'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchRosRankings, fetchAuctionValues } from '@/lib/nfl/api';
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
import { FadeIn } from '@/lib/motion-primitives';
import { toolSeason } from '@/lib/nfl/season';

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K'];

function Spinner() {
  return (
    <div className='flex justify-center py-8'>
      <Icons.spinner className='text-muted-foreground h-6 w-6 animate-spin' />
    </div>
  );
}

export function RosValueView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = toolSeason(cw?.season);
  const [position, setPosition] = useState('ALL');
  const [teams, setTeams] = useState(12);
  const [budget, setBudget] = useState(200);

  const ros = useQuery({
    queryKey: ['nfl', 'ros', season, position],
    queryFn: () => fetchRosRankings(season, { position, limit: 200 }),
    staleTime: 60 * 60 * 1000
  });

  const auction = useQuery({
    queryKey: ['nfl', 'auction', season, teams, budget],
    queryFn: () => fetchAuctionValues(season, { teams, budget, limit: 200 }),
    staleTime: 60 * 60 * 1000
  });

  return (
    <FadeIn>
      <Tabs defaultValue='ros' className='space-y-4'>
        <TabsList>
          <TabsTrigger value='ros'>Rest-of-season value</TabsTrigger>
          <TabsTrigger value='auction'>Auction values</TabsTrigger>
        </TabsList>

        <TabsContent value='ros'>
          <Card>
            <CardHeader className='flex flex-row items-center justify-between'>
              <CardTitle className='text-base'>
                ROS rankings{' '}
                {ros.data && (
                  <span className='text-muted-foreground text-xs font-normal'>
                    from week {ros.data.from_week} ·{' '}
                    {ros.data.weeks_remaining} weeks left
                  </span>
                )}
              </CardTitle>
              <Select value={position} onValueChange={setPosition}>
                <SelectTrigger className='w-24'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {POSITIONS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </CardHeader>
            <CardContent>
              {ros.isLoading ? (
                <Spinner />
              ) : (
                <div className='overflow-x-auto'>
                  <table className='w-full text-sm'>
                    <thead>
                      <tr className='text-muted-foreground border-b text-left text-xs'>
                        <th className='py-2 pr-4'>#</th>
                        <th className='py-2 pr-4'>Player</th>
                        <th className='py-2 pr-4 text-right'>ROS pts</th>
                        <th className='py-2 pr-4 text-right'>Season pts</th>
                        <th className='py-2 text-right'>VORP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ros.data?.players.map((p, i) => (
                        <tr key={p.player_id} className='border-b last:border-0'>
                          <td className='text-muted-foreground py-1.5 pr-4'>
                            {i + 1}
                          </td>
                          <td className='py-1.5 pr-4'>
                            <Badge variant='outline' className='mr-2'>
                              {p.position}
                            </Badge>
                            {p.player_name}
                            <span className='text-muted-foreground ml-1 text-xs'>
                              {p.team}
                            </span>
                          </td>
                          <td className='py-1.5 pr-4 text-right font-mono'>
                            {p.ros_points.toFixed(1)}
                          </td>
                          <td className='py-1.5 pr-4 text-right font-mono'>
                            {p.projected_season_points.toFixed(1)}
                          </td>
                          <td className='py-1.5 text-right font-mono'>
                            {p.vorp?.toFixed(1) ?? '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value='auction'>
          <Card>
            <CardHeader className='flex flex-row items-center justify-between gap-4'>
              <CardTitle className='text-base'>
                Auction dollar values
              </CardTitle>
              <div className='flex items-center gap-2 text-sm'>
                <Select
                  value={String(teams)}
                  onValueChange={(v) => setTeams(Number(v))}
                >
                  <SelectTrigger className='w-28'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[8, 10, 12, 14, 16].map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        {n} teams
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select
                  value={String(budget)}
                  onValueChange={(v) => setBudget(Number(v))}
                >
                  <SelectTrigger className='w-28'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[100, 200, 300].map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        ${n} budget
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {auction.isLoading ? (
                <Spinner />
              ) : (
                <div className='overflow-x-auto'>
                  <table className='w-full text-sm'>
                    <thead>
                      <tr className='text-muted-foreground border-b text-left text-xs'>
                        <th className='py-2 pr-4'>#</th>
                        <th className='py-2 pr-4'>Player</th>
                        <th className='py-2 pr-4 text-right'>Value</th>
                        <th className='py-2 pr-4 text-right'>Season pts</th>
                        <th className='py-2 text-right'>VORP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auction.data?.players.map((p, i) => (
                        <tr key={p.player_id} className='border-b last:border-0'>
                          <td className='text-muted-foreground py-1.5 pr-4'>
                            {i + 1}
                          </td>
                          <td className='py-1.5 pr-4'>
                            <Badge variant='outline' className='mr-2'>
                              {p.position}
                            </Badge>
                            {p.player_name}
                            <span className='text-muted-foreground ml-1 text-xs'>
                              {p.team}
                            </span>
                          </td>
                          <td className='py-1.5 pr-4 text-right font-mono font-medium'>
                            ${p.auction_value}
                          </td>
                          <td className='py-1.5 pr-4 text-right font-mono'>
                            {p.projected_season_points.toFixed(1)}
                          </td>
                          <td className='py-1.5 text-right font-mono'>
                            {p.vorp?.toFixed(1) ?? '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </FadeIn>
  );
}
