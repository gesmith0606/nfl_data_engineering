import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { currentWeekQueryOptions } from '@/features/nfl/api/queries';
import { toolSeason } from '@/lib/nfl/season';
import { StartSitView } from '../start-sit-view';
import { fetchCurrentWeek, fetchRosRankings, fetchStartSitCompare } from '@/lib/nfl/api';
import type {
  CurrentWeekResponse,
  RosResponse,
  ToolsCompareResponse
} from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchCurrentWeek: vi.fn(),
  fetchRosRankings: vi.fn(),
  fetchStartSitCompare: vi.fn()
}));

const CURRENT_WEEK: CurrentWeekResponse = { season: 2025, week: 3, source: 'schedule' };

const ROS: RosResponse = {
  season: 2025,
  from_week: 3,
  weeks_remaining: 15,
  scoring_format: 'half_ppr',
  players: [
    {
      player_id: 'P1',
      player_name: 'Christian McCaffrey',
      team: 'SF',
      position: 'RB',
      ros_points: 220,
      projected_season_points: 300,
      vorp: 80,
      position_rank: 1
    },
    {
      player_id: 'P2',
      player_name: 'Josh Jacobs',
      team: 'GB',
      position: 'RB',
      ros_points: 150,
      projected_season_points: 210,
      vorp: 40,
      position_rank: 8
    }
  ]
};

// Recommended player (P1) has a clear projection edge (18.0 vs 12.0) plus
// floor/ceiling and opp-rank data, so the verdict banner should render a
// confidence percentage and every "why" factor.
const COMPARE: ToolsCompareResponse = {
  season: 2025,
  week: 3,
  scoring_format: 'half_ppr',
  reason: 'Start McCaffrey — clear projection edge with a safer floor.',
  players: [
    {
      player_id: 'P1',
      player_name: 'Christian McCaffrey',
      team: 'SF',
      position: 'RB',
      projected_points: 18,
      projected_floor: 12,
      projected_ceiling: 24,
      injury_status: null,
      opp_rank_vs_position: 28,
      ros_points: 220,
      recommended: true
    },
    {
      player_id: 'P2',
      player_name: 'Josh Jacobs',
      team: 'GB',
      position: 'RB',
      projected_points: 12,
      projected_floor: 8,
      projected_ceiling: 16,
      injury_status: null,
      opp_rank_vs_position: 5,
      ros_points: 150,
      recommended: false
    }
  ]
};

function renderStartSit() {
  const client = new QueryClient({
    // staleTime: Infinity keeps the seeded cache entries fresh so no
    // background refetch flips isFetching mid-assertion.
    defaultOptions: { queries: { retry: false, staleTime: Infinity } }
  });
  // Seed the caches the picker depends on so the autocomplete interaction is
  // fully synchronous — async mock resolution raced the fireEvent flow and
  // flaked under a loaded parallel suite run.
  client.setQueryData(currentWeekQueryOptions().queryKey, CURRENT_WEEK);
  client.setQueryData(['nfl', 'ros', toolSeason(CURRENT_WEEK.season)], ROS);
  // Also seed the compare result for the P1+P2 pick sequence the tests use,
  // so the verdict renders synchronously once both players are picked.
  client.setQueryData(
    [
      'nfl',
      'start-sit',
      toolSeason(CURRENT_WEEK.season),
      CURRENT_WEEK.week,
      ['P1', 'P2']
    ],
    COMPARE
  );
  return render(
    <QueryClientProvider client={client}>
      <StartSitView />
    </QueryClientProvider>
  );
}

async function pickTwoPlayers() {
  renderStartSit();
  const input = await screen.findByPlaceholderText('Add 2-4 players to compare...');

  fireEvent.change(input, { target: { value: 'Christian' } });
  fireEvent.click(await screen.findByText('Christian McCaffrey'));

  fireEvent.change(input, { target: { value: 'Josh' } });
  fireEvent.click(await screen.findByText('Josh Jacobs'));
}

describe('StartSitView verdict + why breakdown (market-gap redesign, 2026-08)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCurrentWeek).mockResolvedValue(CURRENT_WEEK);
    vi.mocked(fetchRosRankings).mockResolvedValue(ROS);
    vi.mocked(fetchStartSitCompare).mockResolvedValue(COMPARE);
  });

  it('renders a derived confidence percentage for the recommended starter', async () => {
    await pickTwoPlayers();

    // gap = 18 - 12 = 6, gapPct = 6/18 = 1/3 -> 50 + (1/3)*150 = 100, clamped to 95.
    // findByText IS the assertion (throws if absent). Holding the node for
    // toBeInTheDocument raced verdict re-renders that replace the node.
    await screen.findByText('95%');
  });

  it('renders the why-breakdown factors backing the verdict', async () => {
    await pickTwoPlayers();

    await screen.findByText('Projection edge');
    expect(screen.getByText('Floor (downside)')).toBeInTheDocument();
    expect(screen.getByText('Matchup (opp rank)')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText('Christian McCaffrey').length).toBeGreaterThan(0)
    );
  });
});
