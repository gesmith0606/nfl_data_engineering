/**
 * Semantic data-color helpers — single source of truth for positive / negative /
 * neutral signaling (deltas, ratings, sentiment, trends).
 *
 * Derives from the `--success` / `--warn` / `--danger` tokens in
 * `src/styles/tokens.css` (theme-neutral, with a `.dark` lightness lift), so a
 * green/red/amber that no theme defines is now consistent across all 10 themes
 * x 2 modes. Retires the ~14 hardcoded `text-green-600 dark:text-green-400`
 * style chains scattered through the feature components.
 */

/** Foreground (text/icon) class for a positive signal. */
export const SUCCESS_TEXT = 'text-[var(--success)]';
/** Foreground (text/icon) class for a cautionary signal. */
export const WARN_TEXT = 'text-[var(--warn)]';
/** Foreground (text/icon) class for a negative signal. */
export const DANGER_TEXT = 'text-[var(--danger)]';

/** Tinted-badge class (subtle bg + readable text) for each semantic role. */
export const SUCCESS_BADGE =
  'text-[var(--success)] bg-[color-mix(in_oklch,var(--success)_14%,transparent)]';
export const WARN_BADGE =
  'text-[var(--warn)] bg-[color-mix(in_oklch,var(--warn)_14%,transparent)]';
export const DANGER_BADGE =
  'text-[var(--danger)] bg-[color-mix(in_oklch,var(--danger)_14%,transparent)]';

/**
 * Map a numeric delta to a foreground class: positive -> success, negative ->
 * danger, zero -> muted (neutral). Centralizes the common
 * `diff > 0 ? green : red` pattern so "no change" reads as neutral, not alarm.
 */
export function deltaTextClass(delta: number): string {
  if (delta > 0) return SUCCESS_TEXT;
  if (delta < 0) return DANGER_TEXT;
  return 'text-muted-foreground';
}
