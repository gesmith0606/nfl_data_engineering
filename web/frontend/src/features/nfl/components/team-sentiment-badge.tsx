'use client';

import { useQuery } from '@tanstack/react-query';
import { teamSentimentQueryOptions } from '../api/queries';
import type { TeamSentiment } from '../api/types';

// ---------------------------------------------------------------------------
// Sentiment color helpers
// ---------------------------------------------------------------------------

function sentimentDotClass(label: TeamSentiment['sentiment_label']): string {
  switch (label) {
    case 'positive':
      return 'bg-green-500';
    case 'negative':
      return 'bg-red-500';
    default:
      return 'bg-yellow-500';
  }
}

function sentimentTextClass(label: TeamSentiment['sentiment_label']): string {
  switch (label) {
    case 'positive':
      return 'text-green-600 dark:text-green-400';
    case 'negative':
      return 'text-red-600 dark:text-red-400';
    default:
      return 'text-yellow-600 dark:text-yellow-400';
  }
}

function sentimentSymbol(label: TeamSentiment['sentiment_label']): string {
  switch (label) {
    case 'positive':
      return '+';
    case 'negative':
      return '-';
    default:
      return '~';
  }
}

// ---------------------------------------------------------------------------
// Inline badge (no network call — accepts pre-fetched data)
// ---------------------------------------------------------------------------

interface TeamSentimentInlineProps {
  sentiment: TeamSentiment;
}

export function TeamSentimentInline({ sentiment }: TeamSentimentInlineProps) {
  const dotClass = sentimentDotClass(sentiment.sentiment_label);
  const textClass = sentimentTextClass(sentiment.sentiment_label);
  const symbol = sentimentSymbol(sentiment.sentiment_label);
  const tooltip = `${sentiment.team} sentiment: ${sentiment.sentiment_label} (${sentiment.signal_count} signal${sentiment.signal_count !== 1 ? 's' : ''})`;

  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-medium ${textClass}`}
      title={tooltip}
    >
      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${dotClass}`} />
      {symbol}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Connected badge — fetches team sentiment from the API
// ---------------------------------------------------------------------------

interface TeamSentimentBadgeProps {
  team: string;
  season: number;
  week: number;
}

/**
 * Displays a compact sentiment indicator for a single team.
 *
 * Fetches team sentiment data from /api/news/team-sentiment and renders
 * a colored dot + symbol next to the team abbreviation. Renders nothing
 * when no sentiment data is available for the team.
 */
export function TeamSentimentBadge({ team, season, week }: TeamSentimentBadgeProps) {
  const { data: sentimentList } = useQuery({
    ...teamSentimentQueryOptions(season, week),
    // Don't show loading state — badge is supplementary info
    staleTime: 5 * 60 * 1000
  });

  const teamSentiment = sentimentList?.find((s) => s.team === team);
  if (!teamSentiment) return null;

  return <TeamSentimentInline sentiment={teamSentiment} />;
}
