'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { projectionsQueryOptions, predictionsQueryOptions } from '../api/queries';
import type { PlayerProjection, GamePrediction, ScoringFormat } from '../api/types';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Icons } from '@/components/icons';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { getTeamFullName, TEAM_SECONDARY_COLORS } from '@/lib/nfl/team-meta';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DIVISIONS: { conference: string; division: string; teams: string[] }[] = [
  { conference: 'AFC', division: 'East', teams: ['BUF', 'MIA', 'NE', 'NYJ'] },
  { conference: 'AFC', division: 'North', teams: ['BAL', 'CIN', 'CLE', 'PIT'] },
  { conference: 'AFC', division: 'South', teams: ['HOU', 'IND', 'JAX', 'TEN'] },
  { conference: 'AFC', division: 'West', teams: ['DEN', 'KC', 'LV', 'LAC'] },
  { conference: 'NFC', division: 'East', teams: ['DAL', 'NYG', 'PHI', 'WAS'] },
  { conference: 'NFC', division: 'North', teams: ['CHI', 'DET', 'GB', 'MIN'] },
  { conference: 'NFC', division: 'South', teams: ['ATL', 'CAR', 'NO', 'TB'] },
  { conference: 'NFC', division: 'West', teams: ['ARI', 'LAR', 'SEA', 'SF'] }
];

/** Offensive positions in display order. */
const OFFENSE_SLOTS = [
  { slot: 'QB1', pos: 'QB', label: 'QB', row: 'backfield' },
  { slot: 'RB1', pos: 'RB', label: 'RB1', row: 'backfield' },
  { slot: 'RB2', pos: 'RB', label: 'RB2', row: 'backfield' },
  { slot: 'WR1', pos: 'WR', label: 'WR1', row: 'receivers' },
  { slot: 'WR2', pos: 'WR', label: 'WR2', row: 'receivers' },
  { slot: 'WR3', pos: 'WR', label: 'WR3', row: 'receivers' },
  { slot: 'TE1', pos: 'TE', label: 'TE', row: 'receivers' },
  { slot: 'LT', pos: 'OL', label: 'LT', row: 'line' },
  { slot: 'LG', pos: 'OL', label: 'LG', row: 'line' },
  { slot: 'C', pos: 'OL', label: 'C', row: 'line' },
  { slot: 'RG', pos: 'OL', label: 'RG', row: 'line' },
  { slot: 'RT', pos: 'OL', label: 'RT', row: 'line' }
] as const;

/** Defensive positions in display order. */
const DEFENSE_SLOTS = [
  { slot: 'DE1', pos: 'DE', label: 'DE', row: 'line' },
  { slot: 'DT1', pos: 'DT', label: 'DT', row: 'line' },
  { slot: 'DT2', pos: 'DT', label: 'DT', row: 'line' },
  { slot: 'DE2', pos: 'DE', label: 'DE', row: 'line' },
  { slot: 'LB1', pos: 'LB', label: 'LB', row: 'linebackers' },
  { slot: 'LB2', pos: 'LB', label: 'LB', row: 'linebackers' },
  { slot: 'LB3', pos: 'LB', label: 'LB', row: 'linebackers' },
  { slot: 'CB1', pos: 'CB', label: 'CB1', row: 'secondary' },
  { slot: 'CB2', pos: 'CB', label: 'CB2', row: 'secondary' },
  { slot: 'SS', pos: 'SS', label: 'SS', row: 'secondary' },
  { slot: 'FS', pos: 'FS', label: 'FS', row: 'secondary' }
] as const;

/** Position group colors. */
const POS_COLORS: Record<string, string> = {
  QB: '#E31837',
  RB: '#00A6A0',
  WR: '#4F46E5',
  TE: '#D97706',
  OL: '#6B7280',
  DE: '#DC2626',
  DT: '#B91C1C',
  LB: '#7C3AED',
  CB: '#2563EB',
  SS: '#0891B2',
  FS: '#0D9488',
  K: '#6B7280'
};

