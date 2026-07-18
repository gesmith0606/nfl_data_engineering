'use client';

import { useQuery } from '@tanstack/react-query';
import { fetchAlertsBundle } from './service';

export const alertKeys = {
  all: ['alerts'] as const,
  bundle: () => [...alertKeys.all, 'bundle'] as const
};

/**
 * The alerts bundle behind the nav bell. Plain `useQuery` (not suspense) —
 * the nav must render instantly; the bell shows no badge until data lands.
 * The queryFn reads localStorage so it only runs client-side (post-mount),
 * which useQuery guarantees.
 */
export function useAlertsBundle() {
  return useQuery({
    queryKey: alertKeys.bundle(),
    queryFn: fetchAlertsBundle,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
    retry: 1
  });
}
