"""Turn live ESPN / Yahoo league reads into the ``data/draft`` pool files.

The waiver and lineup tools read hand-kept text files for the two leagues
without an API (``<league>_2026_roster.txt``, ``_all_rostered.txt`` /
``_available.txt``, ``_league_rosters.txt``, ``_dstk_pool.txt``). Keeping them
fresh by hand was slow and error-prone, so ``scripts/refresh_league_pools.py``
reads the logged-in browser over Chrome DevTools and these pure functions
render the files (offline-testable).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: ESPN defaultPositionId -> position (skill + K + D/ST).
ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
ESPN_INJ = {"QUESTIONABLE": "Q", "OUT": "O", "INJURY_RESERVE": "I", "DOUBTFUL": "D"}

#: Team nickname (as ESPN "<Nickname> D/ST" and Yahoo DEF rows show it) -> abbr.
NICKNAME_TO_ABBR = {
    "Cardinals": "ARI", "Falcons": "ATL", "Ravens": "BAL", "Bills": "BUF",
    "Panthers": "CAR", "Bears": "CHI", "Bengals": "CIN", "Browns": "CLE",
    "Cowboys": "DAL", "Broncos": "DEN", "Lions": "DET", "Packers": "GB",
    "Texans": "HOU", "Colts": "IND", "Jaguars": "JAX", "Chiefs": "KC",
    "Raiders": "LV", "Chargers": "LAC", "Rams": "LAR", "Dolphins": "MIA",
    "Vikings": "MIN", "Patriots": "NE", "Saints": "NO", "Giants": "NYG",
    "Jets": "NYJ", "Eagles": "PHI", "Steelers": "PIT", "49ers": "SF",
    "Seahawks": "SEA", "Buccaneers": "TB", "Titans": "TEN", "Commanders": "WAS",
}  # fmt: skip


def dst_abbr(name: str) -> Optional[str]:
    """``"Giants D/ST"`` / ``"Steelers"`` -> ``"NYG"`` / ``"PIT"`` (None if unknown)."""
    return NICKNAME_TO_ABBR.get(str(name).replace("D/ST", "").strip())


def _fmt_proj(v: Any) -> str:
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return ""


def _stamp(today: Optional[dt.date]) -> str:
    return (today or dt.date.today()).isoformat()


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------


def _espn_player(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    return (entry.get("playerPoolEntry") or {}).get("player") or {}


def espn_pool_files(
    payload: Mapping[str, Any],
    my_team_id: int,
    league: str,
    week: int,
    fa_dst: Sequence[Tuple[str, Any]] = (),
    my_dst_proj: Mapping[str, Any] = None,
    season: int = 2026,
    today: Optional[dt.date] = None,
) -> Dict[str, str]:
    """ESPN ``mTeam``+``mRoster`` payload -> ``{filename: text}``.

    Args:
        payload: league JSON with ``teams[].roster.entries[].playerPoolEntry.player``.
        my_team_id: our ESPN teamId.
        fa_dst: ``[(name, week projection)]`` for free-agent/waiver D/STs.
        my_dst_proj: ``{name: projection}`` for our own D/ST(s).
    """
    day = _stamp(today)
    teams = payload.get("teams") or []
    lines_all: List[str] = []
    league_lines: List[str] = []
    mine: List[str] = []
    my_dst: List[str] = []
    for t in teams:
        name = (
            t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}"
        ).strip()
        rec = ((t.get("record") or {}).get("overall")) or {}
        cells = []
        for e in (t.get("roster") or {}).get("entries") or []:
            p = _espn_player(e)
            pos = ESPN_POS.get(p.get("defaultPositionId"))
            if pos is None:
                continue
            if pos in ("K", "DST"):
                if t.get("id") == my_team_id and pos == "DST":
                    my_dst.append(p.get("fullName", ""))
                continue
            full = p.get("fullName", "")
            lines_all.append(full)
            inj = ESPN_INJ.get(str(p.get("injuryStatus") or ""))
            cells.append(f"{full} ({pos}{',' + inj if inj else ''})")
            if t.get("id") == my_team_id:
                mine.append(full)
        league_lines.append(
            f"{name} [{rec.get('wins', 0)}-{rec.get('losses', 0)}]: " + ", ".join(cells)
        )
    pool = [
        f"# {league} {season} (ESPN) DEF pool — MINE + free agents/waivers with ESPN's own week-{week} projection.",
        f"# Read {day} by scripts/refresh_league_pools.py (kona_player_info filterSlotIds 16).",
    ]
    for n in my_dst:
        if dst_abbr(n):
            pool.append(
                f"MINE|DEF|{dst_abbr(n)}|{_fmt_proj((my_dst_proj or {}).get(n))}"
            )
    for n, proj in fa_dst:
        if dst_abbr(n):
            pool.append(f"DEF|{dst_abbr(n)}|{_fmt_proj(proj)}")
    return {
        f"{league}_{season}_roster.txt": (
            f"# {league} {season} (ESPN, teamId={my_team_id}) — read {day} by scripts/refresh_league_pools.py.\n"
            "# K/DST are not scored by waiver_wire.py.\n" + "\n".join(mine) + "\n"
        ),
        f"{league}_{season}_all_rostered.txt": "\n".join(lines_all) + "\n",
        f"{league}_{season}_league_rosters.txt": "\n".join(league_lines) + "\n",
        f"{league}_{season}_dstk_pool.txt": "\n".join(pool) + "\n",
    }


# ---------------------------------------------------------------------------
# Yahoo
# ---------------------------------------------------------------------------


def yahoo_pool_files(
    my_rows: Sequence[Mapping[str, Any]],
    available: Mapping[str, Sequence[Mapping[str, Any]]],
    league: str,
    week: int,
    team_path: str,
    season: int = 2026,
    today: Optional[dt.date] = None,
) -> Dict[str, str]:
    """Yahoo page rows -> ``{filename: text}``.

    Args:
        my_rows: team-page rows ``{"slot", "name", "status"}`` (slot BN/IR/K/DEF/...).
        available: ``{"QB"|"RB"|"WR"|"TE"|"DEF"|"K": [{"name", "proj"}]}`` from
            Players ``status=A`` pages sorted by week projection (DEF names are
            team nicknames).
        team_path: e.g. ``/f1/658684/10`` (written into the header).
    """
    day = _stamp(today)
    skill = [r for r in my_rows if r.get("slot") not in ("K", "DEF")]
    ir = [r["name"] for r in skill if r.get("slot") == "IR"]
    roster = (
        f"# {league} {season} (Yahoo, {team_path}) — read {day} by scripts/refresh_league_pools.py.\n"
        + (f"# IR slot: {', '.join(ir)}\n" if ir else "")
        + "\n".join(r["name"] for r in skill)
        + "\n"
    )
    avail_lines = [
        f"# {league} {season} (Yahoo) — available players (status=A) sorted by Yahoo week-{week} projection, read {day}."
    ]
    for pos in ("QB", "RB", "WR", "TE"):
        avail_lines += [r["name"] for r in available.get(pos, [])]
    pool = [
        f"# {league} {season} (Yahoo) DEF/K pool — MINE + available (status=A) with Yahoo's own week-{week} projection.",
        f"# Read {day} by scripts/refresh_league_pools.py. MINE projections are not on the team page -> blank.",
    ]
    for r in my_rows:
        if r.get("slot") == "K":
            pool.append(f"MINE|K|{r['name']}|")
        elif r.get("slot") == "DEF" and dst_abbr(r["name"]):
            pool.append(f"MINE|DEF|{dst_abbr(r['name'])}|")
    for r in available.get("DEF", []):
        if dst_abbr(r["name"]):
            pool.append(f"DEF|{dst_abbr(r['name'])}|{_fmt_proj(r.get('proj'))}")
    for r in available.get("K", []):
        pool.append(f"K|{r['name']}|{_fmt_proj(r.get('proj'))}")
    return {
        f"{league}_{season}_roster.txt": roster,
        f"{league}_{season}_available.txt": "\n".join(avail_lines) + "\n",
        f"{league}_{season}_dstk_pool.txt": "\n".join(pool) + "\n",
    }


def first_projection(cells: Iterable[str]) -> Optional[float]:
    """Yahoo player rows: the first ``NN.NN`` cell is the week's projected points."""
    import re

    for c in cells:
        if re.fullmatch(r"\d+\.\d\d", str(c).strip()):
            return float(c)
    return None
