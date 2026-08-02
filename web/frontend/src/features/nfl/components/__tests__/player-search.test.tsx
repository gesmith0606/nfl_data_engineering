import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PlayerSearch } from '../player-search';
import { searchPlayers } from '@/lib/nfl/api';
import type { PlayerSearchResult } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  searchPlayers: vi.fn()
}));

const RESULTS: PlayerSearchResult[] = [
  { player_id: 'P1', player_name: 'Josh Allen', team: 'BUF', position: 'QB' }
];

function renderSearch() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlayerSearch />
    </QueryClientProvider>
  );
}

describe('PlayerSearch (P1 dashboard/players regression, 2026-08-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(searchPlayers).mockResolvedValue(RESULTS);
  });

  it('renders real search results once the query settles instead of hanging behind Suspense', async () => {
    renderSearch();

    fireEvent.change(screen.getByPlaceholderText('Search players by name...'), {
      target: { value: 'allen' }
    });

    expect(await screen.findByText('Josh Allen')).toBeInTheDocument();
    expect(screen.getByText('BUF')).toBeInTheDocument();
  });
});