// ---------------------------------------------------------------------------
// Rating calculation
// ---------------------------------------------------------------------------

interface RatedPlayer {
  player_id: string;
  player_name: string;
  team: string;
  position: string;
  projected_points: number | null;
  injury_status: string | null;
  rating: number;
  position_rank: number | null;
}

/**
 * Calculate a 1-99 Madden-style rating from positional percentile.
 * Top player at position = 99, average = 72, bottom = 50.
 */
function computeRatings(players: PlayerProjection[]): Map<string, RatedPlayer> {
  const byPosition = new Map<string, PlayerProjection[]>();
  for (const p of players) {
    const pos = p.position;
    if (!byPosition.has(pos)) byPosition.set(pos, []);
    byPosition.get(pos)!.push(p);
  }

  const result = new Map<string, RatedPlayer>();

  for (const [, group] of byPosition) {
    const sorted = [...group].sort((a, b) => b.projected_points - a.projected_points);
    const count = sorted.length;

    for (let i = 0; i < sorted.length; i++) {
      const p = sorted[i];
      // Percentile: 1.0 = best, 0.0 = worst
      const pct = count > 1 ? 1 - i / (count - 1) : 0.5;
      // Map to 50-99 range
      const rating = Math.round(50 + pct * 49);
      result.set(p.player_id, {
        player_id: p.player_id,
        player_name: p.player_name,
        team: p.team,
        position: p.position,
        projected_points: p.projected_points,
        injury_status: p.injury_status,
        rating,
        position_rank: p.position_rank
      });
    }
  }

  return result;
}

/**
 * Build a roster from projections, filling offensive slots by positional rank.
 */
