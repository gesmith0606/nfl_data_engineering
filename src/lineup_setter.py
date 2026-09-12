"""Weekly lineup setter — roster → two projection sources → league scoring → deltas.

Built after the Week 1 2026 Mantis review recommended benching a WR1 on a single
stale source (see ``.planning/LINEUP_TOOL_ENHANCEMENT.md``). Rules encoded here:

* Two independent sources per player: OURS (weekly Gold, or preseason pace when the
  weekly board is thin) and SLEEPER (their weekly projection), both re-scored under
  the league's real ``scoring_settings``.
* A swap is recommended only when BOTH sources agree by at least ``threshold``
  points; agreement below the threshold is a coin flip; disagreement is reported,
  never recommended.
* Locked (kickoff passed), bye, and injury-flagged players are surfaced, not hidden.

Pure functions over dicts/DataFrames; the CLI in ``scripts/set_lineups.py`` does I/O.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from src.league_scoring import score_with_settings
from src.roster_optimizer import _SKIP_SLOTS, _SLOT_ELIGIBILITY, optimal_lineup
from src.sleeper_player_map import normalize_name

ET = ZoneInfo("America/New_York")
# Sleeper team codes that differ from the nflverse schedule codes.
_TEAM_ALIAS = {"LAR": "LA", "OAK": "LV"}
_SLOT_DISPLAY = {
    "SUPER_FLEX": "SFLEX",
    "SUPERFLEX": "SFLEX",
    "WRRB_FLEX": "W/R",
    "REC_FLEX": "W/T",
    "WRRB_WRT": "W/R/T",
}
SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}
MIN_WEEKLY_ROWS = 150  # below this the weekly board is a thin/rookie-only artifact

# Weekly Gold stat columns -> the names score_with_settings understands.
_WEEKLY_RENAME = {
    "proj_passing_yards": "passing_yards",
    "proj_passing_tds": "passing_tds",
    "proj_interceptions": "interceptions",
    "proj_rushing_yards": "rushing_yards",
    "proj_rushing_tds": "rushing_tds",
    "proj_receptions": "receptions",
    "proj_receiving_yards": "receiving_yards",
    "proj_receiving_tds": "receiving_tds",
}
_STAT_COLS = list(_WEEKLY_RENAME.values())
_ID_COLS = ["player_id", "player_name", "position", "recent_team"]
GAMES_PER_SEASON = 17


@dataclass
class PlayerRow:
    """One rostered player with both projection sources and status flags."""

    sleeper_id: str
    name: str
    position: str
    team: str
    ours: Optional[float] = None
    sleeper: Optional[float] = None
    injury_status: Optional[str] = None
    depth_chart_order: Optional[int] = None
    kickoff: Optional[dt.datetime] = None
    locked: bool = False
    bye: bool = False
    slot: Optional[str] = None  # current starting slot, None if benched
    slot_index: int = 999  # position of that slot in roster_positions (render order)
    notes: List[str] = field(default_factory=list)

    @property
    def blend(self) -> float:
        vals = [v for v in (self.ours, self.sleeper) if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    def as_optimizer_dict(self, source: str) -> Dict[str, Any]:
        pts = getattr(self, source)
        return {
            "sleeper_id": self.sleeper_id,
            "player_name": self.name,
            "position": self.position,
            "projected_points": 0.0 if (pts is None or self.bye) else pts,
        }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_sleeper_stats(
    stats: Dict[str, Any], scoring_settings: Dict[str, Any], position: str
) -> float:
    """Score a Sleeper projection stat dict under a league's scoring settings.

    Sleeper's projection keys are the same vocabulary as ``scoring_settings``
    (``pass_yd``, ``rec``, ``rec_fd``, ``fum_lost`` ...), so this is a dot product.
    ``bonus_rec_te`` is a per-reception TE premium and only applies to TEs.
    """
    total = 0.0
    for key, weight in scoring_settings.items():
        if key == "bonus_rec_te":
            continue
        val = stats.get(key)
        if val and weight:
            total += float(val) * float(weight)
    te_bonus = scoring_settings.get("bonus_rec_te")
    if te_bonus and position == "TE":
        total += float(stats.get("rec") or 0) * float(te_bonus)
    return round(total, 2)


def weekly_gold_to_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise a weekly Gold parquet (``proj_*`` columns) to plain stat columns."""
    out = df.rename(columns=_WEEKLY_RENAME)
    keep = [c for c in _ID_COLS + _STAT_COLS if c in out.columns]
    return out[keep].copy()


