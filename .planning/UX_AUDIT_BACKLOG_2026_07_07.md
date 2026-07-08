# League Sync UX audit — remaining backlog (2026-07-07)

Live-production audit (playwright, real league). CRITICAL C-1 + HIGH H-1/H-2/H-3
and POLISH P-3/P-4 fixed same-day (see chore/post-launch-polish). Remaining:

- H-4: roster-confirm step shows no team identity — preview roster count/name before commit
- M-1: roster/waiver tabs not sticky on mobile (scrolled off at bench depth)
- M-2: no spinner during Connect lookup (~500-800ms feels dead)
- M-3: drop-candidate reason strings are developer-speak ("redundant — 9 WR rostered, 3 start")
- M-4: right sidebar "Documentation" panel is template boilerplate — replace with league-sync FAQ
- M-5: connect wizard lacks a step indicator (Step 2 of 3)
- P-1: "max 3" cap messaging only useful at 2/3; no explanation at 3/3
- P-2: league tab button 34px tall on mobile (<44px tap target)
- RESOLVED 2026-07-08 — the "Stribling artifact" was NOT an artifact: nflverse
  draft_picks confirms he is SF's 2026 2nd-rounder (pick 33), so his ~181-pt
  projection is legitimate draft-capital-based model opinion (market ADP 271
  disagrees — a value signal, not corruption). The investigation still yielded
  real hardening: the UDFA cap now applies regardless of role source (depth
  charts could crown genuine UDFAs "starter" and bypass it). Residual UI nit:
  huge value badges (ADP−projRank) on rookie-capital picks read as glitches —
  consider capping displayed value or labeling rookie-capital cases.

Audit verdict after fixes: core journey trustworthy; the above is one polish sprint.
