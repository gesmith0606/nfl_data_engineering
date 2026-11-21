import { describe, expect, it } from 'vitest';
import { projectionToolStatus } from '../projection-status';

describe('projectionToolStatus', () => {
  it('turns an unpublished week into an unavailable tool result', () => {
    const s = projectionToolStatus(
      { available: false, message: 'Week 12 publishes Tuesday', latest_available_week: 11 },
      12,
      2026
    );
    expect(s.unavailable).toBe(true);
    if (s.unavailable) {
      expect(s.result.found).toBe(false);
      expect(s.result.available).toBe(false);
      expect(s.result.latest_available_week).toBe(11);
      expect(String(s.result.message)).toContain('Do NOT estimate');
    }
  });

  it('flags season totals explicitly', () => {
    const s = projectionToolStatus({ available: true, is_season_total: true }, 1, 2026);
    expect(s.unavailable).toBe(false);
    if (!s.unavailable) {
      expect(s.extra.is_season_total).toBe(true);
      expect(String(s.extra.warning)).toContain('SEASON TOTALS');
    }
  });

  it('adds nothing for a normal weekly board', () => {
    const s = projectionToolStatus({ available: true }, 5, 2026);
    expect(s).toEqual({ unavailable: false, extra: {} });
  });
});
