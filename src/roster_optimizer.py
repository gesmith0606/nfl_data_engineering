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
from typing import Any, Dict, List, Optional, Sequence

from src.config import ROSTER_CONFIGS

_FLEX_ELIGIBLE = {"RB", "WR", "TE"}
_SFLEX_ELIGIBLE = {"QB", "RB", "WR", "TE"}
_BASE_SLOTS = ("QB", "RB", "WR", "TE", "K", "DST")

# Sleeper roster-slot name -> set of eligible positions (offense + K/DST only).
# Slots not listed (BN, IR, TAXI, IDP DL/LB/DB, etc.) are skipped.
_SLOT_ELIGIBILITY: Dict[str, set] = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "K": {"K"},
    "DEF": {"DST", "DEF"},
    "DST": {"DST", "DEF"},
    "FLEX": _FLEX_ELIGIBLE,
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "WRRB_WRT": {"RB", "WR", "TE"},
    "SUPER_FLEX": _SFLEX_ELIGIBLE,
    "SUPERFLEX": _SFLEX_ELIGIBLE,
    "QB_WR_RB_TE": _SFLEX_ELIGIBLE,
}
_SKIP_SLOTS = {"BN", "IR", "TAXI"}


def _slots_from_positions(roster_positions):
    """Build an ordered ``[(display_name, eligible_set)]`` from Sleeper roster_positions.

    Restrictive (single-position) slots are ordered before flex slots so greedy
    filling does not let a flex steal a player a base slot needs.
    """
    slots = []
    for raw in roster_positions or []:
        name = str(raw).upper()
        if name in _SKIP_SLOTS:
            continue
        elig = _SLOT_ELIGIBILITY.get(name)
        if not elig:  # unknown / defensive IDP slot — not modeled
            continue
        display = (
            "FLEX"
            if name == "FLEX"
            else ("SFLEX" if name in ("SUPER_FLEX", "SUPERFLEX") else name)
        )
        slots.append((display, elig))
    slots.sort(key=lambda s: len(s[1]))  # fewest-eligible first
    return slots


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


def _slots_from_format(roster_format: str):
    """Build the ordered slot list from a ROSTER_CONFIGS preset."""
    cfg = ROSTER_CONFIGS.get(roster_format, ROSTER_CONFIGS["standard"])
    slots = []
    for slot in _BASE_SLOTS:
        for _ in range(cfg.get(slot, 0)):
            slots.append((slot, {slot} if slot not in ("DST",) else {"DST", "DEF"}))
    for _ in range(cfg.get("FLEX", 0)):
        slots.append(("FLEX", _FLEX_ELIGIBLE))
    for _ in range(cfg.get("SFLEX", 0)):
        slots.append(("SFLEX", _SFLEX_ELIGIBLE))
    slots.sort(key=lambda s: len(s[1]))
    return slots


def optimal_lineup(
    roster: Sequence[Dict[str, Any]],
    roster_format: str = "standard",
    roster_positions=None,
) -> Dict[str, Any]:
    """Compute the best legal starting lineup for a roster.

    Greedy by projected points, filling fewest-eligible slots first. When
    ``roster_positions`` (a raw Sleeper roster_positions list) is given it defines
    the exact starting slots; otherwise the ``roster_format`` preset is used.

    Returns:
        ``{"starters": {slot: [players]}, "bench": [players]}``.
    """
    slots = (
        _slots_from_positions(roster_positions)
        if roster_positions
        else _slots_from_format(roster_format)
    )
    order = sorted(range(len(roster)), key=lambda i: _points(roster[i]), reverse=True)
    used: set = set()
    starters: Dict[str, List[Dict[str, Any]]] = {}

    for slot_name, eligible in slots:
        for i in order:
            if i in used or _pos(roster[i]) not in eligible:
                continue
            starters.setdefault(slot_name, []).append(roster[i])
            used.add(i)
            break

    bench = [roster[i] for i in range(len(roster)) if i not in used]
    return {"starters": starters, "bench": bench}


