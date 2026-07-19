import { describe, it, expect } from 'vitest'
import { computeTierExhaustion } from '../tier-exhaustion'

describe('computeTierExhaustion', () => {
  it('flags a position whose top tier has <=2 players remaining', () => {
    const warnings = computeTierExhaustion([
      { position: 'TE', tier: 2 },
      { position: 'TE', tier: 3 },
      { position: 'TE', tier: 3 }
    ])

    expect(warnings).toEqual([{ position: 'TE', tier: 2, count: 1 }])
  })

  it('does not flag a position with 3+ players left in the top tier', () => {
    const warnings = computeTierExhaustion([
      { position: 'RB', tier: 1 },
      { position: 'RB', tier: 1 },
      { position: 'RB', tier: 1 },
      { position: 'RB', tier: 2 }
    ])

    expect(warnings).toEqual([])
  })

  it('ignores players with a null or undefined tier', () => {
    const warnings = computeTierExhaustion([
      { position: 'WR', tier: null },
      { position: 'WR', tier: undefined },
      { position: 'K' }
    ])

    expect(warnings).toEqual([])
  })

  it('sorts by fewest-remaining first, then by position name', () => {
    const warnings = computeTierExhaustion([
      { position: 'TE', tier: 4 },
      { position: 'TE', tier: 4 },
      { position: 'QB', tier: 1 },
      { position: 'K', tier: 5 }
    ])

    expect(warnings.map(w => w.position)).toEqual(['K', 'QB', 'TE'])
  })

  it('only counts players tied at the lowest tier number for that position', () => {
    const warnings = computeTierExhaustion([
      { position: 'WR', tier: 3 },
      { position: 'WR', tier: 5 },
      { position: 'WR', tier: 5 }
    ])

    expect(warnings).toEqual([{ position: 'WR', tier: 3, count: 1 }])
  })
})
