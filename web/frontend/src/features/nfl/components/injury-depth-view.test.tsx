import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InjuryDepthView } from './injury-depth-view';
import { fetchCurrentWeek, fetchDepthCharts, fetchInjuryReport } from '@/lib/nfl/api';
import type { InjuryResponse, DepthChartResponse, CurrentWeekResponse } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchCurrentWeek: vi.fn(),
  fetchDepthCharts: vi.fn(),
  fetchInjuryReport: vi.fn()
}));

const CURRENT_WEEK: CurrentWeekResponse = { season: 2026, week: 1, source: 'schedule' };

const INJURIES: InjuryResponse = {
  season: 2026,
  week: 1,
  players: [
    {
      player_id: 'P1',
      player_name: 'Justin Jefferson',
      team: 'MIN',
      position: 'WR',
      injury_status: 'Questionable',
      projected_points: 14.2
    }
  ]
};

const DEPTH: DepthChartResponse = { season: 2026, as_of: null, entries: [] };

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <InjuryDepthView />
    </QueryClientProvider>
  );
}

describe('InjuryDepthView (BroadcastTable adoption on the injury report table)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCurrentWeek).mockResolvedValue(CURRENT_WEEK);
    vi.mocked(fetchDepthCharts).mockResolvedValue(DEPTH);
  });

  it('renders the injury report as a BroadcastTable row', async () => {
    vi.mocked(fetchInjuryReport).mockResolvedValue(INJURIES);
    renderView();

    expect(await screen.findByText('Justin Jefferson')).toBeInTheDocument();
    expect(screen.getByText('Questionable')).toBeInTheDocument();
    expect(screen.getByText('14.2')).toBeInTheDocument();
  });

  it('shows the empty-state message when there are no fantasy-relevant injuries', async () => {
    vi.mocked(fetchInjuryReport).mockResolvedValue({ ...INJURIES, players: [] });
    renderView();

    expect(
      await screen.findByText('No fantasy-relevant injuries this week.')
    ).toBeInTheDocument();
  });
});
