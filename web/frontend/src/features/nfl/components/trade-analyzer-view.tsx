'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchRosRankings, evaluateTrade } from '@/lib/nfl/api';
import type { RosPlayer, TradeResponse } from '@/lib/nfl/types';
import { currentWeekQueryOptions } from '../api/queries';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import { FadeIn } from '@/lib/motion-primitives';
import { toolSeason } from '@/lib/nfl/season';

/** Autocomplete picker over the ROS player pool (client-side filter). */
export function RosPlayerPicker({
  pool,
  exclude,
  onPick,
  placeholder
}: {
  pool: RosPlayer[];
  exclude: Set<string>;
  onPick: (p: RosPlayer) => void;
  placeholder: string;
}) {
  const [q, setQ] = useState('');
  const hits = useMemo(() => {
    if (q.length < 2) return [];
    const needle = q.toLowerCase();
    return pool
      .filter(
        (p) =>
          !exclude.has(p.player_id) &&
          p.player_name.toLowerCase().includes(needle)
      )
      .slice(0, 6);
  }, [q, pool, exclude]);

  return (
    <div className='relative'>
      <Input
        placeholder={placeholder}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className='h-9'
      />
      {hits.length > 0 && (
        <div className='bg-popover absolute z-10 mt-1 w-full rounded-md border shadow-md'>
          {hits.map((p) => (
            <button
              key={p.player_id}
              type='button'
              className='hover:bg-accent flex w-full items-center justify-between px-3 py-2 text-left text-sm'
              onClick={() => {
                onPick(p);
                setQ('');
              }}
            >
              <span>
                <Badge variant='outline' className='mr-2'>
                  {p.position}
                </Badge>
                {p.player_name}
                <span className='text-muted-foreground ml-2 text-xs'>
                  {p.team}
                </span>
              </span>
              <span className='text-muted-foreground text-xs'>
                {p.ros_points.toFixed(0)} ROS
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SideColumn({
  title,
  players,
  onRemove
}: {
  title: string;
  players: RosPlayer[];
  onRemove: (id: string) => void;
}) {
  const total = players.reduce((s, p) => s + p.ros_points, 0);
  return (
    <div className='space-y-2'>
      <div className='flex items-center justify-between'>
        <span className='text-sm font-medium'>{title}</span>
        <span className='text-muted-foreground text-xs'>
          {total.toFixed(1)} ROS pts
        </span>
      </div>
      {players.map((p) => (
        <div
          key={p.player_id}
          className='flex items-center justify-between rounded-md border px-3 py-2 text-sm'
        >
          <span>
            <Badge variant='outline' className='mr-2'>
              {p.position}
            </Badge>
            {p.player_name}
            <span className='text-muted-foreground ml-2 text-xs'>{p.team}</span>
          </span>
          <span className='flex items-center gap-2'>
            <span className='font-mono text-xs'>{p.ros_points.toFixed(1)}</span>
            <button
              type='button'
              aria-label={`Remove ${p.player_name}`}
              onClick={() => onRemove(p.player_id)}
              className='text-muted-foreground hover:text-foreground'
            >
              <Icons.close className='h-4 w-4' />
            </button>
          </span>
        </div>
      ))}
    </div>
  );
}

export function TradeAnalyzerView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = toolSeason(cw?.season);

  const { data: ros, isLoading } = useQuery({
    queryKey: ['nfl', 'ros', season],
    queryFn: () => fetchRosRankings(season),
    staleTime: 60 * 60 * 1000
  });

  const [give, setGive] = useState<RosPlayer[]>([]);
  const [get, setGet] = useState<RosPlayer[]>([]);
  const [result, setResult] = useState<TradeResponse | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const excluded = useMemo(
    () => new Set([...give, ...get].map((p) => p.player_id)),
    [give, get]
  );

  const pool = ros?.players ?? [];

  async function onEvaluate() {
    setEvaluating(true);
    setError(null);
    try {
      const res = await evaluateTrade({
        side_a: give.map((p) => p.player_id),
        side_b: get.map((p) => p.player_id),
        season
      });
      setResult(res);
    } catch {
      setError('Trade evaluation failed — try again shortly.');
    } finally {
      setEvaluating(false);
    }
  }

  const verdictTone =
    result == null
      ? ''
      : result.fairness_pct < 5
        ? 'text-muted-foreground'
        : result.delta_ros_points > 0
          ? 'text-emerald-500'
          : 'text-red-500';

  return (
    <FadeIn className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>
            Rest-of-season trade evaluator
          </CardTitle>
        </CardHeader>
        <CardContent className='space-y-4'>
          {isLoading ? (
            <div className='flex justify-center py-8'>
              <Icons.spinner className='text-muted-foreground h-6 w-6 animate-spin' />
            </div>
          ) : (
            <>
              <div className='grid gap-4 md:grid-cols-2'>
                <div className='space-y-2'>
                  <RosPlayerPicker
                    pool={pool}
                    exclude={excluded}
                    onPick={(p) => setGive((s) => [...s, p])}
                    placeholder='Add a player you give away...'
                  />
                  <SideColumn
                    title='You give'
                    players={give}
                    onRemove={(id) =>
                      setGive((s) => s.filter((p) => p.player_id !== id))
                    }
                  />
                </div>
                <div className='space-y-2'>
                  <RosPlayerPicker
                    pool={pool}
                    exclude={excluded}
                    onPick={(p) => setGet((s) => [...s, p])}
                    placeholder='Add a player you receive...'
                  />
                  <SideColumn
                    title='You receive'
                    players={get}
                    onRemove={(id) =>
                      setGet((s) => s.filter((p) => p.player_id !== id))
                    }
                  />
                </div>
              </div>
              <Button
                onClick={onEvaluate}
                disabled={give.length === 0 || get.length === 0 || evaluating}
              >
                {evaluating ? 'Evaluating...' : 'Evaluate trade'}
              </Button>
              {error && <p className='text-sm text-red-500'>{error}</p>}
              {result && (
                <div className='space-y-1 rounded-md border p-4'>
                  <p className={`text-sm font-medium ${verdictTone}`}>
                    {result.verdict}
                  </p>
                  <p className='text-muted-foreground text-xs'>
                    Net {result.delta_ros_points > 0 ? '+' : ''}
                    {result.delta_ros_points.toFixed(1)} rest-of-season points
                    from week {result.from_week} · value gap{' '}
                    {result.fairness_pct.toFixed(1)}% ·{' '}
                    {result.scoring_format.replace('_', '-')} scoring
                  </p>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </FadeIn>
  );
}
