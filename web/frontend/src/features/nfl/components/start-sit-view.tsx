'use client';

import { useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchRosRankings, fetchStartSitCompare } from '@/lib/nfl/api';
import type { RosPlayer, ToolsComparePlayer } from '@/lib/nfl/types';
import { currentWeekQueryOptions } from '../api/queries';
import { RosPlayerPicker } from './trade-analyzer-view';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import { FadeIn } from '@/lib/motion-primitives';
import { toolSeason } from '@/lib/nfl/season';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';

/**
 * Confidence heuristic (market-gap redesign, 2026-08): how far the
 * recommended starter's projection leads the best of the rest, read as a
 * 50-95% band off `projected_points` only — the one number every compared
 * player already carries. A dead-even projection (gap = 0) reads as a 50%
 * toss-up; a gap worth 30%+ of the recommended player's own projection
 * saturates the read at 95% (never claim certainty). No hidden inputs, no
 * invented fields — just the existing projection gap turned into a percent.
 */
function deriveConfidence(players: ToolsComparePlayer[], recommendedId: string) {
  const rec = players.find((p) => p.player_id === recommendedId);
  const others = players.filter((p) => p.player_id !== recommendedId);
  if (!rec || others.length === 0) return null;
  const runnerUp = others.reduce((best, p) =>
    p.projected_points > best.projected_points ? p : best
  );
  const gap = rec.projected_points - runnerUp.projected_points;
  const gapPct = rec.projected_points > 0 ? gap / rec.projected_points : 0;
  const pct = Math.min(95, Math.max(50, 50 + gapPct * 150));
  return { pct, rec, runnerUp, gap };
}

/** The 2-4 concrete "why" factors — every one sourced from fields the
 *  /api/tools/compare payload already returns, skipped when a side is
 *  missing the data rather than guessed at. */
function buildWhyFactors(
  rec: ToolsComparePlayer,
  runnerUp: ToolsComparePlayer,
  gap: number
): { label: string; value: string }[] {
  const factors = [
    {
      label: 'Projection edge',
      value: `+${gap.toFixed(1)} pts vs ${runnerUp.player_name}`
    }
  ];
  if (rec.projected_floor != null && runnerUp.projected_floor != null) {
    factors.push({
      label: 'Floor (downside)',
      value: `${rec.projected_floor.toFixed(1)} vs ${runnerUp.projected_floor.toFixed(1)}`
    });
  }
  if (rec.projected_ceiling != null && runnerUp.projected_ceiling != null) {
    factors.push({
      label: 'Ceiling (upside)',
      value: `${rec.projected_ceiling.toFixed(1)} vs ${runnerUp.projected_ceiling.toFixed(1)}`
    });
  }
  if (rec.opp_rank_vs_position != null && runnerUp.opp_rank_vs_position != null) {
    factors.push({
      label: 'Matchup (opp rank)',
      value: `#${rec.opp_rank_vs_position} vs #${runnerUp.opp_rank_vs_position}`
    });
  }
  return factors;
}

/** Compact floor->ceiling range band, dot at the projection. All three
 *  players in a comparison share one min/max scale so the bars read as a
 *  single ruler rather than three independently-normalized ones. */
function RangeBand({
  floor,
  proj,
  ceiling,
  min,
  max
}: {
  floor: number | null;
  proj: number;
  ceiling: number | null;
  min: number;
  max: number;
}) {
  if (floor == null || ceiling == null || max <= min) {
    return <span className='text-muted-foreground text-xs'>—</span>;
  }
  const span = max - min;
  const left = ((floor - min) / span) * 100;
  const width = ((ceiling - floor) / span) * 100;
  const dot = ((proj - min) / span) * 100;
  return (
    <div className='flex flex-col items-end gap-1'>
      <div className='bg-muted relative h-1.5 w-full min-w-[100px] rounded-full'>
        <div
          className='absolute h-full rounded-full'
          style={{ left: `${left}%`, width: `${width}%`, background: 'rgba(145,237,208,0.4)' }}
        />
        <div
          className='absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full'
          style={{ left: `${dot}%`, background: 'var(--wc-mint,#91edd0)' }}
        />
      </div>
      <span className='text-muted-foreground font-mono text-[10px]'>
        {floor.toFixed(1)}–{ceiling.toFixed(1)}
      </span>
    </div>
  );
}

