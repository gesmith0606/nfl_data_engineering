'use client';

import type { OverallSentimentLabel } from '../api/types';
import { Badge } from '@/components/ui/badge';

/**
 * Reusable pill badges rendering rule-extracted event flags (NEWS-04).
 *
 * Each label is mapped to a bullish / bearish / neutral color class using
 * the same bucket rules the backend uses in ``news_service.py`` (D-03 —
 * discrete buckets, NOT a continuous score).
 *
 * Renders ``null`` when ``badges`` is empty so consumers can drop it into
 * layouts without guarding against an empty wrapper.
 */

// ---------------------------------------------------------------------------
// Bucket assignment — mirrors news_service.NEGATIVE/POSITIVE/NEUTRAL_FLAGS
// ---------------------------------------------------------------------------

type BadgeBucket = 'bearish' | 'bullish' | 'neutral';

const BEARISH_LABELS: ReadonlySet<string> = new Set([
  'Ruled Out',
  'Inactive',
  'Suspended',
  'Usage Drop',
  'Weather Risk',
  'Released',
  // Phase 72: cap cuts and holdouts are bearish.
  'Cap Cut',
  'Holdout'
]);

const BULLISH_LABELS: ReadonlySet<string> = new Set([
  'Returning',
  'Activated',
  'Usage Boost',
  'Signed',
  // Phase 72: drafted + rookie buzz lean bullish.
  'Drafted',
  'Rookie Buzz'
]);

const NEUTRAL_LABELS: ReadonlySet<string> = new Set([
  'Traded',
  'Questionable',
  // Phase 72: rumored destinations + trade buzz + coaching changes are
  // informational — not directional fantasy signals.
  'Rumored Destination',
  'Trade Buzz',
  'Coaching Change'
]);

function bucketForBadge(label: string): BadgeBucket {
  if (BEARISH_LABELS.has(label)) return 'bearish';
  if (BULLISH_LABELS.has(label)) return 'bullish';
  if (NEUTRAL_LABELS.has(label)) return 'neutral';
  // Unknown labels default to neutral so future additions don't break the UI.
  return 'neutral';
}

// ---------------------------------------------------------------------------
// Color classes — Tailwind utility pairs for light + dark mode
// ---------------------------------------------------------------------------

const BUCKET_CLASSES: Record<BadgeBucket, string> = {
  bearish: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  bullish:
    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  neutral:
    'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
};

const OVERALL_RING_CLASSES: Record<OverallSentimentLabel, string> = {
  bearish: 'ring-red-300 dark:ring-red-700',
  bullish: 'ring-green-300 dark:ring-green-700',
  neutral: 'ring-yellow-300 dark:ring-yellow-700'
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface EventBadgesProps {
  /** Human-readable event labels (e.g. ``['Questionable', 'Returning']``). */
  badges: string[];
  /**
   * Optional overall bucket — when provided, the container carries a
   * subtle colored ring so glanceability is preserved even when the badge
   * list has mixed colors.
   */
  overallLabel?: OverallSentimentLabel;
  /** Optional wrapper className for layout integration. */
  className?: string;
}

/**
 * Render deduplicated event pills with color-coded buckets.
 *
 * Contract:
 * - Returns ``null`` when ``badges`` is empty (no empty wrapper rendered).
 * - Each badge renders as a ``<Badge>`` using the shadcn primitive.
 * - Color derives from the label's bucket, not the surrounding overall
 *   label — so one bullish + one bearish badge still renders distinctly.
 */
export function EventBadges({
  badges,
  overallLabel,
  className
}: EventBadgesProps) {
  if (!badges || badges.length === 0) return null;

  const ringClass = overallLabel ? OVERALL_RING_CLASSES[overallLabel] : '';
  const wrapperClass = [
    'flex flex-wrap gap-1',
    overallLabel ? `ring-1 rounded-md p-1 ${ringClass}` : '',
    className ?? ''
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={wrapperClass} role='list' aria-label='Event badges'>
      {badges.map((label) => {
        const bucket = bucketForBadge(label);
        return (
          <Badge
            key={label}
            variant='outline'
            role='listitem'
            className={`text-xs font-medium border-transparent ${BUCKET_CLASSES[bucket]}`}
          >
            {label}
          </Badge>
        );
      })}
    </div>
  );
}
