import { describe, expect, it } from 'vitest'

import {
  FALLBACK_PLATFORM_PRESETS,
  ROOM_PLATFORMS,
  normalizePlatformPresets
} from '../platform-presets'

/**
 * Regression tests for the 2026-08-01 draft-room crash.
 *
 * GET /api/draft/platforms returns `custom` with every field null, and the
 * pre-fix hook handed the raw response straight to consumers doing
 * `presets[platform].timer_seconds` — undefined/null fields took down the
 * whole /dashboard/draft route. Normalization must guarantee: every
 * RoomPlatform key present, every field non-null, regardless of API shape.
 */
describe('normalizePlatformPresets', () => {
  // Verbatim (minus roster_slots detail) from the live endpoint, 2026-08-01.
  const liveApiShape = {
    espn: {
      scoring_format: 'half_ppr',
      roster_format: 'espn_default',
      rounds: 16,
      timer_seconds: 30,
      adp_source: 'espn',
      roster_slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, K: 1, DST: 1, BN: 7 }
    },
    sleeper: {
      scoring_format: 'ppr',
      roster_format: 'sleeper_default',
      rounds: 15,
      timer_seconds: 60,
      adp_source: 'sleeper',
      roster_slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 2, K: 1, DST: 1, BN: 5 }
    },
    yahoo: {
      scoring_format: 'half_ppr',
      roster_format: 'yahoo_default',
      rounds: 15,
      timer_seconds: 60,
      adp_source: 'ffc',
      roster_slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, K: 1, DST: 1, BN: 6 }
    },
    custom: {
      scoring_format: null,
      roster_format: null,
      rounds: null,
      timer_seconds: null,
      adp_source: null,
      roster_slots: {}
    }
  }

  it('fills the all-null live `custom` entry from the fallback (the crash case)', () => {
    const presets = normalizePlatformPresets(liveApiShape as never)
    expect(presets.custom).toEqual(FALLBACK_PLATFORM_PRESETS.custom)
    expect(presets.custom.timer_seconds).not.toBeNull()
  })

  it('keeps real API values for real platforms', () => {
    const presets = normalizePlatformPresets(liveApiShape as never)
    expect(presets.espn.timer_seconds).toBe(30)
    expect(presets.sleeper.scoring_format).toBe('ppr')
    expect(presets.yahoo.roster_format).toBe('yahoo_default')
  })

  it('returns pure fallbacks when the API data is undefined', () => {
    expect(normalizePlatformPresets(undefined)).toEqual(FALLBACK_PLATFORM_PRESETS)
  })

  it('fills missing platform keys from fallbacks', () => {
    const presets = normalizePlatformPresets({ espn: liveApiShape.espn } as never)
    expect(presets.sleeper).toEqual(FALLBACK_PLATFORM_PRESETS.sleeper)
    expect(presets.custom).toEqual(FALLBACK_PLATFORM_PRESETS.custom)
  })

  it('guarantees every field is non-null on every platform, whatever the input', () => {
    for (const input of [undefined, {}, liveApiShape, { custom: {} }] as const) {
      const presets = normalizePlatformPresets(input as never)
      for (const platform of ROOM_PLATFORMS) {
        const preset = presets[platform]
        expect(preset.scoring_format).toBeTruthy()
        expect(preset.roster_format).toBeTruthy()
        expect(preset.rounds).toBeGreaterThan(0)
        expect(preset.timer_seconds).toBeGreaterThan(0)
        expect(preset.adp_source).toBeTruthy()
        expect(preset.roster_slots).toBeDefined()
      }
    }
  })
})
