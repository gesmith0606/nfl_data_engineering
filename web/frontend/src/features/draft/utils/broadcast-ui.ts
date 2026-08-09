/**
 * Shared broadcast-chrome class strings for the draft room (sketch 001-B/003 —
 * see .claude/skills/sketch-findings-nfl-data-engineering). Centralized here so
 * the ~15 draft components apply the same near-black/mint/yellow/periwinkle
 * treatment instead of re-deriving long literal class strings per call site
 * (ponytail: one source, not fifteen copies). Every value is a plain string —
 * safe for Tailwind's static class extraction since nothing is interpolated.
 */

/** TabsList shell — near-black pill bar, mint-tinted border. */
export const WC_TABS_LIST =
  'h-auto rounded-full border border-[rgba(145,237,208,0.25)] bg-[var(--wc-bar,#05070d)] p-1'

/** TabsTrigger — condensed caps, mint active state (no shadcn background swap). */
export const WC_TAB_TRIGGER =
  "wc-display rounded-full border border-transparent px-3 py-1.5 text-[12px] tracking-[0.08em] text-[#9aa3b8] shadow-none transition-colors duration-150 data-[state=active]:border-[rgba(145,237,208,0.4)] data-[state=active]:bg-[rgba(145,237,208,0.12)] data-[state=active]:text-[var(--wc-mint,#91edd0)] dark:data-[state=active]:bg-[rgba(145,237,208,0.12)] dark:data-[state=active]:text-[var(--wc-mint,#91edd0)] hover:text-[var(--wc-mint,#91edd0)]"

/** Primary CTA button (periwinkle) — restyles the shadcn Button underneath. */
export const WC_CTA_BUTTON =
  'wc-display rounded-full border-0 bg-[var(--wc-peri,#5b67c7)] tracking-[0.08em] text-white hover:bg-[var(--wc-peri-bright,#6e7ce0)]'

/** Secondary/outline button — near-black surface, mint hover. */
export const WC_OUTLINE_BUTTON =
  'wc-display rounded-full border-[rgba(145,237,208,0.3)] bg-transparent tracking-[0.08em] text-[#cfd6e4] hover:border-[var(--wc-mint,#91edd0)] hover:bg-[rgba(145,237,208,0.08)] hover:text-[var(--wc-mint,#91edd0)]'

/** Ghost/tertiary button — condensed caps, mint on hover. */
export const WC_GHOST_BUTTON =
  'wc-display tracking-[0.08em] text-[#9aa3b8] hover:bg-[rgba(145,237,208,0.08)] hover:text-[var(--wc-mint,#91edd0)]'

/** Yellow "on the clock" attention button (rare — genuinely urgent CTAs only). */
export const WC_ATTENTION_BUTTON =
  'wc-display rounded-full border-0 bg-[var(--wc-yellow,#ffd84d)] tracking-[0.08em] text-[#221b00] hover:bg-[var(--wc-yellow-deep,#e8b820)]'

/** Panel/card surface — near-black, mint-tinted border (BroadcastPanel look, no rail). */
export const WC_PANEL_SURFACE = 'border-[rgba(145,237,208,0.2)] bg-[rgba(5,7,13,0.75)]'

/** Text input / textarea — dark broadcast surface, mint focus ring. */
export const WC_INPUT =
  'border-[rgba(145,237,208,0.25)] bg-[rgba(5,7,13,0.5)] text-[#e6eaf2] placeholder:text-[#5b6577] focus-visible:border-[var(--wc-mint,#91edd0)] focus-visible:ring-[var(--wc-mint,#91edd0)]/40'

/** Condensed-caps section kicker (small yellow label above a panel/section). */
export const WC_KICKER = 'wc-display text-[11px] tracking-[0.16em] text-[var(--wc-yellow,#ffd84d)]'

/** Condensed-caps panel heading. */
export const WC_HEADING = 'wc-display tracking-[0.06em]'

/** "On the clock" / live pulse badge — yellow, functional pulse (not ornamental). */
export const WC_LIVE_BADGE =
  'inline-flex items-center gap-1.5 rounded-full border border-[rgba(255,216,77,0.4)] bg-[rgba(255,216,77,0.12)] px-2.5 py-0.5 text-[11px] font-semibold tracking-[0.08em] text-[var(--wc-yellow,#ffd84d)]'

export const WC_LIVE_DOT = 'h-2 w-2 rounded-full bg-[var(--wc-yellow,#ffd84d)] animate-pulse'

/** Mint hero numeral (pick numbers, values, projections). */
export const WC_NUM_HERO = 'wc-display font-extrabold tabular-nums text-[var(--wc-mint,#91edd0)]'
