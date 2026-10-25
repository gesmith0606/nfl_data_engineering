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
| `feetball` | Yahoo | **none** — no API access yet | No |

Two consequences worth stating out loud when you report:

- For **Yahoo**, the SLOT column is a *recommendation*, not a diff. "No changes" there
  means "nothing beats a starter in the lineup we would pick", not "your lineup is fine".
  The roster file also goes stale — the La Liga one was 4 days old on 2026-10-24 and wrong
  in six places (three dropped players still listed, three adds missing), which produced a
  confident plan for a team George no longer had. Check its date before trusting it.
- For **Sleeper**, never imply a command can set it. There isn't one.

## The SWAP rule, and what the writer is allowed to file

A **SWAP** needs OURS *and* Sleeper to agree by the threshold (default 3.0). Everything
softer exists because it wants a human: **COIN FLIP** (too close), **SPLIT** (the sources
disagree), **CHECK STATUS** (a Sleeper Out/Doubtful the official report has not confirmed).

`--espn-write` files **only the SWAPs the table printed** — never the softer verdicts, and
never the optimizer's full allocation. That is deliberate: filing a move the tool declined
to recommend out loud is indistinguishable from a bug. Dry run first; `--apply` writes.

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

- **K and DEF** are unfillable from our registry — `scripts/stream_dst_k.py --pool
  data/draft/<league>_2026_dstk_pool.txt`.
- Each run prints **last week's bench loss** with the room median for context. Quote it;
  it is the only feedback loop this skill has.
- End with one instruction per league, in the imperative, naming the player and the slot.
  "Start X over Y at FLEX" — not a table for George to interpret at 12:55 on Sunday.
