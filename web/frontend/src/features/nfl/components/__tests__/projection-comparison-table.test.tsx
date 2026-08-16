import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { NuqsTestingAdapter } from 'nuqs/adapters/testing';
import { ProjectionComparisonTable } from '../projection-comparison-table';
import { fetchProjectionsComparison } from '@/lib/nfl/api';
import type { ProjectionComparison } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchProjectionsComparison: vi.fn()
}));

// Mirrors the real season=2025/week=18 fallback bug: the backend resolves
// externals (sleeper) from the latest available snapshot and — after the
// projection_service.get_comparison live-"ours"-overlay fix — also
// populates "ours" for that same resolved slice instead of leaving dashes.
const FALLBACK_WITH_OURS: ProjectionComparison = {
  season: 2026,
  week: 1,
  scoring_format: 'half_ppr',
  rows: [
    {
      player_id: '00-0034857',
      player_name: 'Josh Allen',
      position: 'QB',
      team: 'BUF',
      ours: 21.24,
      espn: null,
      sleeper: 2.47,
      yahoo: null,
      delta_vs_ours: -18.77
    }
  ],
  source_labels: { ours: 'Our projections', sleeper: 'Sleeper' },
  data_as_of: {},
  fallback: true,
  fallback_season: 2025,
  fallback_week: 18
};

function renderComparisonTable() {
  // Explicit season/week props are passed through, but useWeekParams is
  // still invoked unconditionally inside the component, so it needs a nuqs
  // adapter present regardless (same convention as lineup-view.test.tsx).
  return render(
    <NuqsTestingAdapter searchParams='?season=2026&week=1'>
      <ProjectionComparisonTable scoring='half_ppr' season={2026} week={1} />
    </NuqsTestingAdapter>
  );
}

describe('ProjectionComparisonTable (multi-source OURS-column dash fix)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the fallback-snapshot banner and a populated Ours column instead of dashes', async () => {
    vi.mocked(fetchProjectionsComparison).mockResolvedValue(FALLBACK_WITH_OURS);
    renderComparisonTable();

    expect(await screen.findByText('Josh Allen')).toBeInTheDocument();
    expect(
      screen.getByText(/showing the latest available snapshot \(2025 Week 18\)/)
    ).toBeInTheDocument();
    // Ours column renders the real projected value, not the em-dash fallback.
    expect(screen.getByText('21.2')).toBeInTheDocument();
  });
});
