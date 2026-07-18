import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RecommendationsPanel } from '../recommendations-panel'
import { fetchDraftRecommendations } from '@/lib/nfl/api'
import type { DraftPlayer, DraftRecommendationsResponse } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained.
vi.mock('@/lib/nfl/api', () => ({
  fetchDraftRecommendations: vi.fn()
}))

function rec(overrides: Partial<DraftRecommendationsResponse['recommendations'][number]>) {
  return {
    player_id: 'p1',
    player_name: 'Test Player',
    position: 'WR',
    team: 'KC',
    projected_points: 200,
    model_rank: 1,
    vorp: 10,
    recommendation_score: 1,
    ...overrides
  }
}

function player(overrides: Partial<DraftPlayer>): DraftPlayer {
  return {
    player_id: overrides.player_id ?? 'x',
    player_name: overrides.player_name ?? 'X',
    position: 'WR',
    team: 'KC',
    projected_points: 100,
    model_rank: 1,
    adp_rank: 1,
    adp_diff: 0,
    value_tier: 'fair_value',
    vorp: 5,
    ...overrides
  }
}

function renderPanel(recommendations: DraftRecommendationsResponse['recommendations'], players: DraftPlayer[] = []) {
  vi.mocked(fetchDraftRecommendations).mockResolvedValue({
    recommendations,
    reasoning: '',
    remaining_needs: {}
  })
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <RecommendationsPanel sessionId='s1' positionFilter='ALL' players={players} />
    </QueryClientProvider>
  )
}

describe('RecommendationsPanel — gone_probability', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the gone-by-next-pick line when gone_probability is present', async () => {
    renderPanel([rec({ gone_probability: 0.5 })])

    expect(await screen.findByText('50% gone by your next pick')).toBeInTheDocument()
  })

  it('hides the line when gone_probability is null', async () => {
    renderPanel([rec({ player_name: 'No Prob', gone_probability: null })])

    expect(await screen.findByText('No Prob')).toBeInTheDocument()
    expect(screen.queryByText(/gone by your next pick/)).not.toBeInTheDocument()
  })

  it('uses the danger color above 70%', async () => {
    renderPanel([rec({ gone_probability: 0.85 })])

    const line = await screen.findByText('85% gone by your next pick')
    expect(line.className).toContain('--danger')
  })

  it('uses the muted color below 30%', async () => {
    renderPanel([rec({ gone_probability: 0.1 })])

    const line = await screen.findByText('10% gone by your next pick')
    expect(line.className).toContain('text-muted-foreground')
  })
})

describe('RecommendationsPanel — tier exhaustion', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a warning line when a position has <=2 players left in its top tier', async () => {
    renderPanel(
      [rec({})],
      [
        player({ player_id: 'a', position: 'TE', tier: 2 }),
        player({ player_id: 'b', position: 'TE', tier: 3 })
      ]
    )

    expect(await screen.findByText('TE Tier 2: 1 left')).toBeInTheDocument()
  })

  it('does not show a warning when 3+ players remain in the top tier', async () => {
    renderPanel(
      [rec({})],
      [
        player({ player_id: 'a', position: 'RB', tier: 1 }),
        player({ player_id: 'b', position: 'RB', tier: 1 }),
        player({ player_id: 'c', position: 'RB', tier: 1 })
      ]
    )

    await screen.findByText('Test Player')
    expect(screen.queryByText(/RB Tier/)).not.toBeInTheDocument()
  })
})
