'use client';

import { useQuery } from '@tanstack/react-query';
import { teamSentimentQueryOptions } from '../api/queries';
import { SUCCESS_TEXT, WARN_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors';
import type { TeamSentiment } from '../api/types';

// ---------------------------------------------------------------------------
// Sentiment color helpers
// ---------------------------------------------------------------------------

function sentimentDotClass(label: TeamSentiment['sentiment_label']): string {
  switch (label) {
    case 'positive':
      return 'bg-[var(--success)]';
    case 'negative':
      return 'bg-[var(--danger)]';
    default:
      return 'bg-[var(--warn)]';
  }
}

function sentimentTextClass(label: TeamSentiment['sentiment_label']): string {
  switch (label) {
    case 'positive':
      return SUCCESS_TEXT;
    case 'negative':
      return DANGER_TEXT;
    default:
      return WARN_TEXT;
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
      className={`inline-flex items-center gap-0.5 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium transition-colors duration-[var(--motion-base)] ${textClass}`}
      title={tooltip}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full shrink-0 transition-colors duration-[var(--motion-base)] ${dotClass}`}
      />
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
