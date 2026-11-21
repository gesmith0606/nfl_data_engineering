/**
 * Status flags from `GET /api/projections` that an LLM tool result must carry
 * through, so the advisor can never quote a season total (or a missing week)
 * as a weekly number.
 */
export interface ProjectionStatusFields {
  available?: boolean;
  is_season_total?: boolean;
  message?: string | null;
  latest_available_week?: number | null;
}

export type ProjectionToolStatus =
  | { unavailable: true; result: Record<string, unknown> }
  | { unavailable: false; extra: Record<string, unknown> };

export function projectionToolStatus(
  data: ProjectionStatusFields,
  week: number,
  season: number
): ProjectionToolStatus {
  if (data.available === false) {
    return {
      unavailable: true,
      result: {
        found: false,
        available: false,
        season,
        week,
        latest_available_week: data.latest_available_week ?? null,
        message:
          (data.message ?? `Week ${week} projections are not published yet.`) +
          ' Do NOT estimate or quote any projection for this week.'
      }
    };
  }
  if (data.is_season_total) {
    return {
      unavailable: false,
      extra: {
        is_season_total: true,
        warning:
          'These projected_points are FULL-SEASON TOTALS (preseason board), not points for week ' +
          `${week}. Never present them as a weekly projection.`
      }
    };
  }
  return { unavailable: false, extra: {} };
}
