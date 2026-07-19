import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DraftLanding, DRAFT_TOUR_SEEN_KEY } from '../draft-landing'
import { fetchDraftPlatforms, fetchLeagueOverview } from '@/lib/nfl/api'
import { loadConnectedLeagues } from '@/lib/nfl/connected-leagues'
import type { ConnectedLeague, DraftConfig, LeagueOverviewResponse } from '@/lib/nfl/types'

// vi.mock is hoisted — factories must be self-contained.
vi.mock('@/lib/nfl/api', () => ({
  fetchDraftPlatforms: vi.fn(),
  fetchLeagueOverview: vi.fn()
}))
vi.mock('@/lib/nfl/connected-leagues', () => ({
  loadConnectedLeagues: vi.fn()
}))

const BASE_CONFIG: DraftConfig = {
  scoring: 'half_ppr',
  roster_format: 'standard',
  n_teams: 12,
  user_pick: 1,
  season: 2026,
  platform: 'custom'
}

const LEAGUE: ConnectedLeague = {
  league_id: 'L1',
  league_name: 'The League',
  season: '2026',
  user_id: 'U1',
  username: 'gforceee',
  roster_positions: ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'BN'],
  scoring_format_label: 'Full PPR (league)',
  connected_at: '2026-07-17T00:00:00.000Z'
}

const OVERVIEW: LeagueOverviewResponse = {
  league_id: 'L1',
  league_name: 'The League',
  season: '2026',
  status: 'in_season',
  total_rosters: 10,
  roster_positions: ['QB', 'QB', 'RB', 'WR', 'WR', 'TE', 'BN'],
  scoring_format_label: 'Half PPR (league)',
  scoring_deltas: [],
  unmodeled_keys: [],
  user_roster: []
}

function renderLanding(config: DraftConfig = BASE_CONFIG, onConfigChange = vi.fn()) {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <DraftLanding
        config={config}
        onConfigChange={onConfigChange}
        onOpenMockSetup={vi.fn()}
        onEnterLive={vi.fn()}
        onEnterBoard={vi.fn()}
        onOpenSettings={vi.fn()}
        onOpenHowItWorks={vi.fn()}
      />
    </QueryClientProvider>
  )
  return onConfigChange
}

