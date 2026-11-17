---
name: weekly-lineups
description: Weekly start/sit for George's three leagues (Mantis = Sleeper dynasty superflex TE-premium; La Liga = ESPN half-PPR; Feetball = Yahoo half-PPR). Runs scripts/set_lineups.py per league, reads the deltas against the lineup actually set, resolves injury designations against the official report, and for ESPN can file the agreed SWAPs over plain HTTPS. Use when the user says "lineups", "set my lineup", "who should I start", "start/sit", "am I starting the right guys", or asks about a specific player's status for this week. NOT for waivers (weekly-waivers), drafts (draft-agent), trades (scripts/trade_scan.py), or DEF/K streaming (scripts/stream_dst_k.py).
argument-hint: "[league: mantis | la_liga | feetball | all] [week]"
allowed-tools: Bash, Read, WebSearch
---

Set lineups from the lineup that is actually set, not from a recommendation. The
measured failure here is not projection quality — across seven graded weeks George
left a median **26.4 pts/wk** on the bench against the room's 24.7, and **53% of it
was already knowable from our own board**. Advice that does not reach the decision is
worth nothing, so this skill's job is to produce a short, specific instruction.

## Gate — run the tool before naming a player

```bash
source venv/bin/activate
python scripts/set_lineups.py --league mantis      # Sleeper: roster + live lineup
python scripts/set_lineups.py --league la_liga     # ESPN: roster + live lineup (cookies)
python scripts/set_lineups.py --league feetball --roster-file data/draft/feetball_2026_roster.txt
```

Do not suggest a start/sit before the command has run for that league in this session.

## What each platform can actually do — they differ, and it changes the advice

| League | Platform | Lineup you have SET | Can we write it? |
|---|---|---|---|
| `mantis` | Sleeper | **read live** → real deltas | **No** — ToS §11.1. George sets it in the app. |
| `la_liga` | ESPN | **read live** (ESPN_S2/ESPN_SWID) → real deltas | **Yes** — `--espn-write`, then `--apply` |
| `feetball` | Yahoo | **read live** (OAuth grant) when `python scripts/yahoo_auth.py --check` is good → real deltas; else `--roster-file` and a recommendation only | **No** — read-only API (vendor, 2026-10-26). George applies it in the app. |

Two consequences worth stating out loud when you report:

- For **Yahoo without the grant**, the SLOT column is a *recommendation*, not a diff. "No
  changes" there means "nothing beats a starter in the lineup we would pick", not "your
  lineup is fine". The roster file also goes stale — the La Liga one was 4 days old on 2026-10-24 and wrong
  in six places (three dropped players still listed, three adds missing), which produced a
  confident plan for a team George no longer had. Check its date before trusting it.
- For **Sleeper**, never imply a command can set it. There isn't one.

## Read MUST FIX first — it is the only part nobody argues with

The report opens with **MUST FIX**: every starter on a bye, ruled Out, on IR, Doubtful or
with no team, and every empty slot, each with the best eligible replacement already
chosen. These are not judgement calls. In the 2026 Mantis replay, lineups carried over
untouched held 76 such starters across 80 roster-weeks and scored **1,563 points less**
than the same lineups after this repair (11,451 -> 13,014); the old SWAP rule recovered
only 1,156 of it. Start there, say them out loud ("Watson, London, Henry and
Higbee are all on bye"), then move on to deltas.

- A `no eligible player on your bench` line means the slot scores 0 either way: that is a
  waiver pickup, not a lineup decision. Hand it to the waivers skill.
- The deltas that follow are judged on the lineup *after* the MUST FIX moves.
- A bench player whose Sleeper Out tag is unconfirmed is never used as a replacement.
- If the header says **CONSENSUS ONLY**, our weekly board is missing or thin and every
  number is Sleeper's. Say so; do not present it as a two-source agreement. (The tool used
  to fall back to preseason points / 17 here without saying so.)

## The SWAP rule, and what the writer is allowed to file

