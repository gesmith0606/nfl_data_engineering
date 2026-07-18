import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MockDraftView } from '../mock-draft-view'
import { advanceMockDraft } from '@/features/nfl/api/service'
import type { DraftConfig, MockDraftPickResponse } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained.
vi.mock('@/features/nfl/api/service', () => ({
  advanceMockDraft: vi.fn()
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
