"""Rebuild a Sleeper league's past waiver weeks from disk: the replay context.

Shared by ``scripts/waiver_scorecard.py`` (score what happened) and
``scripts/backtest_clearing_price.py`` (replay the bids). Everything here is a
read: Sleeper's public API (cached under ``data/cache/sleeper/<league_id>/``),
the weekly boards under ``data/gold/projections``, and Bronze weekly stats.

A week's *pool* is rebuilt the way the report builds it: every skill player
nobody rostered on Tuesday evening (rosters are today's, with every later move
undone), scored by both sources under the league's scoring, ranked within
position by their mean (the BLEND column). Sleeper's projections are as served
today, which includes later revisions, so they flatter Sleeper against our
pre-kickoff board; say so whenever the two are compared.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from src import config, recommendation_backtest as rb, sleeper_http
from src import waiver_scorecard as sc
from src.lineup_setter import (
    SKILL_POSITIONS,
    full_name_map,
    ours_by_sleeper_id,
    roster_gsis_map,
    score_ours,
    score_sleeper_stats,
    weekly_gold_to_stats,
)
from src.sleeper_player_map import load_sleeper_players

REPO_ROOT = Path(__file__).resolve().parent.parent
API = "https://api.sleeper.app/v1"


# --------------------------------------------------------------------- loading


def _cached(cache: Path, name: str, url: str, refresh: bool) -> Any:
    path = cache / f"{name}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    data = sleeper_http.fetch_sleeper_json(url)
    if not data and data != []:
        sys.exit(f"Sleeper returned nothing for {url} — not guessing past it")
    cache.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def load_sleeper(
    league_id: str, season: int, last_week: int, cache: Path, refresh: bool
) -> Dict[str, Any]:
    """League, rosters, transactions, stats and projections, cached on disk."""
    get = lambda name, url: _cached(cache, name, url, refresh)  # noqa: E731
    league = get("league", f"{API}/league/{league_id}")
    txs: List[Dict[str, Any]] = []
    for leg in range(1, last_week + 3):
        for t in get(f"tx_{leg}", f"{API}/league/{league_id}/transactions/{leg}"):
            txs.append({**t, "_leg": leg})
    return {
        "league": league,
        "users": get("users", f"{API}/league/{league_id}/users"),
        "rosters": get("rosters", f"{API}/league/{league_id}/rosters"),
        "txs": sorted(txs, key=lambda t: t["status_updated"]),
        "stats": {
            w: get(f"stats_{w}", f"{API}/stats/nfl/regular/{season}/{w}")
            for w in range(1, last_week + 1)
        },
        "proj": {
            w: get(
                f"proj_{w}",
                config.SENTIMENT_CONFIG["sleeper_projections_url"].format(
                    season=season, week=w
                ),
            )
            for w in range(1, last_week + 2)  # + the week being decided
        },
        "registry": (
            load_sleeper_players(max_age_days=3650)
            if not (cache / "players.json").exists()
            else json.loads((cache / "players.json").read_text(encoding="utf-8"))
        ),
    }


def roots(extra: Sequence[str]) -> List[Path]:
    return [REPO_ROOT, *[Path(p) for p in extra]]


def schedule(season: int, roots: Sequence[Path]) -> pd.DataFrame:
    files = sorted(
        f
        for r in roots
        for f in glob.glob(
            str(r / f"data/bronze/schedules/season={season}/**/*.parquet"),
            recursive=True,
        )
    )
    if not files:
        sys.exit(f"no schedule for {season} under {list(map(str, roots))}")
    return pd.read_parquet(sorted(files, key=lambda f: Path(f).name)[-1])


def week1_start_ms(sched: pd.DataFrame) -> int:
    """Tuesday 00:00 ET before week 1's first game (04:00 UTC, EDT)."""
    first = pd.to_datetime(sched[sched["week"] == 1]["gameday"].min())
    tuesday = first - pd.Timedelta(days=(first.weekday() - 1) % 7)
    return int(tuesday.tz_localize("UTC").timestamp() * 1000) + 4 * 3_600_000


def last_complete_week(sched: pd.DataFrame, today: Optional[dt.date] = None) -> int:
    """Highest week whose last game was before yesterday."""
    today = today or dt.date.today()
    done = sched[sched["week"] <= 18].groupby("week")["gameday"].max()
    ok = [
        int(w)
        for w, d in done.items()
        if pd.to_datetime(d).date() < today - dt.timedelta(days=1)
    ]
    return max(ok) if ok else 0


def board_for(
    week: int, season: int, sched: pd.DataFrame, roots: Sequence[Path]
) -> Optional[str]:
    """Latest board written before ``week``'s first kickoff, across all roots."""
    kickoff = rb.first_kickoff(sched, week)
    if kickoff is None:
        return None
    best, best_at = None, None
    for r in roots:
        for f in glob.glob(
            str(r / f"data/gold/projections/season={season}/week={week}/*.parquet")
        ):
            at = rb.board_stamp(f)
            if at is not None and at < kickoff and (best_at is None or at > best_at):
                best, best_at = f, at
    return best


def latest_weekly(season: int, roots: Sequence[Path]) -> pd.DataFrame:
    files = [
        f
        for r in roots
        for f in glob.glob(
            str(r / f"data/bronze/players/weekly/season={season}/*.parquet")
        )
    ]
    return pd.read_parquet(sorted(files, key=lambda f: Path(f).name)[-1])


# ----------------------------------------------------------------------- pool


