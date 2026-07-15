'use client';

import { Icons } from '@/components/icons';
import { Stagger, HoverLift } from '@/lib/motion-primitives';
import modelMetrics from '../config/model-metrics.json';

interface StatCardProps {
  title: string;
  value: string;
  description: string;
  trend?: string;
  trendDirection?: 'up' | 'down';
  /**
   * CSS color expression for the left rail and numeral accent.
   * Pass a wc token with a chart fallback so the card stays on-brand
   * in worldcup26 and degrades cleanly under other themes.
   */
  accent: string;
}

/**
 * Broadcast stat pill — near-black `rgba(5,7,13,.85)` background, mint-
 * tinted border (matches the `.b-stat` pattern from broadcast.css / sketch
 * 001-B), condensed 800 numeral in the accent color, condensed uppercase
 * label. Hover lifts 3px via HoverLift.
 */
function StatCard({
  title,
  value,
  description,
  trend,
  trendDirection = 'up',
  accent
}: StatCardProps) {
  const TrendIcon = trendDirection === 'up' ? Icons.trendingUp : Icons.trendingDown;

  return (
    <HoverLift lift={3} className='h-full'>
      <div
        className='relative flex h-full flex-col overflow-hidden rounded-[var(--radius-lg)] border px-[var(--space-4)] py-[var(--space-4)]'
        style={{
          background: 'rgba(5,7,13,0.85)',
          borderColor: 'rgba(145,237,208,0.35)'
        }}
      >
        {/* Accent left rail */}
        <div
          aria-hidden
          className='absolute inset-y-[var(--space-2)] left-0 w-[3px] rounded-full'
          style={{ background: accent }}
        />

        {/* Condensed uppercase label */}
        <div
          className='wc-display text-[length:var(--fs-xs)] font-semibold tracking-[0.14em] uppercase'
          style={{ color: 'rgba(207,214,228,0.7)' }}
        >
          {title}
        </div>

        {/* Large condensed 800 numeral */}
        <div
          className='wc-display mt-[var(--space-1)] text-[length:var(--fs-h1)] font-extrabold leading-[var(--lh-h1)] tabular-nums'
          style={{ color: accent, fontSize: 'clamp(26px, 3.5vw, 36px)' }}
        >
          {value}
        </div>

        {/* Trend badge */}
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

        {/* Description */}
        <div className='mt-auto pt-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
          {description}
        </div>
      </div>
    </HoverLift>
  );
}

export function OverviewStatCards() {
  return (
    <Stagger
      step={0.05}
      className='grid grid-cols-1 gap-[var(--gap-stack)] md:grid-cols-2 lg:grid-cols-4'
    >
      <StatCard
        title='Projection MAE'
        value={modelMetrics.overall.mae.toFixed(2)}
        description={`Fantasy points mean absolute error (${modelMetrics.overall.seasons} backtest)`}
        trend='-3.0% in v4.2'
        trendDirection='down'
        accent='var(--wc-gold,#ffd84d)'
      />
      <StatCard
        title='Tests Passing'
        value={modelMetrics.testsPassing.toLocaleString()}
        description='Full test suite coverage'
        trend='100%'
        trendDirection='up'
        accent='var(--wc-cyan,#22d3ee)'
      />
      <StatCard
        title='ATS Accuracy'
        value={`${modelMetrics.atsAccuracy.value.toFixed(1)}%`}
        description='Against the spread (sealed 2024 holdout)'
        trend='+3.0%'
        trendDirection='up'
        accent='var(--wc-peri,#5b67c7)'
      />
      <StatCard
        title='Players Tracked'
        value='569'
        description='Across all NFL positions'
        accent='var(--wc-mint,#91edd0)'
      />
    </Stagger>
  );
}
