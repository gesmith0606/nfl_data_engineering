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
  season: 2026
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

  const handleStartMock = useCallback(() => {
    mockStartMutation.mutate({
      scoring: config.scoring,
      roster_format: config.roster_format,
      n_teams: config.n_teams,
      user_pick: config.user_pick,
      season: config.season
    })
  }, [config, mockStartMutation])

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
