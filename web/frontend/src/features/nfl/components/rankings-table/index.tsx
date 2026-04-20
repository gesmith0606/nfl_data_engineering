'use client';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Icons } from '@/components/icons';
import { useQuery } from '@tanstack/react-query';
import { nflKeys } from '../../api/queries';
import { fetchProjections } from '../../api/service';
import type { PlayerProjection, ScoringFormat, Position } from '../../api/types';
import { getTeamColor } from '@/lib/nfl/team-colors';
import Link from 'next/link';
import { useMemo, useState } from 'react';

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K'];
const SCORING_OPTIONS: { value: ScoringFormat; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' }
];

const POS_COLORS: Record<string, string> = {
  QB: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  RB: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
  WR: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400',
  TE: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  K: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400'
};

const TIER_CONFIG: Record<string, { label: string; bg: string; badge: string }> = {
  Elite: {
    label: 'Elite',
    bg: 'bg-yellow-50/60 dark:bg-yellow-900/10',
    badge: 'bg-yellow-100 text-yellow-800 border-yellow-300 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-700'
  },
  Strong: {
    label: 'Strong Starter',
    bg: 'bg-blue-50/40 dark:bg-blue-900/10',
    badge: 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-700'
  },
  Starter: {
    label: 'Starter',
    bg: 'bg-green-50/40 dark:bg-green-900/10',
    badge: 'bg-green-100 text-green-800 border-green-300 dark:bg-green-900/30 dark:text-green-400 dark:border-green-700'
  },
  Bench: {
    label: 'Bench / Depth',
    bg: '',
    badge: 'bg-gray-100 text-gray-600 border-gray-300 dark:bg-gray-800/30 dark:text-gray-400 dark:border-gray-700'
  }
};

/** Assign a tier based on position rank within position group. */
function assignTier(positionRank: number | null, position: string): string {
  if (positionRank === null) return 'Bench';

  // Position-specific tier thresholds (approximate roster counts)
  const thresholds: Record<string, [number, number, number]> = {
    QB: [2, 5, 12],
    RB: [3, 10, 24],
    WR: [4, 12, 30],
    TE: [2, 5, 12],
    K: [1, 4, 10]
  };

  const [elite, strong, starter] = thresholds[position] ?? [2, 8, 20];
  if (positionRank <= elite) return 'Elite';
  if (positionRank <= strong) return 'Strong';
  if (positionRank <= starter) return 'Starter';
  return 'Bench';
}

interface RankedPlayer extends PlayerProjection {
  overall_rank: number;
  tier: string;
}