Every player has ONE estimate: Sleeper's weekly projection under the league's scoring
(our projection is blended in at `lineup_setter.OURS_WEIGHT`, which the replay fits at 0:
more weight scored fewer points). Expected points then carry the injury discount:
Questionable = 71% to play and QB -8% / RB -16% / TE -18% / WR -22% when he does,
Doubtful = 6.5%. Each delta prints **P(bench player outscores the starter)** from the gap
and each player's spread: **SWAP** at P >= 0.52 (no LEAN band: the band just under the
line lost points, 15 pairs / 27% right; `--lean-p` shows close calls, never applied),
**CHECK STATUS** (a Sleeper Out/Doubtful the official report has not confirmed).
Read the P, not the label: 0.52-0.60 is "the expected gain is positive and the old record
of deviating from Sleeper's order is bad", not "certain". A Questionable starter gets a
line saying which bench player can still replace him after his inactive report (about 90
minutes before his kickoff) or that none can.

Thresholds were chosen on weeks 1-5 of the 2026 Mantis replay and tested on 6-9 (n = 90
roster-weeks): `python scripts/replay_lineups.py --sweep`. Held out, the tool beat the
lineups set (+34 pts, 18 swaps, 61% right) but NOT Sleeper's own optimum (+78): the
sample is too small to say the rule adds anything over "follow Sleeper".

`--espn-write` files **only MUST FIX moves and SWAPs at P >= 0.60** (`--write-p`) — never
LEAN, CHECK STATUS, the optimizer's full allocation, or an empty slot (there is no
outgoing player to read the slot from; fill it by hand). A script that moves your lineup
should want a clearer edge than the report does, and filing a move the tool declined to
recommend out loud is indistinguishable from a bug. Dry run first; `--apply` writes.

## Injuries: two rules that pull in opposite directions

1. **A designation of OUT is terminal.** A player listed Out will not play. Do not say
   "wait for inactives" — that advice is for *Questionable*, and repeating it after a
   downgrade is just stale reasoning. Sit the player.
2. **A Sleeper tag is not a ruling.** Sleeper carries the LAST game's status, so it shows
   Out all week for a player the official report lists as Questionable. That is why a SWAP
   benching a starter on an unconfirmed tag becomes CHECK STATUS. Judge the direction:
   a platform Out is strong evidence to sit; a platform Out on a player the official report
   calls Questionable is not evidence to bench him blind.

The official line in the tool's NOTES column is the week's nflverse report plus the
DNP>LP>FP practice trail. Prefer it. But see freshness, below.

## Gameday freshness — both our sources are a day old

`daily-sentiment.yml` runs `0 12 * * *` UTC, so `player_news.py` and the injury snapshot
are up to **24 hours stale** for a Saturday-evening or Sunday-morning call. On 2026-10-24
the Ravens downgraded Lamar Jackson to Out at ~19:58 ET and nothing local could see it.

For a same-day status question, search the web **with the date anchored and the word
"downgraded" or "ruled out", in extended mode** — `"<player>" <team> injury report
<Month DD YYYY> downgraded out`. A query about "inactives" finds articles about inactives,
which is not the same as asking what was announced.

Report what the sources say. Do not add a lean they do not support: on 2026-10-24 the tool
correctly flagged a SPLIT and the narration turned it into "trending toward playing" hours
after the player had been ruled out.

## Finishing the job

- **K and DEF** are filled from the roster (Sleeper's projection, default K/DEF scoring on
  ESPN/Yahoo). To pick one up, `scripts/stream_dst_k.py --pool
  data/draft/<league>_2026_dstk_pool.txt`.
- To judge a rule change, replay it: `python scripts/replay_lineups.py --roster 6` scores
  set / v1 / current-tool / hindsight lineups in actual points over weeks 1-9 (n=90
  roster-weeks). `python scripts/snapshot_gameday_inputs.py` on game-day mornings keeps
  what Sleeper said at the time, so future replays are not graded on today's values.
- Each run prints **last week's bench loss** with the room median for context. Quote it;
  it is the only feedback loop this skill has.
- End with one instruction per league, in the imperative, naming the player and the slot.
  "Start X over Y at FLEX" — not a table for George to interpret at 12:55 on Sunday.
