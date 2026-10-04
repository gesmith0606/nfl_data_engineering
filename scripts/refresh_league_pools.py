#!/usr/bin/env python3
"""Refresh the ESPN / Yahoo pool files from the logged-in browser in one command.

    python scripts/refresh_league_pools.py --league la_liga
    python scripts/refresh_league_pools.py --league feetball --week 5
    python scripts/refresh_league_pools.py --league all --cdp-url http://127.0.0.1:9222

Writes ``data/draft/<league>_2026_*.txt`` (roster, all-rostered / available,
league rosters, DEF/K pool) — the exact files waiver_wire.py, stream_dst_k.py and
trade_scan.py read — plus, for ESPN, ``data/external/espn/<league>_<season>_league.json``
(gitignored) for ``league_context.py --espn-json``.

Needs a Chrome started with remote debugging and logged into ESPN and Yahoo
(same setup as the ESPN draft co-pilot):

    chrome --remote-debugging-port=9222 --user-data-dir=<separate profile>

with a fantasy.espn.com and a football.fantasysports.yahoo.com tab open. All
reads are same-origin fetches from those tabs (no clicks, nothing submitted).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config  # noqa: E402
from src.espn_draft_page import ChromeDraftPage  # noqa: E402
from src.league_pools import (  # noqa: E402
    espn_pool_files,
    first_projection,
    yahoo_pool_files,
)

DRAFT_DIR = REPO_ROOT / "data" / "draft"
ESPN_JSON_DIR = REPO_ROOT / "data" / "external" / "espn"
MY_TEAM = {"la_liga": 1, "feetball": 10}

ESPN_JS = """(async () => {
 const SEASON=%(season)d, LID=%(lid)s, TEAM=%(team)d, WEEK=%(week)d;
 const api=`https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${SEASON}`;
 const base=`${api}/segments/0/leagues/${LID}`;
 const get=async (u,f)=>(await fetch(u,{credentials:'include',headers:f?{'x-fantasy-filter':JSON.stringify(f)}:{}})).json();
 const j=await get(base+'?view=mSettings&view=mTeam&view=mRoster');
 let tx=[]; for(let w=0;w<=WEEK;w++){tx=tx.concat((await get(base+`?view=mTransactions2&scoringPeriodId=${w}`)).transactions||[]);}
 tx=tx.filter(t=>t.type!=='ROSTER'&&t.type!=='DRAFT');
 const ids=[...new Set(tx.flatMap(t=>(t.items||[]).map(i=>i.playerId)))].filter(i=>i>0);
 j.transactions=tx;
 j.players=ids.length?await get(`${api}/players?scoringPeriodId=0&view=players_wl`,{filterIds:{value:ids}}):[];
 const pr=p=>{const s=(p.stats||[]).find(s=>s.statSourceId==1&&s.scoringPeriodId==WEEK);return s?s.appliedTotal:null};
 const d=await get(base+`?scoringPeriodId=${WEEK}&view=kona_player_info`,{players:{filterStatus:{value:['FREEAGENT','WAIVERS']},filterSlotIds:{value:[16]},limit:40,sortPercOwned:{sortPriority:1,sortAsc:false}}});
 const m=await get(base+`?scoringPeriodId=${WEEK}&view=mRoster&forTeamId=${TEAM}`);
 const my={}; ((m.teams||[]).find(t=>t.id==TEAM)?.roster.entries||[]).forEach(e=>{const p=e.playerPoolEntry.player; if(p.defaultPositionId==16) my[p.fullName]=pr(p);});
 return JSON.stringify({payload:j, fa_dst:(d.players||[]).map(x=>[x.player.fullName,pr(x.player)]), my_dst:my});
})()"""

YAHOO_JS = """(async () => {
 const LID=%(lid)s, TEAM=%(team)d, WEEK=%(week)d;
 const P=new DOMParser();
 const get=async u=>P.parseFromString(await (await fetch(u,{credentials:'include'})).text(),'text/html');
 const rows=d=>[...d.querySelectorAll('table tbody tr')];
 const nm=r=>(r.querySelector('.ysf-player-name a, a.name')||{}).textContent;
 const team=await get(`/f1/${LID}/${TEAM}`);
 const my=rows(team).map(r=>({slot:((r.querySelector('td.pos, .pos-label')||{}).textContent||'').trim(), name:(nm(r)||'').trim(), status:((r.querySelector('.ysf-player-status, .F-injury')||{}).textContent||'').trim()})).filter(x=>x.name);
 const avail={};
 for (const pos of ['QB','RB','WR','TE','DEF','K']) {
   const d=await get(`/f1/${LID}/players?status=A&pos=${pos}&cut_type=9&stat1=S_PW_${WEEK}&myteam=0&sort=PTS&sdir=1`);
   avail[pos]=rows(d).map(r=>({name:(nm(r)||'').trim(), cells:[...r.querySelectorAll('td')].map(t=>t.textContent.trim())})).filter(x=>x.name).slice(0,25);
 }
 return JSON.stringify({my, avail});
})()"""


def _write(files: Dict[str, str]) -> None:
    for name, text in files.items():
        (DRAFT_DIR / name).write_text(text, encoding="utf-8")
        print(f"  wrote data/draft/{name} ({text.count(chr(10))} lines)")


def refresh_espn(league: str, week: int, season: int, cdp_url: str) -> None:
    preset = config.LEAGUE_PRESETS[league]
    page = ChromeDraftPage(cdp_url, url_fragment="fantasy.espn.com")
    raw = page.evaluate(
        ESPN_JS
        % {
            "season": season,
            "lid": preset["league_id"],
            "team": MY_TEAM[league],
            "week": week,
        },
        await_promise=True,
        timeout=120,
    )
    data = json.loads(raw)
    ESPN_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out = ESPN_JSON_DIR / f"{league}_{season}_league.json"
    out.write_text(json.dumps(data["payload"]), encoding="utf-8")
    print(f"  wrote {out.relative_to(REPO_ROOT)} (league_context.py --espn-json)")
    _write(
        espn_pool_files(
            data["payload"],
            MY_TEAM[league],
            league,
            week,
            fa_dst=data["fa_dst"],
            my_dst_proj=data["my_dst"],
            season=season,
        )
    )


def refresh_yahoo(league: str, week: int, season: int, cdp_url: str) -> None:
    preset = config.LEAGUE_PRESETS[league]
    page = ChromeDraftPage(cdp_url, url_fragment="football.fantasysports.yahoo.com")
    raw = page.evaluate(
        YAHOO_JS % {"lid": preset["league_id"], "team": MY_TEAM[league], "week": week},
        await_promise=True,
        timeout=120,
    )
    data = json.loads(raw)
    if not data["my"]:
        sys.exit("Yahoo team page returned no rows — is the tab logged in?")
    avail = {
        pos: [{"name": r["name"], "proj": first_projection(r["cells"])} for r in rows]
        for pos, rows in data["avail"].items()
    }
    _write(
        yahoo_pool_files(
            data["my"],
            avail,
            league,
            week,
            f"/f1/{preset['league_id']}/{MY_TEAM[league]}",
            season=season,
        )
    )


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", required=True, choices=["la_liga", "feetball", "all"])
    ap.add_argument("--week", type=int, help="NFL week (default: upcoming)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = ap.parse_args(argv)

    week = args.week
    if week is None:
        from importlib import util

        spec = util.spec_from_file_location(
            "set_lineups", REPO_ROOT / "scripts" / "set_lineups.py"
        )
        mod = util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _, week = mod._default_week(args.season)

    for league in ["la_liga", "feetball"] if args.league == "all" else [args.league]:
        print(f"{league} (week {week}):")
        if config.LEAGUE_PRESETS[league]["platform"] == "espn":
            refresh_espn(league, week, args.season, args.cdp_url)
        else:
            refresh_yahoo(league, week, args.season, args.cdp_url)
    print("Next: python scripts/waiver_wire.py ... / stream_dst_k.py --pool ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