def preseason_to_weekly(
    df: pd.DataFrame, games: int = GAMES_PER_SEASON
) -> pd.DataFrame:
    """Turn a preseason (season-total) Gold parquet into per-game stat rows."""
    out = df[[c for c in _ID_COLS + _STAT_COLS if c in df.columns]].copy()
    for col in _STAT_COLS:
        if col in out.columns:
            out[col] = out[col].astype(float) / games
    return out


def score_ours(df: pd.DataFrame, scoring_settings: Dict[str, Any]) -> pd.DataFrame:
    """Score normalised stat rows under league settings -> ``projected_points``."""
    if df.empty:
        return df.assign(projected_points=pd.Series(dtype=float))
    scored = score_with_settings(df.assign(projected_points=0.0), scoring_settings)
    return scored


# ---------------------------------------------------------------------------
# Identity: GSIS / name -> Sleeper id
# ---------------------------------------------------------------------------


def build_id_maps(
    registry: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, str], Dict[Tuple[str, str], str]]:
    """Return ``(gsis_id -> sleeper_id, (normalised name, position) -> sleeper_id)``."""
    by_gsis: Dict[str, str] = {}
    by_name: Dict[Tuple[str, str], str] = {}
    for sid, meta in registry.items():
        if not isinstance(meta, dict):
            continue
        gsis = meta.get("gsis_id")
        if gsis:
            by_gsis[str(gsis)] = str(sid)
        name = meta.get("full_name") or " ".join(
            p for p in (meta.get("first_name"), meta.get("last_name")) if p
        )
        pos = str(meta.get("position") or "")
        if name and pos in SKILL_POSITIONS and meta.get("active", True):
            by_name.setdefault((normalize_name(name), pos), str(sid))
    return by_gsis, by_name


def ours_by_sleeper_id(
    scored: pd.DataFrame, registry: Dict[str, Dict[str, Any]]
) -> Dict[str, float]:
    """Map our scored projections onto Sleeper ids (GSIS first, name+position second)."""
    by_gsis, by_name = build_id_maps(registry)
    out: Dict[str, float] = {}
    for row in scored.itertuples(index=False):
        sid = by_gsis.get(str(row.player_id))
        if sid is None:
            sid = by_name.get((normalize_name(str(row.player_name)), str(row.position)))
        if sid is not None and sid not in out:
            out[sid] = float(row.projected_points)
    return out


# ---------------------------------------------------------------------------
# Schedule: kickoff / lock / bye
# ---------------------------------------------------------------------------


def kickoffs_for_week(schedule: pd.DataFrame, week: int) -> Dict[str, dt.datetime]:
    """``team -> kickoff (ET, tz-aware)`` for every team playing in *week*."""
    wk = schedule[schedule["week"] == week]
    out: Dict[str, dt.datetime] = {}
    for row in wk.itertuples(index=False):
        try:
            day = dt.date.fromisoformat(str(row.gameday))
            hh, mm = str(row.gametime or "13:00").split(":")[:2]
            ko = dt.datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=ET)
        except (ValueError, TypeError):
            continue
        out[str(row.home_team)] = ko
        out[str(row.away_team)] = ko
    return out


# ---------------------------------------------------------------------------
# Assemble the roster table
# ---------------------------------------------------------------------------


