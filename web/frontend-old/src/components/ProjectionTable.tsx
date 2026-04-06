"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import type { PlayerProjection, SortConfig, SortDirection } from "@/lib/types";
import { getTeamColor } from "@/lib/teamColors";

const POSITION_BADGE: Record<string, string> = {
  QB: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  RB: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  WR: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  TE: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  K: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

interface ProjectionTableProps {
  projections: PlayerProjection[];
}

function formatStat(value: number | null): string {
  if (value === null || value === undefined) return "-";
  return value.toFixed(1);
}

function SortIcon({
  column,
  sortConfig,
}: {
  column: string;
  sortConfig: SortConfig;
}) {
  if (sortConfig.key !== column) {
    return (
      <span className="ml-1 text-gray-400 opacity-0 group-hover:opacity-100">
        &#8597;
      </span>
    );
  }
  return (
    <span className="ml-1">
      {sortConfig.direction === "asc" ? "\u2191" : "\u2193"}
    </span>
  );
}

export default function ProjectionTable({ projections }: ProjectionTableProps) {
  const router = useRouter();
  const [sortConfig, setSortConfig] = useState<SortConfig>({
    key: "projected_points",
    direction: "desc",
  });

  function handleSort(key: string) {
    setSortConfig((prev) => {
      if (prev.key === key) {
        return {
          key,
          direction: (prev.direction === "asc" ? "desc" : "asc") as SortDirection,
        };
      }
      return { key, direction: "desc" };
    });
  }

  const sorted = useMemo(() => {
    const items = [...projections];
    items.sort((a, b) => {
      const aVal = (a as unknown as Record<string, unknown>)[sortConfig.key];
      const bVal = (b as unknown as Record<string, unknown>)[sortConfig.key];

      // Nulls sort to the bottom
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;

      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortConfig.direction === "asc"
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }

      const diff = (aVal as number) - (bVal as number);
      return sortConfig.direction === "asc" ? diff : -diff;
    });
    return items;
  }, [projections, sortConfig]);

  const columnHeader = (key: string, label: string, align: "left" | "right" = "right") => (
    <th
      key={key}
      onClick={() => handleSort(key)}
      className={`group cursor-pointer whitespace-nowrap px-3 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white ${align === "left" ? "text-left" : "text-right"}`}
    >
      {label}
      <SortIcon column={key} sortConfig={sortConfig} />
    </th>
  );

  if (projections.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-12 text-center dark:border-gray-800 dark:bg-gray-900">
        <p className="text-gray-500 dark:text-gray-400">
          No projections available. Make sure the backend is running and data has
          been generated.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
        <thead className="bg-gray-50 dark:bg-gray-800/50">
          <tr>
            <th className="w-12 px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              #
            </th>
            {columnHeader("player_name", "Player", "left")}
            {columnHeader("team", "Team", "left")}
            {columnHeader("position", "Pos", "left")}
            {columnHeader("projected_points", "Proj Pts")}
            {columnHeader("projected_floor", "Floor")}
            {columnHeader("projected_ceiling", "Ceiling")}
            {columnHeader("proj_pass_yards", "Pass Yds")}
            {columnHeader("proj_pass_tds", "Pass TD")}
            {columnHeader("proj_rush_yards", "Rush Yds")}
            {columnHeader("proj_rush_tds", "Rush TD")}
            {columnHeader("proj_rec", "Rec")}
            {columnHeader("proj_rec_yards", "Rec Yds")}
            {columnHeader("proj_rec_tds", "Rec TD")}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800/50">
          {sorted.map((player, idx) => (
            <tr
              key={player.player_id}
              onClick={() => router.push(`/players/${player.player_id}`)}
              className="cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/30"
              style={{ borderLeft: `3px solid ${getTeamColor(player.team)}` }}
            >
              <td className="whitespace-nowrap px-3 py-3 text-sm text-gray-500 dark:text-gray-400">
                {idx + 1}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-sm font-medium text-gray-900 dark:text-white">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-white"
                    style={{ backgroundColor: getTeamColor(player.team) }}
                    title={player.team}
                  >
                    {player.team}
                  </span>
                  {player.player_name}
                  {player.injury_status &&
                    player.injury_status !== "Active" && (
                      <span className="rounded bg-yellow-100 px-1 py-0.5 text-xs text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                        {player.injury_status}
                      </span>
                    )}
                </div>
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-sm text-gray-700 dark:text-gray-300">
                {player.team}
              </td>
              <td className="whitespace-nowrap px-3 py-3">
                <span
                  className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${POSITION_BADGE[player.position] || "bg-gray-100 text-gray-700"}`}
                >
                  {player.position}
                </span>
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm font-bold text-gray-900 dark:text-white">
                {player.projected_points.toFixed(1)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-500 dark:text-gray-400">
                {player.projected_floor.toFixed(1)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-500 dark:text-gray-400">
                {player.projected_ceiling.toFixed(1)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                {formatStat(player.proj_pass_yards)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                {formatStat(player.proj_pass_tds)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                {formatStat(player.proj_rush_yards)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                {formatStat(player.proj_rush_tds)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                {formatStat(player.proj_rec)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                {formatStat(player.proj_rec_yards)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600 dark:text-gray-400">
                {formatStat(player.proj_rec_tds)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
