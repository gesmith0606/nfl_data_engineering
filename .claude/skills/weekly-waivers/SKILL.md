---
name: weekly-waivers
description: Weekly fantasy waiver recommendations for George's leagues (Mantis = Sleeper dynasty superflex TE-premium; La Liga = ESPN half-PPR; Feetball = Yahoo half-PPR). Loads league context FIRST (FAAB left per team, the room's winning bids, our past churn, dynasty values), then the waiver reports, then gives claims with bid amounts and drops, and files the agreed ESPN/Yahoo claims with scripts/submit_claims.py once George OKs the dry-run table. Use when the user says "waivers", "who should I pick up", "FAAB bids", "claims for this week", "get ready for waivers", or "submit my claims". NOT for lineups (scripts/set_lineups.py), drafts (draft-agent), or trades (scripts/trade_scan.py).
argument-hint: "[league: mantis | la_liga | feetball | all] [week]"
allowed-tools: Bash, Read, Write
---

Recommend waiver claims the way a sharp league-mate would: from the league outward,
not from one week's projections. Full checklist: `docs/WEEKLY_WAIVER_RUNBOOK.md`.

## Is this skill still any good? Run the audit, don't take my word
```bash
python scripts/audit_waiver_skill.py          # 21 falsifiable checks, exit 1 on any failure
python scripts/audit_waiver_skill.py --offline # the 8 that need no league data
python scripts/backtest_recommendations.py --league mantis --top-k 3   # the advice score
```
It prints **two** numbers and you need both. **MACHINERY 100/100, ADVICE 50/100 as of
2026-10-27.** Machinery asks whether the tool has a property — a guard exists, a tag comes from
something published, the bid model beats a naive rule on bids somebody already made. Nineteen
of the twenty-one checks are that, and **not one of them can fail because a recommendation was
wrong**: week 8 2026 this audit read 100/100 while four recommendations in a row had to be
corrected by hand. One number let "the machinery is sound" be read as "the advice is good",
which it was never evidence for.

The advice checks score the board's own waiver-tier ranking against what those players then
did. It clears a shuffled ranking comfortably (+3.2 pts/wk vs a flat null) but **ties a
heuristic with no model behind it at all** — rank the same tier by last week's box score and
you do just as well (edge -0.05, MDE 1.03, n=6 weeks). So: the ranking is not noise, and it is
not yet worth the pipeline. Read the failing check as the finding it is, not as a broken test.

**Where it loses is only the very top** (`.planning/WAIVER_RANKING_FLAT_TOP.md`, both rooms,
2026 w2-7). At k=10/20/40 the board beats the box score by +0.36 to +0.51; at k=1 it loses. One
step down the tier it is calibrated (ranks 6-10 vs 11-20: claims +1.94, reality +1.88); at the
top it claims three times the gap that exists (ranks 1-5 vs 6-10: claims +1.12, reality +0.37).
So **the board's #1 waiver name is not meaningfully better than its #5-10** -- treat the top ten
as one candidate set and break the tie on role, snaps and news, which is what Step 3c does. It
is not a position (WR loses in Mantis and gains in La Liga) and not inactives (85% vs 84% played).

Only 2026 weeks 2-7 are eligible, because every 2024 and 2025 board on disk was written *after*
the games it covers. Regenerating them would not help — rosters, depth charts and injury
reports are overwritten in place, so a rebuilt board sees what the engine could not have seen.
The sample grows by one week a week.

An earlier 72->100 score for this skill was a judgement call on a rubric written by the agent
doing the work: a claim with no way to be wrong, i.e. the exact thing every invariant here
exists to prevent. A single 100/100 that could not move on bad advice was the same mistake
wearing a lab coat.

## Gate — no recommendation before the tools have run
Do not name a player, a bid or a drop until `league_context.py` AND `waiver_wire.py`
have run for that league in this session. Not a preference: on 2026-10-20 an hour of
hand-rolled analysis produced a bid sized off a Sleeper-wide add count, a TE compared
on PPR actuals against a half-PPR league, and a QB recommended two days before his
starter was due back — all three of which the two commands answer directly. If a
command fails, say so and fix it; do not substitute your own read of the raw data.

## Our leagues are Mantis, La Liga and Feetball — and only those
`LEAGUE_PRESETS` holds exactly those three. A league that is not George's must never be
read directly: a whole session's waiver advice was once written for a stranger's team
whose Sleeper name resembles his. `config.our_league` raises for anything marked
`owned: False`; never reach past that refusal.

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
  error $7 vs 51 real bids), the RENTAL tag (-10.5pp snap share, n=46/34). Also measured:
  `young-drop`'s <=24 cutoff — **VALIDATED +0.96 PPG** (`validate_young_drop.py`): across
  2022-24, a <=24 player whose snap share rose 10pp went on to a median 5.16 PPG the FOLLOWING
  season vs 4.20 for an older riser, consistent in sign all three years (n=97 vs 116). Don't
  "refute" it with a points-after-the-drop sweep — that is the wrong mechanism and its sign
  flips across adjacent cutoffs.
