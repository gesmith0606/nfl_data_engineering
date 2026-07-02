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

/** Signed gap string, e.g. -0.33 -> "-0.33", 0.26 -> "+0.26". */
export function formatGap(gap: number): string {
  return `${gap >= 0 ? '+' : '-'}${Math.abs(gap).toFixed(2)}`;
}
