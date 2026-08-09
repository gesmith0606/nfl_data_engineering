'use client';

import { useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchRosRankings, evaluateTrade } from '@/lib/nfl/api';
import type { RosPlayer, TradeResponse, TradeSide } from '@/lib/nfl/types';
import { currentWeekQueryOptions } from '../api/queries';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import { FadeIn } from '@/lib/motion-primitives';
import { toolSeason } from '@/lib/nfl/season';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';

const GIVE_COLOR = 'var(--wc-peri,#5b67c7)';
const RECEIVE_COLOR = 'var(--wc-mint,#91edd0)';

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

/** Editable side panel (picker input state) — broadcast identity via
 *  BroadcastPanel with a give/receive-colored rail and condensed caps
 *  header. */
function SideColumn({
  title,
  players,
  onRemove,
  railColor
}: {
  title: string;
  players: RosPlayer[];
  onRemove: (id: string) => void;
  railColor: string;
}) {
  const total = players.reduce((s, p) => s + p.ros_points, 0);
  return (
    <BroadcastPanel railColor={railColor} className='space-y-[var(--space-2)] p-[var(--space-4)]'>
      <div className='flex items-center justify-between'>
        <span className='wc-display text-[length:var(--fs-sm)] font-semibold tracking-[0.12em] text-white'>
          {title}
        </span>
        <span className='font-mono text-[length:var(--fs-xs)] text-white/50'>
          {total.toFixed(1)} ROS pts
        </span>
      </div>
      {players.length === 0 && (
        <p className='text-[length:var(--fs-xs)] text-white/40'>No players added yet.</p>
      )}
      {players.map((p) => (
        <div
          key={p.player_id}
          className='flex items-center justify-between rounded-md border border-white/10 px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--fs-sm)] text-white'
        >
          <span>
            <Badge variant='outline' className='mr-2'>
              {p.position}
            </Badge>
            {p.player_name}
            <span className='ml-2 text-xs text-white/50'>{p.team}</span>
          </span>
          <span className='flex items-center gap-2'>
            <span className='font-mono text-xs'>{p.ros_points.toFixed(1)}</span>
            <button
              type='button'
              aria-label={`Remove ${p.player_name}`}
              onClick={() => onRemove(p.player_id)}
              className='text-white/50 hover:text-white'
            >
              <Icons.close className='h-4 w-4' />
            </button>
          </span>
        </div>
      ))}
    </BroadcastPanel>
  );
}

/** Give/receive totals on a shared 0-baseline scale, so the two bar lengths
 *  are directly comparable rather than independently normalized. */