export function RankingsTable() {
  const [scoring, setScoring] = useState<ScoringFormat>('half_ppr');
  const [position, setPosition] = useState<Position>('ALL');
  const [search, setSearch] = useState('');

  // Fetch all players (week=1 for preseason/season-long, high limit)
  const { data, isLoading, isError } = useQuery({
    queryKey: [...nflKeys.all, 'rankings', { scoring }],
    queryFn: () => fetchProjections(2026, 1, scoring, undefined, undefined, 1000)
  });

  const rankedPlayers = useMemo(() => {
    if (!data?.projections) return [];

    // Sort by projected_points descending
    const sorted = [...data.projections].sort(
      (a, b) => b.projected_points - a.projected_points
    );

    // Assign overall rank and tier
    return sorted.map((player, idx) => ({
      ...player,
      overall_rank: idx + 1,
      tier: assignTier(player.position_rank, player.position)
    }));
  }, [data]);

  // Apply position filter and search
  const filteredPlayers = useMemo(() => {
    let result = rankedPlayers;

    if (position !== 'ALL') {
      result = result.filter((p) => p.position === position);
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (p) =>
          p.player_name.toLowerCase().includes(q) ||
          p.team.toLowerCase().includes(q)
      );
    }

    return result;
  }, [rankedPlayers, position, search]);

  // Group by tier for dividers — consolidate into one group per tier
  const tieredGroups = useMemo(() => {
    const tierOrder = ['Elite', 'Strong', 'Starter', 'Bench'];
    const buckets: Record<string, RankedPlayer[]> = {};
    for (const player of filteredPlayers) {
      const t = player.tier;
      if (!buckets[t]) buckets[t] = [];
      buckets[t].push(player);
    }
    // Return in tier order, each group sorted by projected points desc
    return tierOrder
      .filter((t) => buckets[t]?.length)
      .map((t) => ({
        tier: t,
        players: buckets[t].sort((a, b) => b.projected_points - a.projected_points)
      }));
  }, [filteredPlayers]);

  return (
    <div className='space-y-[var(--gap-stack)]'>
      {/* Controls bar — mobile: each control takes its own row and spans the
       *  full card width so tap targets meet 44px. sm+: flex-wrap reverts to
       *  desktop rhythm. */}
      <Card>
        <CardContent className='flex flex-col gap-[var(--space-2)] pt-[var(--space-6)] sm:flex-row sm:flex-wrap sm:items-center sm:gap-[var(--gap-stack)]'>
          {/* Scoring format */}
          <Tabs value={scoring} onValueChange={(v) => setScoring(v as ScoringFormat)}>
            <TabsList className='w-full sm:w-auto'>
              {SCORING_OPTIONS.map((opt) => (
                <TabsTrigger
                  key={opt.value}
                  value={opt.value}
                  className='flex-1 sm:flex-initial'
                >
                  {opt.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {/* Position tabs */}
          <Tabs value={position} onValueChange={(v) => setPosition(v as Position)}>
            <TabsList className='w-full sm:w-auto'>
              {POSITIONS.map((pos) => (
                <TabsTrigger
                  key={pos}
                  value={pos}
                  className='flex-1 sm:flex-initial'
                >
                  {pos === 'ALL' ? 'All' : pos}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {/* Search */}
          <div className='relative w-full sm:ml-auto sm:w-auto sm:min-w-[200px]'>
            <Icons.search className='text-muted-foreground absolute left-[var(--space-3)] top-1/2 -translate-y-1/2 h-[var(--space-4)] w-[var(--space-4)] pointer-events-none' />
            <Input
              placeholder='Search players...'
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className='pl-[var(--space-8)] h-[var(--tap-min)] sm:h-9'
            />
          </div>
        </CardContent>
      </Card>

      {/* Summary stats */}
      {!isLoading && !isError && (
        <div className='flex items-center gap-[var(--gap-section)] px-[var(--space-1)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
          <span>{filteredPlayers.length} players</span>
          <span className='flex items-center gap-[var(--space-2)]'>
            {Object.entries(TIER_CONFIG).map(([key, cfg]) => {
              const count = filteredPlayers.filter((p) => p.tier === key).length;
              if (count === 0) return null;
              return (
                <Badge
                  key={key}
                  variant='outline'
                  className={`text-[length:var(--fs-micro)] leading-[var(--lh-micro)] px-[var(--space-2)] py-0 ${cfg.badge}`}
                >
                  {cfg.label}: {count}
                </Badge>
              );
            })}
          </span>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <Card>
          <CardContent className='pt-[var(--space-4)] space-y-[var(--space-2)]'>
            <div className='flex gap-[var(--gap-stack)] pb-[var(--space-2)] border-b'>
              {[40, 160, 50, 60, 80, 80, 80, 70, 60].map((w, i) => (
                <Skeleton key={i} className='h-[var(--space-4)]' style={{ width: w }} />
              ))}
            </div>
            {Array.from({ length: 15 }).map((_, row) => (
              <div key={row} className='flex gap-[var(--gap-stack)] py-[var(--space-1)]'>
                {[40, 160, 50, 60, 80, 80, 80, 70, 60].map((w, col) => (
                  <Skeleton key={col} className='h-[var(--space-4)]' style={{ width: w }} />
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-[var(--space-12)]'>
            <Icons.alertCircle className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
            <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              Failed to load rankings. Ensure the API is running.
            </p>
          </CardContent>
        </Card>
      ) : filteredPlayers.length === 0 ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-[var(--space-12)]'>
            <Icons.search className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
            <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              No players found matching your criteria.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card className='overflow-hidden'>
          {/* Mobile-first strategy: keep scroll wrapper but hide the 3 least-
           *  critical columns (#, Team, Pos Rk) under sm: and the Range bar +
           *  Tier under md:. Player name stays sticky-left so horizontal
           *  scrolling doesn't orphan rows. */}
          <div className='overflow-x-auto'>
            <table className='w-full text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
              <thead className='bg-muted/50 sticky top-0 z-10'>
                <tr className='border-b'>
                  <th className='hidden md:table-cell px-[var(--space-3)] py-[var(--space-3)] text-left font-semibold text-muted-foreground w-14'>
                    #
                  </th>
                  <th className='px-[var(--space-3)] py-[var(--space-3)] text-left font-semibold text-muted-foreground min-w-[140px] md:min-w-[180px] sticky left-0 bg-muted/50 z-10'>
                    Player
                  </th>
                  <th className='px-[var(--space-3)] py-[var(--space-3)] text-left font-semibold text-muted-foreground w-14'>
                    Pos
                  </th>
                  <th className='hidden sm:table-cell px-[var(--space-3)] py-[var(--space-3)] text-left font-semibold text-muted-foreground w-16'>
                    Team
                  </th>
                  <th className='px-[var(--space-3)] py-[var(--space-3)] text-right font-semibold text-muted-foreground w-20'>
                    Pts
                  </th>
                  <th className='hidden md:table-cell px-[var(--space-3)] py-[var(--space-3)] text-center font-semibold text-muted-foreground w-[140px]'>
                    Range
                  </th>
                  <th className='hidden sm:table-cell px-[var(--space-3)] py-[var(--space-3)] text-left font-semibold text-muted-foreground w-20'>
                    Tier
                  </th>
                  <th className='hidden md:table-cell px-[var(--space-3)] py-[var(--space-3)] text-right font-semibold text-muted-foreground w-16'>
                    Pos Rk
                  </th>
                </tr>
              </thead>
              <tbody>
                {tieredGroups.map((group) => {
                  const cfg = TIER_CONFIG[group.tier] ?? TIER_CONFIG.Bench;
                  return (
                    <TierGroup key={group.tier} tier={group.tier} config={cfg} players={group.players} position={position} />
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function TierGroup({
  tier,
  config,
  players,
  position
}: {
  tier: string;
  config: { label: string; bg: string; badge: string };
  players: RankedPlayer[];
  position: Position;
}) {
  return (
    <>
      {/* Tier divider row */}
      <tr className='border-t-2 border-border'>
        <td colSpan={8} className={`px-[var(--space-3)] py-[var(--space-2)] ${config.bg}`}>
          <div className='flex items-center gap-[var(--space-2)]'>
            <Badge
              variant='outline'
              className={`text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold ${config.badge}`}
            >
              {config.label}
            </Badge>
            <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'>
              {players.length} player{players.length !== 1 ? 's' : ''}
            </span>
          </div>
        </td>
      </tr>
      {players.map((player) => (
        <PlayerRow key={player.player_id || player.player_name} player={player} position={position} tierBg={config.bg} />
      ))}
    </>
  );
}

function PlayerRow({
  player,
  position,
  tierBg
}: {
  player: RankedPlayer;
  position: Position;
  tierBg: string;
}) {
  const teamColor = getTeamColor(player.team);
  const floor = player.projected_floor;
  const ceiling = player.projected_ceiling;
  const pts = player.projected_points;

  // Calculate range bar proportions
  const maxRange = Math.max(ceiling, 1);
  const floorPct = (floor / maxRange) * 100;
  const ptsPct = ((pts - floor) / maxRange) * 100;
  const ceilingPct = ((ceiling - pts) / maxRange) * 100;

  return (
    <tr
      className={`border-b border-border/50 hover:bg-muted/30 transition-colors duration-[var(--motion-base)] ease-[var(--ease-out-standard)] ${tierBg}`}
    >
      {/* Overall rank — desktop only */}
      <td className='hidden md:table-cell px-[var(--space-3)] py-[var(--space-3)]'>
        <span className='text-muted-foreground tabular-nums font-medium text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
          {position === 'ALL' ? player.overall_rank : (player.position_rank ?? '-')}
        </span>
      </td>

      {/* Player name — sticky-left on mobile so horizontal scroll doesn't
       *  orphan rows when the narrower layout still overflows. */}
      <td
        className={`px-[var(--space-3)] min-h-[var(--tap-min)] py-[var(--space-3)] sticky left-0 z-[1] ${tierBg || 'bg-background'}`}
      >
        <div className='flex min-h-[var(--tap-min)] items-center gap-[var(--space-2)]'>
          <Link
            href={`/dashboard/players/${player.player_id}`}
            className='font-medium hover:underline truncate block max-w-[14ch] sm:max-w-none'
          >
            {player.player_name}
          </Link>
          {player.injury_status && player.injury_status !== 'Active' && (
            <Badge
              variant='destructive'
              className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] px-[var(--space-1)] py-0 shrink-0'
            >
              {player.injury_status}
            </Badge>
          )}
        </div>
      </td>

      {/* Position badge */}
      <td className='px-[var(--space-3)] py-[var(--space-3)]'>
        <Badge
          variant='outline'
          className={`text-[length:var(--fs-micro)] leading-[var(--lh-micro)] px-[var(--space-2)] py-0 ${POS_COLORS[player.position] || ''}`}
        >
          {player.position}
        </Badge>
      </td>

      {/* Team — hidden below sm: */}
      <td className='hidden sm:table-cell px-[var(--space-3)] py-[var(--space-3)]'>
        <div className='flex items-center gap-[var(--space-2)]'>
          <span
            className='inline-block h-[var(--space-2)] w-[var(--space-2)] shrink-0 rounded-full'
            style={{ backgroundColor: teamColor }}
          />
          <span className='font-mono text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            {player.team}
          </span>
        </div>
      </td>

      {/* Projected points — always visible */}
      <td className='px-[var(--space-3)] py-[var(--space-3)] text-right'>
        <span className='font-bold tabular-nums text-[length:var(--fs-body)] leading-[var(--lh-body)]'>
          {pts.toFixed(1)}
        </span>
      </td>

      {/* Floor/ceiling range bar — desktop only */}
      <td className='hidden md:table-cell px-[var(--space-3)] py-[var(--space-3)]'>
        <div className='flex items-center gap-[var(--space-2)]'>
          <span className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground tabular-nums w-[var(--space-8)] text-right shrink-0'>
            {floor.toFixed(0)}
          </span>
          <div className='flex-1 h-2.5 bg-muted rounded-full overflow-hidden relative min-w-[60px]'>
            <div
              className='absolute inset-y-0 left-0 bg-transparent'
              style={{ width: `${floorPct}%` }}
            />
            <div
              className='absolute inset-y-0 bg-primary/60 rounded-l-full'
              style={{ left: `${floorPct}%`, width: `${ptsPct}%` }}
            />
            <div
              className='absolute inset-y-0 bg-primary/25 rounded-r-full'
              style={{ left: `${floorPct + ptsPct}%`, width: `${ceilingPct}%` }}
            />
          </div>
          <span className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-muted-foreground tabular-nums w-[var(--space-8)] shrink-0'>
            {ceiling.toFixed(0)}
          </span>
        </div>
      </td>

      {/* Tier badge — hidden below sm: */}
      <td className='hidden sm:table-cell px-[var(--space-3)] py-[var(--space-3)]'>
        <Badge
          variant='outline'
          className={`text-[length:var(--fs-micro)] leading-[var(--lh-micro)] px-[var(--space-2)] py-0 ${TIER_CONFIG[player.tier]?.badge ?? ''}`}
        >
          {TIER_CONFIG[player.tier]?.label ?? player.tier}
        </Badge>
      </td>

      {/* Position rank — desktop only */}
      <td className='hidden md:table-cell px-[var(--space-3)] py-[var(--space-3)] text-right'>
        <span className='text-muted-foreground tabular-nums text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
          {player.position}{player.position_rank ?? '-'}
        </span>
      </td>
    </tr>
  );
}
