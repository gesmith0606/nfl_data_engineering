'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchRosRankings, fetchAuctionValues } from '@/lib/nfl/api';
import { currentWeekQueryOptions } from '../api/queries';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
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
import type { RosPlayer, AuctionPlayer } from '@/lib/nfl/types';

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K'];

const rosColumns: BroadcastColumn<RosPlayer>[] = [
  {
    key: 'rank',
    header: '#',
    accessor: (_p, i) => i + 1,
    cellClassName: 'text-muted-foreground',
    width: 'w-10'
  },
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
    key: 'ros_points',
    header: 'ROS pts',
    align: 'right',
    accessor: (p) => p.ros_points.toFixed(1),
    renderCell: (p) => <span className='wc-num-hero'>{p.ros_points.toFixed(1)}</span>
  },
  {
    key: 'season_points',
    header: 'Season pts',
    align: 'right',
    accessor: (p) => p.projected_season_points.toFixed(1),
    cellClassName: 'font-mono'
  },
  {
    key: 'vorp',
    header: 'VORP',
    align: 'right',
    accessor: (p) => p.vorp?.toFixed(1) ?? '—',
    cellClassName: 'font-mono'
  }
];

const auctionColumns: BroadcastColumn<AuctionPlayer>[] = [
  {
    key: 'rank',
    header: '#',
    accessor: (_p, i) => i + 1,
    cellClassName: 'text-muted-foreground',
    width: 'w-10'
  },
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
    key: 'value',
    header: 'Value',
    align: 'right',
    accessor: (p) => `$${p.auction_value}`,
    renderCell: (p) => <span className='wc-num-hero'>${p.auction_value}</span>
  },
  {
    key: 'season_points',
    header: 'Season pts',
    align: 'right',
    accessor: (p) => p.projected_season_points.toFixed(1),
    cellClassName: 'font-mono'
  },
  {
    key: 'vorp',
    header: 'VORP',
    align: 'right',
    accessor: (p) => p.vorp?.toFixed(1) ?? '—',
    cellClassName: 'font-mono'
  }
];

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

        <TabsContent value='ros' className='space-y-4'>
          <Card>
            <CardHeader className='flex flex-row items-center justify-between'>
              <CardTitle className='text-base'>
                ROS rankings{' '}
                {ros.data && (
                  <span className='text-muted-foreground text-xs font-normal'>
                    from week {ros.data.from_week} · {ros.data.weeks_remaining}{' '}
                    weeks left
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
          </Card>
          <BroadcastTable
            columns={rosColumns}
            rows={ros.data?.players ?? []}
            getRowId={(p) => p.player_id}
            isLoading={ros.isLoading}
            emptyMessage='No rest-of-season rankings available.'
            filteredLabel={position !== 'ALL' ? `${position} only` : undefined}
          />
        </TabsContent>

        <TabsContent value='auction' className='space-y-4'>
          <Card>
            <CardHeader className='flex flex-row items-center justify-between gap-4'>
              <CardTitle className='text-base'>Auction dollar values</CardTitle>
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
          </Card>
          <BroadcastTable
            columns={auctionColumns}
            rows={auction.data?.players ?? []}
            getRowId={(p) => p.player_id}
            isLoading={auction.isLoading}
            emptyMessage='No auction values available.'
          />
        </TabsContent>
      </Tabs>
    </FadeIn>
  );
}