def _is_dynasty_stash(p: Dict[str, Any]) -> bool:
    """True for players whose value the projection model can't see.

    Rookies / near-rookies and low-sample projections carry dynasty value the
    current-season projection doesn't capture — ranking them by projected
    points alone flagged just-drafted rookies as drops the night they were
    drafted (MANTIS 2026-07-11, RR-1).
    """
    years = p.get("years_exp")
    try:
        if years is not None:
            y = float(years)
            if not math.isnan(y) and y <= 1:
                return True
    except (TypeError, ValueError):
        pass
    val = p.get("is_low_sample_projection")
    try:
        if val is not None and not (isinstance(val, float) and math.isnan(val)):
            return bool(val)
    except TypeError:
        pass
    return False


def drop_candidates(
    roster: Sequence[Dict[str, Any]],
    roster_format: str = "standard",
    top_n: int = 5,
    roster_positions=None,
    protected_names: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Rank the weakest droppable players (who to cut to roster a rookie).

    Only bench players (not in the optimal starting lineup) are droppable. They
    are ranked worst-first by VORP (or points), with a short reason noting
    positional redundancy where relevant. Honors league ``roster_positions`` when
    given (so redundancy reflects the real starting requirements).

    Dynasty guards (RR-1): players named in ``protected_names`` (taxi squad)
    are never suggested, and rookies / low-sample players rank AFTER veterans
    with an explicit caveat — their dynasty value is not in the projection.

    Args:
        roster: Player dicts (projection-mapped).
        roster_format: ROSTER_CONFIGS key when ``roster_positions`` absent.
        top_n: Number of candidates to return.
        roster_positions: League's real Sleeper slot list, when available.
        protected_names: Names to exclude entirely (e.g. taxi squad).

    Returns:
        A list of ``{player, value, reason}`` dicts, weakest first.
    """
    lineup = optimal_lineup(roster, roster_format, roster_positions=roster_positions)
    bench = lineup["bench"]

    if protected_names:
        try:
            from src.sleeper_player_map import normalize_name
        except ImportError:  # pragma: no cover
            from sleeper_player_map import normalize_name

        protected = {normalize_name(str(n)) for n in protected_names}
        protected.discard("")
        bench = [
            p
            for p in bench
            if normalize_name(str(p.get("player_name", ""))) not in protected
        ]

    # How many of each position the lineup actually starts (for redundancy reason).
    started_by_pos: Dict[str, int] = {}
    for slot_players in lineup["starters"].values():
        for p in slot_players:
            started_by_pos[_pos(p)] = started_by_pos.get(_pos(p), 0) + 1
    roster_by_pos: Dict[str, int] = {}
    for p in roster:
        roster_by_pos[_pos(p)] = roster_by_pos.get(_pos(p), 0) + 1

    # Veterans rank first; dynasty stashes only fill remaining slots, flagged.
    ranked = sorted(bench, key=lambda p: (_is_dynasty_stash(p), _drop_value(p)))
    out: List[Dict[str, Any]] = []
    for p in ranked[:top_n]:
        pos = _pos(p)
        depth = roster_by_pos.get(pos, 0)
        starts = started_by_pos.get(pos, 0)
        if pos in ("K", "DST"):
            reason = f"Streamable — swap weekly for best available {pos}"
        elif depth - starts >= 2:
            reason = (
                f"You roster {depth} {pos}s but only {starts} can start"
                f" — lowest projected value of the group"
            )
        else:
            reason = "Lowest projected value on your bench"
        if _is_dynasty_stash(p):
            reason = (
                "CAUTION rookie/low-sample — dynasty value not modeled; "
                "verify before dropping. " + reason
            )
        out.append({"player": p, "value": round(_drop_value(p), 1), "reason": reason})
    return out
