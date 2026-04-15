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

  // Group by tier for dividers
  const tieredGroups = useMemo(() => {
    const groups: { tier: string; players: RankedPlayer[] }[] = [];
    let currentTier = '';
    for (const player of filteredPlayers) {
      if (player.tier !== currentTier) {
        currentTier = player.tier;
        groups.push({ tier: currentTier, players: [] });
      }
      groups[groups.length - 1].players.push(player);
    }
    return groups;
  }, [filteredPlayers]);

  return (
    <div className='space-y-4'>
      {/* Controls bar */}
      <Card>
        <CardContent className='flex flex-wrap items-center gap-4 pt-6'>
          {/* Scoring format */}
          <Tabs value={scoring} onValueChange={(v) => setScoring(v as ScoringFormat)}>
            <TabsList>
              {SCORING_OPTIONS.map((opt) => (
                <TabsTrigger key={opt.value} value={opt.value}>
                  {opt.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {/* Position tabs */}
          <Tabs value={position} onValueChange={(v) => setPosition(v as Position)}>
            <TabsList>
              {POSITIONS.map((pos) => (
                <TabsTrigger key={pos} value={pos}>
                  {pos === 'ALL' ? 'All' : pos}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {/* Search */}
          <div className='relative ml-auto min-w-[200px]'>
            <Icons.search className='text-muted-foreground absolute left-2.5 top-2.5 h-4 w-4' />
            <Input
              placeholder='Search players...'
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className='pl-8 h-9'
            />
          </div>
        </CardContent>
      </Card>

      {/* Summary stats */}
      {!isLoading && !isError && (
        <div className='flex items-center gap-6 px-1 text-sm text-muted-foreground'>
          <span>{filteredPlayers.length} players</span>
          <span className='flex items-center gap-1.5'>
            {Object.entries(TIER_CONFIG).map(([key, cfg]) => {
              const count = filteredPlayers.filter((p) => p.tier === key).length;
              if (count === 0) return null;
              return (
                <Badge
                  key={key}
                  variant='outline'
                  className={`text-[10px] px-1.5 py-0 ${cfg.badge}`}
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
          <CardContent className='pt-4 space-y-2'>
            <div className='flex gap-4 pb-2 border-b'>
              {[40, 160, 50, 60, 80, 80, 80, 70, 60].map((w, i) => (
                <Skeleton key={i} className='h-4' style={{ width: w }} />
              ))}
            </div>
            {Array.from({ length: 15 }).map((_, row) => (
              <div key={row} className='flex gap-4 py-1'>
                {[40, 160, 50, 60, 80, 80, 80, 70, 60].map((w, col) => (
                  <Skeleton key={col} className='h-4' style={{ width: w }} />
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-12'>
            <Icons.alertCircle className='text-muted-foreground mb-2 h-8 w-8' />
            <p className='text-muted-foreground text-sm'>
              Failed to load rankings. Ensure the API is running.
            </p>
          </CardContent>
        </Card>
      ) : filteredPlayers.length === 0 ? (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-12'>
            <Icons.search className='text-muted-foreground mb-2 h-8 w-8' />
            <p className='text-muted-foreground text-sm'>
              No players found matching your criteria.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card className='overflow-hidden'>
          <div className='overflow-x-auto'>
            <table className='w-full text-sm'>
              <thead className='bg-muted/50 sticky top-0 z-10'>
                <tr className='border-b'>
                  <th className='px-3 py-3 text-left font-semibold text-muted-foreground w-14'>
                    #
                  </th>
                  <th className='px-3 py-3 text-left font-semibold text-muted-foreground min-w-[180px]'>
                    Player
                  </th>
                  <th className='px-3 py-3 text-left font-semibold text-muted-foreground w-14'>
                    Pos
                  </th>
                  <th className='px-3 py-3 text-left font-semibold text-muted-foreground w-16'>
                    Team
                  </th>
                  <th className='px-3 py-3 text-right font-semibold text-muted-foreground w-20'>
                    Pts
                  </th>
                  <th className='px-3 py-3 text-center font-semibold text-muted-foreground w-[140px]'>
                    Range
                  </th>
                  <th className='px-3 py-3 text-left font-semibold text-muted-foreground w-20'>
                    Tier
                  </th>
                  <th className='px-3 py-3 text-right font-semibold text-muted-foreground w-16'>
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
        <td colSpan={8} className={`px-3 py-2 ${config.bg}`}>
          <div className='flex items-center gap-2'>
            <Badge variant='outline' className={`text-xs font-semibold ${config.badge}`}>
              {config.label}
            </Badge>
            <span className='text-xs text-muted-foreground'>
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
    <tr className={`border-b border-border/50 hover:bg-muted/30 transition-colors ${tierBg}`}>
      {/* Overall rank */}
      <td className='px-3 py-2.5'>
        <span className='text-muted-foreground tabular-nums font-medium text-xs'>
          {position === 'ALL' ? player.overall_rank : (player.position_rank ?? '-')}
        </span>
      </td>

      {/* Player name */}
      <td className='px-3 py-2.5'>
        <div className='flex items-center gap-2'>
          <Link
            href={`/dashboard/players/${player.player_id}`}
            className='font-medium hover:underline truncate'
          >
            {player.player_name}
          </Link>
          {player.injury_status && player.injury_status !== 'Active' && (
            <Badge variant='destructive' className='text-[10px] px-1 py-0 shrink-0'>
              {player.injury_status}
            </Badge>
          )}
        </div>
      </td>

      {/* Position badge */}
      <td className='px-3 py-2.5'>
        <Badge variant='outline' className={`text-[10px] px-1.5 py-0 ${POS_COLORS[player.position] || ''}`}>
          {player.position}
        </Badge>
      </td>

      {/* Team */}
      <td className='px-3 py-2.5'>
        <div className='flex items-center gap-1.5'>
          <span
            className='inline-block h-2 w-2 shrink-0 rounded-full'
            style={{ backgroundColor: teamColor }}
          />
          <span className='font-mono text-xs'>{player.team}</span>
        </div>
      </td>

      {/* Projected points */}
      <td className='px-3 py-2.5 text-right'>
        <span className='font-bold tabular-nums text-base'>
          {pts.toFixed(1)}
        </span>
      </td>

      {/* Floor/ceiling range bar */}
      <td className='px-3 py-2.5'>
        <div className='flex items-center gap-2'>
          <span className='text-[10px] text-muted-foreground tabular-nums w-8 text-right shrink-0'>
            {floor.toFixed(0)}
          </span>
          <div className='flex-1 h-2.5 bg-muted rounded-full overflow-hidden relative min-w-[60px]'>
            {/* Empty space for floor */}
            <div
              className='absolute inset-y-0 left-0 bg-transparent'
              style={{ width: `${floorPct}%` }}
            />
            {/* Projected points bar */}
            <div
              className='absolute inset-y-0 bg-primary/60 rounded-l-full'
              style={{ left: `${floorPct}%`, width: `${ptsPct}%` }}
            />
            {/* Ceiling extension */}
            <div
              className='absolute inset-y-0 bg-primary/25 rounded-r-full'
              style={{ left: `${floorPct + ptsPct}%`, width: `${ceilingPct}%` }}
            />
          </div>
          <span className='text-[10px] text-muted-foreground tabular-nums w-8 shrink-0'>
            {ceiling.toFixed(0)}
          </span>
        </div>
      </td>

      {/* Tier badge */}
      <td className='px-3 py-2.5'>
        <Badge
          variant='outline'
          className={`text-[10px] px-1.5 py-0 ${TIER_CONFIG[player.tier]?.badge ?? ''}`}
        >
          {TIER_CONFIG[player.tier]?.label ?? player.tier}
        </Badge>
      </td>

      {/* Position rank */}
      <td className='px-3 py-2.5 text-right'>
        <span className='text-muted-foreground tabular-nums text-xs'>
          {player.position}{player.position_rank ?? '-'}
        </span>
      </td>
    </tr>
  );
}