def current_slots(
    roster_positions: Sequence[str], starters: Sequence[str]
) -> List[Tuple[str, str]]:
    """Zip Sleeper's ``starters`` list onto the non-bench ``roster_positions``.

    Sleeper stores starters in roster_positions order with BN/IR/TAXI excluded;
    an empty slot is the string ``"0"``.
    """
    slots = [p for p in roster_positions if str(p).upper() not in _SKIP_SLOTS]
    return list(zip(slots, list(starters) + ["0"] * (len(slots) - len(starters))))


def build_rows(
    player_ids: Iterable[str],
    starters: Sequence[str],
    roster_positions: Sequence[str],
    registry: Dict[str, Dict[str, Any]],
    ours: Dict[str, float],
    sleeper_proj: Dict[str, Dict[str, Any]],
    scoring_settings: Dict[str, Any],
    kickoffs: Dict[str, dt.datetime],
    now: Optional[dt.datetime] = None,
) -> List[PlayerRow]:
    """Build one :class:`PlayerRow` per rostered player with both sources + flags."""
    now = now or dt.datetime.now(tz=ET)
    slot_of = {
        pid: (slot, i)
        for i, (slot, pid) in enumerate(current_slots(roster_positions, starters))
        if pid != "0"
    }
    rows: List[PlayerRow] = []
    for pid in player_ids:
        pid = str(pid)
        meta = registry.get(pid) or {}
        pos = str(meta.get("position") or "?")
        team = str(meta.get("team") or "FA")
        name = (
            meta.get("full_name")
            or f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
            or pid
        )
        stats = sleeper_proj.get(pid)
        sl = score_sleeper_stats(stats, scoring_settings, pos) if stats else None
        ko = kickoffs.get(_TEAM_ALIAS.get(team, team))
        slot, slot_index = slot_of.get(pid, (None, 999))
        row = PlayerRow(
            sleeper_id=pid,
            name=name,
            position=pos,
            team=team,
            ours=ours.get(pid),
            sleeper=sl,
            injury_status=meta.get("injury_status") or None,
            depth_chart_order=meta.get("depth_chart_order"),
            kickoff=ko,
            locked=bool(ko and now >= ko),
            bye=ko is None and team != "FA",
            slot=slot,
            slot_index=slot_index,
        )
        if row.bye:
            row.notes.append("BYE")
        if row.locked:
            row.notes.append("LOCKED")
        if row.injury_status:
            row.notes.append(str(row.injury_status))
        if row.ours is None:
            row.notes.append("no model proj")
        if row.sleeper is None:
            row.notes.append("no Sleeper proj")
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Deltas
# ---------------------------------------------------------------------------


@dataclass
class Delta:
    verdict: str  # SWAP | COIN FLIP | SPLIT
    slot: str
    out_player: PlayerRow
    in_player: PlayerRow
    margin_ours: Optional[float]
    margin_sleeper: Optional[float]

    def line(self) -> str:
        m_o = "n/a" if self.margin_ours is None else f"{self.margin_ours:+.1f}"
        m_s = "n/a" if self.margin_sleeper is None else f"{self.margin_sleeper:+.1f}"
        return (
            f"{self.verdict:9s} {self.slot:6s} start {self.in_player.name} "
            f"over {self.out_player.name}  (ours {m_o}, Sleeper {m_s})"
        )


