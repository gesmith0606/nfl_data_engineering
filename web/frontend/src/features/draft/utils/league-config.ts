import type { DraftConfig, LeagueOverviewResponse, RosterFormat, ScoringFormat } from '@/lib/nfl/types'

const TEAM_COUNT_OPTIONS = [8, 10, 12, 14] as const

/** Nearest supported team count to a league's real roster count (falls back when unknown). */
export function clampTeamCount(nTeams: number | null | undefined, fallback: number): number {
  if (!nTeams || nTeams <= 0) return fallback
  return TEAM_COUNT_OPTIONS.reduce((closest, candidate) =>
    Math.abs(candidate - nTeams) < Math.abs(closest - nTeams) ? candidate : closest
  )
}

/** Parse a Sleeper scoring_format_label ('Full PPR (league)', 'Half PPR', 'Standard', ...) into our enum. */
export function mapScoringFormat(label: string | null | undefined): ScoringFormat {
  const normalized = (label ?? '').toLowerCase()
  if (normalized.includes('half')) return 'half_ppr'
  if (normalized.includes('ppr')) return 'ppr'
  return 'standard'
}

/** Infer roster shape from a league's roster_positions slot list. */
export function mapRosterFormat(rosterPositions: string[] | null | undefined): RosterFormat {
  const slots = (rosterPositions ?? []).map(p => p.toUpperCase())
  if (slots.includes('SUPER_FLEX') || slots.includes('SUPERFLEX')) return 'superflex'
  if (slots.filter(p => p === 'QB').length >= 2) return '2qb'
  return 'sleeper_default'
}

/**
 * Map a fetched Sleeper league overview onto a DraftConfig -- the "Use my
 * league" fast path on the draft landing. This is an approximation (exact
 * custom scoring lands later): team count clamps to the nearest supported
 * size, scoring/roster shape are inferred from the label/slot list, not the
 * league's raw scoring_settings.
 */
export function mapLeagueOverviewToConfig(
  overview: LeagueOverviewResponse,
  base: DraftConfig
): DraftConfig {
  const n_teams = clampTeamCount(overview.total_rosters, base.n_teams)
  return {
    ...base,
    n_teams,
    user_pick: Math.min(base.user_pick, n_teams),
    scoring: mapScoringFormat(overview.scoring_format_label),
    roster_format: mapRosterFormat(overview.roster_positions),
    platform: 'sleeper',
    adp_source: 'sleeper'
  }
}
