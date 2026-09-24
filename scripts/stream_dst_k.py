#!/usr/bin/env python3
"""Weekly team-defense and kicker streaming report.

    python scripts/stream_dst_k.py --pool data/draft/feetball_2026_dstk_pool.txt
    python scripts/stream_dst_k.py --pool data/draft/la_liga_2026_dstk_pool.txt --weeks 3

Pool file (read from the league site each Tuesday, see docs/WEEKLY_WAIVER_RUNBOOK.md),
one line per player, ``#`` comments allowed::

    MINE|DEF|JAX|4.3        # my defense: team abbr + the site's projection
    MINE|K|Cameron Dicker|8.5
    DEF|PHI|9.6             # an available defense
    K|Jake Bates|8.7        # an available kicker

Sources shown per row: SITE = the league platform's own projection (its scoring),
SLPR = Sleeper's weekly projection, and Vegas — the opponent's implied total for a
defense (lower is better) or the team's own implied total for a kicker (higher is
better). Current week uses the live odds snapshot; later weeks use schedule lines,
or points-per-game form when no line is posted. A swap is recommended only when the
projection AND Vegas both favor the candidate (src/streaming.swap_verdict).
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, sleeper_http  # noqa: E402
from src.sleeper_player_map import load_sleeper_players, normalize_name  # noqa: E402
from src.streaming import (  # noqa: E402
    implied_totals_from_odds,
    matchup_table,
    swap_verdict,
)

_spec = importlib.util.spec_from_file_location(
    "set_lineups", REPO_ROOT / "scripts" / "set_lineups.py"
)
set_lineups = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(set_lineups)  # type: ignore[union-attr]


def read_pool(path: Path) -> Tuple[List[dict], List[dict]]:
    """Return (mine, available) rows: {pos, key, site}."""
    mine, avail = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        is_mine = parts[0].upper() == "MINE"
        if is_mine:
            parts = parts[1:]
        pos, key = parts[0].upper(), parts[1]
        site = float(parts[2]) if len(parts) > 2 and parts[2] else None
        (mine if is_mine else avail).append({"pos": pos, "key": key, "site": site})
    return mine, avail


def sleeper_dst_k(season: int, week: int) -> Tuple[Dict[str, float], Dict[str, dict]]:
    """(DEF team -> Sleeper pts, normalized kicker name -> {pts, team})."""
    url = config.SENTIMENT_CONFIG["sleeper_projections_url"].format(
        season=season, week=week
    )
    raw = sleeper_http.fetch_sleeper_json(url) or {}
    reg = load_sleeper_players()
    defs: Dict[str, float] = {}
    ks: Dict[str, dict] = {}
    for sid, v in raw.items():
        stats = v.get("stats") if isinstance(v, dict) and "stats" in v else v
        if not isinstance(stats, dict):
            continue
        pts = stats.get("pts_std")
        if pts is None:
            continue
        if not str(sid).isdigit():
            defs[str(sid).upper()] = float(pts)
            continue
        meta = reg.get(str(sid)) or {}
        if meta.get("position") == "K" and meta.get("full_name"):
            ks[normalize_name(meta["full_name"])] = {
                "pts": float(pts),
                "team": str(meta.get("team") or ""),
            }
    return defs, ks


def fmt(v: Optional[float], w: int = 5) -> str:
    return f"{v:{w}.1f}" if v is not None and not pd.isna(v) else " " * (w - 1) + "-"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--pool", type=Path, required=True)
    ap.add_argument("--season", type=int)
    ap.add_argument("--week", type=int)
    ap.add_argument("--weeks", type=int, default=3, help="look-ahead window")
    ap.add_argument("--top", type=int, default=6)
    args = ap.parse_args(argv)

    if args.season and args.week:
        season, week = args.season, args.week
    else:
        season, week = set_lineups._default_week(args.season)
        week = args.week or week

    mine, avail = read_pool(args.pool)
    sched = pd.read_parquet(
        sorted(
            glob.glob(
                str(REPO_ROOT / f"data/bronze/schedules/season={season}/*.parquet")
            )
        )[-1]
    )
    odds_files = sorted(
        glob.glob(
            str(REPO_ROOT / f"data/bronze/odds_api/snapshots/season={season}/*.parquet")
        )
    )
    live = (
        implied_totals_from_odds(pd.read_parquet(odds_files[-1])) if odds_files else {}
    )
    weeks = list(range(week, week + args.weeks))
    mt = matchup_table(sched, weeks, current_week_odds=live)
    slp_def, slp_k = sleeper_dst_k(season, week)

    def row_for(r: dict) -> dict:
        if r["pos"] == "DEF":
            team = r["key"].upper()
            slp = slp_def.get(team)
        else:
            k = slp_k.get(normalize_name(r["key"]), {})
            team, slp = k.get("team", "?"), k.get("pts")
        cur = mt[(mt.team == team) & (mt.week == week)]
        c = cur.iloc[0] if len(cur) else None
        proj = r["site"] if r["site"] is not None else slp
        return {
            **r,
            "team": team,
            "slp": slp,
            "proj": proj,
            "bye": bool(c.bye) if c is not None else False,
            "opp": None if c is None or c.bye else f"{'vs' if c.home else '@'}{c.opp}",
            "vegas": (
                None
                if c is None or c.bye
                else (c.opp_implied if r["pos"] == "DEF" else c.own_implied)
            ),
        }

    def outlook(team: str, pos: str) -> str:
        parts = []
        for w in weeks[1:]:
            x = mt[(mt.team == team) & (mt.week == w)]
            if not len(x):
                continue
            x = x.iloc[0]
            if x.bye:
                parts.append(f"w{w} BYE")
            else:
                v = x.opp_implied if pos == "DEF" else x.own_implied
                parts.append(
                    f"w{w} {'vs' if x.home else '@'}{x.opp} {fmt(v, 4).strip()}"
                )
        return "  ".join(parts)

    print(f"\n=== DEF/K streaming — {season} week {week} ({args.pool.name}) ===")
    print(
        "SITE = league projection, SLPR = Sleeper, VEGAS = opp implied (DEF, lower=better)"
        " / own implied (K, higher=better); look-ahead uses lines or points-per-game form"
    )
    for pos in ("DEF", "K"):
        my = [row_for(r) for r in mine if r["pos"] == pos]
        cand = [row_for(r) for r in avail if r["pos"] == pos]
        if not my and not cand:
            continue
        print(f"\n-- {pos} --")
        cur = my[0] if my else None
        if cur:
            print(
                f"  MINE  {cur['key'][:18]:18} {cur['team']:4} {str(cur['opp'] or 'BYE'):7}"
                f" site{fmt(cur['site'])} slpr{fmt(cur['slp'])} vegas{fmt(cur['vegas'])}"
                f"   next: {outlook(cur['team'], pos)}"
            )
        key = (
            (lambda r: (r["proj"] or -99, -(r["vegas"] or 99)))
            if pos == "DEF"
            else (lambda r: (r["proj"] or -99, r["vegas"] or -99))
        )
        for r in sorted((c for c in cand if not c["bye"]), key=key, reverse=True)[
            : args.top
        ]:
            verdict = ""
            if cur and cur["proj"] is not None and r["proj"] is not None:
                pg = r["proj"] - cur["proj"]
                if cur["vegas"] is None:  # my player is on bye: any healthy option wins
                    verdict = "SWAP (mine on bye)"
                elif r["vegas"] is not None:
                    vg = (
                        (cur["vegas"] - r["vegas"])
                        if pos == "DEF"
                        else (r["vegas"] - cur["vegas"])
                    )
                    verdict = swap_verdict(
                        pg, vg, proj_min=1.5, vegas_min=2.0 if pos == "DEF" else 1.5
                    )
            print(
                f"        {r['key'][:18]:18} {r['team']:4} {str(r['opp']):7}"
                f" site{fmt(r['site'])} slpr{fmt(r['slp'])} vegas{fmt(r['vegas'])}"
                f"   {verdict:18} next: {outlook(r['team'], pos)}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
