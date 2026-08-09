import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RankingsTable } from '../index';
import { fetchProjections } from '@/lib/nfl/api';
import type { ProjectionResponse } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchProjections: vi.fn()
}));

const PROJECTIONS: ProjectionResponse = {
  season: 2026,
  week: 1,
  scoring_format: 'half_ppr',
  generated_at: '2026-07-01T00:00:00Z',
  projections: [
    {
      player_id: 'P1',
      player_name: 'Ja’Marr Chase',
      team: 'CIN',
      position: 'WR',
      projected_points: 18.2,
      projected_floor: 12,
      projected_ceiling: 26,
      proj_pass_yards: null,
      proj_pass_tds: null,
      proj_rush_yards: null,
      proj_rush_tds: null,
      proj_rec: 7,
      proj_rec_yards: 95,
      proj_rec_tds: 1,
      proj_interceptions: null,
      proj_carries: null,
      proj_targets: 9,
      proj_fg_makes: null,
      proj_xp_makes: null,
      scoring_format: 'half_ppr',
      season: 2026,
      week: 1,
      position_rank: 1,
      injury_status: null
    }
  ]
};

function renderTable() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RankingsTable />
    </QueryClientProvider>
  );
}

describe('RankingsTable (P1 dashboard/rankings regression, 2026-08-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchProjections).mockResolvedValue(PROJECTIONS);
  });

  it('renders real ranked players once the query settles instead of hanging behind Suspense', async () => {
    renderTable();

    expect(await screen.findByText('Ja’Marr Chase')).toBeInTheDocument();
    expect(screen.getByText('1 players')).toBeInTheDocument();
  });
});
