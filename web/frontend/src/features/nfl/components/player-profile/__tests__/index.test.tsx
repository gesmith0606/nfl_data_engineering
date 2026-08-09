import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PlayerProfile } from '../index';
import {
  currentWeekQueryOptions,
  gameSeasonsQueryOptions,
  playerDetailQueryOptions,
  playerGameLogQueryOptions,
  playerProjectionHistoryQueryOptions,
  projectionsQueryOptions,
  rosRankingsQueryOptions
} from '@/features/nfl/api/queries';
import { toolSeason } from '@/lib/nfl/season';
import {
  fetchCurrentWeek,
  fetchGameSeasons,
  fetchPlayer,
  fetchPlayerGameLog,
  fetchPlayerProjectionHistory,
  fetchProjections,
  fetchRosRankings
} from '@/lib/nfl/api';
import type {
  CurrentWeekResponse,
  GameSeasonsResponse,
  PlayerGameLogResponse,
  PlayerProjection,
  PlayerProjectionHistoryResponse,
  ProjectionResponse,
  RosResponse
} from '@/lib/nfl/types';

// Every fetcher the profile's queries can transitively reach must exist as a
// vi.fn() here, even though the seeded cache below means none of them are
// actually invoked (staleTime: Infinity keeps every seeded entry fresh for
// the life of the test) — TanStack Query still resolves the queryFn
// reference through the real (mocked) module graph.
vi.mock('@/lib/nfl/api', () => ({
  fetchCurrentWeek: vi.fn(),
  fetchPlayer: vi.fn(),
  fetchProjections: vi.fn(),
  fetchRosRankings: vi.fn(),
  fetchGameSeasons: vi.fn(),
  fetchPlayerGameLog: vi.fn(),
  fetchPlayerProjectionHistory: vi.fn()
}));

const CURRENT_WEEK: CurrentWeekResponse = { season: 2025, week: 3, source: 'schedule' };
const SCORING = 'half_ppr';

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
    scoring_format: SCORING,
    season: 2025,
    week: 3,
    position_rank: null,
    injury_status: null,
    ...overrides
  };
}

const PLAYER: PlayerProjection = rb({
  player_id: 'P1',
  player_name: 'Christian McCaffrey',
  position_rank: 3,
  projected_points: 20,
  proj_rush_yards: 85,
  proj_rush_tds: 0.8,
  proj_targets: 3.5,
  proj_rec_yards: 25,
  injury_status: 'Questionable'
});

const WEEKLY_POOL: ProjectionResponse = {
  season: 2025,
  week: 3,
  scoring_format: SCORING,
  generated_at: '2026-08-01T00:00:00Z',
  projections: [
    rb({ player_id: 'P2', player_name: 'P2', projected_points: 8, proj_rush_yards: 40, proj_rush_tds: 0.2, proj_targets: 1, proj_rec_yards: 5 }),
    rb({ player_id: 'P3', player_name: 'P3', projected_points: 14, proj_rush_yards: 60, proj_rush_tds: 0.5, proj_targets: 2, proj_rec_yards: 15 }),
    PLAYER,
    rb({ player_id: 'P4', player_name: 'P4', projected_points: 26, proj_rush_yards: 110, proj_rush_tds: 1.0, proj_targets: 5, proj_rec_yards: 40 })
  ]
};

const ROS: RosResponse = {
  season: toolSeason(CURRENT_WEEK.season),
  from_week: 1,
  weeks_remaining: 15,
  scoring_format: SCORING,
  players: [
    { player_id: 'P2', player_name: 'P2', team: 'SF', position: 'RB', ros_points: 150, projected_season_points: 200, vorp: 20, position_rank: 10 },
    { player_id: 'P3', player_name: 'P3', team: 'SF', position: 'RB', ros_points: 180, projected_season_points: 230, vorp: 30, position_rank: 6 },
    { player_id: 'P1', player_name: 'Christian McCaffrey', team: 'SF', position: 'RB', ros_points: 220, projected_season_points: 300, vorp: 80, position_rank: 1 },
    { player_id: 'P4', player_name: 'P4', team: 'SF', position: 'RB', ros_points: 260, projected_season_points: 320, vorp: 90, position_rank: 2 }
  ]
};

const GAME_SEASONS: GameSeasonsResponse = {
  seasons: [
    { season: 2024, game_count: 285, has_player_stats: true },
    { season: 2025, game_count: 285, has_player_stats: true }
  ]
};

