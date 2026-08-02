import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NuqsTestingAdapter } from 'nuqs/adapters/testing';
import { LineupView } from '../lineup-view';
import { fetchLineup } from '@/lib/nfl/api';
import type { TeamLineup } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchLineup: vi.fn()
}));

// FieldView links each player to /dashboard/players/[id] via useRouter —
// not mounted under a Next app-router context in this unit test.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() })
}));

const LINEUP: TeamLineup = {
  team: 'KC',
  season: 2025,
  week: 1,
  implied_total: 24.5,
  team_projected_total: 118.4,
  offense: [
    {
      player_id: 'P1',
      player_name: 'Patrick Mahomes',
      position: 'QB',
      field_position: 'qb',
      projected_points: 21.3,
      projected_floor: 15,
      projected_ceiling: 28,
      snap_pct: 0.98,
      depth_rank: 1,
      is_starter: true
    }
  ],
  defense: []
};

function renderLineup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      {/* season/week pre-populated so useWeekParams resolves synchronously
          without needing to mock the latest-week resolver network call. */}
      <NuqsTestingAdapter searchParams='?season=2025&week=1'>
        <LineupView />
      </NuqsTestingAdapter>
    </QueryClientProvider>
  );
}

describe('LineupView (P1 dashboard/lineups regression, 2026-08-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchLineup).mockResolvedValue(LINEUP);
  });

  it('renders the real lineup once a team is selected and the query settles', async () => {
    renderLineup();

    fireEvent.click(screen.getByRole('button', { name: 'KC' }));

    expect(await screen.findByText('Patrick Mahomes')).toBeInTheDocument();
  });
});
