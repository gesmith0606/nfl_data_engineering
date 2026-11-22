import { describe, expect, it } from 'vitest';
import { nflSeasonYear, toolSeason } from '@/lib/nfl/season';

// Local-time constructors: month is 0-based.
const d = (y: number, m: number, day: number) => new Date(y, m - 1, day);

describe('nflSeasonYear', () => {
  it('keeps January and February in the season that started last autumn', () => {
    expect(nflSeasonYear(d(2027, 1, 5))).toBe(2026);
    expect(nflSeasonYear(d(2027, 2, 28))).toBe(2026);
  });
  it('rolls to the new league year in March', () => {
    expect(nflSeasonYear(d(2027, 3, 1))).toBe(2027);
  });
  it('is the calendar year in-season', () => {
    expect(nflSeasonYear(d(2026, 11, 21))).toBe(2026);
  });
});

describe('toolSeason', () => {
  it('does not jump a season ahead during the January playoffs', () => {
    // current-week still resolves the season being played
    expect(toolSeason(2026, d(2027, 1, 5))).toBe(2026);
  });
  it('still clamps up to the upcoming season in the offseason', () => {
    // Aug 2026: current-week says 2025 (last season with games)
    expect(toolSeason(2025, d(2026, 8, 10))).toBe(2026);
  });
  it('falls back to the NFL season when current-week is unknown', () => {
    expect(toolSeason(undefined, d(2027, 2, 1))).toBe(2026);
  });
});
