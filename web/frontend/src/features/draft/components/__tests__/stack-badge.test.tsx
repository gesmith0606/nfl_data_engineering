import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StackBadge } from '../stack-badge'
import type { StackHint } from '@/lib/nfl/types'

function hint(overrides: Partial<StackHint>): StackHint {
  return {
    player_name: 'Puka Nacua',
    position: 'WR',
    team: 'LAR',
    rostered_player_name: 'Matthew Stafford',
    rho: 0.51,
    n_games: 32,
    kind: 'stack_bonus',
    ...overrides
  }
}

describe('StackBadge', () => {
  it('renders a mint STACK badge with the rho bonus and rostered player for stack_bonus', () => {
    render(<StackBadge hint={hint({ kind: 'stack_bonus', rho: 0.51, rostered_player_name: 'Goff' })} />)

    const badge = screen.getByText('STACK +0.51 w/ Goff')
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain('--success')
  })

  it('renders an amber overlap badge for shared_ceiling_warning', () => {
    render(<StackBadge hint={hint({ kind: 'shared_ceiling_warning', rostered_player_name: 'Kupp' })} />)

    const badge = screen.getByText('overlap w/ Kupp')
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain('--warn')
  })

  it('formats a negative rho without a double sign', () => {
    render(<StackBadge hint={hint({ kind: 'stack_bonus', rho: -0.2, rostered_player_name: 'Someone' })} />)

    expect(screen.getByText('STACK -0.20 w/ Someone')).toBeInTheDocument()
  })
})
