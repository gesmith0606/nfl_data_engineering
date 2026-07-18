'use client'

import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Icons } from '@/components/icons'
import { draftBoardQueryOptions } from '@/features/nfl/api/queries'
import { useDraftState } from '../hooks/use-draft-state'
import { DraftBoardTable } from './draft-board-table'
import { DraftConfigDialog } from './draft-config-dialog'
import { MyRosterPanel } from './my-roster-panel'
import { RecommendationsPanel } from './recommendations-panel'
import { MockDraftView } from './mock-draft-view'
import { LiveDraftPanel } from './live-draft-panel'
import { MirrorTurnTracker } from './mirror-turn-tracker'
import { PasteSyncPanel } from './paste-sync-panel'
import { PickClock } from './pick-clock'
import { requestTurnNotificationPermission } from '../hooks/use-turn-alert'
import { usePlatformPresets } from '../hooks/use-platform-presets'
import { PLATFORM_LABELS, isRoomPlatform, scoringLabel, PLATFORM_ACCENT } from '../utils/platform-presets'
import { FadeIn, DataLoadReveal, PressScale } from '@/lib/motion-primitives'
import type { DraftPlatform, Position } from '@/lib/nfl/types'

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K', 'DST']

const MIRROR_COPY: Record<Exclude<DraftPlatform, 'sleeper'>, string> = {
  espn: 'ESPN has no public draft API, so picks can’t stream automatically. Mirror mode is still a co-pilot, not a chore: paste the draft room’s pick history any time and the whole board catches up in one shot (no per-pick clicking), while we track the clock, alert your turn, and call your pick from our board.',
  yahoo: 'Yahoo auto-sync isn’t connected on this server. Mirror mode gives you the same co-pilot: paste-sync or Draft/Taken to record picks — we track the clock, alert your turn, and call your pick from our board.'
}

