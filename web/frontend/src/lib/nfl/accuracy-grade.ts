/**
 * Letter-grade overlays for the accuracy dashboard — FantasyPros publishes
 * the raw MAE numbers with zero visual encoding; this is our "beat". Grades
 * are always rendered alongside the raw number they summarize, never alone.
 */

import { SUCCESS_TEXT, WARN_TEXT, DANGER_TEXT } from './semantic-colors';

export interface GapGrade {
  grade: 'A+' | 'A' | 'B' | 'C' | 'D';
  className: string;
  /** Plain-language description for a title/aria label. */
  description: string;
}

/**
 * Letter grade for a matched-pairs MAE gap vs the consensus benchmark.
 * A gap is `ourMae - consensusMae` (negative = we beat the consensus).
 * +/-0.05 is treated as a statistical tie — a few hundredths of a fantasy
 * point isn't a meaningfully different projection.
 */
export function gradeGap(gap: number): GapGrade {
  if (gap <= -0.2) {
    return { grade: 'A+', className: SUCCESS_TEXT, description: 'Dominant win vs consensus' };
  }
  if (gap <= -0.05) {
    return { grade: 'A', className: SUCCESS_TEXT, description: 'Clear win vs consensus' };
  }
  if (gap <= 0.05) {
    return { grade: 'B', className: WARN_TEXT, description: 'Statistical tie with consensus' };
  }
  if (gap <= 0.2) {
    return { grade: 'C', className: WARN_TEXT, description: 'Narrow loss vs consensus' };
  }
  return { grade: 'D', className: DANGER_TEXT, description: 'Clear loss vs consensus' };
}

export interface MaeGrade {
  grade: 'A' | 'B' | 'C' | 'D';
  label: string;
  className: string;
}

/**
 * Letter grade for raw MAE (average fantasy-point error per player-week).
 * Lower is better. Thresholds match the position-agnostic bands used across
 * the fantasy projection industry for "how far off is this, roughly".
 */
export function gradeMae(mae: number): MaeGrade {
  if (mae < 4.0) return { grade: 'A', label: 'Excellent', className: SUCCESS_TEXT };
  if (mae < 5.0) {
    return { grade: 'B', label: 'Good', className: 'text-blue-600 dark:text-blue-400' };
  }
  if (mae < 6.0) return { grade: 'C', label: 'Fair', className: WARN_TEXT };
  return { grade: 'D', label: 'High', className: DANGER_TEXT };
}
