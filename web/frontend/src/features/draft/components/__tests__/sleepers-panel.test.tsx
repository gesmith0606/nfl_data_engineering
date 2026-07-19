import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SleepersPanel } from '../sleepers-panel'
import { fetchSleepers } from '@/lib/nfl/api'
import type { SleeperEdge, SleepersResponse } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained.
vi.mock('@/lib/nfl/api', () => ({
  fetchSleepers: vi.fn(),
  normalizeSleepers: (data: SleepersResponse | undefined) =>
    !data ? [] : Array.isArray(data) ? data : data.sleepers
}))

function sleeper(overrides: Partial<SleeperEdge>): SleeperEdge {
  return {
    player_name: 'Test Player',
    position: 'WR',
    team: 'KC',
    model_rank: 40,
    adp_rank: 70,
    adp_gap: 30,
    projected_points: 150,
    reason: 'Model likes the target share more than the market does.',
    ...overrides
  }
}

function renderPanel(response: SleepersResponse) {
  vi.mocked(fetchSleepers).mockResolvedValue(response)
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <SleepersPanel sessionId='s1' />
    </QueryClientProvider>
  )
}

describe('SleepersPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders sleeper cards with rank/ADP gap and reason', async () => {
    renderPanel({ sleepers: [sleeper({})] })

    expect(await screen.findByText('Test Player')).toBeInTheDocument()
    expect(screen.getByText(/Rank 40/)).toBeInTheDocument()
    expect(screen.getByText(/ADP 70/)).toBeInTheDocument()
    expect(screen.getByText('Model likes the target share more than the market does.')).toBeInTheDocument()
  })

  it('accepts a bare-array envelope (integration-shape fallback)', async () => {
    renderPanel([sleeper({ player_name: 'Bare Array Player' })])

    expect(await screen.findByText('Bare Array Player')).toBeInTheDocument()
  })

  it('shows the empty state when there are no sleeper edges', async () => {
    renderPanel({ sleepers: [] })

    expect(await screen.findByText('No sleeper edges right now.')).toBeInTheDocument()
  })

  it('shows the empty state (not an error) when the endpoint fails', async () => {
    vi.mocked(fetchSleepers).mockRejectedValue(new Error('404'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <SleepersPanel sessionId='s1' />
      </QueryClientProvider>
    )

    expect(await screen.findByText('No sleeper edges right now.')).toBeInTheDocument()
  })

  it('prompts to initialize a draft when there is no session', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SleepersPanel sessionId={null} />
      </QueryClientProvider>
    )

    expect(screen.getByText('Initialize a draft to see sleepers.')).toBeInTheDocument()
  })
})
