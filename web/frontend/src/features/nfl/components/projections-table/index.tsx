'use client';

import { DataTable } from '@/components/ui/table/data-table';
import { DataTableToolbar } from '@/components/ui/table/data-table-toolbar';
import { useDataTable } from '@/hooks/use-data-table';
import { useQuery } from '@tanstack/react-query';
import { projectionsQueryOptions } from '../../api/queries';
import type { ScoringFormat, Position } from '../../api/types';
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
import { Icons } from '@/components/icons';
import { useState } from 'react';

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K'];
const SCORING_OPTIONS: { value: ScoringFormat; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' }
];

export function ProjectionsTable() {
  const [season, setSeason] = useState(2026);
  const [week, setWeek] = useState(1);
  const [scoring, setScoring] = useState<ScoringFormat>('half_ppr');
  const [position, setPosition] = useState<Position>('ALL');

  const { data, isLoading, isError } = useQuery(
    projectionsQueryOptions(season, week, scoring, position === 'ALL' ? undefined : position)
  );

  const projections = data?.projections ?? [];

  const { table } = useDataTable({
    data: projections,
    columns,
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
                  className='flex-1 sm:flex-initial'
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
            <TabsTrigger key={pos} value={pos} className='flex-1 sm:flex-initial'>
              {pos === 'ALL' ? 'All' : pos}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Table */}
      {isLoading ? (
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
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-[var(--space-12)]'>
            <Icons.alertCircle className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
            <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              Failed to load projections. Ensure the API is running on localhost:8000.
            </p>
          </CardContent>
        </Card>
      ) : (
        <DataTable table={table}>
          <DataTableToolbar table={table} />
        </DataTable>
      )}
    </div>
  );
}
