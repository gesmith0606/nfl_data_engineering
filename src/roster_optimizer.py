"""Fantasy roster optimization — optimal lineup + drop candidates (Phase 90).

Draft-night roster management for keeper leagues: given a roster (kept players +
drafted rookies), compute the best legal starting lineup by ``ROSTER_CONFIGS``
slots and rank the weakest players as drop candidates (who to cut to roster a
rookie). Pure functions over a list of player dicts — trivially testable.

A "player" is a dict with at least ``player_name`` and ``position``; value is read
from ``projected_points`` (or ``projected_season_points``), and ``vorp`` is used as
the primary drop-ranking signal when present.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence

from src.config import ROSTER_CONFIGS

_FLEX_ELIGIBLE = {"RB", "WR", "TE"}
_SFLEX_ELIGIBLE = {"QB", "RB", "WR", "TE"}
_BASE_SLOTS = ("QB", "RB", "WR", "TE", "K", "DST")


def _points(player: Dict[str, Any]) -> float:
    """Projected value of a player (season points preferred), 0 if missing/NaN."""
    for key in ("projected_points", "projected_season_points"):
        val = player.get(key)
        if val is not None:
            try:
                f = float(val)
                if not math.isnan(f):
                    return f
            except (TypeError, ValueError):
                pass
    return 0.0


def _drop_value(player: Dict[str, Any]) -> float:
    """Drop-ranking signal — VORP if present, else projected points."""
    val = player.get("vorp")
    if val is not None:
        try:
            f = float(val)
            if not math.isnan(f):
                return f
        except (TypeError, ValueError):
            pass
    return _points(player)


def _pos(player: Dict[str, Any]) -> str:
    return str(player.get("position", "")).upper()


def optimal_lineup(
    roster: Sequence[Dict[str, Any]], roster_format: str = "standard"
) -> Dict[str, Any]:
    """Compute the best legal starting lineup for a roster.

    Greedy by projected points: fill base position slots, then FLEX (RB/WR/TE),
    then SFLEX (QB/RB/WR/TE) from what remains. Bench is everyone not started.

    Returns:
        ``{"starters": {slot: [players]}, "bench": [players]}``.
    """
    cfg = ROSTER_CONFIGS.get(roster_format, ROSTER_CONFIGS["standard"])
    order = sorted(range(len(roster)), key=lambda i: _points(roster[i]), reverse=True)
    used: set = set()
    starters: Dict[str, List[Dict[str, Any]]] = {}

    for slot in _BASE_SLOTS:
        need = cfg.get(slot, 0)
        if not need:
            continue
        filled: List[Dict[str, Any]] = []
        for i in order:
            if len(filled) >= need:
                break
            if i in used or _pos(roster[i]) != slot:
                continue
            filled.append(roster[i])
            used.add(i)
        if filled:
            starters[slot] = filled

    def _fill_flex(slot_name: str, eligible: set, count: int) -> None:
        for _ in range(count):
            for i in order:
                if i in used or _pos(roster[i]) not in eligible:
                    continue
                starters.setdefault(slot_name, []).append(roster[i])
                used.add(i)
                break

    _fill_flex("FLEX", _FLEX_ELIGIBLE, cfg.get("FLEX", 0))
    _fill_flex("SFLEX", _SFLEX_ELIGIBLE, cfg.get("SFLEX", 0))

    bench = [roster[i] for i in range(len(roster)) if i not in used]
    return {"starters": starters, "bench": bench}


def drop_candidates(
    roster: Sequence[Dict[str, Any]],
    roster_format: str = "standard",
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """Rank the weakest droppable players (who to cut to roster a rookie).

    Only bench players (not in the optimal starting lineup) are droppable. They
    are ranked worst-first by VORP (or points), with a short reason noting
    positional redundancy where relevant.

    Returns a list of ``{player, value, reason}`` dicts, weakest first.
    """
    lineup = optimal_lineup(roster, roster_format)
    bench = lineup["bench"]

    # How many of each position the lineup actually starts (for redundancy reason).
    started_by_pos: Dict[str, int] = {}
    for slot_players in lineup["starters"].values():
        for p in slot_players:
            started_by_pos[_pos(p)] = started_by_pos.get(_pos(p), 0) + 1
    roster_by_pos: Dict[str, int] = {}
    for p in roster:
        roster_by_pos[_pos(p)] = roster_by_pos.get(_pos(p), 0) + 1

    ranked = sorted(bench, key=_drop_value)
    out: List[Dict[str, Any]] = []
    for p in ranked[:top_n]:
        pos = _pos(p)
        depth = roster_by_pos.get(pos, 0)
        starts = started_by_pos.get(pos, 0)
        if pos in ("K", "DST"):
            reason = f"streamable {pos}"
        elif depth - starts >= 2:
            reason = f"redundant — {depth} {pos} rostered, {starts} start"
        else:
            reason = "lowest projected value on bench"
        out.append({"player": p, "value": round(_drop_value(p), 1), "reason": reason})
    return out
