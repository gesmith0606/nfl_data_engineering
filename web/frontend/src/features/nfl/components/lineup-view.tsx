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
import { useState } from 'react';
import { useWeekParams } from '@/hooks/use-week-params';
import { FadeIn, DataLoadReveal } from '@/lib/motion-primitives';

export function LineupView() {
  // HOTFIX-05 (phase 66 / v7.0): resolve default season/week from
  // `/api/projections/latest-week` instead of hardcoded 2026/1 so
  // users land on the latest slice that actually has data.
  const { season, week, setSeason, setWeek, isResolving } = useWeekParams();
  const [team, setTeam] = useState<string | null>(null);

  const { data: lineup, isLoading, isError } = useQuery({
    ...lineupQueryOptions(season, week, team ?? ''),
    enabled: !isResolving && !!team
  });

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
                <div className='flex flex-col items-center justify-center py-[var(--space-12)]'>
                  <Icons.alertCircle className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
                  <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                    Failed to load lineup. Ensure the API is running.
                  </p>
                </div>
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
