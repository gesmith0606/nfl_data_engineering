import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LeagueContextChip } from '../league-context-chip'
import type { DraftConfig } from '@/lib/nfl/types'

const CONFIG: DraftConfig = {
  scoring: 'half_ppr',
  roster_format: 'standard',
  n_teams: 12,
  user_pick: 4,
  season: 2026,
  platform: 'espn'
}

describe('LeagueContextChip', () => {
  it('renders team count, scoring, platform, and pick number', () => {
    render(<LeagueContextChip config={CONFIG} onChange={vi.fn()} />)
    expect(screen.getByText('12-team')).toBeInTheDocument()
    expect(screen.getByText('Half PPR')).toBeInTheDocument()
    expect(screen.getByText('ESPN roster')).toBeInTheDocument()
    expect(screen.getByText('pick #4')).toBeInTheDocument()
  })

  it('calls onChange when Change is clicked', () => {
    const onChange = vi.fn()
    render(<LeagueContextChip config={CONFIG} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Change' }))
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('renders Custom without a "roster" suffix', () => {
    render(<LeagueContextChip config={{ ...CONFIG, platform: 'custom' }} onChange={vi.fn()} />)
    expect(screen.getByText('Custom')).toBeInTheDocument()
    expect(screen.queryByText('Custom roster')).not.toBeInTheDocument()
  })
})
