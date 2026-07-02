'use client';

/**
 * Field-formation matchup view: one team's offense lined up on a football
 * field directly across from the other team's defense, with each defender
 * column-aligned to the offensive player he primarily covers so rating
 * mismatches are visible at a glance.
 *
 * Column map (9 cols):
 *   1:WR1  2:WR3(slot)  3:LT  4:LG  5:C/QB/RB  6:RG  7:RT  8:TE  9:WR2
 * Defense mirrors: CB1(1) SS(2) DE1(3) DT1(4) LB1(5) DT2(6) DE2(7) LB2(8) CB2(9),
 * FS deep over the middle.
 *
 * Each aligned pair gets a rating-differential badge on the offensive chip:
 * green (edge to attack) when the offensive player out-rates his cover by 8+,
 * red when the defender out-rates him by 8+. The QB is paired against the
 * defense's best pass rusher.
 */

import { useMemo } from 'react';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { getTeamFullName } from '@/lib/nfl/team-meta';
import { getPositionColor } from '@/lib/design-tokens';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { Stagger, HoverLift } from '@/lib/motion-primitives';

/** Mirrors RatedPlayer in matchup-view.tsx (kept structural to avoid a cycle). */
export interface FieldPlayer {
  player_id: string;
  player_name: string;
  team: string;
  position: string;
  projected_points: number | null;
  injury_status: string | null;
  rating: number;
  position_rank: number | null;
  rating_detail?: string | null;
}

type RosterMap = Map<string, FieldPlayer | null>;

/** Offense slot ↔ the defensive slot that primarily covers it. */
const MATCHUP_PAIRS: { off: string; def: string }[] = [
  { off: 'WR1', def: 'CB1' },
  { off: 'WR2', def: 'CB2' },
  { off: 'WR3', def: 'SS' },
  { off: 'TE1', def: 'LB2' },
  { off: 'RB1', def: 'LB1' },
  { off: 'LT', def: 'DE1' },
  { off: 'LG', def: 'DT1' },
  { off: 'RG', def: 'DT2' },
  { off: 'RT', def: 'DE2' }
];

/** Rating gap that counts as an exploitable mismatch. */
const MISMATCH_THRESHOLD = 8;

interface PairInfo {
  diff: number;
  vs: FieldPlayer;
}

/** diff > 0: offensive player out-rates his cover (edge to attack). */
function computePairs(offense: RosterMap, defense: RosterMap): Map<string, PairInfo> {
  const pairs = new Map<string, PairInfo>();
  for (const { off, def } of MATCHUP_PAIRS) {
    const o = offense.get(off);
    const d = defense.get(def);
    if (o && d) pairs.set(off, { diff: o.rating - d.rating, vs: d });
  }
  // QB faces the defense's best pass rusher.
  const qb = offense.get('QB1');
  const rushers = ['DE1', 'DE2', 'DT1', 'DT2']
    .map((s) => defense.get(s))
    .filter(Boolean) as FieldPlayer[];
  if (qb && rushers.length) {
    const best = rushers.reduce((a, b) => (b.rating > a.rating ? b : a));
    pairs.set('QB1', { diff: qb.rating - best.rating, vs: best });
  }
  return pairs;
}

function ratingBg(rating: number): string {
  if (rating >= 90) return 'bg-emerald-500';
  if (rating >= 80) return 'bg-blue-500';
  if (rating >= 70) return 'bg-yellow-500';
  if (rating >= 60) return 'bg-orange-500';
  return 'bg-red-500';
}

