'use client';

import { useQuery } from '@tanstack/react-query';
import { parseAsInteger, useQueryState } from 'nuqs';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Icons } from '@/components/icons';
import { EmptyState } from '@/components/EmptyState';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { getTeamFullName } from '@/lib/nfl/team-meta';
import { ApiError } from '@/lib/nfl/api';
import { Stagger, HoverLift, FadeIn } from '@/lib/motion-primitives';
import { cn } from '@/lib/utils';
import { gamesQueryOptions, gameSeasonsQueryOptions } from '../../api/queries';
import type { GameResult } from '../../api/types';

const DEFAULT_SEASON = 2025;
const DEFAULT_WEEK = 1;
const TOTAL_WEEKS = 18;

/** Format "2025-09-07" → "Sep 7, 2025". */
function formatGameDate(date: string | null): string {
  if (!date) return '';
  try {
    const d = new Date(`${date}T12:00:00`);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return date;
  }
}

/** Format "13:00" → "1:00 PM". */
function formatGameTime(time: string | null): string {
  if (!time) return '';
  try {
    const [h, m] = time.split(':').map(Number);
    const ampm = h >= 12 ? 'PM' : 'AM';
    const hour = h % 12 || 12;
    return `${hour}:${String(m).padStart(2, '0')} ${ampm}`;
  } catch {
    return time;
  }
}

interface GameCardProps {
  game: GameResult;
}

/** "W" chip — mint-on-ink, matches the `.bug-verdict.hit` scorebug motif
 *  rather than the shadcn secondary badge, which doesn't guarantee contrast
 *  on the BroadcastPanel's hardcoded near-black surface. */
function WinChip() {
  return (
    <span
      className='wc-display shrink-0 rounded-full px-[6px] py-[1px] text-[10px] leading-[1.4] font-extrabold tracking-[0.08em]'
      style={{ background: 'var(--wc-mint,#91edd0)', color: 'var(--wc-mint-ink,#04140e)' }}
    >
      W
    </span>
  );
}

function GameCard({ game }: GameCardProps) {
  const homeColor = getTeamColor(game.home_team);
  const awayColor = getTeamColor(game.away_team);
  const homeWon = game.winner === game.home_team;
  const awayWon = game.winner === game.away_team;
  const hasScore = game.home_score !== null && game.away_score !== null;

  return (
    <HoverLift lift={3} className='h-full'>
      <BroadcastPanel
        rail={false}
        className='h-full transition-shadow duration-[var(--motion-fast)] ease-out hover:shadow-[var(--elevation-overlay)]'
        data-game-id={game.game_id}
      >
        {/* Team color bar — team colors are data, kept as-is */}
        <div
          className='flex h-1.5'
          style={{
            background: `linear-gradient(to right, ${awayColor} 50%, ${homeColor} 50%)`
          }}
        />

        <div className='wc-display px-[var(--space-4)] pt-[var(--space-3)] pb-[var(--space-2)] text-[length:var(--fs-body)] leading-[var(--lh-body)]'>
          {/* Away team */}
          <div className='flex items-center justify-between gap-[var(--space-2)]'>
            <div className='flex items-center gap-[var(--space-2)] min-w-0'>
              <span
                className='h-2.5 w-2.5 shrink-0 rounded-full'
                style={{ background: awayColor }}
                aria-hidden
              />
              <span
                className={cn(
                  'truncate font-semibold tracking-[0.02em]',
                  awayWon ? 'text-white' : 'text-white/50'
                )}
                title={getTeamFullName(game.away_team)}
              >
                {game.away_team}
              </span>
              {awayWon && <WinChip />}
            </div>
            {hasScore && (
              <span
                className={cn(
                  'wc-num-hero !text-[length:var(--fs-lg)] !leading-[var(--lh-lg)] shrink-0',
                  !awayWon && 'opacity-50'
                )}
              >
                {game.away_score}
              </span>
            )}
          </div>

          {/* Home team */}
          <div className='flex items-center justify-between gap-[var(--space-2)] mt-[var(--space-2)]'>
            <div className='flex items-center gap-[var(--space-2)] min-w-0'>
              <span
                className='h-2.5 w-2.5 shrink-0 rounded-full'
                style={{ background: homeColor }}
                aria-hidden
              />
              <span
                className={cn(
                  'truncate font-semibold tracking-[0.02em]',
                  homeWon ? 'text-white' : 'text-white/50'
                )}
                title={getTeamFullName(game.home_team)}
              >
                {game.home_team}
              </span>
              {homeWon && <WinChip />}
            </div>
            {hasScore && (
              <span
                className={cn(
                  'wc-num-hero !text-[length:var(--fs-lg)] !leading-[var(--lh-lg)] shrink-0',
                  !homeWon && 'opacity-50'
                )}
              >
                {game.home_score}
              </span>
            )}
          </div>
        </div>

        <div className='px-[var(--space-4)] pb-[var(--space-3)] pt-0'>
          <div className='flex items-center justify-between text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/50'>
            <span>
              {formatGameDate(game.game_date)}
              {game.game_time ? ` · ${formatGameTime(game.game_time)}` : ''}
            </span>
            {game.total_points !== null && (
              <span className='font-mono tabular-nums'>
                {game.total_points} pts
              </span>
            )}
          </div>
        </div>
      </BroadcastPanel>
    </HoverLift>
  );
}

