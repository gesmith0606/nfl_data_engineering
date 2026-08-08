/**
 * Season resolution for the manager tools.
 *
 * `/api/teams/current-week` resolves the LAST season with scheduled games
 * during the offseason (e.g. Aug 2026 → season 2025, week 18), because no
 * 2026 game window has started. The preseason-backed tools (ROS pool,
 * dynasty, trade, value) need the UPCOMING season — the one with a
 * committed preseason parquet — so clamp to the calendar year.
 */
export function toolSeason(currentWeekSeason?: number): number {
  const year = new Date().getFullYear();
  return Math.max(currentWeekSeason ?? year, year);
}
