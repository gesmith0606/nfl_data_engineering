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

export function SectionHeading({
  overline,
  title,
  action,
  className
}: {
  overline?: string;
  title: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex items-end justify-between gap-[var(--space-3)]', className)}>
      <div className='space-y-[var(--space-1)]'>
        {overline ? <SectionOverline>{overline}</SectionOverline> : null}
        <h2 className='wc-display text-[length:var(--fs-h3)] leading-[var(--lh-h3)]'>{title}</h2>
      </div>
      {action ? <div className='shrink-0'>{action}</div> : null}
    </div>
  );
}
