"""Platform-neutral draft model types (v8.0, Phase 86).

These are the normalized types every platform adapter produces and the live
engine consumes. They contain NO platform-specific parsing — Sleeper/Yahoo/ESPN
construction logic lives in each adapter's module (e.g. :mod:`src.sleeper_draft`).
Keeping them here is what lets the engine stay platform-agnostic (D-08).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class PickEvent:
    """A single drafted player, normalized across platforms."""

    pick_no: int
    round: int
    draft_slot: int
    roster_id: Optional[int]
    picked_by: str
    sleeper_player_id: (
        str  # source platform's player id (named for the reference adapter)
    )
    first_name: str
    last_name: str
    position: str
    team: str
    is_keeper: bool

    @property
    def full_name(self) -> str:
        """``"First Last"`` with surrounding whitespace collapsed."""
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True)
class DraftState:
    """A normalized snapshot of a draft on any platform."""

    draft_id: str
    status: str
    draft_type: str
    season: str
    n_teams: int
    rounds: int
    scoring_format: str
    roster_format: str
    draft_order: Dict[str, int]
    slot_to_roster_id: Dict[str, int]
    picks: Tuple[PickEvent, ...] = field(default_factory=tuple)
    traded_picks: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def is_active(self) -> bool:
        """True while the draft is in progress (``drafting`` or ``paused``)."""
        return self.status in {"drafting", "paused"}

    @property
    def last_pick_no(self) -> int:
        """Highest ``pick_no`` seen so far (0 if no picks)."""
        return max((p.pick_no for p in self.picks), default=0)
