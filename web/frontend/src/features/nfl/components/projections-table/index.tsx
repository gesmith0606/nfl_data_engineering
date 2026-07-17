'use client';

import { DataTable } from '@/components/ui/table/data-table';
import { DataTableToolbar } from '@/components/ui/table/data-table-toolbar';
import { useDataTable } from '@/hooks/use-data-table';
import { useQuery } from '@tanstack/react-query';
import { projectionsQueryOptions } from '../../api/queries';
import type { PlayerProjection, ScoringFormat, Position } from '../../api/types';
import { columns } from './columns';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Icons } from '@/components/icons';
import { EmptyState } from '@/components/EmptyState';
import { useWeekParams } from '@/hooks/use-week-params';
import { useState } from 'react';

/* Active filter pills use the primary fill (trophy gold in worldcup26) instead
 * of the muted default — themes correctly everywhere since --primary is defined
 * per theme, and the dark-ink primary-foreground stays AA on the gold. */
const ACTIVE_TAB =
  'data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:font-semibold data-[state=active]:shadow-sm dark:data-[state=active]:bg-primary dark:data-[state=active]:text-primary-foreground';

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K'];

/** PLAN 2 free tier: top-N projections per position; bands are premium. */
const FREE_TIER_LIMIT = 50;
const BAND_COLUMN_IDS = new Set(['projected_floor', 'projected_ceiling']);

/** Keep the top `limit` rows per position by projected points. */
function limitPerPosition(rows: PlayerProjection[], limit: number): PlayerProjection[] {
  const kept: PlayerProjection[] = [];
  const counts = new Map<string, number>();
  const sorted = [...rows].sort((a, b) => (b.projected_points ?? 0) - (a.projected_points ?? 0));
  for (const row of sorted) {
    const count = counts.get(row.position) ?? 0;
    if (count < limit) {
      counts.set(row.position, count + 1);
      kept.push(row);
    }
  }
  return kept;
}
const SCORING_OPTIONS: { value: ScoringFormat; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' }
];

export function ProjectionsTable({ freeTier = false }: { freeTier?: boolean }) {
  const { season, week, setSeason, setWeek, isResolving } = useWeekParams();
  const [scoring, setScoring] = useState<ScoringFormat>('half_ppr');
  const [position, setPosition] = useState<Position>('ALL');

  const { data, isLoading, isError, refetch } = useQuery(
    projectionsQueryOptions(season, week, scoring, position === 'ALL' ? undefined : position)
  );

  const allProjections = data?.projections ?? [];
  // Free tier (auth keys present, no premium): top-50 per position, no
  // floor/ceiling bands. Presentational only — see web/DEPLOYMENT.md.
  const projections = freeTier
    ? limitPerPosition(allProjections, FREE_TIER_LIMIT)
    : allProjections;
  const visibleColumns = freeTier
    ? columns.filter((col) => !BAND_COLUMN_IDS.has(col.id ?? ''))
    : columns;

  const { table } = useDataTable({
    data: projections,
    columns: visibleColumns,
    pageCount: Math.ceil(projections.length / 25),
    shallow: true,
    debounceMs: 300
  });

  return (
    <div className='space-y-[var(--gap-stack)]'>
      {/* Filters — on mobile (<sm) these stack into a 2-column grid so the
       *  Select triggers all fit in 343px without horizontal scroll. */}
      <Card>
        <CardContent className='grid grid-cols-2 items-center gap-[var(--space-2)] pt-[var(--space-6)] sm:flex sm:flex-wrap sm:gap-[var(--gap-stack)]'>
          <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
            <SelectTrigger className='h-[var(--tap-min)] w-full sm:h-9 sm:w-28'>
              <SelectValue placeholder='Season' />
            </SelectTrigger>
            <SelectContent>
              {[2026, 2025, 2024, 2023, 2022].map((s) => (
                <SelectItem key={s} value={String(s)}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={String(week)} onValueChange={(v) => setWeek(Number(v))}>
            <SelectTrigger className='h-[var(--tap-min)] w-full sm:h-9 sm:w-24'>
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

          <Tabs
            value={scoring}
            onValueChange={(v) => setScoring(v as ScoringFormat)}
            className='col-span-2 sm:col-span-1'
          >
            <TabsList className='w-full sm:w-auto'>
              {SCORING_OPTIONS.map((opt) => (
                <TabsTrigger
                  key={opt.value}
                  value={opt.value}
                  className={`flex-1 sm:flex-initial ${ACTIVE_TAB}`}
                >
                  {opt.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </CardContent>
      </Card>

      {/* Position tabs — full-width on mobile so the tabs span the whole row
       *  and each tab still clears the 44px tap minimum. */}
      <Tabs value={position} onValueChange={(v) => setPosition(v as Position)}>
        <TabsList className='w-full sm:w-auto'>
          {POSITIONS.map((pos) => (
            <TabsTrigger key={pos} value={pos} className={`flex-1 sm:flex-initial ${ACTIVE_TAB}`}>
              {pos === 'ALL' ? 'All' : pos}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Table */}
      {isLoading || isResolving ? (
        <Card>
          <CardContent className='pt-[var(--space-4)] space-y-[var(--space-2)]'>
            {/* Header row */}
            <div className='flex gap-[var(--gap-stack)] pb-[var(--space-2)] border-b'>
              {[120, 80, 60, 80, 80, 80, 80].map((w, i) => (
                <Skeleton key={i} className='h-[var(--space-4)]' style={{ width: w }} />
              ))}
            </div>
            {/* Data rows */}
            {Array.from({ length: 10 }).map((_, row) => (
              <div key={row} className='flex gap-[var(--gap-stack)] py-[var(--space-1)]'>
                {[120, 80, 60, 80, 80, 80, 80].map((w, col) => (
                  <Skeleton key={col} className='h-[var(--space-4)]' style={{ width: w }} />
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : isError ? (
        <EmptyState
          icon={Icons.alertCircle}
          title='Unable to load projections'
          description='Something went wrong fetching the latest projections. Please try again.'
          action={
            <Button variant='outline' size='sm' onClick={() => void refetch()}>
              Retry
            </Button>
          }
        />
      ) : (
        <>
          {freeTier && (
            <div className='flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--wc-yellow,#ffd84d)]/25 bg-[rgba(255,216,77,0.06)] px-4 py-2.5 text-sm'>
              <span className='text-muted-foreground'>
                Free tier — top {FREE_TIER_LIMIT} per position. Premium unlocks every ranked
                player plus floor/ceiling bands.
              </span>
              <a
                href='/pricing'
                className='wc-display whitespace-nowrap text-[13px] tracking-[0.1em] text-[var(--wc-yellow,#ffd84d)] hover:underline'
              >
                Go Premium →
              </a>
            </div>
          )}
          <DataTable table={table}>
            <DataTableToolbar table={table} />
          </DataTable>
        </>
      )}
    </div>
  );
}
