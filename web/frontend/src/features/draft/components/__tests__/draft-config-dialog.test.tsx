import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DraftConfigDialog } from '../draft-config-dialog'
import { fetchDraftPlatforms } from '@/lib/nfl/api'
import type { DraftConfig, DraftPlatformsResponse } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained.
vi.mock('@/lib/nfl/api', () => ({
  fetchDraftPlatforms: vi.fn()
}))

const PLATFORMS: DraftPlatformsResponse = {
  espn: {
    scoring_format: 'standard',
    roster_format: 'superflex',
    rounds: 16,
    timer_seconds: 90,
    adp_source: 'espn',
    roster_slots: {}
  },
  sleeper: {
    scoring_format: 'half_ppr',
    roster_format: 'standard',
    rounds: 15,
    timer_seconds: 60,
    adp_source: 'sleeper',
    roster_slots: {}
  },
  yahoo: {
    scoring_format: 'ppr',
    roster_format: '2qb',
    rounds: 16,
    timer_seconds: 90,
    adp_source: 'yahoo',
    roster_slots: {}
  },
  // Deliberately different from the hardcoded fallback (15/60s) so tests can
  // confirm the mocked query actually resolved before interacting further —
  // BASE_CONFIG starts on 'custom', so this text is visible immediately.
  custom: {
    scoring_format: 'half_ppr',
    roster_format: 'standard',
    rounds: 20,
    timer_seconds: 45,
    adp_source: 'custom',
    roster_slots: {}
  }
}

const BASE_CONFIG: DraftConfig = {
  scoring: 'half_ppr',
  roster_format: 'standard',
  n_teams: 12,
  user_pick: 1,
  season: 2026,
  platform: 'custom'
}

function renderDialog(config: DraftConfig, onConfigChange = vi.fn()) {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <DraftConfigDialog
        config={config}
        onConfigChange={onConfigChange}
        open
        onOpenChange={vi.fn()}
        onNewDraft={vi.fn()}
      />
    </QueryClientProvider>
  )
  return onConfigChange
}

describe('DraftConfigDialog — platform selector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('applies the platform preset (scoring + roster format) and locks the fields', async () => {
    vi.mocked(fetchDraftPlatforms).mockResolvedValue(PLATFORMS)
    const onConfigChange = renderDialog(BASE_CONFIG)
    // BASE_CONFIG starts on 'custom' — wait for the mocked presets to land
    // (the rounds/timer line updates from the fallback 15/60s to 20/45s)
    // before clicking, so the click reads real preset data, not fallback.
    await screen.findByText('20 rounds · 45s pick clock')

    fireEvent.click(screen.getByRole('radio', { name: /ESPN draft room style/i }))

    expect(onConfigChange).toHaveBeenCalledWith(
      expect.objectContaining({
        platform: 'espn',
        scoring: 'standard',
        roster_format: 'superflex'
      })
    )
  })

  it('disables scoring and roster format selects once locked to a platform', () => {
    vi.mocked(fetchDraftPlatforms).mockReturnValue(new Promise(() => {}))
    renderDialog({ ...BASE_CONFIG, platform: 'sleeper' })

    expect(screen.getByLabelText('Scoring')).toBeDisabled()
    expect(screen.getByLabelText('Roster Format')).toBeDisabled()
  })

  it('leaves scoring and roster format editable for Custom', () => {
    vi.mocked(fetchDraftPlatforms).mockReturnValue(new Promise(() => {}))
    renderDialog({ ...BASE_CONFIG, platform: 'custom' })

    expect(screen.getByLabelText('Scoring')).not.toBeDisabled()
    expect(screen.getByLabelText('Roster Format')).not.toBeDisabled()
  })

  it('"Unlock to customize" switches the platform to custom without changing scoring/roster', () => {
    vi.mocked(fetchDraftPlatforms).mockReturnValue(new Promise(() => {}))
    const onConfigChange = renderDialog({ ...BASE_CONFIG, platform: 'sleeper' })

    fireEvent.click(screen.getByRole('button', { name: 'Unlock to customize' }))

    expect(onConfigChange).toHaveBeenCalledWith(
      expect.objectContaining({
        platform: 'custom',
        scoring: 'half_ppr',
        roster_format: 'standard'
      })
    )
  })

  it('falls back to hardcoded presets when the platforms endpoint fails', async () => {
    vi.mocked(fetchDraftPlatforms).mockRejectedValue(new Error('404'))
    const onConfigChange = renderDialog(BASE_CONFIG)
    // The fallback rounds/timer line is present from the very first render
    // (no query round-trip needed) — wait for it explicitly so the query has
    // had a chance to settle into its error state before clicking.
    await screen.findByText('15 rounds · 60s pick clock')

    fireEvent.click(screen.getByRole('radio', { name: /Sleeper draft room style/i }))

    expect(onConfigChange).toHaveBeenCalledWith(
      expect.objectContaining({ platform: 'sleeper', scoring: 'half_ppr', roster_format: 'standard' })
    )
  })
})
