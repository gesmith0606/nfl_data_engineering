'use client';

/**
 * League Sync — Plan-3 implementation.
 *
 * Connect flow: enter Sleeper username → GET leagues → pick one → confirm
 * roster → save up to 3 leagues in localStorage (key: nfl.connectedLeagues).
 *
 * League home: roster report card (optimal lineup + bench + drop candidates),
 * waiver targets table, and a scoring badge showing how the league's custom
 * settings differ from standard half-PPR.
 *
 * No auth / gating — open for all users. Plan 2 (Clerk/Stripe) deferred.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  fetchLeagueDraftPrep,
  fetchLeagueMyWeek,
  fetchLeagueOverview,
  fetchLeagueRosterReport,
  fetchLeagueWaivers,
  sleeperLogin,
} from '@/lib/nfl/api';
import {
  MAX_CONNECTED_LEAGUES as MAX_LEAGUES,
  loadConnectedLeagues as loadConnected,
  saveConnectedLeagues as saveConnected,
  upsertConnectedLeague as upsertConnected,
  removeConnectedLeague as removeConnected,
} from '@/lib/nfl/connected-leagues';
import { getPositionBadgeClass } from '@/lib/nfl/position-colors';
import { DANGER_TEXT, SUCCESS_TEXT, WARN_TEXT } from '@/lib/nfl/semantic-colors';
import { Icons } from '@/components/icons';
import { useInfobar, type InfobarContent } from '@/components/ui/infobar';
import type {
  BestAvailablePlayer,
  ConnectedLeague,
  LeagueDraftPrepResponse,
  LeagueOverviewResponse,
  MyWeekPlayer,
  MyWeekResponse,
  MyWeekSlot,
  RosterReportResponse,
  SleeperLeague,
  SleeperUser,
  WaiversResponse,
} from '@/lib/nfl/types';

// localStorage helpers (cap 3 leagues) live in @/lib/nfl/connected-leagues —
// shared with the AI advisor, which reads the same key to attach league
// context to chat requests.

// ---------------------------------------------------------------------------
// Position badge colours
// ---------------------------------------------------------------------------

function PosBadge({ pos }: { pos: string | null }) {
  return (
    <span
      className={`inline-flex items-center border px-1.5 py-0.5 text-[10px] font-bold ${getPositionBadgeClass(pos ?? '')}`}
    >
      {pos ?? '?'}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Slot label normalisation (SUPER_FLEX → SF, etc.)
// ---------------------------------------------------------------------------

function slotLabel(slot: string): string {
  if (slot === 'SFLEX' || slot === 'SUPER_FLEX') return 'SF';
  if (slot === 'FLEX') return 'FX';
  return slot;
}

// ---------------------------------------------------------------------------
// PlayerRowList component — shared markup for Starters, Bench, Waivers
// ---------------------------------------------------------------------------

interface PlayerRowListProps<T extends {
  position: string | null;
  player_name: string | null;
  team?: string | null;
  projected_season_points?: number | null;
}> {
  rows: T[];
  showSlot?: boolean;
  getSlot?: (row: T) => string | undefined;
  dimPoints?: boolean;
  extra?: (row: T, index: number) => React.ReactNode;
  compact?: boolean; // Use py-2 instead of py-2.5
}

function PlayerRowList<
  T extends {
    position: string | null;
    player_name: string | null;
    team?: string | null;
    projected_season_points?: number | null;
  },
>({
  rows,
  showSlot,
  getSlot,
  dimPoints,
  extra,
  compact,
}: PlayerRowListProps<T>) {
  if (rows.length === 0) {
    return (
      <p className='px-4 py-3 text-sm text-muted-foreground'>
        No rows available.
      </p>
    );
  }

  if (extra) {
    // Waiver targets layout with extra content
    return (
      <>
        {rows.map((row, i) => (
          <div
            key={i}
            className='flex items-center justify-between px-4 py-2.5 gap-3'
          >
            <div className='flex items-center gap-2.5 min-w-0'>
              {showSlot && getSlot?.(row) && (
                <span className='w-8 text-[10px] font-bold text-muted-foreground font-mono shrink-0'>
                  {slotLabel(getSlot(row)!) === (row.position ?? '')
                    ? ''
                    : slotLabel(getSlot(row)!)}
                </span>
              )}
              <PosBadge pos={row.position} />
              <div className='min-w-0'>
                <p className='text-sm font-medium truncate'>
                  {row.player_name ?? '—'}
                </p>
                {row.team && (
                  <p className='text-[10px] text-muted-foreground'>
                    {row.team}
                  </p>
                )}
              </div>
            </div>
            <div className='text-right shrink-0'>
              <p
                className={`text-sm font-semibold tabular-nums ${
                  dimPoints ? 'text-muted-foreground' : SUCCESS_TEXT
                }`}
              >
                {row.projected_season_points != null
                  ? row.projected_season_points.toFixed(1)
                  : '—'}
              </p>
              {extra(row, i)}
            </div>
          </div>
        ))}
      </>
    );
  }

  // Starters/Bench layout
  return (
    <>
      {rows.map((row, i) => (
        <div
          key={i}
          className={`flex items-center justify-between px-4 ${
            compact ? 'py-2' : 'py-2.5'
          }`}
        >
          <div className='flex items-center gap-2.5'>
            {showSlot && getSlot?.(row) && (
              <span className='w-8 text-[10px] font-bold text-muted-foreground font-mono'>
                {slotLabel(getSlot(row)!) === (row.position ?? '')
                  ? ''
                  : slotLabel(getSlot(row)!)}
              </span>
            )}
            <PosBadge pos={row.position} />
            <span className='text-sm font-medium'>
              {row.player_name ?? '—'}
            </span>
            {row.team && (
              <span className='text-xs text-muted-foreground'>{row.team}</span>
            )}
          </div>
          <span
            className={`text-sm tabular-nums ${
              dimPoints
                ? 'text-muted-foreground'
                : `font-semibold ${SUCCESS_TEXT}`
            }`}
          >
            {row.projected_season_points != null
              ? row.projected_season_points.toFixed(1)
              : '—'}
          </span>
        </div>
      ))}
    </>
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
          description: 'Projections are recomputed under your league\'s exact scoring settings, factoring in custom point values for PPR, pass TD, position multipliers, and more.',
        },
        {
          title: 'Why don\'t I see my roster?',
          description: 'Make sure you\'re using your Sleeper username (not display name). Pre-draft leagues show the draft board; once rosters are set, your players will appear here.',
        },
        {
          title: 'Is my data stored?',
          description: 'Your connected leagues are stored locally in your browser only — no account or cloud storage required. Disconnect anytime without losing access.',
        },
      ],
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
    [username],
  );

  const handlePickLeague = useCallback(
    (user: SleeperUser, league: SleeperLeague, leagues: SleeperLeague[]) => {
      if (connected.length >= MAX_LEAGUES) {
        setError(
          `You can connect up to ${MAX_LEAGUES} leagues. Remove one before adding another.`,
        );
        return;
      }
      setStep({ kind: 'pick_roster', user, league, leagues });
    },
    [connected.length],
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
          connected_at: new Date().toISOString(),
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
    [preview],
  );

  const handleDisconnect = useCallback(
    (leagueId: string) => {
      const updated = removeConnected(leagueId);
      setConnected(updated);
      if (activeLeagueId === leagueId) {
        setActiveLeagueId(updated.length > 0 ? updated[0].league_id : null);
      }
    },
    [activeLeagueId],
  );

  // ----- wizard: pick league -----
  if (step.kind === 'pick_league') {
    return (
      <div className='space-y-4'>
        <div className='rounded-lg border bg-muted/30 p-4'>
          <div className='flex items-center justify-between mb-2'>
            <span className='text-xs font-medium text-muted-foreground'>Step 2 of 3</span>
          </div>
          <p className='text-sm font-medium'>
            Connected as{' '}
            <span className='font-bold'>
              {step.user.display_name ?? step.user.username}
            </span>
          </p>
          <p className='text-xs text-muted-foreground mt-0.5'>
            Pick a league to sync (max {MAX_LEAGUES})
          </p>
        </div>
        <div className='space-y-2'>
          {step.leagues.map((league) => {
            const alreadyConnected = connected.some(
              (c) => c.league_id === league.league_id,
            );
            return (
              <button
                key={league.league_id}
                type='button'
                disabled={alreadyConnected}
                onClick={() => handlePickLeague(step.user, league, step.leagues)}
                className='w-full rounded-lg border p-4 text-left hover:bg-muted/50 disabled:opacity-50 disabled:cursor-not-allowed'
              >
                <div className='flex items-center justify-between'>
                  <span className='font-medium text-sm'>{league.name}</span>
                  {alreadyConnected && (
                    <span className='text-xs text-muted-foreground'>
                      Already connected
                    </span>
                  )}
                </div>
                <p className='text-xs text-muted-foreground mt-0.5'>
                  {league.total_rosters} teams · Season {league.season}
                </p>
              </button>
            );
          })}
        </div>
        <button
          type='button'
          onClick={() => {
            setStep({ kind: 'idle' });
            setError(null);
          }}
          className='rounded-md border px-3 py-1.5 text-sm hover:bg-muted'
        >
          Cancel
        </button>
        {error && <p className={`text-sm ${DANGER_TEXT}`}>{error}</p>}
      </div>
    );
  }

  // ----- wizard: confirm roster -----
  if (step.kind === 'pick_roster') {
    return (
      <div className='space-y-4'>
        <div className='rounded-lg border bg-muted/30 p-4'>
          <div className='flex items-center justify-between mb-2'>
            <span className='text-xs font-medium text-muted-foreground'>Step 3 of 3</span>
          </div>
          <p className='text-sm font-medium'>
            Connecting as{' '}
            <span className='font-bold'>
              {step.user.display_name ?? step.user.username}
            </span>
          </p>
          <p className='text-sm text-muted-foreground mt-1'>
            Joining <span className='font-medium'>{step.league.name}</span> — one of{' '}
            <span className='font-medium'>{step.league.total_rosters}</span> teams
          </p>
          {preview ? (
            <p className='text-sm mt-2'>
              Your team:{' '}
              <span className='font-medium'>
                {preview.team_name ??
                  `Team ${step.user.display_name ?? step.user.username}`}
              </span>
              {preview.user_roster.length > 0 && (
                <span className='text-muted-foreground'>
                  {' '}· {preview.user_roster.length} players rostered
                </span>
              )}
              <span className='text-muted-foreground'>
                {' '}· {preview.scoring_format_label}
              </span>
            </p>
          ) : (
            <p className='text-xs text-muted-foreground mt-2 flex items-center gap-1.5'>
              <Icons.spinner className='h-3 w-3 animate-spin' />
              Looking up your team…
            </p>
          )}
          <p className='text-xs text-muted-foreground mt-2'>
            We'll fetch your roster and re-score it under the league's custom
            settings.
          </p>
        </div>
        <div className='flex gap-2'>
          <button
            type='button'
            disabled={loading}
            onClick={() => handleConfirmRoster(step.user, step.league)}
            className='rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50'
          >
            {loading ? 'Connecting…' : 'Confirm & Sync'}
          </button>
          <button
            type='button'
            onClick={() =>
              setStep({
                kind: 'pick_league',
                user: step.user,
                leagues: step.leagues,
              })
            }
            className='rounded-md border px-3 py-2 text-sm hover:bg-muted'
          >
            Back
          </button>
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
          <div className='flex items-center gap-2 flex-wrap'>
            {connected.map((l) => (
              <button
                key={l.league_id}
                type='button'
                onClick={() => setActiveLeagueId(l.league_id)}
                className={`rounded-md border px-3 py-1.5 text-sm min-h-[44px] flex items-center justify-center ${
                  activeLeagueId === l.league_id
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted'
                }`}
              >
                {l.league_name}
              </button>
            ))}
            {connected.length < MAX_LEAGUES ? (
              <button
                type='button'
                onClick={() => {
                  setStep({ kind: 'entering_username' });
                  setError(null);
                }}
                className='rounded-md border border-dashed px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted min-h-[44px] flex items-center justify-center'
              >
                + Connect another
              </button>
            ) : (
              <span className='text-xs text-muted-foreground px-3 py-2 flex items-center'>
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
        <div className='rounded-lg border p-6 space-y-3'>
          {connected.length === 0 && (
            <>
              <div className='flex items-center justify-between'>
                <h3 className='text-lg font-semibold'>
                  Connect your Sleeper league
                </h3>
                <span className='text-xs font-medium text-muted-foreground'>Step 1 of 3</span>
              </div>
              <p className='text-sm text-muted-foreground'>
                Enter your Sleeper username to get roster advice under your
                league's exact scoring. Your leagues are saved locally — no
                account required.
              </p>
            </>
          )}
          {step.kind === 'entering_username' && connected.length > 0 && (
            <div className='flex items-center justify-between'>
              <h3 className='text-lg font-semibold'>
                Connect another league
              </h3>
              <span className='text-xs font-medium text-muted-foreground'>Step 1 of 3</span>
            </div>
          )}
          <form onSubmit={handleConnect} className='flex gap-2'>
            <label htmlFor='sleeper-username' className='sr-only'>
              Sleeper username
            </label>
            <input
              id='sleeper-username'
              type='text'
              placeholder='Sleeper username'
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className='flex-1 rounded-md border bg-background px-3 py-2 text-sm'
              disabled={loading}
              autoComplete='username'
            />
            <button
              type='submit'
              disabled={loading || !username.trim()}
              className='rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50 flex items-center gap-2'
            >
              {loading && <Icons.spinner className='h-4 w-4 animate-spin' />}
              {loading ? 'Looking up…' : 'Connect'}
            </button>
            {step.kind === 'entering_username' && (
              <button
                type='button'
                onClick={() => {
                  setStep({ kind: 'idle' });
                  setError(null);
                  setUsername('');
                }}
                className='rounded-md border px-3 py-2 text-sm hover:bg-muted'
              >
                Cancel
              </button>
            )}
          </form>
          {error && <p className={`text-sm ${DANGER_TEXT}`}>{error}</p>}
        </div>
      )}

      {/* Active league home */}
      {activeLeague(connected, activeLeagueId) && step.kind === 'idle' && (
        <LeagueHome
          league={activeLeague(connected, activeLeagueId)!}
          onDisconnect={() =>
            handleDisconnect(activeLeague(connected, activeLeagueId)!.league_id)
          }
        />
      )}
    </div>
  );
}

