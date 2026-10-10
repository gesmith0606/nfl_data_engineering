# Weekly waiver runbook (in-season Tuesdays)

Leagues: **Mantis** (Sleeper, `Gforceee`, superflex TE-premium dynasty), **La Liga** (ESPN
`teamId=1`, half-PPR, 2 FLEX, no K), **Feetball** (Yahoo `/f1/658684/10`, half-PPR, 3 WR).
The `gentlemen` / `mahomos` presets in `config.py` are NOT George's leagues.

## 1. Data is current?
- Tuesday cron (`weekly-pipeline.yml`, 09:20 UTC) must have committed
  `data/gold/projections/season=2026/week=N/` for the UPCOMING week and
  `data/bronze/players/weekly/season=2026/` (last week's actuals). `git pull` first.
- If the board is missing: `gh workflow run weekly-pipeline.yml --ref main -f season=2026 -f week=N`.
- Weekly-mode OURS runs low on stars early in the season — always read the BLEND column.

## 1b. League context before any recommendation
```bash
python scripts/league_context.py --league mantis     # FAAB left per team, winning-bid levels, our moves, dynasty values
python scripts/league_context.py --league la_liga    # ESPN cookies in .env, or --espn-json <saved league JSON>
```
Mantis is dynasty: judge claims on dynasty value + age + path to a role (see the
`weekly-waivers` skill), not one week's projection. By week 3 of 2026 we had spent
$602 of $1000 (league median $42) on backup-QB/RB streamers — don't repeat it.

## 2. Refresh the exact free-agent pools
**One command** (Chrome started with `--remote-debugging-port=9222 --user-data-dir=<profile>`,
logged into ESPN + Yahoo, one tab open on each site):
```bash
python scripts/refresh_league_pools.py --league all --week N
```
Writes every `data/draft/{la_liga,feetball}_2026_*` pool file below plus the gitignored
`data/external/espn/la_liga_2026_league.json` for `league_context.py --espn-json`.
Manual fallback (no debug Chrome) — read the sites with claude-in-chrome as below.

### Manual fallback (claude-in-chrome)
- **ESPN**: League Rosters page → all 178 rostered names → `data/draft/la_liga_2026_all_rostered.txt`;
  my team page → `data/draft/la_liga_2026_roster.txt`. (API works from the logged-in tab:
  `lm-api-reads.fantasy.espn.com/.../leagues/1493260?view=mRoster&view=mTeam`, `kona_player_info`
  with `filterStatus FREEAGENT,WAIVERS` gives ESPN's own projections + %rostered.)
- **Yahoo**: Players page `status=A` sorted by week proj (QB/RB/WR/TE pages, 25 per page) →
  `data/draft/feetball_2026_available.txt`; team page → `feetball_2026_roster.txt`;
  `status=T` (taken) → `feetball_2026_league_rosters.txt` for the trade scanner.
- **Sleeper**: nothing to do, rosters are read live.

## 3. Run
```bash
python scripts/waiver_wire.py --league mantis
python scripts/waiver_wire.py --league la_liga  --roster-file data/draft/la_liga_2026_roster.txt  --rostered-file  data/draft/la_liga_2026_all_rostered.txt
python scripts/waiver_wire.py --league feetball --roster-file data/draft/feetball_2026_roster.txt --available-file data/draft/feetball_2026_available.txt
python scripts/player_dossier.py data/draft/weekN_candidates.txt   # usage / injuries / matchup per candidate
python scripts/set_lineups.py --league mantis                        # Sleeper lineups (ESPN/Yahoo: compare by hand)
python scripts/trade_scan.py feetball|la_liga|mantis                 # ROS value, optimal lineups, win-win swaps
python scripts/stream_dst_k.py --pool data/draft/feetball_2026_dstk_pool.txt   # DEF/K streaming (also la_liga)
```

## 3b. Team defense and kicker (La Liga: DEF only; Feetball: DEF + K; Mantis: neither)
- Pull the pool from each site in Chrome with the site's own week projection:
  - **ESPN**: `kona_player_info` with `filterSlotIds [16]` (D/ST), `filterStatus FREEAGENT,WAIVERS`,
    plus my D/ST from `mRoster` -> `data/draft/la_liga_2026_dstk_pool.txt`.
  - **Yahoo**: Players page `status=A&pos=DEF` and `pos=K` with `stat1=S_PW_<week>`, plus my
    K/DEF from the team page -> `data/draft/feetball_2026_dstk_pool.txt`.
  - Format: `MINE|DEF|PHI|8.8`, `MINE|K|Cameron Dicker|8.5`, `DEF|NYG|7.9`, `K|Eddy Pineiro|10.0`.
- Run `python scripts/stream_dst_k.py --pool data/draft/<league>_2026_dstk_pool.txt`.
  Sources: SITE projection, Sleeper, and Vegas (opponent implied total for DEF, own implied for K;
  live odds this week, schedule lines or points-for/against form for the 2-week look-ahead).
  SWAP only when projection and Vegas both clear the bar; also check byes in the look-ahead.
- Defenses/kickers usually clear at $0-1 — don't spend real FAAB on them.

## 4. Bid norms (see vault `fantasy-faab-bid-history-2026`)
- Mantis ($1000): median winning bid 15, p75 75; QB streamers 40-400. A $1 bid only wins junk.
- La Liga ($100): typical winning claim $3-4; two teams empty their budget each year.
- Feetball ($100): the room bids $0-3. $5 wins anything that is not a consensus hot add.

## 5. Waiver clear times
- Sleeper Mantis: Wednesday morning; unclaimed players become instant free agents afterwards.
- ESPN La Liga and Yahoo Feetball: Wednesday ~3am ET.

## 6. File the claims (one confirmed command)
1. Write the final claims to `data/draft/claims_week<N>.yaml`:
   ```yaml
   claims:
     - {league: la_liga,  add: Jaguars D/ST, drop: Bears D/ST, bid: 1, priority: 1}
     - {league: feetball, add: Bo Nix, drop: Cairo Santos, bid: 3}
     - {league: mantis,   add: Braelon Allen, drop: Emanuel Wilson, bid: 55}
   ```
   `bid` is required; `priority` defaults to file order within a league; omit `drop` for an open spot.
   D/STs match on the nickname (`Jaguars`, `Jaguars D/ST`, `Jaguars DEF` are the same). Two
   players with the same name are never guessed between: add `add_id:` / `drop_id:` (the site's
   player id, printed in the error).
2. Dry run (sends nothing):
   `python scripts/submit_claims.py --claims data/draft/claims_week<N>.yaml --cdp-url http://127.0.0.1:<port>`.
   Every claim is checked live (the weekly-waivers Step 4b rule, automated): the add is on
   waivers, the drop is ours and not a keeper (a configured keepers file that is missing or empty
   blocks the league), the bid fits the FAAB left, no claim for the add is already pending (so a
   re-run never files it twice), and Yahoo's own add/drop form posts to our team, offers the drop
   and files a "Create claim". A free agent (adds immediately, cannot be cancelled) is blocked
   unless `--allow-free-agent` is passed. Any `x` line blocks the whole run.
3. Show George the table. **Only after his explicit OK in chat**, run the same command with
   `--submit`. ESPN + Yahoo claims are filed in priority order. In the browser, right before each
   post, ESPN checks the logged-in account owns our team and Yahoo re-checks the form still files a
   claim for our team (waivers clearing at 3am must not turn a claim into an immediate add). An
   unclear result (timeout, 5xx, Yahoo re-serving its form) stops the run, lists what was NOT
   ATTEMPTED and is never retried (no site has idempotency: a retry can spend FAAB twice); then
   every league is re-read and each filed claim is marked CONFIRMED / NOT FOUND. Exit 0 only when
   everything filed is confirmed; exit 2 otherwise - run `check_pending_claims.py` before anything
   else.
4. Mantis is printed as a checklist: enter it in the Sleeper app. Sleeper's public API is
   read-only and hides pending claims, and its Terms (updated 2026-10-06, §11.1-11.3) ban
   scripted access to the private API the app uses.
5. Any time, read-only: `python scripts/check_pending_claims.py --league all` - ESPN pending
   claims + this period's outcomes, Yahoo's team-page Transactions box (claims and pending
   trades), Mantis' processed claims.

Notes:
- **Browser**: ESPN + Yahoo run inside a Chrome profile started with
  `--remote-debugging-port=<port> --user-data-dir=<profile>` and logged into both (same setup as
  §2). The everyday Chrome can hold port 9222 with remote debugging switched on from
  chrome://inspect - that mode has no `/json` endpoints, so start the debug profile on another
  port (e.g. 9333) and pass `--cdp-url`. Cookies, Yahoo's form crumb and the ESPN member id
  stay in the browser; the expired `.env` ESPN cookies are not needed.
- **Claim order**: no API to reorder claims was found for ESPN (Yahoo's is on the official API
  we can't use), so claims are filed in priority order - eyeball the order in the ESPN Clubhouse
  / Yahoo team page. Pending bids are not reserved: if bids add up past the FAAB left, a later
  claim fails once earlier ones win (the dry run warns).
- **ESPN outcomes**: `FAILED_INVALIDPLAYERSOURCE` = the player went elsewhere or an earlier
  claim already used the drop (wk5: Commanders D/ST executed, so the Jaguars claim with the same
  Bears drop failed). A free-agent add executes immediately and cannot be cancelled.
- **Yahoo**: the Fantasy API needs an approved app (ours: 401 `additional_authorization_required`;
  new apps cannot get write scope), so the tool posts Yahoo's own add/drop form. The team page's
  pending-claim markup was not captured yet (nothing was pending) - check the first real Yahoo
  claim's read-back by eye, then lock the parser with a fixture.
- **Terms of use**: ESPN (Disney ToU §2.B.x) and Yahoo (ToS §2.4) also prohibit automated
  access, as do the existing pool-refresh reads. Whether to `--submit` is George's call.
