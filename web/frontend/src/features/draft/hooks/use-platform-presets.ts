'use client'

import { useQuery } from '@tanstack/react-query'
import { draftPlatformsQueryOptions } from '@/features/nfl/api/queries'
import { FALLBACK_PLATFORM_PRESETS, type RoomPlatform } from '../utils/platform-presets'
import type { DraftPlatformPreset } from '@/lib/nfl/types'

/**
 * Draft-room presets per platform (scoring/roster format/rounds/timer/ADP
 * source). Backed by GET /api/draft/platforms; falls back to hardcoded
 * defaults whenever the request errors (404 today, since it's a parallel
 * backend lane) so the platform selector always has values to render.
 */
export function usePlatformPresets(): Record<RoomPlatform, DraftPlatformPreset> {
  const { data } = useQuery(draftPlatformsQueryOptions())
  return (data as Record<RoomPlatform, DraftPlatformPreset> | undefined) ?? FALLBACK_PLATFORM_PRESETS
}
