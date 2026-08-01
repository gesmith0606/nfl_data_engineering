import type { DraftConfig, DraftPlatformPreset, ScoringFormat } from '@/lib/nfl/types'

/** Draft-room platforms the config dialog can pre-fill from. */
export type RoomPlatform = 'espn' | 'sleeper' | 'yahoo' | 'custom'

export const ROOM_PLATFORMS: RoomPlatform[] = ['espn', 'sleeper', 'yahoo', 'custom']

export const PLATFORM_LABELS: Record<RoomPlatform, string> = {
  espn: 'ESPN',
  sleeper: 'Sleeper',
  yahoo: 'Yahoo',
  custom: 'Custom'
}

/**
 * Per-platform accent color for the header chip + pick clock. ESPN red,
 * Sleeper indigo (reads on the dark broadcast surface), Yahoo purple. Custom
 * falls back to the theme's primary token so it never clashes with a theme.
 */
export const PLATFORM_ACCENT: Record<RoomPlatform, string> = {
  espn: '#d50a0a',
  sleeper: '#7c3aed',
  yahoo: '#6001d2',
  custom: 'var(--primary)'
}

/**
 * Hardcoded fallback for GET /api/draft/platforms. That endpoint is a
 * parallel backend lane and 404s today — this keeps the platform selector
 * usable regardless, per the "UI must not break against today's API" brief.
 */
export const FALLBACK_PLATFORM_PRESETS: Record<RoomPlatform, DraftPlatformPreset> = {
  espn: {
    scoring_format: 'half_ppr',
    roster_format: 'standard',
    rounds: 16,
    timer_seconds: 90,
    adp_source: 'espn',
    roster_slots: {}
  },
  sleeper: {
    scoring_format: 'half_ppr',
    roster_format: 'standard',
    rounds: 15,
    timer_seconds: 60,
    // No real Sleeper ADP source exists yet -- FFC is the best available real
    // ADP, mirroring PLATFORM_PRESETS["sleeper"]["adp_source"] in src/config.py.
    adp_source: 'sleeper',
    roster_slots: {}
  },
  yahoo: {
    scoring_format: 'half_ppr',
    roster_format: 'standard',
    rounds: 16,
    timer_seconds: 90,
    adp_source: 'ffc',
    roster_slots: {}
  },
  custom: {
    scoring_format: 'half_ppr',
    roster_format: 'standard',
    rounds: 15,
    timer_seconds: 60,
    adp_source: 'custom',
    roster_slots: {}
  }
}

/**
 * Merge whatever GET /api/draft/platforms returned over the hardcoded
 * fallbacks, per platform AND per field. The live API's `custom` entry is
 * all-null and any platform key may be absent, so a raw replacement of the
 * fallback record crashes preset consumers (`activePreset.timer_seconds` on
 * undefined took down /dashboard/draft on 2026-08-01). Null/undefined fields
 * always resolve to the fallback value; `timer_seconds: null` from a real
 * platform is preserved only via applyPlatformPreset's explicit opt-in, not
 * here — presets must always be fully populated.
 */
export function normalizePlatformPresets(
  data: Record<string, Partial<DraftPlatformPreset> | undefined> | undefined
): Record<RoomPlatform, DraftPlatformPreset> {
  const merged = {} as Record<RoomPlatform, DraftPlatformPreset>
  for (const platform of ROOM_PLATFORMS) {
    const fallback = FALLBACK_PLATFORM_PRESETS[platform]
    const api = data?.[platform]
    merged[platform] = api
      ? {
          scoring_format: api.scoring_format ?? fallback.scoring_format,
          roster_format: api.roster_format ?? fallback.roster_format,
          rounds: api.rounds ?? fallback.rounds,
          timer_seconds: api.timer_seconds ?? fallback.timer_seconds,
          adp_source: api.adp_source ?? fallback.adp_source,
          roster_slots:
            api.roster_slots && Object.keys(api.roster_slots).length > 0
              ? api.roster_slots
              : fallback.roster_slots
        }
      : fallback
  }
  return merged
}

const VALID_SCORING = new Set(['ppr', 'half_ppr', 'standard'])
const VALID_ROSTER_FORMAT = new Set([
  'standard',
  'superflex',
  '2qb',
  'espn_default',
  'sleeper_default',
  'yahoo_default'
])

/** Narrow an API scoring_format string to our enum; undefined when unrecognized (degrade gracefully). */
export function asScoringFormat(value: string | undefined): ScoringFormat | undefined {
  return value && VALID_SCORING.has(value) ? (value as ScoringFormat) : undefined
}

/** Narrow an API roster_format string to our enum; undefined when unrecognized (degrade gracefully). */
export function asRosterFormat(value: string | undefined): import('@/lib/nfl/types').RosterFormat | undefined {
  return value && VALID_ROSTER_FORMAT.has(value)
    ? (value as import('@/lib/nfl/types').RosterFormat)
    : undefined
}

/** All roster formats offered in the setup/settings dialogs, platform shapes first. */
export const ROSTER_FORMAT_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'ESPN default (1 FLEX · 7 BN)', value: 'espn_default' },
  { label: 'Sleeper default (2 FLEX · 5 BN)', value: 'sleeper_default' },
  { label: 'Yahoo default (1 FLEX · 6 BN)', value: 'yahoo_default' },
  { label: 'Standard', value: 'standard' },
  { label: 'Superflex', value: 'superflex' },
  { label: '2QB', value: '2qb' }
]

export function isRoomPlatform(value: string | undefined): value is RoomPlatform {
  return !!value && (ROOM_PLATFORMS as string[]).includes(value)
}

/** Default rankings source for a platform preset; unknown values fall back to consensus (FFC). */
export function defaultAdpSource(presetAdpSource: string | undefined): string {
  return presetAdpSource === 'espn' || presetAdpSource === 'sleeper' ? presetAdpSource : 'ffc'
}

/**
 * Apply a room-platform preset onto a config — shared by the settings dialog,
 * mock setup dialog, and the draft landing's platform-room chooser. 'custom'
 * just flips the platform flag; a real platform pulls scoring/roster format
 * (and, when requested, timer/ADP source) from its preset.
 */
export function applyPlatformPreset(
  config: DraftConfig,
  platform: RoomPlatform,
  presets: Record<RoomPlatform, DraftPlatformPreset>,
  options: { includeTimerAndAdp?: boolean } = {}
): DraftConfig {
  if (platform === 'custom') {
    return { ...config, platform: 'custom' }
  }
  const preset = presets[platform]
  const scoring = asScoringFormat(preset.scoring_format)
  const rosterFormat = asRosterFormat(preset.roster_format)
  return {
    ...config,
    platform,
    ...(scoring ? { scoring } : {}),
    ...(rosterFormat ? { roster_format: rosterFormat } : {}),
    ...(options.includeTimerAndAdp
      ? { timer_seconds: preset.timer_seconds ?? null, adp_source: defaultAdpSource(preset.adp_source) }
      : {})
  }
}

/** Human label for a scoring format value, for the header chip. */
export function scoringLabel(scoring: string): string {
  switch (scoring) {
    case 'ppr':
      return 'PPR'
    case 'half_ppr':
      return 'Half PPR'
    case 'standard':
      return 'Standard'
    default:
      return scoring
  }
}
