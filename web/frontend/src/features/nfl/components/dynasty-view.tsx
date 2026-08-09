'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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

// ponytail: minimal fetch client scoped to this component — mirrors the
// request()/BASE_URL pattern in @/lib/nfl/api.ts without touching that file.
const BASE_URL =
  typeof window !== 'undefined'
    ? ''
    : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? '';

async function fetchJSON<T>(path: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (API_KEY) headers['X-API-Key'] = API_KEY;
  const res = await fetch(`${BASE_URL}${path}`, { headers });
  if (!res.ok) {
    throw new Error(`API request failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

type DynastyPlayer = {
  player_id: string;
  player_name: string;
  team: string | null;
  position: string;
  age: number | null;
  projected_season_points: number;
  dynasty_points: number;
  age_multiplier: number;
  vorp: number | null;
};

type DynastyRankingsResponse = {
  season: number;
  players: DynastyPlayer[];
};

type RookiePlayer = {
  player_id: string;
  player_name: string;
  team: string | null;
  position: string;
  age: number | null;
  projected_season_points: number;
  low_sample_role: string | null;
};

type RookieRankingsResponse = {
  season: number;
  players: RookiePlayer[];
};

function fetchDynastyRankings(season: number, position: string, limit = 200) {
  const params = new URLSearchParams({ season: String(season), limit: String(limit) });
  if (position !== 'ALL') params.set('position', position);
  return fetchJSON<DynastyRankingsResponse>(`/api/dynasty/rankings?${params}`);
}

function fetchRookieRankings(season: number, limit = 100) {
  const params = new URLSearchParams({ season: String(season), limit: String(limit) });
  return fetchJSON<RookieRankingsResponse>(`/api/dynasty/rookies?${params}`);
}

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE'];

const dynastyColumns: BroadcastColumn<DynastyPlayer>[] = [
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
    key: 'age',
    header: 'Age',
    align: 'right',
    accessor: (p) => p.age ?? '—',
    cellClassName: 'font-mono'
  },
  {
    key: 'dynasty_points',
    header: 'Dynasty pts',
    align: 'right',
    accessor: (p) => p.dynasty_points.toFixed(1),
    cellClassName: 'font-mono font-medium'
  },
  {
    key: 'season_points',
    header: 'Season pts',
    align: 'right',
    accessor: (p) => p.projected_season_points.toFixed(1),
    cellClassName: 'font-mono'
  },
  {
    key: 'age_mult',
    header: 'Age mult',
    align: 'right',
    accessor: (p) => `${p.age_multiplier.toFixed(2)}x`,
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

const rookieColumns: BroadcastColumn<RookiePlayer>[] = [
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
    key: 'age',
    header: 'Age',
    align: 'right',
    accessor: (p) => p.age ?? '—',
    cellClassName: 'font-mono'
  },
  {
    key: 'season_points',
    header: 'Season pts',
    align: 'right',
    accessor: (p) => p.projected_season_points.toFixed(1),
    cellClassName: 'font-mono'
  },
  {
    key: 'role',
    header: 'Role',
    align: 'right',
    accessor: (p) => p.low_sample_role ?? '—',
    cellClassName: 'text-muted-foreground text-xs'
  }
];

export function DynastyView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = toolSeason(cw?.season);
  const [position, setPosition] = useState('ALL');

  const rankings = useQuery({
    queryKey: ['nfl', 'dynasty', 'rankings', season, position],
    queryFn: () => fetchDynastyRankings(season, position, 200),
    staleTime: 60 * 60 * 1000
  });

  const rookies = useQuery({
    queryKey: ['nfl', 'dynasty', 'rookies', season],
    queryFn: () => fetchRookieRankings(season, 100),
    staleTime: 60 * 60 * 1000
  });

  return (
    <FadeIn>
      <Tabs defaultValue='dynasty' className='space-y-4'>
        <TabsList>
          <TabsTrigger value='dynasty'>Dynasty value</TabsTrigger>
          <TabsTrigger value='rookies'>Rookies</TabsTrigger>
        </TabsList>

        <TabsContent value='dynasty' className='space-y-4'>
          <Card>
            <CardHeader className='flex flex-row items-center justify-between'>
              <CardTitle className='text-base'>Dynasty rankings</CardTitle>
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
            columns={dynastyColumns}
            rows={rankings.data?.players ?? []}
            getRowId={(p) => p.player_id}
            isLoading={rankings.isLoading}
            emptyMessage='No dynasty rankings available.'
            filteredLabel={position !== 'ALL' ? `${position} only` : undefined}
            densityKey='nfl.dynasty-view.rankings'
            hideableColumns={['age', 'age_mult', 'vorp']}
          />
        </TabsContent>

        <TabsContent value='rookies' className='space-y-4'>
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>Rookie rankings</CardTitle>
            </CardHeader>
          </Card>
          <BroadcastTable
            columns={rookieColumns}
            rows={rookies.data?.players ?? []}
            getRowId={(p) => p.player_id}
            isLoading={rookies.isLoading}
            emptyMessage='No rookie rankings available.'
          />
        </TabsContent>
      </Tabs>
    </FadeIn>
  );
}
