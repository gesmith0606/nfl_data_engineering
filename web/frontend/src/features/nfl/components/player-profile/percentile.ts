import type { PlayerProjection, RosPlayer } from '@/lib/nfl/types';

/**
 * Percentile math for the player profile's percentile-bar section (Opta
 * "raw value + percentile together" pattern — the research finding is that
 * a bare percentile with no raw number is opaque, and a bare raw number with
 * no percentile has no context; showing both is the premium lever). Pure and
 * framework-free so it's directly unit-testable.
 */

/**
 * Percentile rank of `value` within `pool` (0-100, rounded to the nearest
 * whole number). Percentile = the share of the pool at or below `value` —
 * the standard "beats N% of the position" reading. Include the player's own
 * value in `pool` for a self-consistent read (their own row counts toward
 * "at or below").
 */
export function computePercentile(value: number, pool: number[]): number {
  if (pool.length === 0) return 0;
  const atOrBelow = pool.filter((v) => v <= value).length;
  return Math.round((atOrBelow / pool.length) * 100);
}

/** Median of a numeric array. Returns 0 for an empty array. */
export function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

/** Ordinal suffix for a percentile display ("92nd", "11th", "3rd"). */
export function ordinal(n: number): string {
  const rem100 = n % 100;
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

export interface PercentileMetric {
  key: string;
  label: string;
  rawDisplay: string;
  percentile: number;
}

interface WeeklyStatDef {
  key: string;
  label: string;
  decimals: number;
  get: (p: PlayerProjection) => number | null;
}

const WEEKLY_POINTS: WeeklyStatDef = {
  key: 'weekly_points',
  label: 'Weekly Fantasy Points',
  decimals: 1,
  get: (p) => p.projected_points
};

/**
 * Position-specific stat axes, deliberately picked to be DECORRELATED:
 * one volume stat, one scoring-rate stat, one opportunity-share stat where
 * the position has one — never two stats that just restate the same thing
 * (e.g. both `proj_rec` and `proj_targets`, which move together almost 1:1).
 * `WEEKLY_POINTS` is prepended to every position, so a QB tops out at 5
 * metrics and an RB at 6 — under the 5-8 cap without padding it out with
 * redundant axes just to hit a number.
 */
const POSITION_WEEKLY_STATS: Record<string, WeeklyStatDef[]> = {
  QB: [
    { key: 'pass_yards', label: 'Pass Yards', decimals: 0, get: (p) => p.proj_pass_yards },
    { key: 'pass_tds', label: 'Pass TDs', decimals: 1, get: (p) => p.proj_pass_tds },
    { key: 'rush_yards', label: 'Rush Yards', decimals: 0, get: (p) => p.proj_rush_yards }
  ],
  RB: [
    { key: 'rush_yards', label: 'Rush Yards', decimals: 0, get: (p) => p.proj_rush_yards },
    { key: 'rush_tds', label: 'Rush TDs', decimals: 1, get: (p) => p.proj_rush_tds },
    { key: 'targets', label: 'Targets', decimals: 1, get: (p) => p.proj_targets },
    { key: 'rec_yards', label: 'Receiving Yards', decimals: 0, get: (p) => p.proj_rec_yards }
  ],
  WR: [
    { key: 'targets', label: 'Targets', decimals: 1, get: (p) => p.proj_targets },
    { key: 'rec_yards', label: 'Receiving Yards', decimals: 0, get: (p) => p.proj_rec_yards },
    { key: 'rec_tds', label: 'Receiving TDs', decimals: 1, get: (p) => p.proj_rec_tds }
  ],
  TE: [
    { key: 'targets', label: 'Targets', decimals: 1, get: (p) => p.proj_targets },
    { key: 'rec_yards', label: 'Receiving Yards', decimals: 0, get: (p) => p.proj_rec_yards },
    { key: 'rec_tds', label: 'Receiving TDs', decimals: 1, get: (p) => p.proj_rec_tds }
  ],
  K: [
    { key: 'fg_makes', label: 'Field Goals', decimals: 1, get: (p) => p.proj_fg_makes },
    { key: 'xp_makes', label: 'Extra Points', decimals: 1, get: (p) => p.proj_xp_makes }
  ]
};

/** Minimum pool size before a percentile is considered meaningful. */
const MIN_POOL_SIZE = 3;

/**
 * Build the percentile-bar metrics for one player: this week's position
 * pool (from `/api/projections`) for the weekly stat axes, plus one
 * rest-of-season axis (`ros_points`, from `/api/tools/ros`) when a matching
 * ROS entry and pool are available. Any metric the player's own data can't
 * support (null value) or whose pool is too thin to rank against
 * (< MIN_POOL_SIZE) is skipped rather than shown as a fake/zero percentile.
 */
export function buildPercentileMetrics(
  player: PlayerProjection,
  weeklyPositionPool: PlayerProjection[],
  ros: { player?: RosPlayer; pool: RosPlayer[] }
): PercentileMetric[] {
  const defs = [WEEKLY_POINTS, ...(POSITION_WEEKLY_STATS[player.position] ?? [])];
  const metrics: PercentileMetric[] = [];

  for (const def of defs) {
    const raw = def.get(player);
    if (raw == null) continue;
    const pool = weeklyPositionPool
      .map(def.get)
      .filter((v): v is number => v != null);
    if (pool.length < MIN_POOL_SIZE) continue;
    metrics.push({
      key: def.key,
      label: def.label,
      rawDisplay: raw.toFixed(def.decimals),
      percentile: computePercentile(raw, pool)
    });
  }

  if (ros.player && ros.pool.length >= MIN_POOL_SIZE) {
    const rosPool = ros.pool.map((p) => p.ros_points);
    metrics.push({
      key: 'ros_points',
      label: 'ROS Points',
      rawDisplay: ros.player.ros_points.toFixed(1),
      percentile: computePercentile(ros.player.ros_points, rosPool)
    });
  }

  return metrics.slice(0, 8);
}
