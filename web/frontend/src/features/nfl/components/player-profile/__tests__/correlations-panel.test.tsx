import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CorrelationsPanel } from '../correlations-panel';
import { playerCorrelationsQueryOptions } from '@/features/nfl/api/queries';
import { fetchPlayerCorrelations } from '@/lib/nfl/api';
import type { PlayerCorrelationsResponse } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchPlayerCorrelations: vi.fn()
}));

function renderPanel(response: PlayerCorrelationsResponse) {
  const client = new QueryClient({
    // staleTime: Infinity keeps the seeded cache entry fresh so no
    // background refetch races the synchronous assertions below.
    defaultOptions: { queries: { retry: false, staleTime: Infinity } }
  });
  client.setQueryData(playerCorrelationsQueryOptions('P1').queryKey, response);

  return render(
    <QueryClientProvider client={client}>
      <CorrelationsPanel playerId='P1' />
    </QueryClientProvider>
  );
}

describe('CorrelationsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders correlated players with relation label and signed correlation', async () => {
    renderPanel({
      player_id: 'P1',
      generated_at: '2026-08-01T00:00:00Z',
      correlations: [
        { other_player_id: 'P2', other_player_name: 'Deebo Samuel', relation: 'qb_stack', rho: 0.42, n_games: 48 },
        { other_player_id: 'P3', other_player_name: 'Elijah Mitchell', relation: 'same_backfield', rho: -0.18, n_games: 22 }
      ]
    });

    await screen.findByText('Deebo Samuel');
    expect(screen.getByText('QB Stack')).toBeInTheDocument();
    expect(screen.getByText('+0.42')).toBeInTheDocument();
    expect(screen.getByText('Same Backfield')).toBeInTheDocument();
    expect(screen.getByText('-0.18')).toBeInTheDocument();
  });

  it('falls back to the raw relation string when no label is mapped', async () => {
    renderPanel({
      player_id: 'P1',
      generated_at: '2026-08-01T00:00:00Z',
      correlations: [
        { other_player_id: 'P2', other_player_name: 'Some Player', relation: 'unmapped_relation', rho: 0.1, n_games: 10 }
      ]
    });

    await screen.findByText('unmapped_relation');
  });

  it('shows a quiet empty message when the player has no served edges', async () => {
    renderPanel({ player_id: 'P1', generated_at: '2026-08-01T00:00:00Z', correlations: [] });

    await screen.findByText(/No correlated players tracked yet/);
    expect(fetchPlayerCorrelations).not.toHaveBeenCalled();
  });
});