function ChipTooltip({
  children,
  lines
}: {
  children: React.ReactNode;
  lines: string[];
}) {
  if (!lines.length) return <>{children}</>;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent side='top'>
          {lines.map((l) => (
            <p key={l} className='text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
              {l}
            </p>
          ))}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function FieldChip({
  player,
  slotLabel,
  pair
}: {
  player: FieldPlayer | null;
  slotLabel: string;
  /** Rating differential vs the aligned opponent (offense chips only). */
  pair?: PairInfo;
}) {
  if (!player) {
    return (
      <div className='flex h-full min-h-[3.25rem] w-full items-center justify-center rounded-lg border border-dashed border-white/15 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] text-white/25'>
        {slotLabel}
      </div>
    );
  }

  const posColor = getPositionColor(
    ['LT', 'LG', 'C', 'RG', 'RT'].includes(slotLabel) ? 'OL' : player.position
  );
  const isExploit = pair !== undefined && pair.diff >= MISMATCH_THRESHOLD;
  const isDanger = pair !== undefined && pair.diff <= -MISMATCH_THRESHOLD;
  const injured = player.injury_status && player.injury_status !== 'Active';

  const tooltipLines: string[] = [];
  if (pair) {
    tooltipLines.push(
      `${player.player_name} (${player.rating}) vs ${pair.vs.player_name} (${pair.vs.rating})`
    );
  }
  if (player.rating_detail) tooltipLines.push(player.rating_detail);
  if (injured) tooltipLines.push(`Status: ${player.injury_status}`);

  const ring = isExploit
    ? 'ring-2 ring-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.35)]'
    : isDanger
      ? 'ring-2 ring-red-400/80 shadow-[0_0_12px_rgba(248,113,113,0.3)]'
      : 'ring-1 ring-white/10';

  return (
    <ChipTooltip lines={tooltipLines}>
      <div className='relative w-full'>
        <HoverLift lift={2}>
          <div
            className={`relative w-full cursor-help rounded-lg bg-black/60 px-[var(--space-1)] py-[var(--space-1)] text-center backdrop-blur-sm ${ring}`}
            style={{ borderTop: `3px solid ${posColor}` }}
          >
            <div className='flex items-center justify-center gap-[var(--space-1)]'>
              <span
                className={`${ratingBg(player.rating)} inline-flex h-6 w-6 shrink-0 items-center justify-center rounded font-black text-white text-[length:var(--fs-xs)] leading-none`}
              >
                {player.rating}
              </span>
              <span className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-bold uppercase text-white/50'>
                {slotLabel}
              </span>
            </div>
            <div
              className={`mt-0.5 truncate text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold ${injured ? 'text-red-300' : 'text-white'}`}
            >
              {player.player_name}
            </div>
            {player.projected_points !== null && (
              <div className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] tabular-nums text-white/50'>
                {player.projected_points.toFixed(1)} pts
              </div>
            )}
            {/* Rating differential badge */}
            {pair !== undefined && Math.abs(pair.diff) >= MISMATCH_THRESHOLD && (
              <span
                className={`absolute -right-1.5 -top-2 rounded px-1 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-black text-white ${
                  pair.diff > 0 ? 'bg-emerald-500' : 'bg-red-500'
                }`}
              >
                {pair.diff > 0 ? `+${pair.diff}` : pair.diff}
              </span>
            )}
          </div>
        </HoverLift>
      </div>
    </ChipTooltip>
  );
}

/** One cell of the 9-column formation grid. */
function Cell({
  col,
  span = 1,
  children
}: {
  col: number;
  span?: number;
  children: React.ReactNode;
}) {
  return (
    <div
      className='flex items-stretch justify-center'
      style={{ gridColumn: `${col} / span ${span}` }}
    >
      {children}
    </div>
  );
}

function YardLine({ top }: { top: string }) {
  return (
    <div
      className='absolute left-[var(--space-4)] right-[var(--space-4)] h-px bg-white/10'
      style={{ top }}
    />
  );
}

export interface MatchupFieldViewProps {
  offenseTeam: string;
  defenseTeam: string;
  offenseRoster: RosterMap;
  defenseRoster: RosterMap;
}

