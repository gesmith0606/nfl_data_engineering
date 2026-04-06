"use client";

import type { PlayerProjection } from "@/lib/types";

interface MatchupContextProps {
  player: PlayerProjection;
}

export default function MatchupContext({ player }: MatchupContextProps) {
  // The current API returns team but not opponent — show season/week context
  const weekLabel =
    player.week === 0 ? "Preseason" : `Week ${player.week}`;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Game Context
      </h2>
      <div className="flex flex-wrap items-center gap-6">
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Season
          </p>
          <p className="text-lg font-bold text-gray-900 dark:text-white">
            {player.season}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Week
          </p>
          <p className="text-lg font-bold text-gray-900 dark:text-white">
            {weekLabel}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Team
          </p>
          <p className="text-lg font-bold text-gray-900 dark:text-white">
            {player.team}
          </p>
        </div>
      </div>
    </div>
  );
}
