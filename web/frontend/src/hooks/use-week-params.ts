/**
 * Shared hook for resolving (season, week) URL params on data pages.
 *
 * Phase 66 / v7.0 HOTFIX-04 + HOTFIX-05: replaces the hardcoded
 * `useState(2024)` / `useState(1)` defaults on the predictions and lineups
 * pages so users land on the latest-played week instead of a stale/empty
 * slate.
 *
 * Behavior:
 *   - Binds season + week to URL query params via nuqs (bookmarkable,
 *     matches the rest of the codebase).
 *   - On mount, if either param is missing from the URL, fetches
 *     `/api/projections/latest-week` and sets the missing values.
 *   - Exposes `isResolving: boolean` so consumers can show a skeleton
 *     until resolution completes.
 *   - Preserves user selections — once the user explicitly picks a
 *     season or week, the URL carries that selection and the hook does
 *     NOT overwrite it with latest-week.
 *
 * The backend's graceful defaulting (phase 66-02) means the API will
 * return a well-shaped payload even when we fire the first request
 * before resolution completes. This hook is belt-and-braces: it gives
 * users a stable URL + visible freshness indicator while the API does
 * the heavy lifting.
 */
'use client';

import { useEffect, useMemo, useState } from 'react';
import { parseAsInteger, useQueryStates } from 'nuqs';

import {
  resolveDefaultWeek,
  resolvePredictionsLatestWeek,
} from '@/lib/week-context';

export type WeekParamsDataSource = 'projections' | 'predictions';

export interface UseWeekParamsOptions {
  /** Fallback season when latest-week resolution fails (e.g. backend down). */
  fallbackSeason?: number;
  /** Fallback week when latest-week returns null (offseason). */
  fallbackWeek?: number;
  /**
   * Which gold layer to query for the "latest week" default. Predictions
   * pages should pass `'predictions'` so they don't borrow projections'
   * latest-week (which can return a preseason wk1 with no game data).
   * Defaults to `'projections'` for back-compat.
   */
  dataSource?: WeekParamsDataSource;
}

export interface UseWeekParamsResult {
  season: number;
  week: number;
  setSeason: (value: number) => void;
  setWeek: (value: number) => void;
  isResolving: boolean;
  /** ISO timestamp of the underlying parquet, when known. */
  dataAsOf: string | null;
}

const DEFAULT_FALLBACK_SEASON = new Date().getFullYear();
const DEFAULT_FALLBACK_WEEK = 1;

export function useWeekParams(
  options: UseWeekParamsOptions = {}
): UseWeekParamsResult {
  const fallbackSeason = options.fallbackSeason ?? DEFAULT_FALLBACK_SEASON;
  const fallbackWeek = options.fallbackWeek ?? DEFAULT_FALLBACK_WEEK;

  const [{ season: seasonParam, week: weekParam }, setParams] = useQueryStates({
    season: parseAsInteger,
    week: parseAsInteger
  });

  const [isResolving, setIsResolving] = useState(
    seasonParam === null || weekParam === null
  );
  const [dataAsOf, setDataAsOf] = useState<string | null>(null);

  useEffect(() => {
    if (seasonParam !== null && weekParam !== null) {
      setIsResolving(false);
      return;
    }

    let cancelled = false;
    const probeSeason = seasonParam ?? fallbackSeason;
    const resolver =
      options.dataSource === 'predictions'
        ? resolvePredictionsLatestWeek
        : resolveDefaultWeek;

    // If the requested probe season has no data, walk back one season at a
    // time (max 3 hops) so the page still lands on a populated slice when
    // the current calendar year is offseason and brand-new.
    const tryResolve = async (): Promise<void> => {
      let trySeason = probeSeason;
      for (let hop = 0; hop < 3; hop++) {
        if (cancelled) return;
        const info = await resolver(trySeason);
        if (cancelled) return;
        if (info?.week != null) {
          setParams({
            season: seasonParam ?? info.season ?? trySeason,
            week: weekParam ?? info.week
          });
          setDataAsOf(info.data_as_of ?? null);
          setIsResolving(false);
          return;
        }
        trySeason -= 1;
      }
      // No data after walk-back — apply user-provided fallbacks.
      setParams({
        season: seasonParam ?? fallbackSeason,
        week: weekParam ?? fallbackWeek
      });
      setIsResolving(false);
    };

    tryResolve().catch(() => {
      if (cancelled) return;
      setParams({
        season: seasonParam ?? fallbackSeason,
        week: weekParam ?? fallbackWeek
      });
      setIsResolving(false);
    });

    return () => {
      cancelled = true;
    };
    // We deliberately depend only on the raw URL params; setParams and
    // options identities are stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seasonParam, weekParam]);

  const season = seasonParam ?? fallbackSeason;
  const week = weekParam ?? fallbackWeek;

  const setSeason = useMemo(
    () => (value: number) => {
      setParams({ season: value });
    },
    [setParams]
  );
  const setWeek = useMemo(
    () => (value: number) => {
      setParams({ week: value });
    },
    [setParams]
  );

  return {
    season,
    week,
    setSeason,
    setWeek,
    isResolving,
    dataAsOf
  };
}
