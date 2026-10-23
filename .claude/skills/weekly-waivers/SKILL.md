---
name: weekly-waivers
description: Weekly fantasy waiver recommendations for George's leagues (Mantis = Sleeper dynasty superflex TE-premium; La Liga = ESPN half-PPR; Feetball = Yahoo half-PPR). Loads league context FIRST (FAAB left per team, the room's winning bids, our past churn, dynasty values), then the waiver reports, then gives claims with bid amounts and drops, and files the agreed ESPN/Yahoo claims with scripts/submit_claims.py once George OKs the dry-run table. Use when the user says "waivers", "who should I pick up", "FAAB bids", "claims for this week", "get ready for waivers", or "submit my claims". NOT for lineups (scripts/set_lineups.py), drafts (draft-agent), or trades (scripts/trade_scan.py).
argument-hint: "[league: mantis | la_liga | feetball | all] [week]"
allowed-tools: Bash, Read, Write
---

Recommend waiver claims the way a sharp league-mate would: from the league outward,
not from one week's projections. Full checklist: `docs/WEEKLY_WAIVER_RUNBOOK.md`.

## Gate — no recommendation before the tools have run
Do not name a player, a bid or a drop until `league_context.py` AND `waiver_wire.py`
have run for that league in this session. Not a preference: on 2026-10-20 an hour of
hand-rolled analysis produced a bid sized off a Sleeper-wide add count, a TE compared
on PPR actuals against a half-PPR league, and a QB recommended two days before his
starter was due back — all three of which the two commands answer directly. If a
command fails, say so and fix it; do not substitute your own read of the raw data.

## Our leagues are Mantis, La Liga and Feetball — and only those
`gentlemen` and `mahomos` are in `LEAGUE_PRESETS` as 3-FLEX roster-shape examples for
the draft tools; they belong to a stranger whose Sleeper name resembles George's. The
tools refuse them (`owned: False` -> `config.our_league` raises), which is how it was
caught on 2026-10-23 after a session's advice had already been written for one of them.
Never reach past that refusal to read a league directly.

## Arguments
`$ARGUMENTS` — `[league] [week]`. Default league `all`; default week = the upcoming
week, but on Monday (before MNF) pass the NEXT week explicitly — the resolver still
says the current week until MNF kicks off.

## Step 1 — Data is current (runbook §1)
`git pull` — always, first, before reading anything. The Tuesday cron commits the
upcoming week's Gold board and last week's Bronze actuals, so a checkout that has not
moved in days is reading stale numbers and may be missing tooling outright (a 7-week-old
one on 2026-10-20 produced "the pipeline is dead" and "we never built claim automation",
both false). `waiver_wire.py` prints a warning when HEAD is 3+ days old; believe it. Missing -> `gh workflow run weekly-pipeline.yml --ref main -f season=2026 -f week=N`.

## Step 2 — League context BEFORE any recommendation
```bash
python scripts/league_context.py --league mantis
python scripts/league_context.py --league la_liga --espn-browser   # or ESPN cookies / --espn-json
```
Feetball (Yahoo) has no API: read the Transactions page + each team's FAAB in Chrome.
Note from the output: our FAAB left vs every rival's, the room's median/p75 winning
bid, and what we added/dropped recently (do not re-buy a player we just cut, do not
repeat a churn pattern that already failed).

## Step 3 — Waiver reports (runbook §2-3)
Refresh the ESPN/Yahoo pool files first — one command, from a debug-port Chrome logged
into both sites (`chrome --remote-debugging-port=9222 --user-data-dir=<profile>`):
`python scripts/refresh_league_pools.py --league all --week N` (also writes the ESPN
league JSON for `league_context.py --league la_liga --espn-json data/external/espn/la_liga_2026_league.json`).
If no debug Chrome is up, fall back to reading the sites with claude-in-chrome. Then run `scripts/waiver_wire.py`
per league. **For a `"dynasty": True` preset (Mantis), read the "dynasty targets"
section FIRST and treat the weekly blend as secondary** — that list is sorted by market
value, which is the axis the league is actually played on. Reading past it to the
weekly table produced a 2026-10-21 recommendation of the lowest-value asset on the
board (Roschon Johnson, dyn 539, role borrowed from an injured team-mate) over a
23-year-old starting QB at dyn 1271 in a superflex league. Mantis adds DYN + AGE
columns and that list; every
free agent gets a FIT verdict vs MY roster — STARTS / BENCH+ / depth / no help — and
keepers are tagged KEEP and excluded from drop candidates). In a REDRAFT league
(La Liga, Feetball) never recommend a "no help" player however hot he is — FIT is a
weekly verdict. In a DYNASTY league it is advisory only: an asset buy is supposed to
read "no help" this week (2026-10-21, Jalon Daniels: `no help`, dyn 1271, age 23, the
correct Mantis add). Also read the RENTAL/ENDING tag before the points — `ENDING<-NAME`
means the week's news says that team-mate is returning, so the role is going away now.
That is measured, not asserted: a returning blocker costs the fill-in a median **10
percentage points of snap share** against roughly flat when he stays out (n=46 vs 34,
2026 wks 1-5). It barely moves next-week POINTS, so treat it as a role signal, not a
scoring one — re-check with `scripts/validate_rental_tag.py`.
Then
`scripts/player_dossier.py` on the shortlist (usage, injuries around them, matchup).
Check WHY a player is trending (starter injured? which injury, how long?) before
recommending him.

