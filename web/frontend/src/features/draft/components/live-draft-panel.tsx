'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Icons } from '@/components/icons'
import { liveDraftQueryOptions } from '@/features/nfl/api/queries'
import { FadeIn, DataLoadReveal, PressScale } from '@/lib/motion-primitives'
import { getPositionBadgeClass } from '@/lib/nfl/position-colors'
import { SUCCESS_BADGE } from '@/lib/nfl/semantic-colors'
import { pickLabel } from '@/lib/nfl/draft-math'
import { useTurnAlert, requestTurnNotificationPermission } from '../hooks/use-turn-alert'
import { CopyQueueButton } from './copy-queue-button'
import type { LiveDraftParams } from '@/lib/nfl/types'

const MOMENT_BADGE: Record<string, string> = {
  steal: 'text-emerald-500',
  value_drop: 'text-emerald-500',
  reach: 'text-amber-500',
  positional_run: 'text-sky-500',
  grade: 'text-muted-foreground'
}

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

  // Chime + browser notification + tab flash the moment it's your pick — the
  // silent-border-only version is how drafts get autodrafted away.
  useTurnAlert(
    !!data?.is_my_turn,
    connected,
    data?.recommendations[0]
      ? `Our board says ${data.recommendations[0].player_name} (${data.recommendations[0].position}).`
      : 'Check the GIQ board for your pick.'
  )

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
          <label
            htmlFor='live-draft-id'
            className='flex flex-col gap-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
          >
            <span className='text-muted-foreground'>Sleeper draft ID</span>
            <Input
              id='live-draft-id'
              className='w-48'
              placeholder='e.g. 1382528971035406336'
              value={form.draftId}
              onChange={e => setForm(f => ({ ...f, draftId: e.target.value }))}
            />
          </label>
          <span className='text-muted-foreground pb-2 text-[length:var(--fs-xs)]'>or</span>
          <label
            htmlFor='live-draft-username'
            className='flex flex-col gap-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
          >
            <span className='text-muted-foreground'>Sleeper username</span>
            <Input
              id='live-draft-username'
              className='w-40'
              placeholder='Gforceee'
              value={form.username}
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
            />
          </label>
          <label
            htmlFor='live-draft-slot'
            className='flex flex-col gap-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
          >
            <span className='text-muted-foreground'>Your slot</span>
            <Input
              id='live-draft-slot'
              className='w-20'
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
              onClick={() => {
                if (!connected && canConnect) requestTurnNotificationPermission()
                setConnected(c => (canConnect ? !c : c))
              }}
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
                  <div className='flex items-start justify-between gap-[var(--space-2)]'>
                    <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold'>
                      {data.is_my_turn
                        ? "🟢 YOU'RE ON THE CLOCK — take:"
                        : data.picks_until_my_turn != null
                          ? `Your pick in ${data.picks_until_my_turn}${
                              data.my_next_pick_no != null
                                ? ` (${pickLabel(data.my_next_pick_no, data.n_teams)})`
                                : ''
                            } — our board says:`
                          : 'Our recommendation:'}
                    </p>
                    <CopyQueueButton players={data.recommendations} />
                  </div>
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
                        {r.adp_diff != null && r.adp_diff >= 3 && (
                          <span
                            className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] font-semibold ${SUCCESS_BADGE}`}
                            title={`ADP ${r.adp_rank} — the market drafts them ${r.adp_diff} spots later than our board`}
                          >
                            steal +{r.adp_diff}
                          </span>
                        )}
                        <span className='text-muted-foreground ml-auto text-[length:var(--fs-micro)] tabular-nums'>
                          VORP {r.vorp} · {r.projected_points}pt
                          {r.adp_rank != null ? ` · ADP ${r.adp_rank}` : ''}
                        </span>
                      </li>
                    ))}
                  </ol>
                  {data.recommendations.some(r => r.stack_note) && (
                    <p className='text-muted-foreground mt-[var(--space-2)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
                      {data.recommendations.find(r => r.stack_note)?.stack_note}
                    </p>
                  )}
                  <p className='text-muted-foreground mt-[var(--space-2)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
                    Tip: Copy queue and preload it as your Sleeper queue — if
                    the pick timer ever expires, autopick drafts from our
                    board instead of the platform&apos;s.
                  </p>
                </div>

                {/* Key moments ticker — steals, reaches, positional runs */}
                {data.key_moments.length > 0 && (
                  <div className='rounded-md border p-[var(--space-3)]'>
                    <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold'>
                      Key Moments
                    </p>
                    <ul className='mt-[var(--space-2)] space-y-1'>
                      {data.key_moments.map(m => (
                        <li
                          key={`${m.kind}-${m.pick_no}-${m.player}`}
                          className='flex items-baseline gap-[var(--space-2)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
                        >
                          <span
                            className={`w-20 shrink-0 font-semibold uppercase ${MOMENT_BADGE[m.kind] ?? 'text-muted-foreground'}`}
                          >
                            {m.kind.replace('_', ' ')}
                          </span>
                          <span className='text-muted-foreground font-mono tabular-nums'>
                            #{m.pick_no}
                          </span>
                          <span className='font-medium'>{m.player}</span>
                          <span className='text-muted-foreground'>{m.detail}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

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
