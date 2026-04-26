import { formatDistanceToNow } from 'date-fns';

/**
 * Format a timestamp relative to now using date-fns.
 *
 * Rules:
 * - Invalid input → "unknown" (never throws)
 * - < 60s old → "just now"
 * - < 7 days old → relative ("2 hours ago", "3 days ago")
 * - >= 7 days old → absolute date ("Apr 14, 2026")
 *
 * The < 7 day / absolute threshold matches the Phase 63 `data_as_of`
 * freshness pattern — older timestamps are less useful as "X days ago" and
 * more useful as a calendar date.
 *
 * Phase 70-01: introduced as the single source of truth for freshness-chip
 * formatting across the EmptyState card and the 4 page headers
 * (predictions, lineups, matchups, news).
 */
export function formatRelativeTime(input: string | Date | null | undefined): string {
  // TD-05 (Phase 75): empty / null / undefined input → 'unknown' (no
  // "Updated unknown" rendering downstream — callers can null-check the
  // bare 'unknown' return).
  if (input == null) return 'unknown';
  if (typeof input === 'string' && input.trim() === '') return 'unknown';

  const then =
    typeof input === 'string' ? Date.parse(input) : input.getTime();
  if (Number.isNaN(then)) return 'unknown';

  const now = Date.now();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

  if (diffSec < 60) return 'just now';

  if (diffMs < SEVEN_DAYS_MS) {
    // date-fns returns e.g. "about 2 hours", "3 days" — append "ago" once.
    return `${formatDistanceToNow(new Date(then))} ago`;
  }

  const d = new Date(then);
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
}
