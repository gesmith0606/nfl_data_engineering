"""A machine-readable record of every waiver report, so past advice can be scored.

Until 2026-11-15 the report existed only as terminal output: nothing saved it,
so "what did the board say in week 5 and what did those names go on to score?"
could only be answered by rebuilding the board from data that had since moved
(rosters, depth charts and injury reports are overwritten in place). The record
is that week's listing, frozen: every candidate the report printed with its
rank and score components, the bid it recommended, the board file it used, and
how old each input was -- plus every place the report fell back to a guess, so
a number built on one is never mistaken for a consensus.

Written to ``data/waivers/reports/<league>/season=YYYY/week=WW/`` (tracked, see
``.gitignore``); read back by ``scripts/waiver_scorecard.py``.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD_ROOT = REPO_ROOT / "data" / "waivers" / "reports"
SCHEMA = 1


_STAMP = re.compile(r"(\d{8}_\d{6})")


def file_freshness(path: Optional[Path], now: Optional[float] = None) -> Dict[str, Any]:
    """``{file, stamp, age_hours}`` for an input file; all None when it is absent.

    ``stamp`` is the write time the producer put in the file name. ``age_hours``
    is measured from it (read as UTC, which is what CI writes; a local build is
    a few hours off) because a committed file's mtime is its checkout time and
    says nothing about the data. Files without a stamp fall back to mtime.
    """
    if path is None or not Path(path).exists():
        return {"file": None, "stamp": None, "age_hours": None}
    now = now if now is not None else time.time()
    m = _STAMP.search(Path(path).name)
    if m:
        made = dt.datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
        made_at = made.replace(tzinfo=dt.timezone.utc).timestamp()
    else:
        made_at = Path(path).stat().st_mtime
    return {
        "file": Path(path).name,
        "stamp": m.group(1) if m else None,
        "age_hours": round((now - made_at) / 3600, 1),
    }


def _clean(v: Any) -> Any:
    """JSON-safe: numpy scalars to Python, NaN/inf to None, tuples to lists."""
    if hasattr(v, "item") and not isinstance(v, (list, tuple, dict)):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, float):
        return round(v, 3) if math.isfinite(v) else None
    if isinstance(v, Mapping):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_clean(x) for x in v]
    return v


def candidate_row(list_name: str, rank: int, r: Mapping[str, Any]) -> Dict[str, Any]:
    """One listed candidate: its rank, score components and recommended bid."""
    ours, slpr = r.get("ours"), r.get("slpr")
    has_ours = ours is not None and not _isnan(ours)
    has_slpr = slpr is not None and not _isnan(slpr)
    snap = r.get("snap")
    bid = r.get("bid")
    return _clean(
        {
            "list": list_name,
            "rank": rank,
            "sid": r.get("sid"),
            "name": r.get("name"),
            "pos": r.get("pos"),
            "team": r.get("team"),
            "age": r.get("age"),
            "ours": ours if has_ours else None,
            "slpr": slpr if has_slpr else None,
            "blend": r.get("blend"),
            # Which sources the blend actually averaged. A row whose projection
            # of ours is missing is Sleeper alone, and a Sleeper zero halves
            # the blend; both used to be invisible in the number.
            "blend_basis": (
                "both"
                if has_ours and has_slpr
                else "ours_only" if has_ours else "sleeper_only"
            ),
            "sleeper_zero": bool(has_slpr and float(slpr) == 0.0),
            "last": r.get("last"),
            "adds_48h": r.get("adds"),
            "snap_pct": snap[0] if snap else None,
            "snap_delta": snap[1] if snap else None,
            "dyn": r.get("dyn"),
            "verdict": r.get("verdict"),
            "bid": bid[0] if bid else None,
            "bid_reason": bid[1] if bid else None,
            "demand": r.get("demand") or None,
            "injury": r.get("inj") or None,
            "news": r.get("news") or None,
            "blocked_by": list(r.get("blocked_by") or []),
            "role_ending": bool(r.get("blocked_returning")),
            "bye": bool(r.get("bye")),
        }
    )


def _isnan(v: Any) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def build_record(
    *,
    league: str,
    platform: str,
    season: int,
    week: int,
    title: str,
    generated_at: str,
    inputs: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    fallbacks: Sequence[str],
    extras: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the record. ``extras`` carries roster, drops, claims file, gate."""
    return _clean(
        {
            "schema": SCHEMA,
            "league": league,
            "platform": platform,
            "season": season,
            "week": week,
            "title": title,
            "generated_at": generated_at,
            "inputs": dict(inputs),
            "fallbacks": list(fallbacks),
            "candidates": list(candidates),
            **(dict(extras) if extras else {}),
        }
    )


def record_dir(league: str, season: int, week: int, root: Path = RECORD_ROOT) -> Path:
    return Path(root) / league / f"season={season}" / f"week={week:02d}"


def write_record(record: Mapping[str, Any], root: Path = RECORD_ROOT) -> Path:
    """Write one file per run (never overwrites); returns its path."""
    stamp = dt.datetime.fromisoformat(str(record["generated_at"])).strftime(
        "%Y%m%d_%H%M%S"
    )
    folder = record_dir(
        str(record["league"]), int(record["season"]), int(record["week"]), root
    )
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"report_{stamp}.json"
    path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return path


def latest_record(
    league: str, season: int, week: int, root: Path = RECORD_ROOT
) -> Optional[Path]:
    """The newest record for a league-week, or None."""
    files = sorted(record_dir(league, season, week, root).glob("report_*.json"))
    return files[-1] if files else None


def fallback_notes(
    *,
    week: int,
    ours_label: str,
    weekly_board: bool,
    guessed_pool: bool,
    draft_size: int,
    dynasty_missing: bool,
    news_flags: int,
    official_reports: int,
    snap_players: int,
    have_history: bool,
    have_budget: bool,
    bronze_max_week: int,
    recorded: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Every place this run quietly substituted a guess for a reading.

    Each of these used to be a warning line that scrolled past (or nothing at
    all): a missing weekly board became preseason points / 17, a Sleeper zero
    halved the blend, an unknown dynasty value read as 0, an unknown pool was
    guessed from ADP. The record carries them so a score can be read next to
    how much of the advice was a reading.
    """
    out: List[str] = []
    if not weekly_board:
        out.append(
            f"board: no usable weekly Gold for week {week} -- OURS is {ours_label}"
        )
    if guessed_pool:
        out.append(
            "pool: other rosters unknown -- free agents guessed from ADP "
            f"(undrafted or beyond pick {draft_size})"
        )
    if dynasty_missing:
        out.append("dynasty value: FantasyCalc unavailable -- DYN is 0 for everyone")
    if not news_flags:
        out.append(f"news: no sentiment flags for week {week}")
    if not official_reports:
        out.append(f"injuries: no official report for week {week} -- Sleeper tags only")
    if not snap_players:
        out.append("snaps: no Bronze snap counts -- SNAP column empty")
    if not have_history:
        out.append("demand: no transaction history -- no bids computed")
    elif not have_budget:
        out.append("budget: FAAB left unknown -- no bids computed")
    if bronze_max_week < week - 1:
        out.append(
            f"last: Bronze weekly stops at week {bronze_max_week}, LAST wants {week - 1}"
        )
    zero = sum(1 for c in recorded if c.get("sleeper_zero"))
    one = sum(1 for c in recorded if c.get("blend_basis") != "both")
    if zero:
        out.append(
            f"blend: {zero} listed row(s) have a Sleeper projection of 0 (blend halved)"
        )
    if one:
        out.append(f"blend: {one} listed row(s) rest on a single projection source")
    return out
