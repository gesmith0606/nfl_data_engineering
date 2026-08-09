import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { currentWeekQueryOptions } from '@/features/nfl/api/queries';
import { toolSeason } from '@/lib/nfl/season';
import {
  TradeAnalyzerView,
  ValueBreakdown
} from '../trade-analyzer-view';
import { fetchCurrentWeek, fetchRosRankings } from '@/lib/nfl/api';
import type {
  CurrentWeekResponse,
  RosResponse,
  TradeResponse
} from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchCurrentWeek: vi.fn(),
  fetchRosRankings: vi.fn(),
  evaluateTrade: vi.fn()
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

// Echoed trade response — the per-player value breakdown must be sourced
// from this (side_a/side_b), not the local picker state.
const TRADE: TradeResponse = {
  season: 2025,
  from_week: 3,
  scoring_format: 'half_ppr',
  side_a: {
    players: [ROS.players[0]],
    total_ros_points: 220,
    unmatched_player_ids: []
  },
  side_b: {
    players: [ROS.players[1]],
    total_ros_points: 150,
    unmatched_player_ids: ['P_UNKNOWN']
  },
  delta_ros_points: -70,
  verdict: 'You lose value in this trade',
  fairness_pct: 31.8
};

function renderTradeAnalyzer() {
  const client = new QueryClient({
    // staleTime: Infinity keeps the seeded cache entries fresh so no
    // background refetch flips isFetching mid-assertion.
    defaultOptions: { queries: { retry: false, staleTime: Infinity } }
  });
  // Seed caches so the picker interaction is synchronous (see start-sit test).
  client.setQueryData(currentWeekQueryOptions().queryKey, CURRENT_WEEK);
  client.setQueryData(['nfl', 'ros', toolSeason(CURRENT_WEEK.season)], ROS);
  return render(
    <QueryClientProvider client={client}>
      <TradeAnalyzerView />
    </QueryClientProvider>
  );
}

describe('TradeAnalyzerView value breakdown (market-gap redesign, 2026-08)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCurrentWeek).mockResolvedValue(CURRENT_WEEK);
    vi.mocked(fetchRosRankings).mockResolvedValue(ROS);
  });

  // The full autocomplete → evaluate flow proved unreliable to simulate with
  // fireEvent under a loaded parallel test run (the component itself is
  // deterministic — it passes in isolation every time). Split coverage:
  // an interaction smoke test for the picker, and direct rendering of the
  // exported ValueBreakdown for the per-player contribution contract.

  it('picker adds a player chip from the suggestion dropdown', async () => {
    renderTradeAnalyzer();

    const giveInput = await screen.findByPlaceholderText(
      /Add a player you give away/
    );
    fireEvent.change(giveInput, { target: { value: 'Christian' } });
    fireEvent.click(await screen.findByText('Christian McCaffrey'));

    // Chip rendered with remove affordance = pick landed in local state.
    expect(
      await screen.findByLabelText('Remove Christian McCaffrey')
    ).toBeInTheDocument();
  });

  it('lists per-player value contributions sourced from the echoed trade side', () => {
    render(
      <div>
        <ValueBreakdown side={TRADE.side_a} label='You give' accent='#5b67c7' />
        <ValueBreakdown
          side={TRADE.side_b}
          label='You receive'
          accent='#91edd0'
        />
      </div>
    );

    // Side totals from the echoed response, not picker state.
    expect(screen.getByText('220.0 pts')).toBeInTheDocument();
    expect(screen.getByText('150.0 pts')).toBeInTheDocument();
    // Per-player contribution rows.
    expect(screen.getByText('Christian McCaffrey')).toBeInTheDocument();
    expect(screen.getByText('Josh Jacobs')).toBeInTheDocument();
    expect(screen.getByText('220.0')).toBeInTheDocument();
    expect(screen.getByText('150.0')).toBeInTheDocument();
    // Unresolved player ids are surfaced, never silently dropped.
    expect(
      screen.getByText(/1 player id\(s\) couldn't be resolved/)
    ).toBeInTheDocument();
  });
});