function TotalCompareBar({ giveTotal, getTotal }: { giveTotal: number; getTotal: number }) {
  const max = Math.max(giveTotal, getTotal, 1);
  const rows = [
    { label: 'You give', value: giveTotal, color: GIVE_COLOR },
    { label: 'You receive', value: getTotal, color: RECEIVE_COLOR }
  ];
  return (
    <div className='space-y-[var(--space-2)]'>
      {rows.map((row) => (
        <div key={row.label} className='flex items-center gap-[var(--space-3)]'>
          <span className='wc-display w-24 shrink-0 text-[length:var(--fs-xs)] tracking-[0.1em] text-white/60'>
            {row.label}
          </span>
          <div className='h-2.5 flex-1 overflow-hidden rounded-full bg-white/10'>
            <div
              className='h-full rounded-full'
              style={{ width: `${(row.value / max) * 100}%`, background: row.color }}
            />
          </div>
          <span className='w-16 shrink-0 text-right font-mono text-[length:var(--fs-sm)] text-white'>
            {row.value.toFixed(1)}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Per-player value contributions for one side of the graded trade — shows
 *  which players actually moved the needle, sourced entirely from the
 *  /api/tools/trade response's echoed side (`TradeSide.players`), not the
 *  local picker state. Exported for direct unit testing. */
export function ValueBreakdown({
  side,
  label,
  accent
}: {
  side: TradeSide;
  label: string;
  accent: string;
}) {
  const total = side.total_ros_points;
  return (
    <div className='space-y-[var(--space-2)]'>
      <div className='flex items-center justify-between text-[length:var(--fs-xs)]'>
        <span className='wc-display tracking-[0.12em] text-white/60'>{label}</span>
        <span className='font-mono text-white'>{total.toFixed(1)} pts</span>
      </div>
      {side.players.map((p) => {
        const pct = total > 0 ? (p.ros_points / total) * 100 : 0;
        return (
          <div key={p.player_id} className='flex items-center gap-[var(--space-2)] text-[length:var(--fs-xs)]'>
            <span className='w-24 shrink-0 truncate text-white/70'>{p.player_name}</span>
            <div className='h-1.5 flex-1 overflow-hidden rounded-full bg-white/10'>
              <div
                className='h-full rounded-full'
                style={{ width: `${pct}%`, background: accent }}
              />
            </div>
            <span className='w-12 shrink-0 text-right font-mono text-white'>
              {p.ros_points.toFixed(1)}
            </span>
          </div>
        );
      })}
      {side.unmatched_player_ids.length > 0 && (
        <p className='text-[length:var(--fs-xs)] text-amber-400'>
          {side.unmatched_player_ids.length} player id(s) couldn&apos;t be resolved
          and were excluded from this total.
        </p>
      )}
    </div>
  );
}

export function TradeAnalyzerView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = toolSeason(cw?.season);

  const { data: ros, isLoading } = useQuery({
    queryKey: ['nfl', 'ros', season],
    queryFn: () => fetchRosRankings(season),
    staleTime: 60 * 60 * 1000,
    // The season key settles only after the current-week query resolves;
    // without this, the re-key flips isLoading back on and unmounts the
    // form mid-interaction (wiping picker input).
    placeholderData: keepPreviousData
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

  const verdictColor =
    result == null
      ? 'rgba(255,255,255,0.5)'
      : result.fairness_pct < 5
        ? 'rgba(255,255,255,0.5)'
        : result.delta_ros_points > 0
          ? RECEIVE_COLOR
          : '#f87171';

  return (
    <FadeIn className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>
            Rest-of-season trade evaluator
          </CardTitle>
        </CardHeader>
      </Card>

      {isLoading ? (
        <div className='flex justify-center py-8'>
          <Icons.spinner className='text-muted-foreground h-6 w-6 animate-spin' />
        </div>
      ) : (
        <div className='space-y-4'>
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
                railColor={GIVE_COLOR}
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
                railColor={RECEIVE_COLOR}
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
            <BroadcastPanel className='space-y-[var(--space-4)] p-[var(--space-4)]'>
              <div>
                <div
                  className='wc-display text-[length:var(--fs-xs)] tracking-[0.14em]'
                  style={{ color: 'var(--wc-yellow,#ffd84d)' }}
                >
                  Verdict
                </div>
                <p
                  className='wc-display mt-[var(--space-1)] text-[length:var(--fs-h2)] font-extrabold'
                  style={{ color: verdictColor }}
                >
                  {result.verdict}
                </p>
                <p className='mt-[var(--space-1)] text-[length:var(--fs-xs)] text-white/60'>
                  Net {result.delta_ros_points > 0 ? '+' : ''}
                  {result.delta_ros_points.toFixed(1)} rest-of-season points
                  from week {result.from_week} · value gap{' '}
                  {result.fairness_pct.toFixed(1)}% ·{' '}
                  {result.scoring_format.replace('_', '-')} scoring
                </p>
              </div>

              <TotalCompareBar
                giveTotal={result.side_a.total_ros_points}
                getTotal={result.side_b.total_ros_points}
              />

              <div className='grid gap-[var(--space-4)] sm:grid-cols-2'>
                <ValueBreakdown side={result.side_a} label='You give' accent={GIVE_COLOR} />
                <ValueBreakdown side={result.side_b} label='You receive' accent={RECEIVE_COLOR} />
              </div>
            </BroadcastPanel>
          )}
        </div>
      )}
    </FadeIn>
  );
}
