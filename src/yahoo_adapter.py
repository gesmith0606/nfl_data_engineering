"""Yahoo `DraftAdapter` implementation (v8.0 Live Draft Co-Pilot, Phase 88, YH-02).

Mirrors :class:`src.draft_adapter.SleeperAdapter` so the live draft engine
consumes Yahoo through the exact same :class:`~src.draft_adapter.DraftAdapter`
protocol — no engine/skill change required to add Yahoo.

Player-id mapping reuses the generic
:func:`src.sleeper_player_map.map_picks_to_projections`. Yahoo player keys are
opaque (``nfl.p.<id>``), but :func:`src.yahoo_draft.pick_from_yahoo` resolves
name/position/team into each :class:`~src.draft_models.PickEvent`, so we pass
``player_index={}`` and let the generic mapper fall back to that embedded
identity — no Yahoo player registry needed at map time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src import sleeper_player_map, yahoo_draft
from src.draft_models import DraftState, PickEvent
from src.yahoo_oauth import YahooOAuth


class YahooAdapter:
    """`DraftAdapter` over the Phase 88 Yahoo data layer.

    Args:
        oauth: Optional pre-built token manager. When omitted, a
            :class:`~src.yahoo_oauth.YahooOAuth` is constructed lazily from the
            ``YAHOO_CLIENT_ID`` / ``YAHOO_CLIENT_SECRET`` environment variables.
    """

    platform = "yahoo"

    def __init__(self, oauth: Optional[YahooOAuth] = None) -> None:
        self._oauth = oauth

    def _ensure_oauth(self) -> YahooOAuth:
        if self._oauth is None:
            self._oauth = YahooOAuth()
        return self._oauth

    def resolve_draft(
        self, identifier: str, season: str, league_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a Yahoo league draft. See :func:`yahoo_draft.resolve_active_draft`."""
        return yahoo_draft.resolve_active_draft(
            identifier, season, league_id=league_id, oauth=self._ensure_oauth()
        )

    def load_state(self, draft_id: str) -> DraftState:
        """Poll a normalized snapshot. See :func:`yahoo_draft.load_draft_state`.

        Poll conservatively (~once per 5-10s) — Yahoo throttles with HTTP 999.
        """
        return yahoo_draft.load_draft_state(draft_id, oauth=self._ensure_oauth())

    def map_picks(
        self, picks: Sequence[PickEvent], projections_df: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], List[PickEvent]]:
        """Map picks onto projection rows via the generic mapper.

        Passes ``player_index={}`` so the mapper uses each pick's embedded
        name/position/team (populated by :func:`yahoo_draft.pick_from_yahoo`).
        """
        return sleeper_player_map.map_picks_to_projections(
            picks, projections_df, player_index={}
        )
