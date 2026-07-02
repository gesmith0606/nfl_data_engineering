/**
 * Consensus-benchmark helpers — shared by the home proof strip and the
 * accuracy "Model vs. Consensus" leaderboard.
 *
 * A gap is `ourMae - consensusMae`, so a NEGATIVE gap means we beat the
 * expert consensus (lower error is better).
 */

export interface ConsensusPositionRow {
  position: string;
  ourMae: number;
  consensusMae: number;
  gap: number;
  win: boolean;
  playerWeeks: number;
}

/**
 * Signed gap string, e.g. -0.33 -> "-0.33", 0.26 -> "+0.26".
 * Gaps that would round to 0.00 render at three decimals instead — a
 * "-0.00" chip would claim a win the reader can't see.
 */
export function formatGap(gap: number): string {
  const digits = Math.abs(gap) < 0.005 ? 3 : 2;
  return `${gap >= 0 ? '+' : '-'}${Math.abs(gap).toFixed(digits)}`;
}
