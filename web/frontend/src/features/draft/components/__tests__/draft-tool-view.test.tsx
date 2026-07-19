import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DraftToolView } from '../draft-tool-view'
import type { DraftBoardResponse } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained; keep the real
// module for everything not explicitly overridden (isConflictError, ApiError, ...).
vi.mock('@/lib/nfl/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/nfl/api')>()
  return {
    ...actual,
    fetchDraftBoard: vi.fn(),
    fetchStackHints: vi.fn(),
    fetchDraftPlatforms: vi.fn(),
    fetchLeagueOverview: vi.fn(),
    undoDraftPick: vi.fn()
  }
})

vi.mock('@/lib/nfl/connected-leagues', () => ({
  loadConnectedLeagues: vi.fn(() => [])
}))

import { fetchDraftBoard, fetchStackHints, fetchDraftPlatforms } from '@/lib/nfl/api'

const BOARD_RESPONSE: DraftBoardResponse = {
  session_id: 's1',
  players: [],
  my_roster: [],
  picks_taken: 0,
  my_pick_count: 0,
  remaining_needs: {},
  scoring_format: 'half_ppr',
  roster_format: 'standard',
  n_teams: 12
}

function renderTool() {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <DraftToolView />
    </QueryClientProvider>
  )
}

describe('DraftToolView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(fetchDraftBoard).mockResolvedValue(BOARD_RESPONSE)
    vi.mocked(fetchStackHints).mockResolvedValue({ hints: [] })
    vi.mocked(fetchDraftPlatforms).mockRejectedValue(new Error('404'))
  })

  it('shows the landing (mode chooser) by default instead of the board', () => {
    renderTool()
    expect(screen.getByText('Mock Draft')).toBeInTheDocument()
    expect(screen.getByText('Live Draft Co-Pilot')).toBeInTheDocument()
    expect(screen.getByText('Cheat Sheet Board')).toBeInTheDocument()
    // The manual board's toolbar (Board/Sleepers tabs) is not rendered yet.
    expect(screen.queryByRole('tab', { name: 'Board' })).not.toBeInTheDocument()
  })

  it('entering the Cheat Sheet Board hides the landing and shows the board toolbar', async () => {
    renderTool()
    fireEvent.click(screen.getByText('Cheat Sheet Board'))

    expect(await screen.findByRole('tab', { name: 'Board' })).toBeInTheDocument()
    // The landing's mode-card heading is gone (the toolbar's "Mock Draft" button, a
    // pre-existing feature, is a different element and legitimately still present).
    expect(screen.queryByRole('heading', { name: 'Mock Draft' })).not.toBeInTheDocument()
  })

  it('shows the first-run cheat-sheet banner on first board entry and Got it dismisses + persists it', async () => {
    renderTool()
    fireEvent.click(screen.getByText('Cheat Sheet Board'))
    await screen.findByRole('tab', { name: 'Board' })

    expect(await screen.findByText(/This is your cheat sheet/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Got it' }))
    expect(screen.queryByText(/This is your cheat sheet/)).not.toBeInTheDocument()
    expect(localStorage.getItem('nfl.draftBoardBannerSeen')).toBe('1')
  })

  it('does not show the cheat-sheet banner again once the flag is already set', async () => {
    localStorage.setItem('nfl.draftBoardBannerSeen', '1')
    renderTool()
    fireEvent.click(screen.getByText('Cheat Sheet Board'))
    await screen.findByRole('tab', { name: 'Board' })

    expect(screen.queryByText(/This is your cheat sheet/)).not.toBeInTheDocument()
  })

  it('Reset returns to the landing', async () => {
    renderTool()
    fireEvent.click(screen.getByText('Cheat Sheet Board'))
    await screen.findByRole('tab', { name: 'Board' })

    fireEvent.click(screen.getByRole('button', { name: /Reset/ }))

    expect(await screen.findByText('Mock Draft')).toBeInTheDocument()
    expect(await screen.findByText('Cheat Sheet Board')).toBeInTheDocument()
  })

  it('the board toolbar "How this works" button opens board-specific guidance', async () => {
    renderTool()
    fireEvent.click(screen.getByText('Cheat Sheet Board'))
    await screen.findByRole('tab', { name: 'Board' })

    fireEvent.click(screen.getByRole('button', { name: /How this works/ }))
    expect(await screen.findByText('The cheat sheet board')).toBeInTheDocument()
  })

  it('shows the active league context chip once inside the board, with a working Change action', async () => {
    renderTool()
    fireEvent.click(screen.getByText('Cheat Sheet Board'))
    await screen.findByRole('tab', { name: 'Board' })

    expect(screen.getByText('12-team')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Change' }))
    expect(await screen.findByRole('dialog', { name: 'Draft Settings' })).toBeInTheDocument()
  })

  it('entering Live Draft Co-Pilot from the landing hides the landing and shows the live tabs', () => {
    renderTool()
    fireEvent.click(screen.getByText('Live Draft Co-Pilot'))

    expect(screen.getByRole('tab', { name: /sleeper/i })).toBeInTheDocument()
    expect(screen.queryByText('Cheat Sheet Board')).not.toBeInTheDocument()
  })

  it('opening Mock Draft from the landing opens the setup dialog without leaving the landing behind it', () => {
    renderTool()
    fireEvent.click(screen.getByText('Mock Draft'))

    expect(screen.getByRole('dialog', { name: 'Mock Draft Setup' })).toBeInTheDocument()
  })

  it("opening Settings from the landing's Custom option opens the draft settings dialog", () => {
    renderTool()
    fireEvent.click(screen.getByText('Custom'))

    expect(screen.getByRole('dialog', { name: 'Draft Settings' })).toBeInTheDocument()
  })

  it('waits for the query settle before assertions relying on fetchDraftBoard', async () => {
    renderTool()
    fireEvent.click(screen.getByText('Cheat Sheet Board'))
    await waitFor(() => expect(fetchDraftBoard).toHaveBeenCalled())
  })
})
