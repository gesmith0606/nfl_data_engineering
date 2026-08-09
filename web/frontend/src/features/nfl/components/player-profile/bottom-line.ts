import type { PlayerProjection } from '@/lib/nfl/types';
import { median } from './percentile';

export type BottomLinePlayer = Pick<
  PlayerProjection,
  'player_name' | 'position' | 'projected_points' | 'position_rank' | 'injury_status'
>;

/**
 * ESPN "Bottom Line" pattern — one plain-English verdict sentence, derived
 * only from data the page already has: this week's position rank (when the
 * API supplies one — `PlayerProjection.position_rank`) plus this week's
 * projection vs the position median, computed client-side from the same
 * position pool the percentile bars use (`/api/projections`, filtered to
 * this player's position and week). No hidden inputs, nothing invented.
 */
export function deriveBottomLine(player: BottomLinePlayer, positionPool: number[]): string {
  if (positionPool.length === 0) {
    return `Not enough ${player.position} data this week to rank ${player.player_name} yet.`;
  }

  const med = median(positionPool);
  const delta = player.projected_points - med;
  const rankPhrase =
    player.position_rank != null
      ? `the No. ${player.position_rank} ${player.position}`
      : `a ${player.position}`;
  const deltaPhrase =
    delta === 0
      ? `right at the ${player.position} median (${med.toFixed(1)} pts)`
      : `${Math.abs(delta).toFixed(1)} pts ${delta > 0 ? 'above' : 'below'} the ${player.position} median (${med.toFixed(1)})`;

  let sentence = `${player.player_name} is ${rankPhrase} this week, projected for ${player.projected_points.toFixed(1)} pts — ${deltaPhrase}.`;

  if (player.injury_status && player.injury_status.toLowerCase() !== 'active') {
    sentence += ` Listed ${player.injury_status} — confirm status before locking your lineup.`;
  }

  return sentence;
}