export function StartSitView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = toolSeason(cw?.season);
  const week = cw?.week ?? 1;

  const { data: ros } = useQuery({
    queryKey: ['nfl', 'ros', season],
    queryFn: () => fetchRosRankings(season),
    staleTime: 60 * 60 * 1000,
    // Season key settles after the current-week query resolves; keep the
    // previous pool through the re-key so the picker never unmounts.
    placeholderData: keepPreviousData
  });

  const [picked, setPicked] = useState<RosPlayer[]>([]);
  const ids = useMemo(() => picked.map((p) => p.player_id), [picked]);
  const excluded = useMemo(() => new Set(ids), [ids]);

  const {
    data: cmp,
    isFetching,
    error
  } = useQuery({
    queryKey: ['nfl', 'start-sit', season, week, ids],
    queryFn: () => fetchStartSitCompare(ids, season, week),
    enabled: ids.length >= 2,
    retry: false
  });

  const noWeekly =
    error != null &&
    'status' in (error as object) &&
    (error as unknown as { status: number }).status === 404;

  // Shared floor->ceiling scale across all compared players (see RangeBand).
  const rangeScale = useMemo(() => {
    const floors = (cmp?.players ?? [])
      .map((p) => p.projected_floor)
      .filter((v): v is number => v != null);
    const ceilings = (cmp?.players ?? [])
      .map((p) => p.projected_ceiling)
      .filter((v): v is number => v != null);
    if (floors.length === 0 || ceilings.length === 0) return { min: 0, max: 0 };
    return { min: Math.min(...floors), max: Math.max(...ceilings) };
  }, [cmp]);

  const verdict = useMemo(() => {
    if (!cmp) return null;
    const recommended = cmp.players.find((p) => p.recommended);
    if (!recommended) return null;
    const confidence = deriveConfidence(cmp.players, recommended.player_id);
    if (!confidence) return null;
    return {
      recommended,
      confidence: confidence.pct,
      factors: buildWhyFactors(confidence.rec, confidence.runnerUp, confidence.gap)
    };
  }, [cmp]);

  const columns: BroadcastColumn<ToolsComparePlayer>[] = [
    {
      key: 'player',
      header: 'Player',
      sticky: true,
      accessor: (p) => (
        <>
          <Badge variant='outline' className='mr-2'>
            {p.position}
          </Badge>
          {p.player_name}
          <span className='text-muted-foreground ml-1 text-xs'>{p.team}</span>
          {p.recommended && (
            <Badge className='ml-2' variant='default'>
              Start
            </Badge>
          )}
        </>
      )
    },
    {
      key: 'proj',
      header: 'Proj',
      align: 'right',
      accessor: (p) => p.projected_points.toFixed(1),
      cellClassName: 'font-mono font-medium'
    },
    {
      key: 'range',
      header: 'Floor – Ceiling',
      align: 'right',
      width: 'min-w-[140px]',
      accessor: (p) => (
        <RangeBand
          floor={p.projected_floor}
          proj={p.projected_points}
          ceiling={p.projected_ceiling}
          min={rangeScale.min}
          max={rangeScale.max}
        />
      )
    },
    {
      key: 'opp_rank',
      header: 'Opp rank vs pos',
      align: 'right',
      accessor: (p) => p.opp_rank_vs_position ?? '—',
      cellClassName: 'font-mono'
    },
    {
      key: 'ros_points',
      header: 'ROS pts',
      align: 'right',
      accessor: (p) => p.ros_points?.toFixed(0) ?? '—',
      cellClassName: 'font-mono'
    },
    {
      key: 'status',
      header: 'Status',
      accessor: (p) =>
        p.injury_status ? (
          <Badge variant='destructive'>{p.injury_status}</Badge>
        ) : (
          <span className='text-muted-foreground text-xs'>Healthy</span>
        )
    }
  ];

  return (
    <FadeIn className='space-y-4'>
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>
            Who should I start? (week {week})
          </CardTitle>
        </CardHeader>
        <CardContent className='space-y-4'>
          <RosPlayerPicker
            pool={ros?.players ?? []}
            exclude={excluded}
            onPick={(p) =>
              setPicked((s) => (s.length < 4 ? [...s, p] : s))
            }
            placeholder='Add 2-4 players to compare...'
          />
          <div className='flex flex-wrap gap-2'>
            {picked.map((p) => (
              <Badge key={p.player_id} variant='secondary' className='gap-1'>
                {p.player_name}
                <button
                  type='button'
                  aria-label={`Remove ${p.player_name}`}
                  onClick={() =>
                    setPicked((s) =>
                      s.filter((x) => x.player_id !== p.player_id)
                    )
                  }
                >
                  <Icons.close className='h-3 w-3' />
                </button>
              </Badge>
            ))}
          </div>

          {noWeekly && (
            <p className='text-muted-foreground text-sm'>
              Weekly projections for week {week} aren&apos;t published yet —
              start/sit comparisons go live once the season starts. Rest-of-season
              value is shown in the picker meanwhile.
            </p>
          )}
        </CardContent>
      </Card>

      {ids.length >= 2 && !noWeekly && (
        <div className='space-y-4'>
          {verdict && (
            <BroadcastPanel className='space-y-[var(--space-4)] p-[var(--space-4)]'>
              <div className='flex flex-wrap items-start justify-between gap-[var(--space-3)]'>
                <div>
                  <div
                    className='wc-display text-[length:var(--fs-xs)] tracking-[0.14em]'
                    style={{ color: 'var(--wc-mint,#91edd0)' }}
                  >
                    Recommended starter
                  </div>
                  <div className='wc-display mt-[var(--space-1)] text-[length:var(--fs-h2)] font-extrabold text-white'>
                    {verdict.recommended.player_name}
                    <span className='ml-[var(--space-2)] text-[length:var(--fs-sm)] font-normal tracking-normal text-white/50 uppercase'>
                      {verdict.recommended.position} · {verdict.recommended.team}
                    </span>
                  </div>
                  <p className='mt-[var(--space-1)] text-[length:var(--fs-xs)] text-white/60'>
                    {cmp?.reason}
                  </p>
                </div>
                <div className='min-w-[140px] text-right'>
                  <div
                    className='wc-display text-[length:var(--fs-h1)] font-extrabold tabular-nums'
                    style={{ color: 'var(--wc-mint,#91edd0)' }}
                  >
                    {verdict.confidence.toFixed(0)}%
                  </div>
                  <div className='text-[length:var(--fs-xs)] tracking-[0.1em] text-white/50 uppercase'>
                    confidence
                  </div>
                </div>
              </div>

              <div className='h-2 w-full overflow-hidden rounded-full bg-white/10'>
                <div
                  className='h-full rounded-full'
                  style={{
                    width: `${verdict.confidence}%`,
                    background: 'var(--wc-mint,#91edd0)'
                  }}
                />
              </div>

              <div className='grid gap-[var(--space-2)] sm:grid-cols-2'>
                {verdict.factors.map((f) => (
                  <div
                    key={f.label}
                    className='flex items-center justify-between rounded-md border border-white/10 px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--fs-xs)]'
                  >
                    <span className='tracking-[0.08em] text-white/60 uppercase'>
                      {f.label}
                    </span>
                    <span className='font-mono text-white'>{f.value}</span>
                  </div>
                ))}
              </div>
            </BroadcastPanel>
          )}

          <BroadcastTable
            columns={columns}
            rows={cmp?.players ?? []}
            getRowId={(p) => p.player_id}
            isLoading={isFetching}
            emptyMessage='No comparison data returned for these players.'
            rowClassName={(p) =>
              p.recommended ? 'bg-[rgba(145,237,208,0.08)]' : ''
            }
            minWidth='min-w-[760px]'
          />
          <p className='text-muted-foreground text-xs'>
            Opp rank vs pos: 1 = toughest defense against that position, 32
            = softest. Recommendation favors projection, with floor as the
            tiebreaker.
          </p>
        </div>
      )}
    </FadeIn>
  );
}
