'use client';

import { useQuery } from '@tanstack/react-query';
import { playerBadgesQueryOptions, playerDetailQueryOptions } from '../api/queries';
import type { ScoringFormat } from '../api/types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
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
import Link from 'next/link';
import { EventBadges } from './EventBadges';
import { PlayerNewsPanel } from './player-news-panel';
import { FadeIn, PressScale } from '@/lib/motion-primitives';

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

  // NEWS-04: rule-extracted event badges for the player header card.
  const { data: badges } = useQuery(
    playerBadgesQueryOptions(playerId, season, week)
  );

  if (isLoading) {
    return (
      <div className='flex items-center justify-center py-[var(--space-12)]'>
        <Icons.spinner className='text-muted-foreground h-[var(--space-8)] w-[var(--space-8)] animate-spin' />
      </div>
    );
  }

  if (isError || !player) {
    return (
      <Card>
        <CardContent className='flex flex-col items-center justify-center py-[var(--space-12)]'>
          <Icons.alertCircle className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
          <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
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
    <FadeIn className='space-y-[var(--gap-section)]'>
      {/* Back navigation */}
      <div>
        <PressScale>
          <Button variant='ghost' size='sm' asChild className='-ml-[var(--space-2)]'>
            <Link href='/dashboard/projections'>
              <Icons.chevronLeft className='mr-[var(--space-1)] h-[var(--space-4)] w-[var(--space-4)]' />
              Back to Projections
            </Link>
          </Button>
        </PressScale>
      </div>

      {/* Filters */}
      <div className='flex flex-wrap items-center gap-[var(--gap-stack)]'>
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
          <SelectTrigger className='w-28'>
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
        <div className='h-[var(--space-2)] w-full' style={{ backgroundColor: teamColor }} />
        <CardHeader>
          <div className='flex items-center justify-between'>
            <div>
              <CardTitle className='text-[length:var(--fs-h2)] leading-[var(--lh-h2)]'>
                {player.player_name}
              </CardTitle>
              <CardDescription className='flex items-center gap-[var(--space-2)] mt-[var(--space-1)]'>
                <Badge variant='outline'>{player.position}</Badge>
                <span
                  className='font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'
                  style={{ color: teamColor }}
                >
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
              <div className='text-[length:var(--fs-h1)] leading-[var(--lh-h1)] font-bold tabular-nums'>
                {player.projected_points.toFixed(1)}
              </div>
              <div className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                projected pts
              </div>
            </div>
          </div>
          {player.injury_status && player.injury_status !== 'Active' && (
            <Badge variant='destructive' className='mt-[var(--space-2)] w-fit'>
              {player.injury_status}
            </Badge>
          )}
          {badges && badges.badges.length > 0 && (
            <div className='mt-[var(--space-3)]'>
              <EventBadges
                badges={badges.badges}
                overallLabel={badges.overall_label}
              />
            </div>
          )}
        </CardHeader>
      </Card>

      {/* Floor/Ceiling Visualization */}
      <Card>
        <CardHeader>
          <CardTitle>Floor / Ceiling Range</CardTitle>
        </CardHeader>
        <CardContent>
          <div className='space-y-[var(--space-2)]'>
            <div className='flex items-center justify-between text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              <span className='text-muted-foreground'>
                Floor: {player.projected_floor.toFixed(1)}
              </span>
              <span className='font-bold'>{player.projected_points.toFixed(1)}</span>
              <span className='text-muted-foreground'>
                Ceiling: {player.projected_ceiling.toFixed(1)}
              </span>
            </div>
            <Progress value={pointInRange} className='h-[var(--space-3)]' />
          </div>
        </CardContent>
      </Card>

      {/* Stat Breakdown — grouped by category */}
      <StatBreakdown player={player} />

      {/* News Panel — recent news and sentiment signals */}
      <PlayerNewsPanel playerId={playerId} season={season} week={week} />
    </FadeIn>
  );
}

/** Grouped stat breakdown for a single player projection. */
interface StatBreakdownProps {
  player: import('../api/types').PlayerProjection;
}

interface StatRow {
  label: string;
  value: string;
}

interface StatGroup {
  heading: string;
  rows: StatRow[];
}

function buildStatGroups(player: import('../api/types').PlayerProjection): StatGroup[] {
  const groups: StatGroup[] = [];

  const passingRows: StatRow[] = [];
  if (player.proj_pass_yards !== null)
    passingRows.push({ label: 'Passing Yards', value: Math.round(player.proj_pass_yards).toString() });
  if (player.proj_pass_tds !== null)
    passingRows.push({ label: 'Passing TDs', value: player.proj_pass_tds.toFixed(1) });
  if (passingRows.length > 0) groups.push({ heading: 'Passing', rows: passingRows });

  const rushingRows: StatRow[] = [];
  if (player.proj_rush_yards !== null)
    rushingRows.push({ label: 'Rushing Yards', value: Math.round(player.proj_rush_yards).toString() });
  if (player.proj_rush_tds !== null)
    rushingRows.push({ label: 'Rushing TDs', value: player.proj_rush_tds.toFixed(1) });
  if (rushingRows.length > 0) groups.push({ heading: 'Rushing', rows: rushingRows });

  const receivingRows: StatRow[] = [];
  if (player.proj_rec !== null)
    receivingRows.push({ label: 'Receptions', value: player.proj_rec.toFixed(1) });
  if (player.proj_rec_yards !== null)
    receivingRows.push({ label: 'Receiving Yards', value: Math.round(player.proj_rec_yards).toString() });
  if (player.proj_rec_tds !== null)
    receivingRows.push({ label: 'Receiving TDs', value: player.proj_rec_tds.toFixed(1) });
  if (receivingRows.length > 0) groups.push({ heading: 'Receiving', rows: receivingRows });

  const kickingRows: StatRow[] = [];
  if (player.proj_fg_makes !== null)
    kickingRows.push({ label: 'Field Goals Made', value: player.proj_fg_makes.toFixed(1) });
  if (player.proj_xp_makes !== null)
    kickingRows.push({ label: 'Extra Points Made', value: player.proj_xp_makes.toFixed(1) });
  if (kickingRows.length > 0) groups.push({ heading: 'Kicking', rows: kickingRows });

  return groups;
}

function StatBreakdown({ player }: StatBreakdownProps) {
  const groups = buildStatGroups(player);

  if (groups.length === 0) {
    return (
      <Card>
        <CardContent className='py-[var(--space-8)] text-center text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
          No stat projections available for this player.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Projected Stats</CardTitle>
        <CardDescription>
          Broken down by category for{' '}
          {player.scoring_format.replace('_', ' ').toUpperCase()} scoring
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-[var(--gap-section)]'>
        {groups.map((group) => (
          <div key={group.heading}>
            <h4 className='mb-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold uppercase tracking-wider text-muted-foreground'>
              {group.heading}
            </h4>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Stat</TableHead>
                  <TableHead className='text-right'>Projected</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {group.rows.map((row) => (
                  <TableRow key={row.label}>
                    <TableCell>{row.label}</TableCell>
                    <TableCell className='text-right tabular-nums font-medium'>
                      {row.value}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