export function DraftToolView() {
  // Live co-pilot is a distinct surface from the manual board: it reads a real
  // Sleeper/Yahoo draft and drives our recommendation engine. Kept as local UI
  // state so it overlays the existing board/mock flow without touching it.
  const [liveMode, setLiveMode] = useState(false)
  const [livePlatform, setLivePlatform] = useState<DraftPlatform>('sleeper')
  // Yahoo tries true auto-sync first; mirror is the unauthenticated fallback.
  const [yahooMode, setYahooMode] = useState<'live' | 'mirror'>('live')
  // Mirror mode: ESPN/Yahoo drafts tracked on the manual board with snake-math
  // turn alerts + paste-sync. null = not mirroring.
  const [mirror, setMirror] = useState<{ platform: DraftPlatform; slot: number } | null>(null)
  const [mirrorSlotInput, setMirrorSlotInput] = useState('')
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

  const presets = usePlatformPresets()
  const activePlatform = isRoomPlatform(config.platform) ? config.platform : 'custom'
  const activePreset = presets[activePlatform]

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
      <FadeIn className='space-y-[var(--gap-stack)]'>
        <div className='flex items-center gap-[var(--space-2)]'>
          <Icons.clipboardText className='h-[var(--space-4)] w-[var(--space-4)]' />
          <h2 className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
            Mock Draft Simulation
          </h2>
          <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            {config.n_teams} teams · Pick #{config.user_pick} · {config.scoring}
          </span>
        </div>
        <MockDraftView
          sessionId={sessionId}
          config={config}
          onReset={handleReset}
          timerSeconds={activePreset.timer_seconds}
          accentColor={PLATFORM_ACCENT[activePlatform]}
        />
      </FadeIn>
    )
  }

  // -------------------------------------------------------------------------
  // Live draft co-pilot (reads a real Sleeper draft, our engine drives picks)
  // -------------------------------------------------------------------------
  if (liveMode) {
    return (
      <FadeIn className='space-y-[var(--gap-stack)]'>
        <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
          <Tabs
            value={livePlatform}
            onValueChange={v => setLivePlatform(v as DraftPlatform)}
          >
            <TabsList>
              {(['sleeper', 'espn', 'yahoo'] as const).map(p => (
                <TabsTrigger
                  key={p}
                  value={p}
                  className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] capitalize'
                >
                  {p}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <div className='ml-auto'>
            <PressScale>
              <Button variant='outline' size='sm' onClick={() => setLiveMode(false)}>
                <Icons.arrowRight className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)] rotate-180' />
                Back to Board
              </Button>
            </PressScale>
          </div>
        </div>
        {livePlatform === 'sleeper' ? (
          <LiveDraftPanel />
        ) : livePlatform === 'yahoo' && yahooMode === 'live' ? (
          <LiveDraftPanel
            platform='yahoo'
            onUseMirror={() => setYahooMode('mirror')}
          />
        ) : (
          <div className='rounded-md border p-[var(--space-4)] space-y-[var(--space-3)]'>
            <div className='flex items-center gap-[var(--space-2)]'>
              <Icons.target className='h-[var(--space-4)] w-[var(--space-4)]' />
              <h2 className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold capitalize'>
                {livePlatform} Draft — Mirror Mode
              </h2>
              {livePlatform === 'yahoo' && (
                <Button
                  variant='ghost'
                  size='sm'
                  className='ml-auto'
                  onClick={() => setYahooMode('live')}
                >
                  Try auto-sync
                </Button>
              )}
            </div>
            <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
              {MIRROR_COPY[livePlatform]}
            </p>
            <div className='flex flex-wrap items-end gap-[var(--space-2)]'>
              <label
                htmlFor='mirror-slot-input'
                className='flex flex-col gap-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
              >
                <span className='text-muted-foreground'>Your draft slot</span>
                <Input
                  id='mirror-slot-input'
                  className='w-24'
                  placeholder='e.g. 5'
                  inputMode='numeric'
                  value={mirrorSlotInput}
                  onChange={e => setMirrorSlotInput(e.target.value)}
                />
              </label>
              <PressScale>
                <Button
                  size='sm'
                  disabled={!Number(mirrorSlotInput)}
                  onClick={() => {
                    requestTurnNotificationPermission()
                    setMirror({ platform: livePlatform, slot: Number(mirrorSlotInput) })
                    setLiveMode(false)
                  }}
                >
                  Start Mirror Mode
                </Button>
              </PressScale>
            </div>
            <p className='text-muted-foreground text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
              Pro tip: copy our recommendation queue into your {livePlatform === 'espn' ? 'ESPN' : 'Yahoo'}{' '}
              pick queue before the draft — if the timer ever expires, autopick
              drafts from our board instead of the platform&apos;s rankings.
            </p>
          </div>
        )}
      </FadeIn>
    )
  }

  // -------------------------------------------------------------------------
  // Normal draft board view
  // -------------------------------------------------------------------------
  return (
    <FadeIn className='space-y-[var(--gap-stack)]'>
      {/* Top toolbar */}
      <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
        {/* Position filter */}
        <Tabs
          value={positionFilter}
          onValueChange={v => setPositionFilter(v as Position)}
        >
          <TabsList>
            {POSITIONS.map(pos => (
              <TabsTrigger
                key={pos}
                value={pos}
                className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
              >
                {pos}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className='ml-auto flex items-center gap-[var(--space-2)]'>
          <PressScale>
            <Button
              variant='default'
              size='sm'
              onClick={() => setLiveMode(true)}
            >
              <Icons.target className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
              Live Draft
            </Button>
          </PressScale>
          <PressScale>
            <Button
              variant='outline'
              size='sm'
              onClick={() => setConfigOpen(true)}
            >
              <Icons.settings className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
              Settings
            </Button>
          </PressScale>
          <PressScale>
            <Button
              variant='outline'
              size='sm'
              onClick={() => {
                handleStartMock()
              }}
            >
              <Icons.arrowRight className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
              Mock Draft
            </Button>
          </PressScale>
          <PressScale>
            <Button
              variant='outline'
              size='sm'
              onClick={handleNewDraft}
            >
              <Icons.close className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
              Reset
            </Button>
          </PressScale>
        </div>
      </div>

      {/* Draft-room chip + pick clock (light platform-flavored accent) */}
      {data && (
        <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
          <span
            className='inline-flex items-center gap-1 rounded-full border px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold'
            style={{ color: PLATFORM_ACCENT[activePlatform], borderColor: PLATFORM_ACCENT[activePlatform] }}
          >
            {PLATFORM_LABELS[activePlatform]}-style room · {scoringLabel(config.scoring)} ·{' '}
            {activePreset.timer_seconds}s clock
          </span>
          <PickClock
            pickNumber={data.picks_taken + 1}
            timerSeconds={activePreset.timer_seconds}
            accentColor={PLATFORM_ACCENT[activePlatform]}
          />
        </div>
      )}

      {/* Mirror-mode turn tracker + paste-sync (ESPN / Yahoo) */}
      {mirror && data && (
        <>
          <MirrorTurnTracker
            platform={mirror.platform}
            picksTaken={data.picks_taken}
            nTeams={data.n_teams}
            mySlot={mirror.slot}
            onSlotChange={slot => setMirror(m => (m ? { ...m, slot } : m))}
            onExit={() => setMirror(null)}
          />
          <PasteSyncPanel sessionId={sessionId} mySlot={mirror.slot} />
        </>
      )}

      {/* Session info badge */}
      {data && (
        <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
          {data.scoring_format} · {data.roster_format} · {data.n_teams} teams ·{' '}
          {data.picks_taken} picks made · Follow along with your live draft on
          Sleeper, ESPN, or Yahoo — hit Draft for your picks and Taken for
          everyone else&apos;s
        </p>
      )}

      {/* Main content: board + sidebar */}
      <DataLoadReveal
        loading={isLoading}
        skeleton={
          <div className='flex items-center justify-center py-[var(--space-12)]'>
            <div className='flex flex-col items-center gap-[var(--space-3)]'>
              <Icons.spinner className='text-muted-foreground h-[var(--space-8)] w-[var(--space-8)] animate-spin' />
              <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                Generating projections and building draft board...
              </p>
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                This may take 15-30 seconds on first load
              </p>
            </div>
          </div>
        }
      >
        {isError ? (
          <div className='flex items-center justify-center py-[var(--space-12)]'>
            <div className='flex flex-col items-center gap-[var(--space-2)]'>
              <Icons.alertCircle className='text-muted-foreground h-[var(--space-8)] w-[var(--space-8)]' />
              <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                Unable to load the draft board. Please try again.
              </p>
              <PressScale>
                <Button variant='outline' size='sm' onClick={() => void refetch()}>
                  Retry
                </Button>
              </PressScale>
            </div>
          </div>
        ) : (
          <div className='flex flex-col gap-[var(--gap-stack)] lg:flex-row'>
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
            <div className='w-full space-y-[var(--gap-stack)] lg:w-72 lg:shrink-0'>
              <MyRosterPanel
                roster={roster}
                remainingNeeds={remainingNeeds}
                picksCount={picksCount}
              />
              <RecommendationsPanel
                sessionId={sessionId}
                positionFilter={positionFilter}
                players={players}
              />
            </div>
          </div>
        )}
      </DataLoadReveal>

      {/* Config dialog */}
      <DraftConfigDialog
        config={config}
        onConfigChange={setConfig}
        onStartMock={handleStartMock}
        open={configOpen}
        onOpenChange={setConfigOpen}
        onNewDraft={handleNewDraft}
      />
    </FadeIn>
  )
}
