"use client";

import type { GamePrediction } from "@/lib/types";
import { getTeamColor } from "@/lib/teamColors";

interface PredictionCardProps {
  prediction: GamePrediction;
}

function confidenceBadge(tier: string) {
  const normalized = tier.toUpperCase();
  if (normalized === "HIGH") {
    return (
      <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-semibold text-green-800 dark:bg-green-900/30 dark:text-green-400">
        HIGH
      </span>
    );
  }
  if (normalized === "MEDIUM") {
    return (
      <span className="inline-flex items-center rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-semibold text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
        MEDIUM
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-300">
      LOW
    </span>
  );
}

function edgeColor(edge: number | null): string {
  if (edge === null) return "text-gray-500 dark:text-gray-400";
  if (edge > 0) return "text-green-600 dark:text-green-400";
  if (edge < 0) return "text-red-600 dark:text-red-400";
  return "text-gray-500 dark:text-gray-400";
}

function formatEdge(edge: number | null): string {
  if (edge === null) return "N/A";
  const sign = edge > 0 ? "+" : "";
  return `${sign}${edge.toFixed(1)}`;
}

function formatSpread(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}`;
}

/** Edge magnitude bar (0-100% width based on abs(edge), capped at 5). */
function EdgeBar({ edge }: { edge: number | null }) {
  if (edge === null) return null;
  const pct = Math.min(Math.abs(edge) / 5, 1) * 100;
  const color =
    edge > 0
      ? "bg-green-500 dark:bg-green-400"
      : "bg-red-500 dark:bg-red-400";
  return (
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
      <div
        className={`h-full rounded-full ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function PredictionCard({ prediction }: PredictionCardProps) {
  const {
    home_team,
    away_team,
    predicted_spread,
    predicted_total,
    vegas_spread,
    vegas_total,
    spread_edge,
    total_edge,
    confidence_tier,
    ats_pick,
    ou_pick,
  } = prediction;

  const homeColor = getTeamColor(home_team);
  const awayColor = getTeamColor(away_team);

  return (
    <div className="group relative overflow-hidden rounded-lg border border-gray-200 bg-white transition-shadow hover:shadow-md dark:border-gray-800 dark:bg-gray-900">
      {/* Top color accent */}
      <div className="flex h-1.5">
        <div className="w-1/2" style={{ backgroundColor: awayColor }} />
        <div className="w-1/2" style={{ backgroundColor: homeColor }} />
      </div>

      <div className="p-4">
        {/* Matchup header */}
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white">
            <span style={{ color: awayColor }}>{away_team}</span>
            <span className="mx-2 text-gray-400">@</span>
            <span style={{ color: homeColor }}>{home_team}</span>
          </h3>
          {confidenceBadge(confidence_tier)}
        </div>

        {/* Picks */}
        <div className="mt-4 grid grid-cols-2 gap-3">
          {/* Spread pick */}
          <div className="rounded-md bg-gray-50 p-2.5 dark:bg-gray-800/60">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Spread Pick
            </p>
            <p className="mt-0.5 text-sm font-semibold text-gray-900 dark:text-white">
              {ats_pick}
            </p>
            <p className={`mt-0.5 text-xs font-medium ${edgeColor(spread_edge)}`}>
              Edge: {formatEdge(spread_edge)}
            </p>
          </div>

          {/* O/U pick */}
          <div className="rounded-md bg-gray-50 p-2.5 dark:bg-gray-800/60">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              O/U Pick
            </p>
            <p className="mt-0.5 text-sm font-semibold text-gray-900 dark:text-white">
              {ou_pick}
            </p>
            <p className={`mt-0.5 text-xs font-medium ${edgeColor(total_edge)}`}>
              Edge: {formatEdge(total_edge)}
            </p>
          </div>
        </div>

        {/* Edge bar */}
        <EdgeBar edge={spread_edge} />

        {/* Vegas comparison */}
        <div className="mt-3 space-y-1 text-xs text-gray-500 dark:text-gray-400">
          <div className="flex justify-between">
            <span>Spread</span>
            <span>
              Model: {formatSpread(predicted_spread)} | Vegas:{" "}
              {vegas_spread !== null ? formatSpread(vegas_spread) : "N/A"} |{" "}
              <span className={edgeColor(spread_edge)}>
                Edge: {formatEdge(spread_edge)}
              </span>
            </span>
          </div>
          <div className="flex justify-between">
            <span>Total</span>
            <span>
              Model: {predicted_total.toFixed(1)} | Vegas:{" "}
              {vegas_total !== null ? vegas_total.toFixed(1) : "N/A"} |{" "}
              <span className={edgeColor(total_edge)}>
                Edge: {formatEdge(total_edge)}
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
