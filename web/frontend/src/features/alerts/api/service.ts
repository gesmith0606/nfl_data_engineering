/**
 * Alerts center service — assembles roster-scoped alerts from existing APIs.
 *
 * No new backend: composes `GET /api/news/alerts` (season/week alert feed),
 * `GET /api/league/{id}/overview` (connected-league rosters) and
 * `GET /api/news/player-badges/{id}` (event chips for matched players).
 * Client-only — reads connected leagues from localStorage.
 */

import {
  fetchAlerts,
  fetchCurrentWeek,
  fetchLeagueOverview,
  fetchPlayerBadges
} from '@/lib/nfl/api';
import { loadConnectedLeagues } from '@/lib/nfl/connected-leagues';
import {
  assembleAlerts,
  buildRosterIndex,
  type RosterAlert,
  type RosterEntry
} from '@/lib/alerts/assemble';
import type { Alert, ConnectedLeague } from '@/lib/nfl/types';

/** Cap on per-player badge enrichment calls per refresh. */
const MAX_BADGE_LOOKUPS = 12;

export interface AlertsBundle {
  season: number;
  week: number;
  leagueCount: number;
  rosteredCount: number;
  yourPlayers: RosterAlert[];
  leagueNews: Alert[];
  /** player_id → event badge chips (e.g. 'hamstring', 'limited practice'). */
  badges: Record<string, string[]>;
}

/** Flatten each connected league's user roster into match entries. */
async function fetchRosterEntries(leagues: ConnectedLeague[]): Promise<RosterEntry[]> {
  const results = await Promise.allSettled(
    // Older stored leagues may predate user_id; pass undefined so the
    // overview call fails-open for that league instead of sending ''.
    leagues.map((league) =>
      fetchLeagueOverview(league.league_id, league.user_id || undefined)
    )
  );
  const entries: RosterEntry[] = [];
  results.forEach((result, i) => {
    if (result.status !== 'fulfilled') return; // fail-open: skip broken league
    const league = leagues[i];
    for (const player of result.value.user_roster) {
      entries.push({
        playerId: player.sleeper_player_id,
        playerName: player.player_name,
        position: player.position,
        team: player.team,
        leagueId: league.league_id,
        leagueName: league.league_name
      });
    }
  });
  return entries;
}

/** Enrich matched roster alerts with deduplicated event badges (bounded fan-out). */
async function fetchAlertBadges(
  alerts: RosterAlert[],
  season: number,
  week: number
): Promise<Record<string, string[]>> {
  const targets = alerts.slice(0, MAX_BADGE_LOOKUPS);
  const results = await Promise.allSettled(
    targets.map((alert) => fetchPlayerBadges(alert.player_id, season, week))
  );
  const badges: Record<string, string[]> = {};
  results.forEach((result, i) => {
    if (result.status === 'fulfilled' && result.value.badges.length > 0) {
      badges[targets[i].player_id] = result.value.badges;
    }
  });
  return badges;
}

/**
 * Build the full alerts bundle for the bell: current week's alert feed split
 * into "your players" (tagged with league names) and "league news".
 */
export async function fetchAlertsBundle(): Promise<AlertsBundle> {
  const leagues = loadConnectedLeagues();
  const { season, week } = await fetchCurrentWeek();
  const [alerts, rosterEntries] = await Promise.all([
    fetchAlerts(season, week),
    fetchRosterEntries(leagues)
  ]);
  const index = buildRosterIndex(rosterEntries);
  const { yourPlayers, leagueNews } = assembleAlerts(alerts, index);
  const badges = await fetchAlertBadges(yourPlayers, season, week);
  return {
    season,
    week,
    leagueCount: leagues.length,
    rosteredCount: index.size,
    yourPlayers,
    leagueNews,
    badges
  };
}
