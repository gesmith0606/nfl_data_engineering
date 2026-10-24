"""Turn a recommended lineup into ESPN lineup moves.

``set_lineups.py`` plans in our own vocabulary — Sleeper player ids and slot
labels like ``FLEX`` — while ESPN wants numeric ``playerId``s and
``lineupSlotId``s. This module is the join, and its posture is **refuse rather
than guess**: an unresolved name aborts the whole plan instead of silently
leaving a starter on the bench, which is the failure mode that would cost
points without anyone noticing.

Matching is restricted to the 16 players already on the ESPN roster, so this is
a small closed-set problem, not general name resolution.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:  # scripts put the repo root on sys.path and import `src.espn_lineup`
    from src.espn_league import LINEUP_SLOT_MAP
    from src.league_pools import dst_abbr
except ImportError:  # tests put `src/` itself on sys.path
    from espn_league import LINEUP_SLOT_MAP
    from league_pools import dst_abbr

#: Slot label -> ESPN lineupSlotId, inverted from the read-side map.
SLOT_LABEL_TO_ID: Dict[str, int] = {v: k for k, v in LINEUP_SLOT_MAP.items()}
SLOT_LABEL_TO_ID.setdefault("DEF", SLOT_LABEL_TO_ID["DST"])
SLOT_LABEL_TO_ID.setdefault("D/ST", SLOT_LABEL_TO_ID["DST"])
BENCH_SLOT = SLOT_LABEL_TO_ID["BN"]

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name: str) -> str:
    """``"James Cook III"`` and ``"James Cook"`` collapse to the same key.

    ESPN spells out generational suffixes that our registry often omits, and
    punctuation differs between the two ("A.J." vs "AJ"). Lowercase, drop
    anything that is not a letter or space, then drop a trailing suffix.
    """
    cleaned = re.sub(r"[^a-z ]", "", str(name).lower()).split()
    while cleaned and cleaned[-1] in _SUFFIXES:
        cleaned.pop()
    return " ".join(cleaned)


def espn_roster_index(payload: Mapping[str, Any], team_id: int) -> Dict[str, int]:
    """``{normalized name or team abbr: playerId}`` for one ESPN team.

    Defences (``defaultPositionId`` 16) are keyed by team abbreviation, because
    ESPN calls them "Titans D/ST" while our board calls them "TEN".
    """
    team = next(
        (t for t in (payload.get("teams") or []) if t.get("id") == team_id), None
    )
    entries = ((team or {}).get("roster") or {}).get("entries") or []
    index: Dict[str, int] = {}
    for entry in entries:
        player = (entry.get("playerPoolEntry") or {}).get("player") or {}
        pid = (entry.get("playerPoolEntry") or {}).get("id") or entry.get("playerId")
        name = player.get("fullName") or ""
        if pid is None or not name:
            continue
        if player.get("defaultPositionId") == 16:
            abbr = dst_abbr(name)
            if abbr:
                index[abbr.upper()] = int(pid)
        index[normalize_name(name)] = int(pid)
    return index


def espn_names_by_id(payload: Mapping[str, Any], team_id: int) -> Dict[int, str]:
    """``{playerId: display name}`` for one ESPN team, for readable dry runs."""
    team = next(
        (t for t in (payload.get("teams") or []) if t.get("id") == team_id), None
    )
    entries = ((team or {}).get("roster") or {}).get("entries") or []
    out: Dict[int, str] = {}
    for entry in entries:
        pool = entry.get("playerPoolEntry") or {}
        pid = pool.get("id") or entry.get("playerId")
        name = (pool.get("player") or {}).get("fullName")
        if pid is not None and name:
            out[int(pid)] = str(name)
    return out


def resolve_players(
    names: Sequence[str], index: Mapping[str, int]
) -> Tuple[Dict[str, int], List[str]]:
    """Map our names onto ESPN ids. Returns ``(resolved, unresolved)``.

    A name that looks like a team abbreviation (``"TEN"``) is tried as a
    defence first, since normalizing it would just yield ``"ten"``.
    """
    resolved: Dict[str, int] = {}
    unresolved: List[str] = []
    for name in names:
        raw = str(name).strip()
        pid = index.get(raw.upper()) if len(raw) <= 4 else None
        if pid is None:
            pid = index.get(normalize_name(raw))
        if pid is None:
            unresolved.append(raw)
        else:
            resolved[raw] = pid
    return resolved, unresolved


def plan_moves(
    desired: Sequence[Tuple[str, str]],
    resolved: Mapping[str, int],
    current_slots: Mapping[int, int],
) -> Tuple[List[Tuple[int, int, int]], List[str]]:
    """Diff a recommended lineup against ESPN's live slots.

    Args:
        desired: ``(slot_label, our_name)`` pairs for the STARTERS, in roster
            order. Everyone on the roster and not in this list is bench-bound.
        resolved: ``our_name -> espn playerId`` from :func:`resolve_players`.
        current_slots: live ``playerId -> lineupSlotId``.

    Returns:
        ``(moves, problems)`` where moves are ``(playerId, from, to)`` triples
        for players whose slot must change, and problems describe anything that
        makes the plan unsafe to post. A non-empty ``problems`` means do not
        write: a partially-applied lineup benches a starter without starting
        his replacement.
    """
    moves: List[Tuple[int, int, int]] = []
    problems: List[str] = []
    wanted: Dict[int, int] = {}

    for slot_label, name in desired:
        label = str(slot_label).upper()
        slot_id = SLOT_LABEL_TO_ID.get(label)
        if slot_id is None:
            problems.append(f"unknown slot label {slot_label!r}")
            continue
        pid = resolved.get(str(name).strip())
        if pid is None:
            problems.append(f"no ESPN player for {name!r}")
            continue
        if pid in wanted:
            problems.append(f"{name!r} is allocated to two slots")
            continue
        wanted[pid] = slot_id

    for pid, slot_id in wanted.items():
        if pid not in current_slots:
            problems.append(f"player {pid} is not on the ESPN roster")
            continue
        if current_slots[pid] != slot_id:
            moves.append((pid, current_slots[pid], slot_id))

    # Anyone currently starting who is not in the plan has to sit, or ESPN will
    # reject the transaction for over-filling a slot.
    #
    # ONLY for slots the plan actually fills. Our registry carries no D/ST or K,
    # so those slots never appear in `desired` -- and benching their incumbents
    # would empty the slot for the week. A lineup tool that quietly drops your
    # defence is worse than one that does nothing.
    covered = set(wanted.values())
    for pid, slot_id in current_slots.items():
        if slot_id in (BENCH_SLOT, SLOT_LABEL_TO_ID["IR"]):
            continue
        if slot_id not in covered:
            continue
        if pid not in wanted:
            moves.append((pid, slot_id, BENCH_SLOT))

    return moves, problems


def describe_moves(
    moves: Sequence[Tuple[int, int, int]], names_by_id: Optional[Mapping[int, str]] = None
) -> List[str]:
    """Human-readable lines for the dry run, e.g. ``"Derrick Henry  RB -> BN"``."""
    names_by_id = names_by_id or {}
    out = []
    for pid, a, b in moves:
        who = names_by_id.get(pid, str(pid))
        out.append(
            f"{who:<26} {LINEUP_SLOT_MAP.get(a, a):>4} -> {LINEUP_SLOT_MAP.get(b, b)}"
        )
    return out
