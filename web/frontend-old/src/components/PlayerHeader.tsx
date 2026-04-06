"use client";

import type { PlayerProjection } from "@/lib/types";
import { getTeamColor } from "@/lib/teamColors";

const POSITION_BADGE: Record<string, string> = {
  QB: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  RB: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  WR: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  TE: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  K: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};


interface PlayerHeaderProps {
  player: PlayerProjection;
}

export default function PlayerHeader({ player }: PlayerHeaderProps) {
  const badgeClass =
    POSITION_BADGE[player.position] || "bg-gray-100 text-gray-700";
  const teamColor = getTeamColor(player.team);

  return (
    <div
      className="rounded-lg border-l-4 bg-white p-6 shadow-sm dark:bg-gray-900"
      style={{ borderLeftColor: teamColor }}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <span
            className="inline-flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold text-white"
            style={{ backgroundColor: teamColor }}
          >
            {player.team}
          </span>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white sm:text-3xl">
              {player.player_name}
            </h1>
            <div className="mt-1 flex items-center gap-3">
              <span
                className={`inline-block rounded px-2.5 py-1 text-sm font-semibold ${badgeClass}`}
              >
                {player.position}
              </span>
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">
                {player.team}
              </span>
              {player.injury_status &&
                player.injury_status !== "Active" && (
                  <span className="rounded bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                    {player.injury_status}
                  </span>
                )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {player.position_rank !== null && (
            <div className="text-right">
              <p className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                {player.position} Rank
              </p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                #{player.position_rank}
              </p>
            </div>
          )}
          <div className="text-right">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Format
            </p>
            <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">
              {player.scoring_format === "ppr"
                ? "PPR"
                : player.scoring_format === "half_ppr"
                  ? "Half PPR"
                  : "Standard"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
