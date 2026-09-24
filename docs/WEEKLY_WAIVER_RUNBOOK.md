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

## 2. Refresh the exact free-agent pools (Chrome, logged in — claude-in-chrome)
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
