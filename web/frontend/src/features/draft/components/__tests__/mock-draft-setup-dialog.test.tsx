import { useState } from 'react'
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MockDraftSetupDialog } from '../mock-draft-setup-dialog'
import { fetchDraftPlatforms } from '@/lib/nfl/api'
import type { DraftConfig } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained.
vi.mock('@/lib/nfl/api', () => ({
  fetchDraftPlatforms: vi.fn()
}))

beforeAll(() => {
  // Radix Select needs these in jsdom (no real layout/pointer capture support).
  window.HTMLElement.prototype.hasPointerCapture = () => false
  window.HTMLElement.prototype.scrollIntoView = () => {}
  window.HTMLElement.prototype.releasePointerCapture = () => {}
})

const BASE_CONFIG: DraftConfig = {
  scoring: 'half_ppr',
  roster_format: 'standard',
  n_teams: 12,
  user_pick: 1,
  season: 2026,
  platform: 'sleeper'
}

interface WrapperProps {
  initialConfig: DraftConfig
  onStartMock: (overrides?: Partial<DraftConfig>) => void
  configRef: { current: DraftConfig }
}

/** Stateful harness — MockDraftSetupDialog's Selects are controlled by `config`,
 * so a real onConfigChange -> setConfig round trip is required for edits to render. */
function Wrapper({ initialConfig, onStartMock, configRef }: WrapperProps) {
  const [client] = useState(() => new QueryClient())
  const [config, setConfig] = useState(initialConfig)
  configRef.current = config
  return (
    <QueryClientProvider client={client}>
      <MockDraftSetupDialog
        config={config}
        onConfigChange={setConfig}
        onStartMock={onStartMock}
        open
        onOpenChange={() => {}}
      />
    </QueryClientProvider>
  )
}

function openSelect(labelText: string) {
  fireEvent.click(screen.getByLabelText(labelText))
}

