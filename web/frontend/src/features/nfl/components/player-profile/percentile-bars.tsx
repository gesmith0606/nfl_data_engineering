import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { Skeleton } from '@/components/ui/skeleton';
import { ordinal, type PercentileMetric } from './percentile';

export function PercentileBarsSkeleton() {
  return (
    <BroadcastPanel className='space-y-[var(--space-4)] p-[var(--space-4)]'>
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className='space-y-[var(--space-1)]'>
          <Skeleton className='h-[var(--space-3)] w-32' />
          <Skeleton className='h-[var(--space-2)] w-full' />
        </div>
      ))}
    </BroadcastPanel>
  );
}

export interface PercentileBarsProps {
  metrics: PercentileMetric[];
}

/**
 * Opta "premium vs generic" pattern — every bar pairs the raw stat with its
 * percentile so the number always carries context (e.g. "220 ROS pts — 92nd
 * pctile among RBs"). Rendered as horizontal bars, not a radar: a radar only
 * earns its place with a curated gestalt across many axes, and 4-6
 * independent stats read faster stacked as a list than as spokes on a chart
 * most readers can't decode at a glance.
 */
export function PercentileBars({ metrics }: PercentileBarsProps) {
  if (metrics.length === 0) {
    return (
      <BroadcastPanel className='p-[var(--space-4)] text-[length:var(--fs-sm)] text-white/60'>
        Not enough position data yet to compute percentiles for this player.
      </BroadcastPanel>
    );
  }

  return (
    <BroadcastPanel className='space-y-[var(--space-4)] p-[var(--space-4)]'>
      {metrics.map((m) => (
        <div key={m.key}>
          <div className='flex items-baseline justify-between gap-[var(--space-2)]'>
            <span className='wc-display text-[length:var(--fs-xs)] tracking-[0.1em] text-white/60'>
              {m.label}
            </span>
            <span className='font-mono text-[length:var(--fs-sm)] text-white'>
              {m.rawDisplay}
              <span className='ml-[var(--space-2)]' style={{ color: 'var(--wc-mint,#91edd0)' }}>
                {ordinal(m.percentile)} pctile
              </span>
            </span>
          </div>
          <div className='mt-[var(--space-1)] h-2 w-full overflow-hidden rounded-full bg-white/10'>
            <div
              className='h-full rounded-full'
              style={{ width: `${m.percentile}%`, background: 'var(--wc-mint,#91edd0)' }}
            />
          </div>
        </div>
      ))}
    </BroadcastPanel>
  );
}
