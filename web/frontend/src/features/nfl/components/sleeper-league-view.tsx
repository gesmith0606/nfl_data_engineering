'use client';

/**
 * Phase 74 SLEEP-01..03: Sleeper league connection + roster view.
 *
 * Username-only auth (no OAuth). On successful login, the backend sets an
 * HttpOnly cookie; client-side state retains user/leagues for the session.
 */

import { useEffect, useState } from 'react';
import {
  fetchSleeperRosters,
  sleeperLogin,
} from '@/lib/nfl/api';
import type {
  SleeperLeague,
  SleeperRoster,
  SleeperUser
} from '@/lib/nfl/types';

interface AuthState {
  user: SleeperUser;
  leagues: SleeperLeague[];
}

export function SleeperLeagueView() {
  const [username, setUsername] = useState('');
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [selectedLeagueId, setSelectedLeagueId] = useState<string | null>(null);
  const [rosters, setRosters] = useState<SleeperRoster[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await sleeperLogin(username.trim());
      setAuth(resp);
      if (resp.leagues.length > 0) {
        setSelectedLeagueId(resp.leagues[0].league_id);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`Login failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedLeagueId || !auth) return;
    let cancelled = false;
    setLoading(true);
    fetchSleeperRosters(selectedLeagueId, auth.user.user_id)
      .then((r) => {
        if (!cancelled) setRosters(r);
      })
      .catch((e) => {
        if (!cancelled) setError(`Failed to load rosters: ${e?.message ?? e}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedLeagueId, auth]);

  if (!auth) {
    return (
      <div className='space-y-4'>
        <div className='rounded-lg border p-6'>
          <h3 className='text-lg font-semibold'>Connect your Sleeper league</h3>
          <p className='mt-1 text-sm text-muted-foreground'>
            Enter your Sleeper username. We'll fetch your leagues and rosters
            so the AI advisor can give personalized advice.
          </p>
          <form onSubmit={handleLogin} className='mt-4 flex gap-2'>
            <input
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
              className='rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50'
            >
              {loading ? 'Connecting…' : 'Connect'}
            </button>
          </form>
          {error && (
            <p className='mt-2 text-sm text-red-600 dark:text-red-400'>{error}</p>
          )}
        </div>
      </div>
    );
  }

  const userRoster = rosters.find((r) => r.is_user_roster);

  return (
    <div className='space-y-6'>
      <div className='flex items-center justify-between rounded-lg border p-4'>
        <div>
          <p className='text-sm text-muted-foreground'>Connected as</p>
          <p className='font-medium'>
            {auth.user.display_name || auth.user.username}
          </p>
        </div>
        <button
          type='button'
          onClick={() => {
            setAuth(null);
            setRosters([]);
            setSelectedLeagueId(null);
            setUsername('');
          }}
          className='rounded-md border px-3 py-1.5 text-sm hover:bg-muted'
        >
          Disconnect
        </button>
      </div>

      <div className='space-y-2'>
        <h3 className='text-sm font-semibold uppercase text-muted-foreground'>
          Leagues ({auth.leagues.length})
        </h3>
        {auth.leagues.length === 0 ? (
          <p className='rounded-md border p-4 text-sm text-muted-foreground'>
            No leagues found for your account this season.
          </p>
        ) : (
          <div className='flex flex-wrap gap-2'>
            {auth.leagues.map((league) => (
              <button
                key={league.league_id}
                type='button'
                onClick={() => setSelectedLeagueId(league.league_id)}
                className={`rounded-md border px-3 py-1.5 text-sm ${
                  selectedLeagueId === league.league_id
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted'
                }`}
              >
                {league.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedLeagueId && (
        <RosterPanel
          loading={loading}
          rosters={rosters}
          userRoster={userRoster}
        />
      )}
    </div>
  );
}

function RosterPanel({
  loading,
  rosters,
  userRoster
}: {
  loading: boolean;
  rosters: SleeperRoster[];
  userRoster: SleeperRoster | undefined;
}) {
  if (loading) {
    return <p className='text-sm text-muted-foreground'>Loading rosters…</p>;
  }
  if (rosters.length === 0) {
    return (
      <p className='rounded-md border p-4 text-sm text-muted-foreground'>
        No rosters available.
      </p>
    );
  }
  if (!userRoster) {
    return (
      <p className='rounded-md border p-4 text-sm text-muted-foreground'>
        We couldn't find your roster in this league. Check that your username
        matches your Sleeper account.
      </p>
    );
  }

  return (
    <div className='space-y-4'>
      <div>
        <h3 className='text-sm font-semibold uppercase text-muted-foreground'>
          Your Lineup ({userRoster.starters.length})
        </h3>
        <ul className='mt-2 divide-y rounded-md border'>
          {userRoster.starters.map((p) => (
            <li
              key={p.player_id}
              className='flex items-center justify-between px-4 py-2 text-sm'
            >
              <span className='font-medium'>{p.player_name ?? p.player_id}</span>
              <span className='text-xs text-muted-foreground'>
                {p.position ?? '—'} · {p.team ?? '—'}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className='text-sm font-semibold uppercase text-muted-foreground'>
          Bench ({userRoster.bench.length})
        </h3>
        <ul className='mt-2 divide-y rounded-md border'>
          {userRoster.bench.map((p) => (
            <li
              key={p.player_id}
              className='flex items-center justify-between px-4 py-2 text-sm'
            >
              <span>{p.player_name ?? p.player_id}</span>
              <span className='text-xs text-muted-foreground'>
                {p.position ?? '—'} · {p.team ?? '—'}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