describe('MockDraftSetupDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Hang the query so every test renders from FALLBACK_PLATFORM_PRESETS
    // (deterministic, no need to await a resolved promise).
    vi.mocked(fetchDraftPlatforms).mockReturnValue(new Promise(() => {}))
  })

  it('renders the draft room style toggle (ESPN/Sleeper/Yahoo/Custom)', () => {
    render(
      <Wrapper initialConfig={BASE_CONFIG} onStartMock={vi.fn()} configRef={{ current: BASE_CONFIG }} />
    )
    expect(screen.getByRole('radio', { name: /ESPN draft room style/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Sleeper draft room style/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Yahoo draft room style/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Custom draft room style/i })).toBeInTheDocument()
  })

  it('renders the pick slot selector with 1..n_teams options plus Random, prominently', () => {
    render(
      <Wrapper
        initialConfig={{ ...BASE_CONFIG, n_teams: 8 }}
        onStartMock={vi.fn()}
        configRef={{ current: BASE_CONFIG }}
      />
    )
    expect(screen.getByText('Your pick slot')).toBeInTheDocument()
    openSelect('Your pick slot')
    const options = screen.getAllByRole('option').map(o => o.textContent)
    expect(options).toEqual(['Random', 'Pick #1', 'Pick #2', 'Pick #3', 'Pick #4', 'Pick #5', 'Pick #6', 'Pick #7', 'Pick #8'])
  })

  it('renders all pick-clock timer options (Off/15s/30s/60s/90s)', () => {
    render(
      <Wrapper initialConfig={BASE_CONFIG} onStartMock={vi.fn()} configRef={{ current: BASE_CONFIG }} />
    )
    openSelect('Pick clock')
    const options = screen.getAllByRole('option').map(o => o.textContent)
    expect(options).toEqual(['Off', '15s', '30s', '60s', '90s'])
  })

  it('renders both rankings (ADP) source options', () => {
    render(
      <Wrapper initialConfig={BASE_CONFIG} onStartMock={vi.fn()} configRef={{ current: BASE_CONFIG }} />
    )
    openSelect('Rankings (ADP) source')
    const options = screen.getAllByRole('option').map(o => o.textContent)
    expect(options).toEqual(['Consensus ADP (FantasyPros-style, via FFC)', 'ESPN ADP'])
  })

  it('defaults rankings source to ESPN ADP for the espn platform, Consensus otherwise', () => {
    const espnRender = render(
      <Wrapper
        initialConfig={{ ...BASE_CONFIG, platform: 'espn' }}
        onStartMock={vi.fn()}
        configRef={{ current: BASE_CONFIG }}
      />
    )
    expect(screen.getByLabelText('Rankings (ADP) source')).toHaveTextContent('ESPN ADP')
    espnRender.unmount()

    render(
      <Wrapper
        initialConfig={{ ...BASE_CONFIG, platform: 'sleeper' }}
        onStartMock={vi.fn()}
        configRef={{ current: BASE_CONFIG }}
      />
    )
    expect(screen.getByLabelText('Rankings (ADP) source')).toHaveTextContent(
      'Consensus ADP (FantasyPros-style, via FFC)'
    )
  })

  it('locks scoring/roster format to the platform preset, and unlocking switches to custom', () => {
    render(
      <Wrapper
        initialConfig={{ ...BASE_CONFIG, platform: 'sleeper' }}
        onStartMock={vi.fn()}
        configRef={{ current: BASE_CONFIG }}
      />
    )
    expect(screen.getByLabelText('Scoring')).toBeDisabled()
    expect(screen.getByLabelText('Roster Format')).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Unlock to customize' }))

    expect(screen.getByLabelText('Scoring')).not.toBeDisabled()
    expect(screen.getByLabelText('Roster Format')).not.toBeDisabled()
  })

  it('leaves scoring/roster format editable for Custom from the start', () => {
    render(
      <Wrapper
        initialConfig={{ ...BASE_CONFIG, platform: 'custom' }}
        onStartMock={vi.fn()}
        configRef={{ current: BASE_CONFIG }}
      />
    )
    expect(screen.getByLabelText('Scoring')).not.toBeDisabled()
    expect(screen.getByLabelText('Roster Format')).not.toBeDisabled()
  })

  it('Start Mock Draft resolves the chosen platform/slot/timer/rankings before firing onStartMock', () => {
    const onStartMock = vi.fn()
    const configRef = { current: BASE_CONFIG }
    render(
      <Wrapper
        initialConfig={{ ...BASE_CONFIG, platform: 'sleeper', n_teams: 10 }}
        onStartMock={onStartMock}
        configRef={configRef}
      />
    )

    openSelect('Your pick slot')
    fireEvent.click(screen.getByRole('option', { name: 'Pick #4' }))

    openSelect('Pick clock')
    fireEvent.click(screen.getByRole('option', { name: '15s' }))

    openSelect('Rankings (ADP) source')
    fireEvent.click(screen.getByRole('option', { name: 'ESPN ADP' }))

    fireEvent.click(screen.getByRole('button', { name: 'Start Mock Draft' }))

    // A concrete slot was picked (not Random) -- no override needed, the
    // resolved config (asserted below) already carries user_pick.
    expect(onStartMock).toHaveBeenCalledTimes(1)
    expect(onStartMock).toHaveBeenCalledWith({})
    expect(configRef.current).toMatchObject({
      platform: 'sleeper',
      n_teams: 10,
      user_pick: 4,
      timer_seconds: 15,
      adp_source: 'espn'
    })
  })

  it('Random pick slot resolves to an in-range slot via onStartMock overrides', () => {
    const onStartMock = vi.fn()
    render(
      <Wrapper
        initialConfig={{ ...BASE_CONFIG, n_teams: 10 }}
        onStartMock={onStartMock}
        configRef={{ current: BASE_CONFIG }}
      />
    )

    openSelect('Your pick slot')
    fireEvent.click(screen.getByRole('option', { name: 'Random' }))

    fireEvent.click(screen.getByRole('button', { name: 'Start Mock Draft' }))

    expect(onStartMock).toHaveBeenCalledTimes(1)
    const overrides = onStartMock.mock.calls[0][0] as Partial<DraftConfig>
    expect(overrides.user_pick).toBeGreaterThanOrEqual(1)
    expect(overrides.user_pick).toBeLessThanOrEqual(10)
  })
})
