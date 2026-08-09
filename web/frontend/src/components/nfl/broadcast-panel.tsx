import * as React from 'react';
import { Icons } from '@/components/icons';
import { HoverLift } from '@/lib/motion-primitives';
import { cn } from '@/lib/utils';

/**
 * Shared broadcast stat-pill surface (sketch 001-B) — near-black
 * `rgba(5,7,13,.85)` background, mint-tinted border, 3px accent left rail.
 * Extracted from three near-identical inline implementations: StatCard
 * (stat-cards.tsx), ProofStrip and PhaseModule's tiles (home-modules.tsx).
 *
 * Polymorphic via `as` so it can render as a plain `<div>` (StatCard),
 * a `<section>` wrapped in a Link (ProofStrip), or a Link itself carrying
 * the panel chrome directly (PhaseModule tiles).
 */
type BroadcastPanelProps<E extends React.ElementType> = {
  as?: E;
  /** Renders the accent left rail. Default true. */
  rail?: boolean;
  /** CSS color/gradient for the rail. Default broadcast mint. */
  railColor?: string;
  /** Extra classes for the rail (e.g. opacity + group-hover for tiles). */
  railClassName?: string;
  /** Panel border color. Default mint-tinted at .35 opacity. */
  borderColor?: string;
} & Omit<
  React.ComponentPropsWithoutRef<E>,
  'as' | 'rail' | 'railColor' | 'railClassName' | 'borderColor'
>;

export function BroadcastPanel<E extends React.ElementType = 'div'>({
  as,
  rail = true,
  railColor = 'var(--wc-mint,#91edd0)',
  railClassName,
  borderColor = 'rgba(145,237,208,0.35)',
  className,
  style,
  children,
  ...rest
}: BroadcastPanelProps<E>) {
  const Component = (as || 'div') as React.ElementType;
  return (
    <Component
      className={cn(
        'relative overflow-hidden rounded-[var(--radius-lg)] border',
        className
      )}
      style={{ background: 'rgba(5,7,13,0.85)', borderColor, ...style }}
      {...rest}
    >
      {rail && (
        <span
          aria-hidden
          className={cn(
            'absolute inset-y-[var(--space-2)] left-0 w-[3px] rounded-full',
            railClassName
          )}
          style={{ background: railColor }}
        />
      )}
      {children}
    </Component>
  );
}

export interface StatPillProps {
  label: React.ReactNode;
  value: React.ReactNode;
  /** Bottom description line (StatCard's `description`). */
  sublabel?: React.ReactNode;
  trend?: string;
  trendDirection?: 'up' | 'down';
  /** Rail + numeral accent color. Default broadcast mint. */
  railColor?: string;
  /** Numeral font-size CSS expression. Default clamp(26px, 3.5vw, 36px). */
  numeralSize?: string;
  /** Wraps the pill in HoverLift (3px rise). Default true. */
  hoverLift?: boolean;
  className?: string;
}

/**
 * Broadcast stat pill — condensed uppercase label + big accent numeral over
 * the shared `BroadcastPanel` surface. This is the StatCard visual recipe,
 * generalized so ProofStrip/PhaseModule-style call sites can reuse the same
 * label/numeral classes even when they don't want the panel + hover lift.
 */
export function StatPill({
  label,
  value,
  sublabel,
  trend,
  trendDirection = 'up',
  railColor = 'var(--wc-mint,#91edd0)',
  numeralSize = 'clamp(26px, 3.5vw, 36px)',
  hoverLift = true,
  className
}: StatPillProps) {
  const TrendIcon = trendDirection === 'up' ? Icons.trendingUp : Icons.trendingDown;

  const panel = (
    <BroadcastPanel
      railColor={railColor}
      className={cn(
        'flex h-full flex-col px-[var(--space-4)] py-[var(--space-4)]',
        className
      )}
    >
      <div
        className='wc-display text-[length:var(--fs-xs)] font-semibold tracking-[0.14em] uppercase'
        style={{ color: 'rgba(207,214,228,0.7)' }}
      >
        {label}
      </div>

      <div
        className='wc-display mt-[var(--space-1)] text-[length:var(--fs-h1)] font-extrabold leading-[var(--lh-h1)] tabular-nums'
        style={{ color: railColor, fontSize: numeralSize }}
      >
        {value}
      </div>

      {trend && (
        <div
          className='mt-[var(--space-1)] inline-flex w-fit items-center gap-[var(--space-1)] rounded-full border px-[var(--space-2)] py-[2px] text-[length:var(--fs-xs)] font-semibold leading-none'
          style={{
            borderColor: 'rgba(145,237,208,0.25)',
            color: 'rgba(145,237,208,0.8)',
            background: 'rgba(145,237,208,0.08)'
          }}
        >
          <TrendIcon className='size-[var(--space-3)]' />
          {trend}
        </div>
      )}

      {sublabel && (
        <div className='mt-auto pt-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
          {sublabel}
        </div>
      )}
    </BroadcastPanel>
  );

  return hoverLift ? (
    <HoverLift lift={3} className='h-full'>
      {panel}
    </HoverLift>
  ) : (
    panel
  );
}
