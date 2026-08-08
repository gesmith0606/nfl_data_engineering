'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { currentWeekQueryOptions } from '../api/queries';
import { fetchProjections } from '@/lib/nfl/api';
import {
  loadWatchlist,
  toggleWatched,
  type WatchedPlayer
} from '@/lib/nfl/watchlist';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import { toolSeason } from '@/lib/nfl/season';

/** Starred players with this week's projection. Lives on the Players page. */
export function WatchlistPanel() {
  const [watched, setWatched] = useState<WatchedPlayer[]>([]);
  useEffect(() => setWatchedSafe(), []);
  function setWatchedSafe() {
    setWatched(loadWatchlist());
  }

  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = toolSeason(cw?.season);
  const week = cw?.week ?? 1;

  const { data: slate } = useQuery({
    queryKey: ['nfl', 'projections', season, week, 'half_ppr', 'watchlist'],
    queryFn: () => fetchProjections(season, week, 'half_ppr'),
    enabled: watched.length > 0,
    retry: false,
    staleTime: 30 * 60 * 1000
  });

  const projById = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of slate?.projections ?? []) {
      m.set(p.player_id, p.projected_points);
    }
    return m;
  }, [slate]);

  if (watched.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>
          Watchlist{' '}
          <span className='text-muted-foreground text-xs font-normal'>
            starred players · latest projections
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className='grid gap-2 md:grid-cols-2 lg:grid-cols-3'>
          {watched.map((p) => (
            <div
              key={p.player_id}
              className='flex items-center justify-between rounded-md border px-3 py-2 text-sm'
            >
              <Link
                href={`/dashboard/players/${p.player_id}`}
                className='hover:underline'
              >
                <Badge variant='outline' className='mr-2'>
                  {p.position}
                </Badge>
                {p.player_name}
                <span className='text-muted-foreground ml-1 text-xs'>
                  {p.team}
                </span>
              </Link>
              <span className='flex items-center gap-2'>
                <span className='font-mono text-xs'>
                  {projById.get(p.player_id)?.toFixed(1) ?? '—'}
                </span>
                <button
                  type='button'
                  aria-label={`Remove ${p.player_name} from watchlist`}
                  onClick={() => {
                    toggleWatched(p);
                    setWatchedSafe();
                  }}
                  className='text-muted-foreground hover:text-foreground'
                >
                  <Icons.close className='h-4 w-4' />
                </button>
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/** Star toggle button for search results / detail pages. */
export function WatchStar({ player }: { player: WatchedPlayer }) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    setOn(loadWatchlist().some((p) => p.player_id === player.player_id));
  }, [player.player_id]);
  return (
    <button
      type='button'
      aria-label={on ? 'Remove from watchlist' : 'Add to watchlist'}
      aria-pressed={on}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        const updated = toggleWatched(player);
        setOn(updated.some((p) => p.player_id === player.player_id));
      }}
      className={
        on
          ? 'text-amber-400 hover:text-amber-500'
          : 'text-muted-foreground hover:text-foreground'
      }
    >
      <Icons.sparkles className='h-4 w-4' />
    </button>
  );
}
