'use client';

import { useQuery } from '@tanstack/react-query';
import { playerNewsQueryOptions } from '../api/queries';
import type { NewsItem } from '../api/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Icons } from '@/components/icons';
import { DataLoadReveal, Stagger } from '@/lib/motion-primitives';

interface PlayerNewsPanelProps {
  playerId: string;
  season: number;
  week: number;
}

// ---------------------------------------------------------------------------
// Sentiment indicator helpers
// ---------------------------------------------------------------------------

function getSentimentColor(sentiment: number | null): string {
  if (sentiment === null) return 'text-muted-foreground';
  if (sentiment >= 0.2) return 'text-green-600 dark:text-green-400';
  if (sentiment <= -0.2) return 'text-red-600 dark:text-red-400';
  return 'text-yellow-600 dark:text-yellow-400';
}

function getSentimentLabel(sentiment: number | null): string {
  if (sentiment === null) return 'neutral';
  if (sentiment >= 0.2) return 'positive';
  if (sentiment <= -0.2) return 'negative';
  return 'neutral';
}

// ---------------------------------------------------------------------------
// Source display helpers
// ---------------------------------------------------------------------------

const SOURCE_LABELS: Record<string, string> = {
  rss_espn: 'ESPN',
  rss_nfl: 'NFL.com',
  rss_rotoworld: 'Rotoworld',
  sleeper: 'Sleeper',
  twitter: 'Twitter/X',
  nfl_injury_report: 'NFL Injury Report',
  nfl_inactives: 'NFL Inactives',
  official: 'Official',
  reddit: 'Reddit'
};

function formatSource(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

// ---------------------------------------------------------------------------
// Relative time helper
// ---------------------------------------------------------------------------

function relativeTime(isoString: string | null): string {
  if (!isoString) return '';
  try {
    const date = new Date(isoString);
    const diffMs = Date.now() - date.getTime();
    const diffMins = Math.floor(diffMs / 60_000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return '';
  }
}

// ---------------------------------------------------------------------------
// Event flag badges
// ---------------------------------------------------------------------------

function EventBadges({ item }: { item: NewsItem }) {
  const flags: { label: string; variant: 'destructive' | 'secondary' | 'outline' }[] = [];

  if (item.is_ruled_out) flags.push({ label: 'RULED OUT', variant: 'destructive' });
  if (item.is_inactive) flags.push({ label: 'INACTIVE', variant: 'destructive' });
  if (item.is_suspended) flags.push({ label: 'SUSPENDED', variant: 'destructive' });
  if (item.is_questionable) flags.push({ label: 'QUESTIONABLE', variant: 'secondary' });
  if (item.is_returning) flags.push({ label: 'RETURNING', variant: 'outline' });

  if (flags.length === 0) return null;

  return (
    <div className='flex flex-wrap gap-[var(--space-1)] mt-[var(--space-1)]'>
      {flags.map((f) => (
        <Badge
          key={f.label}
          variant={f.variant}
          className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
        >
          {f.label}
        </Badge>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single news item row
// ---------------------------------------------------------------------------

function NewsItemRow({ item }: { item: NewsItem }) {
  const sentimentColor = getSentimentColor(item.sentiment);
  const sentimentLabel = getSentimentLabel(item.sentiment);

  return (
    <div className='flex flex-col gap-[var(--space-1)] py-[var(--space-3)] border-b last:border-b-0'>
      <div className='flex items-start justify-between gap-[var(--space-2)]'>
        <div className='flex-1 min-w-0'>
          {item.url ? (
            <a
              href={item.url}
              target='_blank'
              rel='noopener noreferrer'
              className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium hover:underline line-clamp-2'
            >
              {item.title ?? 'Untitled'}
            </a>
          ) : (
            <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium line-clamp-2'>
              {item.title ?? 'Untitled'}
            </p>
          )}
        </div>
        <span
          className={`text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium shrink-0 ${sentimentColor}`}
        >
          {sentimentLabel}
        </span>
      </div>

      {item.body_snippet && (
        <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground line-clamp-2'>
          {item.body_snippet}
        </p>
      )}

      <EventBadges item={item} />

      <div className='flex items-center gap-[var(--space-2)] mt-[var(--space-1)]'>
        <Badge
          variant='outline'
          className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
        >
          {formatSource(item.source)}
        </Badge>
        {item.category && (
          <Badge
            variant='secondary'
            className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] capitalize'
          >
            {item.category}
          </Badge>
        )}
        {item.published_at && (
          <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground ml-auto'>
            {relativeTime(item.published_at)}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------

function NewsSkeleton() {
  return (
    <div className='space-y-[var(--space-3)] py-[var(--space-2)]'>
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className='flex flex-col gap-[var(--space-2)] py-[var(--space-3)] border-b last:border-b-0'
        >
          <Skeleton className='h-[var(--space-4)] w-3/4' />
          <Skeleton className='h-[var(--space-3)] w-full' />
          <div className='flex gap-[var(--space-2)]'>
            <Skeleton className='h-[var(--space-5)] w-16 rounded-full' />
            <Skeleton className='h-[var(--space-5)] w-12 rounded-full' />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel component
// ---------------------------------------------------------------------------

export function PlayerNewsPanel({ playerId, season, week }: PlayerNewsPanelProps) {
  const { data: items, isLoading, isError, dataUpdatedAt } = useQuery(
    playerNewsQueryOptions(playerId, season, week, 10)
  );

  const lastUpdated = dataUpdatedAt
    ? relativeTime(new Date(dataUpdatedAt).toISOString())
    : null;

  return (
    <Card>
      <CardHeader>
        <div className='flex items-start justify-between gap-[var(--space-2)]'>
          <CardTitle className='flex items-center gap-[var(--space-2)]'>
            <Icons.info className='h-[var(--space-4)] w-[var(--space-4)]' />
            Recent News
          </CardTitle>
          {lastUpdated && (
            <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground pt-0.5'>
              Updated {lastUpdated}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <DataLoadReveal loading={isLoading} skeleton={<NewsSkeleton />}>
          {isError ? (
            <div className='flex flex-col items-center justify-center py-[var(--space-8)] text-center'>
              <Icons.alertCircle className='h-[var(--space-6)] w-[var(--space-6)] text-muted-foreground mb-[var(--space-2)]' />
              <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
                Could not load news. Ensure the API is running.
              </p>
            </div>
          ) : !items || items.length === 0 ? (
            <div className='flex flex-col items-center justify-center py-[var(--space-8)] text-center'>
              <Icons.alertCircle className='h-[var(--space-6)] w-[var(--space-6)] text-muted-foreground mb-[var(--space-2)]' />
              <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
                No recent news for this player.
              </p>
              <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground mt-[var(--space-1)]'>
                News appears here after the sentiment pipeline runs.
              </p>
            </div>
          ) : (
            <Stagger>
              {items.map((item, idx) => (
                <NewsItemRow key={item.doc_id ?? idx} item={item} />
              ))}
            </Stagger>
          )}
        </DataLoadReveal>
      </CardContent>
    </Card>
  );
}
