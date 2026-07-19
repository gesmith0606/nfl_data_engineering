'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { stackHintsQueryOptions } from '@/features/nfl/api/queries'
import type { DraftPlayer, StackHint } from '@/lib/nfl/types'

/**
 * Stack/overlap hints against the user's current roster (GET /api/draft/
 * stack-hints — a parallel backend lane that may 404 today). Refetches
 * whenever the roster changes (the endpoint only takes session_id, so a
 * roster fingerprint drives the query key) and degrades to an empty map on
 * any error, per the graceful-degradation contract.
 */
export function useStackHints(sessionId: string | null, roster: DraftPlayer[]) {
  const rosterSignature = useMemo(() => roster.map(p => p.player_id).sort().join(','), [roster])

  const { data, isError } = useQuery(stackHintsQueryOptions(sessionId ?? '', rosterSignature))

  const hints = isError ? [] : (data?.hints ?? [])

  /** Keyed by player_name -- hints reference players by name, not player_id. */
  const hintsByPlayerName = useMemo(() => {
    const map = new Map<string, StackHint[]>()
    for (const hint of hints) {
      const existing = map.get(hint.player_name)
      if (existing) {
        existing.push(hint)
      } else {
        map.set(hint.player_name, [hint])
      }
    }
    return map
  }, [hints])

  return { hints, hintsByPlayerName }
}
