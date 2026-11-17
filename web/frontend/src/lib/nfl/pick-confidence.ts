/**
 * How to present an ATS pick honestly.
 *
 * A bare team abbreviation reads as a betting recommendation. On 2026 we have
 * no demonstrated ATS edge — 47.1% on 93 settled games, and line capture of
 * -1.07 pts once the gate was fixed to use the price the board was actually
 * priced against. So the pick is a model lean, and the thing worth showing
 * beside it is the calibrated probability that the picked side covers.
 *
 * It replaces the "N pt edge" label that used to sit there. Edge size is not
 * confidence: `scripts/generate_predictions.py::classify_tier_prob` documents
 * that a 3+ point edge hit 53% O/U and 57% ATS on sealed 2025, which is why
 * tiering already runs on the calibrated probability rather than the edge.
 */

/** Win rate that breaks even at -110 odds (110 / 210). */
export const BREAK_EVEN_PROB = 0.5238;

/** Format the picked side's cover probability, e.g. `'52.4% cover'`. */
export function formatCoverProb(prob: number): string {
  return `${(prob * 100).toFixed(1)}% cover`;
}

/** Compact form for a badge, e.g. `'52.4%'`. */
export function formatCoverProbCompact(prob: number | null, spreadEdge: number | null): string {
  if (prob !== null) return `${(prob * 100).toFixed(1)}%`;
  if (spreadEdge !== null) return `${Math.abs(spreadEdge).toFixed(1)}pt`;
  return '—';
}

/**
 * True when the pick clears the -110 break-even point.
 *
 * Below it we are not claiming an edge, and the UI should not imply one.
 */
export function clearsBreakEven(prob: number | null): boolean {
  return prob !== null && prob >= BREAK_EVEN_PROB;
}

/**
 * The label to show beside an ATS pick.
 *
 * Falls back to the edge when no calibrator ran (the single-XGBoost path
 * leaves `pick_cover_prob` null), so older boards still render.
 */
export function pickConfidenceLabel(
  prob: number | null,
  spreadEdge: number | null
): string {
  if (prob !== null) return formatCoverProb(prob);
  if (spreadEdge !== null) return `${Math.abs(spreadEdge).toFixed(1)}pt edge`;
  return '—';
}
