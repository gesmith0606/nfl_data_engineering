/**
 * Shared access to the user's connected Sleeper leagues.
 *
 * League Sync (sleeper-league-view) writes up to 3 leagues to
 * localStorage under `nfl.connectedLeagues`; the AI advisor reads the same
 * key so chat requests carry league context (roster, scoring, user identity).
 */

import type { ConnectedLeague } from '@/lib/nfl/types';

export const CONNECTED_LEAGUES_KEY = 'nfl.connectedLeagues';
export const MAX_CONNECTED_LEAGUES = 3;

export function loadConnectedLeagues(): ConnectedLeague[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(CONNECTED_LEAGUES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (l): l is ConnectedLeague =>
        typeof l === 'object' &&
        l !== null &&
        typeof (l as ConnectedLeague).league_id === 'string' &&
        typeof (l as ConnectedLeague).user_id === 'string'
    );
  } catch {
    return [];
  }
}

export function saveConnectedLeagues(leagues: ConnectedLeague[]): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(
    CONNECTED_LEAGUES_KEY,
    JSON.stringify(leagues.slice(0, MAX_CONNECTED_LEAGUES))
  );
}

/**
 * Returns the updated list with `league` first, deduped by id and capped.
 * Does NOT persist — call saveConnectedLeagues with the result.
 */
export function upsertConnectedLeague(league: ConnectedLeague): ConnectedLeague[] {
  const existing = loadConnectedLeagues();
  const filtered = existing.filter((l) => l.league_id !== league.league_id);
  return [league, ...filtered].slice(0, MAX_CONNECTED_LEAGUES);
}

export function removeConnectedLeague(leagueId: string): ConnectedLeague[] {
  const updated = loadConnectedLeagues().filter((l) => l.league_id !== leagueId);
  saveConnectedLeagues(updated);
  return updated;
}
