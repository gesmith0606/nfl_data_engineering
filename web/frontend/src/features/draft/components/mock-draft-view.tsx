'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import { advanceMockDraft, undoMockDraftPick } from '@/features/nfl/api/service'
import { isConflictError } from '@/lib/nfl/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Icons } from '@/components/icons'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table'
import { PressScale } from '@/lib/motion-primitives'
import { SUCCESS_TEXT, WARN_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors'
import { slotOnClock, picksUntilNextTurn } from '@/lib/nfl/draft-math'
import { PickClock } from './pick-clock'
import { UndoButton } from './undo-button'
import { DraftReportCard } from './draft-report-card'
import type { DraftConfig, MockDraftPickResponse } from '@/lib/nfl/types'

interface MockDraftViewProps {
  sessionId: string
  config: DraftConfig
  onReset: () => void
  /** Room's pick clock length; null hides the clock. */
  timerSeconds?: number | null
  /** Platform accent for the clock ring/bar. */
  accentColor?: string
}

const GRADE_COLORS: Record<string, string> = {
  A: SUCCESS_TEXT,
  B: 'text-blue-600 dark:text-blue-400',
  C: WARN_TEXT,
  D: DANGER_TEXT
}

/** Bot-burst reveal pace -- fast enough to feel automatic, slow enough to read. */
const BOT_BURST_INTERVAL_MS = 150
/** Hard stop so a stuck backend response can't spin the skip loop forever. */
const BOT_BURST_MAX_STEPS = 60

export function MockDraftView({
  sessionId,
  config,
  onReset,
  timerSeconds = null,
  accentColor
}: MockDraftViewProps) {
  const [picks, setPicks] = useState<MockDraftPickResponse[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [isComplete, setIsComplete] = useState(false)
  const [draftGrade, setDraftGrade] = useState<string | null>(null)
  const [totalPts, setTotalPts] = useState<number | null>(null)
  const [totalVorp, setTotalVorp] = useState<number | null>(null)
  const [expiredNotice, setExpiredNotice] = useState<string | null>(null)
  const [botBurstActive, setBotBurstActive] = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)
  const autoRunRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const botBurstRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const noticeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const advanceMutation = useMutation({
    mutationFn: () => advanceMockDraft({ session_id: sessionId }),
    onSuccess: (data) => {
      setPicks(prev => [...prev, data])
      if (data.is_complete) {
        setIsComplete(true)
        setDraftGrade(data.draft_grade)
        setTotalPts(data.total_pts)
        setTotalVorp(data.total_vorp)
        setIsRunning(false)
        setBotBurstActive(false)
        if (autoRunRef.current) {
          clearInterval(autoRunRef.current)
          autoRunRef.current = null
        }
      } else if (data.is_user_turn && !isRunning) {
        // The pick that just landed was the user's -- kick off a skippable
        // bot-burst reveal of the following opponent picks (FantasyPros-flow
        // pacing) rather than making the user click Advance Pick repeatedly.
        setBotBurstActive(true)
      }
    },
    onError: () => {
      setIsRunning(false)
      setBotBurstActive(false)
      if (autoRunRef.current) {
        clearInterval(autoRunRef.current)
        autoRunRef.current = null
      }
    }
  })

  const undoMutation = useMutation({
    mutationFn: () => undoMockDraftPick(sessionId),
    onSuccess: (data) => {
      setPicks(prev => prev.slice(0, data.pick_number))
      setIsComplete(false)
      setDraftGrade(null)
      setTotalPts(null)
      setTotalVorp(null)
      setBotBurstActive(false)
      setIsRunning(false)
    }
  })
  const undoIsConflict = undoMutation.isError && isConflictError(undoMutation.error)

  // Auto-scroll to latest pick
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [picks])

  // Clear any pending "auto-dismiss" timeout on unmount.
  useEffect(() => {
    return () => {
      if (noticeTimeoutRef.current) clearTimeout(noticeTimeoutRef.current)
    }
  }, [])

  // Auto-run interval
  useEffect(() => {
    if (isRunning && !isComplete) {
      autoRunRef.current = setInterval(() => {
        if (!advanceMutation.isPending) {
          advanceMutation.mutate()
        }
      }, 300)
    } else {
      if (autoRunRef.current) {
        clearInterval(autoRunRef.current)
        autoRunRef.current = null
      }
    }
    return () => {
      if (autoRunRef.current) {
        clearInterval(autoRunRef.current)
        autoRunRef.current = null
      }
    }
  }, [isRunning, isComplete, advanceMutation])

  const advanceMutateRef = useRef(advanceMutation.mutate)
  advanceMutateRef.current = advanceMutation.mutate

  /**
   * Bot-burst reveal -- schedules ONE advance BOT_BURST_INTERVAL_MS after the
   * last pick landed, then (as long as the burst is still active and that
   * pick wasn't the user's turn / completion) relies on the resulting
   * `picks` state update to re-run this effect and schedule the next one.
   * Keyed off `picks.length` rather than the mutation object -- the mutation
   * result is a fresh reference every render, which would otherwise tear
   * down and reschedule the timer on unrelated re-renders.
   */
  useEffect(() => {
    if (!botBurstActive || isComplete) return
    const id = setTimeout(() => {
      advanceMutateRef.current(undefined, {
        onSuccess: data => {
          if (data.is_user_turn || data.is_complete) setBotBurstActive(false)
        }
      })
    }, BOT_BURST_INTERVAL_MS)
    botBurstRef.current = id
    return () => {
      clearTimeout(id)
      botBurstRef.current = null
    }
    // picks.length (not `picks`/`advanceMutation`) is the real trigger: each
    // landed pick should reschedule exactly one more timer while bursting.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [botBurstActive, isComplete, picks.length])

  /** Skip fast-forwards the bot burst: fire remaining advances with no delay between them. */
  const handleSkipBurst = useCallback(() => {
    if (!botBurstActive) return
    setBotBurstActive(false)
    if (botBurstRef.current) {
      clearTimeout(botBurstRef.current)
      botBurstRef.current = null
    }
    const runNext = (step: number) => {
      if (step >= BOT_BURST_MAX_STEPS) return
      advanceMutateRef.current(undefined, {
        onSuccess: data => {
          if (!data.is_user_turn && !data.is_complete) runNext(step + 1)
        }
      })
    }
    runNext(0)
  }, [botBurstActive])

  const totalPicks = config.n_teams * 15 // rough estimate
  const currentPick = picks.length
  const userPicks = picks.filter(p => p.is_user_turn)
  const nextPickNo = currentPick + 1
  const isUserTurnNext = slotOnClock(nextPickNo, config.n_teams) === config.user_pick
  const picksUntilTurn = picksUntilNextTurn(nextPickNo, config.user_pick, config.n_teams)

  /**
   * The clock expiring on the user's turn auto-drafts for them -- same
   * action as "Advance Pick" (the backend already auto-drafts the advisor's
   * top recommendation on the user's turn), just triggered by the timer
   * instead of a click. Bots are unaffected: the clock reaching zero on an
   * opponent's turn does nothing (the draft still advances only via
   * "Advance Pick" / "Auto-Run", same as before).
   */
  const handleClockExpire = useCallback(() => {
    if (isComplete || advanceMutation.isPending || isRunning || botBurstActive) return
    advanceMutation.mutate(undefined, {
      onSuccess: data => {
        if (data.is_user_turn && data.player_name) {
          setExpiredNotice(`Clock expired — auto-drafted ${data.player_name}`)
          if (noticeTimeoutRef.current) clearTimeout(noticeTimeoutRef.current)
          noticeTimeoutRef.current = setTimeout(() => setExpiredNotice(null), 4000)
        }
      }
    })
  }, [isComplete, isRunning, botBurstActive, advanceMutation])

  const controlsDisabled = isComplete || advanceMutation.isPending || isRunning || botBurstActive

  return (
    <div className='space-y-[var(--gap-stack)]'>
      {/* Controls */}
      <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
        <PressScale>
          <Button
            variant='outline'
            size='sm'
            onClick={() => advanceMutation.mutate()}
            disabled={controlsDisabled}
          >
            {advanceMutation.isPending ? (
              <Icons.spinner className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)] animate-spin' />
            ) : null}
            Advance Pick
          </Button>
        </PressScale>

        <PressScale>
          <Button
            variant='outline'
            size='sm'
            onClick={() => setIsRunning(prev => !prev)}
            disabled={isComplete || botBurstActive}
          >
            {isRunning ? (
              <>
                <Icons.minus className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
                Pause
              </>
            ) : (
              <>
                <Icons.arrowRight className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
                Auto-Run
              </>
            )}
          </Button>
        </PressScale>

        <UndoButton
          label='Undo my last pick'
          onUndo={() => undoMutation.mutate()}
          isPending={undoMutation.isPending}
          isConflict={undoIsConflict || picks.length === 0}
        />

        <PressScale>
          <Button variant='outline' size='sm' onClick={onReset}>
            <Icons.close className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
            Reset
          </Button>
        </PressScale>

        {!isComplete && picksUntilTurn > 0 && (
          <span className='bg-muted text-muted-foreground inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium'>
            Next turn in {picksUntilTurn} pick{picksUntilTurn === 1 ? '' : 's'}
          </span>
        )}

        <span className='text-muted-foreground ml-auto text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
          Pick {currentPick} of ~{totalPicks}
        </span>
        {!isComplete && (
          <PickClock
            pickNumber={nextPickNo}
            timerSeconds={timerSeconds}
            accentColor={accentColor}
            onExpire={isUserTurnNext ? handleClockExpire : undefined}
          />
        )}
      </div>

      {expiredNotice && (
        <p className={`text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium ${WARN_TEXT}`}>
          {expiredNotice}
        </p>
      )}

      {/* Bot-burst ticker -- shown while opponent picks reveal in sequence after your pick. */}
      {botBurstActive && (
        <div className='flex items-center gap-[var(--space-2)] rounded-md border p-[var(--space-2)]'>
          <Icons.spinner className='text-muted-foreground h-[var(--space-4)] w-[var(--space-4)] animate-spin' />
          <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            Bots picking...
          </span>
          <PressScale className='ml-auto'>
            <Button variant='ghost' size='sm' onClick={handleSkipBurst}>
              Skip
            </Button>
          </PressScale>
        </div>
      )}

      {/* Results card when complete */}
      {isComplete && (
        <Card className='border-green-200 dark:border-green-800'>
          <CardHeader className='pb-[var(--space-2)]'>
            <CardTitle className='text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
              Draft Complete
            </CardTitle>
          </CardHeader>
          <CardContent className='space-y-[var(--space-3)]'>
            {draftGrade && (
              <div className='flex items-center gap-[var(--space-3)]'>
                <span
                  className={`text-[length:var(--fs-h1)] leading-[var(--lh-h1)] font-bold ${GRADE_COLORS[draftGrade] ?? 'text-foreground'}`}
                >
                  {draftGrade}
                </span>
                <div>
                  <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                    Draft Grade
                  </p>
                  {totalPts !== null && (
                    <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                      {totalPts.toFixed(0)} projected pts · VORP{' '}
                      {totalVorp?.toFixed(1) ?? '—'}
                    </p>
                  )}
                </div>
              </div>
            )}

            <div>
              <p className='mb-[var(--space-1)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                Your Roster ({userPicks.length} picks)
              </p>
              <div className='space-y-0.5'>
                {userPicks.map((p, i) => (
                  <p
                    key={i}
                    className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'
                  >
                    Rd {p.round_number}: {p.player_name ?? '—'} ({p.position ?? '?'})
                  </p>
                ))}
              </div>
            </div>

            <div className='flex flex-wrap gap-[var(--space-2)]'>
              <PressScale>
                <Button onClick={onReset} size='sm'>
                  Run Again
                </Button>
              </PressScale>
            </div>

            <DraftReportCard sessionId={sessionId} enabled={isComplete} />
          </CardContent>
        </Card>
      )}

      {/* Draft log */}
      <div className='max-h-[500px] overflow-y-auto rounded-md border'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className='w-16'>Pick</TableHead>
              <TableHead className='w-16'>Round</TableHead>
              <TableHead className='w-20'>Team</TableHead>
              <TableHead>Player</TableHead>
              <TableHead className='w-14'>Pos</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {picks.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className='text-muted-foreground py-[var(--space-8)] text-center text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'
                >
                  Click &quot;Advance Pick&quot; or &quot;Auto-Run&quot; to start the simulation.
                </TableCell>
              </TableRow>
            ) : (
              picks.map((pick, i) => (
                <TableRow
                  key={i}
                  className={pick.is_user_turn ? 'bg-primary/10 font-medium' : undefined}
                >
                  <TableCell className='font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums'>
                    {pick.pick_number}
                  </TableCell>
                  <TableCell className='font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums'>
                    {pick.round_number}
                  </TableCell>
                  <TableCell className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                    {pick.is_user_turn ? (
                      <span className='text-primary font-semibold'>YOU</span>
                    ) : (
                      <span className='text-muted-foreground'>OPP</span>
                    )}
                  </TableCell>
                  <TableCell className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                    {pick.player_name ?? '—'}
                  </TableCell>
                  <TableCell className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                    {pick.position ?? '—'}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        <div ref={logEndRef} />
      </div>
    </div>
  )
}