function buildOffensiveRoster(
  projections: PlayerProjection[],
  team: string,
  ratingsMap: Map<string, RatedPlayer>
): Map<string, RatedPlayer | null> {
  const teamPlayers = projections.filter((p) => p.team === team);
  const byPos = new Map<string, PlayerProjection[]>();
  for (const p of teamPlayers) {
    if (!byPos.has(p.position)) byPos.set(p.position, []);
    byPos.get(p.position)!.push(p);
  }
  // Sort each group by projected points descending
  for (const [, group] of byPos) {
    group.sort((a, b) => b.projected_points - a.projected_points);
  }

  const used = new Set<string>();
  const roster = new Map<string, RatedPlayer | null>();

  for (const slot of OFFENSE_SLOTS) {
    if (slot.pos === 'OL') {
      // OL have no projections -- placeholder
      roster.set(slot.slot, {
        player_id: `${team}-${slot.slot}`,
        player_name: `${slot.label}`,
        team,
        position: 'OL',
        projected_points: null,
        injury_status: null,
        rating: 65, // default OL rating
        position_rank: null
      });
      continue;
    }

    const group = byPos.get(slot.pos) ?? [];
    const next = group.find((p) => !used.has(p.player_id));
    if (next) {
      used.add(next.player_id);
      roster.set(slot.slot, ratingsMap.get(next.player_id) ?? null);
    } else {
      roster.set(slot.slot, null);
    }
  }

  return roster;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RatingBadge({ rating, size = 'md' }: { rating: number; size?: 'sm' | 'md' | 'lg' }) {
  let bg = 'bg-gray-500';
  if (rating >= 90) bg = 'bg-emerald-500';
  else if (rating >= 80) bg = 'bg-blue-500';
  else if (rating >= 70) bg = 'bg-yellow-500';
  else if (rating >= 60) bg = 'bg-orange-500';
  else bg = 'bg-red-500';

  const sizeClasses = {
    sm: 'h-7 w-7 text-xs',
    md: 'h-9 w-9 text-sm',
    lg: 'h-11 w-11 text-base'
  };

  return (
    <div
      className={`${bg} ${sizeClasses[size]} inline-flex items-center justify-center rounded-lg font-black text-white shadow-md`}
    >
      {rating}
    </div>
  );
}

function InjuryBadge({ status }: { status: string | null }) {
  if (!status || status === 'Active') return null;
  const colors: Record<string, string> = {
    Questionable: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    Doubtful: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    Out: 'bg-red-500/20 text-red-400 border-red-500/30',
    IR: 'bg-red-500/20 text-red-400 border-red-500/30',
    PUP: 'bg-red-500/20 text-red-400 border-red-500/30'
  };
  const cls = colors[status] ?? 'bg-gray-500/20 text-gray-400 border-gray-500/30';
  return (
    <span className={`${cls} inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none`}>
      {status}
    </span>
  );
}

interface PlayerRowProps {
  player: RatedPlayer | null;
  slotLabel: string;
  posColor: string;
  side: 'offense' | 'defense';
  matchupAdvantage?: 'strong' | 'slight' | 'neutral' | 'disadvantage';
}

function PlayerRow({ player, slotLabel, posColor, side, matchupAdvantage }: PlayerRowProps) {
  const advantageIndicator = useMemo(() => {
    if (!matchupAdvantage || matchupAdvantage === 'neutral') return null;
    const config = {
      strong: { icon: '>', color: 'text-emerald-400', label: 'Strong advantage' },
      slight: { icon: '>', color: 'text-emerald-300/70', label: 'Slight advantage' },
      disadvantage: { icon: '<', color: 'text-red-400', label: 'Disadvantage' }
    };
    const c = config[matchupAdvantage];
    if (!c) return null;
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={`${c.color} text-xs font-bold`}>{c.icon}</span>
          </TooltipTrigger>
          <TooltipContent side={side === 'offense' ? 'right' : 'left'}>
            <p className='text-xs'>{c.label}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }, [matchupAdvantage, side]);

  if (!player) {
    return (
      <div className='flex items-center gap-3 rounded-lg bg-black/20 px-3 py-2.5'>
        <div
          className='flex h-9 w-9 items-center justify-center rounded-lg text-xs font-bold text-white/60'
          style={{ backgroundColor: `${posColor}44` }}
        >
          {slotLabel}
        </div>
        <span className='text-sm text-white/30 italic'>Empty</span>
      </div>
    );
  }

  const isLowRated = player.rating < 65;

  return (
    <div
      className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors ${
        isLowRated
          ? 'bg-red-900/20 border border-red-500/20 hover:bg-red-900/30'
          : 'bg-white/5 hover:bg-white/10'
      }`}
    >
      {/* Position badge */}
      <div
        className='flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold uppercase text-white'
        style={{ backgroundColor: posColor }}
      >
        {slotLabel}
      </div>

      {/* Rating */}
      <RatingBadge rating={player.rating} />

      {/* Name + info */}
      <div className='min-w-0 flex-1'>
        <div className='flex items-center gap-1.5'>
          <span className='truncate text-sm font-semibold text-white'>
            {player.player_name}
          </span>
          <InjuryBadge status={player.injury_status} />
          {isLowRated && (
            <Icons.alertCircle className='h-3.5 w-3.5 shrink-0 text-red-400' />
          )}
        </div>
        {player.position_rank !== null && (
          <span className='text-[11px] text-white/40'>
            {player.position}#{player.position_rank}
          </span>
        )}
      </div>

      {/* Projection / matchup indicator */}
      <div className='flex items-center gap-2 shrink-0'>
        {advantageIndicator}
        {player.projected_points !== null ? (
          <span className='min-w-[3rem] text-right font-mono text-sm font-bold tabular-nums text-white'>
            {player.projected_points.toFixed(1)}
          </span>
        ) : (
          <span className='min-w-[3rem] text-right text-sm text-white/30'>--</span>
        )}
      </div>
    </div>
  );
}

function RowGroupLabel({ label }: { label: string }) {
  return (
    <div className='px-3 pt-4 pb-1'>
      <span className='text-[10px] font-semibold uppercase tracking-widest text-white/30'>
        {label}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Team panel (offense or defense side)
// ---------------------------------------------------------------------------

interface TeamPanelProps {
  team: string;
  side: 'offense' | 'defense';
  roster: Map<string, RatedPlayer | null>;
  opponentRatings?: Map<string, RatedPlayer | null>;
}

function TeamPanel({ team, side, roster, opponentRatings }: TeamPanelProps) {
  const color = getTeamColor(team);
  const secColor = TEAM_SECONDARY_COLORS[team] ?? '#333';
  const fullName = getTeamFullName(team);
  const slots = side === 'offense' ? OFFENSE_SLOTS : DEFENSE_SLOTS;

  // Compute matchup advantages for offense vs defense
  const getAdvantage = (slot: string): PlayerRowProps['matchupAdvantage'] => {
    if (side !== 'offense' || !opponentRatings) return 'neutral';
    const offPlayer = roster.get(slot);
    if (!offPlayer || offPlayer.position === 'OL') return 'neutral';

    // Map offense positions to defending positions
    const matchupMap: Record<string, string[]> = {
      WR1: ['CB1'],
      WR2: ['CB2'],
      WR3: ['CB2', 'SS'],
      TE1: ['LB1', 'SS'],
      RB1: ['LB2'],
      RB2: ['LB3'],
      QB1: ['DE1', 'DE2']
    };

    const defSlots = matchupMap[slot];
    if (!defSlots) return 'neutral';

    const defPlayers = defSlots.map((ds) => opponentRatings.get(ds)).filter(Boolean);
    if (defPlayers.length === 0) return 'neutral';

    const avgDefRating = defPlayers.reduce((sum, p) => sum + (p?.rating ?? 70), 0) / defPlayers.length;
    const diff = offPlayer.rating - avgDefRating;

    if (diff >= 15) return 'strong';
    if (diff >= 5) return 'slight';
    if (diff <= -10) return 'disadvantage';
    return 'neutral';
  };

  // Group by row
  const rows = new Map<string, typeof slots[number][]>();
  for (const slot of slots) {
    if (!rows.has(slot.row)) rows.set(slot.row, []);
    rows.get(slot.row)!.push(slot);
  }

  const rowLabels: Record<string, string> = {
    backfield: 'Backfield',
    receivers: 'Receivers',
    line: side === 'offense' ? 'Offensive Line' : 'Defensive Line',
    linebackers: 'Linebackers',
    secondary: 'Secondary'
  };

  // Team total projection
  const totalPts = Array.from(roster.values())
    .filter(Boolean)
    .reduce((sum, p) => sum + (p?.projected_points ?? 0), 0);

  return (
    <div className='flex-1 min-w-0'>
      {/* Team header */}
      <div
        className='relative overflow-hidden rounded-t-xl px-5 py-4'
        style={{
          background: `linear-gradient(135deg, ${color} 0%, ${color}dd 60%, ${secColor}88 100%)`
        }}
      >
        <div className='relative z-10'>
          <div className='flex items-center justify-between'>
            <div>
              <h3 className='text-xl font-black uppercase tracking-wide text-white'>
                {team}
              </h3>
              <p className='text-xs font-medium text-white/70'>{fullName}</p>
            </div>
            <div className='text-right'>
              <div className='text-xs font-medium uppercase text-white/50'>
                {side === 'offense' ? 'Offense' : 'Defense'}
              </div>
              {side === 'offense' && totalPts > 0 && (
                <div className='text-lg font-black tabular-nums text-white'>
                  {totalPts.toFixed(1)}
                  <span className='text-xs font-normal text-white/50 ml-1'>pts</span>
                </div>
              )}
            </div>
          </div>
        </div>
        {/* Decorative team logo background */}
        <div
          className='absolute -right-6 -top-6 h-28 w-28 rounded-full opacity-10'
          style={{ backgroundColor: secColor }}
        />
      </div>

      {/* Player rows */}
      <div
        className='space-y-0.5 rounded-b-xl p-2'
        style={{ backgroundColor: '#0f1318' }}
      >
        {Array.from(rows.entries()).map(([rowKey, rowSlots]) => (
          <div key={rowKey}>
            <RowGroupLabel label={rowLabels[rowKey] ?? rowKey} />
            <div className='space-y-1'>
              {rowSlots.map((slot) => (
                <PlayerRow
                  key={slot.slot}
                  player={roster.get(slot.slot) ?? null}
                  slotLabel={slot.label}
                  posColor={POS_COLORS[slot.pos] ?? '#6B7280'}
                  side={side}
                  matchupAdvantage={getAdvantage(slot.slot)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Matchup header bar (game info between panels)
// ---------------------------------------------------------------------------

function MatchupHeaderBar({
  homeTeam,
  awayTeam,
  prediction
}: {
  homeTeam: string;
  awayTeam: string;
  prediction: GamePrediction | null;
}) {
  const homeColor = getTeamColor(homeTeam);
  const awayColor = getTeamColor(awayTeam);

  return (
    <div className='relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 p-4 mb-6'>
      {/* Decorative team color streaks */}
      <div
        className='absolute left-0 top-0 bottom-0 w-1.5'
        style={{ backgroundColor: awayColor }}
      />
      <div
        className='absolute right-0 top-0 bottom-0 w-1.5'
        style={{ backgroundColor: homeColor }}
      />

      <div className='flex items-center justify-between px-4'>
        {/* Away team */}
        <div className='flex items-center gap-3'>
          <div
            className='flex h-12 w-12 items-center justify-center rounded-xl text-lg font-black text-white'
            style={{ backgroundColor: awayColor }}
          >
            {awayTeam.slice(0, 3)}
          </div>
          <div>
            <div className='text-base font-bold text-white'>{getTeamFullName(awayTeam)}</div>
            <div className='text-xs text-white/50'>Away</div>
          </div>
        </div>

        {/* Center: VS + prediction info */}
        <div className='text-center'>
          <div className='text-lg font-black text-white/20 tracking-widest'>VS</div>
          {prediction && (
            <div className='mt-1 space-y-0.5'>
              {prediction.vegas_spread !== null && (
                <div className='text-[11px] text-white/50'>
                  Line: <span className='font-mono text-white/70'>
                    {prediction.vegas_spread > 0 ? '+' : ''}
                    {prediction.vegas_spread.toFixed(1)}
                  </span>
                </div>
              )}
              {prediction.vegas_total !== null && (
                <div className='text-[11px] text-white/50'>
                  O/U: <span className='font-mono text-white/70'>
                    {prediction.vegas_total.toFixed(1)}
                  </span>
                </div>
              )}
              {prediction.confidence_tier && (
                <Badge
                  variant={prediction.confidence_tier === 'high' ? 'default' : 'secondary'}
                  className='mt-1 text-[10px]'
                >
                  {prediction.confidence_tier} confidence
                </Badge>
              )}
            </div>
          )}
        </div>

        {/* Home team */}
        <div className='flex items-center gap-3'>
          <div>
            <div className='text-right text-base font-bold text-white'>{getTeamFullName(homeTeam)}</div>
            <div className='text-right text-xs text-white/50'>Home</div>
          </div>
          <div
            className='flex h-12 w-12 items-center justify-center rounded-xl text-lg font-black text-white'
            style={{ backgroundColor: homeColor }}
          >
            {homeTeam.slice(0, 3)}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Matchup advantage summary
// ---------------------------------------------------------------------------

function MatchupAdvantages({
  offenseRoster,
  defenseRoster
}: {
  offenseRoster: Map<string, RatedPlayer | null>;
  defenseRoster: Map<string, RatedPlayer | null>;
}) {
  const matchups = [
    { off: 'WR1', def: 'CB1', label: 'WR1 vs CB1' },
    { off: 'WR2', def: 'CB2', label: 'WR2 vs CB2' },
    { off: 'TE1', def: 'LB1', label: 'TE vs LB' },
    { off: 'RB1', def: 'LB2', label: 'RB vs LB' }
  ];

  const edges = matchups
    .map(({ off, def, label }) => {
      const o = offenseRoster.get(off);
      const d = defenseRoster.get(def);
      if (!o || !d) return null;
      const diff = o.rating - d.rating;
      return { label, offPlayer: o, defPlayer: d, diff };
    })
    .filter(Boolean)
    .sort((a, b) => (b?.diff ?? 0) - (a?.diff ?? 0));

  if (edges.length === 0) return null;

  return (
    <div className='rounded-xl border border-white/10 bg-gray-900/50 p-4 mt-4'>
      <h4 className='text-xs font-semibold uppercase tracking-widest text-white/40 mb-3'>
        Key Matchups
      </h4>
      <div className='grid grid-cols-1 gap-2 sm:grid-cols-2'>
        {edges.map((edge) => {
          if (!edge) return null;
          const isAdvantage = edge.diff > 5;
          const isDisadvantage = edge.diff < -5;
          return (
            <div
              key={edge.label}
              className={`flex items-center justify-between rounded-lg px-3 py-2 ${
                isAdvantage
                  ? 'bg-emerald-900/20 border border-emerald-500/20'
                  : isDisadvantage
                    ? 'bg-red-900/20 border border-red-500/20'
                    : 'bg-white/5'
              }`}
            >
              <div className='flex items-center gap-2'>
                <RatingBadge rating={edge.offPlayer.rating} size='sm' />
                <div className='text-xs'>
                  <div className='font-semibold text-white'>{edge.offPlayer.player_name}</div>
                  <div className='text-white/40'>{edge.label}</div>
                </div>
              </div>
              <div className='flex items-center gap-2'>
                <span
                  className={`text-xs font-bold ${
                    isAdvantage ? 'text-emerald-400' : isDisadvantage ? 'text-red-400' : 'text-white/50'
                  }`}
                >
                  {edge.diff > 0 ? '+' : ''}{edge.diff}
                </span>
                <RatingBadge rating={edge.defPlayer.rating} size='sm' />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Team picker (compact for matchup page)
// ---------------------------------------------------------------------------

function CompactTeamPicker({
  selectedTeam,
  onSelectTeam,
  label
}: {
  selectedTeam: string | null;
  onSelectTeam: (team: string) => void;
  label: string;
}) {
  return (
    <div>
      <div className='text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2'>
        {label}
      </div>
      <div className='space-y-3'>
        {['AFC', 'NFC'].map((conf) => (
          <div key={conf}>
            <div className='text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60 mb-1.5'>
              {conf}
            </div>
            <div className='grid grid-cols-4 gap-1.5'>
              {DIVISIONS.filter((d) => d.conference === conf)
                .flatMap((d) => d.teams)
                .map((team) => {
                  const color = getTeamColor(team);
                  const isSelected = selectedTeam === team;
                  return (
                    <button
                      key={team}
                      onClick={() => onSelectTeam(team)}
                      className={`rounded-md px-2 py-1.5 text-xs font-bold transition-all ${
                        isSelected
                          ? 'text-white shadow-md scale-105'
                          : 'bg-muted hover:opacity-80'
                      }`}
                      style={
                        isSelected
                          ? { backgroundColor: color, boxShadow: `0 2px 8px ${color}44` }
                          : { borderLeft: `2px solid ${color}` }
                      }
                    >
                      {team}
                    </button>
                  );
                })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Defense placeholder builder (from projection data we can infer opponent)
// ---------------------------------------------------------------------------

/** Simple deterministic hash for consistent slot-level variance. */
function slotHash(team: string, slot: string): number {
  let h = 0;
  const s = `${team}:${slot}`;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return ((h % 10) + 10) % 10 - 5; // range: -5..4
}

function buildDefensiveRoster(team: string): Map<string, RatedPlayer | null> {
  const roster = new Map<string, RatedPlayer | null>();
  // Build placeholder defensive roster with position-typical ratings.
  // Real ratings would come from a defensive stats API.
  const defaults: Record<string, { name: string; rating: number }> = {
    DE1: { name: 'DE', rating: 72 },
    DT1: { name: 'DT', rating: 70 },
    DT2: { name: 'DT', rating: 68 },
    DE2: { name: 'DE', rating: 70 },
    LB1: { name: 'LB', rating: 71 },
    LB2: { name: 'LB', rating: 69 },
    LB3: { name: 'LB', rating: 67 },
    CB1: { name: 'CB', rating: 73 },
    CB2: { name: 'CB', rating: 68 },
    SS: { name: 'SS', rating: 70 },
    FS: { name: 'FS', rating: 71 }
  };

  for (const [slot, def] of Object.entries(defaults)) {
    roster.set(slot, {
      player_id: `${team}-${slot}`,
      player_name: `${team} ${def.name}`,
      team,
      position: slot.replace(/[0-9]/g, ''),
      projected_points: null,
      injury_status: null,
      rating: def.rating + slotHash(team, slot),
      position_rank: null
    });
  }

  return roster;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function MatchupSkeleton() {
  return (
    <div className='space-y-6'>
      <Skeleton className='h-24 w-full rounded-xl' />
      <div className='grid grid-cols-1 gap-4 lg:grid-cols-2'>
        <div className='space-y-1'>
          <Skeleton className='h-20 w-full rounded-t-xl' />
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className='h-12 w-full' />
          ))}
        </div>
        <div className='space-y-1'>
          <Skeleton className='h-20 w-full rounded-t-xl' />
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className='h-12 w-full' />
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function MatchupView() {
  const [season, setSeason] = useState(2026);
  const [week, setWeek] = useState(1);
  const [scoring, setScoring] = useState<ScoringFormat>('half_ppr');
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);

  // Fetch projections for ratings
  const {
    data: projData,
    isLoading: projLoading
  } = useQuery(projectionsQueryOptions(season, week, scoring));

  // Fetch predictions for schedule/matchup info
  const {
    data: predData,
    isLoading: predLoading
  } = useQuery(predictionsQueryOptions(season, week));

  const isLoading = projLoading || predLoading;
  const projections = projData?.projections ?? [];
  const predictions = predData?.predictions ?? [];

  // Ratings map
  const ratingsMap = useMemo(() => computeRatings(projections), [projections]);

  // Find the matchup for the selected team
  const matchup = useMemo<GamePrediction | null>(() => {
    if (!selectedTeam) return null;
    return (
      predictions.find(
        (p) => p.home_team === selectedTeam || p.away_team === selectedTeam
      ) ?? null
    );
  }, [selectedTeam, predictions]);

  // Determine opponent
  const opponent = useMemo(() => {
    if (!matchup || !selectedTeam) return null;
    return matchup.home_team === selectedTeam
      ? matchup.away_team
      : matchup.home_team;
  }, [matchup, selectedTeam]);

  const isHome = matchup?.home_team === selectedTeam;

  // Build rosters
  const offenseRoster = useMemo(() => {
    if (!selectedTeam) return new Map<string, RatedPlayer | null>();
    return buildOffensiveRoster(projections, selectedTeam, ratingsMap);
  }, [selectedTeam, projections, ratingsMap]);

  const defenseRoster = useMemo(() => {
    if (!opponent) return new Map<string, RatedPlayer | null>();
    return buildDefensiveRoster(opponent);
  }, [opponent]);

  return (
    <div className='space-y-6'>
      {/* Controls */}
      <div className='flex flex-wrap items-center gap-4'>
        <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
          <SelectTrigger className='w-28'>
            <SelectValue placeholder='Season' />
          </SelectTrigger>
          <SelectContent>
            {[2026, 2025, 2024, 2023].map((s) => (
              <SelectItem key={s} value={String(s)}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={String(week)} onValueChange={(v) => setWeek(Number(v))}>
          <SelectTrigger className='w-24'>
            <SelectValue placeholder='Week' />
          </SelectTrigger>
          <SelectContent>
            {Array.from({ length: 18 }, (_, i) => i + 1).map((w) => (
              <SelectItem key={w} value={String(w)}>
                Week {w}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={scoring} onValueChange={(v) => setScoring(v as ScoringFormat)}>
          <SelectTrigger className='w-32'>
            <SelectValue placeholder='Scoring' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='half_ppr'>Half PPR</SelectItem>
            <SelectItem value='ppr'>PPR</SelectItem>
            <SelectItem value='standard'>Standard</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Team picker */}
      <Card>
        <CardContent className='pt-6'>
          <CompactTeamPicker
            selectedTeam={selectedTeam}
            onSelectTeam={setSelectedTeam}
            label='Select a team to view matchup'
          />
        </CardContent>
      </Card>

      {/* Matchup display */}
      {selectedTeam && isLoading && <MatchupSkeleton />}

      {selectedTeam && !isLoading && !matchup && (
        <Card>
          <CardContent className='flex flex-col items-center justify-center py-12'>
            <Icons.info className='text-muted-foreground mb-2 h-8 w-8' />
            <p className='text-muted-foreground text-sm'>
              No matchup found for {getTeamFullName(selectedTeam)} in Week {week}.
            </p>
            <p className='text-muted-foreground mt-1 text-xs'>
              This team may be on bye or prediction data is not available for this week.
            </p>
          </CardContent>
        </Card>
      )}

      {selectedTeam && !isLoading && matchup && opponent && (
        <>
          {/* Game header bar */}
          <MatchupHeaderBar
            homeTeam={matchup.home_team}
            awayTeam={matchup.away_team}
            prediction={matchup}
          />

          {/* Split-screen panels */}
          <div className='grid grid-cols-1 gap-4 lg:grid-cols-2'>
            <TeamPanel
              team={selectedTeam}
              side='offense'
              roster={offenseRoster}
              opponentRatings={defenseRoster}
            />
            <TeamPanel
              team={opponent}
              side='defense'
              roster={defenseRoster}
            />
          </div>

          {/* Matchup advantages */}
          <MatchupAdvantages
            offenseRoster={offenseRoster}
            defenseRoster={defenseRoster}
          />

          {/* Matchup notes */}
          <div className='rounded-xl border border-white/10 bg-gray-900/50 p-4'>
            <h4 className='text-xs font-semibold uppercase tracking-widest text-white/40 mb-3'>
              Matchup Notes
            </h4>
            <div className='space-y-2 text-sm text-white/60'>
              <p>
                {getTeamFullName(selectedTeam)} ({isHome ? 'Home' : 'Away'}) vs{' '}
                {getTeamFullName(opponent)} ({isHome ? 'Away' : 'Home'})
              </p>
              {matchup.spread_edge !== null && Math.abs(matchup.spread_edge) >= 1.5 && (
                <p className='flex items-center gap-2'>
                  <Icons.trendingUp className='h-4 w-4 text-emerald-400' />
                  <span>
                    Model sees {Math.abs(matchup.spread_edge).toFixed(1)}-point spread edge.{' '}
                    <span className='text-white/80 font-medium'>
                      {matchup.ats_pick}
                    </span>
                  </span>
                </p>
              )}
              {matchup.total_edge !== null && Math.abs(matchup.total_edge) >= 1.5 && (
                <p className='flex items-center gap-2'>
                  <Icons.target className='h-4 w-4 text-blue-400' />
                  <span>
                    {Math.abs(matchup.total_edge).toFixed(1)}-point total edge.{' '}
                    <span className='text-white/80 font-medium'>
                      {matchup.ou_pick}
                    </span>
                  </span>
                </p>
              )}
              {/* Low-rated player callouts */}
              {Array.from(offenseRoster.values())
                .filter((p) => p && p.rating < 60 && p.position !== 'OL')
                .map((p) => (
                  <p key={p!.player_id} className='flex items-center gap-2'>
                    <Icons.alertCircle className='h-4 w-4 text-orange-400' />
                    <span>
                      <span className='text-white/80 font-medium'>{p!.player_name}</span>{' '}
                      ({p!.position}) rated just {p!.rating} -- possible injury replacement or
                      depth starter. Check news for context.
                    </span>
                  </p>
                ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
