'use client'

import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { draftPick, startMockDraft } from '@/features/nfl/api/service'
import { nflKeys } from '@/features/nfl/api/queries'
import type { DraftConfig, DraftPickRequest, MockDraftStartRequest, Position } from '@/lib/nfl/types'

const DEFAULT_CONFIG: DraftConfig = {
  scoring: 'half_ppr',
  roster_format: 'standard',
  n_teams: 12,
  user_pick: 1,
  season: 2026,
  platform: 'sleeper',
  strategy: 'balanced'
}

export function useDraftState() {
  const queryClient = useQueryClient()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [config, setConfig] = useState<DraftConfig>(DEFAULT_CONFIG)
  const [positionFilter, setPositionFilter] = useState<Position>('ALL')
  const [mode, setMode] = useState<'manual' | 'mock'>('manual')

  const pickMutation = useMutation({
    mutationFn: (req: DraftPickRequest) => draftPick(req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nflKeys.draftBoard(sessionId ?? undefined) })
      if (sessionId) {
        queryClient.invalidateQueries({ queryKey: nflKeys.draftRecommendations(sessionId) })
      }
    }
  })

  const mockStartMutation = useMutation({
    mutationFn: (req: MockDraftStartRequest) => startMockDraft(req),
    onSuccess: (data) => {
      setSessionId(data.session_id)
      setMode('mock')
    }
  })

  const handleDraftPlayer = useCallback((playerId: string, byMe: boolean = true) => {
    if (!sessionId) return
    pickMutation.mutate({ session_id: sessionId, player_id: playerId, by_me: byMe })
  }, [sessionId, pickMutation])

  /**
   * Start a mock draft. `overrides` lets callers (the mock setup dialog's
   * "Random" pick slot) supply a final value resolved at click time without
   * waiting on a state update to land first -- `config` is merged with
   * `overrides` for this call, and (when overrides are given) committed back
   * to state so the rest of the UI reflects the resolved value.
   */
  const handleStartMock = useCallback((overrides?: Partial<DraftConfig>) => {
    const finalConfig: DraftConfig = overrides ? { ...config, ...overrides } : config
    mockStartMutation.mutate({
      scoring: finalConfig.scoring,
      roster_format: finalConfig.roster_format,
      n_teams: finalConfig.n_teams,
      user_pick: finalConfig.user_pick,
      season: finalConfig.season,
      ...(finalConfig.platform && finalConfig.platform !== 'custom'
        ? { platform: finalConfig.platform }
        : {}),
      ...(finalConfig.adp_source ? { adp_source: finalConfig.adp_source } : {}),
      ...(finalConfig.strategy ? { strategy: finalConfig.strategy } : {})
    })
    if (overrides) setConfig(finalConfig)
  }, [config, mockStartMutation, setConfig])

  const resetDraft = useCallback(() => {
    setSessionId(null)
    setMode('manual')
    queryClient.removeQueries({ queryKey: nflKeys.draftBoard() })
  }, [queryClient])

  return {
    sessionId,
    setSessionId,
    config,
    setConfig,
    positionFilter,
    setPositionFilter,
    mode,
    setMode,
    pickMutation,
    mockStartMutation,
    handleDraftPlayer,
    handleStartMock,
    resetDraft
  }
}
