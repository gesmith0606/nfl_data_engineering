"use client";

import { useState, useCallback } from "react";
import TeamSelector from "./TeamSelector";
import FieldView from "./FieldView";
import ScoringToggle from "./ScoringToggle";
import { fetchLineup, ApiError } from "@/lib/api";
import type { TeamLineup, ScoringFormat } from "@/lib/types";

interface LineupViewProps {
  initialSeason: number;
  initialWeek: number;
  initialScoring: ScoringFormat;
}

const SEASONS = Array.from({ length: 7 }, (_, i) => 2020 + i);
const WEEKS = Array.from({ length: 18 }, (_, i) => i + 1);

export default function LineupView({
  initialSeason,
  initialWeek,
  initialScoring,
}: LineupViewProps) {
  const [season, setSeason] = useState(initialSeason);
  const [week, setWeek] = useState(initialWeek);
  const [scoring, setScoring] = useState<ScoringFormat>(initialScoring);
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [lineup, setLineup] = useState<TeamLineup | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLineup = useCallback(
    async (team: string, s: number, w: number) => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await fetchLineup(s, w, team);
        setLineup(data);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(`Failed to load lineup (${err.status})`);
        } else {
          setError("Unable to connect to the backend. Is the API running?");
        }
        setLineup(null);
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const handleSelectTeam = (team: string) => {
    setSelectedTeam(team);
    void loadLineup(team, season, week);
  };

  const handleSeasonChange = (newSeason: number) => {
    setSeason(newSeason);
    if (selectedTeam) {
      void loadLineup(selectedTeam, newSeason, week);
    }
  };

  const handleWeekChange = (newWeek: number) => {
    setWeek(newWeek);
    if (selectedTeam) {
      void loadLineup(selectedTeam, season, newWeek);
    }
  };

  const handleScoringChange = (newScoring: ScoringFormat) => {
    setScoring(newScoring);
    // Scoring affects projections; re-fetch if team is selected
    if (selectedTeam) {
      void loadLineup(selectedTeam, season, week);
    }
  };

  const handleBack = () => {
    setSelectedTeam(null);
    setLineup(null);
    setError(null);
  };

  return (
    <div className="space-y-6">
      {/* Controls bar */}
      <div className="flex flex-wrap items-center gap-4">
        {selectedTeam && (
          <button
            onClick={handleBack}
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
            All Teams
          </button>
        )}

        <div className="flex items-center gap-2">
          <label htmlFor="lineup-season" className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Season
          </label>
          <select
            id="lineup-season"
            value={season}
            onChange={(e) => handleSeasonChange(Number(e.target.value))}
            className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          >
            {SEASONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="lineup-week" className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Week
          </label>
          <select
            id="lineup-week"
            value={week}
            onChange={(e) => handleWeekChange(Number(e.target.value))}
            className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white"
          >
            {WEEKS.map((w) => (
              <option key={w} value={w}>
                Week {w}
              </option>
            ))}
          </select>
        </div>

        <ScoringToggle value={scoring} onChange={handleScoringChange} />
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="animate-pulse">
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: "linear-gradient(to bottom, #2d5a27, #1a3a17)" }}
          >
            <div className="p-6 space-y-6">
              <div className="h-10 w-32 rounded-lg bg-white/10" />
              {/* Skeleton rows mimicking field layout */}
              <div className="grid grid-cols-3 gap-4">
                <div className="h-20 rounded-lg bg-white/10" />
                <div className="h-20 rounded-lg bg-white/10" />
                <div className="h-20 rounded-lg bg-white/10" />
              </div>
              <div className="flex justify-center">
                <div className="h-20 w-32 rounded-lg bg-white/10" />
              </div>
              <div className="flex justify-center">
                <div className="h-20 w-32 rounded-lg bg-white/10" />
              </div>
              <div className="flex justify-center">
                <div className="h-20 w-32 rounded-lg bg-white/10" />
              </div>
              <div className="flex justify-center">
                <div className="h-16 w-24 rounded-lg bg-white/10" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main content */}
      {!isLoading && !selectedTeam && (
        <TeamSelector selectedTeam={selectedTeam} onSelectTeam={handleSelectTeam} />
      )}

      {!isLoading && selectedTeam && lineup && (
        <FieldView lineup={lineup} />
      )}

      {!isLoading && selectedTeam && !lineup && !error && (
        <div className="py-12 text-center text-gray-500 dark:text-gray-400">
          No lineup data available for {selectedTeam} in Week {week}, {season}.
        </div>
      )}
    </div>
  );
}
