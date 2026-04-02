"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import PredictionCard from "./PredictionCard";
import ConfidenceFilter, { type ConfidenceTier } from "./ConfidenceFilter";
import { fetchPredictions, ApiError } from "@/lib/api";
import type { GamePrediction } from "@/lib/types";

type SortKey = "confidence" | "spread_edge" | "total_edge";

interface PredictionsViewProps {
  initialPredictions: GamePrediction[];
  initialSeason: number;
  initialWeek: number;
}

const SEASONS = Array.from({ length: 7 }, (_, i) => 2020 + i);
const WEEKS = Array.from({ length: 18 }, (_, i) => i + 1);

const CONFIDENCE_ORDER: Record<string, number> = {
  HIGH: 0,
  MEDIUM: 1,
  LOW: 2,
};

function sortPredictions(
  predictions: GamePrediction[],
  sortKey: SortKey,
): GamePrediction[] {
  return [...predictions].sort((a, b) => {
    if (sortKey === "confidence") {
      const aOrder = CONFIDENCE_ORDER[a.confidence_tier.toUpperCase()] ?? 3;
      const bOrder = CONFIDENCE_ORDER[b.confidence_tier.toUpperCase()] ?? 3;
      if (aOrder !== bOrder) return aOrder - bOrder;
      // Within same tier, sort by spread edge magnitude descending
      return Math.abs(b.spread_edge ?? 0) - Math.abs(a.spread_edge ?? 0);
    }
    if (sortKey === "spread_edge") {
      return Math.abs(b.spread_edge ?? 0) - Math.abs(a.spread_edge ?? 0);
    }
    // total_edge
    return Math.abs(b.total_edge ?? 0) - Math.abs(a.total_edge ?? 0);
  });
}

export default function PredictionsView({
  initialPredictions,
  initialSeason,
  initialWeek,
}: PredictionsViewProps) {
  const [predictions, setPredictions] =
    useState<GamePrediction[]>(initialPredictions);
  const [season, setSeason] = useState(initialSeason);
  const [week, setWeek] = useState(initialWeek);
  const [confidenceFilter, setConfidenceFilter] =
    useState<ConfidenceTier>("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("confidence");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async (s: number, w: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchPredictions(s, w);
      setPredictions(data.predictions);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Failed to load predictions (${err.status})`);
      } else {
        setError("Unable to connect to the backend. Is the API running?");
      }
      setPredictions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (season === initialSeason && week === initialWeek) {
      return;
    }
    refetch(season, week);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, week]);

  const filtered = useMemo(() => {
    let result = predictions;
    if (confidenceFilter !== "ALL") {
      result = result.filter(
        (p) => p.confidence_tier.toUpperCase() === confidenceFilter,
      );
    }
    return sortPredictions(result, sortKey);
  }, [predictions, confidenceFilter, sortKey]);

  // Summary stats
  const totalGames = predictions.length;
  const highConfidence = predictions.filter(
    (p) => p.confidence_tier.toUpperCase() === "HIGH",
  ).length;

  return (
    <div className="space-y-6">
      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Season selector */}
        <select
          value={season}
          onChange={(e) => setSeason(Number(e.target.value))}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
        >
          {SEASONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        {/* Week selector */}
        <select
          value={week}
          onChange={(e) => setWeek(Number(e.target.value))}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
        >
          {WEEKS.map((w) => (
            <option key={w} value={w}>
              Week {w}
            </option>
          ))}
        </select>

        {/* Sort selector */}
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
        >
          <option value="confidence">Sort: Confidence</option>
          <option value="spread_edge">Sort: Spread Edge</option>
          <option value="total_edge">Sort: Total Edge</option>
        </select>
      </div>

      {/* Confidence filter chips */}
      <ConfidenceFilter value={confidenceFilter} onChange={setConfidenceFilter} />

      {/* Summary stats */}
      {!isLoading && !error && predictions.length > 0 && (
        <div className="flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
          <span>
            <span className="font-semibold text-gray-900 dark:text-white">
              {totalGames}
            </span>{" "}
            game{totalGames !== 1 ? "s" : ""}
          </span>
          <span>
            <span className="font-semibold text-green-600 dark:text-green-400">
              {highConfidence}
            </span>{" "}
            high-confidence pick{highConfidence !== 1 ? "s" : ""}
          </span>
        </div>
      )}

      {/* Loading / Error / Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
            >
              <div className="flex h-1.5">
                <div className="w-1/2 animate-pulse bg-gray-200 dark:bg-gray-700" />
                <div className="w-1/2 animate-pulse bg-gray-300 dark:bg-gray-600" />
              </div>
              <div className="space-y-3 p-4">
                <div className="flex items-center justify-between">
                  <div className="h-5 w-28 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
                  <div className="h-5 w-16 animate-pulse rounded-full bg-gray-200 dark:bg-gray-700" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="h-20 animate-pulse rounded-md bg-gray-100 dark:bg-gray-800/60" />
                  <div className="h-20 animate-pulse rounded-md bg-gray-100 dark:bg-gray-800/60" />
                </div>
                <div className="h-1.5 animate-pulse rounded-full bg-gray-200 dark:bg-gray-700" />
                <div className="space-y-1">
                  <div className="h-3 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
                  <div className="h-3 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-8 text-center dark:border-red-800 dark:bg-red-900/20">
          <svg
            className="mx-auto h-10 w-10 text-red-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
            />
          </svg>
          <p className="mt-3 text-sm font-medium text-red-700 dark:text-red-400">
            {error}
          </p>
          <button
            onClick={() => refetch(season, week)}
            className="mt-4 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700"
          >
            Try Again
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-12 text-center dark:border-gray-800 dark:bg-gray-900">
          <p className="text-lg font-medium text-gray-500 dark:text-gray-400">
            No predictions available
          </p>
          <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">
            {predictions.length === 0
              ? "No game predictions found for this season and week."
              : "No games match the selected confidence filter."}
          </p>
        </div>
      ) : (
        <>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            Showing {filtered.length} of {predictions.length} game
            {predictions.length !== 1 ? "s" : ""}
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filtered.map((prediction) => (
              <PredictionCard
                key={prediction.game_id}
                prediction={prediction}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