- **ENDING has two independent sources**, either sufficient: the week's news flag, and the
  blocker's own **DNP->LP->FP practice trail** from the official report. The second exists
  because the first is keyword-grade — and week 7 proved they catch different players:
  Charbonnet had the flag with a flat `('FP',)` trail, Beaux Collins had `('LP','FP')` and no
  flag at all, so Jahan Dotson's role ending was invisible until the trail was read. A single
  `FP` is NOT a return — he never left.
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
  Backtested in **both rooms we can read**: Mantis median error $7 vs the median rule's $22
  (n=51), La Liga $4 vs $4 (n=16). It was WORSE than the naive rule in La Liga until the
  no-rival floor became per-room — `bid_floor_divisor`, measured by
  `backtest_bid_model.py --league <L>`, is 1 there and the default 5 in Mantis. A price model
  tuned in one market has an unknown generalisation; re-run the sweep if a room's habits shift. Deviate only with a reason you can state, and
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

## Step 3c — READ the news for the shortlist (don't count flags)
Once the board is down to the 3-5 candidates a claim actually comes down to:
```bash
python scripts/player_news.py "Roschon Johnson" "Dalton Schultz" --days 5
```
Gold sentiment reduces an article to keyword flags and the header shows only a COUNT. The
articles are in Bronze with ids attached, so for a shortlist, read them. Comprehension-grade
extraction *in the pipeline* needs a funded `ANTHROPIC_API_KEY`; comprehension at **advice
time** needs only this, because you are the language model.

Week 7 showed why: Schultz returned `[pft] TE Dalton Schultz... return to practice Thursday`,
a third independent confirmation of his `returning` flag and DNP>LP trail. Roschon Johnson
returned **0 articles in 5 days** on 1,355k adds — nobody is writing about the player the
market is buying. **Silence is not good news; it is no news.**

**ADDS is belief; SNAP is fact.** Every row now carries last week's offensive snap share and
its change (`snap 40% +1`). A big `adds` number on a flat or falling share is hype, not a role —
week 7 had Roschon Johnson at **1,355k adds on a flat 40%** and Dalton Schultz at **40% (-12)**
behind a quad DNP. This is the column that answers "isn't he a backup?", which was the very
first correction this skill ever needed. Where they disagree, believe SNAP.

**Every league — start from MY roster:** before recommending a claim, ask whether the
player would actually start or cover a real bye/injury hole on our roster. A trending
player who ranks below our own bench at his position is a pass, however hot.

**La Liga / Feetball:** rest-of-season role and this week's two-source
BLEND; ESPN typical winning claim $3-4, Yahoo room bids $0-3 ($5 wins non-consensus
adds). One-source edges are coin flips. George prefers RB/WR depth over a second TE.

Anyone in the **current** lineup is off the drop list, not just the optimizer's picks —
gated as `start-drop`. The report prints `-- Sanity -- N critical, N warnings` **always**,
clean or not: if you cannot see that line you are looking at filtered output, not a pass.

**Four live news sources**, audited 2026-10-23: `rss` (5 feeds), `pft`, `sleeper`, `rotowire`
— ~149 articles a run. **Reddit is gone** (403 to unauthenticated reads since 2024) and is now
explicitly DISABLED rather than erroring daily; revive it via the Arctic Shift archive if ever
wanted. Extraction is **keyword rules, not comprehension** — `ENABLE_LLM_ENRICHMENT` with a
funded `ANTHROPIC_API_KEY` is the single biggest upgrade left to this skill.

The header states `NEWS = Gold sentiment, N flags for week W`. **`N` is small by design**
(24 in week 7, league-wide), so most rows carry no NEWS and that is normal. `N = 0` is not:
the extractor fails open to keyword rules while its cron still reports success, so zero
flags means *unknown*, and the gate warns (`news-source`). Say so rather than implying the
week was quiet.

**Know whether this process is actually working.** `python scripts/backtest_claim_outcomes.py
--league mantis|la_liga` scores every add-minus-drop in the room over the weeks after the move and
compares our median gain against our leaguemates'. **Quote the pooled number** (`--pool`), not one
league: our own claim count per season is tiny, so a single season is directional at best.
Pooled across redraft (La Liga 2024/2025/2026, n=13 ours vs 88 room) the verdict is **BEATING
THE ROOM** — median +23.0pt vs +16.0pt, 69% vs 57% win rate, and **half the FAAB per point**
($0.2 vs $0.4). Mantis alone reads BEHIND (+1.6 vs +6.3), but it is dynasty and six weeks in,
where points over the following weeks is an incomplete measure of an asset buy — the script
says so and leaves dynasty out of the pool rather than averaging two different questions.
Always quote the median: our Mantis mean (+20.2pt) is one Brissett at +84.7pt.

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
says which flag is missing. **Feetball needs no Yahoo login to get priced bids.** The computed bid is gated on the demand
history AND our budget; `--transactions-file` (the Transactions page pasted as text) supplies
the first, and `--faab N` supplies the second from the number George reads off his own page:
```bash
python scripts/waiver_wire.py --league feetball --week N \
  --roster-file data/draft/feetball_2026_roster.txt \
  --available-file data/draft/feetball_2026_available.txt \
  --transactions-file <pasted.txt> --faab 42
```
The login (`league_login.py`) is still the nicer path and would add the rival model, but it is
behind bot detection and is George's hands only — this route is not blocked on anything.

ESPN now has the **same rival model as Sleeper** — its payload carries every team's
roster, injury statuses and FAAB spent, so "thin here, holding money, and a proven bidder" is
answerable there too (`espn_rivals`). Yahoo still has none and says so in the reason.
A `depth` verdict caps the bid at the room-median floor regardless of contest: the model prices
what it takes to WIN a player, not what he is worth to us, and wiring ESPN's rivals immediately
produced $14 — a quarter of the FAAB — on 20 depth players. `python scripts/waiver_wire.py
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
