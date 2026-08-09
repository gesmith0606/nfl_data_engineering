'use client';

/**
 * League Sync — Plan-3 implementation, WC26 Broadcast identity pass.
 *
 * Connect flow: enter Sleeper username → GET leagues → pick one → confirm
 * roster → save up to 3 leagues in localStorage (key: nfl.connectedLeagues).
 *
 * League home: roster report card (optimal lineup + bench + drop candidates),
 * waiver targets table, and a scoring badge showing how the league's custom
 * settings differ from standard half-PPR.
 *
 * No auth / gating — open for all users. Plan 2 (Clerk/Stripe) deferred.
 *
 * Presentation normalized to the shared broadcast primitives (BroadcastPanel/
 * StatPill/BroadcastTable + draft's broadcast-ui.ts class constants) so this
 * page reads as a sibling of rankings/draft rather than raw inline-Tailwind
 * markup. All data flow / handlers are unchanged from the pre-pass version.
 */

import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import {
  fetchLeagueDraftPrep,
  fetchLeagueMyWeek,
  fetchLeagueOverview,
  fetchLeagueRosterReport,
  fetchLeagueWaivers,
  sleeperLogin
} from '@/lib/nfl/api';
import {
  MAX_CONNECTED_LEAGUES as MAX_LEAGUES,
  loadConnectedLeagues as loadConnected,
  saveConnectedLeagues as saveConnected,
  upsertConnectedLeague as upsertConnected,
  removeConnectedLeague as removeConnected
} from '@/lib/nfl/connected-leagues';
import { getPositionBadgeClass } from '@/lib/nfl/position-colors';
import { DANGER_TEXT, SUCCESS_TEXT, WARN_TEXT } from '@/lib/nfl/semantic-colors';
import { useInfobar, type InfobarContent } from '@/components/ui/infobar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BroadcastPanel, StatPill } from '@/components/nfl/broadcast-panel';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { DataLoadReveal } from '@/lib/motion-primitives';
import {
  WC_CTA_BUTTON,
  WC_OUTLINE_BUTTON,
  WC_GHOST_BUTTON,
  WC_TABS_LIST,
  WC_TAB_TRIGGER,
  WC_INPUT,
  WC_HEADING,
  WC_KICKER
} from '@/features/draft/utils/broadcast-ui';
import type {
  BestAvailablePlayer,
  ConnectedLeague,
  DropCandidate,
  KeeperCandidate,
  LeagueDraftPrepResponse,
  LeagueOverviewResponse,
  LeagueRosterPlayer,
  MyWeekPlayer,
  MyWeekResponse,
  MyWeekSlot,
  MyWeekWaiverTarget,
  RosterReportResponse,
  SleeperLeague,
  SleeperUser,
  StarterSlot,
  WaiverTarget,
  WaiversResponse
} from '@/lib/nfl/types';

// localStorage helpers (cap 3 leagues) live in @/lib/nfl/connected-leagues —
// shared with the AI advisor, which reads the same key to attach league
// context to chat requests.

// ---------------------------------------------------------------------------
// Shared helpers — position badge, slot labels, points formatting
// ---------------------------------------------------------------------------

