/**
 * Shared helpers for resolving "latest available" NFL week context.
 *
 * Used by the AI advisor tool {@link getPositionRankings} to auto-resolve a
 * sensible default week when the user asks "who are the top 10 RBs" without
 * specifying one. The backend `/api/projections/latest-week` endpoint scans
 * the Gold layer for the highest week that has projection data and returns
 * it alongside the parquet's mtime.
 *
 * Caching: responses are memoized per-season for 5 minutes — long enough to
 * absorb tool-call fan-out from a single chat turn (advisor may fire
 * getPositionRankings multiple times in one response), short enough that a
 * newly-written Gold week surfaces within reasonable drift.
 */
const FASTAPI_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface LatestWeekInfo {
  season: number | null;
  week: number | null;
  data_as_of: string | null;
}

interface CacheEntry {
  value: LatestWeekInfo;
  expiresAt: number;
}

const CACHE_TTL_MS = 5 * 60_000;

const projectionsCache = new Map<number, CacheEntry>();
const predictionsCache = new Map<number, CacheEntry>();

/**
 * Generic latest-week resolver shared between the projections and predictions
 * gold layers. Each layer passes its own endpoint path and per-layer cache so
 * a fresh write to one layer doesn't invalidate the other. Returns `null` on
 * network/HTTP failure so callers can fall back to a user-supplied default
 * instead of silently misreporting.
 */
async function resolveLatestWeek(
  endpoint: string,
  cache: Map<number, CacheEntry>,
  season: number,
  label: string
): Promise<LatestWeekInfo | null> {
  const now = Date.now();
  const cached = cache.get(season);
  if (cached && cached.expiresAt > now) {
    return cached.value;
  }

  try {
    const res = await fetch(`${FASTAPI_URL}${endpoint}?season=${season}`, {
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store'
    });
    if (!res.ok) {
      console.warn(
        `[week-context] ${endpoint} returned HTTP ${res.status} for season ${season}`
      );
      return null;
    }
    const data = (await res.json()) as LatestWeekInfo;
    cache.set(season, { value: data, expiresAt: now + CACHE_TTL_MS });
    return data;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(
      `[week-context] failed to fetch ${label} latest week for season ${season}: ${msg}`
    );
    return null;
  }
}

/**
 * Look up the highest week of Gold projections data for the given season.
 *
 * Returns:
 *   - `{ season, week: number, data_as_of: string }` when data is available
 *   - `{ season, week: null, data_as_of: null }` when the backend reports
 *     no projections yet (offseason / brand-new season)
 *   - `null` when the backend is unreachable
 */
export function resolveDefaultWeek(
  season: number
): Promise<LatestWeekInfo | null> {
  return resolveLatestWeek(
    '/api/projections/latest-week',
    projectionsCache,
    season,
    'projections'
  );
}

/**
 * Look up the highest week of Gold predictions data for the given season.
 *
 * Mirror of {@link resolveDefaultWeek} anchored to game predictions. The two
 * layers can be out of sync (e.g. 2026 has preseason projections but zero
 * game predictions until the season starts), so the predictions page must
 * resolve its own latest-week to avoid landing on an empty slice.
 */
export function resolvePredictionsLatestWeek(
  season: number
): Promise<LatestWeekInfo | null> {
  return resolveLatestWeek(
    '/api/predictions/latest-week',
    predictionsCache,
    season,
    'predictions'
  );
}

/**
 * Clear all latest-week caches. Exported for tests and forced refreshes.
 */
export function clearLatestWeekCache(): void {
  projectionsCache.clear();
  predictionsCache.clear();
}
