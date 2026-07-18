/**
 * Last-seen tracking for the alerts center — mirrors the localStorage
 * conventions of `src/lib/nfl/connected-leagues.ts` (window-guarded, fails
 * closed to a safe default).
 */

export const ALERTS_LAST_SEEN_KEY = 'nfl.alerts.lastSeen';

/** ISO timestamp of the last time the alerts sheet was opened, or null. */
export function loadAlertsLastSeen(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(ALERTS_LAST_SEEN_KEY);
    if (!raw || Number.isNaN(Date.parse(raw))) return null;
    return raw;
  } catch {
    return null;
  }
}

/** Persist the last-seen timestamp (defaults to now). Returns the value saved. */
export function saveAlertsLastSeen(iso: string = new Date().toISOString()): string {
  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem(ALERTS_LAST_SEEN_KEY, iso);
    } catch {
      // Quota/private-mode failures are non-fatal — the badge just stays lit.
    }
  }
  return iso;
}