function PosBadge({ pos }: { pos: string | null }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${getPositionBadgeClass(pos ?? '')}`}
    >
      {pos ?? '?'}
    </span>
  );
}

function slotLabel(slot: string): string {
  if (slot === 'SFLEX' || slot === 'SUPER_FLEX') return 'SF';
  if (slot === 'FLEX') return 'FX';
  return slot;
}

function fmtPts(v: number | null | undefined): string {
  return v != null ? v.toFixed(1) : '—';
}

function fmtWeekPts(v: number | null): string {
  return v === null ? '—' : v.toFixed(1);
}

/** Shared identity cell (position badge + name + team) for every player table. */
function playerCell(name: string | null, position: string | null, team?: string | null, extra?: ReactNode) {
  return (
    <div className='flex min-w-0 items-center gap-2.5'>
      <PosBadge pos={position} />
      <div className='min-w-0'>
        <p className='truncate text-sm font-medium'>{name ?? '—'}</p>
        {team && (
          <p className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground'>
            {team}
          </p>
        )}
      </div>
      {extra}
    </div>
  );
}

/** Section label — condensed caps, matches rankings/draft table headers. */
function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h3
      className={`${WC_HEADING} mb-2 text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground`}
    >
      {children}
    </h3>
  );
}

/** Loading placeholder for a header row + player table — shared by League
 *  Home and My Week so the "shared loading state" never renders a bare
 *  spinner. */
function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className='space-y-3'>
      <Skeleton className='h-9 w-64 rounded-full' />
      <div className='overflow-hidden rounded-[var(--radius-lg)] border divide-y'>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className='flex items-center justify-between px-4 py-2.5'>
            <div className='flex items-center gap-2.5'>
              <Skeleton className='h-5 w-8 rounded-full' />
              <Skeleton className='h-4 w-32' />
            </div>
            <Skeleton className='h-4 w-10' />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Connect wizard state machine
// ---------------------------------------------------------------------------

type ConnectStep =
  | { kind: 'idle' }
  | { kind: 'entering_username' }
  | { kind: 'pick_league'; user: SleeperUser; leagues: SleeperLeague[] }
  | { kind: 'pick_roster'; user: SleeperUser; league: SleeperLeague; leagues: SleeperLeague[] };

// ---------------------------------------------------------------------------
// Root component
// ---------------------------------------------------------------------------

export function SleeperLeagueView() {
  const [connected, setConnected] = useState<ConnectedLeague[]>([]);
  const [activeLeagueId, setActiveLeagueId] = useState<string | null>(null);
  const [step, setStep] = useState<ConnectStep>({ kind: 'idle' });
  const [username, setUsername] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // H-4: overview prefetched on entering the confirm step so the user sees
  // their team identity (team name, roster size, scoring) BEFORE committing.
  const [preview, setPreview] = useState<LeagueOverviewResponse | null>(null);
  const { setContent } = useInfobar();

  // Hydrate from localStorage once on mount
  useEffect(() => {
    const stored = loadConnected();
    setConnected(stored);
    if (stored.length > 0) setActiveLeagueId(stored[0].league_id);
  }, []);

  // Set custom sidebar content for leagues page
  useEffect(() => {
    const leaguesFaqContent: InfobarContent = {
      title: 'League Sync FAQ',
      sections: [
        {
          title: 'What is re-scoring?',
          description:
            "Projections are recomputed under your league's exact scoring settings, factoring in custom point values for PPR, pass TD, position multipliers, and more."
        },
        {
          title: "Why don't I see my roster?",
          description:
            "Make sure you're using your Sleeper username (not display name). Pre-draft leagues show the draft board; once rosters are set, your players will appear here."
        },
        {
          title: 'Is my data stored?',
          description:
            'Your connected leagues are stored locally in your browser only — no account or cloud storage required. Disconnect anytime without losing access.'
        }
      ]
    };
    setContent(leaguesFaqContent);
  }, [setContent]);

  const handleConnect = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!username.trim()) return;
      setLoading(true);
      setError(null);
      try {
        const resp = await sleeperLogin(username.trim());
        const { user, leagues } = resp;
        if (leagues.length === 0) {
          setError(`No NFL leagues found for '${username}' this season.`);
          return;
        }
        setStep({ kind: 'pick_league', user, leagues });
      } catch (err: unknown) {
        // Raw backend errors carry HTTP plumbing ("Sleeper login failed: 404")
        // — a missing username gets human copy, everything else a generic one.
        const msg = err instanceof Error ? err.message : String(err);
        setError(
          msg.includes('404')
            ? `That Sleeper username wasn't found. Check the spelling and try again.`
            : `Couldn't reach Sleeper right now — try again in a moment.`
        );
      } finally {
        setLoading(false);
      }
    },
    [username]
  );

  const handlePickLeague = useCallback(
    (user: SleeperUser, league: SleeperLeague, leagues: SleeperLeague[]) => {
      if (connected.length >= MAX_LEAGUES) {
        setError(`You can connect up to ${MAX_LEAGUES} leagues. Remove one before adding another.`);
        return;
      }
      setStep({ kind: 'pick_roster', user, league, leagues });
    },
    [connected.length]
  );

  // Prefetch the league overview when the confirm step opens; the fetch is
  // reused on confirm so previewing costs no extra round-trip.
  useEffect(() => {
    if (step.kind !== 'pick_roster') {
      setPreview(null);
      return;
    }
    let cancelled = false;
    fetchLeagueOverview(step.league.league_id, step.user.user_id)
      .then((overview) => {
        if (!cancelled) setPreview(overview);
      })
      .catch(() => {
        // Preview is best-effort — confirm still fetches and surfaces errors.
      });
    return () => {
      cancelled = true;
    };
  }, [step]);

  const handleConfirmRoster = useCallback(
    async (user: SleeperUser, league: SleeperLeague) => {
      setLoading(true);
      setError(null);
      try {
        const overview =
          preview && preview.league_id === league.league_id
            ? preview
            : await fetchLeagueOverview(league.league_id, user.user_id);
        const entry: ConnectedLeague = {
          league_id: league.league_id,
          league_name: league.name,
          season: league.season,
          user_id: user.user_id,
          username: user.username,
          roster_positions: overview.roster_positions,
          scoring_format_label: overview.scoring_format_label,
          connected_at: new Date().toISOString()
        };
        const updated = upsertConnected(entry);
        saveConnected(updated);
        setConnected(updated);
        setActiveLeagueId(league.league_id);
        setStep({ kind: 'idle' });
        setUsername('');
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(`Failed to load league: ${msg}`);
      } finally {
        setLoading(false);
      }
    },
    [preview]
  );

  const handleDisconnect = useCallback(
    (leagueId: string) => {
      const updated = removeConnected(leagueId);
      setConnected(updated);
      if (activeLeagueId === leagueId) {
        setActiveLeagueId(updated.length > 0 ? updated[0].league_id : null);
      }
    },
    [activeLeagueId]
  );

  // ----- wizard: pick league -----
  if (step.kind === 'pick_league') {
    return (
      <div className='space-y-4'>
        <BroadcastPanel className='space-y-2 p-4'>
          <div className='flex items-center justify-between'>
            <span className={WC_KICKER}>Step 2 of 3</span>
          </div>
          <p className='text-sm font-medium'>
            Connected as{' '}
            <span className='font-bold'>{step.user.display_name ?? step.user.username}</span>
          </p>
          <p className='text-xs text-muted-foreground'>Pick a league to sync (max {MAX_LEAGUES})</p>
        </BroadcastPanel>
        <div className='space-y-2'>
          {step.leagues.map((league) => {
            const alreadyConnected = connected.some((c) => c.league_id === league.league_id);
            return (
              <Button
                key={league.league_id}
                type='button'
                variant='outline'
                disabled={alreadyConnected}
                onClick={() => handlePickLeague(step.user, league, step.leagues)}
                className={`h-auto w-full flex-col items-stretch gap-1 whitespace-normal p-4 text-left ${WC_OUTLINE_BUTTON}`}
              >
                <span className='flex items-center justify-between gap-2'>
                  <span className='wc-display text-sm tracking-[0.02em]'>{league.name}</span>
                  {alreadyConnected && (
                    <span className='text-xs text-muted-foreground'>Already connected</span>
                  )}
                </span>
                <span className='text-xs text-muted-foreground'>
                  {league.total_rosters} teams · Season {league.season}
                </span>
              </Button>
            );
          })}
        </div>
        <Button
          type='button'
          variant='ghost'
          size='sm'
          className={WC_GHOST_BUTTON}
          onClick={() => {
            setStep({ kind: 'idle' });
            setError(null);
          }}
        >
          Cancel
        </Button>
        {error && <p className={`text-sm ${DANGER_TEXT}`}>{error}</p>}
      </div>
    );
  }

  // ----- wizard: confirm roster -----
  if (step.kind === 'pick_roster') {
    return (
      <div className='space-y-4'>
        <BroadcastPanel className='space-y-2 p-4'>
          <div className='flex items-center justify-between'>
            <span className={WC_KICKER}>Step 3 of 3</span>
          </div>
          <p className='text-sm font-medium'>
            Connecting as{' '}
            <span className='font-bold'>{step.user.display_name ?? step.user.username}</span>
          </p>
          <p className='text-sm text-muted-foreground'>
            Joining <span className='font-medium'>{step.league.name}</span> — one of{' '}
            <span className='font-medium'>{step.league.total_rosters}</span> teams
          </p>
          {preview ? (
            <p className='text-sm'>
              Your team:{' '}
              <span className='font-medium'>
                {preview.team_name ?? `Team ${step.user.display_name ?? step.user.username}`}
              </span>
              {preview.user_roster.length > 0 && (
                <span className='text-muted-foreground'> · {preview.user_roster.length} players rostered</span>
              )}
              <span className='text-muted-foreground'> · {preview.scoring_format_label}</span>
            </p>
          ) : (
            <Skeleton className='h-4 w-56' />
          )}
          <p className='text-xs text-muted-foreground'>
            We'll fetch your roster and re-score it under the league's custom settings.
          </p>
        </BroadcastPanel>
        <div className='flex gap-2'>
          <Button
            type='button'
            variant='outline'
            disabled={loading}
            onClick={() => handleConfirmRoster(step.user, step.league)}
            className={WC_CTA_BUTTON}
          >
            {loading ? 'Connecting…' : 'Confirm & Sync'}
          </Button>
          <Button
            type='button'
            variant='outline'
            className={WC_OUTLINE_BUTTON}
            onClick={() =>
              setStep({
                kind: 'pick_league',
                user: step.user,
                leagues: step.leagues
              })
            }
          >
            Back
          </Button>
        </div>
        {error && <p className={`text-sm ${DANGER_TEXT}`}>{error}</p>}
      </div>
    );
  }

  // ----- main view -----
  return (
    <div className='space-y-6'>
      {/* League tab switcher */}
      {connected.length > 0 && (
        <div className='space-y-2'>
          <div className='flex flex-wrap items-center gap-2'>
            {connected.map((l) => (
              <Button
                key={l.league_id}
                type='button'
                size='sm'
                variant='outline'
                onClick={() => setActiveLeagueId(l.league_id)}
                className={`min-h-[44px] ${activeLeagueId === l.league_id ? WC_CTA_BUTTON : WC_OUTLINE_BUTTON}`}
              >
                {l.league_name}
              </Button>
            ))}
            {connected.length < MAX_LEAGUES ? (
              <Button
                type='button'
                size='sm'
                variant='ghost'
                onClick={() => {
                  setStep({ kind: 'entering_username' });
                  setError(null);
                }}
                className={`min-h-[44px] border border-dashed ${WC_GHOST_BUTTON}`}
              >
                + Connect another
              </Button>
            ) : (
              <span className='flex items-center px-3 py-2 text-xs text-muted-foreground'>
                Remove a league to add another
              </span>
            )}
          </div>
          {connected.length >= 2 && (
            <p className='text-xs text-muted-foreground'>
              {connected.length} of {MAX_LEAGUES} league slots used
            </p>
          )}
        </div>
      )}

      {/* Connect form */}
      {(connected.length === 0 || step.kind === 'entering_username') && (
        <BroadcastPanel className='space-y-3 p-6'>
          {connected.length === 0 && (
            <>
              <div className='flex items-center justify-between'>
                <h3 className={`${WC_HEADING} text-lg`}>Connect your Sleeper league</h3>
                <span className={WC_KICKER}>Step 1 of 3</span>
              </div>
              <p className='text-sm text-muted-foreground'>
                Enter your Sleeper username to get roster advice under your league's exact scoring.
                Your leagues are saved locally — no account required.
              </p>
            </>
          )}
          {step.kind === 'entering_username' && connected.length > 0 && (
            <div className='flex items-center justify-between'>
              <h3 className={`${WC_HEADING} text-lg`}>Connect another league</h3>
              <span className={WC_KICKER}>Step 1 of 3</span>
            </div>
          )}
          <form onSubmit={handleConnect} className='flex gap-2'>
            <label htmlFor='sleeper-username' className='sr-only'>
              Sleeper username
            </label>
            <Input
              id='sleeper-username'
              type='text'
              placeholder='Sleeper username'
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={`flex-1 ${WC_INPUT}`}
              disabled={loading}
              autoComplete='username'
            />
            <Button
              type='submit'
              variant='outline'
              disabled={loading || !username.trim()}
              className={WC_CTA_BUTTON}
            >
              {loading ? 'Looking up…' : 'Connect'}
            </Button>
            {step.kind === 'entering_username' && (
              <Button
                type='button'
                variant='ghost'
                className={WC_GHOST_BUTTON}
                onClick={() => {
                  setStep({ kind: 'idle' });
                  setError(null);
                  setUsername('');
                }}
              >
                Cancel
              </Button>
            )}
          </form>
          {error && <p className={`text-sm ${DANGER_TEXT}`}>{error}</p>}
        </BroadcastPanel>
      )}

      {/* Active league home */}
      {activeLeague(connected, activeLeagueId) && step.kind === 'idle' && (
        <LeagueHome
          league={activeLeague(connected, activeLeagueId)!}
          onDisconnect={() => handleDisconnect(activeLeague(connected, activeLeagueId)!.league_id)}
        />
      )}
    </div>
  );
}

