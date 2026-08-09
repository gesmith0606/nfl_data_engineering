import { describe, it, expect } from 'vitest';
import { deriveBottomLine, type BottomLinePlayer } from '../bottom-line';

function player(overrides: Partial<BottomLinePlayer>): BottomLinePlayer {
  return {
    player_name: 'Christian McCaffrey',
    position: 'RB',
    projected_points: 20,
    position_rank: 3,
    injury_status: null,
    ...overrides
  };
}

describe('deriveBottomLine', () => {
  it('states the position rank and the above-median gap', () => {
    // pool median([8,14,20,26]) = 17, player = 20 -> +3.0 above.
    const sentence = deriveBottomLine(player({}), [8, 14, 20, 26]);
    expect(sentence).toContain('No. 3 RB');
    expect(sentence).toContain('3.0 pts above the RB median (17.0)');
  });

  it('states a below-median gap when the player trails the pool', () => {
    // pool median([10,20,30,40]) = 25, player projected 15 -> 10.0 below.
    const sentence = deriveBottomLine(player({ projected_points: 15, position_rank: 30 }), [
      10, 20, 30, 40
    ]);
    expect(sentence).toContain('No. 30 RB');
    expect(sentence).toContain('10.0 pts below the RB median (25.0)');
  });

  it('falls back to a generic rank phrase when position_rank is unavailable', () => {
    const sentence = deriveBottomLine(player({ position_rank: null }), [10, 20, 30]);
    expect(sentence).toContain('a RB this week');
  });

  it('appends an injury callout for a non-Active status', () => {
    const sentence = deriveBottomLine(player({ injury_status: 'Questionable' }), [8, 14, 20, 26]);
    expect(sentence).toContain('Listed Questionable');
  });

  it('omits the injury callout for an Active status', () => {
    const sentence = deriveBottomLine(player({ injury_status: 'Active' }), [8, 14, 20, 26]);
    expect(sentence).not.toContain('Listed');
  });

  it('returns a data-honest fallback when the position pool is empty', () => {
    const sentence = deriveBottomLine(player({}), []);
    expect(sentence).toBe('Not enough RB data this week to rank Christian McCaffrey yet.');
  });
});
