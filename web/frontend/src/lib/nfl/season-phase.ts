/**
 * Season phase helper — drives the phase-aware module on the home hub.
 *
 * NFL calendar (US):
 *   - Regular season + playoffs run early September through early February.
 *   - Draft-prep ramp is July–August (rankings, mocks, preseason projections).
 *   - Everything else (February–June) is quiet offseason.
 *
 * Deliberately date-only and dependency-free so it can run on the server at
 * request time or on the client without a hydration mismatch.
 */

export type SeasonPhase = 'draft-prep' | 'in-season' | 'offseason';

export function getSeasonPhase(date: Date = new Date()): SeasonPhase {
  const month = date.getMonth(); // 0 = January
  // September(8)–December(11) and January(0): games are played / graded.
  if (month >= 8 || month === 0) return 'in-season';
  // July(6)–August(7): draft season.
  if (month === 6 || month === 7) return 'draft-prep';
  // February(1)–June(5): quiet.
  return 'offseason';
}

export type InSeasonCadence = 'refresh' | 'gameday' | 'midweek';

/**
 * Within the in-season phase, map the weekday to the dominant activity:
 *   - Tuesday: fresh projections publish + the waiver wire opens.
 *   - Thursday–Sunday: game days — start/sit calls and live edges.
 *   - Otherwise: mid-week prep.
 */
export function getInSeasonCadence(date: Date = new Date()): InSeasonCadence {
  const day = date.getDay(); // 0 = Sunday ... 6 = Saturday
  if (day === 2) return 'refresh'; // Tuesday
  if (day === 0 || day === 4 || day === 5 || day === 6) return 'gameday'; // Thu–Sun
  return 'midweek';
}
