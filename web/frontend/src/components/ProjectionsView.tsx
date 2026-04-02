"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import ProjectionTable from "./ProjectionTable";
import ScoringToggle from "./ScoringToggle";
import PositionFilter from "./PositionFilter";
import TeamFilter from "./TeamFilter";
import SearchBar from "./SearchBar";
import { fetchProjections, ApiError } from "@/lib/api";
import type {
  PlayerProjection,
  ScoringFormat,
  Position,
} from "@/lib/types";

interface ProjectionsViewProps {
  initialProjections: PlayerProjection[];
  initialSeason: number;
  initialWeek: number;
  initialScoring: ScoringFormat;
}

const SEASONS = Array.from({ length: 7 }, (_, i) => 2020 + i);
const WEEKS = Array.from({ length: 18 }, (_, i) => i + 1);

export default function ProjectionsView({
  initialProjections,
  initialSeason,
  initialWeek,
  initialScoring,
}: ProjectionsViewProps) {
  const [projections, setProjections] =
    useState<PlayerProjection[]>(initialProjections);
  const [season, setSeason] = useState(initialSeason);
  const [week, setWeek] = useState(initialWeek);
  const [scoring, setScoring] = useState<ScoringFormat>(initialScoring);
  const [position, setPosition] = useState<Position>("ALL");
  const [team, setTeam] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(
    async (s: number, w: number, sc: ScoringFormat) => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await fetchProjections(s, w, sc);
        setProjections(data.projections);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(`Failed to load projections (${err.status})`);
        } else {
          setError("Unable to connect to the backend. Is the API running?");
        }
        setProjections([]);
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    // Skip refetch for the initial server-provided values
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

  // Client-side filtering (position / team) -- no API round-trip needed
  const filtered = useMemo(() => {
    let result = projections;
    if (position !== "ALL") {
      result = result.filter((p) => p.position === position);
    }
    if (team) {
      result = result.filter((p) => p.team === team);
    }
    return result;
  }, [projections, position, team]);

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="flex min-w-0 flex-wrap items-center gap-3 sm:gap-4">
        {/* Season selector */}
        <select
          value={season}
          onChange={(e) => setSeason(Number(e.target.value))}
          className="min-h-[44px] rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white sm:min-h-0"
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
          className="min-h-[44px] rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white sm:min-h-0"
        >
          <option value={0}>Preseason</option>
          {WEEKS.map((w) => (
            <option key={w} value={w}>
              Week {w}
            </option>
          ))}
        </select>

        {/* Scoring toggle */}
        <ScoringToggle value={scoring} onChange={setScoring} />

        {/* Team filter */}
        <TeamFilter value={team} onChange={setTeam} />

        {/* Search */}
        <div className="ml-auto">
          <SearchBar />
        </div>
      </div>

      {/* Position filter chips */}
      <PositionFilter value={position} onChange={setPosition} />

      {/* Loading / Error / Table */}
      {isLoading ? (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          <div className="bg-gray-50 px-3 py-3 dark:bg-gray-800/50">
            <div className="h-4 w-full animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
          </div>
          {Array.from({ length: 10 }).map((_, i) => (
            <div
              key={i}
              className="flex items-center gap-4 border-t border-gray-100 px-3 py-3 dark:border-gray-800/50"
            >
              <div className="h-4 w-8 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <div className="h-4 w-32 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <div className="h-4 w-10 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <div className="h-4 w-10 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <div className="ml-auto h-4 w-12 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <div className="h-4 w-12 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
              <div className="h-4 w-12 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
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
            onClick={() => refetch(season, week, scoring)}
            className="mt-4 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700"
          >
            Try Again
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-12 text-center dark:border-gray-800 dark:bg-gray-900">
          <svg
            className="mx-auto h-12 w-12 text-gray-300 dark:text-gray-600"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z"
            />
          </svg>
          <p className="mt-4 text-lg font-medium text-gray-500 dark:text-gray-400">
            No data available for this week
          </p>
          <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">
            Projections may not have been generated yet for {season} Week{" "}
            {week === 0 ? "Preseason" : week}. Try a different season or week.
          </p>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {filtered.length} player{filtered.length !== 1 ? "s" : ""}
            </p>
          </div>
          <ProjectionTable projections={filtered} />
        </>
      )}
    </div>
  );
}
