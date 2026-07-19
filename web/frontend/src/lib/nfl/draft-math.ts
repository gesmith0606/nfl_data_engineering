/**
 * Snake-draft slot math for mirror mode (ESPN / Yahoo / any platform where we
 * can't auto-sync picks). Mirrors the slot logic in src/live_draft_engine.py.
 */

/** Which slot (1-based) is on the clock for a given overall pick number. */
export function slotOnClock(pickNo: number, nTeams: number): number {
  const round = Math.ceil(pickNo / nTeams)
  const idx = (pickNo - 1) % nTeams
  return round % 2 === 1 ? idx + 1 : nTeams - idx
}

/**
 * The next overall pick number belonging to `slot`, starting at `fromPickNo`.
 * Returns null when `slot` never comes up (out-of-range slot) — matching the
 * Python engine's None convention so callers hide the countdown instead of
 * showing "your pick in 0".
 */
export function nextPickForSlot(
  fromPickNo: number,
  slot: number,
  nTeams: number
): number | null {
  for (let p = fromPickNo; p < fromPickNo + nTeams * 2; p++) {
    if (slotOnClock(p, nTeams) === slot) return p
  }
  return null
}

/** Human-readable round.pick label for an overall pick number, e.g. "3.07". */
export function pickLabel(pickNo: number, nTeams: number): string {
  const round = Math.ceil(pickNo / nTeams)
  const inRound = ((pickNo - 1) % nTeams) + 1
  return `${round}.${String(inRound).padStart(2, '0')}`
}

/**
 * How many picks until `slot` is next on the clock, counting from
 * `currentPickNo` (inclusive). Returns 0 when `slot` is on the clock right
 * now at `currentPickNo`. Powers the mock-draft header's "Next turn in N
 * picks" chip.
 */
export function picksUntilNextTurn(currentPickNo: number, slot: number, nTeams: number): number {
  if (slotOnClock(currentPickNo, nTeams) === slot) return 0
  const next = nextPickForSlot(currentPickNo, slot, nTeams)
  return next != null ? next - currentPickNo : 0
}
