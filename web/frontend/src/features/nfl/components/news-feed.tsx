'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { newsFeedQueryOptions } from '../api/queries';
import type { NewsItem } from '../api/types';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Icons } from '@/components/icons';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 25;

type FeedFilter = 'all' | 'player' | 'team';

const SOURCE_LABELS: Record<string, string> = {
  rss_espn: 'ESPN',
  rss_nfl: 'NFL.com',
  rss_rotoworld: 'Rotoworld',
  sleeper: 'Sleeper',
  twitter: 'Twitter/X',
  nfl_injury_report: 'Injury Report',
  nfl_inactives: 'Inactives',
  official: 'Official',
  reddit: 'Reddit'
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatSource(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

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
    if (diffDays === 1) return 'yesterday';
    return `${diffDays}d ago`;
  } catch {
    return '';
  }
}

function getSentimentBadgeClass(sentiment: number | null): string {
  if (sentiment === null) return 'bg-muted text-muted-foreground';
  if (sentiment >= 0.2) return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
  if (sentiment <= -0.2) return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
  return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400';
}

function getSentimentLabel(sentiment: number | null): string {
  if (sentiment === null) return 'Neutral';
  if (sentiment >= 0.2) return 'Positive';
  if (sentiment <= -0.2) return 'Negative';
  return 'Neutral';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function NewsCard({ item }: { item: NewsItem }) {
  const sentimentClass = getSentimentBadgeClass(item.sentiment);
  const sentimentLabel = getSentimentLabel(item.sentiment);

  return (
    <Card className='overflow-hidden'>
      <CardContent className='p-4 space-y-2'>
        {/* Header row: source + timestamp + sentiment */}
        <div className='flex items-center justify-between gap-2 flex-wrap'>
          <div className='flex items-center gap-2'>
            <Badge variant='outline' className='text-xs shrink-0'>
              {formatSource(item.source)}
            </Badge>
            {item.category && (
              <Badge variant='secondary' className='text-xs capitalize shrink-0'>
                {item.category}
              </Badge>
            )}
          </div>
          <div className='flex items-center gap-2 ml-auto'>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${sentimentClass}`}>
              {sentimentLabel}
            </span>
            {item.published_at && (
              <span className='text-xs text-muted-foreground shrink-0'>
                {relativeTime(item.published_at)}
              </span>
            )}
          </div>
        </div>

        {/* Title */}
        {item.url ? (
          <a
            href={item.url}
            target='_blank'
            rel='noopener noreferrer'
            className='flex items-start gap-1 group'
          >
            <span className='text-sm font-medium leading-snug group-hover:underline line-clamp-3'>
              {item.title ?? 'Untitled'}
            </span>
            <Icons.externalLink className='h-3 w-3 mt-0.5 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity' />
          </a>
        ) : (
          <p className='text-sm font-medium leading-snug line-clamp-3'>
            {item.title ?? 'Untitled'}
          </p>
        )}

        {/* Body snippet */}
        {item.body_snippet && (
          <p className='text-xs text-muted-foreground line-clamp-2'>
            {item.body_snippet}
          </p>
        )}

        {/* Player / team info */}
        {(item.player_name || item.team) && (
          <div className='flex items-center gap-2 pt-1'>
            {item.player_name && (
              <span className='text-xs text-muted-foreground'>
                <span className='font-medium text-foreground'>{item.player_name}</span>
                {item.team ? ` · ${item.team}` : ''}
              </span>
            )}
          </div>
        )}

        {/* Event flags */}
        <div className='flex flex-wrap gap-1'>
          {item.is_ruled_out && <Badge variant='destructive' className='text-xs'>RULED OUT</Badge>}
          {item.is_inactive && <Badge variant='destructive' className='text-xs'>INACTIVE</Badge>}
          {item.is_suspended && <Badge variant='destructive' className='text-xs'>SUSPENDED</Badge>}
          {item.is_questionable && <Badge variant='secondary' className='text-xs'>QUESTIONABLE</Badge>}
          {item.is_returning && <Badge variant='outline' className='text-xs'>RETURNING</Badge>}
        </div>
      </CardContent>
    </Card>
  );
}

function NewsCardSkeleton() {
  return (
    <Card>
      <CardContent className='p-4 space-y-2'>
        <div className='flex items-center gap-2'>
          <Skeleton className='h-5 w-16 rounded-full' />
          <Skeleton className='h-5 w-20 rounded-full' />
          <Skeleton className='h-5 w-14 rounded-full ml-auto' />
        </div>
        <Skeleton className='h-4 w-full' />
        <Skeleton className='h-4 w-3/4' />
        <Skeleton className='h-3 w-full' />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Filter helpers
// ---------------------------------------------------------------------------

function applyClientFilters(
  items: NewsItem[],
  filter: FeedFilter,
  search: string
): NewsItem[] {
  let result = items;

  if (filter === 'player') {
    result = result.filter((item) => !!item.player_id);
  } else if (filter === 'team') {
    result = result.filter((item) => !item.player_id && !!item.team);
  }

  if (search.trim()) {
    const q = search.trim().toLowerCase();
    result = result.filter(
      (item) =>
        item.player_name?.toLowerCase().includes(q) ||
        item.team?.toLowerCase().includes(q) ||
        item.title?.toLowerCase().includes(q)
    );
  }

  return result;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface NewsFeedProps {
  season: number;
  week?: number;
}

/**
 * Full news feed with filter tabs (All / Player / Team), search, and
 * pagination. Auto-refreshes every 5 minutes via TanStack Query.
 */
export function NewsFeed({ season, week }: NewsFeedProps) {
  const [filter, setFilter] = useState<FeedFilter>('all');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);

  const offset = page * PAGE_SIZE;

  const { data: allItems, isLoading, isError } = useQuery(
    newsFeedQueryOptions(season, week, undefined, undefined, PAGE_SIZE * (page + 2), 0)
  );

  const filtered = applyClientFilters(allItems ?? [], filter, search);
  const visibleItems = filtered.slice(0, offset + PAGE_SIZE);
  const hasMore = filtered.length > visibleItems.length;

  const filterButtons: { key: FeedFilter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'player', label: 'Player News' },
    { key: 'team', label: 'Team News' }
  ];

  function handleFilterChange(next: FeedFilter) {
    setFilter(next);
    setPage(0);
  }

  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(0);
  }

  return (
    <div className='space-y-4'>
      {/* Filter row */}
      <div className='flex flex-wrap items-center gap-3'>
        <div className='flex items-center gap-1 rounded-lg border p-1'>
          {filterButtons.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => handleFilterChange(key)}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                filter === key
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className='relative flex-1 min-w-48'>
          <Icons.search className='absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none' />
          <Input
            placeholder='Search player or team...'
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            className='pl-8 h-9'
          />
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className='grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3'>
          {Array.from({ length: 6 }).map((_, i) => (
            <NewsCardSkeleton key={i} />
          ))}
        </div>
      ) : isError ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-12'>
            <Icons.alertCircle className='h-8 w-8 text-muted-foreground mb-2' />
            <p className='text-sm text-muted-foreground'>
              Could not load news. Ensure the API is running.
            </p>
          </CardContent>
        </Card>
      ) : visibleItems.length === 0 ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-12'>
            <Icons.news className='h-8 w-8 text-muted-foreground mb-2' />
            <p className='text-sm font-medium'>No recent news</p>
            <p className='text-xs text-muted-foreground mt-1'>
              {search
                ? 'Try a different search term.'
                : 'Check back during the NFL season after the sentiment pipeline runs.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className='grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3'>
            {visibleItems.map((item, idx) => (
              <NewsCard key={item.doc_id ?? idx} item={item} />
            ))}
          </div>

          {hasMore && (
            <div className='flex justify-center pt-2'>
              <Button
                variant='outline'
                onClick={() => setPage((p) => p + 1)}
              >
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
