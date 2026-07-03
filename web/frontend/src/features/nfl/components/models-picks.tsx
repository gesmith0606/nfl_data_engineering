'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';

import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Icons } from '@/components/icons';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { resolvePredictionsLatestWeek } from '@/lib/week-context';
import { predictionsQueryOptions } from '../api/queries';
import { SectionHeading } from './section-heading';
import type { GamePrediction } from '../api/types';

const EDGE_HIGH_THRESHOLD = 3.0;
const MAX_HOPS = 3;

function topEdge(p: GamePrediction): number {
  return Math.max(Math.abs(p.spread_edge ?? 0), Math.abs(p.total_edge ?? 0));
}

function PickTile({ prediction }: { prediction: GamePrediction }) {
  const awayColor = getTeamColor(prediction.away_team);
  const homeColor = getTeamColor(prediction.home_team);
  const edge = topEdge(prediction);
  const isSpreadEdge =
    Math.abs(prediction.spread_edge ?? 0) >= Math.abs(prediction.total_edge ?? 0);
  const pick = isSpreadEdge ? prediction.ats_pick : prediction.ou_pick;

  return (
    <Link
      href='/dashboard/predictions'
      className='group bg-card hover:border-primary/50 focus-visible:ring-ring/50 relative flex flex-col gap-[var(--space-2)] overflow-hidden rounded-[var(--radius-lg)] border py-[var(--space-3)] pr-[var(--space-3)] pl-[var(--space-4)] shadow-sm transition-colors duration-[var(--motion-base)] focus-visible:ring-[3px] focus-visible:outline-none'
    >
      <div
        className='absolute inset-y-[var(--space-2)] left-0 w-[3px] rounded-full'
        style={{ background: `linear-gradient(to bottom, ${awayColor}, ${homeColor})` }}
      />
      <div className='flex items-center justify-between gap-[var(--space-2)]'>
        <span className='wc-display text-[length:var(--fs-body)] leading-none'>
          <span style={{ color: awayColor }}>{prediction.away_team}</span>
          <span className='text-muted-foreground mx-[var(--space-1)]'>@</span>
          <span style={{ color: homeColor }}>{prediction.home_team}</span>
        </span>
        <Badge
          variant={edge >= EDGE_HIGH_THRESHOLD ? 'default' : 'secondary'}
          className='shrink-0 gap-[var(--space-1)] whitespace-nowrap tabular-nums'
        >
          <Icons.trendingUp className='size-[var(--space-3)]' />
          {edge.toFixed(1)}pt
        </Badge>
      </div>
      <div className='flex items-center justify-between text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
        <span className='font-medium'>{pick}</span>
        <span className='text-muted-foreground tabular-nums'>
          {isSpreadEdge ? 'Spread' : 'Total'}{' '}
          <span className='font-mono'>
            {isSpreadEdge
              ? `${prediction.predicted_spread > 0 ? '+' : ''}${prediction.predicted_spread.toFixed(1)}`
              : prediction.predicted_total.toFixed(1)}
          </span>
          {isSpreadEdge && prediction.vegas_spread !== null
            ? ` vs ${prediction.vegas_spread > 0 ? '+' : ''}${prediction.vegas_spread.toFixed(1)}`
            : !isSpreadEdge && prediction.vegas_total !== null
              ? ` vs ${prediction.vegas_total.toFixed(1)}`
              : ''}
        </span>
      </div>
    </Link>
  );
}

function PicksHeading() {
  return (
    <SectionHeading
      overline='Biggest Edges vs Vegas'
      title='Model’s Picks'
      action={
        <Link
          href='/dashboard/predictions'
          className='text-muted-foreground hover:text-foreground inline-flex items-center gap-[var(--space-1)] text-[length:var(--fs-xs)] leading-none tracking-[0.08em] uppercase transition-colors duration-[var(--motion-base)]'
        >
          All games
          <Icons.arrowRight className='size-[var(--space-3)]' />
        </Link>
      }
    />
  );
}

/**
 * "Model's Picks" home module — surfaces the top-3 edges from the latest
 * populated predictions week. Resolves the week without touching the URL
 * (walks back up to 3 seasons), and collapses to nothing if the backend is
 * unavailable or there are no games yet (offseason) so the page never breaks.
 */
export function ModelsPicks() {
  const probeSeason = new Date().getFullYear();

  const weekQuery = useQuery({
    queryKey: ['models-picks', 'latest-week', probeSeason],
    queryFn: async () => {
      for (let hop = 0; hop < MAX_HOPS; hop++) {
        const info = await resolvePredictionsLatestWeek(probeSeason - hop);
        if (info?.week != null && info.season != null) return info;
      }
      return null;
    },
    staleTime: 60 * 60 * 1000
  });

  const resolved = weekQuery.data ?? null;

  const predQuery = useQuery({
    ...predictionsQueryOptions(resolved?.season ?? 0, resolved?.week ?? 0),
    enabled: Boolean(resolved?.week)
  });

  // Still resolving — render a compact placeholder so the hub feels alive.
  const isPending = weekQuery.isPending || (Boolean(resolved?.week) && predQuery.isPending);

  if (isPending) {
    return (
      <section className='space-y-[var(--space-3)]'>
        <PicksHeading />
        <div className='grid grid-cols-1 gap-[var(--gap-stack)] sm:grid-cols-3'>
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className='overflow-hidden'>
              <CardContent className='space-y-[var(--space-2)] py-[var(--space-3)]'>
                <Skeleton className='h-[var(--space-5)] w-3/4' />
                <Skeleton className='h-[var(--space-3)] w-1/2' />
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    );
  }

  const picks = [...(predQuery.data?.predictions ?? [])]
    .filter((p) => topEdge(p) > 0)
    .sort((a, b) => topEdge(b) - topEdge(a))
    .slice(0, 3);

  // Backend down, offseason, or no edges — collapse gracefully.
  if (!resolved?.week || predQuery.isError || picks.length === 0) return null;

  return (
    <section className='space-y-[var(--space-3)]'>
      <PicksHeading />
      <div className='grid grid-cols-1 gap-[var(--gap-stack)] sm:grid-cols-3'>
        {picks.map((p) => (
          <PickTile key={p.game_id} prediction={p} />
        ))}
      </div>
    </section>
  );
}
