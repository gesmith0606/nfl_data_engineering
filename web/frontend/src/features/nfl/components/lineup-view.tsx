'use client';

import { useQuery } from '@tanstack/react-query';
import { lineupQueryOptions } from '../api/queries';
import TeamSelector from './team-selector';
import FieldView from './field-view';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Icons } from '@/components/icons';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/EmptyState';
import { formatRelativeTime } from '@/lib/format-relative-time';
import { useState } from 'react';
import { useWeekParams } from '@/hooks/use-week-params';
import { FadeIn, DataLoadReveal } from '@/lib/motion-primitives';

export function LineupView() {
  // HOTFIX-05 (phase 66 / v7.0): resolve default season/week from
  // `/api/projections/latest-week` instead of hardcoded 2026/1 so
  // users land on the latest slice that actually has data.
  const { season, week, setSeason, setWeek, isResolving, dataAsOf } =
    useWeekParams();
  const [team, setTeam] = useState<string | null>(null);

  const { data: lineup, isLoading, isError } = useQuery({
    ...lineupQueryOptions(season, week, team ?? ''),
    enabled: !isResolving && !!team
  });

  // Plan 70-01: treat an empty offense payload the same as "no lineup"
  // for empty-state routing — the backend's graceful defaulting (phase 66)
  // returns a 200 with an empty array in offseason.
  const lineupIsEmpty = !!lineup && (lineup.offense?.length ?? 0) === 0;

  return (
    <FadeIn className='space-y-[var(--gap-section)]'>
      {/* Season/Week selectors — 2-col grid on mobile, flex at sm+. */}
      <div className='grid grid-cols-2 gap-[var(--space-2)] sm:flex sm:flex-wrap sm:items-center sm:gap-[var(--gap-stack)]'>
        <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
          <SelectTrigger className='h-[var(--tap-min)] w-full sm:h-9 sm:w-28'>
            <SelectValue placeholder='Season' />
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
          <SelectTrigger className='h-[var(--tap-min)] w-full sm:h-9 sm:w-28'>
            <SelectValue placeholder='Week' />
          </SelectTrigger>
          <SelectContent>
            {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
              <SelectItem key={w} value={String(w)}>
                Week {w}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Freshness chip (phase 70-01). Silent when no timestamp available. */}
        {dataAsOf ? (
          <Badge
            variant='outline'
            className='ml-auto h-[var(--tap-min)] items-center text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground sm:h-9'
          >
            Updated {formatRelativeTime(dataAsOf)}
          </Badge>
        ) : null}
      </div>

      {/* Team Selector */}
      <Card>
        <CardHeader>
          <CardTitle>Select Team</CardTitle>
        </CardHeader>
        <CardContent>
          <TeamSelector selectedTeam={team} onSelectTeam={setTeam} />
        </CardContent>
      </Card>

      {/* Field View with skeleton → content crossfade */}
      {team && (
        <Card>
          <CardContent className='pt-[var(--space-6)]'>
            <DataLoadReveal
              loading={isLoading || isResolving}
              skeleton={
                <div className='flex items-center justify-center py-[var(--space-12)]'>
                  <Icons.spinner className='text-muted-foreground h-[var(--space-8)] w-[var(--space-8)] animate-spin' />
                </div>
              }
            >
              {isError ? (
                <EmptyState
                  icon={Icons.alertCircle}
                  title='Unable to load lineup'
                  description='The lineup service is unavailable right now. Please try again in a moment.'
                  dataAsOf={dataAsOf}
                />
              ) : lineupIsEmpty ? (
                <EmptyState
                  icon={Icons.calendar}
                  title='No lineup yet'
                  description={`Lineup data for ${team} in Week ${week} of ${season} is not available. This usually means the season has not started or this week's games are upcoming.`}
                  dataAsOf={dataAsOf}
                />
              ) : lineup ? (
                <FieldView lineup={lineup} />
              ) : null}
            </DataLoadReveal>
          </CardContent>
        </Card>
      )}
    </FadeIn>
  );
}
