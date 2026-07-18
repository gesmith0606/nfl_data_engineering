import { describe, expect, it } from 'vitest';

import {
  assembleAlerts,
  buildRosterIndex,
  countUnread,
  normalizePlayerName,
  type RosterEntry
} from '@/lib/alerts/assemble';
import type { Alert } from '@/lib/nfl/types';

function alert(overrides: Partial<Alert> = {}): Alert {
  return {
    player_id: 'gsis-1',
    player_name: 'Justin Jefferson',
    team: 'MIN',
    position: 'WR',
    alert_type: 'questionable',
    sentiment_multiplier: null,
    latest_signal_at: '2026-07-16T12:00:00Z',
    doc_count: 3,
    ...overrides
  };
}

function entry(overrides: Partial<RosterEntry> = {}): RosterEntry {
  return {
    playerId: 'sleeper-100',
    playerName: 'Justin Jefferson',
    position: 'WR',
    team: 'MIN',
    leagueId: 'L1',
    leagueName: 'MANTIS Dynasty',
    ...overrides
  };
}

describe('normalizePlayerName', () => {
  it('lowercases and strips punctuation', () => {
    expect(normalizePlayerName("Ja'Marr Chase")).toBe('ja marr chase');
    expect(normalizePlayerName('A.J. Brown')).toBe('a j brown');
  });

  it('drops generational suffixes so cross-source names join', () => {
    expect(normalizePlayerName('Kenneth Walker III')).toBe('kenneth walker');
    expect(normalizePlayerName('Marvin Harrison Jr.')).toBe('marvin harrison');
    expect(normalizePlayerName('Odell Beckham Sr')).toBe('odell beckham');
  });

  it('strips diacritics and collapses whitespace', () => {
    expect(normalizePlayerName('  José   Ramírez ')).toBe('jose ramirez');
  });

  it('returns empty string for null/undefined', () => {
    expect(normalizePlayerName(null)).toBe('');
    expect(normalizePlayerName(undefined)).toBe('');
  });
});

describe('buildRosterIndex', () => {
  it('indexes entries by id and normalized name', () => {
    const index = buildRosterIndex([entry()]);
    expect(index.size).toBe(1);
    expect(index.byId.get('sleeper-100')).toHaveLength(1);
    expect(index.byName.get('justin jefferson')).toHaveLength(1);
  });

  it('keeps one entry per league for the same player', () => {
    const index = buildRosterIndex([
      entry({ leagueId: 'L1' }),
      entry({ leagueId: 'L2', leagueName: 'Work League' })
    ]);
    expect(index.byName.get('justin jefferson')).toHaveLength(2);
  });
});

describe('assembleAlerts', () => {
  it('routes rostered players to yourPlayers with league tags', () => {
    const index = buildRosterIndex([entry()]);
    const { yourPlayers, leagueNews } = assembleAlerts([alert()], index);
    expect(yourPlayers).toHaveLength(1);
    expect(yourPlayers[0].leagues).toEqual([
      { leagueId: 'L1', leagueName: 'MANTIS Dynasty' }
    ]);
    expect(leagueNews).toHaveLength(0);
  });

  it('matches by normalized name across id systems (GSIS vs Sleeper)', () => {
    // Alert carries a GSIS id, roster a Sleeper id — only the name joins.
    const index = buildRosterIndex([entry({ playerName: 'Kenneth Walker III' })]);
    const { yourPlayers } = assembleAlerts(
      [alert({ player_id: '00-0037746', player_name: 'Kenneth Walker' })],
      index
    );
    expect(yourPlayers).toHaveLength(1);
  });

  it('tags each league once even when the player matches by id and name', () => {
    const index = buildRosterIndex([entry({ playerId: 'gsis-1' })]);
    const { yourPlayers } = assembleAlerts([alert()], index);
    expect(yourPlayers[0].leagues).toHaveLength(1);
  });

  it('tags multiple leagues that roster the same player', () => {
    const index = buildRosterIndex([
      entry({ leagueId: 'L1' }),
      entry({ leagueId: 'L2', leagueName: 'Work League' })
    ]);
    const { yourPlayers } = assembleAlerts([alert()], index);
    expect(yourPlayers[0].leagues.map((l) => l.leagueId)).toEqual(['L1', 'L2']);
  });

  it('routes unrostered players to leagueNews', () => {
    const index = buildRosterIndex([entry()]);
    const { yourPlayers, leagueNews } = assembleAlerts(
      [alert({ player_id: 'gsis-2', player_name: 'Puka Nacua' })],
      index
    );
    expect(yourPlayers).toHaveLength(0);
    expect(leagueNews).toHaveLength(1);
  });

  it('dedupes multiple alerts for one player, keeping the most severe', () => {
    const index = buildRosterIndex([]);
    const { leagueNews } = assembleAlerts(
      [alert({ alert_type: 'questionable' }), alert({ alert_type: 'ruled_out' })],
      index
    );
    expect(leagueNews).toHaveLength(1);
    expect(leagueNews[0].alert_type).toBe('ruled_out');
  });

  it('sorts by severity, then player name', () => {
    const index = buildRosterIndex([]);
    const { leagueNews } = assembleAlerts(
      [
        alert({ player_id: 'a', player_name: 'Zed Positive', alert_type: 'major_positive' }),
        alert({ player_id: 'b', player_name: 'Bob Out', alert_type: 'ruled_out' }),
        alert({ player_id: 'c', player_name: 'Al Out', alert_type: 'ruled_out' })
      ],
      index
    );
    expect(leagueNews.map((a) => a.player_name)).toEqual([
      'Al Out',
      'Bob Out',
      'Zed Positive'
    ]);
  });

  it('handles empty feeds and empty rosters', () => {
    expect(assembleAlerts([], buildRosterIndex([]))).toEqual({
      yourPlayers: [],
      leagueNews: []
    });
  });
});

describe('countUnread', () => {
  const alerts = [
    { latest_signal_at: '2026-07-16T12:00:00Z' },
    { latest_signal_at: '2026-07-14T12:00:00Z' },
    { latest_signal_at: null }
  ];

  it('counts everything when never seen', () => {
    expect(countUnread(alerts, null)).toBe(3);
  });

  it('counts only alerts newer than last-seen', () => {
    expect(countUnread(alerts, '2026-07-15T00:00:00Z')).toBe(1);
  });

  it('counts zero when everything is older than last-seen', () => {
    expect(countUnread(alerts, '2026-07-17T00:00:00Z')).toBe(0);
  });

  it('ignores timestamp-less alerts once the center has been opened', () => {
    expect(countUnread([{ latest_signal_at: null }], '2026-07-15T00:00:00Z')).toBe(0);
  });

  it('treats an unparseable last-seen as never seen', () => {
    expect(countUnread(alerts, 'not-a-date')).toBe(3);
  });
});