function GameCardSkeleton() {
  return (
    <BroadcastPanel rail={false} className='h-full'>
      <div className='h-1.5 bg-white/10' />
      <div className='space-y-[var(--space-2)] px-[var(--space-4)] pt-[var(--space-3)] pb-[var(--space-2)]'>
        <div className='flex items-center justify-between'>
          <Skeleton className='h-[var(--space-4)] w-24 bg-white/10' />
          <Skeleton className='h-[var(--space-5)] w-8 bg-white/10' />
        </div>
        <div className='flex items-center justify-between'>
          <Skeleton className='h-[var(--space-4)] w-24 bg-white/10' />
          <Skeleton className='h-[var(--space-5)] w-8 bg-white/10' />
        </div>
      </div>
      <div className='px-[var(--space-4)] pb-[var(--space-3)] pt-0'>
        <div className='flex items-center justify-between'>
          <Skeleton className='h-[var(--space-3)] w-32 bg-white/10' />
          <Skeleton className='h-[var(--space-3)] w-12 bg-white/10' />
        </div>
      </div>
    </BroadcastPanel>
  );
}

export function GameResultsGrid() {
  const [season, setSeason] = useQueryState(
    'season',
    parseAsInteger.withDefault(DEFAULT_SEASON)
  );
  const [rawWeek, setWeek] = useQueryState(
    'week',
    parseAsInteger.withDefault(DEFAULT_WEEK)
  );
  // Clamp hand-edited URLs (?week=99) into the valid range — the backend
  // 422s outside 1..18 and that should never reach the network.
  const week = Math.min(Math.max(rawWeek, 1), TOTAL_WEEKS);

  const { data: seasonsData } = useQuery(gameSeasonsQueryOptions());
  const { data, isLoading, isError, error } = useQuery(gamesQueryOptions(season, week));

  const isNotFound =
    isError && error instanceof ApiError && error.status === 404;

  const availableSeasons = seasonsData?.seasons ?? [];

  return (
    <div className='space-y-[var(--gap-stack)]'>
      {/* Filters */}
      <div className='grid grid-cols-2 gap-[var(--space-2)] sm:flex sm:flex-wrap sm:items-center sm:gap-[var(--gap-stack)]'>
        <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
          <SelectTrigger
            aria-label='Season'
            className='h-[var(--tap-min)] w-full sm:h-9 sm:w-28'
          >
            <SelectValue placeholder='Season' />
          </SelectTrigger>
          <SelectContent>
            {(availableSeasons.length > 0
              ? availableSeasons.map((s) => s.season)
              : [DEFAULT_SEASON]
            ).map((s) => (
              <SelectItem key={s} value={String(s)}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={String(week)} onValueChange={(v) => setWeek(Number(v))}>
          <SelectTrigger
            aria-label='Week'
            className='h-[var(--tap-min)] w-full sm:h-9 sm:w-24'
          >
            <SelectValue placeholder='Week' />
          </SelectTrigger>
          <SelectContent>
            {Array.from({ length: TOTAL_WEEKS }, (_, i) => i + 1).map((w) => (
              <SelectItem key={w} value={String(w)}>
                Week {w}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Cards */}
      {isLoading ? (
        <div className='grid grid-cols-1 gap-[var(--gap-stack)] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'>
          {Array.from({ length: 8 }).map((_, i) => (
            <GameCardSkeleton key={i} />
          ))}
        </div>
      ) : isNotFound || (data?.games?.length === 0) ? (
        <EmptyState
          icon={Icons.calendar}
          title='No games for this week'
          description={`Game results for ${season} Week ${week} are not available.`}
        />
      ) : isError ? (
        <EmptyState
          icon={Icons.alertCircle}
          title='Unable to load scores'
          description='The scores feed is unavailable right now. Please try again in a moment.'
        />
      ) : (
        <FadeIn>
          <Stagger
            step={0.03}
            className='grid grid-cols-1 gap-[var(--gap-stack)] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
          >
            {(data?.games ?? []).map((game) => (
              <GameCard key={game.game_id} game={game} />
            ))}
          </Stagger>
        </FadeIn>
      )}
    </div>
  );
}
