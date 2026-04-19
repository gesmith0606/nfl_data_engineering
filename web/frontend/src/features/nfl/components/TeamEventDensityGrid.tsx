'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { teamEventsQueryOptions } from '../api/queries';
import type { OverallSentimentLabel, TeamEvents } from '../api/types';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Icons } from '@/components/icons';

/**
 * 32-team event density grid (NEWS-03).
 *
 * Renders a stable 4×8 tile layout — one tile per NFL team — driven by the
 * ``/api/news/team-events`` response. Background color is keyed off the
 * discrete ``sentiment_label`` bucket (D-03: bullish / bearish / neutral),
 * NOT a continuous sentiment score.
 *
 * Each tile is a keyboard-focusable link to the news feed filtered to the
 * team — matches the existing ``/dashboard/news?team=XXX`` contract.
 */

interface TeamEventDensityGridProps {
  season: number;
  week: number;
  /** Override the link destination (defaults to /dashboard/news?team=ABBR). */
  hrefBuilder?: (team: string) => string;
}

// ---------------------------------------------------------------------------
// Tile color + icon helpers (discrete buckets per D-03)
// ---------------------------------------------------------------------------

function bucketBgClass(label: OverallSentimentLabel): string {
  switch (label) {
    case 'bearish':
      return 'border-red-200 bg-red-50 hover:bg-red-100 dark:border-red-900 dark:bg-red-950/40 dark:hover:bg-red-900/40';
    case 'bullish':
      return 'border-green-200 bg-green-50 hover:bg-green-100 dark:border-green-900 dark:bg-green-950/40 dark:hover:bg-green-900/40';
    default:
      return 'border-border bg-muted/40 hover:bg-muted dark:border-border dark:bg-muted/20 dark:hover:bg-muted/40';
  }
}

function bucketTextClass(label: OverallSentimentLabel): string {
  switch (label) {
    case 'bearish':
      return 'text-red-700 dark:text-red-400';
    case 'bullish':
      return 'text-green-700 dark:text-green-400';
    default:
      return 'text-muted-foreground';
  }
}

function bucketIcon(label: OverallSentimentLabel) {
  switch (label) {
    case 'bearish':
      return Icons.trendingDown;
    case 'bullish':
      return Icons.trendingUp;
    default:
      return Icons.minus;
  }
}

function defaultHref(team: string): string {
  return `/dashboard/news?team=${encodeURIComponent(team)}`;
}

// ---------------------------------------------------------------------------
// Single tile
// ---------------------------------------------------------------------------

function TeamTile({
  team,
  href
}: {
  team: TeamEvents;
  href: string;
}) {
  const Icon = bucketIcon(team.sentiment_label);
  const bgClass = bucketBgClass(team.sentiment_label);
  const textClass = bucketTextClass(team.sentiment_label);

  const ariaLabel = `${team.team} — ${team.sentiment_label} (${team.negative_event_count} bearish, ${team.positive_event_count} bullish, ${team.neutral_event_count} neutral events)`;

  return (
    <Link
      href={href}
      aria-label={ariaLabel}
      className={`group flex flex-col items-start justify-between rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${bgClass}`}
    >
      <div className='flex w-full items-center justify-between'>
        <span className='text-sm font-bold tracking-tight'>{team.team}</span>
        <Icon className={`h-4 w-4 ${textClass}`} />
      </div>

      <div className='mt-2 flex flex-col gap-0.5'>
        <span className={`text-xs font-medium capitalize ${textClass}`}>
          {team.sentiment_label}
        </span>
        <span className='text-muted-foreground text-[11px] tabular-nums'>
          {team.total_articles} article{team.total_articles === 1 ? '' : 's'}
        </span>
      </div>

      {team.top_events.length > 0 && (
        <ul className='mt-2 w-full space-y-0.5 text-[11px] text-muted-foreground'>
          {team.top_events.slice(0, 3).map((evt) => (
            <li key={evt} className='truncate'>
              {evt}
            </li>
          ))}
        </ul>
      )}
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Grid (main export)
// ---------------------------------------------------------------------------

export function TeamEventDensityGrid({
  season,
  week,
  hrefBuilder
}: TeamEventDensityGridProps) {
  const { data, isLoading, isError } = useQuery(
    teamEventsQueryOptions(season, week)
  );

  if (isLoading) {
    return (
      <div className='grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8'>
        {Array.from({ length: 32 }).map((_, i) => (
          <Skeleton key={i} className='h-28 rounded-lg' />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardContent className='flex flex-col items-center justify-center py-8 text-center'>
          <Icons.alertCircle className='text-muted-foreground mb-2 h-6 w-6' />
          <p className='text-muted-foreground text-sm'>
            Could not load team events. The backend returned an error.
          </p>
        </CardContent>
      </Card>
    );
  }

  // Backend contract: exactly 32 rows, zero-filled on empty data.
  const builder = hrefBuilder ?? defaultHref;

  return (
    <div
      className='grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8'
      role='list'
      aria-label={`Team event density for week ${week}`}
    >
      {data.map((team) => (
        <div key={team.team} role='listitem'>
          <TeamTile team={team} href={builder(team.team)} />
        </div>
      ))}
    </div>
  );
}