Pass `--espn-browser` on an ESPN league to get the `[demand]` column and `BID $N`
there too — it reads that league's own transaction log through the claims profile.
Yahoo's API is approval-gated, so for Feetball save the league Transactions page
(`/f1/<league>/transactions`, `body.innerText`) and pass `--transactions-file`; page
through "Next 25" first if you want more than the recent window. All three leagues
now price claims off their own history.

## Step 3b — Every slot the league actually has
Read `roster_positions` from the report's "Roster mechanics" block and cover EVERY slot,
not just the skill positions. Mantis and Mahomo's have no K and no DEF; La Liga has a
D/ST but no K; Feetball has both. On 2026-10-20 La Liga's D/ST was streamed and
Feetball's K and DEF were forgotten entirely until George asked.

```bash
python scripts/stream_dst_k.py --pool data/draft/<league>_2026_dstk_pool.txt --week N
```
Refresh the pool file from the league site first (one line per DEF/K with the site's own
projection — format in the script's docstring). The report gives SITE + Sleeper + the
Vegas implied total, flags SWAP/KEEP on a two-source rule, and looks three weeks ahead
for byes. A DEF-for-DEF swap costs no roster spot, so it is nearly free value.

## Step 4 — Decide
**Mantis (dynasty) — value over points:**
- Rank claims by dynasty value + age + a real path to a role. A short-term fill-in
  for a starter with a 1-3 week injury is a rental: $0-5 or skip.
- Never drop a young (≤24) player with a role path for a one-week streamer. The drop list
  **no longer offers one** in Mantis or Feetball (`drop_order(keeps_players=True)`), and
  `young-drop` stays as the backstop if anything routes around it. A young player nobody
  is adding stays droppable, or this would protect every rookie forever.
- **Which rules are measured, and which are preferences.** Measured: the bid model (median
  error $7 vs 51 real bids), the RENTAL tag (-10.5pp snap share, n=46/34). A *preference*:
  `young-drop`'s <=24 cutoff — `scripts/validate_young_drop.py` shows the obvious test is the
  wrong mechanism for a dynasty rule, and the right one needs value history that only started
  on 2026-10-23. Don't present it as evidence-backed, and don't "refute" it with a points sweep.
- A role the week's news says is **ENDING is priced at $1 by `suggest_bid` itself**, above
  every other pricing rule — you are not buying the usage you are looking at. `ending-role`
  remains the backstop. (Live week 7: George Holani was bid $4 behind
  `Charbonnet(returning)`; the gate caught it, which means the price model should have.)
- Stream a QB only when Lamar/Dak/the QB3 cannot cover a week (byes, injuries).
- Use the 3 taxi slots for rookies/2nd-years; swap out the lowest-value, falling-trend
  taxi player.
- Drop order = lowest dynasty value with no role (old backups first).
- **Check the "Roster mechanics" block before naming a drop.** It prints open active On ESPN and Yahoo that block is
  **partial by design** — active slots come from the roster shape and the names in the
  roster file, while `IR accepts: unknown on <platform>` means confirm on the site in
  Step 4b. Only Sleeper reads live settings, so only Mantis gets real IR/taxi rules.
  slots, IR/taxi use, which `injury_status` values this league's IR actually accepts,
  and any IR-eligible player sitting on your bench. A free IR slot is not usable by an
  "Out" player unless `reserve_allow_out` is set — Mantis 2026 does not set it — and a
  bench player who *is* eligible frees an active slot for free. Both were got wrong on
  2026-10-20.
- **Bids — use the report's `BID $N`.** It is computed from the three things that
  actually set a price, in this order: what this room paid for HIM, which rivals are
  thin at his position AND have both money and a bidding record, and only then the
  room's median. Backtested on 51 real Mantis winning bids its median absolute error
  is $6 against the median rule's $22. Deviate only with a reason you can state, and
  note it caps at a quarter of your remaining budget by design.
  Behind it, read his `[demand]` bracket: `unclaimed`, `held $N wkN`, or `cut wkN (was $N), free Nwk`.
  That is what these managers have actually paid for *him*. The room's median/p75 from
  Step 2 is the price of a CONTESTED player and is only the fallback when he has no
  history. On 2026-10-21 Jalon Daniels read `cut wk4 (was $1), free 3wk` after three
  straight 13-point starts while the room median said $12 — three bids that session
  were sized off the median and all three were too high. A player sitting free while
  producing is information: ask what the other managers know before paying a premium.
  Then sanity-check against rivals' remaining budgets, and keep a reserve (~25% of the
  original budget) for a real starter injury.