export default function MatchupFieldView({
  offenseTeam,
  defenseTeam,
  offenseRoster,
  defenseRoster
}: MatchupFieldViewProps) {
  const offColor = getTeamColor(offenseTeam);
  const defColor = getTeamColor(defenseTeam);

  const pairs = useMemo(
    () => computePairs(offenseRoster, defenseRoster),
    [offenseRoster, defenseRoster]
  );

  // Top exploitable pairings (offense out-rates cover), for the strip below.
  const exploits = useMemo(() => {
    return [...pairs.entries()]
      .filter(([, p]) => Math.abs(p.diff) >= MISMATCH_THRESHOLD)
      .sort((a, b) => b[1].diff - a[1].diff)
      .slice(0, 4);
  }, [pairs]);

  const off = (slot: string) => offenseRoster.get(slot) ?? null;
  const def = (slot: string) => defenseRoster.get(slot) ?? null;

  const grid = 'grid grid-cols-9 gap-[var(--space-2)]';

  return (
    <div>
      <div
        className='relative overflow-hidden rounded-xl'
        style={{ background: 'linear-gradient(to bottom, #24491f, #2d5a27 48%, #2d5a27 52%, #1a3a17)' }}
      >
        <YardLine top='18%' />
        <YardLine top='34%' />
        <YardLine top='66%' />
        <YardLine top='82%' />

        {/* Defense header */}
        <div className='relative z-10 flex items-center justify-between px-[var(--space-4)] pt-[var(--space-3)]'>
          <div
            className='rounded-lg px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-black uppercase tracking-wide text-white'
            style={{ backgroundColor: `${defColor}cc` }}
          >
            {defenseTeam} Defense
          </div>
          <span className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] uppercase tracking-widest text-white/40'>
            {getTeamFullName(defenseTeam)}
          </span>
        </div>

        <Stagger step={0.02} className='relative z-10 space-y-[var(--space-3)] px-[var(--space-3)] py-[var(--space-4)] sm:px-[var(--space-5)]'>
          {/* Deep safety */}
          <div className={grid}>
            <Cell col={5}>
              <FieldChip player={def('FS')} slotLabel='FS' />
            </Cell>
          </div>

          {/* Second level: SS over the slot, LB1 in the middle, LB2 over the TE */}
          <div className={grid}>
            <Cell col={2}>
              <FieldChip player={def('SS')} slotLabel='SS' />
            </Cell>
            <Cell col={5}>
              <FieldChip player={def('LB1')} slotLabel='LB1' />
            </Cell>
            <Cell col={8}>
              <FieldChip player={def('LB2')} slotLabel='LB2' />
            </Cell>
          </div>

          {/* Front: press corners wide, DL over the tackles/guards */}
          <div className={grid}>
            <Cell col={1}>
              <FieldChip player={def('CB1')} slotLabel='CB1' />
            </Cell>
            <Cell col={3}>
              <FieldChip player={def('DE1')} slotLabel='DE1' />
            </Cell>
            <Cell col={4}>
              <FieldChip player={def('DT1')} slotLabel='DT1' />
            </Cell>
            <Cell col={5}>
              <FieldChip player={def('LB3')} slotLabel='LB3' />
            </Cell>
            <Cell col={6}>
              <FieldChip player={def('DT2')} slotLabel='DT2' />
            </Cell>
            <Cell col={7}>
              <FieldChip player={def('DE2')} slotLabel='DE2' />
            </Cell>
            <Cell col={9}>
              <FieldChip player={def('CB2')} slotLabel='CB2' />
            </Cell>
          </div>

          {/* Line of scrimmage */}
          <div className='flex items-center gap-[var(--space-3)] py-[var(--space-1)]'>
            <div className='h-0.5 flex-1 bg-white/25' />
            <span className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-medium uppercase tracking-widest text-white/40'>
              Line of Scrimmage
            </span>
            <div className='h-0.5 flex-1 bg-white/25' />
          </div>

          {/* Offense front: receivers wide, OL inside, TE attached */}
          <div className={grid}>
            <Cell col={1}>
              <FieldChip player={off('WR1')} slotLabel='WR1' pair={pairs.get('WR1')} />
            </Cell>
            <Cell col={2}>
              <FieldChip player={off('WR3')} slotLabel='WR3' pair={pairs.get('WR3')} />
            </Cell>
            <Cell col={3}>
              <FieldChip player={off('LT')} slotLabel='LT' pair={pairs.get('LT')} />
            </Cell>
            <Cell col={4}>
              <FieldChip player={off('LG')} slotLabel='LG' pair={pairs.get('LG')} />
            </Cell>
            <Cell col={5}>
              <FieldChip player={off('C')} slotLabel='C' />
            </Cell>
            <Cell col={6}>
              <FieldChip player={off('RG')} slotLabel='RG' pair={pairs.get('RG')} />
            </Cell>
            <Cell col={7}>
              <FieldChip player={off('RT')} slotLabel='RT' pair={pairs.get('RT')} />
            </Cell>
            <Cell col={8}>
              <FieldChip player={off('TE1')} slotLabel='TE' pair={pairs.get('TE1')} />
            </Cell>
            <Cell col={9}>
              <FieldChip player={off('WR2')} slotLabel='WR2' pair={pairs.get('WR2')} />
            </Cell>
          </div>

          {/* QB */}
          <div className={grid}>
            <Cell col={5}>
              <FieldChip player={off('QB1')} slotLabel='QB' pair={pairs.get('QB1')} />
            </Cell>
          </div>

          {/* Backfield */}
          <div className={grid}>
            <Cell col={4}>
              <FieldChip player={off('RB1')} slotLabel='RB1' pair={pairs.get('RB1')} />
            </Cell>
            <Cell col={6}>
              <FieldChip player={off('RB2')} slotLabel='RB2' />
            </Cell>
          </div>
        </Stagger>

        {/* Offense header */}
        <div className='relative z-10 flex items-center justify-between px-[var(--space-4)] pb-[var(--space-3)]'>
          <div
            className='rounded-lg px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-black uppercase tracking-wide text-white'
            style={{ backgroundColor: `${offColor}cc` }}
          >
            {offenseTeam} Offense
          </div>
          <span className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] uppercase tracking-widest text-white/40'>
            {getTeamFullName(offenseTeam)}
          </span>
        </div>
        <div className='h-[var(--space-2)] w-full' style={{ backgroundColor: offColor }} />
      </div>

      {/* Mismatch strip: the pairings worth attacking (or avoiding) */}
      {exploits.length > 0 && (
        <div className='mt-[var(--space-3)] flex flex-wrap gap-[var(--space-2)]'>
          {exploits.map(([slot, p]) => {
            const o = offenseRoster.get(slot)!;
            const attacking = p.diff > 0;
            return (
              <div
                key={slot}
                className={`flex items-center gap-[var(--space-2)] rounded-lg border px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] ${
                  attacking
                    ? 'border-emerald-500/30 bg-emerald-900/20 text-emerald-300'
                    : 'border-red-500/30 bg-red-900/20 text-red-300'
                }`}
              >
                <span className='font-black tabular-nums'>
                  {attacking ? `+${p.diff}` : p.diff}
                </span>
                <span className='text-white/80'>
                  {o.player_name} ({o.rating}) vs {p.vs.player_name} ({p.vs.rating})
                </span>
                <span className='uppercase text-[length:var(--fs-micro)] leading-[var(--lh-micro)] opacity-70'>
                  {attacking ? 'attack' : 'avoid'}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
