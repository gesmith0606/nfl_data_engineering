"use client";

import type { PlayerProjection } from "@/lib/types";

interface ProjectionBreakdownProps {
  player: PlayerProjection;
}

function formatStat(value: number | null): string {
  if (value === null || value === undefined) return "-";
  return value.toFixed(1);
}

interface StatRow {
  label: string;
  value: number | null;
}

function getPositionStats(player: PlayerProjection): StatRow[] {
  switch (player.position) {
    case "QB":
      return [
        { label: "Pass Yards", value: player.proj_pass_yards },
        { label: "Pass TDs", value: player.proj_pass_tds },
        { label: "Rush Yards", value: player.proj_rush_yards },
        { label: "Rush TDs", value: player.proj_rush_tds },
        { label: "INTs", value: null }, // Not in current type, show dash
      ];
    case "RB":
      return [
        { label: "Rush Yards", value: player.proj_rush_yards },
        { label: "Rush TDs", value: player.proj_rush_tds },
        { label: "Receptions", value: player.proj_rec },
        { label: "Rec Yards", value: player.proj_rec_yards },
        { label: "Rec TDs", value: player.proj_rec_tds },
      ];
    case "WR":
      return [
        { label: "Receptions", value: player.proj_rec },
        { label: "Rec Yards", value: player.proj_rec_yards },
        { label: "Rec TDs", value: player.proj_rec_tds },
        { label: "Rush Yards", value: player.proj_rush_yards },
      ];
    case "TE":
      return [
        { label: "Receptions", value: player.proj_rec },
        { label: "Rec Yards", value: player.proj_rec_yards },
        { label: "Rec TDs", value: player.proj_rec_tds },
      ];
    case "K":
      return [
        { label: "FG Makes", value: player.proj_fg_makes },
        { label: "XP Makes", value: player.proj_xp_makes },
      ];
    default:
      return [];
  }
}

export default function ProjectionBreakdown({
  player,
}: ProjectionBreakdownProps) {
  const stats = getPositionStats(player);
  const range = player.projected_ceiling - player.projected_floor;
  const projectedOffset =
    range > 0
      ? ((player.projected_points - player.projected_floor) / range) * 100
      : 50;

  return (
    <div className="space-y-6">
      {/* Projected Points Card */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Projected Points
        </h2>

        {/* Large number */}
        <div className="mb-6 text-center">
          <p className="text-5xl font-bold text-gray-900 dark:text-white">
            {player.projected_points.toFixed(1)}
          </p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            projected fantasy points
          </p>
        </div>

        {/* Range bar */}
        <div className="mb-2 flex items-center justify-between text-xs font-medium text-gray-500 dark:text-gray-400">
          <span>Floor: {player.projected_floor.toFixed(1)}</span>
          <span>Ceiling: {player.projected_ceiling.toFixed(1)}</span>
        </div>
        <div className="relative h-4 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
          {/* Gradient bar */}
          <div className="absolute inset-0 rounded-full bg-gradient-to-r from-red-400 via-yellow-400 to-green-400 opacity-80" />
          {/* Projected marker */}
          <div
            className="absolute top-0 h-full w-1 -translate-x-1/2 rounded bg-gray-900 shadow-md dark:bg-white"
            style={{ left: `${projectedOffset}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-xs text-gray-400 dark:text-gray-500">
          <span>Worst case</span>
          <span>Best case</span>
        </div>
      </div>

      {/* Position-specific stats */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Stat Projections
        </h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="rounded-lg bg-gray-50 p-4 text-center dark:bg-gray-800/50"
            >
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {formatStat(stat.value)}
              </p>
              <p className="mt-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                {stat.label}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
