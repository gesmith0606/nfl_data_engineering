import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SosGridView } from './sos-grid-view';
import { fetchSosGrid } from '@/lib/nfl/api';
import type { SosResponse } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchSosGrid: vi.fn()
}));

const SOS: SosResponse = {
  season: 2026,
  week: 1,
  cells: [
    { team: 'KC', position: 'QB', avg_pts_allowed: 22.1, rank: 30 },
    { team: 'KC', position: 'RB', avg_pts_allowed: 10.4, rank: 5 },
    { team: 'BUF', position: 'QB', avg_pts_allowed: 15.0, rank: 12 }
  ]
};

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SosGridView />
    </QueryClientProvider>
  );
}

describe('SosGridView (BroadcastTable adoption)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the defense-vs-position matrix with a sticky team column', async () => {
    vi.mocked(fetchSosGrid).mockResolvedValue(SOS);
    renderView();

    expect(await screen.findByText('KC')).toBeInTheDocument();
    expect(screen.getByText('BUF')).toBeInTheDocument();
    expect(screen.getByText('vs QB')).toBeInTheDocument();
    // KC's soft vs-RB matchup (rank 5) renders inside the graded cell.
    expect(
      screen.getByTitle('10.4 avg fantasy pts allowed to RB')
    ).toBeInTheDocument();
  });

  it('shows the empty-state message instead of a spinner when the fetch fails', async () => {
    vi.mocked(fetchSosGrid).mockRejectedValue(new Error('boom'));
    renderView();

    expect(
      await screen.findByText(
        "Defense-vs-position data isn't available yet for this season."
      )
    ).toBeInTheDocument();
  });
});
