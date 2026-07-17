import { beforeEach, describe, expect, it } from 'vitest';

import {
  CONNECTED_LEAGUES_KEY,
  loadConnectedLeagues,
  removeConnectedLeague,
  saveConnectedLeagues,
  upsertConnectedLeague
} from '@/lib/nfl/connected-leagues';
import type { ConnectedLeague } from '@/lib/nfl/types';

function league(id: string, overrides: Partial<ConnectedLeague> = {}): ConnectedLeague {
  return {
    league_id: id,
    league_name: `League ${id}`,
    season: '2026',
    user_id: `user-${id}`,
    username: 'gforceee',
    roster_positions: ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'BN'],
    scoring_format_label: 'Half PPR (league)',
    connected_at: '2026-07-17T00:00:00.000Z',
    ...overrides
  };
}

beforeEach(() => {
  localStorage.clear();
});

describe('loadConnectedLeagues', () => {
  it('returns [] when nothing is stored', () => {
    expect(loadConnectedLeagues()).toEqual([]);
  });

  it('round-trips leagues through save/load', () => {
    saveConnectedLeagues([league('a'), league('b')]);
    const loaded = loadConnectedLeagues();
    expect(loaded).toHaveLength(2);
    expect(loaded[0].league_id).toBe('a');
  });

  it('returns [] on corrupt JSON', () => {
    localStorage.setItem(CONNECTED_LEAGUES_KEY, '{not json');
    expect(loadConnectedLeagues()).toEqual([]);
  });

  it('returns [] when stored value is not an array', () => {
    localStorage.setItem(CONNECTED_LEAGUES_KEY, JSON.stringify({ a: 1 }));
    expect(loadConnectedLeagues()).toEqual([]);
  });

  it('drops entries missing league_id or user_id', () => {
    localStorage.setItem(
      CONNECTED_LEAGUES_KEY,
      JSON.stringify([league('a'), { league_name: 'no ids' }, null])
    );
    const loaded = loadConnectedLeagues();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].league_id).toBe('a');
  });
});

describe('saveConnectedLeagues', () => {
  it('caps storage at 3 leagues', () => {
    saveConnectedLeagues([league('a'), league('b'), league('c'), league('d')]);
    expect(loadConnectedLeagues()).toHaveLength(3);
  });
});

describe('upsertConnectedLeague', () => {
  it('puts the new league first and dedupes by id', () => {
    saveConnectedLeagues([league('a'), league('b')]);
    const updated = upsertConnectedLeague(league('a', { league_name: 'Renamed' }));
    expect(updated[0].league_name).toBe('Renamed');
    expect(updated).toHaveLength(2);
  });
});

describe('removeConnectedLeague', () => {
  it('removes by id and persists', () => {
    saveConnectedLeagues([league('a'), league('b')]);
    const updated = removeConnectedLeague('a');
    expect(updated.map((l) => l.league_id)).toEqual(['b']);
    expect(loadConnectedLeagues().map((l) => l.league_id)).toEqual(['b']);
  });
});
