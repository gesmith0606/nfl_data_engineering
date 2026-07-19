'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table'
import { Icons } from '@/components/icons'
import { PressScale, DataLoadReveal } from '@/lib/motion-primitives'
import { mockDraftReportQueryOptions } from '@/features/nfl/api/queries'
import { SUCCESS_TEXT, SUCCESS_BADGE, WARN_BADGE, deltaTextClass } from '@/lib/nfl/semantic-colors'

interface DraftReportCardProps {
  sessionId: string
  /** Report only exists once the mock is complete (or far enough along); gates the fetch. */
  enabled: boolean
}

const GRADE_COLORS: Record<string, string> = {
  A: SUCCESS_TEXT,
  B: 'text-blue-600 dark:text-blue-400',
  C: 'text-[var(--warn)]',
  D: 'text-[var(--danger)]'
}

/**
 * Post-draft report card: fetches GET /draft/mock/report and renders a
 * receipts-style breakdown — letter grade hero, grade notes, a per-pick
 * table (your pick vs. the best player still on the board, steal/reach from
 * adp_delta's sign), and floor/ceiling sums. Lazily fetched behind a "View
 * Draft Report" toggle so a completed-but-unopened mock doesn't pay for it.
 */
export function DraftReportCard({ sessionId, enabled }: DraftReportCardProps) {
  const [open, setOpen] = useState(false)
  const { data, isLoading, isError } = useQuery(mockDraftReportQueryOptions(sessionId, enabled && open))

  if (!enabled) return null

  return (
    <div className='space-y-[var(--space-3)]'>
      <PressScale>
        <Button variant='outline' size='sm' onClick={() => setOpen(o => !o)}>
          <Icons.chartBar className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
          {open ? 'Hide Draft Report' : 'View Draft Report'}
        </Button>
      </PressScale>

      {open && (
        <DataLoadReveal
          loading={isLoading}
          skeleton={
            <div className='flex items-center gap-[var(--space-2)] py-[var(--space-4)]'>
              <Icons.spinner className='text-muted-foreground h-[var(--space-4)] w-[var(--space-4)] animate-spin' />
              <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                Building your draft report...
              </span>
            </div>
          }
        >
          {isError ? (
            <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              Couldn&apos;t load the draft report. Try again in a moment.
            </p>
          ) : data ? (
            <div className='space-y-[var(--space-4)] rounded-md border p-[var(--space-4)]'>
              {/* Grade hero */}
              <div className='flex items-center gap-[var(--space-3)]'>
                <span
                  className={`text-[length:var(--fs-h1)] leading-[var(--lh-h1)] font-bold ${GRADE_COLORS[data.summary.letter_grade] ?? 'text-foreground'}`}
                >
                  {data.summary.letter_grade}
                </span>
                <div>
                  <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                    Draft Report
                  </p>
                  <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                    {data.summary.total_projected.toFixed(0)} projected pts · VORP{' '}
                    {data.summary.total_vorp.toFixed(1)}
                    {data.summary.floor_sum != null && data.summary.ceiling_sum != null
                      ? ` · Floor ${data.summary.floor_sum.toFixed(0)} / Ceiling ${data.summary.ceiling_sum.toFixed(0)}`
                      : ''}
                  </p>
                </div>
              </div>

              {/* Grade notes */}
              {data.summary.grade_notes.length > 0 && (
                <ul className='list-inside list-disc space-y-0.5'>
                  {data.summary.grade_notes.map((note, i) => (
                    <li key={i} className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                      {note}
                    </li>
                  ))}
                </ul>
              )}

              {/* Per-pick receipts */}
              <div className='overflow-x-auto rounded-md border'>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className='w-16'>Pick</TableHead>
                      <TableHead>Your Pick</TableHead>
                      <TableHead>Best Alternative</TableHead>
                      <TableHead className='w-20'>Δ VORP</TableHead>
                      <TableHead className='w-24' />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.picks.map(pick => (
                      <TableRow key={pick.overall_pick}>
                        <TableCell className='font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums'>
                          {pick.round}.{String(pick.overall_pick).padStart(2, '0')}
                        </TableCell>
                        <TableCell className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                          <span className='font-medium'>{pick.player_name}</span>{' '}
                          <span className='text-muted-foreground'>({pick.position})</span>
                        </TableCell>
                        <TableCell className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                          {pick.best_alternative
                            ? `${pick.best_alternative.player_name}${pick.best_alternative.vorp != null ? ` (VORP ${pick.best_alternative.vorp.toFixed(1)})` : ''}`
                            : '—'}
                        </TableCell>
                        <TableCell
                          className={`font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tabular-nums ${pick.vorp_delta != null ? deltaTextClass(pick.vorp_delta) : ''}`}
                        >
                          {pick.vorp_delta != null
                            ? `${pick.vorp_delta > 0 ? '+' : ''}${pick.vorp_delta.toFixed(1)}`
                            : '—'}
                        </TableCell>
                        <TableCell>
                          {pick.adp_delta != null && pick.adp_delta > 0 && (
                            <span
                              className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${SUCCESS_BADGE}`}
                              title={`Fell ${pick.adp_delta.toFixed(0)} spots past ADP`}
                            >
                              steal
                            </span>
                          )}
                          {pick.adp_delta != null && pick.adp_delta < 0 && (
                            <span
                              className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${WARN_BADGE}`}
                              title={`Drafted ${Math.abs(pick.adp_delta).toFixed(0)} spots ahead of ADP`}
                            >
                              reach
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          ) : null}
        </DataLoadReveal>
      )}
    </div>
  )
}
