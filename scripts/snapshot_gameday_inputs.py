#!/usr/bin/env python3
"""Save dated copies of what Sleeper says about the week RIGHT NOW.

    python scripts/snapshot_gameday_inputs.py              # the upcoming week
    python scripts/snapshot_gameday_inputs.py --week 11

Why: the lineup replay (``scripts/replay_lineups.py``) could only use the
Sleeper projections the API serves today for past weeks, and the registry file
``data/bronze/players/sleeper_players.json`` is overwritten in place, so every
past injury tag was gone. A replay that is graded on "what was known at kickoff"
needs the values as they stood then. Run this on game-day mornings (and the
evening before a Thursday game) and every later replay can use them.

Writes, under ``data/bronze/gameday_inputs/season=YYYY/week=WW/``:

    sleeper_projections_<UTC ts>.parquet   sleeper_player_id, raw_payload (JSON stat dict)
    sleeper_status_<UTC ts>.parquet        one row per fantasy-relevant player: team, status,
                                           injury_status / body part / practice, news_updated,
                                           depth_chart_order

Same ``raw_payload`` shape as ``data/bronze/external_projections/sleeper``, so
anything that reads that can read these. Fails open (D-06): no payload, no file,
exit 0, a loud line saying so.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, sleeper_http  # noqa: E402
from src import sleeper_player_map  # noqa: E402
from src.sleeper_player_map import load_sleeper_players  # noqa: E402

ROOT = REPO_ROOT / "data" / "bronze" / "gameday_inputs"
_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}
STATUS_FIELDS = [
    "team",
    "status",
    "injury_status",
    "injury_body_part",
    "practice_participation",
    "news_updated",
    "depth_chart_order",
    "position",
    "full_name",
]


def projections_frame(raw: Any) -> pd.DataFrame:
    """Sleeper's projections payload -> one row per player with the JSON stat dict."""
    if isinstance(raw, list):  # defensive: a list of {player_id, stats}
        raw = {str(x.get("player_id")): x for x in raw if isinstance(x, dict)}
    rows = []
    for pid, v in (raw or {}).items():
        stats = v.get("stats") if isinstance(v, dict) and "stats" in v else v
        if isinstance(stats, dict) and stats:  # nothing projected: not worth a row
            rows.append(
                {"sleeper_player_id": str(pid), "raw_payload": json.dumps(stats)}
            )
    return pd.DataFrame(rows, columns=["sleeper_player_id", "raw_payload"])


def status_frame(registry: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    """Fantasy-relevant slice of the player registry, tags and all."""
    rows = []
    for pid, meta in registry.items():
        if not isinstance(meta, dict) or meta.get("position") not in _POSITIONS:
            continue
        if not meta.get("team") and not meta.get("injury_status"):
            continue  # unsigned and untagged: nobody rosters him
        rows.append({"sleeper_id": str(pid), **{f: meta.get(f) for f in STATUS_FIELDS}})
    df = pd.DataFrame(rows, columns=["sleeper_id", *STATUS_FIELDS])
    return df.astype(
        {"news_updated": "float64", "depth_chart_order": "float64"}, errors="ignore"
    )


def _registry_age_hours() -> float:
    """Age of the on-disk registry cache the loader just (re)wrote."""
    import os
    import time

    try:
        return (time.time() - os.path.getmtime(sleeper_player_map._CACHE_PATH)) / 3600
    except OSError:
        return float("inf")


def write_snapshot(
    df: pd.DataFrame, root: Path, season: int, week: int, kind: str, now: dt.datetime
) -> Path:
    out = root / f"season={season}" / f"week={week:02d}"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{kind}_{now:%Y%m%d_%H%M%S}.parquet"
    df.to_parquet(path, index=False)
    return path


def snapshot(
    season: int, week: int, root: Path = ROOT, now: Optional[dt.datetime] = None
) -> List[Path]:
    """Fetch and save both snapshots; returns the paths written (empty on failure)."""
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    written: List[Path] = []
    url = config.SENTIMENT_CONFIG["sleeper_projections_url"].format(
        season=season, week=week
    )
    proj = projections_frame(sleeper_http.fetch_sleeper_json(url))
    if proj.empty:
        print(
            f"NO SNAPSHOT: Sleeper projections empty for {season} week {week} ({url})"
        )
    else:
        written.append(
            write_snapshot(proj, root, season, week, "sleeper_projections", now)
        )
    # force_refresh: a snapshot of a stale cache is a snapshot of the wrong moment
    status = status_frame(load_sleeper_players(force_refresh=True))
    if status.empty:
        print("NO SNAPSHOT: Sleeper player registry empty")
    elif _registry_age_hours() > 1:
        # the fetch failed and the loader fell back to an old cache: do not file
        # last Tuesday's injury tags under today's timestamp
        print(
            f"NO SNAPSHOT: registry fetch failed, cache is {_registry_age_hours():.0f}h old"
        )
    else:
        written.append(
            write_snapshot(status, root, season, week, "sleeper_status", now)
        )
    return written


# ---------------------------------------------------------------------------
# Readers (what the replay uses)
# ---------------------------------------------------------------------------


def _stamp(path: Path) -> dt.datetime:
    return dt.datetime.strptime("_".join(path.stem.split("_")[-2:]), "%Y%m%d_%H%M%S")


def latest_before(
    root: Path, season: int, week: int, kind: str, cutoff_utc: dt.datetime
) -> Optional[Path]:
    """Newest ``kind`` snapshot for the week stamped at or before ``cutoff_utc``."""
    files = [
        f
        for f in (root / f"season={season}" / f"week={week:02d}").glob(
            f"{kind}_*.parquet"
        )
        if _stamp(f) <= cutoff_utc
    ]
    return max(files, key=_stamp) if files else None


def read_projections(
    root: Path, season: int, week: int, cutoff_utc: dt.datetime
) -> Optional[Dict[str, Dict[str, Any]]]:
    """``{sleeper_id: stat dict}`` as saved before the cutoff, or None if nothing was saved."""
    path = latest_before(root, season, week, "sleeper_projections", cutoff_utc)
    if path is None:
        return None
    df = pd.read_parquet(path)
    return {
        str(s): json.loads(p)
        for s, p in zip(df["sleeper_player_id"], df["raw_payload"])
        if p
    }


def read_status(
    root: Path, season: int, week: int, cutoff_utc: dt.datetime
) -> Optional[Dict[str, Dict[str, Any]]]:
    """``{sleeper_id: {injury_status, ...}}`` as saved before the cutoff, or None."""
    path = latest_before(root, season, week, "sleeper_status", cutoff_utc)
    if path is None:
        return None
    df = pd.read_parquet(path)
    keep = [
        "injury_status",
        "injury_body_part",
        "practice_participation",
        "news_updated",
    ]
    return {
        str(r["sleeper_id"]): {k: r[k] for k in keep if pd.notna(r[k])}
        for r in df.to_dict("records")
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--season", type=int)
    ap.add_argument("--week", type=int)
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    season, week = args.season, args.week
    if not (season and week):
        from scripts import set_lineups

        s, w = set_lineups._default_week(season)
        season, week = season or s, week or w
    paths = snapshot(season, week, args.root)
    for p in paths:
        print(f"saved {p.relative_to(REPO_ROOT) if p.is_relative_to(REPO_ROOT) else p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
