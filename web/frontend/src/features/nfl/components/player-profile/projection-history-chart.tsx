'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import type { TooltipProps } from 'recharts';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { Skeleton } from '@/components/ui/skeleton';
import { playerProjectionHistoryQueryOptions } from '../../api/queries';
import type { PlayerProjectionHistoryWeek, ScoringFormat } from '@/lib/nfl/types';

const MINT = 'var(--wc-mint,#91edd0)';
const ACTUAL_BAR = 'rgba(255,255,255,0.6)';
const BAND_FILL = 'rgba(145,237,208,0.16)';

interface ChartRow {
  week: number;
  actual: number | null;
  projected: number | null;
  band: [number, number] | undefined;
}

function buildRows(weeks: PlayerProjectionHistoryWeek[]): ChartRow[] {
  return weeks
    .slice()
    .sort((a, b) => a.week - b.week)
    .map((w) => ({
      week: w.week,
      actual: w.actual_points,
      projected: w.projected_points,
      band:
        w.projected_floor != null && w.projected_ceiling != null
          ? [w.projected_floor, w.projected_ceiling]
          : undefined
    }));
}

export function ProjectionHistoryChartSkeleton() {
  return (
    <BroadcastPanel className='p-[var(--space-4)]'>
      <Skeleton className='h-[var(--space-3)] w-48' />
      <Skeleton className='mt-[var(--space-3)] h-[220px] w-full' />
    </BroadcastPanel>
  );
}

/** Right-aligned numeric tooltip — dark surface matching the broadcast panel it sits over. */
function ProjectionTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0]?.payload as ChartRow | undefined;
  if (!row) return null;

  return (
    <div
      className='min-w-[140px] rounded-[var(--radius-md)] border px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--fs-xs)]'
      style={{ background: 'rgba(5,7,13,0.95)', borderColor: 'rgba(145,237,208,0.35)' }}
    >
      <div className='wc-display mb-[var(--space-1)] tracking-[0.08em] text-white/60'>
        Week {label}
      </div>
      {row.actual != null && (
        <div className='flex items-center justify-between gap-[var(--space-3)]'>
          <span className='text-white/60'>Actual</span>
          <span className='text-right font-mono text-white'>{row.actual.toFixed(1)}</span>
        </div>
      )}
      {row.projected != null && (
        <div className='flex items-center justify-between gap-[var(--space-3)]'>
          <span className='text-white/60'>Projected</span>
          <span className='text-right font-mono' style={{ color: MINT }}>
            {row.projected.toFixed(1)}
          </span>
        </div>
      )}
      {row.band && (
        <div className='flex items-center justify-between gap-[var(--space-3)]'>
          <span className='text-white/60'>Floor–Ceiling</span>
          <span className='text-right font-mono text-white/50'>
            {row.band[0].toFixed(1)}–{row.band[1].toFixed(1)}
          </span>
        </div>
      )}
    </div>
  );
}

/** Inline labeled swatches — never color-alone, since Actual/Projected also differ in mark shape (bar vs line). */
function ChartLegend({ showActual, showBand }: { showActual: boolean; showBand: boolean }) {
  return (
    <div className='flex flex-wrap items-center gap-[var(--space-4)] text-[length:var(--fs-xs)] text-white/60'>
      {showActual && (
        <span className='inline-flex items-center gap-[var(--space-1)]'>
          <span className='inline-block h-2 w-3 rounded-[2px]' style={{ background: ACTUAL_BAR }} />
          Actual
        </span>
      )}
      <span className='inline-flex items-center gap-[var(--space-1)]'>
        <span className='inline-block h-[2px] w-3 rounded-full' style={{ background: MINT }} />
        Projected
      </span>
      {showBand && (
        <span className='inline-flex items-center gap-[var(--space-1)]'>
          <span className='inline-block h-2 w-3 rounded-[2px]' style={{ background: BAND_FILL }} />
          Floor–Ceiling
        </span>
      )}
    </div>
  );
}

export interface ProjectionHistoryChartProps {
  playerId: string;
  season: number;
  scoring: ScoringFormat;
}

/**
 * Projected-vs-actual overlay for a player-season: actual points as bars,
 * the projected line + floor/ceiling band drawn over them. Honest by
 * construction about two real gaps in the backing data:
 *
 * - `weeks` can come back empty for a season with no archived Gold
 *   projections or Bronze actuals at all — shown as the server's `reason`
 *   (or a quiet generic note when `reason` is absent).
 * - On the production backend `actual_points` is currently `null` for every
 *   week (a data-gap fix pending server-side) — rather than render a chart
 *   full of zero-height bars, the bar series is omitted entirely and a
 *   one-line note explains why. The projected line + band still carry the
 *   chart's value in that state.
 */
export function ProjectionHistoryChart({ playerId, season, scoring }: ProjectionHistoryChartProps) {
  const { data, isLoading } = useQuery(
    playerProjectionHistoryQueryOptions(playerId, season, scoring)
  );

  const rows = useMemo(() => buildRows(data?.weeks ?? []), [data]);
  const hasAnyActual = rows.some((r) => r.actual != null);
  const hasAnyProjected = rows.some((r) => r.projected != null);
  const hasAnyBand = rows.some((r) => r.band != null);

  if (isLoading) return <ProjectionHistoryChartSkeleton />;

  return (
    <BroadcastPanel className='p-[var(--space-4)]'>
      <div className='flex flex-wrap items-baseline justify-between gap-[var(--space-2)]'>
        <h2 className='wc-display text-[length:var(--fs-xs)] tracking-[0.14em] text-white/60'>
          Projected vs. Actual — {season}
        </h2>
        {rows.length > 0 && <ChartLegend showActual={hasAnyActual} showBand={hasAnyBand} />}
      </div>

      {rows.length === 0 ? (
        <p className='mt-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/50'>
          {data?.reason ?? 'No projection history recorded for this player-season yet.'}
        </p>
      ) : (
        <>
          <div className='mt-[var(--space-3)] h-[240px] w-full'>
            <ResponsiveContainer width='100%' height='100%'>
              <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke='rgba(255,255,255,0.08)' />
                <XAxis
                  dataKey='week'
                  tickLine={false}
                  axisLine={{ stroke: 'rgba(255,255,255,0.15)' }}
                  tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 11 }}
                  tickFormatter={(w: number) => `Wk ${w}`}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 11 }}
                  width={32}
                />
                <Tooltip content={<ProjectionTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                {hasAnyBand && (
                  <Area
                    dataKey='band'
                    stroke='none'
                    fill={BAND_FILL}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                )}
                {hasAnyActual && (
                  <Bar dataKey='actual' fill={ACTUAL_BAR} radius={[2, 2, 0, 0]} maxBarSize={28} />
                )}
                {hasAnyProjected && (
                  <Line
                    dataKey='projected'
                    stroke={MINT}
                    strokeWidth={2}
                    dot={{ r: 3, fill: MINT, strokeWidth: 0 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                    isAnimationActive={false}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {!hasAnyActual && (
            <p className='mt-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/40'>
              Actuals unavailable — projections only.
            </p>
          )}
        </>
      )}
    </BroadcastPanel>
  );
}
