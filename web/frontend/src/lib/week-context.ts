/**
 * Shared helpers for resolving "latest available" NFL week context.
 *
 * Used by the AI advisor tool {@link getPositionRankings} to auto-resolve a
 * sensible default week when the user asks "who are the top 10 RBs" without
 * specifying one. The backend `/api/projections/latest-week` endpoint scans
 * the Gold layer for the highest week that has projection data and returns
 * it alongside the parquet's mtime.
 *
 * Caching: responses are memoized per-season for 60 seconds so a single chat
 * turn making multiple tool calls doesn't hammer the backend.
 */
const FASTAPI_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface LatestWeekInfo {
  season: number;
  week: number | null;
  data_as_of: string | null;
}

interface CacheEntry {
  value: LatestWeekInfo;
  expiresAt: number;
}

const CACHE_TTL_MS = 60_000;
const cache = new Map<number, CacheEntry>();

/**
 * Look up the highest week of Gold projections data for the given season.
 *
 * Returns:
 *   - `{ season, week: number, data_as_of: string }` when data is available
 *   - `{ season, week: null, data_as_of: null }` when the backend reports
 *     no projections yet (offseason / brand-new season)
 *   - `null` when the backend is unreachable — caller should fall back to a
 *     user-supplied default rather than silently misreporting
 */
export async function resolveDefaultWeek(
  season: number
): Promise<LatestWeekInfo | null> {
  const now = Date.now();
  const cached = cache.get(season);
  if (cached && cached.expiresAt > now) {
    return cached.value;
  }

  try {
    const res = await fetch(
      `${FASTAPI_URL}/api/projections/latest-week?season=${season}`,
      {
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store'
      }
    );
    if (!res.ok) {
      console.warn(
        `[week-context] /api/projections/latest-week returned HTTP ${res.status} for season ${season}`
      );
      return null;
    }
    const data = (await res.json()) as LatestWeekInfo;
    const entry: CacheEntry = {
      value: data,
      expiresAt: now + CACHE_TTL_MS
    };
    cache.set(season, entry);
    return data;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(
      `[week-context] failed to fetch latest week for season ${season}: ${msg}`
    );
    return null;
  }
}

/**
 * Clear the latest-week cache. Exported for tests and forced refreshes.
 */
export function clearLatestWeekCache(): void {
  cache.clear();
}
