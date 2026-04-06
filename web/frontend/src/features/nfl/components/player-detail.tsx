'use client';

import { useQuery } from '@tanstack/react-query';
import { playerDetailQueryOptions } from '../api/queries';
import type { ScoringFormat } from '../api/types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import { Icons } from '@/components/icons';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { useState } from 'react';

interface PlayerDetailProps {
  playerId: string;
}

const SCORING_OPTIONS: { value: ScoringFormat; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' }
];

export function PlayerDetail({ playerId }: PlayerDetailProps) {
  const [season, setSeason] = useState(2026);
  const [week, setWeek] = useState(1);
  const [scoring, setScoring] = useState<ScoringFormat>('half_ppr');

  const { data: player, isLoading, isError } = useQuery(
    playerDetailQueryOptions(playerId, season, week, scoring)
  );

  if (isLoading) {
    return (
      <div className='flex items-center justify-center py-12'>
        <Icons.spinner className='text-muted-foreground h-8 w-8 animate-spin' />
      </div>
    );
  }

  if (isError || !player) {
    return (
      <Card>
        <CardContent className='flex flex-col items-center justify-center py-12'>
          <Icons.alertCircle className='text-muted-foreground mb-2 h-8 w-8' />
          <p className='text-muted-foreground text-sm'>
            Failed to load player details. Ensure the API is running.
          </p>
        </CardContent>
      </Card>
    );
  }

  const teamColor = getTeamColor(player.team);
  const range = player.projected_ceiling - player.projected_floor;
  const pointInRange = range > 0 ? ((player.projected_points - player.projected_floor) / range) * 100 : 50;

  return (
    <div className='space-y-6'>
      {/* Filters */}
      <div className='flex flex-wrap items-center gap-4'>
        <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
          <SelectTrigger className='w-28'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[2026, 2025, 2024, 2023].map((s) => (
              <SelectItem key={s} value={String(s)}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={String(week)} onValueChange={(v) => setWeek(Number(v))}>
          <SelectTrigger className='w-24'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
              <SelectItem key={w} value={String(w)}>
                Week {w}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Tabs value={scoring} onValueChange={(v) => setScoring(v as ScoringFormat)}>
          <TabsList>
            {SCORING_OPTIONS.map((opt) => (
              <TabsTrigger key={opt.value} value={opt.value}>
                {opt.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {/* Player Header Card */}
      <Card className='overflow-hidden'>
        <div className='h-2 w-full' style={{ backgroundColor: teamColor }} />
        <CardHeader>
          <div className='flex items-center justify-between'>
            <div>
              <CardTitle className='text-2xl'>{player.player_name}</CardTitle>
              <CardDescription className='flex items-center gap-2 mt-1'>
                <Badge variant='outline'>{player.position}</Badge>
                <span className='font-mono text-sm' style={{ color: teamColor }}>
                  {player.team}
                </span>
                {player.position_rank && (
                  <span className='text-muted-foreground'>
                    #{player.position_rank} {player.position}
                  </span>
                )}
              </CardDescription>
            </div>
            <div className='text-right'>
              <div className='text-4xl font-bold tabular-nums'>
                {player.projected_points.toFixed(1)}
              </div>
              <div className='text-muted-foreground text-sm'>projected pts</div>
            </div>
          </div>
          {player.injury_status && player.injury_status !== 'Active' && (
            <Badge variant='destructive' className='mt-2 w-fit'>
              {player.injury_status}
            </Badge>
          )}
        </CardHeader>
      </Card>

      {/* Floor/Ceiling Visualization */}
      <Card>
        <CardHeader>
          <CardTitle>Floor / Ceiling Range</CardTitle>
        </CardHeader>
        <CardContent>
          <div className='space-y-2'>
            <div className='flex items-center justify-between text-sm'>
              <span className='text-muted-foreground'>
                Floor: {player.projected_floor.toFixed(1)}
              </span>
              <span className='font-bold'>{player.projected_points.toFixed(1)}</span>
              <span className='text-muted-foreground'>
                Ceiling: {player.projected_ceiling.toFixed(1)}
              </span>
            </div>
            <Progress value={pointInRange} className='h-3' />
          </div>
        </CardContent>
      </Card>

      {/* Stat Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle>Projected Stats</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Stat</TableHead>
                <TableHead className='text-right'>Projected</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {player.proj_pass_yards !== null && (
                <TableRow>
                  <TableCell>Passing Yards</TableCell>
                  <TableCell className='text-right tabular-nums'>
                    {Math.round(player.proj_pass_yards)}
                  </TableCell>
                </TableRow>
              )}
              {player.proj_pass_tds !== null && (
                <TableRow>
                  <TableCell>Passing TDs</TableCell>
                  <TableCell className='text-right tabular-nums'>
                    {player.proj_pass_tds.toFixed(1)}
                  </TableCell>
                </TableRow>
              )}
              {player.proj_rush_yards !== null && (
                <TableRow>
                  <TableCell>Rushing Yards</TableCell>
                  <TableCell className='text-right tabular-nums'>
                    {Math.round(player.proj_rush_yards)}
                  </TableCell>
                </TableRow>
              )}
              {player.proj_rush_tds !== null && (
                <TableRow>
                  <TableCell>Rushing TDs</TableCell>
                  <TableCell className='text-right tabular-nums'>
                    {player.proj_rush_tds.toFixed(1)}
                  </TableCell>
                </TableRow>
              )}
              {player.proj_rec !== null && (
                <TableRow>
                  <TableCell>Receptions</TableCell>
                  <TableCell className='text-right tabular-nums'>
                    {player.proj_rec.toFixed(1)}
                  </TableCell>
                </TableRow>
              )}
              {player.proj_rec_yards !== null && (
                <TableRow>
                  <TableCell>Receiving Yards</TableCell>
                  <TableCell className='text-right tabular-nums'>
                    {Math.round(player.proj_rec_yards)}
                  </TableCell>
                </TableRow>
              )}
              {player.proj_rec_tds !== null && (
                <TableRow>
                  <TableCell>Receiving TDs</TableCell>
                  <TableCell className='text-right tabular-nums'>
                    {player.proj_rec_tds.toFixed(1)}
                  </TableCell>
                </TableRow>
              )}
              {player.proj_fg_makes !== null && (
                <TableRow>
                  <TableCell>Field Goals</TableCell>
                  <TableCell className='text-right tabular-nums'>
                    {player.proj_fg_makes.toFixed(1)}
                  </TableCell>
                </TableRow>
              )}
              {player.proj_xp_makes !== null && (
                <TableRow>
                  <TableCell>Extra Points</TableCell>
                  <TableCell className='text-right tabular-nums'>
                    {player.proj_xp_makes.toFixed(1)}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
