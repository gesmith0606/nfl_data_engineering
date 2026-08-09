import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProjectionHistoryChart } from '../projection-history-chart';
import { playerProjectionHistoryQueryOptions } from '@/features/nfl/api/queries';
import { fetchPlayerProjectionHistory } from '@/lib/nfl/api';
import type { PlayerProjectionHistoryResponse } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchPlayerProjectionHistory: vi.fn()
}));

const SCORING = 'half_ppr';

function renderChart(response: PlayerProjectionHistoryResponse) {
  const client = new QueryClient({
    // staleTime: Infinity keeps the seeded cache entry fresh so no
    // background refetch races the synchronous assertions below.
    defaultOptions: { queries: { retry: false, staleTime: Infinity } }
  });
  client.setQueryData(
    playerProjectionHistoryQueryOptions('P1', 2025, SCORING).queryKey,
    response
  );

  return render(
    <QueryClientProvider client={client}>
      <ProjectionHistoryChart playerId='P1' season={2025} scoring={SCORING} />
    </QueryClientProvider>
  );
}

describe('ProjectionHistoryChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the overlay with a mix of projected + actual weeks and both legend swatches', async () => {
    renderChart({
      player_id: 'P1',
      player_name: 'Christian McCaffrey',
      team: 'SF',
      position: 'RB',
      season: 2025,
      scoring_format: SCORING,
      weeks: [
        { week: 1, projected_points: 17.0, actual_points: 18.4, projected_floor: 12.0, projected_ceiling: 22.0 },
        { week: 2, projected_points: 15.5, actual_points: null, projected_floor: 10.0, projected_ceiling: 20.0 }
      ],
      reason: null
    });

    await screen.findByText('Projected vs. Actual — 2025');
    expect(screen.getByText('Actual')).toBeInTheDocument();
    expect(screen.getByText('Projected')).toBeInTheDocument();
    expect(screen.getByText('Floor–Ceiling')).toBeInTheDocument();
    // Some actuals exist (week 1) so the degraded-state note must NOT show.
    expect(screen.queryByText(/Actuals unavailable/)).not.toBeInTheDocument();
    expect(fetchPlayerProjectionHistory).not.toHaveBeenCalled();
  });

  it('degrades to projection-only mode with a quiet note when every week has a null actual', async () => {
    renderChart({
      player_id: 'P1',
      player_name: 'Christian McCaffrey',
      team: 'SF',
      position: 'RB',
      season: 2025,
      scoring_format: SCORING,
      weeks: [
        { week: 1, projected_points: 17.0, actual_points: null, projected_floor: 12.0, projected_ceiling: 22.0 },
        { week: 2, projected_points: 15.5, actual_points: null, projected_floor: 10.0, projected_ceiling: 20.0 }
      ],
      reason: null
    });

    await screen.findByText('Actuals unavailable — projections only.');
    // Bar series is omitted entirely in this mode — no "Actual" legend swatch.
    expect(screen.queryByText('Actual')).not.toBeInTheDocument();
    expect(screen.getByText('Projected')).toBeInTheDocument();
  });

  it('shows the server reason when weeks come back empty', async () => {
    renderChart({
      player_id: 'P1',
      player_name: 'Christian McCaffrey',
      team: 'SF',
      position: 'RB',
      season: 2016,
      scoring_format: SCORING,
      weeks: [],
      reason: 'No archived Gold projections or Bronze actuals exist for season 2016.'
    });

    await screen.findByText(/No archived Gold projections or Bronze actuals exist for season 2016/);
  });

  it('shows a quiet generic empty note when weeks is empty and reason is null', async () => {
    renderChart({
      player_id: 'P1',
      player_name: 'Christian McCaffrey',
      team: 'SF',
      position: 'RB',
      season: 2026,
      scoring_format: SCORING,
      weeks: [],
      reason: null
    });

    await screen.findByText('No projection history recorded for this player-season yet.');
  });

  it('renders a skeleton while loading (no spinner)', () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } }
    });
    // Not seeded, and queryFn never resolves — stays in loading state.
    vi.mocked(fetchPlayerProjectionHistory).mockReturnValue(new Promise(() => {}));

    render(
      <QueryClientProvider client={client}>
        <ProjectionHistoryChart playerId='P1' season={2025} scoring={SCORING} />
      </QueryClientProvider>
    );

    expect(screen.queryByText('Projected vs. Actual — 2025')).not.toBeInTheDocument();
    expect(document.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });
});
