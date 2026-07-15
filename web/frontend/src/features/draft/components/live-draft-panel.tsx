'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Icons } from '@/components/icons'
import { liveDraftQueryOptions } from '@/features/nfl/api/queries'
import { FadeIn, DataLoadReveal, PressScale } from '@/lib/motion-primitives'
import { getPositionBadgeClass } from '@/lib/nfl/position-colors'
import { SUCCESS_BADGE } from '@/lib/nfl/semantic-colors'
import type { LiveDraftParams } from '@/lib/nfl/types'

/**
 * Live draft co-pilot. Connect to a live Sleeper draft (by draft ID or
 * username) and the panel polls every ~5s: picks are read straight from the
 * platform, and the recommendation for your next pick comes from OUR
 * roster-aware engine (VORP + positional need + stacks) — not the platform's
 * autopick order. This is the answer to "autopick doesn't represent our board".
 */
export function LiveDraftPanel() {
  const [form, setForm] = useState<{ draftId: string; username: string; mySlot: string }>({
    draftId: '',
    username: '',
    mySlot: ''
  })
  const [connected, setConnected] = useState(false)

  const params: LiveDraftParams = {
    draftId: form.draftId.trim() || undefined,
    username: form.username.trim() || undefined,
    mySlot: form.mySlot ? Number(form.mySlot) : undefined,
    season: 2026,
    scoring: 'half_ppr',
    topN: 6
  }

  const { data, isLoading, isError, dataUpdatedAt } = useQuery(
    liveDraftQueryOptions(params, connected)
  )

  const canConnect = !!(params.draftId || params.username)

  return (
    <FadeIn className='space-y-[var(--gap-stack)]'>
      {/* Connection form */}
      <div className='rounded-md border p-[var(--space-4)] space-y-[var(--space-3)]'>
        <div className='flex items-center gap-[var(--space-2)]'>
          <Icons.target className='h-[var(--space-4)] w-[var(--space-4)]' />
          <h2 className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
            Live Draft Co-Pilot
          </h2>
          {connected && (
            <span className='inline-flex items-center gap-1 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-emerald-500'>
              <span className='h-2 w-2 rounded-full bg-emerald-500 animate-pulse' />
              LIVE
            </span>
          )}
        </div>
        <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
          Connect your live Sleeper draft. We read every pick as it happens and
          recommend your pick from our board — VORP, roster need, and stacks —
          not the platform&apos;s rankings.
        </p>
        <div className='flex flex-wrap items-end gap-[var(--space-2)]'>
          <label className='flex flex-col gap-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            <span className='text-muted-foreground'>Sleeper draft ID</span>
            <input
              className='border-input bg-background h-9 w-48 rounded-md border px-[var(--space-2)] text-[length:var(--fs-sm)]'
              placeholder='e.g. 1382528971035406336'
              value={form.draftId}
              onChange={e => setForm(f => ({ ...f, draftId: e.target.value }))}
            />
          </label>
          <span className='text-muted-foreground pb-2 text-[length:var(--fs-xs)]'>or</span>
          <label className='flex flex-col gap-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            <span className='text-muted-foreground'>Sleeper username</span>
            <input
              className='border-input bg-background h-9 w-40 rounded-md border px-[var(--space-2)] text-[length:var(--fs-sm)]'
              placeholder='Gforceee'
              value={form.username}
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
            />
          </label>
          <label className='flex flex-col gap-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            <span className='text-muted-foreground'>Your slot</span>
            <input
              className='border-input bg-background h-9 w-20 rounded-md border px-[var(--space-2)] text-[length:var(--fs-sm)]'
              placeholder='5'
              inputMode='numeric'
              value={form.mySlot}
              onChange={e => setForm(f => ({ ...f, mySlot: e.target.value }))}
            />
          </label>
          <PressScale>
            <Button
              size='sm'
              disabled={!canConnect}
              onClick={() => setConnected(c => (canConnect ? !c : c))}
            >
              {connected ? 'Disconnect' : 'Connect'}
            </Button>
          </PressScale>
        </div>
      </div>

      {/* Live state */}
      {connected && (
        <DataLoadReveal
          loading={isLoading}
          skeleton={
            <div className='flex items-center gap-[var(--space-2)] py-[var(--space-6)]'>
              <Icons.spinner className='text-muted-foreground h-[var(--space-5)] w-[var(--space-5)] animate-spin' />
              <span className='text-muted-foreground text-[length:var(--fs-sm)]'>
                Connecting to your live draft…
              </span>
            </div>
          }
        >
          {isError ? (
            <p className='text-muted-foreground text-[length:var(--fs-sm)] py-[var(--space-4)]'>
              Couldn&apos;t reach that draft. Check the draft ID / username (the
              draft must be active on Sleeper).
            </p>
          ) : data ? (
            <div className='flex flex-col gap-[var(--gap-stack)] lg:flex-row'>
              {/* Recommendation (our board) */}
              <div className='min-w-0 flex-1 space-y-[var(--space-3)]'>
                <div
                  className={`rounded-md border p-[var(--space-3)] ${
                    data.is_my_turn ? 'border-emerald-500 bg-emerald-500/5' : ''
                  }`}
                >
                  <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold'>
                    {data.is_my_turn
                      ? "🟢 YOU'RE ON THE CLOCK — take:"
                      : data.picks_until_my_turn != null
                        ? `Your pick in ${data.picks_until_my_turn} — our board says:`
                        : 'Our recommendation:'}
                  </p>
                  <p className='text-muted-foreground mt-1 text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
                    {data.reasoning}
                  </p>
                  <ol className='mt-[var(--space-2)] space-y-1'>
                    {data.recommendations.map((r, i) => (
                      <li
                        key={r.player_id || r.player_name}
                        className={`flex items-center gap-[var(--space-2)] rounded px-[var(--space-2)] py-1 ${
                          i === 0 ? 'bg-muted/60' : ''
                        }`}
                      >
                        <span className='text-muted-foreground w-5 font-mono text-[length:var(--fs-xs)] tabular-nums'>
                          {i + 1}
                        </span>
                        <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                          {r.player_name}
                        </span>
                        <span
                          className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] font-semibold ${getPositionBadgeClass(r.position)}`}
                        >
                          {r.position}
                        </span>
                        {r.fills_need && (
                          <span
                            className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] font-semibold ${SUCCESS_BADGE}`}
                          >
                            fills need
                          </span>
                        )}
                        <span className='text-muted-foreground ml-auto text-[length:var(--fs-micro)] tabular-nums'>
                          VORP {r.vorp} · {r.projected_points}pt
                        </span>
                      </li>
                    ))}
                  </ol>
                  {data.recommendations.some(r => r.stack_note) && (
                    <p className='text-muted-foreground mt-[var(--space-2)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
                      {data.recommendations.find(r => r.stack_note)?.stack_note}
                    </p>
                  )}
                </div>
                <p className='text-muted-foreground text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
                  {data.status} · {data.picks_made} picks made · {data.n_teams} teams
                  {dataUpdatedAt
                    ? ` · updated ${new Date(dataUpdatedAt).toLocaleTimeString()}`
                    : ''}
                </p>
              </div>

              {/* My roster + needs */}
              <div className='w-full space-y-[var(--space-3)] lg:w-64 lg:shrink-0'>
                <div className='rounded-md border p-[var(--space-3)]'>
                  <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold'>
                    My Team ({data.my_roster.length})
                  </p>
                  <ul className='mt-[var(--space-2)] space-y-1'>
                    {data.my_roster.length === 0 ? (
                      <li className='text-muted-foreground text-[length:var(--fs-micro)]'>
                        No picks yet.
                      </li>
                    ) : (
                      data.my_roster.map(p => (
                        <li
                          key={p.player_id || p.player_name}
                          className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
                        >
                          <span
                            className={`inline-flex w-8 justify-center rounded-full px-1 py-0.5 text-[length:var(--fs-micro)] font-semibold ${getPositionBadgeClass(p.position)}`}
                          >
                            {p.position}
                          </span>
                          <span className='font-medium'>{p.player_name}</span>
                        </li>
                      ))
                    )}
                  </ul>
                </div>
                <div className='rounded-md border p-[var(--space-3)]'>
                  <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold'>
                    Remaining Needs
                  </p>
                  <div className='mt-[var(--space-2)] flex flex-wrap gap-1'>
                    {Object.entries(data.remaining_needs)
                      .filter(([, n]) => n > 0)
                      .map(([pos, n]) => (
                        <span
                          key={pos}
                          className='bg-muted text-muted-foreground inline-flex items-center rounded px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] font-medium'
                        >
                          {pos} ×{n}
                        </span>
                      ))}
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </DataLoadReveal>
      )}
    </FadeIn>
  )
}
