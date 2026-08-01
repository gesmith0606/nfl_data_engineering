import { Skeleton } from '@/components/ui/skeleton';

/**
 * Generic page-level Suspense fallback (P1 remediation, 2026-08-01 audit).
 *
 * The dashboard/games, rankings, players, lineups, and matchups routes
 * wrapped their feature component in a bare `<Suspense>` with no `fallback`
 * — while the Suspense boundary was pending (even briefly, or indefinitely
 * under the audited production incident) the route showed nothing at all
 * below the header. Every route now passes a real fallback so a pending
 * boundary always reads as "loading" rather than a blank void.
 *
 * Intentionally generic (filter-row + content blocks) rather than bespoke
 * per route — the feature components already render their own precise
 * skeletons once mounted (GameCardSkeleton, MatchupSkeleton, etc.); this
 * only covers the brief/degenerate window before that.
 */
export function RouteSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className='space-y-[var(--gap-stack)]'>
      <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
        <Skeleton className='h-9 w-28' />
        <Skeleton className='h-9 w-24' />
      </div>
      <div className='space-y-[var(--space-2)]'>
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className='h-24 w-full rounded-lg' />
        ))}
      </div>
    </div>
  );
}
