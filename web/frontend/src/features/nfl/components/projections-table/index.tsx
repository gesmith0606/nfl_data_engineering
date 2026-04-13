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
    <div className='space-y-4'>
      {/* Filters */}
      <Card>
        <CardContent className='flex flex-wrap items-center gap-4 pt-6'>
          <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
            <SelectTrigger className='w-28'>
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
            <SelectTrigger className='w-24'>
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

          <Tabs value={scoring} onValueChange={(v) => setScoring(v as ScoringFormat)}>
            <TabsList>
              {SCORING_OPTIONS.map((opt) => (
                <TabsTrigger key={opt.value} value={opt.value}>
                  {opt.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </CardContent>
      </Card>

      {/* Position tabs */}
      <Tabs value={position} onValueChange={(v) => setPosition(v as Position)}>
        <TabsList>
          {POSITIONS.map((pos) => (
            <TabsTrigger key={pos} value={pos}>
              {pos === 'ALL' ? 'All' : pos}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Table */}
      {isLoading ? (
        <Card>
          <CardContent className='pt-4 space-y-2'>
            {/* Header row */}
            <div className='flex gap-4 pb-2 border-b'>
              {[120, 80, 60, 80, 80, 80, 80].map((w, i) => (
                <Skeleton key={i} className='h-4' style={{ width: w }} />
              ))}
            </div>
            {/* Data rows */}
            {Array.from({ length: 10 }).map((_, row) => (
              <div key={row} className='flex gap-4 py-1'>
                {[120, 80, 60, 80, 80, 80, 80].map((w, col) => (
                  <Skeleton key={col} className='h-4' style={{ width: w }} />
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-12'>
            <Icons.alertCircle className='text-muted-foreground mb-2 h-8 w-8' />
            <p className='text-muted-foreground text-sm'>
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