function activeLeague(
  connected: ConnectedLeague[],
  id: string | null,
): ConnectedLeague | null {
  return connected.find((l) => l.league_id === id) ?? null;
}

// ---------------------------------------------------------------------------
// League home: roster report + waivers tabs
// ---------------------------------------------------------------------------

function LeagueHome({
  league,
  onDisconnect,
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

    const seasonYear =
      parseInt(league.season, 10) || new Date().getFullYear();

    Promise.all([
      fetchLeagueRosterReport(league.league_id, league.user_id, seasonYear),
      fetchLeagueWaivers(league.league_id, league.user_id, seasonYear),
      // Draft prep is best-effort: its absence must not take down the view.
      fetchLeagueDraftPrep(league.league_id, league.user_id, seasonYear).catch(
        () => null
      ),
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
    report !== null &&
    report.roster_size === 0 &&
    report.unmatched_player_ids.length > 0;
  // Draft prep keys off the league's DRAFT status, not roster emptiness —
  // dynasty rosters carry players year-round, so an empty roster can't be
  // the pre-draft signal. Empty-roster (redraft) leagues stay covered as a
  // fallback for when the drafts API returns nothing.
  const draftStatus = prep?.draft_info?.status ?? null;
  const showDraftPrep =
    draftStatus === 'pre_draft' ||
    draftStatus === 'drafting' ||
    (isEmptyRoster && !isMatchFailure);

  return (
    <div className='space-y-4'>
      {/* League header */}
      <div className='flex items-start justify-between rounded-lg border p-4'>
        <div className='space-y-1'>
          <h2 className='font-semibold'>{league.league_name}</h2>
          <p className='text-xs text-muted-foreground'>
            {league.username} · Season {league.season}
          </p>
          <div className='flex flex-wrap gap-1 mt-1'>
            <span className='inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium text-muted-foreground'>
              {league.scoring_format_label}
            </span>
            {league.roster_positions
              .filter((p) => !['BN', 'IR', 'TAXI'].includes(p))
              .map((p, i) => (
                <span
                  key={i}
                  className='inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground'
                >
                  {p}
                </span>
              ))}
          </div>
        </div>
        <button
          type='button'
          onClick={onDisconnect}
          className='min-h-[44px] rounded-md border px-3 py-1 text-xs text-muted-foreground hover:bg-muted'
        >
          Disconnect
        </button>
      </div>

      {/* Tab bar — needs roster content (empty-roster leagues have nothing
          for either tab; DraftPrepView owns the whole panel then) */}
      {!isEmptyRoster && (
        <div className='sticky top-0 z-10 bg-background flex gap-1 border-b'>
          {(['myweek', 'report', 'waivers'] as const).map((t) => (
            <button
              key={t}
              type='button'
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-sm -mb-px border-b-2 ${
                tab === t
                  ? 'border-primary font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t === 'myweek'
                ? 'My Week'
                : t === 'report'
                  ? 'Roster Report'
                  : 'Waiver Targets'}
            </button>
          ))}
        </div>
      )}

      {/* Loading / error states */}
      {loading && (
        <div className='py-8 text-center text-sm text-muted-foreground'>
          Loading league data…
        </div>
      )}
      {!loading && error && (
        <div className={`rounded-md border p-4 text-sm ${DANGER_TEXT}`}>
          {error}
        </div>
      )}

      {/* Match-failure warning — roster exists but projections couldn't be matched */}
      {!loading && !error && isMatchFailure && report && (
        <div className='rounded-lg border p-6 text-center space-y-2'>
          <p className={`font-medium text-sm ${WARN_TEXT}`}>
            Roster Found — Projections Pending
          </p>
          <p className='text-sm text-muted-foreground'>
            We found your roster but couldn&apos;t match{' '}
            {report.unmatched_player_ids.length}{' '}
            {report.unmatched_player_ids.length === 1 ? 'player' : 'players'} to
            projections — data may be refreshing, try again shortly.
          </p>
        </div>
      )}

      {/* Draft-prep panel — league draft status is pre_draft/drafting
          (dynasty rosters stay populated, so roster emptiness can't gate this) */}
      {!loading && !error && showDraftPrep && prep && (
        <DraftPrepView prep={prep} />
      )}
      {!loading && !error && showDraftPrep && !prep && (
        <div className='rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground'>
          Pre-Draft Mode — draft board data is unavailable right now; check
          back shortly.
        </div>
      )}

      {/* My Week tab — weekly command center; owns its own fetch so the
          week selector can refetch without reloading the whole view */}
      {!loading && !error && !isEmptyRoster && tab === 'myweek' && (
        <MyWeekView league={league} onShowReport={() => setTab('report')} />
      )}

      {/* Roster report tab */}
      {!loading && !error && !isEmptyRoster && tab === 'report' && report && (
        <RosterReportView report={report} />
      )}

      {/* Waivers tab */}
      {!loading && !error && !isEmptyRoster && tab === 'waivers' && waivers && (
        <WaiversView waivers={waivers} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// My Week view — weekly command center
// ---------------------------------------------------------------------------

function fmtWeekPts(v: number | null): string {
  return v === null ? '—' : v.toFixed(1);
}

function MyWeekStatusBadges({ p }: { p: MyWeekPlayer }) {
  return (
    <>
      {p.is_bye_week && (
        <span className='rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground'>
          BYE
        </span>
      )}
      {p.is_out && (
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${DANGER_TEXT}`}>
          {p.injury_status?.toUpperCase() ?? 'OUT'}
        </span>
      )}
      {!p.is_out && p.injury_status && p.injury_status !== 'Active' && (
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${WARN_TEXT}`}>
          {p.injury_status.toUpperCase()}
        </span>
      )}
    </>
  );
}

function MyWeekRow({
  p,
  slot,
}: {
  p: MyWeekPlayer;
  slot?: string;
}) {
  return (
    <div className='flex items-center justify-between px-4 py-2.5 gap-3'>
      <div className='flex items-center gap-2.5 min-w-0'>
        {slot && (
          <span className='w-10 text-[10px] font-bold text-muted-foreground font-mono shrink-0'>
            {slot}
          </span>
        )}
        <PosBadge pos={p.position} />
        <div className='min-w-0'>
          <div className='flex items-center gap-1.5'>
            <p className='text-sm font-medium truncate'>
              {p.player_name ?? '—'}
            </p>
            <MyWeekStatusBadges p={p} />
          </div>
          {p.team && (
            <p className='text-[11px] text-muted-foreground'>{p.team}</p>
          )}
        </div>
      </div>
      <div className='text-right shrink-0'>
        <p className='text-sm font-semibold tabular-nums'>
          {fmtWeekPts(p.projected_points)}
        </p>
        {p.floor !== null && p.ceiling !== null && (
          <p className='text-[10px] text-muted-foreground tabular-nums'>
            {p.floor.toFixed(1)}–{p.ceiling.toFixed(1)}
          </p>
        )}
      </div>
    </div>
  );
}

function MyWeekView({
  league,
  onShowReport,
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
    const seasonYear =
      parseInt(league.season, 10) || new Date().getFullYear();
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

  if (loading) {
    return (
      <div className='py-8 text-center text-sm text-muted-foreground'>
        Loading your week…
      </div>
    );
  }
  if (error) {
    return (
      <div className={`rounded-md border p-4 text-sm ${DANGER_TEXT}`}>
        {error}
      </div>
    );
  }
  if (!data) return null;

  // Preseason / no weekly data: explain, point at the season-long report.
  if (data.mode !== 'weekly') {
    return (
      <div className='rounded-lg border border-dashed p-6 text-center space-y-3'>
        <p className='text-sm font-medium'>My Week starts with the season</p>
        <p className='text-sm text-muted-foreground'>
          {data.message ??
            'Weekly projections are not available yet for this week.'}
        </p>
        <button
          type='button'
          onClick={onShowReport}
          className='min-h-[44px] rounded-md border px-3 py-1 text-xs hover:bg-muted'
        >
          View season-long Roster Report
        </button>
      </div>
    );
  }

  const changes = data.changes;
  const isOptimal = !changes || changes.net_gain <= 0.05;

  return (
    <div className='space-y-5'>
      {/* Week header: selector + scoring context + GX-01 handoff */}
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div className='flex items-center gap-2'>
          <label
            htmlFor='myweek-week'
            className='text-xs font-semibold uppercase text-muted-foreground'
          >
            Week
          </label>
          <select
            id='myweek-week'
            value={week ?? data.week ?? ''}
            onChange={(e) =>
              setWeek(e.target.value ? parseInt(e.target.value, 10) : undefined)
            }
            className='rounded-md border bg-background px-2 py-1 text-sm'
          >
            {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
          <span className='rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground'>
            {data.scoring_format_label || league.scoring_format_label}
          </span>
        </div>
        <button
          type='button'
          onClick={askGx01}
          className='min-h-[44px] rounded-md border px-3 py-1 text-xs font-medium hover:bg-muted'
        >
          Ask GX-01 about this week
        </button>
      </div>

      {/* Start/Sit callout */}
      {isOptimal ? (
        <div className={`rounded-lg border p-4 text-sm ${SUCCESS_TEXT}`}>
          Your lineup is optimal for week {data.week} — projected{' '}
          {changes ? changes.optimal_points.toFixed(1) : '—'} pts.
        </div>
      ) : (
        <div className='rounded-lg border p-4 space-y-2'>
          <div className='flex items-center justify-between'>
            <p className='text-sm font-semibold'>Start/Sit changes</p>
            <span className={`text-sm font-bold tabular-nums ${SUCCESS_TEXT}`}>
              +{changes.net_gain.toFixed(1)} pts
            </span>
          </div>
          <div className='grid gap-3 sm:grid-cols-2'>
            <div>
              <p className='text-[10px] font-semibold uppercase text-muted-foreground mb-1'>
                Start
              </p>
              <div className='rounded-md border divide-y'>
                {changes.to_start.map((p, i) => (
                  <MyWeekRow key={i} p={p} slot={p.slot} />
                ))}
              </div>
            </div>
            <div>
              <p className='text-[10px] font-semibold uppercase text-muted-foreground mb-1'>
                Bench
              </p>
              <div className='rounded-md border divide-y'>
                {changes.to_bench.map((p, i) => (
                  <MyWeekRow key={i} p={p} />
                ))}
              </div>
            </div>
          </div>
          <p className='text-[11px] text-muted-foreground'>
            Current lineup {changes.current_points.toFixed(1)} pts → optimal{' '}
            {changes.optimal_points.toFixed(1)} pts.
          </p>
        </div>
      )}

      {/* Optimal lineup */}
      <section>
        <h3 className='text-xs font-semibold uppercase text-muted-foreground mb-2'>
          Optimal Lineup — Week {data.week}
        </h3>
        <div className='rounded-lg border divide-y'>
          {data.optimal_starters.length === 0 ? (
            <p className='px-4 py-3 text-sm text-muted-foreground'>
              No rows available.
            </p>
          ) : (
            data.optimal_starters.map((s: MyWeekSlot, i: number) => (
              <MyWeekRow key={i} p={s} slot={s.slot} />
            ))
          )}
        </div>
      </section>

      {/* Bench */}
      {data.bench.length > 0 && (
        <section>
          <h3 className='text-xs font-semibold uppercase text-muted-foreground mb-2'>
            Bench ({data.bench.length})
          </h3>
          <div className='rounded-lg border divide-y'>
            {data.bench.map((p, i) => (
              <MyWeekRow key={i} p={p} />
            ))}
          </div>
        </section>
      )}

      {/* Weekly waiver targets */}
      {data.waiver_targets.length > 0 && (
        <section>
          <h3 className='text-xs font-semibold uppercase text-muted-foreground mb-2'>
            Waiver Targets This Week
          </h3>
          <div className='rounded-lg border divide-y'>
            {data.waiver_targets.map((t, i) => (
              <div key={i}>
                <MyWeekRow p={t} />
                {t.upgrades_over && (
                  <p className={`px-4 pb-2 -mt-1 text-[11px] ${SUCCESS_TEXT}`}>
                    Upgrades over {t.upgrades_over}
                    {t.upgrade_slot ? ` (${t.upgrade_slot})` : ''}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {data.unmatched_player_ids.length > 0 && (
        <p className='text-[11px] text-muted-foreground'>
          {data.unmatched_player_ids.length}{' '}
          {data.unmatched_player_ids.length === 1 ? 'player' : 'players'} had no
          weekly projection and {data.unmatched_player_ids.length === 1 ? 'is' : 'are'}{' '}
          excluded.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Roster report view
// ---------------------------------------------------------------------------

function RosterReportView({ report }: { report: RosterReportResponse }) {
  return (
    <div className='space-y-5'>
      {/* Scoring context badge */}
      <div className='flex items-center gap-1.5 text-xs text-muted-foreground'>
        <span className='rounded-full bg-muted px-2 py-0.5 font-medium'>
          Re-scored under league settings
        </span>
        <span>·</span>
        <span>
          {report.roster_format} format · {report.roster_size} players
        </span>
      </div>

      {/* Optimal starters */}
      <section>
        <h3 className='text-xs font-semibold uppercase text-muted-foreground mb-2'>
          Optimal Starters
        </h3>
        <div className='rounded-lg border divide-y'>
          <PlayerRowList
            rows={report.starters}
            showSlot
            getSlot={(s) => s.slot}
          />
        </div>
      </section>

      {/* Bench */}
      {report.bench.length > 0 && (
        <section>
          <h3 className='text-xs font-semibold uppercase text-muted-foreground mb-2'>
            Bench ({report.bench.length})
          </h3>
          <div className='rounded-lg border divide-y'>
            <PlayerRowList rows={report.bench} compact dimPoints />
          </div>
        </section>
      )}

      {/* Drop candidates */}
      {report.drop_candidates.length > 0 && (
        <section>
          <h3 className='text-xs font-semibold uppercase text-muted-foreground mb-2'>
            Drop Candidates
          </h3>
          <div className='rounded-lg border divide-y'>
            {report.drop_candidates.map((d, i) => (
              <div
                key={i}
                className='flex items-start justify-between px-4 py-2.5 gap-3'
              >
                <div className='flex items-center gap-2.5 min-w-0'>
                  <PosBadge pos={d.position ?? null} />
                  <span className='text-sm font-medium truncate'>
                    {d.player_name ?? '—'}
                  </span>
                </div>
                <div className='text-right shrink-0'>
                  <p className={`text-xs ${DANGER_TEXT}`}>{d.reason}</p>
                  <p className='text-[10px] text-muted-foreground tabular-nums'>
                    {Number(d.value).toFixed(1)} proj pts
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Waivers view
// ---------------------------------------------------------------------------

function WaiversView({ waivers }: { waivers: WaiversResponse }) {
  if (waivers.targets.length === 0) {
    return (
      <p className='rounded-md border p-4 text-sm text-muted-foreground'>
        No waiver targets available. All projected players may already be
        rostered.
      </p>
    );
  }

  return (
    <div className='space-y-2'>
      <div className='text-xs text-muted-foreground'>
        Top {waivers.targets.length} available free agents ranked by
        league-scored season projection
      </div>
      <div className='rounded-lg border divide-y'>
        <PlayerRowList
          rows={waivers.targets}
          extra={(t) =>
            t.upgrades_over ? (
              <p className={`text-[10px] ${WARN_TEXT}`}>
                upgrades over {t.upgrades_over}
              </p>
            ) : (
              <p className='text-[10px] text-muted-foreground'>depth</p>
            )
          }
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Draft-Prep view (pre-season / pre_draft league state)
// ---------------------------------------------------------------------------

/**
 * Value badge shown next to a player's ADP rank in the best-available table.
 *
 * Positive value means our model projects the player higher than the market
 * does (adp_rank - projection_rank > 0). Green when value >= 10 (strong
 * undervaluation signal), yellow for 1-9, muted for neutral/negative.
 */
function ValueBadge({ value }: { value: number | null }) {
  if (value == null) return null;
  let cls: string;
  let label: string;
  if (value >= 10) {
    cls = `${SUCCESS_TEXT} font-semibold`;
    label = `+${value}`;
  } else if (value > 0) {
    cls = `${WARN_TEXT}`;
    label = `+${value}`;
  } else if (value === 0) {
    cls = 'text-muted-foreground';
    label = '±0';
  } else {
    cls = 'text-muted-foreground';
    label = String(value);
  }
  return (
    <span className={`text-[10px] tabular-nums ${cls}`} title='ADP rank − our projection rank'>
      {label}
    </span>
  );
}

/** A single player row used in the best-available and rookies tables. */
function BestAvailableRow({
  player,
  rank,
}: {
  player: BestAvailablePlayer;
  rank: number;
}) {
  return (
    <div className='flex items-center justify-between px-4 py-2.5 gap-3'>
      <div className='flex items-center gap-2.5 min-w-0'>
        <span className='w-5 text-xs text-muted-foreground tabular-nums shrink-0'>
          {rank}
        </span>
        <PosBadge pos={player.position} />
        <div className='min-w-0'>
          <p className='text-sm font-medium truncate'>
            {player.player_name ?? '—'}
          </p>
          {player.team && (
            <p className='text-[10px] text-muted-foreground'>{player.team}</p>
          )}
        </div>
      </div>
      <div className='flex items-center gap-3 shrink-0'>
        {/* ADP column */}
        <div className='text-right w-16'>
          {player.adp_rank != null ? (
            <>
              <p className='text-xs tabular-nums text-muted-foreground'>
                ADP {player.adp_rank}
              </p>
              <ValueBadge value={player.value} />
            </>
          ) : (
            <p className='text-[10px] text-muted-foreground'>no ADP</p>
          )}
        </div>
        {/* Projected points column */}
        <p className={`text-sm font-semibold tabular-nums w-12 text-right ${SUCCESS_TEXT}`}>
          {player.projected_season_points != null
            ? player.projected_season_points.toFixed(1)
            : '—'}
        </p>
      </div>
    </div>
  );
}

/**
 * DraftPrepView — shown when the connected league is in pre-draft mode.
 *
 * Fetches GET /api/league/{id}/draft-prep and renders four sections:
 *   1. Draft info header (type, rounds, slot, status)
 *   2. Keeper candidates card (when the user has a pre-loaded roster)
 *   3. Best-available table with ADP rank + value badge (green = undervalued)
 *   4. Rookies tab (subset sorted by ADP — market rank beats our fallback projections)
 */
function DraftPrepView({ prep }: { prep: LeagueDraftPrepResponse }) {
  const [tab, setTab] = useState<'best_available' | 'rookies'>('best_available');

  const { draft_info, keeper_candidates, best_available, rookies, rookie_note } = prep;
  const activeList = tab === 'rookies' ? rookies : best_available;

  return (
    <div className='space-y-4'>
      {/* Draft info header */}
      {draft_info && (
        <div className='rounded-lg border p-4 space-y-2'>
          <div className='flex items-center justify-between'>
            <h3 className='text-sm font-semibold'>Draft</h3>
            <span className='inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium text-muted-foreground capitalize'>
              {draft_info.status.replace('_', ' ')}
            </span>
          </div>
          <div className='flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground'>
            <span>
              Type:{' '}
              <span className='font-medium text-foreground capitalize'>
                {draft_info.type}
              </span>
            </span>
            <span>
              <span className='font-medium text-foreground'>
                {draft_info.rounds}
              </span>{' '}
              {draft_info.rounds === 1 ? 'round' : 'rounds'}
            </span>
            {draft_info.user_slot != null ? (
              <span>
                Your slot:{' '}
                <span className='font-medium text-foreground'>
                  #{draft_info.user_slot}
                </span>
              </span>
            ) : (
              <span className='italic'>Draft order not set yet</span>
            )}
          </div>
        </div>
      )}

      {/* Keeper candidates — only shown when the user has a roster */}
      {keeper_candidates.length > 0 && (
        <section>
          <h3 className='text-xs font-semibold uppercase text-muted-foreground mb-2'>
            Your Roster — Keeper Candidates
          </h3>
          <div className='rounded-lg border divide-y'>
            {keeper_candidates.map((k, i) => (
              <div
                key={i}
                className='flex items-center justify-between px-4 py-2.5 gap-3'
              >
                <div className='flex items-center gap-2.5 min-w-0'>
                  <PosBadge pos={k.position} />
                  <div className='min-w-0'>
                    <p className='text-sm font-medium truncate'>
                      {k.player_name ?? '—'}
                    </p>
                    {k.team && (
                      <p className='text-[10px] text-muted-foreground'>
                        {k.team}
                      </p>
                    )}
                  </div>
                  {k.taxi_eligible && (
                    <span className='inline-flex items-center rounded border border-dashed px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground'>
                      TAXI
                    </span>
                  )}
                </div>
                <p className={`text-sm font-semibold tabular-nums shrink-0 ${SUCCESS_TEXT}`}>
                  {k.projected_season_points != null
                    ? k.projected_season_points.toFixed(1)
                    : '—'}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Best-available / Rookies tab bar */}
      <div>
        <div className='sticky top-0 z-10 bg-background flex gap-1 border-b mb-0'>
          {(['best_available', 'rookies'] as const).map((t) => (
            <button
              key={t}
              type='button'
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-sm -mb-px border-b-2 ${
                tab === t
                  ? 'border-primary font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t === 'best_available'
                ? `Best Available (${best_available.length})`
                : `Rookies (${rookies.length})`}
            </button>
          ))}
        </div>

        {/* Rookies tab note */}
        {tab === 'rookies' && rookie_note && (
          <p className='text-[10px] text-muted-foreground px-1 pt-2 pb-1 italic'>
            {rookie_note}
          </p>
        )}

        {/* Column headers */}
        {activeList.length > 0 && (
          <div className='flex items-center justify-between px-4 py-1.5 text-[10px] font-semibold uppercase text-muted-foreground'>
            <span>Player</span>
            <div className='flex gap-3'>
              <span className='w-16 text-right'>ADP / Value</span>
              <span className='w-12 text-right'>Proj Pts</span>
            </div>
          </div>
        )}

        {activeList.length === 0 ? (
          <p className='rounded-md border p-4 text-sm text-muted-foreground mt-2'>
            No players found for this view.
          </p>
        ) : (
          <div className='rounded-lg border divide-y'>
            {activeList.map((player, i) => (
              <BestAvailableRow
                key={player.sleeper_player_id || i}
                player={player}
                rank={i + 1}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
