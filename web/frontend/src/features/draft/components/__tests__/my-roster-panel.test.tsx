import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MyRosterPanel } from '../my-roster-panel'
import type { RosterRisk } from '@/lib/nfl/types'

function risk(overrides: Partial<RosterRisk>): RosterRisk {
  return {
    floor_sum: 800,
    ceiling_sum: 1200,
    projected_sum: 1000,
    volatility_index: 0.2,
    ...overrides
  }
}

describe('MyRosterPanel — roster risk meter', () => {
  it('renders nothing extra when rosterRisk is absent', () => {
    render(<MyRosterPanel roster={[]} remainingNeeds={{}} picksCount={0} />)
    expect(screen.queryByText('Roster Risk')).not.toBeInTheDocument()
  })

  it('shows floor/ceiling sums when rosterRisk is present', () => {
    render(
      <MyRosterPanel roster={[]} remainingNeeds={{}} picksCount={0} rosterRisk={risk({ floor_sum: 812, ceiling_sum: 1234 })} />
    )
    expect(screen.getByText('Roster Risk')).toBeInTheDocument()
    expect(screen.getByText('Floor 812 · Ceiling 1234')).toBeInTheDocument()
  })

  it('labels a low volatility_index as steady', () => {
    render(<MyRosterPanel roster={[]} remainingNeeds={{}} picksCount={0} rosterRisk={risk({ volatility_index: 0.2 })} />)
    expect(screen.getByText('Steady roster')).toBeInTheDocument()
  })

  it('labels a mid-range volatility_index as balanced', () => {
    render(<MyRosterPanel roster={[]} remainingNeeds={{}} picksCount={0} rosterRisk={risk({ volatility_index: 0.45 })} />)
    expect(screen.getByText('Balanced roster')).toBeInTheDocument()
  })

  it('labels a high volatility_index as volatile', () => {
    render(<MyRosterPanel roster={[]} remainingNeeds={{}} picksCount={0} rosterRisk={risk({ volatility_index: 0.7 })} />)
    expect(screen.getByText('Volatile roster — high ceiling, low floor')).toBeInTheDocument()
  })

  it('treats the 0.35 boundary as balanced (not steady)', () => {
    render(<MyRosterPanel roster={[]} remainingNeeds={{}} picksCount={0} rosterRisk={risk({ volatility_index: 0.35 })} />)
    expect(screen.getByText('Balanced roster')).toBeInTheDocument()
  })

  it('treats the 0.55 boundary as balanced (not volatile)', () => {
    render(<MyRosterPanel roster={[]} remainingNeeds={{}} picksCount={0} rosterRisk={risk({ volatility_index: 0.55 })} />)
    expect(screen.getByText('Balanced roster')).toBeInTheDocument()
  })

  it('omits the volatility bar/label when volatility_index is null', () => {
    render(
      <MyRosterPanel roster={[]} remainingNeeds={{}} picksCount={0} rosterRisk={risk({ volatility_index: null })} />
    )
    expect(screen.getByText('Roster Risk')).toBeInTheDocument()
    expect(screen.queryByText('Steady roster')).not.toBeInTheDocument()
    expect(screen.queryByText('Balanced roster')).not.toBeInTheDocument()
    expect(screen.queryByText('Volatile roster — high ceiling, low floor')).not.toBeInTheDocument()
  })
})