describe('DraftLanding', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(fetchDraftPlatforms).mockReturnValue(new Promise(() => {}))
    vi.mocked(loadConnectedLeagues).mockReturnValue([])
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('renders the three mode cards', () => {
    renderLanding()
    expect(screen.getByText('Mock Draft')).toBeInTheDocument()
    expect(screen.getByText('Live Draft Co-Pilot')).toBeInTheDocument()
    expect(screen.getByText('Cheat Sheet Board')).toBeInTheDocument()
  })

  it('invokes the right callback when each mode card is clicked', () => {
    const client = new QueryClient()
    const onOpenMockSetup = vi.fn()
    const onEnterLive = vi.fn()
    const onEnterBoard = vi.fn()
    render(
      <QueryClientProvider client={client}>
        <DraftLanding
          config={BASE_CONFIG}
          onConfigChange={vi.fn()}
          onOpenMockSetup={onOpenMockSetup}
          onEnterLive={onEnterLive}
          onEnterBoard={onEnterBoard}
          onOpenSettings={vi.fn()}
          onOpenHowItWorks={vi.fn()}
        />
      </QueryClientProvider>
    )

    fireEvent.click(screen.getByText('Mock Draft'))
    expect(onOpenMockSetup).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByText('Live Draft Co-Pilot'))
    expect(onEnterLive).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByText('Cheat Sheet Board'))
    expect(onEnterBoard).toHaveBeenCalledTimes(1)
  })

  it('shows an empty state with a link to /dashboard/leagues when no leagues are connected', () => {
    renderLanding()
    expect(screen.getByText('No leagues connected yet.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Connect your Sleeper league' })).toHaveAttribute(
      'href',
      '/dashboard/leagues'
    )
  })

  it('lists connected leagues with name and scoring label', () => {
    vi.mocked(loadConnectedLeagues).mockReturnValue([LEAGUE])
    renderLanding()
    expect(screen.getByText('The League')).toBeInTheDocument()
    expect(screen.getByText('Full PPR (league)')).toBeInTheDocument()
  })

  it('clicking a connected league fetches the overview and maps it onto the config, incl. clamping and scoring parsing', async () => {
    vi.mocked(loadConnectedLeagues).mockReturnValue([LEAGUE])
    vi.mocked(fetchLeagueOverview).mockResolvedValue(OVERVIEW)
    const onConfigChange = renderLanding(BASE_CONFIG)

    fireEvent.click(screen.getByText('The League'))

    await waitFor(() => expect(onConfigChange).toHaveBeenCalled())
    expect(fetchLeagueOverview).toHaveBeenCalledWith('L1', 'U1')
    expect(onConfigChange).toHaveBeenCalledWith(
      expect.objectContaining({
        n_teams: 10, // clamps total_rosters=10 to the supported 10
        scoring: 'half_ppr', // 'Half PPR (league)' -> half_ppr
        roster_format: '2qb', // two QB slots, no SUPER_FLEX
        platform: 'sleeper',
        adp_source: 'sleeper'
      })
    )
    await screen.findByText(/Approximated from your league settings/)
  })

  it('shows an inline error and falls back to manual choice when the league fetch fails', async () => {
    vi.mocked(loadConnectedLeagues).mockReturnValue([LEAGUE])
    vi.mocked(fetchLeagueOverview).mockRejectedValue(new Error('network error'))
    const onConfigChange = renderLanding(BASE_CONFIG)

    fireEvent.click(screen.getByText('The League'))

    await screen.findByText(/Couldn't load that league's settings/)
    expect(onConfigChange).not.toHaveBeenCalled()
  })

  it('applies a platform-room preset via the Platform room chooser', async () => {
    vi.mocked(fetchDraftPlatforms).mockResolvedValue({
      espn: { scoring_format: 'standard', roster_format: 'superflex', rounds: 16, timer_seconds: 90, adp_source: 'espn', roster_slots: {} },
      sleeper: { scoring_format: 'half_ppr', roster_format: 'standard', rounds: 15, timer_seconds: 60, adp_source: 'sleeper', roster_slots: {} },
      yahoo: { scoring_format: 'ppr', roster_format: '2qb', rounds: 16, timer_seconds: 90, adp_source: 'yahoo', roster_slots: {} },
      custom: { scoring_format: 'half_ppr', roster_format: 'standard', rounds: 15, timer_seconds: 60, adp_source: 'custom', roster_slots: {} }
    })
    const onConfigChange = renderLanding(BASE_CONFIG)

    // Retry the click until the platform-presets query has resolved and the
    // resulting config reflects the real (non-fallback) ESPN preset.
    await waitFor(() => {
      fireEvent.click(screen.getByText('ESPN'))
      expect(onConfigChange).toHaveBeenCalledWith(
        expect.objectContaining({ platform: 'espn', scoring: 'standard', roster_format: 'superflex' })
      )
    })
  })

  it('shows the first-run intro panel when the tour flag is unset, and dismissing it sets the flag', () => {
    renderLanding()
    expect(screen.getByText(/Set your league — connect Sleeper/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Got it' }))
    expect(localStorage.getItem(DRAFT_TOUR_SEEN_KEY)).toBe('1')
    expect(screen.queryByText(/Set your league — connect Sleeper/)).not.toBeInTheDocument()
  })

  it('hides the intro panel on a later visit once the tour flag is set', () => {
    localStorage.setItem(DRAFT_TOUR_SEEN_KEY, '1')
    renderLanding()
    expect(screen.queryByText(/Set your league — connect Sleeper/)).not.toBeInTheDocument()
  })

  it('calls onOpenHowItWorks from the persistent "How this works" button', () => {
    const client = new QueryClient()
    const onOpenHowItWorks = vi.fn()
    render(
      <QueryClientProvider client={client}>
        <DraftLanding
          config={BASE_CONFIG}
          onConfigChange={vi.fn()}
          onOpenMockSetup={vi.fn()}
          onEnterLive={vi.fn()}
          onEnterBoard={vi.fn()}
          onOpenSettings={vi.fn()}
          onOpenHowItWorks={onOpenHowItWorks}
        />
      </QueryClientProvider>
    )
    fireEvent.click(screen.getByRole('button', { name: /How this works/ }))
    expect(onOpenHowItWorks).toHaveBeenCalledTimes(1)
  })
})
