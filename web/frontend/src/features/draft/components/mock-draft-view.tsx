'use client'

import { useState, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { advanceMockDraft } from '@/features/nfl/api/service'
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
import type { DraftConfig, MockDraftPickResponse } from '@/lib/nfl/types'

interface MockDraftViewProps {
  sessionId: string
  config: DraftConfig
  onReset: () => void
}

const GRADE_COLORS: Record<string, string> = {
  A: 'text-green-600 dark:text-green-400',
  B: 'text-blue-600 dark:text-blue-400',
  C: 'text-yellow-600 dark:text-yellow-400',
  D: 'text-red-600 dark:text-red-400'
}

export function MockDraftView({ sessionId, config, onReset }: MockDraftViewProps) {
  const [picks, setPicks] = useState<MockDraftPickResponse[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [isComplete, setIsComplete] = useState(false)
  const [draftGrade, setDraftGrade] = useState<string | null>(null)
  const [totalPts, setTotalPts] = useState<number | null>(null)
  const [totalVorp, setTotalVorp] = useState<number | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)
  const autoRunRef = useRef<ReturnType<typeof setInterval> | null>(null)

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
        if (autoRunRef.current) {
          clearInterval(autoRunRef.current)
          autoRunRef.current = null
        }
      }
    },
    onError: () => {
      setIsRunning(false)
      if (autoRunRef.current) {
        clearInterval(autoRunRef.current)
        autoRunRef.current = null
      }
    }
  })

  // Auto-scroll to latest pick
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [picks])

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

  const totalPicks = config.n_teams * 15 // rough estimate
  const currentPick = picks.length
  const userPicks = picks.filter(p => p.is_user_turn)

  return (
    <div className='space-y-4'>
      {/* Controls */}
      <div className='flex flex-wrap items-center gap-2'>
        <Button
          variant='outline'
          size='sm'
          onClick={() => advanceMutation.mutate()}
          disabled={isComplete || advanceMutation.isPending || isRunning}
        >
          {advanceMutation.isPending ? (
            <Icons.spinner className='mr-1.5 h-4 w-4 animate-spin' />
          ) : null}
          Advance Pick
        </Button>

        <Button
          variant='outline'
          size='sm'
          onClick={() => setIsRunning(prev => !prev)}
          disabled={isComplete}
        >
          {isRunning ? (
            <>
              <Icons.minus className='mr-1.5 h-4 w-4' />
              Pause
            </>
          ) : (
            <>
              <Icons.arrowRight className='mr-1.5 h-4 w-4' />
              Auto-Run
            </>
          )}
        </Button>

        <Button variant='outline' size='sm' onClick={onReset}>
          <Icons.close className='mr-1.5 h-4 w-4' />
          Reset
        </Button>

        <span className='text-muted-foreground ml-auto text-sm'>
          Pick {currentPick} of ~{totalPicks}
        </span>
      </div>

      {/* Results card when complete */}
      {isComplete && (
        <Card className='border-green-200 dark:border-green-800'>
          <CardHeader className='pb-2'>
            <CardTitle className='text-base'>Draft Complete</CardTitle>
          </CardHeader>
          <CardContent className='space-y-3'>
            {draftGrade && (
              <div className='flex items-center gap-3'>
                <span className={`text-5xl font-bold ${GRADE_COLORS[draftGrade] ?? 'text-foreground'}`}>
                  {draftGrade}
                </span>
                <div>
                  <p className='font-medium'>Draft Grade</p>
                  {totalPts !== null && (
                    <p className='text-muted-foreground text-sm'>
                      {totalPts.toFixed(0)} projected pts · VORP {totalVorp?.toFixed(1) ?? '—'}
                    </p>
                  )}
                </div>
              </div>
            )}

            <div>
              <p className='mb-1 text-sm font-medium'>Your Roster ({userPicks.length} picks)</p>
              <div className='space-y-0.5'>
                {userPicks.map((p, i) => (
                  <p key={i} className='text-muted-foreground text-sm'>
                    Rd {p.round_number}: {p.player_name ?? '—'} ({p.position ?? '?'})
                  </p>
                ))}
              </div>
            </div>

            <Button onClick={onReset} size='sm'>
              Run Again
            </Button>
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
                <TableCell colSpan={5} className='text-muted-foreground py-8 text-center text-sm'>
                  Click &quot;Advance Pick&quot; or &quot;Auto-Run&quot; to start the simulation.
                </TableCell>
              </TableRow>
            ) : (
              picks.map((pick, i) => (
                <TableRow
                  key={i}
                  className={pick.is_user_turn ? 'bg-primary/10 font-medium' : undefined}
                >
                  <TableCell className='font-mono text-sm tabular-nums'>{pick.pick_number}</TableCell>
                  <TableCell className='font-mono text-sm tabular-nums'>{pick.round_number}</TableCell>
                  <TableCell className='text-sm'>
                    {pick.is_user_turn ? (
                      <span className='text-primary font-semibold'>YOU</span>
                    ) : (
                      <span className='text-muted-foreground'>OPP</span>
                    )}
                  </TableCell>
                  <TableCell className='text-sm'>{pick.player_name ?? '—'}</TableCell>
                  <TableCell className='text-muted-foreground text-sm'>{pick.position ?? '—'}</TableCell>
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
