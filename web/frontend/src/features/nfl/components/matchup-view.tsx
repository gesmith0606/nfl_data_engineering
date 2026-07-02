'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  predictionsQueryOptions,
  projectionsQueryOptions,
  teamDefenseMetricsQueryOptions,
  teamMatchupQueryOptions,
  teamRosterQueryOptions
} from '../api/queries';
import { useWeekParams } from '@/hooks/use-week-params';
import type {
  GamePrediction,
  PlayerProjection,
  PositionalDefenseRank,
  RosterPlayer,
  ScoringFormat,
  TeamDefenseMetricsResponse,
  TeamMatchupResponse,
  TeamRosterResponse
} from '../api/types';
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
import { EmptyState } from '@/components/EmptyState';
import { formatRelativeTime } from '@/lib/format-relative-time';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { getTeamFullName, TEAM_SECONDARY_COLORS } from '@/lib/nfl/team-meta';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { getPositionColor } from '@/lib/design-tokens';
import {
  DataLoadReveal,
  FadeIn,
  HoverLift,
  PressScale,
  Stagger
} from '@/lib/motion-primitives';
import MatchupFieldView from './matchup-field';

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
  // 'LA' (not 'LAR') — nflverse team code used by rosters/schedules/projections.
  { conference: 'NFC', division: 'West', teams: ['ARI', 'LA', 'SEA', 'SF'] }
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

/**
 * Offense slot → defense position that covers it. Used by getAdvantage() to
 * look up the opposing team's positional defense rank for each key matchup.
 */
const OFFENSE_TO_DEF_POSITION: Record<string, 'QB' | 'RB' | 'WR' | 'TE'> = {
  QB1: 'QB',
  RB1: 'RB',
  RB2: 'RB',
  WR1: 'WR',
  WR2: 'WR',
  WR3: 'WR',
  TE1: 'TE'
};

/**
 * Normalize raw roster injury_status codes into the user-facing labels the
 * InjuryBadge expects. Bronze rosters carry short codes (A01, R48, I01, P01);
 * turn them into 'Active' / 'Questionable' / 'Out' / 'IR' / 'PUP' so the
 * existing badge styling still applies.
 */
function normalizeInjuryStatus(status: string | null | undefined): string | null {
  if (!status) return null;
  const code = status.toUpperCase();
  // nfl-data-py status codes — see docs/NFL_DATA_DICTIONARY.md
  if (code.startsWith('A')) return 'Active';
  if (code.startsWith('R')) return 'IR';
  if (code.startsWith('I')) return 'Out';
  if (code.startsWith('P')) return 'PUP';
  if (code.startsWith('Q')) return 'Questionable';
  if (code.startsWith('D')) return 'Doubtful';
  // Fall through for already-normalized labels (e.g., 'Questionable').
  return status;
}

/**
 * Invert the backend's positional rating for display.
 *
 * Silver rank=1 = WEAKEST defense (most pts allowed). The backend maps
 * rank=1 → rating=99 under that semantic. For the defensive roster panel
 * we want the opposite: rating=99 should read as "tough defender, hard for
 * offense." This inverts so rating=50 (easy matchup) → 99 becomes 50, and
 * vice versa. See 64-03-SUMMARY.md for the full semantic discussion.
 */
function displayDefenseRating(backendRating: number): number {
  return Math.max(50, Math.min(99, 149 - backendRating));
}

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
  /** Stat basis behind the rating (PFR-derived, defense only) — tooltip copy. */
  rating_detail?: string | null;
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
 * Build an offensive roster. Skill positions (QB/RB/WR/TE) are populated from
 * the projections feed; OL slots (LT/LG/C/RG/RT) from the rosterResponse's
 * slot_hint assignments.
 *
 * Ratings: the backend's ``madden_rating`` (EA's live Madden OVR, PFR-stat
 * fallback) is authoritative when present — joined by player_id, then
 * normalized name. Players the backend couldn't rate keep the
 * projection-percentile rating from ``ratingsMap`` (better than nothing,
 * but inflated — see computeRatings).
 */
