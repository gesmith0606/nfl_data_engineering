'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/EmptyState';
import { Icons } from '@/components/icons';
import { FadeIn } from '@/lib/motion-primitives';
import { toolSeason } from '@/lib/nfl/season';
import type { RosPlayer } from '@/lib/nfl/types';
import {
  currentWeekQueryOptions,
  gameSeasonsQueryOptions,
  playerDetailQueryOptions,
  playerGameLogQueryOptions,
  projectionsQueryOptions,
  rosRankingsQueryOptions
} from '../../api/queries';
import { PlayerProfileHeader, PlayerProfileHeaderSkeleton } from './player-profile-header';
import { BottomLinePanel, BottomLinePanelSkeleton } from './bottom-line-panel';
import { PercentileBars, PercentileBarsSkeleton } from './percentile-bars';
import { GameLogTable } from './game-log-table';
import { ProjectionHistoryChart } from './projection-history-chart';
import { CorrelationsPanel } from './correlations-panel';
import { PlayerNewsSection } from './news-section';
import { buildPercentileMetrics } from './percentile';

export interface PlayerProfileProps {
  playerId: string;
}

const SCORING = 'half_ppr' as const;

/**
 * Player profile — the flagship surface for two research-backed patterns:
 * (1) the ESPN "Bottom Line" one-sentence verdict, and (2) the Opta
 * raw-value+percentile bars. See the individual section components for the
 * derivation of each. Loading is skeletons throughout (no spinners); a
 * player with no current-week projection (rookie, or off the active slate)
 * gets a named empty state rather than a blank page or crash.
 */
export function PlayerProfile({ playerId }: PlayerProfileProps) {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = cw?.season ?? new Date().getFullYear();
  const week = cw?.week ?? 1;

  const {
    data: player,
    isLoading: playerLoading,
    isError: playerError,
    refetch
  } = useQuery(playerDetailQueryOptions(playerId, season, week, SCORING));

  // Position pool for this week — backs both the percentile bars and the
  // Bottom Line's "vs position median" comparison. Disabled until the
  // player's position is known so we never fetch the unfiltered full slate.
  const { data: weeklyPoolResp, isLoading: poolLoading } = useQuery({
    ...projectionsQueryOptions(season, week, SCORING, player?.position),
    enabled: !!player?.position
  });

  // ROS pool backs the one rest-of-season percentile axis. Uses the same
  // "clamp to the upcoming season" resolution as the other manager tools
  // (dynasty/trade/value) since /api/tools/ros is preseason-backed.
  const rosSeason = toolSeason(cw?.season);
  const { data: rosResp } = useQuery({
    ...rosRankingsQueryOptions(rosSeason, player?.position ?? null),
    enabled: !!player?.position
  });

  // Default the game log to the most recent season that actually has player
  // stats, rather than the current (possibly preseason, gameless) season —
  // an honest non-empty default instead of forcing every profile into the
  // "no games yet" empty state during the offseason.
  const { data: gameSeasons } = useQuery(gameSeasonsQueryOptions());
  const gameLogSeason = useMemo(() => {
    const withStats = (gameSeasons?.seasons ?? []).filter((s) => s.has_player_stats);
    if (withStats.length === 0) return season;
    return Math.max(...withStats.map((s) => s.season));
  }, [gameSeasons, season]);

  const { data: gameLogResp, isLoading: gameLogLoading } = useQuery(
    playerGameLogQueryOptions(playerId, gameLogSeason, SCORING)
  );

  const weeklyPositionPool = useMemo(
    () => weeklyPoolResp?.projections ?? [],
    [weeklyPoolResp]
  );
  const weeklyPointsPool = useMemo(
    () => weeklyPositionPool.map((p) => p.projected_points),
    [weeklyPositionPool]
  );

  const rosPlayer: RosPlayer | undefined = useMemo(
    () => rosResp?.players.find((p) => p.player_id === playerId),
    [rosResp, playerId]
  );

  const metrics = useMemo(() => {
    if (!player) return [];
    return buildPercentileMetrics(player, weeklyPositionPool, {
      player: rosPlayer,
      pool: rosResp?.players ?? []
    });
  }, [player, weeklyPositionPool, rosPlayer, rosResp]);

  if (playerLoading) {
    return (
      <div className='space-y-[var(--gap-section)]'>
        <PlayerProfileHeaderSkeleton />
        <BottomLinePanelSkeleton />
        <PercentileBarsSkeleton />
      </div>
    );
  }

  if (playerError || !player) {
    return (
      <EmptyState
        icon={Icons.alertCircle}
        title='No projection data for this player yet'
        description='This can happen for a rookie or a player without a current-week projection. Check back once the slate is published, or search for another player.'
        action={
          <div className='flex gap-[var(--space-2)]'>
            <Button variant='outline' size='sm' onClick={() => void refetch()}>
              Retry
            </Button>
            <Button variant='outline' size='sm' asChild>
              <Link href='/dashboard/players'>Back to Search</Link>
            </Button>
          </div>
        }
      />
    );
  }

  return (
    <FadeIn className='space-y-[var(--gap-section)]'>
      <div>
        <Button variant='ghost' size='sm' asChild className='-ml-[var(--space-2)]'>
          <Link href='/dashboard/players'>
            <Icons.chevronLeft className='mr-[var(--space-1)] h-[var(--space-4)] w-[var(--space-4)]' />
            Back to Search
          </Link>
        </Button>
      </div>

      <PlayerProfileHeader player={player} />

      <BottomLinePanel player={player} positionPool={weeklyPointsPool} />

      {poolLoading ? <PercentileBarsSkeleton /> : <PercentileBars metrics={metrics} />}

      {/* Projected-vs-actual overlay — same season resolution as the Game
       *  Log below (gameLogSeason: current season if it has played games,
       *  else the most recent season that does) so the two sections never
       *  disagree about which season they're showing. */}
      <ProjectionHistoryChart playerId={playerId} season={gameLogSeason} scoring={SCORING} />

      {/* Correlated players (UC3) and recent news — ported from the retired
       *  PlayerDetail page. Each section owns its own query/loading/empty
       *  state, independent of the player-detail load above. */}
      <CorrelationsPanel playerId={playerId} />

      <PlayerNewsSection playerId={playerId} season={season} week={week} />

      <div>
        <h2 className='wc-display mb-[var(--space-2)] text-[length:var(--fs-sm)] tracking-[0.1em] text-muted-foreground'>
          Game Log — {gameLogSeason}
        </h2>
        <GameLogTable
          position={player.position}
          rows={gameLogResp?.game_log ?? []}
          isLoading={gameLogLoading}
          emptyMessage={`No completed games logged for ${player.player_name} in ${gameLogSeason} yet.`}
        />
        <p className='mt-[var(--space-2)] text-[length:var(--fs-xs)] text-muted-foreground'>
          Actual results only — the game log endpoint doesn&apos;t carry a per-week projected
          value, so this week&apos;s projection (above) is the only projected number available
          for this player right now.
        </p>
      </div>
    </FadeIn>
  );
}
