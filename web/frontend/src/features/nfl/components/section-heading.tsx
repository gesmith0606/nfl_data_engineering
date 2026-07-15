import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * Signature section motif for the surfaces we own (home hub, accuracy proof
 * sections): a short gold rail + a condensed uppercase overline.
 *
 * `--wc-rail-x` / `--wc-gold` fall back to `--primary` / `--chart-1`, so the
 * motif degrades cleanly under the other 10 themes rather than disappearing.
 */

export function SectionOverline({
  children,
  className
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex items-center gap-[var(--space-2)]', className)}>
      <span
        aria-hidden
        className='h-[3px] w-[var(--space-5)] shrink-0 rounded-full'
        style={{ background: 'var(--wc-rail-x, var(--primary))' }}
      />
      <span className='text-[var(--wc-gold,var(--chart-1))] text-[length:var(--fs-xs)] leading-none font-semibold tracking-[0.16em] uppercase'>
        {children}
      </span>
    </div>
  );
}

/**
 * Section heading with optional broadcast mode.
 *
 * `broadcast` — activates the GIQ broadcast identity:
 *   - Overline: vibrant yellow condensed caps, .2em tracking (matches the
 *     marketing home SectionKicker and the hub page header eyebrow).
 *   - Title: white condensed 800 extrabold, .04em tracking.
 *
 * Without `broadcast`, the standard SectionOverline gold-rail motif is used —
 * unchanged for all non-hub pages so other pages are unaffected.
 */
export function SectionHeading({
  overline,
  title,
  action,
  broadcast = false,
  className
}: {
  overline?: string;
  title: string;
  action?: ReactNode;
  broadcast?: boolean;
  className?: string;
}) {
  return (
    <div className={cn('flex items-end justify-between gap-[var(--space-3)]', className)}>
      <div className='space-y-[var(--space-1)]'>
        {overline ? (
          broadcast ? (
            /* Broadcast yellow kicker — vibrant yellow, .2em tracking */
            <div
              className='wc-display text-[length:var(--fs-xs)] font-semibold tracking-[0.2em] uppercase'
              style={{ color: 'var(--wc-yellow,#ffd84d)' }}
            >
              {overline}
            </div>
          ) : (
            <SectionOverline>{overline}</SectionOverline>
          )
        ) : null}
        <h2
          className={cn(
            'wc-display text-[length:var(--fs-h3)] leading-[var(--lh-h3)]',
            broadcast && 'font-extrabold tracking-[0.04em] text-white'
          )}
        >
          {title}
        </h2>
      </div>
      {action ? <div className='shrink-0'>{action}</div> : null}
    </div>
  );
}
