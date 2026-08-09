import { useQuery } from '@tanstack/react-query';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { playerNewsQueryOptions } from '../../api/queries';
import type { NewsItem } from '@/lib/nfl/types';
import { SUCCESS_TEXT, WARN_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors';
import { formatRelativeTime } from '@/lib/format-relative-time';
import { DataLoadReveal, Stagger } from '@/lib/motion-primitives';

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

function relativeTime(isoString: string | null): string {
  if (!isoString) return '';
  const out = formatRelativeTime(isoString);
  return out === 'unknown' ? '' : out;
}

function sentimentColorClass(sentiment: number | null): string {
  if (sentiment === null) return 'text-white/50';
  if (sentiment >= 0.2) return SUCCESS_TEXT;
  if (sentiment <= -0.2) return DANGER_TEXT;
  return WARN_TEXT;
}

function sentimentLabel(sentiment: number | null): string {
  if (sentiment === null) return 'neutral';
  if (sentiment >= 0.2) return 'positive';
  if (sentiment <= -0.2) return 'negative';
  return 'neutral';
}

function eventFlags(item: NewsItem): { label: string; variant: 'destructive' | 'secondary' | 'outline' }[] {
  const flags: { label: string; variant: 'destructive' | 'secondary' | 'outline' }[] = [];
  if (item.is_ruled_out) flags.push({ label: 'RULED OUT', variant: 'destructive' });
  if (item.is_inactive) flags.push({ label: 'INACTIVE', variant: 'destructive' });
  if (item.is_suspended) flags.push({ label: 'SUSPENDED', variant: 'destructive' });
  if (item.is_questionable) flags.push({ label: 'QUESTIONABLE', variant: 'secondary' });
  if (item.is_returning) flags.push({ label: 'RETURNING', variant: 'outline' });
  return flags;
}

function NewsRow({ item }: { item: NewsItem }) {
  // Only render the sentiment label when BOTH the numeric sentiment AND the
  // LLM summary are present — otherwise a dangling "neutral" chip shows up
  // over articles with no real sentiment signal (Phase 70-01 fix, ported).
  const hasValidSentiment =
    typeof item.sentiment === 'number' &&
    !Number.isNaN(item.sentiment) &&
    typeof item.summary === 'string' &&
    item.summary.trim().length > 0;
  const flags = eventFlags(item);

  return (
    <div className='flex flex-col gap-[var(--space-1)] border-b border-white/10 py-[var(--space-3)] last:border-b-0'>
      <div className='flex items-start justify-between gap-[var(--space-2)]'>
        <div className='min-w-0 flex-1'>
          {item.url ? (
            <a
              href={item.url}
              target='_blank'
              rel='noopener noreferrer'
              className='line-clamp-2 text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium text-white hover:underline'
            >
              {item.title ?? 'Untitled'}
            </a>
          ) : (
            <p className='line-clamp-2 text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium text-white'>
              {item.title ?? 'Untitled'}
            </p>
          )}
        </div>
        {hasValidSentiment && (
          <span
            className={`shrink-0 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium ${sentimentColorClass(item.sentiment)}`}
            title={item.summary ?? undefined}
          >
            {sentimentLabel(item.sentiment)}
          </span>
        )}
      </div>

      {item.body_snippet && (
        <p className='line-clamp-2 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/50'>
          {item.body_snippet}
        </p>
      )}

      {flags.length > 0 && (
        <div className='mt-[var(--space-1)] flex flex-wrap gap-[var(--space-1)]'>
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
      )}

      <div className='mt-[var(--space-1)] flex items-center gap-[var(--space-2)]'>
        <Badge
          variant='outline'
          className='border-white/20 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-white/60'
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
          <span className='ml-auto text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
            {relativeTime(item.published_at)}
          </span>
        )}
      </div>
    </div>
  );
}

function NewsSkeleton() {
  return (
    <div className='space-y-[var(--space-3)]'>
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className='space-y-[var(--space-2)] border-b border-white/10 py-[var(--space-3)] last:border-b-0'
        >
          <Skeleton className='h-[var(--space-4)] w-3/4 bg-white/10' />
          <Skeleton className='h-[var(--space-3)] w-full bg-white/10' />
          <div className='flex gap-[var(--space-2)]'>
            <Skeleton className='h-[var(--space-5)] w-16 rounded-full bg-white/10' />
            <Skeleton className='h-[var(--space-5)] w-12 rounded-full bg-white/10' />
          </div>
        </div>
      ))}
    </div>
  );
}

export interface PlayerNewsSectionProps {
  playerId: string;
  season: number;
  week: number;
}

/**
 * Recent player news (ported from the retired PlayerDetail page). Neutral
 * (rail-less) BroadcastPanel surface, deliberately distinct from the
 * mint-railed CorrelationsPanel above it — news carries no single
 * positive/negative signal of its own the way a correlation edge does.
 * Same empty-state policy as PercentileBars/CorrelationsPanel: a quiet
 * inline note rather than omitting the section, since preseason and
 * newly-signed players routinely have zero articles.
 */
export function PlayerNewsSection({ playerId, season, week }: PlayerNewsSectionProps) {
  const {
    data: items,
    isLoading,
    isError
  } = useQuery(playerNewsQueryOptions(playerId, season, week, 10));

  return (
    <BroadcastPanel rail={false} className='p-[var(--space-4)]'>
      <h2 className='wc-display mb-[var(--space-2)] text-[length:var(--fs-xs)] tracking-[0.14em] text-white/60'>
        Recent News
      </h2>
      <DataLoadReveal loading={isLoading} skeleton={<NewsSkeleton />}>
        {isError ? (
          <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/50'>
            Unable to load news for this player right now. Please try again in a moment.
          </p>
        ) : !items || items.length === 0 ? (
          <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/50'>
            No news yet this week — articles are still being aggregated. Check back in a few
            hours.
          </p>
        ) : (
          <Stagger>
            {items.map((item, idx) => (
              <NewsRow key={item.doc_id ?? idx} item={item} />
            ))}
          </Stagger>
        )}
      </DataLoadReveal>
    </BroadcastPanel>
  );
}