function activeLeague(connected: ConnectedLeague[], id: string | null): ConnectedLeague | null {
  return connected.find((l) => l.league_id === id) ?? null;
}

// ---------------------------------------------------------------------------
// League home: My Week / Roster Report / Waivers tabs
// ---------------------------------------------------------------------------

function LeagueHome({
  league,
  onDisconnect
}: {
  league: ConnectedLeague;
  onDisconnect: () => void;
}) {
  const [report, setReport] = useState<RosterReportResponse | null>(null);
  const [waivers, setWaivers] = useState<WaiversResponse | null>(null);
  const [prep, setPrep] = useState<LeagueDraftPrepResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'myweek' | 'report' | 'waivers'>('myweek');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const seasonYear = parseInt(league.season, 10) || new Date().getFullYear();

    Promise.all([
      fetchLeagueRosterReport(league.league_id, league.user_id, seasonYear),
      fetchLeagueWaivers(league.league_id, league.user_id, seasonYear),
      // Draft prep is best-effort: its absence must not take down the view.
      fetchLeagueDraftPrep(league.league_id, league.user_id, seasonYear).catch(() => null)
    ])
      .then(([r, w, p]) => {
        if (!cancelled) {
          setReport(r);
          setWaivers(w);
          setPrep(p);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : String(err);
          setError(`Failed to load league data: ${msg}`);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [league.league_id, league.user_id, league.season]);

  const isEmptyRoster = !report || report.roster_size === 0;
  const isMatchFailure =
    report !== null && report.roster_size === 0 && report.unmatched_player_ids.length > 0;
  // Draft prep keys off the league's DRAFT status, not roster emptiness —
  // dynasty rosters carry players year-round, so an empty roster can't be
  // the pre-draft signal. Empty-roster (redraft) leagues stay covered as a
  // fallback for when the drafts API returns nothing.
  const draftStatus = prep?.draft_info?.status ?? null;
  const showDraftPrep =
    draftStatus === 'pre_draft' || draftStatus === 'drafting' || (isEmptyRoster && !isMatchFailure);

  return (
    <div className='space-y-4'>
      {/* League header */}
      <BroadcastPanel className='flex items-start justify-between p-4'>
        <div className='space-y-1'>
          <h2 className={`${WC_HEADING} text-base`}>{league.league_name}</h2>
          <p className='text-xs text-muted-foreground'>
            {league.username} · Season {league.season}
          </p>
          <div className='mt-1 flex flex-wrap gap-1'>
            <span className='inline-flex items-center rounded-full border px-2 py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-medium text-muted-foreground'>
              {league.scoring_format_label}
            </span>
            {league.roster_positions
              .filter((p) => !['BN', 'IR', 'TAXI'].includes(p))
              .map((p, i) => (
                <span
                  key={i}
                  className='inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-mono text-muted-foreground'
                >
                  {p}
                </span>
              ))}
          </div>
        </div>
        <Button
          type='button'
          variant='outline'
          size='sm'
          onClick={onDisconnect}
          className={`min-h-[44px] ${WC_OUTLINE_BUTTON}`}
        >
          Disconnect
        </Button>
      </BroadcastPanel>

      {/* Tab bar — needs roster content (empty-roster leagues have nothing
          for either tab; DraftPrepView owns the whole panel then). Content
          renders below, gated the same way it always was — during loading
          `report` is still null so `isEmptyRoster` naturally hides this. */}
      {!isEmptyRoster && (
        <div className='sticky top-0 z-10 bg-background'>
          <Tabs value={tab} onValueChange={(v) => setTab(v as 'myweek' | 'report' | 'waivers')}>
            <TabsList className={WC_TABS_LIST}>
              <TabsTrigger value='myweek' className={WC_TAB_TRIGGER}>
                My Week
              </TabsTrigger>
              <TabsTrigger value='report' className={WC_TAB_TRIGGER}>
                Roster Report
              </TabsTrigger>
              <TabsTrigger value='waivers' className={WC_TAB_TRIGGER}>
                Waiver Targets
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      )}

      <DataLoadReveal loading={loading} skeleton={<TableSkeleton rows={8} />}>
        <div className='space-y-4'>
          {error && (
            <BroadcastPanel railColor='var(--danger)' className='p-4'>
              <p className={`text-sm ${DANGER_TEXT}`}>{error}</p>
            </BroadcastPanel>
          )}

          {/* Match-failure warning — roster exists but projections couldn't be matched */}
          {!error && isMatchFailure && report && (
            <BroadcastPanel railColor='var(--wc-yellow,#ffd84d)' className='space-y-2 p-6 text-center'>
              <p className={`text-sm font-medium ${WARN_TEXT}`}>Roster Found — Projections Pending</p>
              <p className='text-sm text-muted-foreground'>
                We found your roster but couldn&apos;t match {report.unmatched_player_ids.length}{' '}
                {report.unmatched_player_ids.length === 1 ? 'player' : 'players'} to projections — data
                may be refreshing, try again shortly.
              </p>
            </BroadcastPanel>
          )}

          {/* Draft-prep panel — league draft status is pre_draft/drafting
              (dynasty rosters stay populated, so roster emptiness can't gate this) */}
          {!error && showDraftPrep && prep && <DraftPrepView prep={prep} />}
          {!error && showDraftPrep && !prep && (
            <BroadcastPanel
              railColor='var(--wc-yellow,#ffd84d)'
              className='space-y-2 border-dashed p-6 text-center'
            >
              <p className='text-sm text-muted-foreground'>
                Pre-Draft Mode — draft board data is unavailable right now; check back shortly.
              </p>
            </BroadcastPanel>
          )}

          {/* My Week tab — weekly command center; owns its own fetch so the
              week selector can refetch without reloading the whole view */}
          {!error && !isEmptyRoster && tab === 'myweek' && (
            <MyWeekView league={league} onShowReport={() => setTab('report')} />
          )}

          {/* Roster report tab */}
          {!error && !isEmptyRoster && tab === 'report' && report && <RosterReportView report={report} />}

          {/* Waivers tab */}
          {!error && !isEmptyRoster && tab === 'waivers' && waivers && <WaiversView waivers={waivers} />}
        </div>
      </DataLoadReveal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// My Week view — weekly command center
// ---------------------------------------------------------------------------

function MyWeekStatusBadges({ p }: { p: MyWeekPlayer }) {
  return (
    <>
      {p.is_bye_week && (
        <span className='rounded bg-muted px-1.5 py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-bold text-muted-foreground'>
          BYE
        </span>
      )}
      {p.is_out && (
        <span
          className={`rounded border px-1.5 py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-bold ${DANGER_TEXT}`}
        >
          {p.injury_status?.toUpperCase() ?? 'OUT'}
        </span>
      )}
      {!p.is_out && p.injury_status && p.injury_status !== 'Active' && (
        <span
          className={`rounded border px-1.5 py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-bold ${WARN_TEXT}`}
        >
          {p.injury_status.toUpperCase()}
        </span>
      )}
    </>
  );
}

/** Shared column set for every MyWeekPlayer-shaped table (optimal lineup,
 *  bench, start/sit deltas, weekly waiver targets) — one definition instead
 *  of five near-identical row renderers. */
function buildMyWeekColumns<T extends MyWeekPlayer>(
  getSlot?: (row: T) => string | undefined,
  extra?: (row: T) => ReactNode
): BroadcastColumn<T>[] {
  const columns: BroadcastColumn<T>[] = [];
  if (getSlot) {
    columns.push({
      key: 'slot',
      header: '',
      width: 'w-10',
      cellClassName: 'font-mono text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-bold text-muted-foreground',
      accessor: (row) => {
        const slot = getSlot(row);
        return slot ? slotLabel(slot) : '';
      }
    });
  }
  columns.push({
    key: 'player',
    header: 'Player',
    sticky: true,
    accessor: (p) => playerCell(p.player_name, p.position, p.team, <MyWeekStatusBadges p={p} />)
  });
  columns.push({
    key: 'pts',
    header: 'Pts',
    align: 'right',
    accessor: (p) => (
      <div>
        <p className='text-sm font-semibold tabular-nums'>{fmtWeekPts(p.projected_points)}</p>
        {p.floor !== null && p.ceiling !== null && (
          <p className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground tabular-nums'>
            {p.floor.toFixed(1)}–{p.ceiling.toFixed(1)}
          </p>
        )}
      </div>
    )
  });
  if (extra) {
    columns.push({ key: 'extra', header: '', accessor: extra });
  }
  return columns;
}

function MyWeekView({
  league,
  onShowReport
}: {
  league: ConnectedLeague;
  onShowReport: () => void;
}) {
  const [data, setData] = useState<MyWeekResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // undefined = let the backend resolve the current week
  const [week, setWeek] = useState<number | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const seasonYear = parseInt(league.season, 10) || new Date().getFullYear();
    fetchLeagueMyWeek(league.league_id, league.user_id, seasonYear, week)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : String(err);
          setError(`Failed to load My Week: ${msg}`);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [league.league_id, league.user_id, league.season, week]);

  const askGx01 = () => window.dispatchEvent(new Event('gx01:toggle'));

  const changes = data?.changes;
  const isOptimal = !changes || changes.net_gain <= 0.05;

  return (
    <DataLoadReveal loading={loading} skeleton={<TableSkeleton rows={6} />}>
      {error ? (
        <BroadcastPanel railColor='var(--danger)' className='p-4'>
          <p className={`text-sm ${DANGER_TEXT}`}>{error}</p>
        </BroadcastPanel>
      ) : !data ? null : data.mode !== 'weekly' ? (
        // Preseason / no weekly data: explain, point at the season-long report.
        <BroadcastPanel railColor='var(--wc-yellow,#ffd84d)' className='space-y-3 p-6 text-center'>
          <p className='text-sm font-medium'>My Week starts with the season</p>
          <p className='text-sm text-muted-foreground'>
            {data.message ?? 'Weekly projections are not available yet for this week.'}
          </p>
          <Button
            type='button'
            variant='outline'
            size='sm'
            onClick={onShowReport}
            className={`min-h-[44px] ${WC_OUTLINE_BUTTON}`}
          >
            View season-long Roster Report
          </Button>
        </BroadcastPanel>
      ) : (
        <div className='space-y-5'>
          {/* Week header: selector + scoring context + GX-01 handoff */}
          <div className='flex flex-wrap items-center justify-between gap-2'>
            <div className='flex items-center gap-2'>
              <label htmlFor='myweek-week' className='text-xs font-semibold uppercase text-muted-foreground'>
                Week
              </label>
              <select
                id='myweek-week'
                value={week ?? data.week ?? ''}
                onChange={(e) => setWeek(e.target.value ? parseInt(e.target.value, 10) : undefined)}
                className={`rounded-md border px-2 py-1 text-sm ${WC_INPUT}`}
              >
                {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
              <span className='rounded-full bg-muted px-2 py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-medium text-muted-foreground'>
                {data.scoring_format_label || league.scoring_format_label}
              </span>
            </div>
            <Button
              type='button'
              variant='outline'
              size='sm'
              onClick={askGx01}
              className={`min-h-[44px] ${WC_OUTLINE_BUTTON}`}
            >
              Ask GX-01 about this week
            </Button>
          </div>

          {/* Start/Sit callout */}
          {isOptimal ? (
            <BroadcastPanel className='flex flex-wrap items-center gap-4 p-4'>
              <StatPill
                label='Projected'
                value={changes ? changes.optimal_points.toFixed(1) : '—'}
                sublabel={`Week ${data.week}`}
                hoverLift={false}
                numeralSize='clamp(22px, 3vw, 30px)'
                className='w-40'
              />
              <p className={`text-sm ${SUCCESS_TEXT}`}>Your lineup is optimal for week {data.week}.</p>
            </BroadcastPanel>
          ) : changes ? (
            <BroadcastPanel railColor='var(--wc-yellow,#ffd84d)' className='space-y-3 p-4'>
              <div className='flex flex-wrap items-center justify-between gap-3'>
                <p className={`${WC_HEADING} text-sm`}>Start/Sit Changes</p>
                <StatPill
                  label='Net Gain'
                  value={`+${changes.net_gain.toFixed(1)}`}
                  railColor='var(--wc-yellow,#ffd84d)'
                  hoverLift={false}
                  numeralSize='clamp(20px, 2.6vw, 26px)'
                  className='w-32 py-2'
                />
              </div>
              <div className='grid gap-3 sm:grid-cols-2'>
                <div>
                  <p className='mb-1 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold uppercase text-muted-foreground'>
                    Start
                  </p>
                  <BroadcastTable
                    columns={buildMyWeekColumns<MyWeekSlot>((s) => s.slot)}
                    rows={changes.to_start}
                    getRowId={(p) => p.sleeper_player_id}
                    emptyMessage='No changes.'
                    minWidth='min-w-[280px]'
                  />
                </div>
                <div>
                  <p className='mb-1 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold uppercase text-muted-foreground'>
                    Bench
                  </p>
                  <BroadcastTable
                    columns={buildMyWeekColumns<MyWeekPlayer>()}
                    rows={changes.to_bench}
                    getRowId={(p) => p.sleeper_player_id}
                    emptyMessage='No changes.'
                    minWidth='min-w-[280px]'
                  />
                </div>
              </div>
              <p className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground'>
                Current lineup {changes.current_points.toFixed(1)} pts → optimal{' '}
                {changes.optimal_points.toFixed(1)} pts.
              </p>
            </BroadcastPanel>
          ) : null}

          {/* Optimal lineup */}
          <section>
            <SectionHeading>Optimal Lineup — Week {data.week}</SectionHeading>
            <BroadcastTable
              columns={buildMyWeekColumns<MyWeekSlot>((s) => s.slot)}
              rows={data.optimal_starters}
              getRowId={(p) => p.sleeper_player_id}
              emptyMessage='No rows available.'
            />
          </section>

          {/* Bench */}
          {data.bench.length > 0 && (
            <section>
              <SectionHeading>Bench ({data.bench.length})</SectionHeading>
              <BroadcastTable
                columns={buildMyWeekColumns<MyWeekPlayer>()}
                rows={data.bench}
                getRowId={(p) => p.sleeper_player_id}
                emptyMessage='No rows available.'
              />
            </section>
          )}

          {/* Weekly waiver targets */}
          {data.waiver_targets.length > 0 && (
            <section>
              <SectionHeading>Waiver Targets This Week</SectionHeading>
              <BroadcastTable
                columns={buildMyWeekColumns<MyWeekWaiverTarget>(undefined, (t) =>
                  t.upgrades_over ? (
                    <span className={`text-[length:var(--fs-micro)] leading-[var(--lh-micro)] ${SUCCESS_TEXT}`}>
                      Upgrades over {t.upgrades_over}
                      {t.upgrade_slot ? ` (${t.upgrade_slot})` : ''}
                    </span>
                  ) : null
                )}
                rows={data.waiver_targets}
                getRowId={(p) => p.sleeper_player_id}
                emptyMessage='No waiver targets available.'
              />
            </section>
          )}

          {data.unmatched_player_ids.length > 0 && (
            <p className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground'>
              {data.unmatched_player_ids.length}{' '}
              {data.unmatched_player_ids.length === 1 ? 'player' : 'players'} had no weekly projection
              and {data.unmatched_player_ids.length === 1 ? 'is' : 'are'} excluded.
            </p>
          )}
        </div>
      )}
    </DataLoadReveal>
  );
}

// ---------------------------------------------------------------------------
// Roster report view
// ---------------------------------------------------------------------------

const starterColumns: BroadcastColumn<StarterSlot>[] = [
  {
    key: 'slot',
    header: '',
    width: 'w-10',
    cellClassName: 'font-mono text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-bold text-muted-foreground',
    accessor: (s) => (slotLabel(s.slot) === (s.position ?? '') ? '' : slotLabel(s.slot))
  },
  {
    key: 'player',
    header: 'Player',
    sticky: true,
    accessor: (s) => playerCell(s.player_name, s.position, s.team)
  },
  {
    key: 'pts',
    header: 'Pts',
    align: 'right',
    cellClassName: `font-semibold tabular-nums ${SUCCESS_TEXT}`,
    accessor: (s) => fmtPts(s.projected_season_points)
  }
];

const benchColumns: BroadcastColumn<LeagueRosterPlayer>[] = [
  {
    key: 'player',
    header: 'Player',
    sticky: true,
    accessor: (p) => playerCell(p.player_name, p.position, p.team)
  },
  {
    key: 'pts',
    header: 'Pts',
    align: 'right',
    cellClassName: 'text-muted-foreground tabular-nums',
    accessor: (p) => fmtPts(p.projected_season_points)
  }
];

const dropColumns: BroadcastColumn<DropCandidate>[] = [
  {
    key: 'player',
    header: 'Player',
    sticky: true,
    accessor: (d) => playerCell(d.player_name, d.position ?? null)
  },
  {
    key: 'reason',
    header: 'Reason',
    cellClassName: DANGER_TEXT,
    accessor: (d) => d.reason
  },
  {
    key: 'value',
    header: 'Proj Pts',
    align: 'right',
    cellClassName: 'text-muted-foreground tabular-nums',
    accessor: (d) => Number(d.value).toFixed(1)
  }
];

function RosterReportView({ report }: { report: RosterReportResponse }) {
  return (
    <div className='space-y-5'>
      {/* Scoring context badge */}
      <div className='flex items-center gap-1.5 text-xs text-muted-foreground'>
        <span className='rounded-full bg-muted px-2 py-0.5 font-medium'>Re-scored under league settings</span>
        <span>·</span>
        <span>
          {report.roster_format} format · {report.roster_size} players
        </span>
      </div>

      {/* Optimal starters */}
      <section>
        <SectionHeading>Optimal Starters</SectionHeading>
        <BroadcastTable
          columns={starterColumns}
          rows={report.starters}
          getRowId={(s, i) => s.player_name ?? i}
          emptyMessage='No rows available.'
        />
      </section>

      {/* Bench */}
      {report.bench.length > 0 && (
        <section>
          <SectionHeading>Bench ({report.bench.length})</SectionHeading>
          <BroadcastTable
            columns={benchColumns}
            rows={report.bench}
            getRowId={(p) => p.sleeper_player_id}
            emptyMessage='No rows available.'
          />
        </section>
      )}

      {/* Drop candidates */}
      {report.drop_candidates.length > 0 && (
        <section>
          <SectionHeading>Drop Candidates</SectionHeading>
          <BroadcastTable
            columns={dropColumns}
            rows={report.drop_candidates}
            getRowId={(d, i) => d.player_name ?? i}
            emptyMessage='No rows available.'
            minWidth='min-w-[420px]'
          />
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Waivers view
// ---------------------------------------------------------------------------

const waiverColumns: BroadcastColumn<WaiverTarget>[] = [
  {
    key: 'player',
    header: 'Player',
    sticky: true,
    accessor: (t) => playerCell(t.player_name, t.position, t.team)
  },
  {
    key: 'pts',
    header: 'Pts',
    align: 'right',
    cellClassName: `font-semibold tabular-nums ${SUCCESS_TEXT}`,
    accessor: (t) => fmtPts(t.projected_season_points)
  },
  {
    key: 'note',
    header: '',
    accessor: (t) =>
      t.upgrades_over ? (
        <span className={`text-[length:var(--fs-micro)] leading-[var(--lh-micro)] ${WARN_TEXT}`}>
          upgrades over {t.upgrades_over}
        </span>
      ) : (
        <span className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground'>depth</span>
      )
  }
];

function WaiversView({ waivers }: { waivers: WaiversResponse }) {
  return (
    <div className='space-y-2'>
      <div className='text-xs text-muted-foreground'>
        Top {waivers.targets.length} available free agents ranked by league-scored season projection
      </div>
      <BroadcastTable
        columns={waiverColumns}
        rows={waivers.targets}
        getRowId={(t) => t.sleeper_player_id}
        emptyMessage='No waiver targets available. All projected players may already be rostered.'
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Draft-Prep view (pre-season / pre_draft league state)
// ---------------------------------------------------------------------------

const VALUE_DISPLAY_CAP = 99;

/**
 * Value badge shown next to a player's ADP rank in the best-available table.
 *
 * Positive value means our model projects the player higher than the market
 * does (adp_rank - projection_rank > 0). Green when value >= 10 (strong
 * undervaluation signal), yellow for 1-9, muted for neutral/negative.
 *
 * Rookie-capital picks can push |value| into the hundreds (draft-capital
 * projection ranks vs. a much later real-world ADP), which reads as a data
 * glitch rather than signal. The DISPLAYED magnitude is capped at 99
 * ("99+"/"-99+"); sort/comparison logic upstream keeps using the raw,
 * uncapped value.
 */
function ValueBadge({ value, isRookie }: { value: number | null; isRookie?: boolean }) {
  if (value == null) return null;
  const isCapped = Math.abs(value) > VALUE_DISPLAY_CAP;
  let cls: string;
  let label: string;
  if (value >= 10) {
    cls = `${SUCCESS_TEXT} font-semibold`;
    label = isCapped ? `${VALUE_DISPLAY_CAP}+` : `+${value}`;
  } else if (value > 0) {
    cls = `${WARN_TEXT}`;
    label = `+${value}`;
  } else if (value === 0) {
    cls = 'text-muted-foreground';
    label = '±0';
  } else {
    cls = 'text-muted-foreground';
    label = isCapped ? `-${VALUE_DISPLAY_CAP}+` : String(value);
  }
  const title = isRookie
    ? 'Rookie — ADP rank − our projection rank'
    : 'ADP rank − our projection rank';
  return (
    <span className={`text-[length:var(--fs-micro)] leading-[var(--lh-micro)] tabular-nums ${cls}`} title={title}>
      {label}
    </span>
  );
}

const keeperColumns: BroadcastColumn<KeeperCandidate>[] = [
  {
    key: 'player',
    header: 'Player',
    sticky: true,
    accessor: (k) =>
      playerCell(
        k.player_name,
        k.position,
        k.team,
        k.taxi_eligible ? (
          <span className='inline-flex items-center rounded border border-dashed px-1.5 py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-medium text-muted-foreground'>
            TAXI
          </span>
        ) : undefined
      )
  },
  {
    key: 'pts',
    header: 'Pts',
    align: 'right',
    cellClassName: `font-semibold tabular-nums ${SUCCESS_TEXT}`,
    accessor: (k) => fmtPts(k.projected_season_points)
  }
];

const bestAvailableColumns: BroadcastColumn<BestAvailablePlayer>[] = [
  {
    key: 'rank',
    header: '#',
    width: 'w-8',
    align: 'right',
    cellClassName: 'text-muted-foreground tabular-nums',
    accessor: (_p, i) => i + 1
  },
  {
    key: 'player',
    header: 'Player',
    sticky: true,
    accessor: (p) => playerCell(p.player_name, p.position, p.team)
  },
  {
    key: 'adp',
    header: 'ADP / Value',
    align: 'right',
    width: 'w-24',
    accessor: (p) =>
      p.adp_rank != null ? (
        <div>
          <p className='text-xs tabular-nums text-muted-foreground'>ADP {p.adp_rank}</p>
          <ValueBadge value={p.value} isRookie={p.years_exp === 0} />
        </div>
      ) : (
        <p className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground'>no ADP</p>
      )
  },
  {
    key: 'pts',
    header: 'Proj Pts',
    align: 'right',
    cellClassName: `font-semibold tabular-nums ${SUCCESS_TEXT}`,
    accessor: (p) => fmtPts(p.projected_season_points)
  }
];

/**
 * DraftPrepView — shown when the connected league is in pre-draft mode.
 *
 * Renders four sections: draft info header, keeper candidates table (when
 * the user has a pre-loaded roster), best-available table with ADP rank +
 * value badge (green = undervalued), and a rookies tab (subset sorted by
 * ADP — market rank beats our fallback projections).
 */
function DraftPrepView({ prep }: { prep: LeagueDraftPrepResponse }) {
  const [tab, setTab] = useState<'best_available' | 'rookies'>('best_available');

  const { draft_info, keeper_candidates, best_available, rookies, rookie_note } = prep;
  const activeList = tab === 'rookies' ? rookies : best_available;

  return (
    <div className='space-y-4'>
      {/* Draft info header */}
      {draft_info && (
        <BroadcastPanel className='space-y-3 p-4'>
          <div className='flex items-center justify-between'>
            <p className={`${WC_HEADING} text-sm`}>Draft</p>
            <span className='inline-flex items-center rounded-full border px-2 py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-medium capitalize text-muted-foreground'>
              {draft_info.status.replace('_', ' ')}
            </span>
          </div>
          <div className='flex flex-wrap items-center gap-3'>
            <span className='text-sm text-muted-foreground'>
              Type: <span className='font-medium text-foreground capitalize'>{draft_info.type}</span>
            </span>
            <StatPill
              label='Rounds'
              value={draft_info.rounds}
              hoverLift={false}
              numeralSize='clamp(18px, 2.2vw, 22px)'
              className='w-24 py-2'
            />
            {draft_info.user_slot != null ? (
              <StatPill
                label='Your Slot'
                value={`#${draft_info.user_slot}`}
                hoverLift={false}
                numeralSize='clamp(18px, 2.2vw, 22px)'
                className='w-24 py-2'
              />
            ) : (
              <span className='text-sm italic text-muted-foreground'>Draft order not set yet</span>
            )}
          </div>
        </BroadcastPanel>
      )}

      {/* Keeper candidates — only shown when the user has a roster */}
      {keeper_candidates.length > 0 && (
        <section>
          <SectionHeading>Your Roster — Keeper Candidates</SectionHeading>
          <BroadcastTable
            columns={keeperColumns}
            rows={keeper_candidates}
            getRowId={(k) => k.sleeper_player_id}
            emptyMessage='No keeper candidates.'
          />
        </section>
      )}

      {/* Best-available / Rookies tab bar */}
      <div className='space-y-2'>
        <div className='sticky top-0 z-10 bg-background'>
          <Tabs value={tab} onValueChange={(v) => setTab(v as 'best_available' | 'rookies')}>
            <TabsList className={WC_TABS_LIST}>
              <TabsTrigger value='best_available' className={WC_TAB_TRIGGER}>
                Best Available ({best_available.length})
              </TabsTrigger>
              <TabsTrigger value='rookies' className={WC_TAB_TRIGGER}>
                Rookies ({rookies.length})
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* Rookies tab note */}
        {tab === 'rookies' && rookie_note && (
          <p className='px-1 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] italic text-muted-foreground'>
            {rookie_note}
          </p>
        )}

        <BroadcastTable
          columns={bestAvailableColumns}
          rows={activeList}
          getRowId={(p, i) => p.sleeper_player_id || i}
          emptyMessage='No players found for this view.'
        />
      </div>
    </div>
  );
}
