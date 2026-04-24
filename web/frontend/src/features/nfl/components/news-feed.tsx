'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  alertsQueryOptions,
  newsFeedQueryOptions,
  sentimentSummaryQueryOptions,
  teamSentimentQueryOptions
} from '../api/queries';
import type { Alert, NewsItem, TeamSentiment } from '../api/types';
import type { SentimentSummary } from '@/lib/nfl/types';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Icons } from '@/components/icons';
import { EmptyState } from '@/components/EmptyState';
import { formatRelativeTime } from '@/lib/format-relative-time';
import { EventBadges } from './EventBadges';
import {
  DataLoadReveal,
  FadeIn,
  HoverLift,
  PressScale,
  Stagger
} from '@/lib/motion-primitives';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 25;

const SOURCE_LABELS: Record<string, string> = {
  rss_espn_news: 'ESPN',
  rss_espn: 'ESPN',
  rss_nfl: 'NFL.com',
  rss_rotoworld: 'Rotoworld',
  rss_fantasypros: 'FantasyPros',
  rss_pro_football_talk: 'Pro Football Talk',
  sleeper: 'Sleeper',
  twitter: 'Twitter/X',
  nfl_injury_report: 'Injury Report',
  nfl_inactives: 'Inactives',
  official: 'Official',
  reddit: 'Reddit',
  reddit_nfl: 'r/NFL',
  reddit_fantasyfootball: 'r/FantasyFootball',
  rss: 'RSS'
};

const SOURCE_FILTER_OPTIONS = [
  { value: 'all', label: 'All Sources' },
  { value: 'rss', label: 'RSS / News' },
  { value: 'reddit', label: 'Reddit' },
  { value: 'sleeper', label: 'Sleeper' }
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatSource(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
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
    if (diffDays < 7) return `${diffDays}d ago`;
    const diffWeeks = Math.floor(diffDays / 7);
    return `${diffWeeks}w ago`;
  } catch {
    return '';
  }
}

function getSentimentBadgeClass(sentiment: number | null): string {
  if (sentiment === null) return 'bg-muted text-muted-foreground';
  if (sentiment >= 0.2)
    return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
  if (sentiment <= -0.2)
    return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
  return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400';
}

function getSentimentLabel(sentiment: number | null): string {
  if (sentiment === null) return 'Neutral';
  if (sentiment >= 0.2) return 'Bullish';
  if (sentiment <= -0.2) return 'Bearish';
  return 'Neutral';
}

function getMultiplierLabel(mult: number): string {
  if (mult >= 1.10) return 'Bullish';
  if (mult <= 0.90) return 'Bearish';
  return 'Neutral';
}

function getMultiplierClass(mult: number): string {
  if (mult >= 1.10) return 'text-green-600 dark:text-green-400';
  if (mult <= 0.90) return 'text-red-600 dark:text-red-400';
  return 'text-yellow-600 dark:text-yellow-400';
}

function getTeamSentimentBg(label: string): string {
  switch (label) {
    case 'positive':
      return 'border-green-200 bg-green-50/50 dark:border-green-900 dark:bg-green-950/20';
    case 'negative':
      return 'border-red-200 bg-red-50/50 dark:border-red-900 dark:bg-red-950/20';
    default:
      return 'border-border bg-muted/30';
  }
}

function getAlertTypeLabel(alertType: string): string {
  const labels: Record<string, string> = {
    ruled_out: 'RULED OUT',
    inactive: 'INACTIVE',
    suspended: 'SUSPENDED',
    questionable: 'QUESTIONABLE',
    major_negative: 'BEARISH',
    major_positive: 'BULLISH'
  };
  return labels[alertType] ?? alertType.toUpperCase();
}

function getAlertVariant(
  alertType: string
): 'destructive' | 'secondary' | 'outline' {
  if (['ruled_out', 'inactive', 'suspended'].includes(alertType))
    return 'destructive';
  if (alertType === 'major_negative') return 'destructive';
  if (alertType === 'questionable') return 'secondary';
  return 'outline';
}