function buildOffensiveRoster(
  projections: PlayerProjection[],
  team: string,
  ratingsMap: Map<string, RatedPlayer>,
  rosterResponse: TeamRosterResponse | undefined
): Map<string, RatedPlayer | null> {
  const teamPlayers = projections.filter((p) => p.team === team);
  const byPos = new Map<string, PlayerProjection[]>();
  for (const p of teamPlayers) {
    if (!byPos.has(p.position)) byPos.set(p.position, []);
    byPos.get(p.position)!.push(p);
  }
  for (const [, group] of byPos) {
    group.sort((a, b) => b.projected_points - a.projected_points);
  }

  // Index the roster response for rating joins: by player_id and by name.
  const rosterById = new Map<string, RosterPlayer>();
  const rosterByName = new Map<string, RosterPlayer>();
  const olBySlot = new Map<string, RosterPlayer>();
  if (rosterResponse) {
    for (const p of rosterResponse.roster ?? []) {
      rosterById.set(p.player_id, p);
      rosterByName.set(p.player_name.toLowerCase(), p);
      if (p.slot_hint && ['LT', 'LG', 'C', 'RG', 'RT'].includes(p.slot_hint)) {
        olBySlot.set(p.slot_hint, p);
      }
    }
  }

  // Skill slots by backend hint (QB1/RB1/RB2/WR1-3/TE1) — the roster is the
  // authority on WHO is on the team today (Sleeper live corrections, EA-
  // rating-ordered depth); projections may carry stale team assignments.
  const skillBySlot = new Map<string, RosterPlayer>();
  if (rosterResponse) {
    for (const p of rosterResponse.roster ?? []) {
      if (p.slot_hint && !olBySlot.has(p.slot_hint)) {
        skillBySlot.set(p.slot_hint, p);
      }
    }
  }

  // Projections joined back in for the fantasy-points line on each chip.
  const projById = new Map<string, PlayerProjection>();
  const projByName = new Map<string, PlayerProjection>();
  for (const p of projections) {
    projById.set(p.player_id, p);
    projByName.set(p.player_name.toLowerCase(), p);
  }

  const used = new Set<string>();
  const roster = new Map<string, RatedPlayer | null>();

  const fromRosterPlayer = (rp: RosterPlayer, pos: string): RatedPlayer => {
    const proj = projById.get(rp.player_id) ?? projByName.get(rp.player_name.toLowerCase());
    const pctRating = proj ? ratingsMap.get(proj.player_id)?.rating : undefined;
    return {
      player_id: rp.player_id,
      player_name: rp.player_name,
      team,
      position: pos,
      projected_points: proj?.projected_points ?? null,
      injury_status: normalizeInjuryStatus(rp.injury_status ?? rp.status),
      // EA Madden OVR (or PFR fallback) from the backend; projection
      // percentile only when the backend couldn't rate; snap heuristic last.
      rating:
        rp.madden_rating ??
        pctRating ??
        ((rp.snap_pct_offense ?? 0) >= 0.8 ? 70 : 65),
      position_rank: proj?.position_rank ?? null,
      rating_detail: rp.rating_detail ?? null
    };
  };

  for (const slot of OFFENSE_SLOTS) {
    if (slot.pos === 'OL') {
      const olPlayer = olBySlot.get(slot.slot);
      roster.set(slot.slot, olPlayer ? fromRosterPlayer(olPlayer, 'OL') : null);
      continue;
    }

    // Prefer the roster's slot assignment (current team, EA-rating depth).
    const hintKey = slot.slot === 'TE1' ? 'TE1' : slot.slot;
    const rosterPick = skillBySlot.get(hintKey);
    if (rosterPick) {
      used.add(rosterPick.player_id);
      roster.set(slot.slot, fromRosterPlayer(rosterPick, slot.pos));
      continue;
    }

    // Fallback: highest-projected remaining player at the position.
    const group = byPos.get(slot.pos) ?? [];
    const next = group.find((p) => !used.has(p.player_id));
    if (next) {
      used.add(next.player_id);
      const base = ratingsMap.get(next.player_id) ?? null;
      const backend =
        rosterById.get(next.player_id) ??
        rosterByName.get(next.player_name.toLowerCase());
      if (base && backend?.madden_rating != null) {
        roster.set(slot.slot, {
          ...base,
          rating: backend.madden_rating,
          rating_detail: backend.rating_detail ?? null
        });
      } else {
        roster.set(slot.slot, base);
      }
    } else {
      roster.set(slot.slot, null);
    }
  }

  return roster;
}

/**
 * Build a defensive roster from the real backend roster + defense-metrics
 * responses. Replaces the old slotHash-driven placeholder.
 *
 * Strategy:
 *   1. Index roster players by their slot_hint (the backend already resolved
 *      CB1/CB2/DE1/DT1/LB1/LB2/LB3/SS/FS etc.).
 *   2. For each DEFENSE_SLOTS entry, look up the matching roster player.
 *   3. Derive a DISPLAY rating using the opposing-offense positional rank
 *      from defenseMetrics (inverted — high rating = tough defender) plus
 *      a snap-share starter bonus.
 */
function buildDefensiveRosterFromApi(
  rosterResponse: TeamRosterResponse | undefined,
  defenseMetrics: TeamDefenseMetricsResponse | undefined
): Map<string, RatedPlayer | null> {
  const result = new Map<string, RatedPlayer | null>();

  if (!rosterResponse) {
    for (const slot of DEFENSE_SLOTS) result.set(slot.slot, null);
    return result;
  }

  // Index by slot_hint (primary) with a fallback to depth_chart_position
  // buckets for roster responses that happen to omit a hint.
  const bySlot = new Map<string, RosterPlayer>();
  const bucket = new Map<string, RosterPlayer[]>();
  const rows = rosterResponse.roster ?? [];
  for (const p of rows) {
    if (p.slot_hint) bySlot.set(p.slot_hint, p);
    const dp = p.depth_chart_position ?? p.position;
    if (!bucket.has(dp)) bucket.set(dp, []);
    bucket.get(dp)!.push(p);
  }
  // Sort each bucket by defensive snap-pct desc for fallback selection.
  for (const [, arr] of bucket) {
    arr.sort((a, b) => (b.snap_pct_defense ?? 0) - (a.snap_pct_defense ?? 0));
  }

  // Invert backend ratings for a display-friendly "higher = tougher" scale.
  const overallDisplayRating = displayDefenseRating(
    defenseMetrics?.overall_def_rating ?? 72
  );
  const bestPositional = (pos: 'QB' | 'RB' | 'WR' | 'TE'): number | null => {
    const entry = defenseMetrics?.positional.find((p) => p.position === pos);
    if (!entry) return null;
    return displayDefenseRating(entry.rating);
  };
  const wrDisplay = bestPositional('WR') ?? overallDisplayRating;
  const rbDisplay = bestPositional('RB') ?? overallDisplayRating;
  const teDisplay = bestPositional('TE') ?? overallDisplayRating;
  const qbDisplay = bestPositional('QB') ?? overallDisplayRating;

  // Slot → candidate depth_chart_positions + anchor display-rating.
  // Anchor maps the slot to the offensive position it primarily defends:
  //  CB, S → WR; LB → RB/TE; DL → QB pressure.
  const slotConfig: Record<
    string,
    { candidates: string[]; anchor: number }
  > = {
    DE1: { candidates: ['DE', 'OLB'], anchor: qbDisplay },
    DE2: { candidates: ['DE', 'OLB'], anchor: qbDisplay },
    DT1: { candidates: ['DT', 'NT'], anchor: rbDisplay },
    DT2: { candidates: ['DT', 'NT'], anchor: rbDisplay },
    LB1: { candidates: ['MLB', 'ILB', 'LB', 'OLB'], anchor: rbDisplay },
    LB2: { candidates: ['ILB', 'MLB', 'LB'], anchor: teDisplay },
    LB3: { candidates: ['OLB', 'ILB', 'LB'], anchor: rbDisplay },
    CB1: { candidates: ['CB', 'DB'], anchor: wrDisplay },
    CB2: { candidates: ['CB', 'DB'], anchor: wrDisplay },
    SS: { candidates: ['SS', 'S', 'DB'], anchor: teDisplay },
    FS: { candidates: ['FS', 'S', 'DB'], anchor: wrDisplay }
  };

  const used = new Set<string>();
  for (const defSlot of DEFENSE_SLOTS) {
    const cfg = slotConfig[defSlot.slot];
    // Prefer the backend's slot_hint; fall back to depth-bucket pick.
    let picked = bySlot.get(defSlot.slot) ?? null;
    if (!picked && cfg) {
      for (const dp of cfg.candidates) {
        const arr = bucket.get(dp) ?? [];
        picked = arr.find((p) => !used.has(p.player_id)) ?? null;
        if (picked) break;
      }
    }

    if (!picked) {
      result.set(defSlot.slot, null);
      continue;
    }
    used.add(picked.player_id);

    // Rating: prefer the backend's real per-player Madden rating (PFR stat
    // percentiles). Players without rated production (rookies, special-teams
    // depth) fall back to the team positional anchor with a starter boost /
    // depth penalty so every rendered defender still carries a rating.
    let rating: number;
    if (picked.madden_rating != null) {
      rating = picked.madden_rating;
    } else {
      const baseRating = cfg?.anchor ?? overallDisplayRating;
      const starterBonus = (picked.snap_pct_defense ?? 0) >= 0.6 ? 3 : 0;
      const depthPenalty = defSlot.slot.endsWith('3') ? -4 : 0;
      rating = Math.min(
        99,
        Math.max(50, Math.round(baseRating + starterBonus + depthPenalty))
      );
    }

    result.set(defSlot.slot, {
      player_id: picked.player_id,
      player_name: picked.player_name,
      team: picked.team,
      position: picked.depth_chart_position ?? picked.position,
      projected_points: null,
      injury_status: normalizeInjuryStatus(picked.injury_status ?? picked.status),
      rating,
      position_rank: null,
      rating_detail: picked.rating_detail ?? null
    });
  }

  return result;
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
    sm: 'h-7 w-7 text-[length:var(--fs-xs)] leading-[var(--lh-xs)]',
    md: 'h-9 w-9 text-[length:var(--fs-sm)] leading-[var(--lh-sm)]',
    lg: 'h-11 w-11 text-[length:var(--fs-body)] leading-[var(--lh-body)]'
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
    <span
      className={`${cls} inline-flex items-center rounded border px-[var(--space-2)] py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold uppercase`}
    >
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
  advantageTooltip?: string;
}

