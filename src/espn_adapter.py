"""ESPN draft adapter — live via the draft-room page (v8.3, supersedes Phase 89 stub).

History: the Phase 89 spike (ESPN-01) returned NO-GO for *API* live capture —
ESPN's REST ``mDraftDetail`` view stays empty until the draft completes
(re-verified 2026-08-23: 121 picks on screen, 0 via REST). That verdict still
stands for the API. What changed is the source: the draft app's rendered page
text carries every pick, the clock, and the upcoming-pick strip, and a Chrome
started with ``--remote-debugging-port`` lets us read it locally in ~50 ms
(:mod:`src.espn_draft_page`). The 2026-08-23 mock — where a human-in-the-loop
scrape lost four picks to autopick — is why this ships despite the brittleness
of text parsing.

The adapter conforms to :class:`~src.draft_adapter.DraftAdapter`:

* ``resolve_draft`` finds the draft tab (identifier/season are informational).
* ``load_state`` reads + parses the page into a :class:`DraftState` whose
  ``draft_order`` maps **owner team name -> slot**, so pass your ESPN team name
  as ``my_user_id`` (or give ``--my-slot`` explicitly).
* ``map_picks`` reuses the shared name/position matcher (no ESPN player ids).
* ``enqueue`` (extra, like Sleeper's ``get_keepers``) fills ESPN's Pick Queue so
  an autopick on a timeout follows *our* board, not ESPN's rankings.

``page`` is injectable (anything with ``inner_text()``/``enqueue()``/
``find_tab()``) so the adapter is fully unit-testable offline.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.draft_models import DraftState, PickEvent
from src.espn_draft_page import ChromeDraftPage, parse_draft_page, state_from_page

_LEAGUE_ID_RE = re.compile(r"leagueId=(\d+)")


class EspnAdapter:
    """``DraftAdapter`` for ESPN drafts, read from the draft-room page."""

    platform = "espn"

    #: The API verdict is unchanged; live capture goes through the page instead.
    spike_verdict = "NO-GO (REST) / GO (draft-room page via CDP)"

    def __init__(
        self,
        page: Optional[Any] = None,
        n_teams: int = 12,
        scoring_format: str = "standard",
        roster_format: str = "espn_default",
        draft_type: str = "snake",
        cdp_url: Optional[str] = None,
    ) -> None:
        self.page = page if page is not None else ChromeDraftPage(
            cdp_url or "http://127.0.0.1:9222"
        )
        self.n_teams = int(n_teams)
        self.scoring_format = scoring_format
        self.roster_format = roster_format
        self.draft_type = draft_type
        self._draft_id = "espn"

    def resolve_draft(
        self, identifier: str, season: str, league_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Locate the open draft-room tab; never raises (fail-open ``found=False``)."""
        try:
            tab = self.page.find_tab()
        except Exception as exc:  # noqa: BLE001 — surface reason, don't crash
            return {
                "found": False,
                "candidates": [],
                "platform": self.platform,
                "reason": str(exc),
            }
        url = str(tab.get("url", ""))
        m = _LEAGUE_ID_RE.search(url)
        did = league_id or (m.group(1) if m else "espn")
        self._draft_id = str(did)
        return {
            "found": True,
            "draft_id": self._draft_id,
            "league_id": self._draft_id,
            "status": "drafting",
            "platform": self.platform,
            "candidates": [{"draft_id": self._draft_id, "title": tab.get("title", "")}],
        }

    def load_state(self, draft_id: str) -> DraftState:
        """Read the draft page and normalize it (one CDP round-trip)."""
        text = self.page.inner_text()
        parsed = parse_draft_page(text)
        return state_from_page(
            parsed,
            n_teams=self.n_teams,
            season=str(getattr(self, "season", "")),
            scoring_format=self.scoring_format,
            roster_format=self.roster_format,
            draft_id=draft_id or self._draft_id,
            draft_type=self.draft_type,
        )

    def map_picks(
        self, picks: Sequence[PickEvent], projections_df: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], List[PickEvent]]:
        """Map picks onto projection rows by normalized name + position."""
        from src.sleeper_player_map import map_picks_to_projections

        return map_picks_to_projections(picks, projections_df, player_index={})

    def enqueue(self, names: Sequence[str]) -> List[str]:
        """Fill ESPN's Pick Queue with ``names`` (top first); returns statuses."""
        return list(self.page.enqueue(list(names)))