def build_pool(
    week: int,
    board_path: str,
    ctx: Mapping[str, Any],
    pts: sc.Pts,
    last_week: int,
    weekly_df: pd.DataFrame,
    roots: Sequence[Path],
) -> List[Dict[str, Any]]:
    """The free agents a Tuesday report could rank, with what they went on to score."""
    registry, scoring = ctx["registry"], ctx["scoring"]
    ours = ours_by_sleeper_id(
        score_ours(weekly_gold_to_stats(pd.read_parquet(board_path)), scoring),
        registry,
        gsis_map=ctx["gsis_map"],
        full_names=ctx["names"],
    )
    prev = weekly_df[
        (weekly_df["week"] == week - 1) & weekly_df["position"].isin(SKILL_POSITIONS)
    ]
    prev = prev.rename(columns={"player_display_name": "player_name"})
    cols = [
        "player_id",
        "player_name",
        "position",
        "recent_team",
        "passing_yards",
        "passing_tds",
        "interceptions",
        "rushing_yards",
        "rushing_tds",
        "receptions",
        "receiving_yards",
        "receiving_tds",
    ]
    last = (
        ours_by_sleeper_id(
            score_ours(prev[[c for c in cols if c in prev.columns]].copy(), scoring),
            registry,
            gsis_map=ctx["gsis_map"],
            full_names=ctx["names"],
        )
        if week > 1
        else {}
    )
    rostered = sc.rostered_at(
        ctx["rosters_now"], ctx["txs"], sc.week_cutoff(week, ctx["week1_start"])
    )
    rows = []
    for sid, meta in registry.items():
        if sid in rostered or not isinstance(meta, dict):
            continue
        pos = meta.get("position")
        if pos not in SKILL_POSITIONS:
            continue
        stats = ctx["proj"][week].get(sid) or {}
        s = score_sleeper_stats(stats, scoring, pos) if stats else None
        o = ours.get(sid)
        both = [v for v in (o, s) if v is not None]
        if not both:
            continue
        rows.append(
            {
                "sid": sid,
                "name": meta.get("full_name") or sid,
                "pos": pos,
                "ours": o,
                "slpr": s,
                "blend": sum(both) / len(both),
                "last": last.get(sid),
                "age": meta.get("age"),
            }
        )
    return sc.attach_windows(rows, week, pts, last_week)


@dataclass
class Replay:
    """Everything a replay needs about one league-season."""

    league_id: str
    season: int
    last_week: int
    data: Dict[str, Any]
    scoring: Dict[str, float]
    sched: pd.DataFrame
    roots: List[Path]
    week1_start: int
    me: int
    ctx: Dict[str, Any]
    weekly_df: pd.DataFrame
    pts: Callable[[str, int], float]

    def name(self, pid: Any) -> str:
        meta = self.data["registry"].get(str(pid)) or {}
        return meta.get("full_name") or str(pid)

    def pos_of(self, pid: Any) -> Optional[str]:
        return (self.data["registry"].get(str(pid)) or {}).get("position")

    def pool(self, week: int) -> Optional[List[Dict[str, Any]]]:
        """The week's free agents with windows attached, or None without a board."""
        path = board_for(week, self.season, self.sched, self.roots)
        if path is None:
            return None
        return build_pool(
            week, path, self.ctx, self.pts, self.last_week, self.weekly_df, self.roots
        )


def load_replay(
    league: str,
    season: int,
    extra_root: Sequence[str] = (),
    last_week: Optional[int] = None,
    cache: Optional[str] = None,
    refresh: bool = False,
) -> Replay:
    """Load a Sleeper league's season for replay (Sleeper presets only)."""
    preset = config.our_league(league)
    if preset.get("platform") != "sleeper":
        sys.exit(
            f"{league} is on {preset.get('platform')}: only Sleeper's log is public"
        )
    rts = roots(extra_root)
    sched = schedule(season, rts)
    last = last_week or last_complete_week(sched)
    league_id = str(preset["league_id"])
    cache_dir = (
        Path(cache) if cache else REPO_ROOT / "data" / "cache" / "sleeper" / league_id
    )
    data = load_sleeper(league_id, season, last, cache_dir, refresh)
    scoring = data["league"]["scoring_settings"]
    users = {u["user_id"]: u["display_name"] for u in data["users"]}
    me = next(
        r["roster_id"]
        for r in data["rosters"]
        if users.get(r["owner_id"], "").lower() == str(preset.get("my_user")).lower()
    )
    w1 = week1_start_ms(sched)

    def pts(pid: str, week: int) -> float:
        s = data["stats"].get(week, {}).get(str(pid))
        return sc.league_points(s, scoring) if s else 0.0

    rost_files = [
        f
        for r in rts
        for f in glob.glob(
            str(r / "data/bronze/players/rosters/season=*/**/*.parquet"), recursive=True
        )
    ]
    rosters_df = pd.concat(
        [pd.read_parquet(f) for f in sorted(set(rost_files))], ignore_index=True
    )
    weekly_df = latest_weekly(season, rts)
    ctx = {
        "registry": data["registry"],
        "scoring": scoring,
        "proj": data["proj"],
        "txs": data["txs"],
        "week1_start": w1,
        "rosters_now": {
            r["roster_id"]: r.get("players") or [] for r in data["rosters"]
        },
        "gsis_map": roster_gsis_map(rosters_df),
        "names": full_name_map(rosters_df, weekly_df),
    }
    return Replay(
        league_id, season, last, data, scoring, sched, rts, w1, me, ctx, weekly_df, pts
    )