const GAME_LOG: PlayerGameLogResponse = {
  player_id: 'P1',
  season: 2025,
  scoring_format: SCORING,
  game_log: [
    {
      week: 1,
      opponent: 'DAL',
      home_away: 'home',
      fantasy_points: 18.4,
      game_result: 'W 24-17',
      passing_yards: null,
      passing_tds: null,
      rushing_yards: 90,
      rushing_tds: 1,
      receptions: 3,
      receiving_yards: 20,
      receiving_tds: 0,
      targets: 4,
      carries: 18
    }
  ]
};

const PROJECTION_HISTORY: PlayerProjectionHistoryResponse = {
  player_id: 'P1',
  player_name: 'Christian McCaffrey',
  team: 'SF',
  position: 'RB',
  season: 2025,
  scoring_format: SCORING,
  weeks: [
    { week: 1, projected_points: 17.0, actual_points: 18.4, projected_floor: 12.0, projected_ceiling: 22.0 }
  ],
  reason: null
};

function renderProfile() {
  const client = new QueryClient({
    // staleTime: Infinity keeps every seeded cache entry fresh so no
    // background refetch races the synchronous assertions below.
    defaultOptions: { queries: { retry: false, staleTime: Infinity } }
  });

  client.setQueryData(currentWeekQueryOptions().queryKey, CURRENT_WEEK);
  client.setQueryData(
    playerDetailQueryOptions('P1', CURRENT_WEEK.season, CURRENT_WEEK.week, SCORING).queryKey,
    PLAYER
  );
  client.setQueryData(
    projectionsQueryOptions(CURRENT_WEEK.season, CURRENT_WEEK.week, SCORING, 'RB').queryKey,
    WEEKLY_POOL
  );
  client.setQueryData(
    rosRankingsQueryOptions(toolSeason(CURRENT_WEEK.season), 'RB').queryKey,
    ROS
  );
  client.setQueryData(gameSeasonsQueryOptions().queryKey, GAME_SEASONS);
  client.setQueryData(playerGameLogQueryOptions('P1', 2025, SCORING).queryKey, GAME_LOG);
  client.setQueryData(
    playerProjectionHistoryQueryOptions('P1', 2025, SCORING).queryKey,
    PROJECTION_HISTORY
  );

  return render(
    <QueryClientProvider client={client}>
      <PlayerProfile playerId='P1' />
    </QueryClientProvider>
  );
}

describe('PlayerProfile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCurrentWeek).mockResolvedValue(CURRENT_WEEK);
    vi.mocked(fetchPlayer).mockResolvedValue(PLAYER);
    vi.mocked(fetchProjections).mockResolvedValue(WEEKLY_POOL);
    vi.mocked(fetchRosRankings).mockResolvedValue(ROS);
    vi.mocked(fetchGameSeasons).mockResolvedValue(GAME_SEASONS);
    vi.mocked(fetchPlayerGameLog).mockResolvedValue(GAME_LOG);
    vi.mocked(fetchPlayerProjectionHistory).mockResolvedValue(PROJECTION_HISTORY);
  });

  it('renders the header with name, team, and injury status never hidden', async () => {
    renderProfile();
    await screen.findByText('Christian McCaffrey');
    expect(screen.getByText('Questionable')).toBeInTheDocument();
    expect(screen.getByText('SF')).toBeInTheDocument();
  });

  it('renders the Bottom Line verdict derived from the position pool', async () => {
    renderProfile();
    // median([8,14,20,26]) = 17, player = 20 -> "3.0 pts above ... (17.0)".
    await screen.findByText(/No\. 3 RB/);
    expect(screen.getByText(/3\.0 pts above the RB median \(17\.0\)/)).toBeInTheDocument();
  });

  it('renders percentile bars pairing raw value with percentile', async () => {
    renderProfile();
    await screen.findByText('Weekly Fantasy Points');
    // computePercentile(20, [8,14,20,26]) = 75 -> 75th pctile.
    expect(screen.getAllByText(/75th pctile/).length).toBeGreaterThan(0);
    // "20.0" appears twice by design (header hero numeral + the Weekly
    // Fantasy Points percentile row) — assert at least one, not uniqueness.
    expect(screen.getAllByText('20.0').length).toBeGreaterThan(0);
  });

  it('renders the game log as an actuals-only table with the honest disclaimer', async () => {
    renderProfile();
    await screen.findByText('vs DAL');
    expect(screen.getByText('18.4')).toBeInTheDocument();
    expect(screen.getByText(/doesn.t carry a per-week projected/)).toBeInTheDocument();
  });
});
