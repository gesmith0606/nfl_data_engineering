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
import { ApiError } from '@/lib/nfl/api';
import { useState } from 'react';
import { useWeekParams } from '@/hooks/use-week-params';
import { Stagger, HoverLift, FadeIn } from '@/lib/motion-primitives';
import { cn } from '@/lib/utils';

/** Edge threshold for the edge-reveal badge. Matches the prediction pipeline's
 *  medium-tier threshold (>=1.5pt) documented in CLAUDE.md. */
const EDGE_REVEAL_THRESHOLD = 1.5;
const EDGE_HIGH_THRESHOLD = 3.0;

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
  const topEdge = Math.max(spreadEdge, totalEdge);
  const hasRevealEdge = topEdge >= EDGE_REVEAL_THRESHOLD;
  const hasHighEdge = topEdge >= EDGE_HIGH_THRESHOLD;

  return (
    <HoverLift lift={3} className='h-full'>
      <Card className='h-full overflow-hidden transition-shadow duration-[var(--motion-base)] hover:shadow-[var(--elevation-overlay)]'>
        <div
          className='flex h-1.5'
          style={{
            background: `linear-gradient(to right, ${awayColor} 50%, ${homeColor} 50%)`
          }}
        />
        <CardHeader className='pb-[var(--space-2)]'>
          <div className='flex items-center justify-between gap-[var(--space-2)]'>
            <CardTitle className='text-[length:var(--fs-body)] leading-[var(--lh-body)]'>
              <span className='inline-flex items-center gap-[var(--space-1)]'>
                <span style={{ color: awayColor }} className='font-bold'>
                  {prediction.away_team}
                </span>
                <TeamSentimentBadge team={prediction.away_team} season={season} week={week} />
              </span>
              <span className='text-muted-foreground mx-[var(--space-2)]'>@</span>
              <span className='inline-flex items-center gap-[var(--space-1)]'>
                <span style={{ color: homeColor }} className='font-bold'>
                  {prediction.home_team}
                </span>
                <TeamSentimentBadge team={prediction.home_team} season={season} week={week} />
              </span>
            </CardTitle>
            <div className='flex items-center gap-[var(--space-1)]'>
              {hasRevealEdge && (
                <FadeIn delay={0.22} rise={4}>
                  <Badge
                    variant={hasHighEdge ? 'default' : 'secondary'}
                    className={cn(
                      'gap-[var(--space-1)] whitespace-nowrap',
                      hasHighEdge && 'edge-shimmer'
                    )}
                    aria-label={`${topEdge.toFixed(1)} point edge`}
                  >
                    <Icons.trendingUp className='h-[var(--space-3)] w-[var(--space-3)]' />
                    {topEdge.toFixed(1)}pt edge
                  </Badge>
                </FadeIn>
              )}
              <Badge variant={confidenceBadgeVariant(prediction.confidence_tier)}>
                {prediction.confidence_tier}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className='space-y-[var(--space-3)]'>
          {/* Spread */}
          <div className='space-y-[var(--space-1)]'>
            <div className='flex items-center justify-between text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              <span className='text-muted-foreground'>Spread</span>
              <div className='flex items-center gap-[var(--space-2)]'>
                <span className='font-mono tabular-nums'>
                  {prediction.predicted_spread > 0 ? '+' : ''}
                  {prediction.predicted_spread.toFixed(1)}
                </span>
                {prediction.vegas_spread !== null && (
                  <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                    (Vegas: {prediction.vegas_spread > 0 ? '+' : ''}
                    {prediction.vegas_spread.toFixed(1)})
                  </span>
                )}
              </div>
            </div>
            {prediction.spread_edge !== null && (
              <div className='space-y-[var(--space-1)]'>
                <Progress value={Math.min((spreadEdge / maxEdge) * 100, 100)} className='h-1.5' />
                <div className='flex items-center justify-between'>
                  <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium'>
                    {prediction.ats_pick}
                  </span>
                  <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                    {spreadEdge.toFixed(1)}pt edge
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Total */}
          <div className='space-y-[var(--space-1)]'>
            <div className='flex items-center justify-between text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              <span className='text-muted-foreground'>Total</span>
              <div className='flex items-center gap-[var(--space-2)]'>
                <span className='font-mono tabular-nums'>
                  {prediction.predicted_total.toFixed(1)}
                </span>
                {prediction.vegas_total !== null && (
                  <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                    (Vegas: {prediction.vegas_total.toFixed(1)})
                  </span>
                )}
              </div>
            </div>
            {prediction.total_edge !== null && (
              <div className='space-y-[var(--space-1)]'>
                <Progress value={Math.min((totalEdge / maxEdge) * 100, 100)} className='h-1.5' />
                <div className='flex items-center justify-between'>
                  <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium'>
                    {prediction.ou_pick}
                  </span>
                  <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                    {totalEdge.toFixed(1)}pt edge
                  </span>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </HoverLift>
  );
}

export function PredictionCardGrid() {
  // HOTFIX-04 (phase 66 / v7.0): resolve default season/week from
  // `/api/projections/latest-week` instead of a hardcoded 2024/1 slate
  // that nobody has data for. Falls back to the current year + week 1
  // when the backend is unreachable so the page still renders.
  const { season, week, setSeason, setWeek, isResolving } = useWeekParams();
  const [sortBy, setSortBy] = useState<SortKey>('confidence');

  const { data, isLoading, isError, error } = useQuery({
    ...predictionsQueryOptions(season, week),
    enabled: !isResolving
  });

  const isNotFound = isError && error instanceof ApiError && error.status === 404;

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
    <div className='space-y-[var(--gap-stack)]'>
      {/* Filters — 2-col grid on mobile (<sm) so the three Selects fit
       *  without horizontal overflow; flex-wrap at sm+. */}
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

        <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortKey)}>
          <SelectTrigger className='h-[var(--tap-min)] col-span-2 w-full sm:h-9 sm:col-span-1 sm:w-36'>
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
      {isLoading || isResolving ? (
        <div className='grid grid-cols-1 gap-[var(--gap-stack)] md:grid-cols-2 lg:grid-cols-3'>
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className='overflow-hidden'>
              <div className='h-1.5 bg-muted' />
              <CardHeader className='pb-[var(--space-2)]'>
                <Skeleton className='h-[var(--space-5)] w-3/4' />
              </CardHeader>
              <CardContent className='space-y-[var(--space-3)]'>
                <div className='space-y-[var(--space-1)]'>
                  <Skeleton className='h-[var(--space-4)] w-full' />
                  <Skeleton className='h-1.5 w-full' />
                  <Skeleton className='h-[var(--space-3)] w-1/2' />
                </div>
                <div className='space-y-[var(--space-1)]'>
                  <Skeleton className='h-[var(--space-4)] w-full' />
                  <Skeleton className='h-1.5 w-full' />
                  <Skeleton className='h-[var(--space-3)] w-1/2' />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : isNotFound ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-[var(--space-12)]'>
            <Icons.info className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
            <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              No prediction data available for {season} Week {week}.
            </p>
            <p className='text-muted-foreground mt-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
              Predictions are generated during the NFL season for weeks with scheduled games.
            </p>
          </CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-[var(--space-12)]'>
            <Icons.alertCircle className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
            <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              Failed to load predictions. Please try again later.
            </p>
          </CardContent>
        </Card>
      ) : predictions.length === 0 ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-[var(--space-12)]'>
            <Icons.info className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
            <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              No predictions available for this week.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Stagger
          step={0.04}
          className='grid grid-cols-1 gap-[var(--gap-stack)] md:grid-cols-2 lg:grid-cols-3'
        >
          {predictions.map((pred) => (
            <PredictionCard key={pred.game_id} prediction={pred} season={season} week={week} />
          ))}
        </Stagger>
      )}
    </div>
  );
}
