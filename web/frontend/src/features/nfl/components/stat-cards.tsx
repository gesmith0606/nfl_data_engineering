'use client';

import { StatPill } from '@/components/nfl/broadcast-panel';
import { Stagger } from '@/lib/motion-primitives';
import modelMetrics from '../config/model-metrics.json';

export function OverviewStatCards() {
  return (
    <Stagger
      step={0.05}
      className='grid grid-cols-1 gap-[var(--gap-stack)] md:grid-cols-2 lg:grid-cols-4'
    >
      <StatPill
        label='Projection MAE'
        value={modelMetrics.overall.mae.toFixed(2)}
        sublabel={`Fantasy points mean absolute error (${modelMetrics.overall.seasons} backtest)`}
        trend='-3.0% in v4.2'
        trendDirection='down'
        railColor='var(--wc-gold,#ffd84d)'
      />
      <StatPill
        label='Tests Passing'
        value={modelMetrics.testsPassing.toLocaleString()}
        sublabel='Full test suite coverage'
        trend='100%'
        trendDirection='up'
        railColor='var(--wc-cyan,#22d3ee)'
      />
      <StatPill
        label='ATS Accuracy'
        value={`${modelMetrics.atsAccuracy.value.toFixed(1)}%`}
        sublabel='Against the spread (sealed 2024 holdout)'
        trend='+3.0%'
        trendDirection='up'
        railColor='var(--wc-peri,#5b67c7)'
      />
      <StatPill
        label='Players Tracked'
        value='569'
        sublabel='Across all NFL positions'
        railColor='var(--wc-mint,#91edd0)'
      />
    </Stagger>
  );
}
