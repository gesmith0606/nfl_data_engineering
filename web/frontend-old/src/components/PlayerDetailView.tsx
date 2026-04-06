"use client";

import { useState, useEffect, useCallback } from "react";
import PlayerHeader from "./PlayerHeader";
import ProjectionBreakdown from "./ProjectionBreakdown";
import MatchupContext from "./MatchupContext";
import ScoringToggle from "./ScoringToggle";
import { fetchPlayer, ApiError } from "@/lib/api";
import type { PlayerProjection, ScoringFormat } from "@/lib/types";

const SEASONS = Array.from({ length: 7 }, (_, i) => 2020 + i);
const WEEKS = Array.from({ length: 18 }, (_, i) => i + 1);

interface PlayerDetailViewProps {
  playerId: string;
  initialPlayer: PlayerProjection | null;
  initialSeason: number;
  initialWeek: number;
  initialScoring: ScoringFormat;
}

export default function PlayerDetailView({
  playerId,
  initialPlayer,
  initialSeason,
  initialWeek,
  initialScoring,
}: PlayerDetailViewProps) {
  const [player, setPlayer] = useState<PlayerProjection | null>(initialPlayer);
  const [season, setSeason] = useState(initialSeason);
  const [week, setWeek] = useState(initialWeek);
  const [scoring, setScoring] = useState<ScoringFormat>(initialScoring);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(
    async (s: number, w: number, sc: ScoringFormat) => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await fetchPlayer(playerId, s, w, sc);
        setPlayer(data);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setError("Player not found for the selected season/week.");
        } else if (err instanceof ApiError) {
          setError(`Failed to load player data (${err.status})`);
        } else {
          setError("Unable to connect to the backend. Is the API running?");
        }
        setPlayer(null);
      } finally {
        setIsLoading(false);
      }
    },
    [playerId],
  );

  useEffect(() => {
    if (
      season === initialSeason &&
      week === initialWeek &&
      scoring === initialScoring
    ) {
      return;
    }
    refetch(season, week, scoring);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, week, scoring]);

  function handlePrevWeek() {
    if (week > 0) {
      setWeek((prev) => prev - 1);
    }
  }

  function handleNextWeek() {
    if (week < 18) {
      setWeek((prev) => prev + 1);
    }
  }

  return (
    <div className="space-y-6">
      {/* Back link */}
      <a
        href="/"
        className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
      >
        <svg
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={2}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15.75 19.5L8.25 12l7.5-7.5"
          />
        </svg>
        Back to Projections
      </a>

      {/* Controls */}
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

        {/* Week navigation */}
        <div className="flex items-center gap-2">
          <button
            onClick={handlePrevWeek}
            disabled={week <= 0}
            className="rounded-md border border-gray-300 p-2 text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
            aria-label="Previous week"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15.75 19.5L8.25 12l7.5-7.5"
              />
            </svg>
          </button>
          <select
            value={week}
            onChange={(e) => setWeek(Number(e.target.value))}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
          >
            <option value={0}>Preseason</option>
            {WEEKS.map((w) => (
              <option key={w} value={w}>
                Week {w}
              </option>
            ))}
          </select>
          <button
            onClick={handleNextWeek}
            disabled={week >= 18}
            className="rounded-md border border-gray-300 p-2 text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
            aria-label="Next week"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M8.25 4.5l7.5 7.5-7.5 7.5"
              />
            </svg>
          </button>
        </div>

        {/* Scoring toggle */}
        <ScoringToggle value={scoring} onChange={setScoring} />
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-6">
          {/* Skeleton header */}
          <div className="rounded-lg border-l-4 border-gray-300 bg-white p-6 shadow-sm dark:border-gray-600 dark:bg-gray-900">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 animate-pulse rounded-full bg-gray-200 dark:bg-gray-700" />
              <div className="space-y-2">
                <div className="h-7 w-48 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
                <div className="flex gap-2">
                  <div className="h-5 w-12 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
                  <div className="h-5 w-16 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
                </div>
              </div>
            </div>
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900">
                <div className="h-4 w-32 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
                <div className="mt-6 flex justify-center">
                  <div className="h-14 w-24 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
                </div>
                <div className="mt-6 h-4 w-full animate-pulse rounded-full bg-gray-200 dark:bg-gray-700" />
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900">
                <div className="h-4 w-32 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
                <div className="mt-4 grid grid-cols-3 gap-4">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div
                      key={i}
                      className="h-16 animate-pulse rounded-lg bg-gray-100 dark:bg-gray-800/50"
                    />
                  ))}
                </div>
              </div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900">
              <div className="h-4 w-24 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <div className="mt-4 space-y-4">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-10 animate-pulse rounded bg-gray-100 dark:bg-gray-800/50"
                  />
                ))}
              </div>
            </div>
          </div>
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
            onClick={() => refetch(season, week, scoring)}
            className="mt-4 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700"
          >
            Try Again
          </button>
        </div>
      ) : player ? (
        <div className="space-y-6">
          <PlayerHeader player={player} />
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <ProjectionBreakdown player={player} />
            </div>
            <div>
              <MatchupContext player={player} />
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-gray-200 bg-white p-12 text-center dark:border-gray-800 dark:bg-gray-900">
          <p className="text-lg font-medium text-gray-500 dark:text-gray-400">
            No projection data available
          </p>
          <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">
            Try selecting a different season, week, or scoring format.
          </p>
        </div>
      )}
    </div>
  );
}