def _margin(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round(a - b, 2)


def _verdict(
    m_o: Optional[float], m_s: Optional[float], threshold: float
) -> Optional[str]:
    """SWAP: both clear the threshold. COIN FLIP: both positive, one thin.
    SPLIT: one source clears the threshold while the other is missing or leans
    the other way. None: nothing worth saying."""
    if m_o is not None and m_s is not None:
        if m_o >= threshold and m_s >= threshold:
            return "SWAP"
        if m_o > 0 and m_s > 0:
            return "COIN FLIP"
        if max(m_o, m_s) >= threshold and min(m_o, m_s) <= 0:
            return "SPLIT"
        return None
    known = m_o if m_o is not None else m_s
    return "SPLIT" if known is not None and known >= threshold else None


_RANK = {"SWAP": 2, "COIN FLIP": 1, "SPLIT": 0}


def lineup_deltas(rows: List[PlayerRow], threshold: float = 3.0) -> List[Delta]:
    """Pairwise deltas vs the lineup currently set.

    For each current starter, every eligible bench player is a candidate; see
    :func:`_verdict` for the SWAP / COIN FLIP / SPLIT rule. Candidates are taken
    strongest-first (verdict, then the worse of the two margins) and each player
    appears in at most one delta. Locked and bye bench players are never proposed;
    a locked starter cannot be swapped out.
    """
    starters = [r for r in rows if r.slot and not r.locked]
    bench = [r for r in rows if not r.slot and not r.locked and not r.bye]
    candidates = []
    for s in starters:
        elig = _SLOT_ELIGIBILITY.get(s.slot.upper(), set())
        for b in bench:
            if b.position not in elig:
                continue
            m_o, m_s = _margin(b.ours, s.ours), _margin(b.sleeper, s.sleeper)
            verdict = _verdict(m_o, m_s, threshold)
            if verdict:
                worst = min(m for m in (m_o, m_s) if m is not None)
                candidates.append((_RANK[verdict], worst, s, b, m_o, m_s, verdict))
    used: set = set()
    deltas: List[Delta] = []
    for _, _, s, b, m_o, m_s, verdict in sorted(
        candidates, key=lambda c: (c[0], c[1]), reverse=True
    ):
        if b.sleeper_id in used or s.sleeper_id in used:
            continue
        used.update({b.sleeper_id, s.sleeper_id})
        deltas.append(Delta(verdict, s.slot, s, b, m_o, m_s))
    return deltas


def optimal_by_source(
    rows: List[PlayerRow], roster_positions: Sequence[str], source: str
) -> set:
    """Set of sleeper_ids the greedy optimizer would start under one source."""
    pool = [r.as_optimizer_dict(source) for r in rows if not r.locked or r.slot]
    lu = optimal_lineup(pool, roster_positions=list(roster_positions))
    return {p["sleeper_id"] for ps in lu["starters"].values() for p in ps}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt(v: Optional[float]) -> str:
    return "  -  " if v is None else f"{v:5.1f}"


def render(
    rows: List[PlayerRow], deltas: List[Delta], header: str, ours_label: str
) -> str:
    """Plain-text report: current lineup, bench, then the deltas."""
    lines = [
        header,
        "",
        f"  {'SLOT':7s}{'PLAYER':24s}{'POS':4s}{'TM':4s} {'OURS':>5s} {'SLPR':>5s} {'BLEND':>5s}  NOTES",
    ]
    starters = sorted((r for r in rows if r.slot), key=lambda r: r.slot_index)
    bench = sorted((r for r in rows if not r.slot), key=lambda r: r.blend, reverse=True)
    for r in starters + bench:
        slot = _SLOT_DISPLAY.get(r.slot or "", r.slot) or "BN"
        lines.append(
            f"  {slot:7s}{r.name[:23]:24s}{r.position:4s}{r.team:4s} {_fmt(r.ours)} {_fmt(r.sleeper)} {r.blend:5.1f}  {', '.join(r.notes)}"
        )
    tot_o = sum(r.ours or 0 for r in starters)
    tot_s = sum(r.sleeper or 0 for r in starters)
    lines += [
        "",
        f"  Starters total: ours {tot_o:.1f} / Sleeper {tot_s:.1f}   (OURS = {ours_label})",
        "",
    ]
    if deltas:
        lines.append(
            "DELTAS vs the lineup currently set (rule: SWAP only when BOTH sources agree by the threshold):"
        )
        lines += ["  " + d.line() for d in deltas]
    else:
        lines.append("No changes: no bench player beats a starter on both sources.")
    return "\n".join(lines)
