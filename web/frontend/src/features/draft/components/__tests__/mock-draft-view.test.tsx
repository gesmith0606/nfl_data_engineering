import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from 'vitest'
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MockDraftView } from '../mock-draft-view'
import { advanceMockDraft, undoMockDraftPick } from '@/features/nfl/api/service'
import { ApiError } from '@/lib/nfl/api'
import type { DraftConfig, MockDraftPickResponse } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained.
vi.mock('@/features/nfl/api/service', () => ({
  advanceMockDraft: vi.fn(),
  undoMockDraftPick: vi.fn()
}))

beforeAll(() => {
  // jsdom doesn't implement scrollIntoView; the auto-scroll-to-latest-pick effect needs it.
  window.HTMLElement.prototype.scrollIntoView = () => {}
})

const CONFIG: DraftConfig = {
  scoring: 'half_ppr',
  roster_format: 'standard',
  n_teams: 10,
  user_pick: 1,
  season: 2026,
  platform: 'sleeper'
}

function renderMockView(config: DraftConfig = CONFIG, timerSeconds: number | null = 15) {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <MockDraftView
        sessionId='s1'
        config={config}
        onReset={vi.fn()}
        timerSeconds={timerSeconds}
        accentColor='#7c3aed'
      />
    </QueryClientProvider>
  )
}

describe('MockDraftView — clock expiry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('auto-drafts the top recommendation (same action as clicking Advance Pick) when the clock expires on the user\'s turn, and shows an inline notice', async () => {
    const response: MockDraftPickResponse = {
      pick_number: 1,
      round_number: 1,
      is_user_turn: true,
      player_name: 'Bijan Robinson',
      position: 'RB',
      team: 'ATL',
      is_complete: false,
      draft_grade: null,
      total_pts: null,
      total_vorp: null
    }
    vi.mocked(advanceMockDraft).mockResolvedValue(response)

    // user_pick=1 -> the very first pick (pick 1) is the user's turn.
    renderMockView({ ...CONFIG, user_pick: 1 }, 15)

    expect(screen.getByRole('timer')).toHaveTextContent('0:15')

    await act(async () => {
      vi.advanceTimersByTime(15000)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(advanceMockDraft).toHaveBeenCalledWith({ session_id: 's1' })
    expect(screen.getByText('Clock expired — auto-drafted Bijan Robinson')).toBeInTheDocument()
    // The pick landed in the draft log too -- same effect as a manual advance.
    expect(screen.getByText('Bijan Robinson')).toBeInTheDocument()
  })

  it('does not auto-advance when the clock expires on a bot turn (bots are unaffected)', async () => {
    // user_pick=5, n_teams=10 -> pick 1 is on slot 1's clock, not the user's.
    renderMockView({ ...CONFIG, user_pick: 5 }, 15)

    await act(async () => {
      vi.advanceTimersByTime(15000)
      await Promise.resolve()
    })

    expect(advanceMockDraft).not.toHaveBeenCalled()
  })

  it('does not auto-advance when the pick clock is off (timerSeconds null)', async () => {
    renderMockView({ ...CONFIG, user_pick: 1 }, null)

    // No clock rendered at all when timerSeconds is null.
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()

    await act(async () => {
      vi.advanceTimersByTime(30000)
      await Promise.resolve()
    })

    expect(advanceMockDraft).not.toHaveBeenCalled()
  })
})

function mockPick(overrides: Partial<MockDraftPickResponse>): MockDraftPickResponse {
  return {
    pick_number: 1,
    round_number: 1,
    is_user_turn: false,
    player_name: 'Some Player',
    position: 'WR',
    team: 'DAL',
    is_complete: false,
    draft_grade: null,
    total_pts: null,
    total_vorp: null,
    ...overrides
  }
}

async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

