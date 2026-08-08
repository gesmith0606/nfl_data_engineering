'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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

function Spinner() {
  return (
    <div className='flex justify-center py-8'>
      <Icons.spinner className='text-muted-foreground h-6 w-6 animate-spin' />
    </div>
  );
}

export function DynastyView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = cw?.season ?? new Date().getFullYear();
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

        <TabsContent value='dynasty'>
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
            <CardContent>
              {rankings.isLoading ? (
                <Spinner />
              ) : (
                <div className='overflow-x-auto'>
                  <table className='w-full text-sm'>
                    <thead>
                      <tr className='text-muted-foreground border-b text-left text-xs'>
                        <th className='py-2 pr-4'>#</th>
                        <th className='py-2 pr-4'>Player</th>
                        <th className='py-2 pr-4 text-right'>Age</th>
                        <th className='py-2 pr-4 text-right'>Dynasty pts</th>
                        <th className='py-2 pr-4 text-right'>Season pts</th>
                        <th className='py-2 pr-4 text-right'>Age mult</th>
                        <th className='py-2 text-right'>VORP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rankings.data?.players.map((p, i) => (
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
                            {p.age ?? '—'}
                          </td>
                          <td className='py-1.5 pr-4 text-right font-mono font-medium'>
                            {p.dynasty_points.toFixed(1)}
                          </td>
                          <td className='py-1.5 pr-4 text-right font-mono'>
                            {p.projected_season_points.toFixed(1)}
                          </td>
                          <td className='py-1.5 pr-4 text-right font-mono'>
                            {p.age_multiplier.toFixed(2)}x
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

        <TabsContent value='rookies'>
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>Rookie rankings</CardTitle>
            </CardHeader>
            <CardContent>
              {rookies.isLoading ? (
                <Spinner />
              ) : (
                <div className='overflow-x-auto'>
                  <table className='w-full text-sm'>
                    <thead>
                      <tr className='text-muted-foreground border-b text-left text-xs'>
                        <th className='py-2 pr-4'>#</th>
                        <th className='py-2 pr-4'>Player</th>
                        <th className='py-2 pr-4 text-right'>Age</th>
                        <th className='py-2 pr-4 text-right'>Season pts</th>
                        <th className='py-2 text-right'>Role</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rookies.data?.players.map((p, i) => (
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
                            {p.age ?? '—'}
                          </td>
                          <td className='py-1.5 pr-4 text-right font-mono'>
                            {p.projected_season_points.toFixed(1)}
                          </td>
                          <td className='text-muted-foreground py-1.5 text-right text-xs'>
                            {p.low_sample_role ?? '—'}
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
