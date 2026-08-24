import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DraftBoardTable } from '../draft-board-table'
import type { DraftPlayer, StackHint } from '@/lib/nfl/types'

function player(overrides: Partial<DraftPlayer>): DraftPlayer {
  return {
    player_id: 'p1',
    player_name: 'Test Player',
    position: 'WR',
    team: 'KC',
    projected_points: 200,
    model_rank: 1,
    adp_rank: 1,
    adp_diff: 0,
    value_tier: 'fair_value',
    vorp: 10,
    ...overrides
  }
}

describe('DraftBoardTable', () => {
  it('renders DST rows with dash placeholders when projections/vorp are null', () => {
    render(
      <DraftBoardTable
        players={[
          player({
            player_id: 'dst1',
            player_name: 'Chiefs D/ST',
            position: 'DST',
            team: 'KC',
            projected_points: null,
            vorp: null,
            adp_rank: 40,
            model_rank: 120
          })
        ]}
        positionFilter='DST'
        onDraft={vi.fn()}
        isPicking={false}
      />
    )

    expect(screen.getByText('Chiefs D/ST')).toBeInTheDocument();
    // Pts and VORP columns both fall back to a dash for the DST row.
    const dashes = screen.getAllByText('—').filter(el => el.tagName === 'TD')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
  })

  it('shows a tier badge (e.g. T3) when the player has a tier', () => {
    render(
      <DraftBoardTable
        players={[player({ tier: 3 })]}
        positionFilter='ALL'
        onDraft={vi.fn()}
        isPicking={false}
      />
    )

    expect(screen.getByText('T3')).toBeInTheDocument()
  })

  it('does not render a tier badge when tier is absent', () => {
    render(
      <DraftBoardTable
        players={[player({ tier: null })]}
        positionFilter='ALL'
        onDraft={vi.fn()}
        isPicking={false}
      />
    )

    expect(screen.queryByText(/^T\d+$/)).not.toBeInTheDocument()
  })

  it('adds a tier-boundary divider between consecutive rank-sorted rows in different tiers', () => {
    render(
      <DraftBoardTable
        players={[
          player({ player_id: 'a', player_name: 'A', model_rank: 1, tier: 1 }),
          player({ player_id: 'b', player_name: 'B', model_rank: 2, tier: 1 }),
          player({ player_id: 'c', player_name: 'C', model_rank: 3, tier: 2 })
        ]}
        positionFilter='ALL'
        onDraft={vi.fn()}
        isPicking={false}
      />
    )

    const rowC = screen.getByText('C').closest('tr')
    const rowB = screen.getByText('B').closest('tr')
    expect(rowC?.className).toMatch(/border-t-2/)
    expect(rowB?.className).not.toMatch(/border-t-2/)
  })

  it('renders a stack badge on a row when a hint matches the player name', () => {
    const hint: StackHint = {
      player_name: 'Test Player',
      position: 'WR',
      team: 'KC',
      rostered_player_name: 'Mahomes',
      rho: 0.42,
      n_games: 20,
      kind: 'stack_bonus'
    }
    render(
      <DraftBoardTable
        players={[player({})]}
        positionFilter='ALL'
        onDraft={vi.fn()}
        isPicking={false}
        hintsByPlayerName={new Map([['Test Player', [hint]]])}
      />
    )

    expect(screen.getByText('STACK +0.42 w/ Mahomes')).toBeInTheDocument()
  })

  it('renders an overlap badge for a shared_ceiling_warning hint', () => {
    const hint: StackHint = {
      player_name: 'Test Player',
      position: 'WR',
      team: 'KC',
      rostered_player_name: 'Rice',
      rho: 0.6,
      n_games: 12,
      kind: 'shared_ceiling_warning'
    }
    render(
      <DraftBoardTable
        players={[player({})]}
        positionFilter='ALL'
        onDraft={vi.fn()}
        isPicking={false}
        hintsByPlayerName={new Map([['Test Player', [hint]]])}
      />
    )

    expect(screen.getByText('overlap w/ Rice')).toBeInTheDocument()
  })

  it('renders no badge when hintsByPlayerName has no entry for the player', () => {
    render(
      <DraftBoardTable
        players={[player({})]}
        positionFilter='ALL'
        onDraft={vi.fn()}
        isPicking={false}
        hintsByPlayerName={new Map()}
      />
    )

    expect(screen.queryByText(/STACK/)).not.toBeInTheDocument()
    expect(screen.queryByText(/overlap/)).not.toBeInTheDocument()
  })
})


describe('DraftBoardTable readOnly (ADP page)', () => {
  it('hides Draft/Taken controls and starts sorted by ADP', () => {
    render(
      <DraftBoardTable
        players={[
          player({ player_id: 'a', player_name: 'Late Pick', model_rank: 1, adp_rank: 40, adp_diff: 39 }),
          player({ player_id: 'b', player_name: 'First Overall', model_rank: 2, adp_rank: 1, adp_diff: -1 })
        ]}
        positionFilter='ALL'
        readOnly
        defaultSort='adp_rank'
      />
    )
    expect(screen.queryByRole('button', { name: 'Draft' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Taken' })).toBeNull()
    const rows = screen.getAllByRole('row').slice(1) // drop header row
    expect(rows[0]).toHaveTextContent('First Overall')
    expect(rows[1]).toHaveTextContent('Late Pick')
    expect(screen.getByText(/of 2 players/)).toBeInTheDocument()
  })
})
