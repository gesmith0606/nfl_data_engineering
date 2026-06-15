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

from src import sleeper_draft, sleeper_player_map
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
