"""Explicit (custom) draft pick order — traded picks + keeper slots.

Plain snake drafts derive "who is on the clock at pick N" arithmetically. A
commish-customized order (Feetball 2026: The Oracle picks twice in rounds 2-4,
not at all in 10/14/17, and 25 keeper slots consume pick numbers without a live
pick) breaks that arithmetic, so this module turns a small text file into the
:class:`src.draft_models.PickSlot` tuple that :class:`src.draft_models.DraftState`
carries and :class:`src.live_draft_engine.LiveDraftEngine` reads instead.

File format (``data/draft/feetball_2026_pick_order.txt``) — one round per line,
picks in clock order, ``(K)``/``(K=name)`` marks a keeper slot, ``#`` comments::

    R1: Amon Ra, Dude, Nico$uave, One Giant Mess, Murtaugh, Oracle, ...
    R4: Crazy Eddie, Billiever, Bird Gang, Oracle, Oracle, Murtaugh(K), ...

A team's ``draft_slot`` is its position in the ROUND 1 line (Oracle = 6).
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from src.draft_models import DraftState, PickEvent, PickSlot

_ROUND_RE = re.compile(r"^R(\d+)\s*:\s*(.*)$", re.IGNORECASE)
_ENTRY_RE = re.compile(r"^(?P<label>.*?)\s*(?:\(\s*K[^)]*\))?\s*$", re.IGNORECASE)
_KEEPER_RE = re.compile(r"\(\s*K[^)]*\)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class PickOrder:
    """A parsed pick order: every slot plus the round-1 team labels."""

    slots: Tuple[PickSlot, ...]
    labels: Dict[int, str]  # draft_slot -> team label as written in round 1

    @property
    def n_teams(self) -> int:
        return len(self.labels)

    @property
    def rounds(self) -> int:
        return max((s.round for s in self.slots), default=0)

    @property
    def keeper_slots(self) -> Tuple[PickSlot, ...]:
        return tuple(s for s in self.slots if s.is_keeper)

    @property
    def live_slots(self) -> Tuple[PickSlot, ...]:
        return tuple(s for s in self.slots if not s.is_keeper)

    def live_picks_for(self, draft_slot: int) -> Tuple[int, ...]:
        """Overall pick numbers where ``draft_slot`` is live on the clock."""
        return tuple(s.pick_no for s in self.live_slots if s.draft_slot == draft_slot)


def _norm(label: str) -> str:
    return label.replace("*", "").strip().casefold()


def parse_pick_order(lines: Iterable[str]) -> PickOrder:
    """Parse ``R<n>: team, team(K), ...`` lines into a validated :class:`PickOrder`.

    Raises ``ValueError`` on a malformed round line, a round with the wrong
    number of entries, a team label that never appears in round 1, or rounds
    that are not numbered 1..R contiguously.
    """
    rounds: Dict[int, List[Tuple[str, bool]]] = {}
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _ROUND_RE.match(line)
        if not m:
            raise ValueError(f"pick order: expected 'R<n>: ...', got {raw.strip()!r}")
        rnd = int(m.group(1))
        if rnd in rounds:
            raise ValueError(f"pick order: round {rnd} listed twice")
        entries = []
        for part in m.group(2).split(","):
            part = part.strip()
            if not part:
                continue
            is_keeper = bool(_KEEPER_RE.search(part))
            raw_label = _ENTRY_RE.match(part).group("label").replace("*", "").strip()
            if not raw_label:
                raise ValueError(f"pick order: empty team label in round {rnd}")
            entries.append((_norm(raw_label), raw_label, is_keeper))
        rounds[rnd] = entries

    if not rounds:
        raise ValueError("pick order: no rounds found")
    expected = list(range(1, max(rounds) + 1))
    if sorted(rounds) != expected:
        raise ValueError(
            f"pick order: rounds must be 1..{max(rounds)} (got {sorted(rounds)})"
        )

    r1 = [label for label, _, _ in rounds[1]]
    if len(set(r1)) != len(r1):
        raise ValueError("pick order: round 1 must list each team exactly once")
    slot_of = {label: i + 1 for i, label in enumerate(r1)}
    labels = {i + 1: raw for i, (_, raw, _) in enumerate(rounds[1])}
    n = len(r1)

    slots: List[PickSlot] = []
    for rnd in expected:
        entries = rounds[rnd]
        if len(entries) != n:
            raise ValueError(
                f"pick order: round {rnd} has {len(entries)} entries, expected {n}"
            )
        for idx, (label, _, is_keeper) in enumerate(entries):
            if label not in slot_of:
                raise ValueError(
                    f"pick order: round {rnd} team {label!r} is not in round 1"
                )
            slots.append(
                PickSlot(
                    pick_no=(rnd - 1) * n + idx + 1,
                    round=rnd,
                    draft_slot=slot_of[label],
                    is_keeper=is_keeper,
                )
            )
    return PickOrder(slots=tuple(slots), labels=labels)


def load_pick_order(path: str) -> PickOrder:
    """Read and parse a pick-order text file."""
    with open(path, encoding="utf-8") as fh:
        return parse_pick_order(fh)


def apply_pick_order(state: DraftState, order: PickOrder) -> DraftState:
    """Return ``state`` carrying ``order`` with every pick's round/slot re-derived.

    Platforms number picks the same way the order does (every slot counts), but
    a platform-reported ``draft_slot`` may be a team id rather than the round-1
    position the order uses — so ownership is re-read from the order by
    ``pick_no``. Picks beyond the order are left untouched.
    """
    by_no = {s.pick_no: s for s in order.slots}

    def _fix(p: PickEvent) -> PickEvent:
        s = by_no.get(p.pick_no)
        if s is None:
            return p
        return dataclasses.replace(p, round=s.round, draft_slot=s.draft_slot)

    return dataclasses.replace(
        state,
        n_teams=order.n_teams,
        rounds=order.rounds,
        pick_order=order.slots,
        picks=tuple(_fix(p) for p in state.picks),
    )
