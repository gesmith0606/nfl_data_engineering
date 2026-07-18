/**
 * Tier-exhaustion cue: for each position, is the current top tier about to
 * run out? Computed client-side from the board's `tier` field (optional —
 * boards without tier data simply produce no warnings, per the graceful-
 * degradation contract).
 */

interface TieredPlayer {
  position: string
  tier?: number | null
}

export interface TierExhaustionWarning {
  position: string
  tier: number
  /** Players remaining in this position's current top tier. */
  count: number
}

/** Threshold at/under which a tier counts as "about to run out". */
const EXHAUSTION_THRESHOLD = 2

/**
 * For each position present in `players`, find the lowest (best) tier number
 * still available and how many players remain in it. Positions where that
 * count is <= EXHAUSTION_THRESHOLD are returned as warnings, sorted by
 * fewest-remaining first (most urgent first), then by position name.
 */
export function computeTierExhaustion(players: TieredPlayer[]): TierExhaustionWarning[] {
  const tiersByPosition = new Map<string, number[]>()

  for (const p of players) {
    if (p.tier == null) continue
    const existing = tiersByPosition.get(p.position)
    if (existing) {
      existing.push(p.tier)
    } else {
      tiersByPosition.set(p.position, [p.tier])
    }
  }

  const warnings: TierExhaustionWarning[] = []
  for (const [position, tiers] of tiersByPosition) {
    const topTier = Math.min(...tiers)
    const count = tiers.filter(t => t === topTier).length
    if (count <= EXHAUSTION_THRESHOLD) {
      warnings.push({ position, tier: topTier, count })
    }
  }

  return warnings.sort((a, b) => a.count - b.count || a.position.localeCompare(b.position))
}
