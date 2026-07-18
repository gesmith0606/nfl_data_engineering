/**
 * Roster-scoped alert assembly — pure functions, no DOM/network.
 *
 * Takes the season-wide alert feed (`GET /api/news/alerts`) plus the user's
 * rostered players across connected Sleeper leagues and splits it into
 * "your players" (rostered, tagged with league names) vs "league news"
 * (everything else). Kept side-effect free so vitest covers it without jsdom
 * fixtures — the network fan-out lives in `src/features/alerts/api/service.ts`.
 *
 * Matching note: `Alert.player_id` is a GSIS id while Sleeper rosters carry
 * `sleeper_player_id`, so exact-id equality rarely fires across sources.
 * Normalized-name matching is the workhorse; id equality is kept as a
 * free extra for same-source ids.
 */

import type { Alert } from '@/lib/nfl/types';

/** One rostered player in one connected league. */
export interface RosterEntry {
  playerId: string;
  playerName: string | null;
  position: string | null;
  team: string | null;
  leagueId: string;
  leagueName: string;
}

/** League tag attached to a matched alert. */
export interface AlertLeagueTag {
  leagueId: string;
  leagueName: string;
}

/** An alert affecting one of the user's rostered players. */
export interface RosterAlert extends Alert {
  leagues: AlertLeagueTag[];
}

export interface AssembledAlerts {
  yourPlayers: RosterAlert[];
  leagueNews: Alert[];
}

export interface RosterIndex {
  byId: Map<string, RosterEntry[]>;
  byName: Map<string, RosterEntry[]>;
  size: number;
}

/** Severity order — lower sorts first. Negative availability news outranks hype. */
const SEVERITY_RANK: Record<Alert['alert_type'], number> = {
  ruled_out: 0,
  inactive: 1,
  suspended: 2,
  questionable: 3,
  major_negative: 4,
  major_positive: 5
};

const NAME_SUFFIXES = new Set(['jr', 'sr', 'ii', 'iii', 'iv', 'v']);

/**
 * Normalize a player name for cross-source joins: lowercase, strip
 * diacritics/punctuation, drop generational suffixes (Jr/Sr/II...), collapse
 * whitespace. 'Kenneth Walker III' and 'kenneth walker' both → 'kenneth walker'.
 */
export function normalizePlayerName(name: string | null | undefined): string {
  if (!name) return '';
  return name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter((token) => token && !NAME_SUFFIXES.has(token))
    .join(' ');
}

/** Build lookup maps over every rostered player across connected leagues. */
export function buildRosterIndex(entries: RosterEntry[]): RosterIndex {
  const byId = new Map<string, RosterEntry[]>();
  const byName = new Map<string, RosterEntry[]>();
  for (const entry of entries) {
    if (entry.playerId) {
      const list = byId.get(entry.playerId) ?? [];
      list.push(entry);
      byId.set(entry.playerId, list);
    }
    const key = normalizePlayerName(entry.playerName);
    if (key) {
      const list = byName.get(key) ?? [];
      list.push(entry);
      byName.set(key, list);
    }
  }
  return { byId, byName, size: entries.length };
}

function severityOf(alert: Alert): number {
  return SEVERITY_RANK[alert.alert_type] ?? 99;
}

function matchRoster(alert: Alert, index: RosterIndex): RosterEntry[] {
  const matches = [
    ...(index.byId.get(alert.player_id) ?? []),
    ...(index.byName.get(normalizePlayerName(alert.player_name)) ?? [])
  ];
  // Dedupe by league — a player matched by both id and name, or rostered in
  // starters + bench payloads, should tag each league once.
  const seen = new Set<string>();
  return matches.filter((m) => {
    if (seen.has(m.leagueId)) return false;
    seen.add(m.leagueId);
    return true;
  });
}

/**
 * Split the alert feed into roster-scoped and general buckets.
 *
 * Alerts are deduped by player (highest severity wins), matched against the
 * roster index, and each bucket is sorted severity-first then by name for a
 * stable render order.
 */
export function assembleAlerts(alerts: Alert[], index: RosterIndex): AssembledAlerts {
  // Dedupe by player id (fall back to normalized name for id-less feeds).
  const byPlayer = new Map<string, Alert>();
  for (const alert of alerts) {
    const key = alert.player_id || normalizePlayerName(alert.player_name);
    if (!key) continue;
    const existing = byPlayer.get(key);
    if (!existing || severityOf(alert) < severityOf(existing)) {
      byPlayer.set(key, alert);
    }
  }

  const yourPlayers: RosterAlert[] = [];
  const leagueNews: Alert[] = [];
  for (const alert of byPlayer.values()) {
    const rosterMatches = matchRoster(alert, index);
    if (rosterMatches.length > 0) {
      yourPlayers.push({
        ...alert,
        leagues: rosterMatches.map((m) => ({ leagueId: m.leagueId, leagueName: m.leagueName }))
      });
    } else {
      leagueNews.push(alert);
    }
  }

  const bySeverityThenName = (a: Alert, b: Alert) =>
    severityOf(a) - severityOf(b) ||
    (a.player_name || '').localeCompare(b.player_name || '');
  yourPlayers.sort(bySeverityThenName);
  leagueNews.sort(bySeverityThenName);

  return { yourPlayers, leagueNews };
}

/**
 * Count alerts newer than the last-seen timestamp.
 *
 * `lastSeenIso === null` (never opened) counts everything. Alerts without a
 * signal timestamp only count when the center has never been opened —
 * otherwise they would ring the bell forever.
 */
export function countUnread(
  alerts: Array<Pick<Alert, 'latest_signal_at'>>,
  lastSeenIso: string | null
): number {
  if (lastSeenIso === null) return alerts.length;
  const lastSeen = Date.parse(lastSeenIso);
  if (Number.isNaN(lastSeen)) return alerts.length;
  return alerts.filter((alert) => {
    if (!alert.latest_signal_at) return false;
    const at = Date.parse(alert.latest_signal_at);
    return !Number.isNaN(at) && at > lastSeen;
  }).length;
}
