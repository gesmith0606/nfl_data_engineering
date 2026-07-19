'use client'

import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Icons } from '@/components/icons'
import { draftBoardQueryOptions } from '@/features/nfl/api/queries'
import { undoDraftPick } from '@/features/nfl/api/service'
import { isConflictError } from '@/lib/nfl/api'
import { useDraftState } from '../hooks/use-draft-state'
import { useStackHints } from '../hooks/use-stack-hints'
import { DraftBoardTable } from './draft-board-table'
import { DraftConfigDialog } from './draft-config-dialog'
import { DraftLanding } from './draft-landing'
import { HowItWorksDialog, type HowItWorksMode } from './how-it-works-dialog'
import { LeagueContextChip } from './league-context-chip'
import { MockDraftSetupDialog } from './mock-draft-setup-dialog'
import { MyRosterPanel } from './my-roster-panel'
import { RecommendationsPanel } from './recommendations-panel'
import { MockDraftView } from './mock-draft-view'
import { LiveDraftPanel } from './live-draft-panel'
import { MirrorTurnTracker } from './mirror-turn-tracker'
import { PasteSyncPanel } from './paste-sync-panel'
import { SleepersPanel } from './sleepers-panel'
import { UndoButton } from './undo-button'
import { requestTurnNotificationPermission } from '../hooks/use-turn-alert'
import { usePlatformPresets } from '../hooks/use-platform-presets'
import { isRoomPlatform, PLATFORM_ACCENT } from '../utils/platform-presets'
import { STRATEGY_LABELS, asDraftStrategy } from '../utils/draft-strategy'
import { FadeIn, DataLoadReveal, PressScale } from '@/lib/motion-primitives'
import type { DraftPlatform, Position } from '@/lib/nfl/types'

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K', 'DST']
const MAIN_TABS = ['board', 'sleepers'] as const
type MainTab = (typeof MAIN_TABS)[number]

/** Which top-level mode the user has entered this session; null = landing. */
type EnteredMode = 'board' | 'mock' | 'live' | null

const BOARD_BANNER_SEEN_KEY = 'nfl.draftBoardBannerSeen'

const MIRROR_COPY: Record<Exclude<DraftPlatform, 'sleeper'>, string> = {
  espn: 'ESPN has no public draft API, so picks can’t stream automatically. Mirror mode is still a co-pilot, not a chore: paste the draft room’s pick history any time and the whole board catches up in one shot (no per-pick clicking), while we track the clock, alert your turn, and call your pick from our board.',
  yahoo: 'Yahoo auto-sync isn’t connected on this server. Mirror mode gives you the same co-pilot: paste-sync or Draft/Taken to record picks — we track the clock, alert your turn, and call your pick from our board.'
}

