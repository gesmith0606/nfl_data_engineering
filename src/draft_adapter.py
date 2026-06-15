"""Platform-agnostic draft adapter interface (v8.0, Phase 86, ENG-05 / D-08).

The live draft engine consumes ONLY the :class:`DraftAdapter` protocol — it never
imports Sleeper/Yahoo/ESPN specifics directly. Each platform supplies its own
auth, resolution, polling, and player-id mapping behind this interface, so adding
Yahoo (Phase 88) or ESPN (Phase 89) requires no engine change.

`SleeperAdapter` is the reference implementation, wrapping Phase 85's
:mod:`src.sleeper_draft` and :mod:`src.sleeper_player_map`.
"""

from __future__ import annotations

from typing import (
    Any,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)

import pandas as pd

from src import sleeper_draft, sleeper_http, sleeper_player_map
from src.draft_models import DraftState, PickEvent


@runtime_checkable
class DraftAdapter(Protocol):
    """Contract every platform adapter must satisfy."""

    platform: str

    def resolve_draft(
        self, identifier: str, season: str, league_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a draft from a user identifier (username/handle) or draft id.

        Returns ``{found, draft_id, league_id, status, candidates}``.
        """
        ...

    def load_state(self, draft_id: str) -> DraftState:
        """Poll a full normalized snapshot of the draft."""
        ...

    def map_picks(
        self, picks: Sequence[PickEvent], projections_df: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], List[PickEvent]]:
        """Map picks onto projection rows; return ``(matched, unmatched)``."""
        ...


class SleeperAdapter:
    """Reference `DraftAdapter` over the Phase 85 Sleeper data layer."""

    platform = "sleeper"

    def __init__(self) -> None:
        self._player_index: Optional[Dict[str, Dict[str, str]]] = None

    def resolve_draft(
        self, identifier: str, season: str, league_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return sleeper_draft.resolve_active_draft(
            identifier, season, league_id=league_id
        )

    def load_state(self, draft_id: str) -> DraftState:
        return sleeper_draft.load_draft_state(draft_id)

    def _ensure_index(self) -> Dict[str, Dict[str, str]]:
        if self._player_index is None:
            registry = sleeper_player_map.load_sleeper_players()
            self._player_index = sleeper_player_map.build_player_index(registry)
        return self._player_index

    def map_picks(
        self, picks: Sequence[PickEvent], projections_df: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], List[PickEvent]]:
        return sleeper_player_map.map_picks_to_projections(
            picks, projections_df, player_index=self._ensure_index()
        )

    # Keeper support (Phase 90) — not part of the DraftAdapter Protocol; the engine
    # calls it via hasattr() so non-keeper platforms need not implement it.
    def get_keepers(
        self, league_id: str, my_user_id: Optional[str] = None
    ) -> Dict[str, List[PickEvent]]:
        """Return already-rostered (kept) players for a keeper-league draft.

        Reads every team's league roster and represents each kept player as a
        ``PickEvent`` (``is_keeper=True``) so it flows through the same mapping
        path as live picks. ``mine`` is the subset on the user's roster.

        Returns ``{"all": [...], "mine": [...]}``; empty lists on any error.
        """
        rosters = sleeper_http.get_league_rosters(league_id)
        index = self._ensure_index()
        all_kept: List[PickEvent] = []
        mine: List[PickEvent] = []
        for roster in rosters:
            if not isinstance(roster, dict):
                continue
            owner = str(roster.get("owner_id") or "")
            roster_id = roster.get("roster_id")
            for pid in roster.get("players") or []:
                pe = self._keeper_pick(str(pid), index, roster_id, owner)
                all_kept.append(pe)
                if my_user_id and owner == str(my_user_id):
                    mine.append(pe)
        return {"all": all_kept, "mine": mine}

    @staticmethod
    def _keeper_pick(
        player_id: str, index: Dict[str, Dict[str, str]], roster_id, owner: str
    ) -> PickEvent:
        rec = index.get(player_id, {})
        first, _, last = str(rec.get("full_name", "")).partition(" ")
        return PickEvent(
            pick_no=0,
            round=0,
            draft_slot=0,
            roster_id=None if roster_id is None else int(roster_id),
            picked_by=owner,
            sleeper_player_id=player_id,
            first_name=first,
            last_name=last,
            position=str(rec.get("position", "")).upper(),
            team=str(rec.get("team", "")).upper(),
            is_keeper=True,
        )