**Feetball is a KEEPER league.** Before proposing any Feetball drop, read
`data/draft/feetball_2026_keepers.txt` — our keepers (2026: Luther Burden III, Colston
Loveland) are never drop candidates, and young players on cheap slots carry keeper
value. Check the drop against the pickup's projected edge only after that.

**Every league — start from MY roster:** before recommending a claim, ask whether the
player would actually start or cover a real bye/injury hole on our roster. A trending
player who ranks below our own bench at his position is a pass, however hot.

**La Liga / Feetball:** rest-of-season role and this week's two-source
BLEND; ESPN typical winning claim $3-4, Yahoo room bids $0-3 ($5 wins non-consensus
adds). One-source edges are coin flips. George prefers RB/WR depth over a second TE.

Anyone in the **current** lineup is off the drop list, not just the optimizer's picks —
gated as `start-drop`. The report prints `-- Sanity -- N critical, N warnings` **always**,
clean or not: if you cannot see that line you are looking at filtered output, not a pass.

The header states `NEWS = Gold sentiment, N flags for week W`. **`N` is small by design**
(24 in week 7, league-wide), so most rows carry no NEWS and that is normal. `N = 0` is not:
the extractor fails open to keyword rules while its cron still reports success, so zero
flags means *unknown*, and the gate warns (`news-source`). Say so rather than implying the
week was quiet.

**Know whether this process is actually working.** `python scripts/backtest_claim_outcomes.py
--league mantis` scores every add-minus-drop in the room over the weeks after the move and
compares our median gain against our leaguemates'. As of week 6 2026 the verdict is **BEHIND
THE ROOM**: our median claim gained **+1.6pt vs the room's +6.3pt**, at $4.3/pt against their
$3.8 (n=7, directional). Our mean looks great (+20.2pt) only because of one Brissett at
+84.7pt — quote the median. The worst value was **$300 on Adonai Mitchell for -2.9pt**.
Re-run it before claiming the tooling is good, not just internally consistent.

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

## Step 4b — Gate the advice before you present it
`waiver_wire.py` now runs this check itself at the end of every report and exits 1 on
any CRITICAL, so there is nothing to remember. Run it standalone when you want the
verdict without the board, or add `--no-gate` to suppress it:
```bash
python scripts/sanity_check_waivers.py --league <league> --week N
```
Exits 1 on any CRITICAL. Each check is a correction that had to be made by hand this
season: nothing on a bye recommended, no real money on a role the news says is ENDING,
no bid over a quarter of the budget or above the room's own record, every bid backed by
`[demand]` history, a fresh board, roster mechanics present. **If it fails, fix the
cause — do not present the report with a note.** Gold projections have been gated since
v7.0; this is the same idea for advice.

## Step 5 — Output
Per league: the context line (our FAAB vs the room), then each claim as
`player — bid — drop — why (role/value/injury context)`, then "don't claim" with the
reason for any tempting trending name, then things to re-check before the waiver
run (practice reports, MNF results). Waivers clear Wednesday morning (all three).

## Step 6 — File the claims (runbook §6; only after George's explicit OK)
Write the agreed claims to `data/draft/claims_week<N>.yaml` and run the dry run:
`python scripts/submit_claims.py --claims data/draft/claims_week<N>.yaml` (headless Playwright
profile; if a league says logged out, George runs `python scripts/league_login.py` himself).
It re-checks Step 4b live and prints the table — show it to George. Run it again with
**Build the claims file with `--emit-claims`, do not type it.** On ESPN and Yahoo this needs
`--espn-browser` / `--yahoo-browser` too: the computed `BID $N` is gated on the demand history
AND our remaining FAAB, and without the flag both are absent, so the emitter writes nothing and
says which flag is missing. There is **no rival model on those platforms** (only Sleeper exposes
every rival's roster and budget), so their bids are a room-median floor and the reason says so —
check who else needs the spot yourself before raising one. `python scripts/waiver_wire.py
--league <L> --week N --emit-claims data/draft/claims_week<N>.yaml` writes the STARTS/BENCH+
rows with the report's own computed `BID $N`, the next name off its drop list, and the reason
the model gave, and it refuses to overwrite an existing file. A hand-typed bid is the one
number in this pipeline that never came out of the pipeline, which is why it was the thing
most often wrong. Edit the file freely — but state a reason whenever you move a bid off the
computed one.

`--submit` ONLY when George says yes to that table in chat; never on your own, never from a
cron. Show the read-back (CONFIRMED / NOT FOUND per claim). Mantis is never submitted: tell
George to enter the printed checklist in the Sleeper app. After an `outcome UNKNOWN` line, do
not re-run `--submit` — run `python scripts/check_pending_claims.py --league all` first.
