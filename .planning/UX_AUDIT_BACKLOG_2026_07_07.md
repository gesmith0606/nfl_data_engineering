# League Sync UX audit — remaining backlog (2026-07-07)

Live-production audit (playwright, real league). CRITICAL C-1 + HIGH H-1/H-2/H-3
and POLISH P-3/P-4 fixed same-day (see chore/post-launch-polish).

ALL ITEMS RESOLVED as of 2026-07-18. M-1..M-5/P-1/P-2 landed in the
ux-polish-sprint commits (b5b9c8ac spinner+steps, 599e6b71 sticky tabs,
8e65f2c6 switcher UX, 7ed9aab5 leagues FAQ sidebar, 4ec5e66f humanized
drop reasons) — this file was stale. H-4 + an M-1 residual closed 2026-07-18:

- [x] H-4: roster-confirm now previews team identity before commit — overview
  is prefetched on step entry (team_name via new backend league-users lookup,
  roster count, scoring label) and reused on confirm. Backend:
  `get_league_users` in src/sleeper_http.py + `team_name` on
  LeagueOverviewResponse. Tests: tests/web/test_league_sync.py +
  web/frontend/.../__tests__/sleeper-league-view.test.tsx.
- [x] M-1 residual: the sticky tab bar collided with PageContainer's sticky
  page header (both top-0 z-10 in one scroll container) — leagues page now
  passes `stickyHeader={false}`.
- [x] M-2: spinner + "Looking up…" on Connect (b5b9c8ac)
- [x] M-3: humanized drop reasons, backend src/roster_optimizer.py (4ec5e66f)
- [x] M-4: leagues page sets League Sync FAQ sidebar via useInfobar (7ed9aab5)
- [x] M-5: "Step N of 3" indicators on all wizard steps (b5b9c8ac)
- [x] P-1: slot count at 2/3+, "Remove a league to add another" at cap (8e65f2c6)
- [x] P-2: min-h-[44px] tap targets on league tab buttons (8e65f2c6)
- RESOLVED 2026-07-08 — the "Stribling artifact" was NOT an artifact: nflverse
  draft_picks confirms he is SF's 2026 2nd-rounder (pick 33), so his ~181-pt
  projection is legitimate draft-capital-based model opinion (market ADP 271
  disagrees — a value signal, not corruption). The investigation still yielded
  real hardening: the UDFA cap now applies regardless of role source (depth
  charts could crown genuine UDFAs "starter" and bypass it). Residual UI nit:
  huge value badges (ADP−projRank) on rookie-capital picks read as glitches —
  consider capping displayed value or labeling rookie-capital cases.

Audit verdict after fixes: core journey trustworthy; the above is one polish sprint.
