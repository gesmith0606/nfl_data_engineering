'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { draftPlatformsQueryOptions } from '@/features/nfl/api/queries'
import { normalizePlatformPresets, type RoomPlatform } from '../utils/platform-presets'
import type { DraftPlatformPreset } from '@/lib/nfl/types'

/**
 * Draft-room presets per platform (scoring/roster format/rounds/timer/ADP
 * source). Backed by GET /api/draft/platforms, but ALWAYS normalized over the
 * hardcoded fallbacks: every RoomPlatform key present, every field non-null.
 * Consumers may safely do `presets[platform].timer_seconds` — the raw API
 * shape (envelope, missing keys, null fields) must never reach them.
 */
export function usePlatformPresets(): Record<RoomPlatform, DraftPlatformPreset> {
  const { data } = useQuery(draftPlatformsQueryOptions())
  return useMemo(
    () => normalizePlatformPresets(data as Record<string, Partial<DraftPlatformPreset>> | undefined),
    [data]
  )
}
