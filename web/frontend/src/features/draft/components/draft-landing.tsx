'use client'

import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Icons } from '@/components/icons'
import { FadeIn, PressScale } from '@/lib/motion-primitives'
import { cn } from '@/lib/utils'
import { fetchLeagueOverview } from '@/lib/nfl/api'
import { loadConnectedLeagues } from '@/lib/nfl/connected-leagues'
import { usePlatformPresets } from '../hooks/use-platform-presets'
import { mapLeagueOverviewToConfig } from '../utils/league-config'
import {
  PLATFORM_ACCENT,
  PLATFORM_LABELS,
  applyPlatformPreset,
  type RoomPlatform
} from '../utils/platform-presets'
import type { ConnectedLeague, DraftConfig } from '@/lib/nfl/types'

export const DRAFT_TOUR_SEEN_KEY = 'nfl.draftTourSeen'

const ROOM_PLATFORM_CHOICES: RoomPlatform[] = ['espn', 'sleeper', 'yahoo']

interface DraftLandingProps {
  config: DraftConfig
  onConfigChange: (config: DraftConfig) => void
  onOpenMockSetup: () => void
  onEnterLive: () => void
  onEnterBoard: () => void
  onOpenSettings: () => void
  onOpenHowItWorks: () => void
}

/**
 * Draft tool landing -- shown before the user has picked a mode this
 * session. League-first setup strip on top (FantasyPros-style: get the
 * league context before anything else), then the three mode cards. A
 * dismissible first-run "how this works" panel appears above the mode cards
 * until the user dismisses it once.
 */
