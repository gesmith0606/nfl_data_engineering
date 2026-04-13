'use client'

import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Icons } from '@/components/icons'
import { draftBoardQueryOptions } from '@/features/nfl/api/queries'
import { useDraftState } from '../hooks/use-draft-state'
import { DraftBoardTable } from './draft-board-table'
import { DraftConfigDialog } from './draft-config-dialog'
import { MyRosterPanel } from './my-roster-panel'
import { RecommendationsPanel } from './recommendations-panel'
import { MockDraftView } from './mock-draft-view'
import type { Position } from '@/lib/nfl/types'

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K']

export function DraftToolView() {
  const {
    sessionId,
    setSessionId,
    config,
    setConfig,
    positionFilter,
    setPositionFilter,
    mode,
    handleDraftPlayer,
    handleStartMock,
    pickMutation,
    resetDraft
  } = useDraftState()

  const [configOpen, setConfigOpen] = useState(false)

  // Fetch the draft board (creates a new session on first call)
  const { data, isLoading, isError, refetch } = useQuery({
    ...draftBoardQueryOptions(
      config.scoring,
      config.roster_format,
      config.n_teams,
      config.season,
      sessionId ?? undefined
    ),
    enabled: true
  })

  // Store the session_id returned from the first board fetch
  useEffect(() => {
    if (data?.session_id && !sessionId) {
      setSessionId(data.session_id)
    }
  }, [data?.session_id, sessionId, setSessionId])

  // After a pick mutation succeeds the board query is invalidated; refetch it
  useEffect(() => {
    if (pickMutation.isSuccess) {
      void refetch()
    }
  }, [pickMutation.isSuccess, refetch])

  const handleNewDraft = useCallback(() => {
    resetDraft()
    // Clear the session so next board fetch creates a fresh one
    setSessionId(null)
    void refetch()
  }, [resetDraft, setSessionId, refetch])

  const handleReset = useCallback(() => {
    resetDraft()
    void refetch()
  }, [resetDraft, refetch])

  const players = data?.players ?? []
  const roster = data?.my_roster ?? []
  const remainingNeeds = data?.remaining_needs ?? {}
  const picksCount = data?.my_pick_count ?? 0

  // -------------------------------------------------------------------------
  // Mock draft mode
  // -------------------------------------------------------------------------
  if (mode === 'mock' && sessionId) {
    return (
      <div className='space-y-4'>
        <div className='flex items-center gap-2'>
          <Icons.clipboardText className='h-4 w-4' />
          <h2 className='text-sm font-semibold'>Mock Draft Simulation</h2>
          <span className='text-muted-foreground text-xs'>
            {config.n_teams} teams · Pick #{config.user_pick} · {config.scoring}
          </span>
        </div>
        <MockDraftView sessionId={sessionId} config={config} onReset={handleReset} />
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // Normal draft board view
  // -------------------------------------------------------------------------
  return (
    <div className='space-y-4'>
      {/* Top toolbar */}
      <div className='flex flex-wrap items-center gap-2'>
        {/* Position filter */}
        <Tabs
          value={positionFilter}
          onValueChange={v => setPositionFilter(v as Position)}
        >
          <TabsList>
            {POSITIONS.map(pos => (
              <TabsTrigger key={pos} value={pos} className='text-xs'>
                {pos}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className='ml-auto flex items-center gap-2'>
          <Button
            variant='outline'
            size='sm'
            onClick={() => setConfigOpen(true)}
          >
            <Icons.settings className='mr-1.5 h-4 w-4' />
            Settings
          </Button>
          <Button
            variant='outline'
            size='sm'
            onClick={() => {
              handleStartMock()
            }}
          >
            <Icons.arrowRight className='mr-1.5 h-4 w-4' />
            Mock Draft
          </Button>
          <Button
            variant='outline'
            size='sm'
            onClick={handleNewDraft}
          >
            <Icons.close className='mr-1.5 h-4 w-4' />
            Reset
          </Button>
        </div>
      </div>

      {/* Session info badge */}
      {data && (
        <p className='text-muted-foreground text-xs'>
          {data.scoring_format} · {data.roster_format} · {data.n_teams} teams ·{' '}
          {data.picks_taken} picks made
        </p>
      )}

      {/* Main content: board + sidebar */}
      {isLoading ? (
        <div className='flex items-center justify-center py-24'>
          <div className='flex flex-col items-center gap-3'>
            <Icons.spinner className='text-muted-foreground h-8 w-8 animate-spin' />
            <p className='text-muted-foreground text-sm'>
              Generating projections and building draft board...
            </p>
            <p className='text-muted-foreground text-xs'>This may take 15–30 seconds on first load</p>
          </div>
        </div>
      ) : isError ? (
        <div className='flex items-center justify-center py-24'>
          <div className='flex flex-col items-center gap-2'>
            <Icons.alertCircle className='text-muted-foreground h-8 w-8' />
            <p className='text-muted-foreground text-sm'>
              Failed to load draft board. Ensure the API is running on localhost:8000.
            </p>
            <Button variant='outline' size='sm' onClick={() => void refetch()}>
              Retry
            </Button>
          </div>
        </div>
      ) : (
        <div className='flex flex-col gap-4 lg:flex-row'>
          {/* Draft board (70%) */}
          <div className='min-w-0 flex-1'>
            <DraftBoardTable
              players={players}
              positionFilter={positionFilter}
              onDraft={handleDraftPlayer}
              isPicking={pickMutation.isPending}
            />
          </div>

          {/* Sidebar panels (30%) */}
          <div className='w-full space-y-4 lg:w-72 lg:shrink-0'>
            <MyRosterPanel
              roster={roster}
              remainingNeeds={remainingNeeds}
              picksCount={picksCount}
            />
            <RecommendationsPanel
              sessionId={sessionId}
              positionFilter={positionFilter}
            />
          </div>
        </div>
      )}

      {/* Config dialog */}
      <DraftConfigDialog
        config={config}
        onConfigChange={setConfig}
        onStartMock={handleStartMock}
        open={configOpen}
        onOpenChange={setConfigOpen}
        onNewDraft={handleNewDraft}
      />
    </div>
  )
}
