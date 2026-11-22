/**
 * Season resolution for the manager tools.
 *
 * `/api/teams/current-week` resolves the LAST season with scheduled games
 * during the offseason (e.g. Aug 2026 → season 2025, week 18), because no
 * 2026 game window has started. The preseason-backed tools (ROS pool,
 * dynasty, trade, value) need the UPCOMING season — the one with a
 * committed preseason parquet — so clamp to the NFL season year.
 */

/**
 * The NFL season in progress or most recently played, as its start year.
 * January and February belong to the season that started the previous
 * autumn (weeks 17–18 and the playoffs); the new league year starts in March.
 * The calendar year is wrong for exactly those weeks.
 */
export function nflSeasonYear(now: Date = new Date()): number {
  const year = now.getFullYear();
  return now.getMonth() >= 2 ? year : year - 1;
}

export function toolSeason(currentWeekSeason?: number, now: Date = new Date()): number {
  const year = nflSeasonYear(now);
  return Math.max(currentWeekSeason ?? year, year);
}
