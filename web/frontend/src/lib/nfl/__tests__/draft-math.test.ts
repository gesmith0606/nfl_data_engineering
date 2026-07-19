import { describe, it, expect } from 'vitest'
import { picksUntilNextTurn, slotOnClock, nextPickForSlot, pickLabel } from '../draft-math'

describe('picksUntilNextTurn', () => {
  it('returns 0 when the slot is on the clock right now', () => {
    // 10 teams, round 1: pick 1 is slot 1.
    expect(picksUntilNextTurn(1, 1, 10)).toBe(0)
  })

  it('counts forward picks until the slot comes up again (same round, later slot)', () => {
    // 10 teams: pick 1 -> slot 1; slot 4 is next up at pick 4.
    expect(picksUntilNextTurn(1, 4, 10)).toBe(3)
  })

  it('counts across the snake turn (round 1 -> round 2 reverses direction)', () => {
    // 10 teams: pick 10 (round 1, last slot=10) is on slot 10's clock.
    // Round 2 snakes back — pick 11 is slot 10 again (immediate back-to-back).
    expect(picksUntilNextTurn(1, 10, 10)).toBe(9)
    expect(slotOnClock(10, 10)).toBe(10)
    expect(slotOnClock(11, 10)).toBe(10)
  })

  it('matches nextPickForSlot for the general case', () => {
    const nTeams = 12
    for (let slot = 1; slot <= nTeams; slot++) {
      const from = 5
      const expected = nextPickForSlot(from, slot, nTeams)
      const want = expected != null ? expected - from : 0
      expect(picksUntilNextTurn(from, slot, nTeams)).toBe(want)
    }
  })

  it('is consistent with pickLabel round math at a snake turn', () => {
    // 12 teams: pick 11 is slot 11's turn; slot 12 (last pick of round 1,
    // which snakes straight into the first pick of round 2) is next up in
    // just 1 pick.
    expect(picksUntilNextTurn(11, 12, 12)).toBe(1)
    expect(pickLabel(12, 12)).toBe('1.12')
    expect(pickLabel(13, 12)).toBe('2.01')
  })
})