export function DraftLanding({
  config,
  onConfigChange,
  onOpenMockSetup,
  onEnterLive,
  onEnterBoard,
  onOpenSettings,
  onOpenHowItWorks
}: DraftLandingProps) {
  const presets = usePlatformPresets()
  const [leagues, setLeagues] = useState<ConnectedLeague[]>([])
  const [selectedLeagueId, setSelectedLeagueId] = useState<string | null>(null)
  const [leagueError, setLeagueError] = useState<string | null>(null)
  const [introOpen, setIntroOpen] = useState(false)

  useEffect(() => {
    setLeagues(loadConnectedLeagues())
    if (typeof window !== 'undefined' && !window.localStorage.getItem(DRAFT_TOUR_SEEN_KEY)) {
      setIntroOpen(true)
    }
  }, [])

  const leagueMutation = useMutation({
    mutationFn: (league: ConnectedLeague) => fetchLeagueOverview(league.league_id, league.user_id),
    onSuccess: (overview, league) => {
      setLeagueError(null)
      setSelectedLeagueId(league.league_id)
      onConfigChange(mapLeagueOverviewToConfig(overview, config))
    },
    onError: () => {
      setSelectedLeagueId(null)
      setLeagueError("Couldn't load that league's settings — pick a platform room or customize below instead.")
    }
  })

  function dismissIntro() {
    setIntroOpen(false)
    if (typeof window !== 'undefined') window.localStorage.setItem(DRAFT_TOUR_SEEN_KEY, '1')
  }

  function handlePlatformRoom(platform: RoomPlatform) {
    setLeagueError(null)
    setSelectedLeagueId(null)
    onConfigChange(applyPlatformPreset(config, platform, presets))
  }

  return (
    <FadeIn className='space-y-[var(--gap-stack)]'>
      <div className='flex flex-wrap items-start justify-between gap-[var(--space-2)]'>
        <div>
          <h1 className='text-[length:var(--fs-lg)] leading-[var(--lh-lg)] font-semibold'>
            Set up your draft
          </h1>
          <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
            League first, then pick a mode.
          </p>
        </div>
        <PressScale>
          <Button variant='ghost' size='sm' onClick={onOpenHowItWorks}>
            <Icons.help className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)]' />
            How this works
          </Button>
        </PressScale>
      </div>

      {introOpen && (
        <Card>
          <CardContent className='space-y-[var(--space-3)] p-[var(--space-4)]'>
            <h2 className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>How this works</h2>
            <ul className='text-muted-foreground list-disc space-y-1 pl-[var(--space-5)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
              <li>Set your league — connect Sleeper, pick a platform room, or go custom.</li>
              <li>
                Pick a mode — Mock Draft to practice, Live Co-Pilot to sync a real draft, or the
                Cheat Sheet Board to track one by hand.
              </li>
              <li>
                During any draft, Draft means it&apos;s your pick and Taken means anyone else&apos;s
                — recommendations update every pick.
              </li>
            </ul>
            <PressScale>
              <Button size='sm' onClick={dismissIntro}>
                Got it
              </Button>
            </PressScale>
          </CardContent>
        </Card>
      )}

      {/* League setup strip */}
      <div className='grid gap-[var(--gap-stack)] md:grid-cols-3'>
        <Card>
          <CardContent className='space-y-[var(--space-2)] p-[var(--space-4)]'>
            <h3 className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
              <Icons.teams className='h-[var(--space-4)] w-[var(--space-4)]' />
              Use my league
            </h3>
            {leagues.length === 0 ? (
              <div className='text-muted-foreground space-y-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                <p>No leagues connected yet.</p>
                <Link href='/dashboard/leagues' className='text-primary underline'>
                  Connect your Sleeper league
                </Link>
              </div>
            ) : (
              <ul className='space-y-[var(--space-2)]'>
                {leagues.map(league => (
                  <li key={league.league_id}>
                    <PressScale>
                      <button
                        type='button'
                        onClick={() => leagueMutation.mutate(league)}
                        disabled={leagueMutation.isPending}
                        className={cn(
                          'hover:bg-accent w-full rounded-md border px-[var(--space-3)] py-[var(--space-2)] text-left text-[length:var(--fs-xs)] leading-[var(--lh-xs)] transition-colors disabled:opacity-60',
                          selectedLeagueId === league.league_id && 'border-primary'
                        )}
                      >
                        <div className='font-medium'>{league.league_name}</div>
                        <div className='text-muted-foreground'>{league.scoring_format_label}</div>
                      </button>
                    </PressScale>
                  </li>
                ))}
              </ul>
            )}
            {leagueError && (
              <p className='text-destructive text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>{leagueError}</p>
            )}
            {selectedLeagueId && !leagueError && (
              <p className='text-muted-foreground text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'>
                Approximated from your league settings — exact custom scoring lands later.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className='space-y-[var(--space-2)] p-[var(--space-4)]'>
            <h3 className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
              <Icons.target className='h-[var(--space-4)] w-[var(--space-4)]' />
              Platform room
            </h3>
            <div className='flex flex-wrap gap-[var(--space-2)]'>
              {ROOM_PLATFORM_CHOICES.map(platform => (
                <PressScale key={platform}>
                  <button
                    type='button'
                    onClick={() => handlePlatformRoom(platform)}
                    className='rounded-full border px-[var(--space-3)] py-1 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold'
                    style={
                      config.platform === platform
                        ? { color: PLATFORM_ACCENT[platform], borderColor: PLATFORM_ACCENT[platform] }
                        : undefined
                    }
                  >
                    {PLATFORM_LABELS[platform]}
                  </button>
                </PressScale>
              ))}
            </div>
            <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
              Pre-fills scoring, roster shape, and pick clock to match that room.
            </p>
          </CardContent>
        </Card>

        <PressScale>
          <Card
            role='button'
            tabIndex={0}
            onClick={onOpenSettings}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') onOpenSettings()
            }}
            className='hover:border-primary h-full cursor-pointer transition-colors'
          >
            <CardContent className='space-y-[var(--space-2)] p-[var(--space-4)]'>
              <h3 className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
                <Icons.settings className='h-[var(--space-4)] w-[var(--space-4)]' />
                Custom
              </h3>
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                Skip the presets — set scoring, roster, and teams yourself.
              </p>
            </CardContent>
          </Card>
        </PressScale>
      </div>

      {/* Mode cards */}
      <div className='grid gap-[var(--gap-stack)] md:grid-cols-3'>
        <PressScale className='md:col-span-2'>
          <Card
            role='button'
            tabIndex={0}
            onClick={onOpenMockSetup}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') onOpenMockSetup()
            }}
            className='h-full cursor-pointer border-2 transition-colors'
            style={{ borderColor: 'var(--wc-mint,#91edd0)' }}
          >
            <CardContent className='space-y-[var(--space-3)] p-[var(--space-6)]'>
              <Icons.football className='h-[var(--space-8)] w-[var(--space-8)]' style={{ color: 'var(--wc-mint,#91edd0)' }} />
              <h2 className='text-[length:var(--fs-lg)] leading-[var(--lh-lg)] font-bold'>Mock Draft</h2>
              <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                Practice vs realistic bots in your league&apos;s style.
              </p>
            </CardContent>
          </Card>
        </PressScale>

        <div className='flex flex-col gap-[var(--gap-stack)]'>
          <PressScale>
            <Card
              role='button'
              tabIndex={0}
              onClick={onEnterLive}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') onEnterLive()
              }}
              className='hover:border-primary cursor-pointer transition-colors'
            >
              <CardContent className='space-y-[var(--space-2)] p-[var(--space-4)]'>
                <Icons.target className='h-[var(--space-6)] w-[var(--space-6)]' />
                <h3 className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
                  Live Draft Co-Pilot
                </h3>
                <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  Sync your real Sleeper/Yahoo draft or mirror ESPN.
                </p>
              </CardContent>
            </Card>
          </PressScale>

          <PressScale>
            <Card
              role='button'
              tabIndex={0}
              onClick={onEnterBoard}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') onEnterBoard()
              }}
              className='hover:border-primary cursor-pointer transition-colors'
            >
              <CardContent className='space-y-[var(--space-2)] p-[var(--space-4)]'>
                <Icons.table className='h-[var(--space-6)] w-[var(--space-6)]' />
                <h3 className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold'>
                  Cheat Sheet Board
                </h3>
                <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  Full rankings with ADP value, tiers and sleepers — track any draft manually.
                </p>
              </CardContent>
            </Card>
          </PressScale>
        </div>
      </div>
    </FadeIn>
  )
}
