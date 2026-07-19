import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DraftIntelPanel } from '../draft-intel-panel'
import { fetchDraftIntel } from '@/lib/nfl/api'
import type { DraftIntelResponse } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained.
vi.mock('@/lib/nfl/api', () => ({
  fetchDraftIntel: vi.fn()
}))

function renderPanel(leagueId: string | null, response?: DraftIntelResponse) {
  if (response) vi.mocked(fetchDraftIntel).mockResolvedValue(response)
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <DraftIntelPanel leagueId={leagueId} />
    </QueryClientProvider>
  )
}

describe('DraftIntelPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when there is no known league_id', () => {
    const { container } = renderPanel(null)
    expect(container).toBeEmptyDOMElement()
  })

  it('explains it needs league history when there are no managers, without an error', async () => {
    renderPanel('lg1', { league_id: 'lg1', seasons_analyzed: 0, managers: [] })

    fireEvent.click(screen.getByRole('button', { name: /Opponent Intel/ }))
    expect(
      await screen.findByText(/Needs league draft history to build tendencies/)
    ).toBeInTheDocument()
  })

  it('degrades to the empty state (not an error) when the endpoint fails', async () => {
    vi.mocked(fetchDraftIntel).mockRejectedValue(new Error('404'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <DraftIntelPanel leagueId='lg1' />
      </QueryClientProvider>
    )

    fireEvent.click(screen.getByRole('button', { name: /Opponent Intel/ }))
    expect(
      await screen.findByText(/Needs league draft history to build tendencies/)
    ).toBeInTheDocument()
  })

  it('lists each manager summary once expanded', async () => {
    renderPanel('lg1', {
      league_id: 'lg1',
      seasons_analyzed: 3,
      managers: [
        {
          user_id: 'u1',
          display_name: 'Alice',
          team_name: 'Alice Team',
          tendencies: 'reaches for RBs',
          summary: ['Reaches for RBs early.', 'Ignores TE until round 10.']
        }
      ]
    })

    fireEvent.click(screen.getByRole('button', { name: /Opponent Intel/ }))
    expect(await screen.findByText(/Alice/)).toBeInTheDocument()
    expect(screen.getByText('Reaches for RBs early.')).toBeInTheDocument()
    expect(screen.getByText('Ignores TE until round 10.')).toBeInTheDocument()
  })
})
