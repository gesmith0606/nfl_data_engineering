import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NuqsTestingAdapter } from 'nuqs/adapters/testing';
import { MatchupView } from '../matchup-view';
import {
  fetchProjections,
  fetchPredictions,
  fetchTeamMatchup,
  fetchTeamRoster,
  fetchTeamDefenseMetrics
} from '@/lib/nfl/api';
import type {
  ProjectionResponse,
  PredictionResponse,
  TeamMatchupResponse,
  TeamRosterResponse,
  TeamDefenseMetricsResponse
} from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchProjections: vi.fn(),
  fetchPredictions: vi.fn(),
  fetchTeamMatchup: vi.fn(),
  fetchTeamRoster: vi.fn(),
  fetchTeamDefenseMetrics: vi.fn()
}));

const PROJECTIONS: ProjectionResponse = {
  season: 2025,
  week: 1,
  scoring_format: 'half_ppr',
  generated_at: '2025-09-01T00:00:00Z',
  projections: [
    {
      player_id: 'P1',
      player_name: 'Patrick Mahomes',
      team: 'KC',
      position: 'QB',
      projected_points: 21.3,
      projected_floor: 15,
      projected_ceiling: 28,
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
      week: 1,
      position_rank: 1,
      injury_status: null
    }
  ]
};

const PREDICTIONS: PredictionResponse = { season: 2025, week: 1, predictions: [], generated_at: '2025-09-01T00:00:00Z' };

const MATCHUP: TeamMatchupResponse = {
  team: 'KC',
  season: 2025,
  week: 1,
  opponent: 'BAL',
  is_home: true,
  home_team: 'KC',
  away_team: 'BAL',
  game_id: 'g1',
  gameday: '2025-09-05',
  gametime: '20:20',
  spread_line: -2.5,
  total_line: 47.5,
  is_bye: false,
  fallback: false,
  fallback_season: null
};

const ROSTER_KC_OFFENSE: TeamRosterResponse = {
  team: 'KC',
  season: 2025,
  week: 1,
  side: 'offense',
  fallback: false,
  fallback_season: null,
  roster: [
    {
      player_id: 'P1',
      player_name: 'Patrick Mahomes',
      team: 'KC',
      position: 'QB',
      depth_chart_position: 'QB',
      jersey_number: 15,
      status: 'Active',
      snap_pct_offense: 0.98,
      snap_pct_defense: null,
      injury_status: null,
      slot_hint: 'QB1',
      madden_rating: null,
      rating_detail: null
    }
  ]
};

const EMPTY_ROSTER = (team: string, side: 'offense' | 'defense'): TeamRosterResponse => ({
  team,
  season: 2025,
  week: 1,
  side,
  fallback: false,
  fallback_season: null,
  roster: []
});

const DEFENSE_METRICS = (team: string): TeamDefenseMetricsResponse => ({
  team,
  season: 2025,
  requested_week: 1,
  source_week: 1,
  fallback: false,
  fallback_season: null,
  overall_def_rating: 72,
  def_sos_score: null,
  def_sos_rank: null,
  adj_def_epa: null,
  positional: []
});

function renderMatchup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NuqsTestingAdapter searchParams='?season=2025&week=1'>
        <MatchupView />
      </NuqsTestingAdapter>
    </QueryClientProvider>
  );
}

describe('MatchupView (P1 dashboard/matchups regression, 2026-08-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchProjections).mockResolvedValue(PROJECTIONS);
    vi.mocked(fetchPredictions).mockResolvedValue(PREDICTIONS);
    vi.mocked(fetchTeamMatchup).mockResolvedValue(MATCHUP);
    vi.mocked(fetchTeamDefenseMetrics).mockImplementation((team: string) =>
      Promise.resolve(DEFENSE_METRICS(team))
    );
    vi.mocked(fetchTeamRoster).mockImplementation((team: string, _s: number, _w: number, side) =>
      Promise.resolve(
        team === 'KC' && side === 'offense' ? ROSTER_KC_OFFENSE : EMPTY_ROSTER(team, side as 'offense' | 'defense')
      )
    );
  });

  it('renders the real roster for a selected team once the queries settle', async () => {
    renderMatchup();

    fireEvent.click(screen.getByRole('button', { name: 'KC' }));

    const matches = await screen.findAllByText('Patrick Mahomes');
    expect(matches.length).toBeGreaterThan(0);
  });
});
