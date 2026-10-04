"""Waiver verdicts relative to MY roster, plus keeper protection.

A free agent is only worth a claim if he helps *this* roster: he would start
(beats the weakest starter in a slot he is eligible for) or he upgrades the
bench at his position. Keepers are never drop candidates. (2026-09-29: two
trending RBs were recommended in Feetball although neither beat the bench, and
a keeper TE was suggested as a drop.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

try:
    from src.roster_optimizer import (
        _SFLEX_ELIGIBLE,
        _FLEX_ELIGIBLE,
        optimal_lineup,
    )
    from src.sleeper_player_map import normalize_name
except ImportError:  # pragma: no cover - direct-script import path
    from roster_optimizer import _SFLEX_ELIGIBLE, _FLEX_ELIGIBLE, optimal_lineup
    from sleeper_player_map import normalize_name

STARTS, BENCH_UP, DEPTH, NO_HELP = "STARTS", "BENCH+", "depth", "no help"
#: A one-week edge smaller than this is noise, not a reason to churn the roster.
DEFAULT_MARGIN = 2.0
SKILL = ("QB", "RB", "WR", "TE")


def load_keepers(path: Path) -> Set[str]:
    """Normalized names of OUR keepers (``*`` lines) from a keepers file.

    Format (``data/draft/<league>_2026_keepers.txt``): one player per line,
    ``*`` prefix = ours, ``#`` starts a comment. Missing file -> empty set.
    """
    if not path or not Path(path).is_file():
        return set()
    out: Set[str] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("*"):
            out.add(normalize_name(line[1:].strip()))
    return out


def _eligible(slot: str) -> Set[str]:
    if slot == "FLEX":
        return set(_FLEX_ELIGIBLE)
    if slot == "SFLEX":
        return set(_SFLEX_ELIGIBLE)
    return {slot}


def roster_baseline(
    my_rows: Sequence[Mapping[str, Any]],
    roster_format: Optional[str] = None,
    roster_positions: Optional[Sequence[str]] = None,
    keepers: Iterable[str] = (),
) -> Dict[str, Any]:
    """Best lineup by ``blend`` and the bars a free agent must clear.

    Args:
        my_rows: dicts with ``sid``, ``name``, ``pos``, ``blend`` and optional
            ``ir`` (True = parked on IR: neither a lineup option nor a drop) and
            ``out`` (Out/Doubtful this week: not a bar for "weakest bench" — a
            hurt player's 0.0 is not a reason to call every pickup an upgrade).
        roster_format / roster_positions: lineup shape (Sleeper positions win).
        keepers: normalized names that are never drop candidates.

    Returns:
        ``{"starters": {sid: slot}, "slot_floor": [(eligible_set, blend)],
        "bench_floor": {pos: blend}}`` — bench floors exclude keepers.
    """
    keep = set(keepers)
    pool = [
        {"sid": r["sid"], "position": r["pos"], "projected_points": r["blend"]}
        for r in my_rows
        if r["pos"] in SKILL and not r.get("ir")
    ]
    positions = (
        [p for p in roster_positions if str(p).upper() not in ("K", "DEF", "DST")]
        if roster_positions
        else None
    )
    lu = optimal_lineup(
        pool, roster_format=roster_format or "standard", roster_positions=positions
    )
    starters: Dict[str, str] = {}
    slot_floor = []
    for slot, players in lu["starters"].items():
        for p in players:
            starters[p["sid"]] = slot
            if slot not in ("K", "DST", "DEF"):
                slot_floor.append((_eligible(slot), p["projected_points"]))
    bench_floor: Dict[str, float] = {}
    bench_positions: Set[str] = set()  # healthy bench incl. keepers
    for r in my_rows:
        if r["sid"] in starters or r.get("ir"):
            continue
        bench_positions.add(r["pos"])
        if r.get("out"):
            continue
        if normalize_name(r["name"]) in keep:
            continue
        cur = bench_floor.get(r["pos"])
        bench_floor[r["pos"]] = r["blend"] if cur is None else min(cur, r["blend"])
    return {
        "starters": starters,
        "slot_floor": slot_floor,
        "bench_floor": bench_floor,
        "bench_positions": bench_positions,
    }


def verdict(
    pos: str,
    blend: float,
    baseline: Mapping[str, Any],
    margin: float = DEFAULT_MARGIN,
) -> str:
    """STARTS if he beats a starter in a slot he can fill, BENCH+ if he beats the
    weakest non-keeper bench player at his position, ``depth`` if we carry nobody
    on the bench at that position (a pure add, e.g. a bye-week QB), else
    ``no help`` — including when the only bench player there is a keeper.
    Both bars must be cleared by ``margin`` points."""
    if any(
        pos in elig and blend >= floor + margin
        for elig, floor in baseline["slot_floor"]
    ):
        return STARTS
    floor = baseline["bench_floor"].get(pos)
    if floor is None:
        return NO_HELP if pos in baseline.get("bench_positions", ()) else DEPTH
    return BENCH_UP if blend >= floor + margin else NO_HELP


def drop_order(
    my_rows: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, Any],
    keepers: Iterable[str] = (),
    key: str = "blend",
) -> List[Mapping[str, Any]]:
    """Bench players eligible to drop, weakest first — starters and keepers excluded."""
    keep = set(keepers)
    return sorted(
        (
            r
            for r in my_rows
            if r["sid"] not in baseline["starters"]
            and not r.get("ir")
            and normalize_name(r["name"]) not in keep
        ),
        key=lambda r: r.get(key) or 0,
    )
