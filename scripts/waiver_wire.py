#!/usr/bin/env python3
"""Weekly waiver-wire report: free agents on two projection sources + last week's actuals.

    python scripts/waiver_wire.py --league mantis
    python scripts/waiver_wire.py --league la_liga --roster-file data/draft/la_liga_2026_roster.txt

Sleeper leagues: every roster in the league is pulled live, so the free-agent pool is
exact and both sources are scored under the league's own ``scoring_settings``.
ESPN/Yahoo leagues have no roster reader yet: pass ``--roster-file`` (one name per
line) for YOUR roster. Other teams' rosters are unknown, so each candidate carries the
room ADP rank and an ``FA?`` guess (undrafted by ADP) that you must verify on the site.

Columns: OURS = our weekly Gold projection, SLPR = Sleeper's weekly projection,
BLEND = mean of the two, LAST = last week's actual under the same scoring,
ADDS = Sleeper trending adds (48h, thousands), NEWS = Gold sentiment flags.
Drop candidates are the lowest-BLEND bench players (K/DEF are not scored here).
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, sleeper_http  # noqa: E402
from src.lineup_setter import (  # noqa: E402
    SKILL_POSITIONS,
    build_id_maps,
    ours_by_sleeper_id,
    roster_gsis_map,
    score_ours,
    score_sleeper_stats,
)
from src.sleeper_player_map import load_sleeper_players, normalize_name  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "set_lineups", REPO_ROOT / "scripts" / "set_lineups.py"
)
set_lineups = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(set_lineups)  # type: ignore[union-attr]

GOLD = REPO_ROOT / "data" / "gold"
BRONZE = REPO_ROOT / "data" / "bronze"
ADP_FILES = {
    "espn": "adp_espn_half_ppr.csv",
    "yahoo": "adp_yahoo_feetball_half_ppr.csv",
}
TRENDING_URL = (
    "https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=48&limit=200"
)

# SCORING_CONFIGS vocabulary -> Sleeper scoring_settings vocabulary (ESPN/Yahoo leagues).
_TO_SLEEPER_KEYS = {
    "reception": "rec",
    "rush_yd": "rush_yd",
    "rec_yd": "rec_yd",
    "rush_td": "rush_td",
    "rec_td": "rec_td",
    "pass_yd": "pass_yd",
    "pass_td": "pass_td",
    "interception": "pass_int",
    "fumble_lost": "fum_lost",
}
_ACTUAL_COLS = {
    "passing_yards": "passing_yards",
    "passing_tds": "passing_tds",
    "interceptions": "interceptions",
    "rushing_yards": "rushing_yards",
    "rushing_tds": "rushing_tds",
    "receptions": "receptions",
    "receiving_yards": "receiving_yards",
    "receiving_tds": "receiving_tds",
}


def scoring_for(
    preset: Dict[str, Any], league: Optional[Dict[str, Any]]
) -> Dict[str, float]:
    if league and league.get("scoring_settings"):
        return league["scoring_settings"]
    base = config.SCORING_CONFIGS[preset["scoring_format"]]
    return {_TO_SLEEPER_KEYS[k]: v for k, v in base.items() if k in _TO_SLEEPER_KEYS}


def last_week_actuals(
    season: int, week: int, scoring: Dict[str, float]
) -> pd.DataFrame:
    files = sorted(
        glob.glob(str(BRONZE / "players" / "weekly" / f"season={season}" / "*.parquet"))
    )
    if not files:
        return pd.DataFrame()
    df = pd.read_parquet(files[-1])
    df = df[(df["week"] == week) & df["position"].isin(SKILL_POSITIONS)]
    if "player_display_name" in df.columns:
        df = df.rename(columns={"player_display_name": "player_name"})
    keep = ["player_id", "player_name", "position", "recent_team"] + list(_ACTUAL_COLS)
    return score_ours(df[[c for c in keep if c in df.columns]].copy(), scoring)


def sentiment_flags() -> Dict[str, str]:
    files = sorted(
        glob.glob(str(GOLD / "sentiment" / "season=*" / "week=*" / "*.parquet"))
    )
    if not files:
        return {}
    df = pd.read_parquet(files[-1])
    flags = [c for c in df.columns if c.startswith("is_")]
    out: Dict[str, str] = {}
    for row in df.itertuples(index=False):
        tags = [c[3:] for c in flags if getattr(row, c)]
        if tags:
            out[str(row.player_id)] = ",".join(tags)
    return out


def adp_rank_map(platform: str) -> Dict[str, int]:
    path = REPO_ROOT / "data" / "adp" / ADP_FILES.get(platform, "")
    if not path.is_file():
        return {}
    df = pd.read_csv(path)
    return {
        normalize_name(str(n)): int(r)
        for n, r in zip(df["player_name"], df["adp_rank"])
    }


def roster_ids_from_file(path: Path, by_name: Dict[Any, str]) -> Set[str]:
    ids: Set[str] = set()
    for line in path.read_text().splitlines():
        name = line.split("#", 1)[0].strip()
        if not name:
            continue
        norm = normalize_name(name)
        hit = next((sid for (n, _p), sid in by_name.items() if n == norm), None)
        if hit is None:
            print(f"WARN: roster name not in Sleeper registry: {name}")
        else:
            ids.add(hit)
    return ids


def fmt(v: Optional[float]) -> str:
    return f"{v:5.1f}" if v is not None else "    -"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", required=True, help="LEAGUE_PRESETS key")
    ap.add_argument("--week", type=int, help="NFL week to project (default: upcoming)")
    ap.add_argument("--season", type=int)
    ap.add_argument(
        "--user", help="Sleeper display name (default: preset my_user / georgesmith)"
    )
    ap.add_argument(
        "--roster-file", type=Path, help="ESPN/Yahoo: my roster, one name per line"
    )
    ap.add_argument("--top", type=int, default=6, help="free agents shown per position")
    args = ap.parse_args(argv)

    preset = config.LEAGUE_PRESETS.get(args.league)
    if preset is None:
        sys.exit(
            f"Unknown league '{args.league}'. Presets: {sorted(config.LEAGUE_PRESETS)}"
        )
    platform = preset.get("platform")
    if args.season and args.week:
        season, week = args.season, args.week
    else:
        season, week = set_lineups._default_week(args.season)
        week = args.week or week

    registry = load_sleeper_players()
    by_gsis, by_name = build_id_maps(registry)
    league = None
    rostered: Set[str] = set()
    mine: List[str] = []
    starters: Set[str] = set()
    if platform == "sleeper":
        league = sleeper_http.get_league(str(preset["league_id"]))
        if not league:
            sys.exit("Sleeper league unavailable")
        username = args.user or preset.get("my_user") or "georgesmith"
        for r in sleeper_http.get_league_rosters(str(preset["league_id"])):
            rostered.update(str(p) for p in (r.get("players") or []))
        my = set_lineups.find_my_roster(str(preset["league_id"]), username)
        mine = [
            str(p) for p in (my.get("players") or []) if p not in (my.get("taxi") or [])
        ]
        starters = {str(p) for p in (my.get("starters") or [])}
        title = f"{league.get('name')} — {username}"
    else:
        if not args.roster_file:
            sys.exit(
                f"{args.league} is on {platform}: pass --roster-file with your roster"
            )
        mine = sorted(roster_ids_from_file(args.roster_file, by_name))
        rostered = set(mine)
        title = f"{args.league} ({platform}, my roster from {args.roster_file.name})"
    scoring = scoring_for(preset, league)

    ours_df, ours_label = set_lineups.load_ours(season, week)
    roster_files = glob.glob(
        str(BRONZE / "players" / "rosters" / "season=*" / "**" / "*.parquet"),
        recursive=True,
    )
    gsis_map = roster_gsis_map(
        pd.concat([pd.read_parquet(f) for f in roster_files], ignore_index=True)
    )
    ours = ours_by_sleeper_id(score_ours(ours_df, scoring), registry, gsis_map=gsis_map)
    slpr_raw = set_lineups.load_sleeper_projections(season, week)
    last = ours_by_sleeper_id(
        last_week_actuals(season, week - 1, scoring), registry, gsis_map=gsis_map
    )
    adds = {
        str(t["player_id"]): t["count"]
        for t in (sleeper_http.fetch_sleeper_json(TRENDING_URL) or [])
    }
    news_by_gsis = sentiment_flags()
    gsis_to_sid = {**by_gsis, **gsis_map}
    news = {gsis_to_sid[g]: f for g, f in news_by_gsis.items() if g in gsis_to_sid}
    adp = adp_rank_map(platform) if platform != "sleeper" else {}
    draft_size = preset["teams"] * sum(config.ROSTER_CONFIGS[preset["roster"]].values())

    def adp_rank(sid: str, meta: Dict[str, Any]) -> Optional[int]:
        """Room ADP rank, else Sleeper's own ADP from the projection feed (1000 = undrafted)."""
        rank = adp.get(normalize_name(str(meta.get("full_name") or "")))
        if rank is None:
            dd = (slpr_raw.get(sid) or {}).get("adp_dd_ppr")
            rank = int(dd) if dd and dd < 1000 else None
        return rank

    def row(sid: str) -> Optional[Dict[str, Any]]:
        meta = registry.get(sid) or {}
        pos = str(meta.get("position") or "")
        if pos not in SKILL_POSITIONS or not meta.get("team"):
            return None
        stats = slpr_raw.get(sid) or {}
        s = score_sleeper_stats(stats, scoring, pos) if stats else None
        o = ours.get(sid)
        both = [v for v in (o, s) if v is not None]
        if not both:
            return None
        return {
            "sid": sid,
            "name": meta.get("full_name") or sid,
            "pos": pos,
            "team": meta.get("team"),
            "ours": o,
            "slpr": s,
            "blend": sum(both) / len(both),
            "last": last.get(sid),
            "adds": adds.get(sid, 0),
            "inj": meta.get("injury_status") or "",
            "news": news.get(sid, ""),
            "adp": adp_rank(sid, meta),
        }

    def likely_fa(r: Dict[str, Any]) -> bool:
        return platform == "sleeper" or r["adp"] is None or r["adp"] > draft_size

    def line(r: Dict[str, Any], tag: str = "") -> str:
        fa = ""
        if platform != "sleeper":
            fa = "FA?" if likely_fa(r) else f"adp{r['adp']}"
        return (
            f"  {tag:6}{r['name'][:24]:24} {r['pos']:3}{r['team']:4}"
            f" ours{fmt(r['ours'])} slpr{fmt(r['slpr'])} blend{fmt(r['blend'])}"
            f" last{fmt(r['last'])} adds{r['adds'] / 1000:5.0f}k {fa:7}"
            f" {r['inj']:4} {r['news']}"
        )

    print(f"\n=== {title} — {season} week {week} waivers ===")
    print(
        f"OURS = {ours_label}; SLPR = Sleeper week {week}; LAST = week {week - 1} actuals"
    )
    if platform != "sleeper":
        print(
            f"Other rosters unknown: showing only players drafted beyond pick {draft_size} "
            f"({platform} ADP, Sleeper ADP fallback) — verify availability on the site"
        )

    fas = [
        r for r in (row(s) for s in registry if s not in rostered) if r and likely_fa(r)
    ]
    for pos in ("QB", "RB", "WR", "TE"):
        print(f"\n-- {pos} free agents --")
        for r in sorted((r for r in fas if r["pos"] == pos), key=lambda r: -r["blend"])[
            : args.top
        ]:
            print(line(r))
    hot = sorted((r for r in fas if r["adds"] >= 100_000), key=lambda r: -r["adds"])[
        :10
    ]
    if hot:
        print("\n-- Most added on Sleeper (48h) still available --")
        for r in hot:
            print(line(r))

    my_rows = [r for r in (row(s) for s in mine) if r]
    unscored = [
        registry.get(s, {}).get("full_name") or s for s in mine if row(s) is None
    ]
    missing = ", ".join(map(str, unscored)) or "none"
    print(
        f"\n-- My roster (weakest first; {len(my_rows)} scored, unscored: {missing}) --"
    )
    for r in sorted(my_rows, key=lambda r: r["blend"]):
        print(line(r, "START" if r["sid"] in starters else "bench"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
