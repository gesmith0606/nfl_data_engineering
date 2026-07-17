import { describe, expect, it } from 'vitest';

import {
  buildLeagueContextPrompt,
  parseAdvisorLeagues
} from '../league-context';

const validLeague = {
  league_id: '1378522447686402048',
  league_name: 'MANTIS Dynasty',
  season: '2026',
  user_id: '997016529965223936',
  username: 'Gforceee',
  roster_positions: ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'BN', 'BN'],
  scoring_format_label: 'Half PPR + TE premium (league)'
};

describe('parseAdvisorLeagues', () => {
  it('returns [] for non-array payloads', () => {
    expect(parseAdvisorLeagues(undefined)).toEqual([]);
    expect(parseAdvisorLeagues(null)).toEqual([]);
    expect(parseAdvisorLeagues('leagues')).toEqual([]);
    expect(parseAdvisorLeagues({ league_id: 'x' })).toEqual([]);
  });

  it('keeps well-formed leagues intact', () => {
    const parsed = parseAdvisorLeagues([validLeague]);
    expect(parsed).toHaveLength(1);
    expect(parsed[0]).toMatchObject({
      league_id: validLeague.league_id,
      user_id: validLeague.user_id,
      league_name: 'MANTIS Dynasty',
      scoring_format_label: 'Half PPR + TE premium (league)'
    });
  });

  it('drops entries missing league_id or user_id', () => {
    const parsed = parseAdvisorLeagues([
      { ...validLeague, league_id: '' },
      { ...validLeague, user_id: undefined },
      null,
      42,
      validLeague
    ]);
    expect(parsed).toHaveLength(1);
  });

  it('caps at 3 leagues', () => {
    const many = Array.from({ length: 5 }, (_, i) => ({
      ...validLeague,
      league_id: `league-${i}`
    }));
    expect(parseAdvisorLeagues(many)).toHaveLength(3);
  });

  it('sanitizes malformed optional fields to safe defaults', () => {
    const parsed = parseAdvisorLeagues([
      {
        league_id: 'l1',
        user_id: 'u1',
        league_name: 123,
        roster_positions: ['QB', 7, null, 'BN'],
        scoring_format_label: false
      }
    ]);
    expect(parsed[0].league_name).toBe('Unnamed league');
    expect(parsed[0].roster_positions).toEqual(['QB', 'BN']);
    expect(parsed[0].scoring_format_label).toBe('Half PPR');
  });
});

describe('buildLeagueContextPrompt', () => {
  it('returns empty string when no leagues connected', () => {
    expect(buildLeagueContextPrompt([])).toBe('');
  });

  it('includes league identity, scoring, and tool guidance', () => {
    const prompt = buildLeagueContextPrompt(parseAdvisorLeagues([validLeague]));
    expect(prompt).toContain('MANTIS Dynasty');
    expect(prompt).toContain(validLeague.league_id);
    expect(prompt).toContain(validLeague.user_id);
    expect(prompt).toContain('Half PPR + TE premium (league)');
    expect(prompt).toContain('getMyLineup');
    expect(prompt).toContain('getMyWaiverTargets');
    expect(prompt).toContain('never ask them for a league ID');
  });

  it('lists starting slots without bench slots', () => {
    const prompt = buildLeagueContextPrompt(parseAdvisorLeagues([validLeague]));
    expect(prompt).toContain('QB, RB, RB, WR, WR, TE, FLEX');
    expect(prompt).not.toMatch(/Starting slots:.*BN/);
  });

  it('marks the first league as primary only when several are connected', () => {
    const single = buildLeagueContextPrompt(parseAdvisorLeagues([validLeague]));
    expect(single).not.toContain('(PRIMARY)');

    const multi = buildLeagueContextPrompt(
      parseAdvisorLeagues([
        validLeague,
        { ...validLeague, league_id: 'other', league_name: 'Work League' }
      ])
    );
    expect(multi).toContain('(PRIMARY)');
    expect(multi).toContain('Work League');
  });
});
