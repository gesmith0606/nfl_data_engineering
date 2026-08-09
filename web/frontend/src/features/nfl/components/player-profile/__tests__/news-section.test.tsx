import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PlayerNewsSection } from '../news-section';
import { playerNewsQueryOptions } from '@/features/nfl/api/queries';
import { fetchPlayerNews } from '@/lib/nfl/api';
import type { NewsItem } from '@/lib/nfl/types';

vi.mock('@/lib/nfl/api', () => ({
  fetchPlayerNews: vi.fn()
}));

function newsItem(overrides: Partial<NewsItem>): NewsItem {
  return {
    doc_id: 'D1',
    title: 'Untitled',
    source: 'rss_espn',
    url: null,
    published_at: null,
    sentiment: null,
    category: null,
    player_id: 'P1',
    player_name: 'Christian McCaffrey',
    team: 'SF',
    is_ruled_out: false,
    is_inactive: false,
    is_questionable: false,
    is_suspended: false,
    is_returning: false,
    body_snippet: null,
    event_flags: [],
    summary: null,
    ...overrides
  };
}

function renderSection(items: NewsItem[]) {
  const client = new QueryClient({
    // staleTime: Infinity keeps the seeded cache entry fresh so no
    // background refetch races the synchronous assertions below.
    defaultOptions: { queries: { retry: false, staleTime: Infinity } }
  });
  client.setQueryData(
    playerNewsQueryOptions('P1', 2026, 1, 10).queryKey,
    items
  );

  return render(
    <QueryClientProvider client={client}>
      <PlayerNewsSection playerId='P1' season={2026} week={1} />
    </QueryClientProvider>
  );
}

describe('PlayerNewsSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders news items with source, event flags, and sentiment', async () => {
    renderSection([
      newsItem({
        doc_id: 'D1',
        title: 'CMC ruled out for Sunday',
        is_ruled_out: true,
        sentiment: -0.4,
        summary: 'Injury update.'
      })
    ]);

    await screen.findByText('CMC ruled out for Sunday');
    expect(screen.getByText('RULED OUT')).toBeInTheDocument();
    expect(screen.getByText('ESPN')).toBeInTheDocument();
    expect(screen.getByText('negative')).toBeInTheDocument();
  });

  it('suppresses the sentiment chip when there is no summary backing it', async () => {
    renderSection([
      newsItem({ doc_id: 'D2', title: 'Roster note', sentiment: 0.5, summary: null })
    ]);

    await screen.findByText('Roster note');
    expect(screen.queryByText('positive')).not.toBeInTheDocument();
  });

  it('shows a quiet empty message when there is no news yet', async () => {
    renderSection([]);

    await screen.findByText(/No news yet this week/);
    expect(fetchPlayerNews).not.toHaveBeenCalled();
  });
});
