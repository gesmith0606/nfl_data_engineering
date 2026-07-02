'use client';

/**
 * Season Sentiment Pulse — the live, trailing-window view at the top of the
 * News tab. A Day / Week / Month toggle drives two panels:
 *
 *   1. Top Stories — the most important stories in the window, ranked by
 *      |sentiment| × confidence + event weight with recency decay.
 *   2. Sentiment Rankings — players with the most positive (risers) and
 *      most negative (fallers) confidence-weighted average sentiment.
 *
 * Both queries poll every 5 minutes so the section stays live as the daily
 * sentiment pipeline lands new signals.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  sentimentRankingsQueryOptions,
  topStoriesQueryOptions
} from '../api/queries';
import type { SentimentRankingEntry, SentimentWindow, TopStory } from '../api/types';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Icons } from '@/components/icons';
import { EmptyState } from '@/components/EmptyState';
import { formatRelativeTime } from '@/lib/format-relative-time';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { FadeIn, HoverLift, PressScale, Stagger } from '@/lib/motion-primitives';

const WINDOWS: { id: SentimentWindow; label: string }[] = [
  { id: 'day', label: 'Day' },
  { id: 'week', label: 'Week' },
  { id: 'month', label: 'Month' }
];

function sentimentColor(score: number | null): string {
  if (score === null) return 'text-muted-foreground';
  if (score >= 0.1) return 'text-emerald-500';
  if (score <= -0.1) return 'text-red-500';
  return 'text-muted-foreground';
}

function TeamChip({ team }: { team: string | null }) {
  if (!team) return null;
  return (
    <span
      className='inline-flex items-center rounded px-[var(--space-1)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-bold text-white'
      style={{ backgroundColor: getTeamColor(team) }}
    >
      {team}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Top stories
// ---------------------------------------------------------------------------

function StoryRow({ story }: { story: TopStory }) {
  const inner = (
    <div className='flex items-start gap-[var(--space-3)] rounded-lg border border-border/60 bg-card/50 px-[var(--space-3)] py-[var(--space-2)] transition-colors hover:bg-muted/50'>
      {/* Sentiment marker */}
      <div
        className={`mt-0.5 shrink-0 text-[length:var(--fs-lg)] leading-none font-black tabular-nums ${sentimentColor(story.sentiment)}`}
      >
        {story.sentiment === null
          ? '·'
          : story.sentiment >= 0.1
            ? '▲'
            : story.sentiment <= -0.1
              ? '▼'
              : '·'}
      </div>
      <div className='min-w-0 flex-1'>
        <div className='line-clamp-2 text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
          {story.title ?? story.body_snippet ?? 'Untitled'}
        </div>
        <div className='mt-[var(--space-1)] flex flex-wrap items-center gap-[var(--space-2)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground'>
          <span className='uppercase font-medium'>{story.source}</span>
          {story.published_at && <span>{formatRelativeTime(story.published_at)}</span>}
          {story.player_name && <span>{story.player_name}</span>}
          <TeamChip team={story.team} />
          {story.event_flags.map((f) => (
            <Badge
              key={f}
              variant='outline'
              className='h-4 px-[var(--space-1)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
            >
              {f}
            </Badge>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <HoverLift lift={1}>
      {story.url ? (
        <a href={story.url} target='_blank' rel='noopener noreferrer' className='block'>
          {inner}
        </a>
      ) : (
        inner
      )}
    </HoverLift>
  );
}

// ---------------------------------------------------------------------------
// Rankings
// ---------------------------------------------------------------------------

function RankingRow({
  entry,
  rank
}: {
  entry: SentimentRankingEntry;
  rank: number;
}) {
  const positive = entry.avg_sentiment > 0;
  // Bar width scaled to |avg| in [0, 1].
  const width = Math.min(100, Math.round(Math.abs(entry.avg_sentiment) * 100));
  return (
    <div
      className='flex items-center gap-[var(--space-2)] rounded-md px-[var(--space-2)] py-[var(--space-1)] hover:bg-muted/50'
      title={entry.latest_headline ?? undefined}
    >
      <span className='w-4 shrink-0 text-right text-[length:var(--fs-micro)] leading-[var(--lh-micro)] tabular-nums text-muted-foreground'>
        {rank}
      </span>
      <div className='min-w-0 flex-1'>
        <div className='flex items-center gap-[var(--space-2)]'>
          <span className='truncate text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
            {entry.player_name}
          </span>
          <TeamChip team={entry.team} />
          {entry.event_flags.slice(0, 2).map((f) => (
            <Badge
              key={f}
              variant='outline'
              className='h-4 px-[var(--space-1)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
            >
              {f}
            </Badge>
          ))}
        </div>
        <div className='mt-0.5 h-1 w-full overflow-hidden rounded bg-muted'>
          <div
            className={`h-full ${positive ? 'bg-emerald-500' : 'bg-red-500'}`}
            style={{ width: `${width}%` }}
          />
        </div>
      </div>
      <span
        className={`shrink-0 text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-bold tabular-nums ${positive ? 'text-emerald-500' : 'text-red-500'}`}
      >
        {positive ? '+' : ''}
        {entry.avg_sentiment.toFixed(2)}
      </span>
      <span className='w-8 shrink-0 text-right text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground'>
        {entry.doc_count} {entry.doc_count === 1 ? 'doc' : 'docs'}
      </span>
    </div>
  );
}

function RankingsColumn({
  title,
  icon,
  entries,
  empty
}: {
  title: string;
  icon: React.ReactNode;
  entries: SentimentRankingEntry[];
  empty: string;
}) {
  return (
    <div>
      <h4 className='mb-[var(--space-2)] flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold uppercase tracking-widest text-muted-foreground'>
        {icon}
        {title}
      </h4>
      {entries.length === 0 ? (
        <p className='px-[var(--space-2)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
          {empty}
        </p>
      ) : (
        <Stagger step={0.03} className='space-y-[var(--space-1)]'>
          {entries.map((e, i) => (
            <RankingRow key={e.player_id ?? e.player_name} entry={e} rank={i + 1} />
          ))}
        </Stagger>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function SentimentPulse() {
  const [activeWindow, setActiveWindow] = useState<SentimentWindow>('week');

  const { data: stories, isLoading: storiesLoading } = useQuery(
    topStoriesQueryOptions(activeWindow)
  );
  const { data: rankings, isLoading: rankingsLoading } = useQuery(
    sentimentRankingsQueryOptions(activeWindow)
  );

  const asOf = stories?.as_of ?? rankings?.as_of ?? null;

  return (
    <Card>
      <CardHeader>
        <div className='flex flex-wrap items-center justify-between gap-[var(--space-3)]'>
          <div>
            <CardTitle className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
              <Icons.trendingUp className='h-[var(--space-4)] w-[var(--space-4)]' />
              Season Sentiment Pulse
            </CardTitle>
            <CardDescription>
              Live top stories and player sentiment rankings from the news
              feeds — heading into the {new Date().getFullYear()} season.
            </CardDescription>
          </div>
          <div className='flex items-center gap-[var(--space-2)]'>
            {/* Window toggle */}
            <div className='flex rounded-lg bg-muted p-0.5'>
              {WINDOWS.map((w) => (
                <PressScale key={w.id}>
                  <button
                    onClick={() => setActiveWindow(w.id)}
                    className={`rounded-md px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium transition-colors ${
                      activeWindow === w.id
                        ? 'bg-background shadow-sm'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {w.label}
                  </button>
                </PressScale>
              ))}
            </div>
            {asOf && (
              <Badge variant='outline' className='text-muted-foreground'>
                Updated {formatRelativeTime(asOf)}
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className='grid grid-cols-1 gap-[var(--gap-stack)] lg:grid-cols-2'>
          {/* Top stories */}
          <div>
            <h4 className='mb-[var(--space-2)] flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold uppercase tracking-widest text-muted-foreground'>
              <Icons.news className='h-[var(--space-3)] w-[var(--space-3)]' />
              Top Stories — past {activeWindow}
            </h4>
            {storiesLoading ? (
              <div className='space-y-[var(--space-2)]'>
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className='h-14 w-full rounded-lg' />
                ))}
              </div>
            ) : !stories || stories.stories.length === 0 ? (
              <EmptyState
                icon={Icons.news}
                title='No stories in this window'
                description='Try a wider window — the pipeline ingests new stories daily.'
              />
            ) : (
              <FadeIn key={activeWindow} className='space-y-[var(--space-2)]'>
                {stories.stories.map((s) => (
                  <StoryRow key={s.doc_id ?? s.title} story={s} />
                ))}
              </FadeIn>
            )}
          </div>

          {/* Rankings */}
          <div className='space-y-[var(--gap-stack)]'>
            {rankingsLoading ? (
              <div className='space-y-[var(--space-2)]'>
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className='h-8 w-full rounded-md' />
                ))}
              </div>
            ) : (
              <>
                <RankingsColumn
                  title={`Sentiment Risers — past ${activeWindow}`}
                  icon={
                    <Icons.trendingUp className='h-[var(--space-3)] w-[var(--space-3)] text-emerald-500' />
                  }
                  entries={rankings?.risers ?? []}
                  empty='No positive player signals in this window.'
                />
                <RankingsColumn
                  title={`Sentiment Fallers — past ${activeWindow}`}
                  icon={
                    <Icons.trendingDown className='h-[var(--space-3)] w-[var(--space-3)] text-red-500' />
                  }
                  entries={rankings?.fallers ?? []}
                  empty='No negative player signals in this window.'
                />
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
