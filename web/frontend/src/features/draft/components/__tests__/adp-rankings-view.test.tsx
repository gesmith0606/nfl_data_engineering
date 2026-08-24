import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AdpRankingsView } from '../adp-rankings-view'
import { fetchAdpBoard } from '@/lib/nfl/api'
import type { AdpBoardResponse, DraftPlayer } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained.
vi.mock('@/lib/nfl/api', () => ({
  fetchAdpBoard: vi.fn()
}))

function player(overrides: Partial<DraftPlayer>): DraftPlayer {
  return {
    player_id: 'p',
    player_name: 'Someone',
    position: 'RB',
    team: 'KC',
    projected_points: 200,
    model_rank: 1,
    adp_rank: 1,
    adp_diff: 0,
    value_tier: 'fair_value',
    vorp: 10,
    ...overrides
  }
}

const BOARD: AdpBoardResponse = {
  scoring_format: 'half_ppr',
  season: 2026,
  adp_source: 'ffc',
  count: 2,
  players: [
    player({ player_id: 'qb', player_name: 'Josh Allen', position: 'QB', model_rank: 9, adp_rank: 32, adp_diff: 23, value_tier: 'undervalued' }),
    player({ player_id: 'rb', player_name: 'Jahmyr Gibbs', position: 'RB', model_rank: 1, adp_rank: 1, adp_diff: 0 })
  ]
}

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AdpRankingsView />
    </QueryClientProvider>
  )
}

describe('AdpRankingsView', () => {
  beforeEach(() => {
    vi.mocked(fetchAdpBoard).mockReset()
  })

  it('fetches the FFC half-PPR board by default and renders it read-only, ADP-sorted', async () => {
    vi.mocked(fetchAdpBoard).mockResolvedValue(BOARD)
    renderView()

    expect(await screen.findByText('Jahmyr Gibbs')).toBeInTheDocument()
    expect(fetchAdpBoard).toHaveBeenCalledWith('half_ppr', 2026, 'ffc')
    // Read-only: no pick controls on a public rankings page.
    expect(screen.queryByRole('button', { name: 'Draft' })).toBeNull()
    // Sorted by ADP: Gibbs (ADP 1) above Allen (ADP 32) even though Allen is listed first.
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('Jahmyr Gibbs')
    expect(rows[1]).toHaveTextContent('Josh Allen')
    expect(rows[1]).toHaveTextContent('+23.0')
  })

  it('shows a recovery hint instead of crashing when the ADP feed is missing', async () => {
    vi.mocked(fetchAdpBoard).mockRejectedValue(new Error('ADP data file not found'))
    renderView()

    expect(await screen.findByText(/ADP board unavailable/)).toBeInTheDocument()
    expect(screen.getByText(/refresh_adp\.py/)).toBeInTheDocument()
  })
})
