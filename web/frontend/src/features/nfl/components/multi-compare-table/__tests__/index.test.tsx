import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MultiCompareTable } from '../index';
import { fetchMultiCompareRankings } from '@/lib/nfl/api';
import type { MultiCompareResponse } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchMultiCompareRankings: vi.fn()
}));

const COMPARE: MultiCompareResponse = {
  scoring_format: 'half_ppr',
  position_filter: null,
  season: 2026,
  sources: ['sleeper', 'espn', 'yahoo', 'draftsharks', 'ftn', 'sharps'],
  sort_by: 'consensus',
  rank_basis: 'overall',
  source_labels: {},
  our_projections_available: true,
  stale: {},
  cache_age_hours: {},
  last_updated: {},
  compared_at: '2026-08-01T00:00:00Z',
  players: [
    {
      rank: 1,
      player_name: 'Bijan Robinson',
      position: 'RB',
      team: 'ATL',
      our_rank: 1,
      sleeper_rank: 2,
      espn_rank: 3,
      yahoo_rank: 2,
      draftsharks_rank: 1,
      ftn_rank: null,
      sharps_rank: null,
      our_pos_rank: 1,
      our_overall_rank: 1,
      sleeper_pos_rank: 1,
      sleeper_overall_rank: 2,
      espn_pos_rank: 1,
      espn_overall_rank: 3,
      yahoo_pos_rank: 1,
      yahoo_overall_rank: 2,
      draftsharks_pos_rank: 1,
      draftsharks_overall_rank: 1,
      ftn_pos_rank: null,
      ftn_overall_rank: null,
      sharps_pos_rank: null,
      sharps_overall_rank: null,
      our_projected_points: 21.4,
      rank_diff_vs_sleeper: 1,
      rank_diff_vs_espn: 2,
      rank_diff_vs_yahoo: 1,
      rank_diff_vs_draftsharks: 0,
      rank_diff_vs_ftn: null,
      rank_diff_vs_sharps: null
    }
  ]
};

function renderTable() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MultiCompareTable />
    </QueryClientProvider>
  );
}

describe('MultiCompareTable (BroadcastTable adoption, sibling of rankings-table)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders comparison rows with the sticky player column and sortable headers', async () => {
    vi.mocked(fetchMultiCompareRankings).mockResolvedValue(COMPARE);
    renderTable();

    expect(await screen.findByText('Bijan Robinson')).toBeInTheDocument();
    const sortButton = screen.getByRole('button', { name: /Sleeper/ });
    expect(sortButton).toBeInTheDocument();
  });

  it('clicking a source header re-sorts by that source', async () => {
    vi.mocked(fetchMultiCompareRankings).mockResolvedValue(COMPARE);
    renderTable();

    await screen.findByText('Bijan Robinson');
    const sortButton = screen.getByRole('button', { name: /Sleeper/ });
    fireEvent.click(sortButton);

    await waitFor(() =>
      expect(fetchMultiCompareRankings).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort_by: 'sleeper' })
      )
    );
  });

  it('shows the empty-state message for an empty result set', async () => {
    vi.mocked(fetchMultiCompareRankings).mockResolvedValue({ ...COMPARE, players: [] });
    renderTable();

    expect(
      await screen.findByText('No rows for the current filter combination.')
    ).toBeInTheDocument();
  });
});
