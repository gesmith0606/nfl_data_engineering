# Feetball 2026 — Draft-Night Runbook (Mon Sep 7, 8:30pm ET, Yahoo league 658684)

Strategy lives in `FEETBALL_2026_DRAFT_PLAN.md` (§10 = day-before refresh). This file is the
operational checklist: what to run, in what order, and the traps from the 2026-08-31 La Liga
draft that this setup is designed to avoid.

## T-minus afternoon (Sep 7, before 6pm)

1. **Re-read the Yahoo draft-order page** (League → Draft → "2026 draft order"). The commish
   customized it ~3h before the Aug 30 capture; anything can have moved. Diff against
   `FEETBALL_2026_DRAFT_ORDER.md`. If a slot/keeper changed, edit BOTH
   `data/draft/feetball_2026_pick_order.txt` and `data/draft/feetball_2026_keepers.txt`.
   (La Liga lesson #5: prep doc said 17 rounds + K, reality was 16 rounds, no K, reshuffled order.)
2. **Yahoo room ADP** (doctrine §11 — price against the room, not FFC). Start Chrome with
   `--remote-debugging-port=9333 --user-data-dir=<separate profile>`, open the league's
   Draft Analysis page, then:
   ```bash
   python scripts/refresh_adp.py --source yahoo --scoring half_ppr --cdp-url http://127.0.0.1:9333
   ```
   DONE 2026-09-07 afternoon via the Chrome extension (parser updated for Yahoo's 2026
   "Basic ADP" layout): `data/adp/adp_yahoo_half_ppr.csv` = raw Yahoo board (210 players,
   last-7-days ADP) and **`data/adp/adp_yahoo_feetball_half_ppr.csv` = the ROOM board** (25
   keepers removed, everyone else shifted by the keepers priced above him). Use the room file.
3. **Audit the Yahoo pre-draft queue / autopick list.** Load the §5 queue (60 names, keepers
   excluded). Then remove **every QB except your one target tier, every K, every DST**, and any
   name already on the fade list. La Liga lesson #3: a leftover queue entry autopicked a 2nd QB.
   Yahoo autopicks from your queue if the clock expires — the queue is a loaded gun.
4. Confirm `.env`/shell has nothing the co-pilot needs from Yahoo: the API path is NOT the plan
   (Fantasy-scope approval never confirmed). The co-pilot runs in **manual mode**.

## Launch (8:00pm) — ALWAYS from the repo root

La Liga lesson #4: launching from another directory silently zeroed ADP and the NEWS guard.
The cwd fix on this branch re-anchors paths, but still launch from the root:

```bash
cd "Z:\z drive\repos\nfl_data_engineering"; .\venv\Scripts\activate
```

Snapshot command (re-run after every pick; see the manual-mode section below for the flags
the co-pilot expects):

```bash
python scripts/draft_live.py --manual --teams 10 --my-slot 6 --scoring half_ppr \
  --roster-format yahoo_feetball --season 2026 \
  --pick-order-file data/draft/feetball_2026_pick_order.txt \
  --keepers-file data/draft/feetball_2026_keepers.txt \
  --adp-file data/adp/adp_yahoo_feetball_half_ppr.csv --top 8 \
  --add-pick "Jahmyr Gibbs" --add-pick "Bijan Robinson" ...
```

- `--add-pick` entries are the LIVE picks in room order. Keeper slots (4.06, 4.08, …) are
  never typed — the pick-order file's `(K)` markers consume those pick numbers automatically.
- Expected startup lines (verified 2026-09-06 against the committed files):
  `(pick order: 10 teams, 17 rounds, 25 keeper slots; your live picks: 6, 13, 15, 21, 26, 34, 35,
  46, 55, 66, 75, 106, 115, 146, 155; your keeper slots: 86, 126)` and
  `(keepers file: 2/2 rostered to you, 23/23 others removed from the board)`. Anything less on
  the keepers line = a name mismatch (names match suffix-blind; inline `#` comments are fine).
- Turn check: with 14 picks typed the output reads `On the clock: pick 15, slot 6  <<< YOUR PICK`
  and `COST OF WAITING to pick 21`. If the on-clock pick or the next-pick number disagrees with
  the room, the order file is wrong — fix it before trusting cost-of-waiting.
- The order file counts EVERY slot Yahoo counts (4.06 = overall 36), so overall pick numbers in
  the output match the room's.

## In-room loop (the thing that actually worked at La Liga)

- **You are the availability truth, the model is the pricing.** When the tracker and the room
  disagree on who is available, the ROOM is right — screenshot the room list, chat prices it.
- Every pick: type it in, re-run, read three things: `COST OF WAITING` (take the biggest),
  `TIER CLIFF` (LAST-of-tier), `NEWS` tags (verify before drafting — Nacua's suspension was real).
- Pick-by-pick targets and the QB trigger (Allen #21 / Lamar #26 / else wait to #75+) are in
  the plan §2–§3. Do not let a VALUE tag override §36 exempt-list / roster-status warnings.
- House rules that never bend: **never a 2nd QB**, no K/DST before #146/#155, no TE2 before
  round 9 while a starter slot is open (Loveland is already yours).

## Post-draft (same night)

- `python scripts/draft_live.py ... --roster-report` (or the plan §9) for the lineup +
  drop candidates; float the Caleb Williams offer to "Dude I got a Dell" per plan §9.
- Append the post-mortem + tooling bugs to the vault note `espn-mock-draft-lessons-2026-08-23`.
