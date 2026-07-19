import { describe, it, expect } from 'vitest'
import {
  clampTeamCount,
  mapLeagueOverviewToConfig,
  mapRosterFormat,
  mapScoringFormat
} from '../league-config'
import type { DraftConfig, LeagueOverviewResponse } from '@/lib/nfl/types'

const BASE_CONFIG: DraftConfig = {
  scoring: 'standard',
  roster_format: 'standard',
  n_teams: 12,
  user_pick: 5,
  season: 2026,
  platform: 'custom'
}

function overview(overrides: Partial<LeagueOverviewResponse> = {}): LeagueOverviewResponse {
  return {
    league_id: 'L1',
    league_name: 'Test League',
    season: '2026',
    status: 'in_season',
    total_rosters: 12,
    roster_positions: ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'BN'],
    scoring_format_label: 'Full PPR (league)',
    scoring_deltas: [],
    unmodeled_keys: [],
    user_roster: [],
    ...overrides
  }
}

describe('clampTeamCount', () => {
  it('returns an exact supported size unchanged', () => {
    expect(clampTeamCount(10, 12)).toBe(10)
  })

  it('rounds to the nearest supported size', () => {
    expect(clampTeamCount(11, 12)).toBe(10) // tie -> lower candidate wins
    expect(clampTeamCount(13, 12)).toBe(12) // |12-13|=1 < |14-13|=1? tie -> 12 wins (first match)
    expect(clampTeamCount(9, 12)).toBe(8)
    expect(clampTeamCount(16, 12)).toBe(14)
  })

  it('falls back when the count is missing or invalid', () => {
    expect(clampTeamCount(null, 12)).toBe(12)
    expect(clampTeamCount(undefined, 12)).toBe(12)
    expect(clampTeamCount(0, 12)).toBe(12)
  })
})

describe('mapScoringFormat', () => {
  it('maps Full PPR labels to ppr', () => {
    expect(mapScoringFormat('Full PPR (league)')).toBe('ppr')
    expect(mapScoringFormat('PPR')).toBe('ppr')
  })

  it('maps Half PPR labels to half_ppr', () => {
    expect(mapScoringFormat('Half PPR (league)')).toBe('half_ppr')
  })

  it('falls back to standard for anything else', () => {
    expect(mapScoringFormat('Standard')).toBe('standard')
    expect(mapScoringFormat(null)).toBe('standard')
    expect(mapScoringFormat(undefined)).toBe('standard')
  })
})

describe('mapRosterFormat', () => {
  it('detects superflex from SUPER_FLEX slots', () => {
    expect(mapRosterFormat(['QB', 'RB', 'WR', 'SUPER_FLEX', 'BN'])).toBe('superflex')
  })

  it('detects 2qb from two QB slots when no superflex slot exists', () => {
    expect(mapRosterFormat(['QB', 'QB', 'RB', 'WR', 'BN'])).toBe('2qb')
  })

  it('defaults to sleeper_default otherwise', () => {
    expect(mapRosterFormat(['QB', 'RB', 'WR', 'FLEX', 'BN'])).toBe('sleeper_default')
    expect(mapRosterFormat(null)).toBe('sleeper_default')
  })
})

describe('mapLeagueOverviewToConfig', () => {
  it('maps total_rosters, scoring, roster format, and forces platform/adp_source to sleeper', () => {
    const result = mapLeagueOverviewToConfig(overview(), BASE_CONFIG)
    expect(result).toMatchObject({
      n_teams: 12,
      scoring: 'ppr',
      roster_format: 'sleeper_default',
      platform: 'sleeper',
      adp_source: 'sleeper'
    })
  })

  it('clamps an odd total_rosters count to the nearest supported size', () => {
    const result = mapLeagueOverviewToConfig(overview({ total_rosters: 11 }), BASE_CONFIG)
    expect(result.n_teams).toBe(10)
  })

  it('clamps user_pick down when it exceeds the mapped team count', () => {
    const result = mapLeagueOverviewToConfig(
      overview({ total_rosters: 8 }),
      { ...BASE_CONFIG, user_pick: 12 }
    )
    expect(result.n_teams).toBe(8)
    expect(result.user_pick).toBe(8)
  })

  it('parses a half-PPR league with a superflex slot', () => {
    const result = mapLeagueOverviewToConfig(
      overview({
        scoring_format_label: 'Half PPR (league)',
        roster_positions: ['QB', 'SUPER_FLEX', 'RB', 'WR', 'TE', 'BN']
      }),
      BASE_CONFIG
    )
    expect(result.scoring).toBe('half_ppr')
    expect(result.roster_format).toBe('superflex')
  })

  it('falls back to base n_teams when total_rosters is missing', () => {
    const result = mapLeagueOverviewToConfig(overview({ total_rosters: null }), BASE_CONFIG)
    expect(result.n_teams).toBe(BASE_CONFIG.n_teams)
  })
})
