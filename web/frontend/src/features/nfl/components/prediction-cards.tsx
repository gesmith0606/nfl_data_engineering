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
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Icons } from '@/components/icons';
import { EmptyState } from '@/components/EmptyState';
import { PredictionLedger } from './prediction-ledger';
import { formatRelativeTime } from '@/lib/format-relative-time';
import { getTeamColor, getReadableTeamColorVars } from '@/lib/nfl/team-colors';
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
          className='flex h-1.5 bg-[linear-gradient(to_right,var(--away-c)_50%,var(--home-c)_50%)] dark:bg-[linear-gradient(to_right,var(--away-r)_50%,var(--home-r)_50%)]'
          style={
            {
              '--away-c': awayColor,
              '--home-c': homeColor,
              '--away-r': `color-mix(in oklch, ${awayColor} 60%, white)`,
              '--home-r': `color-mix(in oklch, ${homeColor} 60%, white)`
            } as React.CSSProperties
          }
        />
        <CardHeader className='pb-[var(--space-2)]'>
          <div className='flex items-center justify-between gap-[var(--space-2)]'>
            <CardTitle className='text-[length:var(--fs-body)] leading-[var(--lh-body)]'>
              <span className='inline-flex items-center gap-[var(--space-1)]'>
                <span
                  style={getReadableTeamColorVars(prediction.away_team)}
                  className='font-bold text-[var(--team-color)] dark:text-[var(--team-color-readable)]'
                >
                  {prediction.away_team}
                </span>
                <TeamSentimentBadge team={prediction.away_team} season={season} week={week} />
              </span>
              <span className='text-muted-foreground mx-[var(--space-2)]'>@</span>
              <span className='inline-flex items-center gap-[var(--space-1)]'>
                <span
                  style={getReadableTeamColorVars(prediction.home_team)}
                  className='font-bold text-[var(--team-color)] dark:text-[var(--team-color-readable)]'
                >
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
  // Resolve default season/week from `/api/predictions/latest-week` (NOT
  // projections) — predictions and projections can be out of sync (e.g.
  // preseason 2026 has projections but zero game predictions until the
  // season starts). useWeekParams walks back up to 3 seasons if the probe
  // season has no data, so we always land on a populated slice when one
  // exists in any recent season.
  const { season, week, setSeason, setWeek, isResolving, dataAsOf } =
    useWeekParams({ dataSource: 'predictions' });
  const [sortBy, setSortBy] = useState<SortKey>('confidence');
  const [view, setView] = useState<'cards' | 'ledger'>('cards');

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

        {/* Cards ↔ Ledger view toggle — the ledger is the 005-C audit table
         *  (our line vs market side-by-side with edge glyphs). */}
        <Tabs value={view} onValueChange={(v) => setView(v as 'cards' | 'ledger')}>
          <TabsList className='h-[var(--tap-min)] w-full sm:h-9 sm:w-auto'>
            <TabsTrigger value='cards' className='flex-1 sm:flex-initial'>
              Cards
            </TabsTrigger>
            <TabsTrigger value='ledger' className='flex-1 sm:flex-initial'>
              Ledger
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Freshness chip (phase 70-01). Only renders when the /projections
         *  /latest-week probe surfaced a data_as_of timestamp; silent
         *  otherwise (no "Unknown" placeholder). */}
        {dataAsOf ? (
          <Badge
            variant='outline'
            className='ml-auto h-[var(--tap-min)] items-center text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground sm:h-9'
          >
            Updated {formatRelativeTime(dataAsOf)}
          </Badge>
        ) : null}
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
        <EmptyState
          icon={Icons.calendar}
          title='No predictions yet'
          description={`Predictions for ${season} Week ${week} are not available. Check back when games are scheduled.`}
          dataAsOf={dataAsOf}
        />
      ) : isError ? (
        <EmptyState
          icon={Icons.alertCircle}
          title='Unable to load predictions'
          description='The prediction feed is unavailable right now. Please try again in a moment.'
          dataAsOf={dataAsOf}
        />
      ) : predictions.length === 0 ? (
        <EmptyState
          icon={Icons.calendar}
          title='No predictions yet'
          description={`Predictions for ${season} Week ${week} are not available. Check back when games are scheduled.`}
          dataAsOf={dataAsOf}
        />
      ) : view === 'ledger' ? (
        <PredictionLedger predictions={predictions} />
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