// ---------------------------------------------------------------------------
// Skeleton components
// ---------------------------------------------------------------------------

function NewsCardSkeleton() {
  return (
    <Card>
      <CardContent className='p-[var(--pad-card)] space-y-[var(--space-2)]'>
        <div className='flex items-center gap-[var(--space-2)]'>
          <Skeleton className='h-[var(--space-5)] w-16 rounded-full' />
          <Skeleton className='h-[var(--space-5)] w-20 rounded-full' />
          <Skeleton className='h-[var(--space-5)] w-14 rounded-full ml-auto' />
        </div>
        <Skeleton className='h-[var(--space-4)] w-full' />
        <Skeleton className='h-[var(--space-4)] w-3/4' />
        <Skeleton className='h-[var(--space-3)] w-full' />
      </CardContent>
    </Card>
  );
}

function SummaryCardSkeleton() {
  return (
    <Card>
      <CardContent className='p-[var(--pad-card)] space-y-[var(--space-2)]'>
        <Skeleton className='h-[var(--space-4)] w-20' />
        <Skeleton className='h-[var(--space-8)] w-16' />
        <Skeleton className='h-[var(--space-3)] w-24' />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Summary stats bar
// ---------------------------------------------------------------------------

function SentimentSummaryBar({
  summary,
  isLoading
}: {
  summary: SentimentSummary | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className='grid grid-cols-2 gap-[var(--space-3)] md:grid-cols-4'>
        {Array.from({ length: 4 }).map((_, i) => (
          <SummaryCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (!summary) return null;

  const dist = summary.sentiment_distribution;
  const total = dist.positive + dist.neutral + dist.negative;

  return (
    <Stagger className='grid grid-cols-2 gap-[var(--space-3)] md:grid-cols-4'>
      <HoverLift>
        <Card>
          <CardContent className='p-[var(--pad-card)]'>
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
              Players Tracked
            </p>
            <p className='text-[length:var(--fs-h2)] leading-[var(--lh-h2)] font-semibold tabular-nums'>
              {summary.total_players}
            </p>
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
              {summary.total_docs} document{summary.total_docs !== 1 ? 's' : ''}{' '}
              analyzed
            </p>
          </CardContent>
        </Card>
      </HoverLift>

      <HoverLift>
        <Card>
          <CardContent className='p-[var(--pad-card)]'>
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
              Bullish Signals
            </p>
            <p className='text-[length:var(--fs-h2)] leading-[var(--lh-h2)] font-semibold tabular-nums text-green-600 dark:text-green-400'>
              {dist.positive}
            </p>
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
              {total > 0 ? Math.round((dist.positive / total) * 100) : 0}% of
              players
            </p>
          </CardContent>
        </Card>
      </HoverLift>

      <HoverLift>
        <Card>
          <CardContent className='p-[var(--pad-card)]'>
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
              Bearish Signals
            </p>
            <p className='text-[length:var(--fs-h2)] leading-[var(--lh-h2)] font-semibold tabular-nums text-red-600 dark:text-red-400'>
              {dist.negative}
            </p>
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
              {total > 0 ? Math.round((dist.negative / total) * 100) : 0}% of
              players
            </p>
          </CardContent>
        </Card>
      </HoverLift>

      <HoverLift>
        <Card>
          <CardContent className='p-[var(--pad-card)]'>
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
              Neutral
            </p>
            <p className='text-[length:var(--fs-h2)] leading-[var(--lh-h2)] font-semibold tabular-nums text-yellow-600 dark:text-yellow-400'>
              {dist.neutral}
            </p>
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
              {total > 0 ? Math.round((dist.neutral / total) * 100) : 0}% of
              players
            </p>
          </CardContent>
        </Card>
      </HoverLift>
    </Stagger>
  );
}

// ---------------------------------------------------------------------------
// Alerts panel
// ---------------------------------------------------------------------------

function AlertsPanel({
  alerts,
  isLoading
}: {
  alerts: Alert[] | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
            <Icons.warning className='h-[var(--space-4)] w-[var(--space-4)]' />
            Active Alerts
          </CardTitle>
        </CardHeader>
        <CardContent className='space-y-[var(--space-2)]'>
          <Skeleton className='h-[var(--space-6)] w-full' />
          <Skeleton className='h-[var(--space-6)] w-full' />
          <Skeleton className='h-[var(--space-6)] w-3/4' />
        </CardContent>
      </Card>
    );
  }

  if (!alerts || alerts.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
            <Icons.circleCheck className='h-[var(--space-4)] w-[var(--space-4)] text-green-600 dark:text-green-400' />
            No Active Alerts
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
            No players with significant status changes or sentiment shifts this
            week.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
          <Icons.warning className='h-[var(--space-4)] w-[var(--space-4)] text-amber-500' />
          Active Alerts ({alerts.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Stagger className='space-y-[var(--space-2)]'>
          {alerts.map((alert, idx) => (
            <div
              key={`${alert.player_id}-${idx}`}
              className='flex items-center justify-between gap-[var(--space-2)] py-[var(--space-2)] border-b last:border-b-0'
            >
              <div className='flex items-center gap-[var(--space-2)] min-w-0'>
                <Badge
                  variant={getAlertVariant(alert.alert_type)}
                  className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] shrink-0'
                >
                  {getAlertTypeLabel(alert.alert_type)}
                </Badge>
                <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium truncate'>
                  {alert.player_name}
                </span>
                {alert.team && (
                  <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground shrink-0'>
                    {alert.team}
                  </span>
                )}
              </div>
              {alert.sentiment_multiplier != null && (
                <span
                  className={`text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium tabular-nums shrink-0 ${getMultiplierClass(alert.sentiment_multiplier)}`}
                >
                  {alert.sentiment_multiplier.toFixed(2)}x
                </span>
              )}
            </div>
          ))}
        </Stagger>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Top movers panel (bullish / bearish players)
// ---------------------------------------------------------------------------

function TopMoversPanel({
  summary,
  isLoading
}: {
  summary: SentimentSummary | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className='grid grid-cols-1 gap-[var(--space-3)] md:grid-cols-2'>
        <Card>
          <CardContent className='p-[var(--pad-card)] space-y-[var(--space-2)]'>
            <Skeleton className='h-[var(--space-4)] w-24' />
            <Skeleton className='h-[var(--space-5)] w-full' />
            <Skeleton className='h-[var(--space-5)] w-full' />
            <Skeleton className='h-[var(--space-5)] w-3/4' />
          </CardContent>
        </Card>
        <Card>
          <CardContent className='p-[var(--pad-card)] space-y-[var(--space-2)]'>
            <Skeleton className='h-[var(--space-4)] w-24' />
            <Skeleton className='h-[var(--space-5)] w-full' />
            <Skeleton className='h-[var(--space-5)] w-full' />
            <Skeleton className='h-[var(--space-5)] w-3/4' />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!summary) return null;

  return (
    <div className='grid grid-cols-1 gap-[var(--space-3)] md:grid-cols-2'>
      {/* Bullish players */}
      <Card className='border-green-200 dark:border-green-900'>
        <CardHeader className='pb-[var(--space-2)]'>
          <CardTitle className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
            <Icons.trendingUp className='h-[var(--space-4)] w-[var(--space-4)] text-green-600 dark:text-green-400' />
            Bullish Players
          </CardTitle>
          <CardDescription>
            Highest sentiment multipliers this week
          </CardDescription>
        </CardHeader>
        <CardContent>
          {summary.top_positive.length === 0 ? (
            <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground py-[var(--space-2)]'>
              No strong bullish signals detected.
            </p>
          ) : (
            <Stagger className='space-y-[var(--space-1)]'>
              {summary.top_positive.map((p, idx) => (
                <div
                  key={`${p.player_id}-${idx}`}
                  className='flex items-center justify-between py-[var(--space-2)] border-b last:border-b-0'
                >
                  <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                    {p.player_name}
                  </span>
                  <div className='flex items-center gap-[var(--space-2)]'>
                    <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
                      {p.doc_count} doc{p.doc_count !== 1 ? 's' : ''}
                    </span>
                    <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold tabular-nums text-green-600 dark:text-green-400'>
                      {p.sentiment_multiplier.toFixed(2)}x
                    </span>
                  </div>
                </div>
              ))}
            </Stagger>
          )}
        </CardContent>
      </Card>

      {/* Bearish players */}
      <Card className='border-red-200 dark:border-red-900'>
        <CardHeader className='pb-[var(--space-2)]'>
          <CardTitle className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
            <Icons.trendingDown className='h-[var(--space-4)] w-[var(--space-4)] text-red-600 dark:text-red-400' />
            Bearish Players
          </CardTitle>
          <CardDescription>
            Lowest sentiment multipliers this week
          </CardDescription>
        </CardHeader>
        <CardContent>
          {summary.top_negative.length === 0 ? (
            <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground py-[var(--space-2)]'>
              No strong bearish signals detected.
            </p>
          ) : (
            <Stagger className='space-y-[var(--space-1)]'>
              {summary.top_negative.map((p, idx) => (
                <div
                  key={`${p.player_id}-${idx}`}
                  className='flex items-center justify-between py-[var(--space-2)] border-b last:border-b-0'
                >
                  <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                    {p.player_name}
                  </span>
                  <div className='flex items-center gap-[var(--space-2)]'>
                    <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
                      {p.doc_count} doc{p.doc_count !== 1 ? 's' : ''}
                    </span>
                    <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold tabular-nums text-red-600 dark:text-red-400'>
                      {p.sentiment_multiplier.toFixed(2)}x
                    </span>
                  </div>
                </div>
              ))}
            </Stagger>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Team sentiment grid
// ---------------------------------------------------------------------------

function TeamSentimentGrid({
  teams,
  isLoading
}: {
  teams: TeamSentiment[] | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className='grid grid-cols-2 gap-[var(--space-2)] sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8'>
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className='h-20 rounded-lg' />
        ))}
      </div>
    );
  }

  if (!teams || teams.length === 0) {
    return (
      <Card>
        <CardContent className='flex flex-col items-center justify-center py-[var(--space-8)]'>
          <Icons.shield className='h-[var(--space-6)] w-[var(--space-6)] text-muted-foreground mb-[var(--space-2)]' />
          <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
            No team sentiment data available for this period.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Stagger
      step={0.02}
      className='grid grid-cols-2 gap-[var(--space-2)] sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8'
    >
      {teams.map((team) => {
        const bgClass = getTeamSentimentBg(team.sentiment_label);
        const scoreColor =
          team.sentiment_label === 'positive'
            ? 'text-green-600 dark:text-green-400'
            : team.sentiment_label === 'negative'
              ? 'text-red-600 dark:text-red-400'
              : 'text-yellow-600 dark:text-yellow-400';
        const TrendIcon =
          team.sentiment_label === 'positive'
            ? Icons.trendingUp
            : team.sentiment_label === 'negative'
              ? Icons.trendingDown
              : Icons.minus;

        return (
          <HoverLift key={team.team}>
            <div
              className={`flex flex-col items-center justify-center rounded-lg border p-[var(--space-3)] text-center ${bgClass}`}
            >
              <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-bold'>
                {team.team}
              </span>
              <TrendIcon className={`h-[var(--space-4)] w-[var(--space-4)] mt-[var(--space-1)] ${scoreColor}`} />
              <span
                className={`text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium mt-0.5 capitalize ${scoreColor}`}
              >
                {team.sentiment_label}
              </span>
              <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground mt-0.5'>
                {team.signal_count} signal{team.signal_count !== 1 ? 's' : ''}
              </span>
            </div>
          </HoverLift>
        );
      })}
    </Stagger>
  );
}

// ---------------------------------------------------------------------------
// News card
// ---------------------------------------------------------------------------

function NewsCard({ item }: { item: NewsItem }) {
  // Phase 70-01 (FE-04): suppress the sentiment chip when the article lacks
  // the underlying signal that makes the chip meaningful. Requires BOTH a
  // numeric `sentiment` AND a non-empty `summary` (the LLM-extracted 1-line
  // rationale). Without the summary the number is a "dangling" figure over
  // empty article bodies — the exact bug the 2026-04-20 audit flagged.
  const hasValidSentiment =
    typeof item.sentiment === 'number' &&
    !Number.isNaN(item.sentiment) &&
    typeof item.summary === 'string' &&
    item.summary.trim().length > 0;
  const sentimentClass = hasValidSentiment
    ? getSentimentBadgeClass(item.sentiment)
    : '';
  const sentimentLabel = hasValidSentiment
    ? getSentimentLabel(item.sentiment)
    : '';

  return (
    <HoverLift>
      <Card className='overflow-hidden'>
        <CardContent className='p-[var(--pad-card)] space-y-[var(--space-2)]'>
          {/* Header row: source + timestamp + sentiment */}
          <div className='flex items-center justify-between gap-[var(--space-2)] flex-wrap'>
            <div className='flex items-center gap-[var(--space-2)]'>
              <Badge
                variant='outline'
                className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] shrink-0'
              >
                {formatSource(item.source)}
              </Badge>
              {item.category && (
                <Badge
                  variant='secondary'
                  className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] capitalize shrink-0'
                >
                  {item.category}
                </Badge>
              )}
            </div>
            <div className='flex items-center gap-[var(--space-2)] ml-auto'>
              {hasValidSentiment && (
                <span
                  className={`inline-flex items-center px-[var(--space-2)] py-0.5 rounded-full text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-medium ${sentimentClass}`}
                  title={item.summary ?? undefined}
                >
                  {sentimentLabel}
                </span>
              )}
              {item.published_at && (
                <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground shrink-0'>
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
              className='flex items-start gap-[var(--space-1)] group'
            >
              <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium group-hover:underline line-clamp-3'>
                {item.title ?? 'Untitled'}
              </span>
              <Icons.externalLink className='h-[var(--space-3)] w-[var(--space-3)] mt-0.5 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity' />
            </a>
          ) : (
            <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium line-clamp-3'>
              {item.title ?? item.body_snippet ?? 'Untitled'}
            </p>
          )}

          {/* Body snippet */}
          {item.body_snippet && item.title && (
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground line-clamp-2'>
              {item.body_snippet}
            </p>
          )}

          {/* Player / team info */}
          {(item.player_name || item.team) && (
            <div className='flex items-center gap-[var(--space-2)] pt-[var(--space-1)]'>
              {item.player_name && (
                <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
                  <span className='font-medium text-foreground'>
                    {item.player_name}
                  </span>
                  {item.team ? ` · ${item.team}` : ''}
                </span>
              )}
              {!item.player_name && item.team && (
                <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium text-foreground'>
                  {item.team}
                </span>
              )}
            </div>
          )}

          {/* Event flags (Plan 61-05): render the rule-extractor labels as
              color-coded pills. Falls back to the legacy 5-flag booleans when
              ``event_flags`` is empty (old cached silver records). */}
          <EventBadges
            badges={
              item.event_flags && item.event_flags.length > 0
                ? item.event_flags
                : legacyFlagsToLabels(item)
            }
          />
        </CardContent>
      </Card>
    </HoverLift>
  );
}

function legacyFlagsToLabels(item: NewsItem): string[] {
  const labels: string[] = [];
  if (item.is_ruled_out) labels.push('Ruled Out');
  if (item.is_inactive) labels.push('Inactive');
  if (item.is_suspended) labels.push('Suspended');
  if (item.is_questionable) labels.push('Questionable');
  if (item.is_returning) labels.push('Returning');
  return labels;
}

// ---------------------------------------------------------------------------
// Filter helpers
// ---------------------------------------------------------------------------

function applyClientFilters(
  items: NewsItem[],
  search: string,
  sourceFilter: string
): NewsItem[] {
  let result = items;

  if (sourceFilter !== 'all') {
    result = result.filter((item) =>
      (item.source || '').includes(sourceFilter)
    );
  }

  if (search.trim()) {
    const q = search.trim().toLowerCase();
    result = result.filter(
      (item) =>
        item.player_name?.toLowerCase().includes(q) ||
        item.team?.toLowerCase().includes(q) ||
        item.title?.toLowerCase().includes(q) ||
        item.body_snippet?.toLowerCase().includes(q)
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
 * Comprehensive news and sentiment dashboard.
 *
 * Shows:
 * - Summary statistics (players tracked, bullish/bearish/neutral counts)
 * - Active alerts (ruled out, injury, major sentiment shifts)
 * - Top movers (bullish and bearish players)
 * - Team sentiment grid (all teams at a glance)
 * - Full news feed with source and search filters
 *
 * Auto-refreshes every 5 minutes via TanStack Query.
 */
export function NewsFeed({ season, week }: NewsFeedProps) {
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [page, setPage] = useState(0);

  const effectiveWeek = week ?? 1;
  const offset = page * PAGE_SIZE;

  // Queries
  const {
    data: allItems,
    isLoading: feedLoading,
    isError: feedError,
    dataUpdatedAt: feedUpdatedAt
  } = useQuery(
    newsFeedQueryOptions(
      season,
      week,
      undefined,
      undefined,
      PAGE_SIZE * (page + 2),
      0
    )
  );

  // Phase 70-01: surface the TanStack cache timestamp as a freshness chip.
  // Silent when the query hasn't resolved yet (feedUpdatedAt === 0).
  const dataAsOf: string | null = feedUpdatedAt
    ? new Date(feedUpdatedAt).toISOString()
    : null;

  const { data: summary, isLoading: summaryLoading } = useQuery(
    sentimentSummaryQueryOptions(season, effectiveWeek)
  );

  const { data: alerts, isLoading: alertsLoading } = useQuery(
    alertsQueryOptions(season, effectiveWeek)
  );

  const { data: teamSentiments, isLoading: teamsLoading } = useQuery(
    teamSentimentQueryOptions(season, effectiveWeek)
  );

  const filtered = applyClientFilters(allItems ?? [], search, sourceFilter);
  const visibleItems = filtered.slice(0, offset + PAGE_SIZE);
  const hasMore = filtered.length > visibleItems.length;

  function handleSourceChange(value: string) {
    setSourceFilter(value);
    setPage(0);
  }

  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(0);
  }

  return (
    <FadeIn>
      <Tabs defaultValue='overview' className='space-y-[var(--gap-stack)]'>
        {/* Horizontal scroll on narrow screens so all 4 tabs stay reachable
         *  without squeezing to illegible widths. */}
        <div className='-mx-[var(--space-1)] overflow-x-auto sm:mx-0 sm:overflow-visible'>
          <TabsList className='inline-flex w-max sm:w-auto'>
            <TabsTrigger value='overview'>Overview</TabsTrigger>
            <TabsTrigger value='feed'>News Feed</TabsTrigger>
            <TabsTrigger value='teams'>Team Sentiment</TabsTrigger>
            <TabsTrigger value='players'>Player Signals</TabsTrigger>
          </TabsList>
        </div>

        {/* ================================================================= */}
        {/* Overview tab — dashboard summary                                  */}
        {/* ================================================================= */}
        <TabsContent value='overview' className='space-y-[var(--gap-stack)]'>
          <SentimentSummaryBar summary={summary} isLoading={summaryLoading} />

          <div className='grid grid-cols-1 gap-[var(--gap-stack)] lg:grid-cols-3'>
            <div className='lg:col-span-2'>
              <TopMoversPanel summary={summary} isLoading={summaryLoading} />
            </div>
            <div>
              <AlertsPanel alerts={alerts} isLoading={alertsLoading} />
            </div>
          </div>

          {/* Quick team sentiment preview */}
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
                <Icons.shield className='h-[var(--space-4)] w-[var(--space-4)]' />
                Team Outlook
              </CardTitle>
              <CardDescription>
                Aggregated sentiment by team for Week {effectiveWeek}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <TeamSentimentGrid
                teams={teamSentiments}
                isLoading={teamsLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* ================================================================= */}
        {/* News Feed tab — scrolling list of articles                        */}
        {/* ================================================================= */}
        <TabsContent value='feed' className='space-y-[var(--gap-stack)]'>
          {/* Filter row — mobile: stack (source filter on its own line so all
           *  4 chips stay visible as a horizontally-scrollable pill group;
           *  search on its own line). sm+: flex-wrap. */}
          <div className='flex flex-col gap-[var(--space-3)] sm:flex-row sm:flex-wrap sm:items-center'>
            {/* Source filter — horizontal scroll on narrow screens so all
             *  4 chips stay reachable without forcing vertical stacks. */}
            <div className='-mx-[var(--space-1)] overflow-x-auto sm:mx-0 sm:overflow-visible'>
              <div className='inline-flex items-center gap-[var(--space-1)] rounded-lg border p-[var(--space-1)]'>
                {SOURCE_FILTER_OPTIONS.map(({ value, label }) => (
                  <PressScale key={value}>
                    <button
                      onClick={() => handleSourceChange(value)}
                      className={`min-h-[var(--tap-min)] whitespace-nowrap px-[var(--space-3)] py-[var(--space-2)] rounded-md text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium transition-colors sm:min-h-0 sm:py-[var(--space-1)] ${
                        sourceFilter === value
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                      }`}
                    >
                      {label}
                    </button>
                  </PressScale>
                ))}
              </div>
            </div>

            {/* Search */}
            <div className='relative w-full sm:flex-1 sm:min-w-48'>
              <Icons.search className='absolute left-[var(--space-3)] top-1/2 -translate-y-1/2 h-[var(--space-4)] w-[var(--space-4)] text-muted-foreground pointer-events-none' />
              <Input
                placeholder='Search player, team, or headline...'
                value={search}
                onChange={(e) => handleSearchChange(e.target.value)}
                className='pl-[var(--space-10)] h-[var(--tap-min)] sm:h-9'
              />
            </div>
          </div>

          {/* Feed content */}
          <DataLoadReveal
            loading={feedLoading}
            skeleton={
              <div className='grid grid-cols-1 gap-[var(--space-3)] md:grid-cols-2 lg:grid-cols-3'>
                {Array.from({ length: 6 }).map((_, i) => (
                  <NewsCardSkeleton key={i} />
                ))}
              </div>
            }
          >
            {feedError ? (
              <EmptyState
                icon={Icons.alertCircle}
                title='Unable to load news'
                description='The news service is unavailable right now. Please try again in a moment.'
                dataAsOf={dataAsOf}
              />
            ) : visibleItems.length === 0 ? (
              <EmptyState
                icon={Icons.news}
                title='No news yet this week'
                description={
                  search
                    ? 'Try a different search term or source filter.'
                    : 'News articles are still being aggregated. Check back in a few hours.'
                }
                dataAsOf={dataAsOf}
              />
            ) : (
              <div className='space-y-[var(--gap-stack)]'>
                <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
                  Showing {visibleItems.length} of {filtered.length} articles
                </p>
                <Stagger className='grid grid-cols-1 gap-[var(--space-3)] md:grid-cols-2 lg:grid-cols-3'>
                  {visibleItems.map((item, idx) => (
                    <NewsCard key={item.doc_id ?? idx} item={item} />
                  ))}
                </Stagger>

                {hasMore && (
                  <div className='flex justify-center pt-[var(--space-2)]'>
                    <PressScale>
                      <Button
                        variant='outline'
                        onClick={() => setPage((p) => p + 1)}
                      >
                        Load more
                      </Button>
                    </PressScale>
                  </div>
                )}
              </div>
            )}
          </DataLoadReveal>
        </TabsContent>

        {/* ================================================================= */}
        {/* Team Sentiment tab                                                */}
        {/* ================================================================= */}
        <TabsContent value='teams' className='space-y-[var(--gap-stack)]'>
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-[var(--space-2)]'>
                <Icons.shield className='h-[var(--space-5)] w-[var(--space-5)]' />
                Team Sentiment Overview
              </CardTitle>
              <CardDescription>
                Aggregated sentiment by team for{' '}
                {week ? `Week ${week}` : `${season} Season`}. Derived from player
                news signals and community discussion.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <TeamSentimentGrid
                teams={teamSentiments}
                isLoading={teamsLoading}
              />
            </CardContent>
          </Card>

          {/* Team detail list */}
          {teamSentiments && teamSentiments.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className='text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
                  Team Details
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Stagger step={0.02} className='space-y-[var(--space-1)]'>
                  {teamSentiments.map((team) => {
                    const scoreColor =
                      team.sentiment_label === 'positive'
                        ? 'text-green-600 dark:text-green-400'
                        : team.sentiment_label === 'negative'
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-muted-foreground';
                    return (
                      <div
                        key={team.team}
                        className='flex items-center justify-between py-[var(--space-2)] border-b last:border-b-0'
                      >
                        <div className='flex items-center gap-[var(--space-3)]'>
                          <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-bold w-10'>
                            {team.team}
                          </span>
                          <Badge
                            variant={
                              team.sentiment_label === 'positive'
                                ? 'outline'
                                : team.sentiment_label === 'negative'
                                  ? 'destructive'
                                  : 'secondary'
                            }
                            className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] capitalize'
                          >
                            {team.sentiment_label}
                          </Badge>
                        </div>
                        <div className='flex items-center gap-[var(--space-4)]'>
                          <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
                            {team.signal_count} signal
                            {team.signal_count !== 1 ? 's' : ''}
                          </span>
                          <span
                            className={`text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold tabular-nums ${scoreColor}`}
                          >
                            {team.sentiment_score > 0 ? '+' : ''}
                            {team.sentiment_score.toFixed(2)}
                          </span>
                          <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tabular-nums text-muted-foreground'>
                            {team.sentiment_multiplier.toFixed(2)}x
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </Stagger>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ================================================================= */}
        {/* Player Signals tab — bullish/bearish/neutral per player            */}
        {/* ================================================================= */}
        <TabsContent value='players' className='space-y-[var(--gap-stack)]'>
          <TopMoversPanel summary={summary} isLoading={summaryLoading} />

          <AlertsPanel alerts={alerts} isLoading={alertsLoading} />

          {/* Full player sentiment list from gold data */}
          {summary && (
            <Card>
              <CardHeader>
                <CardTitle className='text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
                  Sentiment Distribution
                </CardTitle>
                <CardDescription>
                  {summary.total_players} players tracked across{' '}
                  {summary.total_docs} documents
                </CardDescription>
              </CardHeader>
              <CardContent>
                {/* Visual bar */}
                <div className='flex h-[var(--space-4)] rounded-full overflow-hidden mb-[var(--space-4)]'>
                  {summary.sentiment_distribution.positive > 0 && (
                    <div
                      className='bg-green-500 dark:bg-green-600'
                      style={{
                        width: `${(summary.sentiment_distribution.positive / summary.total_players) * 100}%`
                      }}
                    />
                  )}
                  {summary.sentiment_distribution.neutral > 0 && (
                    <div
                      className='bg-yellow-400 dark:bg-yellow-600'
                      style={{
                        width: `${(summary.sentiment_distribution.neutral / summary.total_players) * 100}%`
                      }}
                    />
                  )}
                  {summary.sentiment_distribution.negative > 0 && (
                    <div
                      className='bg-red-500 dark:bg-red-600'
                      style={{
                        width: `${(summary.sentiment_distribution.negative / summary.total_players) * 100}%`
                      }}
                    />
                  )}
                </div>
                <div className='flex justify-between text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  <span className='text-green-600 dark:text-green-400'>
                    {summary.sentiment_distribution.positive} Bullish
                  </span>
                  <span className='text-yellow-600 dark:text-yellow-400'>
                    {summary.sentiment_distribution.neutral} Neutral
                  </span>
                  <span className='text-red-600 dark:text-red-400'>
                    {summary.sentiment_distribution.negative} Bearish
                  </span>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </FadeIn>
  );
}