export function DraftToolView() {
  // Landing: shown until the user picks a mode this session. Reset/new-draft
  // returns here (see handleNewDraft/handleReset below).
  const [entered, setEntered] = useState<EnteredMode>(null)

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
  const [mockSetupOpen, setMockSetupOpen] = useState(false)
  const [mainTab, setMainTab] = useState<MainTab>('board')
  const [howItWorks, setHowItWorks] = useState<HowItWorksMode | null>(null)
  const [boardBannerVisible, setBoardBannerVisible] = useState(false)

  const presets = usePlatformPresets()
  const activePlatform = isRoomPlatform(config.platform) ? config.platform : 'custom'
  const activePreset = presets[activePlatform]
  const mockTimerSeconds = config.timer_seconds !== undefined ? config.timer_seconds : activePreset.timer_seconds

  // Fetch the draft board (creates a new session on first call)
  const { data, isLoading, isError, refetch } = useQuery({
    ...draftBoardQueryOptions(
      config.scoring,
      config.roster_format,
      config.n_teams,
      config.season,
      sessionId ?? undefined,
      config.adp_source,
      config.strategy
    ),
    enabled: true
  })

  const undoMutation = useMutation({
    mutationFn: () => undoDraftPick(sessionId as string),
    onSuccess: () => void refetch()
  })
  const undoIsConflict = undoMutation.isError && isConflictError(undoMutation.error)

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

  // A mock draft can only start via handleStartMock (mockStartMutation),
  // which flips `mode` to 'mock' -- once that happens we're committed past
  // the landing even if it was opened from there.
  useEffect(() => {
    if (mode === 'mock' && entered === null) {
      setEntered('mock')
    }
  }, [mode, entered])

  // First time landing on the manual board this browser, surface the
  // dismissible cheat-sheet explainer banner.
  useEffect(() => {
    if (
      entered === 'board' &&
      typeof window !== 'undefined' &&
      !window.localStorage.getItem(BOARD_BANNER_SEEN_KEY)
    ) {
      setBoardBannerVisible(true)
    }
  }, [entered])

  const dismissBoardBanner = useCallback(() => {
    setBoardBannerVisible(false)
    if (typeof window !== 'undefined') window.localStorage.setItem(BOARD_BANNER_SEEN_KEY, '1')
  }, [])

  const enterLive = useCallback(() => {
    requestTurnNotificationPermission()
    setLiveMode(true)
    setEntered('live')
  }, [])

  const enterBoard = useCallback(() => {
    setEntered('board')
  }, [])

  const handleNewDraft = useCallback(() => {
    resetDraft()
    // Clear the session so next board fetch creates a fresh one
    setSessionId(null)
    setEntered(null)
    void refetch()
  }, [resetDraft, setSessionId, refetch])

  const handleReset = useCallback(() => {
    resetDraft()
    setEntered(null)
    void refetch()
  }, [resetDraft, refetch])

  const players = data?.players ?? []
  const roster = data?.my_roster ?? []
  const remainingNeeds = data?.remaining_needs ?? {}
  const picksCount = data?.my_pick_count ?? 0

  // Stack/overlap hints refetch whenever the roster changes (a parallel
  // backend lane -- degrades to an empty map on 404/error).
  const { hints: stackHints, hintsByPlayerName } = useStackHints(sessionId, roster)

  const activeStrategy = asDraftStrategy(data?.strategy ?? config.strategy)

  let content: React.ReactNode

  // -------------------------------------------------------------------------
  // Landing -- mode chooser with league-first setup
  // -------------------------------------------------------------------------
  if (entered === null) {
    content = (
      <DraftLanding
        config={config}
        onConfigChange={setConfig}
        onOpenMockSetup={() => setMockSetupOpen(true)}
        onEnterLive={enterLive}
        onEnterBoard={enterBoard}
        onOpenSettings={() => setConfigOpen(true)}
        onOpenHowItWorks={() => setHowItWorks('landing')}
      />
    )
  } else if (mode === 'mock' && sessionId) {
    // -----------------------------------------------------------------------
    // Mock draft mode
    // -----------------------------------------------------------------------
    content = (
      <FadeIn className='space-y-[var(--gap-stack)]'>
        <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
          <Icons.clipboardText className='h-[var(--space-4)] w-[var(--space-4)]' />
          <h2 className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
            Mock Draft Simulation
          </h2>
          <LeagueContextChip config={config} onChange={() => setConfigOpen(true)} />
          <span className='bg-muted text-muted-foreground inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold'>
            {STRATEGY_LABELS[asDraftStrategy(config.strategy)]}
          </span>
          <PressScale className='ml-auto'>
            <Button variant='ghost' size='sm' onClick={() => setHowItWorks('mock')}>
              <Icons.help className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
              How this works
            </Button>
          </PressScale>
        </div>
        <MockDraftView
          sessionId={sessionId}
          config={config}
          onReset={handleReset}
          timerSeconds={mockTimerSeconds}
          accentColor={PLATFORM_ACCENT[activePlatform]}
        />
      </FadeIn>
    )
  } else if (liveMode) {
    // -----------------------------------------------------------------------
    // Live draft co-pilot (reads a real Sleeper draft, our engine drives picks)
    // -----------------------------------------------------------------------
    content = (
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
          <div className='ml-auto flex items-center gap-[var(--space-2)]'>
            <PressScale>
              <Button variant='ghost' size='sm' onClick={() => setHowItWorks('live')}>
                <Icons.help className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
                How this works
              </Button>
            </PressScale>
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
  } else {
    // -----------------------------------------------------------------------
    // Normal draft board view
    // -----------------------------------------------------------------------
    content = (
      <FadeIn className='space-y-[var(--gap-stack)]'>
        {/* Top toolbar */}
        <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
          {/* Board / Sleepers switch */}
          <Tabs value={mainTab} onValueChange={v => setMainTab(v as MainTab)}>
            <TabsList>
              <TabsTrigger value='board' className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                Board
              </TabsTrigger>
              <TabsTrigger value='sleepers' className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                Sleepers
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Position filter (board tab only) */}
          {mainTab === 'board' && (
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
          )}

          <LeagueContextChip config={config} onChange={() => setConfigOpen(true)} />

          <span className='bg-muted text-muted-foreground inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold'>
            {STRATEGY_LABELS[activeStrategy]}
          </span>

          <div className='ml-auto flex items-center gap-[var(--space-2)]'>
            <PressScale>
              <Button variant='ghost' size='sm' onClick={() => setHowItWorks('board')}>
                <Icons.help className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
                How this works
              </Button>
            </PressScale>
            <PressScale>
              <Button
                variant='default'
                size='sm'
                onClick={enterLive}
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
                onClick={() => setMockSetupOpen(true)}
              >
                <Icons.arrowRight className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
                Mock Draft
              </Button>
            </PressScale>
            <UndoButton
              label='Undo'
              onUndo={() => undoMutation.mutate()}
              isPending={undoMutation.isPending}
              isConflict={undoIsConflict || (data?.picks_taken ?? 0) === 0}
            />
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

        {/* First-run cheat-sheet explainer (manual board only, own dismiss flag) */}
        {boardBannerVisible && (
          <Alert>
            <AlertDescription className='flex flex-wrap items-center justify-between gap-[var(--space-2)]'>
              <span>
                This is your cheat sheet — our model&apos;s ranks vs real ADP. Following a real
                draft? Hit Draft for your picks, Taken for everyone else&apos;s.
              </span>
              <Button variant='ghost' size='sm' onClick={dismissBoardBanner}>
                Got it
              </Button>
            </AlertDescription>
          </Alert>
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
          ) : mainTab === 'sleepers' ? (
            <SleepersPanel sessionId={sessionId} />
          ) : (
            <div className='flex flex-col gap-[var(--gap-stack)] lg:flex-row'>
              {/* Draft board (70%) */}
              <div className='min-w-0 flex-1'>
                <DraftBoardTable
                  players={players}
                  positionFilter={positionFilter}
                  onDraft={handleDraftPlayer}
                  isPicking={pickMutation.isPending}
                  hintsByPlayerName={hintsByPlayerName}
                />
              </div>

              {/* Sidebar panels (30%) */}
              <div className='w-full space-y-[var(--gap-stack)] lg:w-72 lg:shrink-0'>
                <MyRosterPanel
                  roster={roster}
                  remainingNeeds={remainingNeeds}
                  picksCount={picksCount}
                  rosterRisk={data?.roster_risk}
                />
                <RecommendationsPanel
                  sessionId={sessionId}
                  positionFilter={positionFilter}
                  players={players}
                  hintsByPlayerName={hintsByPlayerName}
                  stackHints={stackHints}
                />
              </div>
            </div>
          )}
        </DataLoadReveal>
      </FadeIn>
    )
  }

  return (
    <>
      {content}

      {/* Config dialog (manual board only — scoring/roster/teams/season) */}
      <DraftConfigDialog
        config={config}
        onConfigChange={setConfig}
        open={configOpen}
        onOpenChange={setConfigOpen}
        onNewDraft={handleNewDraft}
      />

      {/* Mock draft setup (slot/timer/rankings selection — never instant-starts) */}
      <MockDraftSetupDialog
        config={config}
        onConfigChange={setConfig}
        onStartMock={handleStartMock}
        open={mockSetupOpen}
        onOpenChange={setMockSetupOpen}
      />

      {/* Hand-rolled "how this works" guidance, reopenable from the landing and every mode's toolbar */}
      <HowItWorksDialog
        mode={howItWorks ?? 'landing'}
        open={howItWorks !== null}
        onOpenChange={open => {
          if (!open) setHowItWorks(null)
        }}
      />
    </>
  )
}
