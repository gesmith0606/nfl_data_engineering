/**
 * Player watchlist — starred players, persisted to localStorage.
 *
 * Complements the roster-scoped alerts bell: the watchlist tracks players
 * you do NOT roster (waiver stashes, trade targets). Client-only, mirrors
 * the connected-leagues storage pattern.
 */

export const WATCHLIST_KEY = 'nfl.watchlist';
export const MAX_WATCHLIST = 30;

export interface WatchedPlayer {
  player_id: string;
  player_name: string;
  position: string;
  team: string | null;
}

export function loadWatchlist(): WatchedPlayer[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (p): p is WatchedPlayer =>
        typeof p === 'object' &&
        p !== null &&
        typeof (p as WatchedPlayer).player_id === 'string' &&
        typeof (p as WatchedPlayer).player_name === 'string'
    );
  } catch {
    return [];
  }
}

export function isWatched(playerId: string): boolean {
  return loadWatchlist().some((p) => p.player_id === playerId);
}

/** Toggle a player; returns the updated (persisted) list. */
export function toggleWatched(player: WatchedPlayer): WatchedPlayer[] {
  const existing = loadWatchlist();
  const updated = existing.some((p) => p.player_id === player.player_id)
    ? existing.filter((p) => p.player_id !== player.player_id)
    : [player, ...existing].slice(0, MAX_WATCHLIST);
  if (typeof window !== 'undefined') {
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(updated));
  }
  return updated;
}
