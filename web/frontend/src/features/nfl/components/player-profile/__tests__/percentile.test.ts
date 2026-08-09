import { describe, it, expect } from 'vitest';
import { computePercentile, median, ordinal, buildPercentileMetrics } from '../percentile';
import type { PlayerProjection, RosPlayer } from '@/lib/nfl/types';

describe('computePercentile', () => {
  it('ranks the max of the pool at 100th percentile', () => {
    expect(computePercentile(25, [8, 14, 20, 25])).toBe(100);
  });

  it('ranks 3rd of 4 (75% at-or-below) as 75th percentile', () => {
    expect(computePercentile(20, [8, 14, 20, 26])).toBe(75);
  });

  it('ranks the min of the pool at its 1/n share, not 0', () => {
    // 1 of 4 values (the value itself) is <= it -> 25%.
    expect(computePercentile(8, [8, 14, 20, 26])).toBe(25);
  });

  it('returns 0 for an empty pool rather than throwing', () => {
    expect(computePercentile(10, [])).toBe(0);
  });
});

describe('median', () => {
  it('averages the two middle values for an even-length array', () => {
    expect(median([10, 20, 30, 40])).toBe(25);
  });

  it('returns the middle value for an odd-length array', () => {
    expect(median([5, 1, 9])).toBe(5);
  });

  it('returns 0 for an empty array', () => {
    expect(median([])).toBe(0);
  });
});

describe('ordinal', () => {
  it('handles the 1st/2nd/3rd special cases', () => {
    expect(ordinal(1)).toBe('1st');
    expect(ordinal(2)).toBe('2nd');
    expect(ordinal(3)).toBe('3rd');
  });

  it('handles the 11th/12th/13th teens exception (not -st/-nd/-rd)', () => {
    expect(ordinal(11)).toBe('11th');
    expect(ordinal(12)).toBe('12th');
    expect(ordinal(13)).toBe('13th');
  });

  it('falls back to -th for everything else, including 92', () => {
    expect(ordinal(4)).toBe('4th');
    expect(ordinal(21)).toBe('21st');
    expect(ordinal(92)).toBe('92nd');
    expect(ordinal(100)).toBe('100th');
  });
});

function rb(overrides: Partial<PlayerProjection>): PlayerProjection {
  return {
    player_id: 'X',
    player_name: 'X',
    team: 'SF',
    position: 'RB',
    projected_points: 0,
    projected_floor: 0,
    projected_ceiling: 0,
    proj_pass_yards: null,
    proj_pass_tds: null,
    proj_rush_yards: null,
    proj_rush_tds: null,
    proj_rec: null,
    proj_rec_yards: null,
    proj_rec_tds: null,
    proj_interceptions: null,
    proj_carries: null,
    proj_targets: null,
    proj_fg_makes: null,
    proj_xp_makes: null,
    scoring_format: 'half_ppr',
    season: 2025,
    week: 3,
    position_rank: null,
    injury_status: null,
    ...overrides
  };
}

function rosPlayer(overrides: Partial<RosPlayer>): RosPlayer {
  return {
    player_id: 'X',
    player_name: 'X',
    team: 'SF',
    position: 'RB',
    ros_points: 0,
    projected_season_points: 0,
    vorp: null,
    position_rank: null,
    ...overrides
  };
}

describe('buildPercentileMetrics', () => {
  const player = rb({
    player_id: 'P1',
    projected_points: 20,
    proj_rush_yards: 85,
    proj_rush_tds: 0.8,
    proj_targets: 3.5,
    proj_rec_yards: 25
  });

  const pool: PlayerProjection[] = [
    rb({ player_id: 'P2', projected_points: 8, proj_rush_yards: 40, proj_rush_tds: 0.2, proj_targets: 1, proj_rec_yards: 5 }),
    rb({ player_id: 'P3', projected_points: 14, proj_rush_yards: 60, proj_rush_tds: 0.5, proj_targets: 2, proj_rec_yards: 15 }),
    player,
    rb({ player_id: 'P4', projected_points: 26, proj_rush_yards: 110, proj_rush_tds: 1.0, proj_targets: 5, proj_rec_yards: 40 })
  ];

  it('includes the weekly-points metric with raw value + percentile', () => {
    const metrics = buildPercentileMetrics(player, pool, { pool: [] });
    const points = metrics.find((m) => m.key === 'weekly_points');
    expect(points).toMatchObject({ rawDisplay: '20.0', percentile: 75 });
  });

  it('includes RB-specific axes (rush yards, rush TDs, targets, rec yards)', () => {
    const metrics = buildPercentileMetrics(player, pool, { pool: [] });
    expect(metrics.map((m) => m.key)).toEqual(
      expect.arrayContaining(['rush_yards', 'rush_tds', 'targets', 'rec_yards'])
    );
  });

  it('skips a metric the player has no data for (e.g. a QB stat on an RB)', () => {
    const metrics = buildPercentileMetrics(player, pool, { pool: [] });
    expect(metrics.find((m) => m.key === 'pass_yards')).toBeUndefined();
  });

  it('adds the ROS Points metric only when a matching ROS entry + pool exist', () => {
    const withoutRos = buildPercentileMetrics(player, pool, { pool: [] });
    expect(withoutRos.find((m) => m.key === 'ros_points')).toBeUndefined();

    const rosPool = [
      rosPlayer({ player_id: 'P2', ros_points: 150 }),
      rosPlayer({ player_id: 'P3', ros_points: 180 }),
      rosPlayer({ player_id: 'P1', ros_points: 220 }),
      rosPlayer({ player_id: 'P4', ros_points: 260 })
    ];
    const withRos = buildPercentileMetrics(player, pool, {
      player: rosPool[2],
      pool: rosPool
    });
    expect(withRos.find((m) => m.key === 'ros_points')).toMatchObject({
      rawDisplay: '220.0',
      percentile: 75
    });
  });

  it('skips every weekly metric when the position pool is too thin to rank against (< 3)', () => {
    const metrics = buildPercentileMetrics(player, pool.slice(0, 2), { pool: [] });
    expect(metrics).toHaveLength(0);
  });

  it('caps at 8 metrics even in principle (RB set is 6, well under the cap)', () => {
    const rosPool = [
      rosPlayer({ player_id: 'P2', ros_points: 150 }),
      rosPlayer({ player_id: 'P3', ros_points: 180 }),
      rosPlayer({ player_id: 'P1', ros_points: 220 }),
      rosPlayer({ player_id: 'P4', ros_points: 260 })
    ];
    const metrics = buildPercentileMetrics(player, pool, { player: rosPool[2], pool: rosPool });
    expect(metrics.length).toBeLessThanOrEqual(8);
    expect(metrics.length).toBe(6);
  });
});
