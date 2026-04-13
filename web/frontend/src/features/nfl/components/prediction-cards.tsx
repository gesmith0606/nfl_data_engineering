'use client';

import { useQuery } from '@tanstack/react-query';
import { predictionsQueryOptions } from '../api/queries';
import type { GamePrediction } from '../api/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Icons } from '@/components/icons';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { TeamSentimentBadge } from './team-sentiment-badge';
import { useState } from 'react';

type SortKey = 'confidence' | 'spread_edge' | 'total_edge';

function confidenceBadgeVariant(tier: string): 'default' | 'secondary' | 'outline' | 'destructive' {
  switch (tier.toLowerCase()) {
    case 'high':
      return 'default';
    case 'medium':
      return 'secondary';
    default:
      return 'outline';
  }
}

function PredictionCard({ prediction, season, week }: { prediction: GamePrediction; season: number; week: number }) {
  const homeColor = getTeamColor(prediction.home_team);
  const awayColor = getTeamColor(prediction.away_team);
  const spreadEdge = Math.abs(prediction.spread_edge ?? 0);
  const totalEdge = Math.abs(prediction.total_edge ?? 0);
  const maxEdge = 10;

  return (
    <Card className='overflow-hidden'>
      <div
        className='flex h-1.5'
        style={{
          background: `linear-gradient(to right, ${awayColor} 50%, ${homeColor} 50%)`
        }}
      />
      <CardHeader className='pb-2'>
        <div className='flex items-center justify-between'>
          <CardTitle className='text-base'>
            <span className='inline-flex items-center gap-1'>
              <span style={{ color: awayColor }} className='font-bold'>
                {prediction.away_team}
              </span>
              <TeamSentimentBadge team={prediction.away_team} season={season} week={week} />
            </span>
            <span className='text-muted-foreground mx-2'>@</span>
            <span className='inline-flex items-center gap-1'>
              <span style={{ color: homeColor }} className='font-bold'>
                {prediction.home_team}
              </span>
              <TeamSentimentBadge team={prediction.home_team} season={season} week={week} />
            </span>
          </CardTitle>
          <Badge variant={confidenceBadgeVariant(prediction.confidence_tier)}>
            {prediction.confidence_tier}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className='space-y-3'>
        {/* Spread */}
        <div className='space-y-1'>
          <div className='flex items-center justify-between text-sm'>
            <span className='text-muted-foreground'>Spread</span>
            <div className='flex items-center gap-2'>
              <span className='font-mono tabular-nums'>
                {prediction.predicted_spread > 0 ? '+' : ''}
                {prediction.predicted_spread.toFixed(1)}
              </span>
              {prediction.vegas_spread !== null && (
                <span className='text-muted-foreground text-xs'>
                  (Vegas: {prediction.vegas_spread > 0 ? '+' : ''}
                  {prediction.vegas_spread.toFixed(1)})
                </span>
              )}
            </div>
          </div>
          {prediction.spread_edge !== null && (
            <div className='space-y-0.5'>
              <Progress value={Math.min((spreadEdge / maxEdge) * 100, 100)} className='h-1.5' />
              <div className='flex items-center justify-between'>
                <span className='text-xs font-medium'>{prediction.ats_pick}</span>
                <span className='text-muted-foreground text-xs'>
                  {spreadEdge.toFixed(1)}pt edge
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Total */}
        <div className='space-y-1'>
          <div className='flex items-center justify-between text-sm'>
            <span className='text-muted-foreground'>Total</span>
            <div className='flex items-center gap-2'>
              <span className='font-mono tabular-nums'>
                {prediction.predicted_total.toFixed(1)}
              </span>
              {prediction.vegas_total !== null && (
                <span className='text-muted-foreground text-xs'>
                  (Vegas: {prediction.vegas_total.toFixed(1)})
                </span>
              )}
            </div>
          </div>
          {prediction.total_edge !== null && (
            <div className='space-y-0.5'>
              <Progress value={Math.min((totalEdge / maxEdge) * 100, 100)} className='h-1.5' />
              <div className='flex items-center justify-between'>
                <span className='text-xs font-medium'>{prediction.ou_pick}</span>
                <span className='text-muted-foreground text-xs'>
                  {totalEdge.toFixed(1)}pt edge
                </span>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function PredictionCardGrid() {
  const [season, setSeason] = useState(2026);
  const [week, setWeek] = useState(1);
  const [sortBy, setSortBy] = useState<SortKey>('confidence');

  const { data, isLoading, isError } = useQuery(predictionsQueryOptions(season, week));

  const predictions = [...(data?.predictions ?? [])].sort((a, b) => {
    if (sortBy === 'confidence') {
      const order = { high: 0, medium: 1, low: 2 };
      return (
        (order[a.confidence_tier.toLowerCase() as keyof typeof order] ?? 3) -
        (order[b.confidence_tier.toLowerCase() as keyof typeof order] ?? 3)
      );
    }
    if (sortBy === 'spread_edge') {
      return Math.abs(b.spread_edge ?? 0) - Math.abs(a.spread_edge ?? 0);
    }
    return Math.abs(b.total_edge ?? 0) - Math.abs(a.total_edge ?? 0);
  });

  return (
    <div className='space-y-4'>
      {/* Filters */}
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

        <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortKey)}>
          <SelectTrigger className='w-36'>
            <SelectValue placeholder='Sort by' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='confidence'>Confidence</SelectItem>
            <SelectItem value='spread_edge'>Spread Edge</SelectItem>
            <SelectItem value='total_edge'>Total Edge</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Cards */}
      {isLoading ? (
        <div className='grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3'>
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className='overflow-hidden'>
              <div className='h-1.5 bg-muted' />
              <CardHeader className='pb-2'>
                <Skeleton className='h-5 w-3/4' />
              </CardHeader>
              <CardContent className='space-y-3'>
                <div className='space-y-1'>
                  <Skeleton className='h-4 w-full' />
                  <Skeleton className='h-1.5 w-full' />
                  <Skeleton className='h-3 w-1/2' />
                </div>
                <div className='space-y-1'>
                  <Skeleton className='h-4 w-full' />
                  <Skeleton className='h-1.5 w-full' />
                  <Skeleton className='h-3 w-1/2' />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : isError ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-12'>
            <Icons.alertCircle className='text-muted-foreground mb-2 h-8 w-8' />
            <p className='text-muted-foreground text-sm'>
              Failed to load predictions. Ensure the API is running on localhost:8000.
            </p>
          </CardContent>
        </Card>
      ) : predictions.length === 0 ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-12'>
            <Icons.info className='text-muted-foreground mb-2 h-8 w-8' />
            <p className='text-muted-foreground text-sm'>No predictions available for this week.</p>
          </CardContent>
        </Card>
      ) : (
        <div className='grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3'>
          {predictions.map((pred) => (
            <PredictionCard key={pred.game_id} prediction={pred} season={season} week={week} />
          ))}
        </div>
      )}
    </div>
  );
}