function PlayerRow({
  player,
  slotLabel,
  posColor,
  side,
  matchupAdvantage,
  advantageTooltip
}: PlayerRowProps) {
  const advantageIndicator = useMemo(() => {
    if (!matchupAdvantage || matchupAdvantage === 'neutral') return null;
    const config = {
      strong: { icon: '>', color: 'text-emerald-400', label: 'Strong advantage' },
      slight: { icon: '>', color: 'text-emerald-300/70', label: 'Slight advantage' },
      disadvantage: { icon: '<', color: 'text-red-400', label: 'Disadvantage' }
    };
    const c = config[matchupAdvantage];
    if (!c) return null;
    const tooltipLabel = advantageTooltip ?? c.label;
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className={`${c.color} text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-bold`}
            >
              {c.icon}
            </span>
          </TooltipTrigger>
          <TooltipContent side={side === 'offense' ? 'right' : 'left'}>
            <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>{tooltipLabel}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }, [matchupAdvantage, side, advantageTooltip]);

  if (!player) {
    return (
      <div className='flex items-center gap-[var(--space-3)] rounded-lg bg-black/20 px-[var(--space-3)] py-[var(--space-2)]'>
        <div
          className='flex h-9 w-9 items-center justify-center rounded-lg text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-bold text-white/60'
          style={{ backgroundColor: `${posColor}44` }}
        >
          {slotLabel}
        </div>
        <span className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/30 italic'>
          Empty
        </span>
      </div>
    );
  }

  const isLowRated = player.rating < 65;

  return (
    <HoverLift lift={1}>
      <div
        className={`group flex items-center gap-[var(--space-3)] rounded-lg px-[var(--space-3)] py-[var(--space-2)] transition-colors duration-[var(--motion-fast)] ${
          isLowRated
            ? 'bg-red-900/20 border border-red-500/20 hover:bg-red-900/30'
            : 'bg-white/5 hover:bg-white/10'
        }`}
      >
        {/* Position badge */}
        <div
          className='flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-bold uppercase text-white'
          style={{ backgroundColor: posColor }}
        >
          {slotLabel}
        </div>

        {/* Rating — tooltip shows the stat basis when the backend provided one */}
        {player.rating_detail ? (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className='shrink-0 cursor-help'>
                  <RatingBadge rating={player.rating} />
                </span>
              </TooltipTrigger>
              <TooltipContent side={side === 'offense' ? 'right' : 'left'}>
                <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  {player.rating_detail}
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : (
          <RatingBadge rating={player.rating} />
        )}

        {/* Name + info */}
        <div className='min-w-0 flex-1'>
          <div className='flex items-center gap-[var(--space-2)]'>
            <span className='truncate text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-semibold text-white'>
              {player.player_name}
            </span>
            <InjuryBadge status={player.injury_status} />
            {isLowRated && (
              <Icons.alertCircle className='h-[var(--space-4)] w-[var(--space-4)] shrink-0 text-red-400' />
            )}
          </div>
          {player.position_rank !== null && (
            <span className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-white/40'>
              {player.position}#{player.position_rank}
            </span>
          )}
        </div>

        {/* Projection / matchup indicator */}
        <div className='flex items-center gap-[var(--space-2)] shrink-0'>
          {advantageIndicator}
          {player.projected_points !== null ? (
            <span className='min-w-[3rem] text-right font-mono text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-bold tabular-nums text-white'>
              {player.projected_points.toFixed(1)}
            </span>
          ) : (
            <span className='min-w-[3rem] text-right text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/30'>
              --
            </span>
          )}
        </div>
      </div>
    </HoverLift>
  );
}

function RowGroupLabel({ label }: { label: string }) {
  return (
    <div className='px-[var(--space-3)] pt-[var(--space-4)] pb-[var(--space-1)]'>
      <span className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold uppercase tracking-widest text-white/30'>
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
  /** Opposing team's defensive metrics — drives offense advantage tooltips. */
  opponentDefense?: TeamDefenseMetricsResponse;
}

function TeamPanel({ team, side, roster, opponentDefense }: TeamPanelProps) {
  const color = getTeamColor(team);
  // Brand-color fallback. Kept as a hex literal because it is concatenated with
  // an `88` alpha suffix in the gradient below (a CSS var() cannot take a hex
  // alpha suffix); only used when a team has no secondary color mapped.
  const secColor = TEAM_SECONDARY_COLORS[team] ?? '#333333';
  const fullName = getTeamFullName(team);
  const slots = side === 'offense' ? OFFENSE_SLOTS : DEFENSE_SLOTS;

  /**
   * Compute per-slot matchup advantage from real positional defense ranks.
   *
   * Rank semantics (from silver/defense/positional): rank=1 = MOST pts
   * allowed = easiest matchup for offense; rank=32 = fewest pts allowed =
   * hardest. So high rank for the opposing defense → strong advantage.
   */
  const advantageFor = (
    slot: string
  ): {
    level: PlayerRowProps['matchupAdvantage'];
    tooltip: string;
  } => {
    if (side !== 'offense' || !opponentDefense) {
      return { level: 'neutral', tooltip: '' };
    }
    const offPlayer = roster.get(slot);
    if (!offPlayer || offPlayer.position === 'OL') {
      return { level: 'neutral', tooltip: '' };
    }

    const defPos = OFFENSE_TO_DEF_POSITION[slot];
    if (!defPos) return { level: 'neutral', tooltip: '' };

    const pRank: PositionalDefenseRank | undefined = opponentDefense.positional.find(
      (p) => p.position === defPos
    );
    if (!pRank || pRank.rank == null) return { level: 'neutral', tooltip: '' };

    const rank = pRank.rank;
    const avg = pRank.avg_pts_allowed ?? null;
    const avgCopy = avg !== null ? ` (${avg.toFixed(1)} pts/game)` : '';
    const tooltip = `${opponentDefense.team} ranks #${rank}/32 vs ${defPos}${avgCopy}`;

    let level: PlayerRowProps['matchupAdvantage'] = 'neutral';
    if (rank <= 5) level = 'strong'; // offense faces weakest 5 → strongest advantage
    else if (rank <= 12) level = 'slight';
    else if (rank >= 25) level = 'disadvantage'; // offense faces top-8 defense
    return { level, tooltip };
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
        className='relative overflow-hidden rounded-t-xl px-[var(--space-5)] py-[var(--space-4)]'
        style={{
          background: `linear-gradient(135deg, ${color} 0%, ${color}dd 60%, ${secColor}88 100%)`
        }}
      >
        <div className='relative z-10'>
          <div className='flex items-center justify-between'>
            <div>
              <h3 className='text-[length:var(--fs-h3)] leading-[var(--lh-h3)] font-black uppercase tracking-wide text-white'>
                {team}
              </h3>
              <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium text-white/70'>
                {fullName}
              </p>
            </div>
            <div className='text-right'>
              <div className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium uppercase text-white/50'>
                {side === 'offense' ? 'Offense' : 'Defense'}
              </div>
              {side === 'offense' && totalPts > 0 && (
                <div className='text-[length:var(--fs-lg)] leading-[var(--lh-lg)] font-black tabular-nums text-white'>
                  {totalPts.toFixed(1)}
                  <span className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-normal text-white/50 ml-[var(--space-1)]'>
                    pts
                  </span>
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
        className='space-y-0.5 rounded-b-xl p-[var(--space-2)]'
        style={{ backgroundColor: 'var(--surface-scoreboard)' }}
      >
        {Array.from(rows.entries()).map(([rowKey, rowSlots]) => (
          <div key={rowKey}>
            <RowGroupLabel label={rowLabels[rowKey] ?? rowKey} />
            <Stagger step={0.03} className='space-y-[var(--space-1)]'>
              {rowSlots.map((slot) => {
                const adv = advantageFor(slot.slot);
                return (
                  <PlayerRow
                    key={slot.slot}
                    player={roster.get(slot.slot) ?? null}
                    slotLabel={slot.label}
                    posColor={getPositionColor(slot.pos)}
                    side={side}
                    matchupAdvantage={adv.level}
                    advantageTooltip={adv.tooltip || undefined}
                  />
                );
              })}
            </Stagger>
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
  prediction,
  schedule
}: {
  homeTeam: string;
  awayTeam: string;
  prediction: GamePrediction | null;
  /** Schedule-based matchup — supplies Vegas lines + kickoff before predictions exist. */
  schedule: TeamMatchupResponse | null;
}) {
  const homeColor = getTeamColor(homeTeam);
  const awayColor = getTeamColor(awayTeam);
  // Prefer the model prediction's lines; fall back to the schedule's Vegas
  // lines so the header stays informative months before predictions publish.
  const spread = prediction?.vegas_spread ?? schedule?.spread_line ?? null;
  const total = prediction?.vegas_total ?? schedule?.total_line ?? null;

  return (
    <div className='relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 p-[var(--space-3)] sm:p-[var(--pad-card)] mb-[var(--space-6)]'>
      {/* Decorative team color streaks */}
      <div
        className='absolute left-0 top-0 bottom-0 w-1.5'
        style={{ backgroundColor: awayColor }}
      />
      <div
        className='absolute right-0 top-0 bottom-0 w-1.5'
        style={{ backgroundColor: homeColor }}
      />

      {/* On mobile, squeeze team badges and drop the full-name line; use only
       *  the 3-letter code + Away/Home label. sm:+ restores the full layout. */}
      <div className='flex items-center justify-between gap-[var(--space-2)] px-[var(--space-2)] sm:px-[var(--space-4)]'>
        {/* Away team */}
        <div className='flex min-w-0 items-center gap-[var(--space-2)] sm:gap-[var(--space-3)]'>
          <div
            className='flex h-10 w-10 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-xl text-[length:var(--fs-sm)] sm:text-[length:var(--fs-lg)] leading-none font-black text-white'
            style={{ backgroundColor: awayColor }}
          >
            {awayTeam.slice(0, 3)}
          </div>
          <div className='min-w-0'>
            <div className='text-[length:var(--fs-sm)] sm:text-[length:var(--fs-body)] leading-tight font-bold text-white truncate'>
              <span className='hidden sm:inline'>{getTeamFullName(awayTeam)}</span>
              <span className='sm:hidden'>{awayTeam}</span>
            </div>
            <div className='text-[length:var(--fs-micro)] sm:text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/50'>
              Away
            </div>
          </div>
        </div>

        {/* Center: VS + prediction info */}
        <div className='shrink-0 text-center'>
          <div className='text-[length:var(--fs-sm)] sm:text-[length:var(--fs-lg)] leading-none font-black text-white/20 tracking-widest'>
            VS
          </div>
          <div className='mt-[var(--space-1)] space-y-0.5'>
            {schedule?.gameday && (
              <div className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-white/50'>
                {schedule.gameday}
                {schedule.gametime ? ` · ${schedule.gametime}` : ''}
              </div>
            )}
            {spread !== null && (
              <div className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-white/50'>
                Line: <span className='font-mono text-white/70'>
                  {spread > 0 ? '+' : ''}
                  {spread.toFixed(1)}
                </span>
              </div>
            )}
            {total !== null && (
              <div className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-white/50'>
                O/U: <span className='font-mono text-white/70'>
                  {total.toFixed(1)}
                </span>
              </div>
            )}
            {prediction?.confidence_tier && (
              <Badge
                variant={prediction.confidence_tier === 'high' ? 'default' : 'secondary'}
                className='mt-[var(--space-1)] text-[length:var(--fs-micro)] leading-[var(--lh-micro)]'
              >
                {prediction.confidence_tier}
              </Badge>
            )}
          </div>
        </div>

        {/* Home team */}
        <div className='flex min-w-0 items-center gap-[var(--space-2)] sm:gap-[var(--space-3)]'>
          <div className='min-w-0 text-right'>
            <div className='text-[length:var(--fs-sm)] sm:text-[length:var(--fs-body)] leading-tight font-bold text-white truncate'>
              <span className='hidden sm:inline'>{getTeamFullName(homeTeam)}</span>
              <span className='sm:hidden'>{homeTeam}</span>
            </div>
            <div className='text-[length:var(--fs-micro)] sm:text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-white/50'>
              Home
            </div>
          </div>
          <div
            className='flex h-10 w-10 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-xl text-[length:var(--fs-sm)] sm:text-[length:var(--fs-lg)] leading-none font-black text-white'
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
// Matchup advantage summary — now grounded in real positional defense ranks
// ---------------------------------------------------------------------------

interface MatchupAdvantagesProps {
  offenseRoster: Map<string, RatedPlayer | null>;
  opponentDefense?: TeamDefenseMetricsResponse;
}

function MatchupAdvantages({ offenseRoster, opponentDefense }: MatchupAdvantagesProps) {
  if (!opponentDefense) return null;

  const pairings: { slot: string; label: string; defPos: 'QB' | 'RB' | 'WR' | 'TE' }[] = [
    { slot: 'WR1', label: 'WR1 vs defense', defPos: 'WR' },
    { slot: 'WR2', label: 'WR2 vs defense', defPos: 'WR' },
    { slot: 'TE1', label: 'TE vs defense', defPos: 'TE' },
    { slot: 'RB1', label: 'RB vs defense', defPos: 'RB' }
  ];

  const edges = pairings
    .map(({ slot, label, defPos }) => {
      const offPlayer = offenseRoster.get(slot);
      const pRank = opponentDefense.positional.find((p) => p.position === defPos);
      if (!offPlayer || !pRank || pRank.rank == null) return null;
      return {
        label,
        offPlayer,
        rank: pRank.rank,
        avg: pRank.avg_pts_allowed,
        defPos,
        defDisplayRating: displayDefenseRating(pRank.rating)
      };
    })
    .filter(Boolean) as {
    label: string;
    offPlayer: RatedPlayer;
    rank: number;
    avg: number | null;
    defPos: 'QB' | 'RB' | 'WR' | 'TE';
    defDisplayRating: number;
  }[];

  // Sort so the strongest offense advantages (lowest opposing rank = weakest
  // defense) surface first.
  edges.sort((a, b) => b.rank - a.rank);

  if (edges.length === 0) return null;

  return (
    <div className='rounded-xl border border-white/10 bg-gray-900/50 p-[var(--pad-card)] mt-[var(--space-4)]'>
      <h4 className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold uppercase tracking-widest text-white/40 mb-[var(--space-3)]'>
        Key Matchups
      </h4>
      <Stagger className='grid grid-cols-1 gap-[var(--space-2)] sm:grid-cols-2'>
        {edges.map((edge) => {
          const isAdvantage = edge.rank <= 8; // weakest 8 defenses
          const isDisadvantage = edge.rank >= 25; // top-8 defenses
          const avgCopy = edge.avg !== null ? ` (${edge.avg.toFixed(1)} pts/g)` : '';
          const rankCopy = `#${edge.rank}/32 vs ${edge.defPos}${avgCopy}`;
          return (
            <HoverLift key={edge.label} lift={1}>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div
                      className={`flex items-center justify-between rounded-lg px-[var(--space-3)] py-[var(--space-2)] ${
                        isAdvantage
                          ? 'bg-emerald-900/20 border border-emerald-500/20'
                          : isDisadvantage
                            ? 'bg-red-900/20 border border-red-500/20'
                            : 'bg-white/5'
                      }`}
                    >
                      <div className='flex items-center gap-[var(--space-2)]'>
                        <RatingBadge rating={edge.offPlayer.rating} size='sm' />
                        <div className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                          <div className='font-semibold text-white'>
                            {edge.offPlayer.player_name}
                          </div>
                          <div className='text-white/40'>{edge.label}</div>
                        </div>
                      </div>
                      <div className='flex items-center gap-[var(--space-2)]'>
                        <span
                          className={`text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-bold ${
                            isAdvantage
                              ? 'text-emerald-400'
                              : isDisadvantage
                                ? 'text-red-400'
                                : 'text-white/50'
                          }`}
                        >
                          {rankCopy}
                        </span>
                        <RatingBadge rating={edge.defDisplayRating} size='sm' />
                      </div>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent side='top'>
                    <p className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                      {opponentDefense.team} allows {rankCopy.toLowerCase()} — fantasy pts/game
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </HoverLift>
          );
        })}
      </Stagger>
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
      <div className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold uppercase tracking-wider text-muted-foreground mb-[var(--space-2)]'>
        {label}
      </div>
      <div className='space-y-[var(--space-3)]'>
        {['AFC', 'NFC'].map((conf) => (
          <div key={conf}>
            <div className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-bold uppercase tracking-widest text-muted-foreground/60 mb-[var(--space-2)]'>
              {conf}
            </div>
            <div className='grid grid-cols-4 gap-[var(--space-2)]'>
              {DIVISIONS.filter((d) => d.conference === conf)
                .flatMap((d) => d.teams)
                .map((team) => {
                  const color = getTeamColor(team);
                  const isSelected = selectedTeam === team;
                  return (
                    <PressScale key={team}>
                      <button
                        onClick={() => onSelectTeam(team)}
                        className={`flex h-[var(--tap-min)] w-full items-center justify-center rounded-md px-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-bold transition-[background-color,box-shadow] duration-[var(--motion-fast)] ${
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
                    </PressScale>
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
// Loading skeleton
// ---------------------------------------------------------------------------

function MatchupSkeleton() {
  return (
    <div className='space-y-[var(--gap-section)]'>
      <Skeleton className='h-24 w-full rounded-xl' />
      <div className='grid grid-cols-1 gap-[var(--gap-stack)] lg:grid-cols-2'>
        <div className='space-y-[var(--space-1)]'>
          <Skeleton className='h-20 w-full rounded-t-xl' />
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className='h-[var(--space-12)] w-full' />
          ))}
        </div>
        <div className='space-y-[var(--space-1)]'>
          <Skeleton className='h-20 w-full rounded-t-xl' />
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className='h-[var(--space-12)] w-full' />
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
  // Resolve season/week from `/api/projections/latest-week` rather than the
  // schedule's current-week endpoint. The schedule resolves to a populated
  // (season, week) pair; the projections endpoint resolves to a (season,
  // week) pair where actual roster + projection data exists. During the
  // offseason these diverge — schedule says "2025 week 18" but no week-18
  // projection file exists, so the matchups page rendered every team with
  // empty rosters. `useWeekParams` walks back across seasons (max 3 hops)
  // until it finds a populated slice, matching the lineups + predictions
  // pages.
  const {
    season: resolvedSeason,
    week: resolvedWeek,
    setSeason: setSeasonParam,
    setWeek: setWeekParam,
    isResolving,
    dataAsOf: weekDataAsOf
  } = useWeekParams();

  const setSeason = (v: number) => setSeasonParam(v);
  const setWeek = (v: number) => setWeekParam(v);

  const [scoring, setScoring] = useState<ScoringFormat>('half_ppr');
  const [selectedTeam, setSelectedTeamState] = useState<string | null>(null);
  // 'sel-off' = selected team's offense vs opponent's defense; 'opp-off' = reverse.
  const [direction, setDirection] = useState<'sel-off' | 'opp-off'>('sel-off');
  const setSelectedTeam = (team: string) => {
    setSelectedTeamState(team);
    setDirection('sel-off');
  };

  const isOffseason503 = false; // useWeekParams handles offseason gracefully

  // --- Step 2: fetch projections + predictions for the resolved week ---
  // Both queries gated on `!isResolving` so they don't fire with the
  // fallback (DEFAULT_FALLBACK_SEASON, 1) values before the latest-week
  // resolver has settled — which would briefly show empty rosters.
  const { data: projData, isLoading: projLoading } = useQuery({
    ...projectionsQueryOptions(resolvedSeason, resolvedWeek, scoring),
    enabled: !isResolving
  });
  const { data: predData, isLoading: predLoading } = useQuery({
    ...predictionsQueryOptions(resolvedSeason, resolvedWeek),
    enabled: !isResolving
  });

  const projections = projData?.projections ?? [];
  const predictions = predData?.predictions ?? [];

  // Ratings map (projection-derived — unchanged from prior build)
  const ratingsMap = useMemo(() => computeRatings(projections), [projections]);

  // Resolve the opponent from the schedule (available months before model
  // predictions publish). The predictions feed is optional enrichment on top.
  const {
    data: matchup,
    isLoading: matchupLoading,
    isError: matchupError
  } = useQuery({
    ...teamMatchupQueryOptions(selectedTeam, resolvedSeason, resolvedWeek),
    enabled: !isResolving && !!selectedTeam
  });

  const isLoading =
    isResolving || projLoading || predLoading || (!!selectedTeam && matchupLoading);

  // Model prediction for the selected team's game — may not exist yet.
  const prediction = useMemo<GamePrediction | null>(() => {
    if (!selectedTeam) return null;
    return (
      predictions.find(
        (p) => p.home_team === selectedTeam || p.away_team === selectedTeam
      ) ?? null
    );
  }, [selectedTeam, predictions]);

  const opponent = matchup?.opponent ?? null;
  const isHome = matchup?.is_home ?? false;

  // --- Step 3: fetch rosters + defense metrics for BOTH directions ---
  // (selected offense vs opponent defense, and the reverse). React Query
  // caches per team/side so flipping the direction toggle is instant.
  const { data: offenseRosterData } = useQuery(
    teamRosterQueryOptions(selectedTeam, resolvedSeason, resolvedWeek, 'offense')
  );
  const { data: defenseRosterData } = useQuery(
    teamRosterQueryOptions(opponent, resolvedSeason, resolvedWeek, 'defense')
  );
  const { data: defenseMetricsData } = useQuery(
    teamDefenseMetricsQueryOptions(opponent, resolvedSeason, resolvedWeek)
  );
  const { data: oppOffenseRosterData } = useQuery(
    teamRosterQueryOptions(opponent, resolvedSeason, resolvedWeek, 'offense')
  );
  const { data: selDefenseRosterData } = useQuery(
    teamRosterQueryOptions(selectedTeam, resolvedSeason, resolvedWeek, 'defense')
  );
  const { data: selDefenseMetricsData } = useQuery(
    teamDefenseMetricsQueryOptions(selectedTeam, resolvedSeason, resolvedWeek)
  );

  // Build rosters — both directions
  const offenseRoster = useMemo(() => {
    if (!selectedTeam) return new Map<string, RatedPlayer | null>();
    return buildOffensiveRoster(projections, selectedTeam, ratingsMap, offenseRosterData);
  }, [selectedTeam, projections, ratingsMap, offenseRosterData]);

  const defenseRoster = useMemo(() => {
    return buildDefensiveRosterFromApi(defenseRosterData, defenseMetricsData);
  }, [defenseRosterData, defenseMetricsData]);

  const oppOffenseRoster = useMemo(() => {
    if (!opponent) return new Map<string, RatedPlayer | null>();
    return buildOffensiveRoster(projections, opponent, ratingsMap, oppOffenseRosterData);
  }, [opponent, projections, ratingsMap, oppOffenseRosterData]);

  const selDefenseRoster = useMemo(() => {
    return buildDefensiveRosterFromApi(selDefenseRosterData, selDefenseMetricsData);
  }, [selDefenseRosterData, selDefenseMetricsData]);

  // Which direction is on screen: selected team's offense (default) or the
  // opponent's offense. Both field views pair each offensive player with the
  // defender aligned across from him.
  const active =
    direction === 'sel-off'
      ? {
          offTeam: selectedTeam ?? '',
          defTeam: opponent ?? '',
          offense: offenseRoster,
          defense: defenseRoster,
          defMetrics: defenseMetricsData
        }
      : {
          offTeam: opponent ?? '',
          defTeam: selectedTeam ?? '',
          offense: oppOffenseRoster,
          defense: selDefenseRoster,
          defMetrics: selDefenseMetricsData
        };

  // Fallback banner: any API response had to walk back to a prior season.
  const anyFallback = Boolean(
    offenseRosterData?.fallback ||
      defenseRosterData?.fallback ||
      defenseMetricsData?.fallback
  );
  const fallbackSeason =
    offenseRosterData?.fallback_season ??
    defenseRosterData?.fallback_season ??
    defenseMetricsData?.fallback_season ??
    null;

  // Freshness timestamp — pull from whichever payload carries generated_at
  // first; silent when nothing is available (plan 70-01: no "Unknown" label).
  const dataAsOf: string | null =
    predData?.generated_at ?? projData?.generated_at ?? weekDataAsOf ?? null;

  return (
    <FadeIn className='space-y-[var(--gap-section)]'>
      {/* Controls — mobile: 3-column grid of equal selects so all fit at 375px;
       *  sm+: flex-wrap natural widths. */}
      <div className='grid grid-cols-3 gap-[var(--space-2)] sm:flex sm:flex-wrap sm:items-center sm:gap-[var(--gap-stack)]'>
        <Select
          value={String(resolvedSeason)}
          onValueChange={(v) => setSeason(Number(v))}
        >
          <SelectTrigger className='h-[var(--tap-min)] w-full sm:h-9 sm:w-28'>
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

        <Select value={String(resolvedWeek)} onValueChange={(v) => setWeek(Number(v))}>
          <SelectTrigger className='h-[var(--tap-min)] w-full sm:h-9 sm:w-28'>
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
          <SelectTrigger className='h-[var(--tap-min)] w-full sm:h-9 sm:w-32'>
            <SelectValue placeholder='Scoring' />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='half_ppr'>Half PPR</SelectItem>
            <SelectItem value='ppr'>PPR</SelectItem>
            <SelectItem value='standard'>Standard</SelectItem>
          </SelectContent>
        </Select>

        {/* Freshness chip (phase 70-01). Silent when no generated_at. */}
        {dataAsOf ? (
          <Badge
            variant='outline'
            className='ml-auto h-[var(--tap-min)] items-center text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground sm:h-9'
          >
            Updated {formatRelativeTime(dataAsOf)}
          </Badge>
        ) : null}
      </div>

      {/* Offseason empty state (phase 70-01). When /api/teams/current-week
       *  returns 503 it signals the offseason — surface the expected state
       *  as a friendly card (NOT styled as an error) and keep the team
       *  picker below so users can still explore preseason previews. */}
      {isOffseason503 && (
        <EmptyState
          icon={Icons.calendar}
          title='No games this week'
          description="The season hasn't started yet — pick a team below to browse the preseason preview."
          dataAsOf={dataAsOf}
        />
      )}

      {/* Fallback banner */}
      {anyFallback && (
        <div className='rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-yellow-300/80'>
          Showing data from the most recent available season
          {fallbackSeason ? ` (${fallbackSeason})` : ''} — current-season data is not yet
          published.
        </div>
      )}

      {/* Team picker */}
      <Card>
        <CardContent className='pt-[var(--space-6)]'>
          <CompactTeamPicker
            selectedTeam={selectedTeam}
            onSelectTeam={setSelectedTeam}
            label='Select a team to view matchup'
          />
        </CardContent>
      </Card>

      {/* Matchup display */}
      {selectedTeam && (
        <DataLoadReveal loading={isLoading} skeleton={<MatchupSkeleton />}>
          {matchup?.is_bye ? (
            <EmptyState
              icon={Icons.calendar}
              title='Bye week'
              description={`${getTeamFullName(selectedTeam)} has no game in Week ${resolvedWeek}.`}
              dataAsOf={dataAsOf}
            />
          ) : !matchup || matchupError ? (
            <EmptyState
              icon={Icons.calendar}
              title='No matchup found'
              description={`Schedule data is not available for ${getTeamFullName(selectedTeam)} in Week ${resolvedWeek} of ${resolvedSeason}.`}
              dataAsOf={dataAsOf}
            />
          ) : !opponent || !matchup.home_team || !matchup.away_team ? null : (
            <div className='space-y-[var(--gap-section)]'>
              {/* Game header bar */}
              <MatchupHeaderBar
                homeTeam={matchup.home_team}
                awayTeam={matchup.away_team}
                prediction={prediction}
                schedule={matchup}
              />

              {/* Direction toggle: which offense is on the field */}
              <div className='flex flex-wrap gap-[var(--space-2)]'>
                {(
                  [
                    ['sel-off', selectedTeam, opponent],
                    ['opp-off', opponent, selectedTeam]
                  ] as const
                ).map(([dir, offT, defT]) => (
                  <PressScale key={dir}>
                    <button
                      onClick={() => setDirection(dir)}
                      className={`rounded-lg px-[var(--space-4)] py-[var(--space-2)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-bold transition-colors duration-[var(--motion-fast)] ${
                        direction === dir
                          ? 'text-white shadow-md'
                          : 'bg-muted text-muted-foreground hover:opacity-80'
                      }`}
                      style={
                        direction === dir
                          ? { backgroundColor: getTeamColor(offT) }
                          : undefined
                      }
                    >
                      {offT} Offense vs {defT} Defense
                    </button>
                  </PressScale>
                ))}
              </div>

              {/* Field formation (md+): offense lined up across from the
                  defense, each defender column-aligned to his assignment. */}
              <div className='hidden md:block'>
                <MatchupFieldView
                  offenseTeam={active.offTeam}
                  defenseTeam={active.defTeam}
                  offenseRoster={active.offense}
                  defenseRoster={active.defense}
                />
              </div>

              {/* Mobile fallback: stacked list panels for the active direction */}
              <div className='grid grid-cols-1 gap-[var(--gap-stack)] md:hidden'>
                <TeamPanel
                  team={active.offTeam}
                  side='offense'
                  roster={active.offense}
                  opponentDefense={active.defMetrics}
                />
                <TeamPanel
                  team={active.defTeam}
                  side='defense'
                  roster={active.defense}
                />
              </div>

              {/* Matchup advantages (positional defense ranks) */}
              <MatchupAdvantages
                offenseRoster={active.offense}
                opponentDefense={active.defMetrics}
              />

              {/* Matchup notes */}
              <div className='rounded-xl border border-white/10 bg-gray-900/50 p-[var(--pad-card)]'>
                <h4 className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold uppercase tracking-widest text-white/40 mb-[var(--space-3)]'>
                  Matchup Notes
                </h4>
                <div className='space-y-[var(--space-2)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/60'>
                  <p>
                    {getTeamFullName(selectedTeam)} ({isHome ? 'Home' : 'Away'}) vs{' '}
                    {getTeamFullName(opponent)} ({isHome ? 'Away' : 'Home'})
                  </p>
                  {!prediction && (
                    <p className='flex items-center gap-[var(--space-2)] text-white/40'>
                      <Icons.info className='h-[var(--space-4)] w-[var(--space-4)]' />
                      <span>
                        Model prediction not yet published for this game — lines
                        shown are the schedule&apos;s Vegas numbers.
                      </span>
                    </p>
                  )}
                  {prediction?.spread_edge != null &&
                    Math.abs(prediction.spread_edge) >= 1.5 && (
                      <p className='flex items-center gap-[var(--space-2)]'>
                        <Icons.trendingUp className='h-[var(--space-4)] w-[var(--space-4)] text-emerald-400' />
                        <span>
                          Model sees {Math.abs(prediction.spread_edge).toFixed(1)}-point spread edge.{' '}
                          <span className='text-white/80 font-medium'>{prediction.ats_pick}</span>
                        </span>
                      </p>
                    )}
                  {prediction?.total_edge != null &&
                    Math.abs(prediction.total_edge) >= 1.5 && (
                      <p className='flex items-center gap-[var(--space-2)]'>
                        <Icons.target className='h-[var(--space-4)] w-[var(--space-4)] text-blue-400' />
                        <span>
                          {Math.abs(prediction.total_edge).toFixed(1)}-point total edge.{' '}
                          <span className='text-white/80 font-medium'>{prediction.ou_pick}</span>
                        </span>
                      </p>
                    )}
                  {active.defMetrics && (
                    <p className='flex items-center gap-[var(--space-2)]'>
                      <Icons.shield className='h-[var(--space-4)] w-[var(--space-4)] text-indigo-300' />
                      <span>
                        {active.defTeam} defense: SoS rank{' '}
                        <span className='text-white/80 font-medium'>
                          {active.defMetrics.def_sos_rank ?? 'N/A'}
                        </span>
                        , allows WR #{active.defMetrics.positional.find((p) => p.position === 'WR')?.rank ?? '—'},
                        {' '}RB #{active.defMetrics.positional.find((p) => p.position === 'RB')?.rank ?? '—'},
                        {' '}TE #{active.defMetrics.positional.find((p) => p.position === 'TE')?.rank ?? '—'}
                      </span>
                    </p>
                  )}
                  {/* Low-rated player callouts */}
                  {Array.from(active.offense.values())
                    .filter((p) => p && p.rating < 60 && p.position !== 'OL')
                    .map((p) => (
                      <p
                        key={p!.player_id}
                        className='flex items-center gap-[var(--space-2)]'
                      >
                        <Icons.alertCircle className='h-[var(--space-4)] w-[var(--space-4)] text-orange-400' />
                        <span>
                          <span className='text-white/80 font-medium'>{p!.player_name}</span>{' '}
                          ({p!.position}) rated just {p!.rating} -- possible injury replacement or
                          depth starter. Check news for context.
                        </span>
                      </p>
                    ))}
                </div>
              </div>
            </div>
          )}
        </DataLoadReveal>
      )}
    </FadeIn>
  );
}
