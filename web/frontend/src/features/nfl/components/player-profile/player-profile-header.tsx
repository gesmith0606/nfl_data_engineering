import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { getPositionBadgeClass } from '@/lib/nfl/position-colors';
import { getTeamColor, getReadableTeamColorVars } from '@/lib/nfl/team-colors';
import type { PlayerProjection } from '@/lib/nfl/types';
import { cn } from '@/lib/utils';

export function PlayerProfileHeaderSkeleton() {
  return (
    <BroadcastPanel className='p-[var(--space-5)]'>
      <div className='flex flex-wrap items-start justify-between gap-[var(--space-4)]'>
        <div className='min-w-0 flex-1 space-y-[var(--space-2)]'>
          <Skeleton className='h-[var(--space-4)] w-24' />
          <Skeleton className='h-[var(--space-8)] w-64' />
          <Skeleton className='h-[var(--space-4)] w-40' />
        </div>
        <Skeleton className='h-[var(--space-10)] w-20' />
      </div>
    </BroadcastPanel>
  );
}

export interface PlayerProfileHeaderProps {
  player: PlayerProjection;
}

/**
 * Header: name, team/position badges, injury status. Injury status renders
 * inline here — never in a collapsed/below-fold section — per the research
 * rule that status is the single highest-priority read on a player page.
 */
export function PlayerProfileHeader({ player }: PlayerProfileHeaderProps) {
  const hasInjury = !!player.injury_status && player.injury_status.toLowerCase() !== 'active';

  return (
    <BroadcastPanel railColor={getTeamColor(player.team)} className='p-[var(--space-5)]'>
      <div className='flex flex-wrap items-start justify-between gap-[var(--space-4)]'>
        <div className='min-w-0 flex-1'>
          <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
            <span
              className={cn(
                'inline-flex items-center px-[var(--space-2)] py-[2px] text-[length:var(--fs-xs)]',
                getPositionBadgeClass(player.position)
              )}
            >
              {player.position}
            </span>
            <span
              className='font-mono text-[length:var(--fs-sm)] font-semibold uppercase text-[var(--team-color)] dark:text-[var(--team-color-readable)]'
              style={getReadableTeamColorVars(player.team)}
            >
              {player.team}
            </span>
            {player.position_rank != null && (
              <span className='text-[length:var(--fs-xs)] text-white/50'>
                #{player.position_rank} {player.position}
              </span>
            )}
            {hasInjury && (
              <Badge
                variant='destructive'
                className='wc-display text-[length:var(--fs-xs)] tracking-[0.06em]'
              >
                {player.injury_status}
              </Badge>
            )}
          </div>
          <h1 className='wc-display mt-[var(--space-2)] text-[length:var(--fs-h1)] leading-[var(--lh-h1)] font-extrabold text-white'>
            {player.player_name}
          </h1>
        </div>
        <div className='shrink-0 text-right'>
          <div
            className='wc-display font-extrabold tabular-nums'
            style={{ fontSize: 'clamp(28px, 4vw, 40px)', color: 'var(--wc-mint,#91edd0)' }}
          >
            {player.projected_points.toFixed(1)}
          </div>
          <div className='text-[length:var(--fs-xs)] tracking-[0.1em] text-white/50 uppercase'>
            projected pts · wk {player.week}
          </div>
        </div>
      </div>
    </BroadcastPanel>
  );
}