describe('MockDraftView — bot burst', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // The 4th pick both lands on the user's turn AND completes the draft, so
  // the burst cleanly terminates (is_complete short-circuits before the
  // "start a fresh burst for what follows this user pick" branch) instead
  // of scheduling a new burst this fixture has no further picks queued for.
  const RESPONSES: MockDraftPickResponse[] = [
    mockPick({ pick_number: 1, is_user_turn: true, player_name: 'Me Pick' }),
    mockPick({ pick_number: 2, is_user_turn: false, player_name: 'Bot A' }),
    mockPick({ pick_number: 3, is_user_turn: false, player_name: 'Bot B' }),
    mockPick({ pick_number: 4, is_user_turn: true, player_name: 'Me Pick 2', is_complete: true })
  ]

  function queueResponses() {
    let call = 0
    vi.mocked(advanceMockDraft).mockImplementation(() => Promise.resolve(RESPONSES[call++]))
  }

  it('starts a bot-burst ticker after a user-turn pick and reveals bots at ~150ms intervals', async () => {
    queueResponses()
    renderMockView({ ...CONFIG, user_pick: 1 }, null)

    fireEvent.click(screen.getByRole('button', { name: 'Advance Pick' }))
    await act(flush)

    expect(screen.getByText('Me Pick')).toBeInTheDocument()
    expect(screen.getByText('Bots picking...')).toBeInTheDocument()

    await act(async () => {
      vi.advanceTimersByTime(150)
      await flush()
    })
    expect(screen.getByText('Bot A')).toBeInTheDocument()

    await act(async () => {
      vi.advanceTimersByTime(150)
      await flush()
    })
    expect(screen.getByText('Bot B')).toBeInTheDocument()

    await act(async () => {
      vi.advanceTimersByTime(150)
      await flush()
    })
    expect(screen.getByText('Me Pick 2')).toBeInTheDocument()
    expect(screen.queryByText('Bots picking...')).not.toBeInTheDocument()
  })

  it('Skip fast-forwards the remaining bot picks instantly, without waiting on the interval', async () => {
    queueResponses()
    renderMockView({ ...CONFIG, user_pick: 1 }, null)

    fireEvent.click(screen.getByRole('button', { name: 'Advance Pick' }))
    await act(flush)
    expect(screen.getByText('Bots picking...')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    await act(flush)
    await act(flush)
    await act(flush)

    expect(screen.getByText('Bot A')).toBeInTheDocument()
    expect(screen.getByText('Bot B')).toBeInTheDocument()
    expect(screen.getByText('Me Pick 2')).toBeInTheDocument()
    expect(screen.queryByText('Bots picking...')).not.toBeInTheDocument()
    expect(advanceMockDraft).toHaveBeenCalledTimes(4)
  })

  it('disables Advance Pick and Auto-Run while the bot burst is running', async () => {
    queueResponses()
    renderMockView({ ...CONFIG, user_pick: 1 }, null)

    fireEvent.click(screen.getByRole('button', { name: 'Advance Pick' }))
    await act(flush)

    expect(screen.getByRole('button', { name: 'Advance Pick' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Auto-Run/ })).toBeDisabled()
  })
})

describe('MockDraftView — undo', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('is disabled before any picks have been made', () => {
    renderMockView()
    expect(screen.getByRole('button', { name: /Undo my last pick/ })).toBeDisabled()
  })

  it('undoes the last pick and truncates the draft log', async () => {
    vi.mocked(advanceMockDraft).mockResolvedValue(mockPick({ player_name: 'To Be Undone', is_user_turn: false }))
    vi.mocked(undoMockDraftPick).mockResolvedValue({ success: true, pick_number: 0, message: '' })

    renderMockView()
    fireEvent.click(screen.getByRole('button', { name: 'Advance Pick' }))
    await act(flush)
    expect(screen.getByText('To Be Undone')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Undo my last pick/ }))
    await act(flush)

    expect(undoMockDraftPick).toHaveBeenCalledWith('s1')
    expect(screen.queryByText('To Be Undone')).not.toBeInTheDocument()
  })

  it('disables Undo with a tooltip after a 409 (nothing to undo)', async () => {
    vi.mocked(advanceMockDraft).mockResolvedValue(mockPick({ is_user_turn: false }))
    vi.mocked(undoMockDraftPick).mockRejectedValue(new ApiError('Conflict', 409))

    renderMockView()
    fireEvent.click(screen.getByRole('button', { name: 'Advance Pick' }))
    await act(flush)

    const undoButton = screen.getByRole('button', { name: /Undo my last pick/ })
    expect(undoButton).not.toBeDisabled()

    fireEvent.click(undoButton)

    await waitFor(() => expect(undoButton).toBeDisabled())
    expect(undoButton).toHaveAttribute('title', 'Nothing to undo')
  })
})
