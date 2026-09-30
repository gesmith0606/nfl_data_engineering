---
name: weekly-waivers
description: Weekly fantasy waiver recommendations for George's leagues (Mantis = Sleeper dynasty superflex TE-premium; La Liga = ESPN half-PPR; Feetball = Yahoo half-PPR). Loads league context FIRST (FAAB left per team, the room's winning bids, our past churn, dynasty values), then the waiver reports, then gives claims with bid amounts and drops. Use when the user says "waivers", "who should I pick up", "FAAB bids", "claims for this week", or "get ready for waivers". NOT for lineups (scripts/set_lineups.py), drafts (draft-agent), or trades (scripts/trade_scan.py).
argument-hint: "[league: mantis | la_liga | feetball | all] [week]"
allowed-tools: Bash, Read, Write
---

Recommend waiver claims the way a sharp league-mate would: from the league outward,
not from one week's projections. Full checklist: `docs/WEEKLY_WAIVER_RUNBOOK.md`.

## Arguments
`$ARGUMENTS` — `[league] [week]`. Default league `all`; default week = the upcoming
week, but on Monday (before MNF) pass the NEXT week explicitly — the resolver still
says the current week until MNF kicks off.

## Step 1 — Data is current (runbook §1)
`git pull`. The Tuesday cron commits the upcoming week's Gold board and last week's
Bronze actuals. Missing -> `gh workflow run weekly-pipeline.yml --ref main -f season=2026 -f week=N`.

## Step 2 — League context BEFORE any recommendation
```bash
python scripts/league_context.py --league mantis
python scripts/league_context.py --league la_liga   # ESPN cookies, or --espn-json <saved league JSON>
```
Feetball (Yahoo) has no API: read the Transactions page + each team's FAAB in Chrome.
Note from the output: our FAAB left vs every rival's, the room's median/p75 winning
bid, and what we added/dropped recently (do not re-buy a player we just cut, do not
repeat a churn pattern that already failed).

## Step 3 — Waiver reports (runbook §2-3)
Refresh the ESPN/Yahoo pool files in Chrome first, then run `scripts/waiver_wire.py`
per league (Mantis adds DYN value + AGE columns and a "dynasty targets" list), and
`scripts/player_dossier.py` on the shortlist (usage, injuries around them, matchup).
Check WHY a player is trending (starter injured? which injury, how long?) before
recommending him.

## Step 4 — Decide
**Mantis (dynasty) — value over points:**
- Rank claims by dynasty value + age + a real path to a role. A short-term fill-in
  for a starter with a 1-3 week injury is a rental: $0-5 or skip.
- Never drop a young (≤24) player with a role path for a one-week streamer.
- Stream a QB only when Lamar/Dak/the QB3 cannot cover a week (byes, injuries).
- Use the 3 taxi slots for rookies/2nd-years; swap out the lowest-value, falling-trend
  taxi player.
- Drop order = lowest dynasty value with no role (old backups first).
- Bids: anchor on the room's median/p75 from Step 2 and on rivals' remaining budgets.
  Keep a reserve (~25% of the original budget) for a real starter injury.

**La Liga / Feetball (redraft):** rest-of-season role and this week's two-source
BLEND; ESPN typical winning claim $3-4, Yahoo room bids $0-3 ($5 wins non-consensus
adds). One-source edges are coin flips. George prefers RB/WR depth over a second TE.

## Step 4b — Confirm every claim and drop LIVE (mandatory, never skip)
Pool files and trending lists go stale within hours. Right before presenting, check
each recommended ADD is still unrostered and each DROP is on our roster, on the site:
- Sleeper: `/league/<id>/rosters` — search `players` + `taxi` + `reserve` of all teams.
- ESPN: `kona_player_info` with `filterStatus FREEAGENT,WAIVERS` (status = FREEAGENT or
  WAIVERS) and `mRoster` for our drops; also read `mSettings` roster slot counts before
  suggesting IR moves (La Liga has 0 IR slots).
- Yahoo: Players page `status=A` (Roster Status `W (date)` = on waivers) and our team page.
Show the result as a table (player → live status → source). Anything unverified is
labelled UNVERIFIED, never presented as available.

## Step 5 — Output
Per league: the context line (our FAAB vs the room), then each claim as
`player — bid — drop — why (role/value/injury context)`, then "don't claim" with the
reason for any tempting trending name, then things to re-check before the waiver
run (practice reports, MNF results). Waivers clear Wednesday morning (all three).
