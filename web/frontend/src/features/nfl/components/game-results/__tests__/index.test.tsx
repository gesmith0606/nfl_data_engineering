import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NuqsTestingAdapter } from 'nuqs/adapters/testing';
import { GameResultsGrid } from '../index';
import { fetchGames, fetchGameSeasons } from '@/lib/nfl/api';
import type { GamesResponse, GameSeasonsResponse } from '@/lib/nfl/types';

// vi.mock is hoisted — factory must be self-contained.
vi.mock('@/lib/nfl/api', () => ({
  fetchGames: vi.fn(),
  fetchGameSeasons: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  }
}));

const GAMES: GamesResponse = {
  season: 2025,
  week: 1,
  count: 1,
  games: [
    {
      game_id: '2025_01_BAL_KC',
      season: 2025,
      week: 1,
      home_team: 'KC',
      away_team: 'BAL',
      home_score: 20,
      away_score: 27,
      winner: 'BAL',
      point_spread_result: null,
      total_points: 47,
      game_date: '2025-09-05',
      game_time: '20:20'
    }
  ]
};

const SEASONS: GameSeasonsResponse = {
  seasons: [{ season: 2025, game_count: 272, has_player_stats: true }]
};

function renderGrid() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NuqsTestingAdapter>
        <GameResultsGrid />
      </NuqsTestingAdapter>
    </QueryClientProvider>
  );
}

describe('GameResultsGrid (P1 dashboard/games regression, 2026-08-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchGames).mockResolvedValue(GAMES);
    vi.mocked(fetchGameSeasons).mockResolvedValue(SEASONS);
  });

  it('renders real game results once the query settles instead of hanging behind the loading skeleton', async () => {
    renderGrid();

    // Confirmed final scores appear — not the skeleton, not an empty void.
    expect(await screen.findByText('BAL')).toBeInTheDocument();
    expect(screen.getByText('KC')).toBeInTheDocument();
    expect(screen.getByText('27')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
  });
});
