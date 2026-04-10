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

export function LineupView() {
  const [season, setSeason] = useState(2024);
  const [week, setWeek] = useState(17);
  const [team, setTeam] = useState<string | null>(null);

  const { data: lineup, isLoading, isError } = useQuery(
    lineupQueryOptions(season, week, team ?? '')
  );

  return (
    <div className='space-y-6'>
      {/* Season/Week selectors */}
      <div className='flex flex-wrap items-center gap-4'>
        <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
          <SelectTrigger className='w-28'>
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

      {/* Field View */}
      {team && (
        <Card>
          <CardContent className='pt-6'>
            {isLoading ? (
              <div className='flex items-center justify-center py-12'>
                <Icons.spinner className='text-muted-foreground h-8 w-8 animate-spin' />
              </div>
            ) : isError ? (
              <div className='flex flex-col items-center justify-center py-12'>
                <Icons.alertCircle className='text-muted-foreground mb-2 h-8 w-8' />
                <p className='text-muted-foreground text-sm'>
                  Failed to load lineup. Ensure the API is running.
                </p>
              </div>
            ) : lineup ? (
              <FieldView lineup={lineup} />
            ) : null}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
