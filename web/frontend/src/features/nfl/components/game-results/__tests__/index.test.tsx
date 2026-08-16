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

/** Mimics a real weekly slate — several games, not just one — so a
 *  regression that silently drops rows (e.g. an accidental slice/filter/
 *  early-return in the query or render path) shows up as a failing count
 *  assertion instead of passing on a single-game fixture. */
function buildGame(
  away: string,
  home: string,
  awayScore: number,
  homeScore: number
): GamesResponse['games'][number] {
  return {
    game_id: `2025_01_${away}_${home}`,
    season: 2025,
    week: 1,
    home_team: home,
    away_team: away,
    home_score: homeScore,
    away_score: awayScore,
    winner: awayScore > homeScore ? away : home,
    point_spread_result: null,
    total_points: awayScore + homeScore,
    game_date: '2025-09-07',
    game_time: '13:00'
  };
}

const GAMES: GamesResponse = {
  season: 2025,
  week: 1,
  count: 4,
  games: [
    buildGame('BAL', 'KC', 27, 20),
    buildGame('ARI', 'NO', 23, 13),
    buildGame('DAL', 'PHI', 19, 24),
    buildGame('CIN', 'CLE', 17, 16)
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

  it('renders one card per game returned by the API — not just the first', async () => {
    renderGrid();

    await screen.findByText('BAL');

    const cards = document.querySelectorAll('[data-game-id]');
    expect(cards).toHaveLength(GAMES.games.length);
    expect(
      Array.from(cards).map((c) => c.getAttribute('data-game-id')).sort()
    ).toEqual(GAMES.games.map((g) => g.game_id).sort());
  });
});
