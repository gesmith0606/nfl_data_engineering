'use client';

import { useQuery } from '@tanstack/react-query';
import { lineupQueryOptions } from '../api/queries';
import TeamSelector from './team-selector';
import FieldView from './field-view';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Icons } from '@/components/icons';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/EmptyState';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { WC_KICKER } from '@/features/draft/utils/broadcast-ui';
import { formatRelativeTime } from '@/lib/format-relative-time';
import { useState } from 'react';
import { useWeekParams } from '@/hooks/use-week-params';
import { FadeIn, DataLoadReveal } from '@/lib/motion-primitives';

/** Broadcast-styled Select trigger — dark surface, mint focus (mirrors
 *  WC_INPUT's recipe; SelectTrigger isn't covered by broadcast-ui.ts). */
const WC_SELECT_TRIGGER =
  'wc-display tracking-[0.06em] border-[rgba(145,237,208,0.25)] bg-[rgba(5,7,13,0.5)] text-[#e6eaf2] focus-visible:border-[var(--wc-mint,#91edd0)] focus-visible:ring-[var(--wc-mint,#91edd0)]/40';

export function LineupView() {
  // HOTFIX-05 (phase 66 / v7.0): resolve default season/week from
  // `/api/projections/latest-week` instead of hardcoded 2026/1 so
  // users land on the latest slice that actually has data.
  const { season, week, setSeason, setWeek, isResolving, dataAsOf } = useWeekParams();
  const [team, setTeam] = useState<string | null>(null);

  const {
    data: lineup,
    isLoading,
    isError
  } = useQuery({
    ...lineupQueryOptions(season, week, team ?? ''),
    enabled: !isResolving && !!team
  });

  // Plan 70-01: treat null (envelope unwrapped to no team) or an empty
  // offense payload the same as "no lineup" for empty-state routing — the
  // backend's graceful defaulting (phase 66) returns a 200 with an empty
  // lineups[] in offseason.
  const lineupIsEmpty = lineup === null || (!!lineup && (lineup.offense?.length ?? 0) === 0);

  return (
    <FadeIn className='space-y-[var(--gap-section)]'>
      {/* Season/Week selectors — 2-col grid on mobile, flex at sm+. */}
      <div className='grid grid-cols-2 gap-[var(--space-2)] sm:flex sm:flex-wrap sm:items-center sm:gap-[var(--gap-stack)]'>
        <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
          <SelectTrigger className={`${WC_SELECT_TRIGGER} h-[var(--tap-min)] w-full sm:h-9 sm:w-28`}>
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
          <SelectTrigger className={`${WC_SELECT_TRIGGER} h-[var(--tap-min)] w-full sm:h-9 sm:w-28`}>
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
      <BroadcastPanel className='p-[var(--space-4)]'>
        <div className={WC_KICKER}>Select Team</div>
        <div className='mt-[var(--space-3)]'>
          <TeamSelector selectedTeam={team} onSelectTeam={setTeam} />
        </div>
      </BroadcastPanel>

      {/* Field View with skeleton → content crossfade */}
      {team && (
        <BroadcastPanel className='p-[var(--space-4)] sm:p-[var(--space-6)]'>
          <div className={`${WC_KICKER} mb-[var(--space-3)]`}>Field View</div>
          <div>
            <DataLoadReveal
              loading={isLoading || isResolving}
              skeleton={
                <div className='space-y-[var(--space-4)]'>
                  <Skeleton className='mx-auto h-64 w-full max-w-md rounded-md' />
                  <div className='grid grid-cols-2 gap-[var(--space-2)] sm:grid-cols-3'>
                    {Array.from({ length: 9 }).map((_, i) => (
                      <Skeleton key={i} className='h-[var(--space-8)] w-full rounded-md' />
                    ))}
                  </div>
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
          </div>
        </BroadcastPanel>
      )}
    </FadeIn>
  );
}
