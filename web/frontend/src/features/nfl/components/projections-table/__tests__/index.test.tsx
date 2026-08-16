import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NuqsTestingAdapter } from 'nuqs/adapters/testing';
import { ProjectionsTable } from '../index';
import { fetchProjections } from '@/lib/nfl/api';
import type { ProjectionResponse } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchProjections: vi.fn()
}));

const EMPTY_RESPONSE: ProjectionResponse = {
  season: 2026,
  week: 1,
  scoring_format: 'half_ppr',
  generated_at: '2026-08-16T00:00:00Z',
  projections: [],
  meta: {
    season: 2026,
    week: 1,
    data_as_of: null,
    source_path: null,
    source: 'weekly'
  }
};

const POPULATED_RESPONSE: ProjectionResponse = {
  ...EMPTY_RESPONSE,
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

function renderTable(freeTier = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      {/* season/week pre-populated so useWeekParams resolves synchronously
          without needing to mock the latest-week resolver network call
          (same convention as lineup-view.test.tsx). */}
      <NuqsTestingAdapter searchParams='?season=2026&week=1'>
        <ProjectionsTable freeTier={freeTier} />
      </NuqsTestingAdapter>
    </QueryClientProvider>
  );
}

describe('ProjectionsTable empty-state guard (projections page blank-void fix)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an explanatory empty state instead of a blank void when the resolved week has zero projections', async () => {
    vi.mocked(fetchProjections).mockResolvedValue(EMPTY_RESPONSE);
    renderTable();

    expect(await screen.findByText('No projections yet')).toBeInTheDocument();
    expect(
      screen.getByText(/No projections are available for 2026 Week 1/)
    ).toBeInTheDocument();
  });

  it('renders real rows instead of the empty state when projections are present', async () => {
    vi.mocked(fetchProjections).mockResolvedValue(POPULATED_RESPONSE);
    renderTable();

    expect(await screen.findByText('Ja’Marr Chase')).toBeInTheDocument();
    expect(screen.queryByText('No projections yet')).not.toBeInTheDocument();
  });
});
