"""ESPN draft adapter — honestly gated NO-GO stub (v8.0, Phase 89, ESPN-01/02/03).

ESPN has **no official live draft API**. The Phase 89 feasibility spike (ESPN-01)
returned a **NO-GO** verdict for automated live pick capture:

* The documented REST view ``mDraftDetail`` is **post-draft only** — the
  maintainer of ``cwendt94/espn-api`` confirms ESPN runs the live draft on a
  separate, undocumented realtime backend that the REST surface does not reflect
  until the draft completes.
* The only mechanisms that capture picks live are **brittle browser/DOM scrapers**
  (Selenium + XPATHs, or a Chrome extension), self-described as "VERY brittle" and
  broken by any ESPN UI change — un-shippable for a draft-night tool.
* ``espn_s2`` / ``SWID`` cookies only gate *post-draft* private-league REST reads;
  they do not unlock live picks.

See ``.planning/phases/89-espn-draft-adapter/89-SPIKE-FINDINGS.md`` for full
evidence and citations.

Consequently this module ships a :class:`EspnAdapter` **stub** that conforms to the
:class:`~src.draft_adapter.DraftAdapter` protocol so the platform is registerable
and *visible*, but fails loudly: live capture raises ``NotImplementedError`` with
guidance toward the supported path. ESPN's supported path is the **manual-entry
fallback (D-09)** in :mod:`scripts.draft_live` (``--manual`` / ``--add-pick``),
which drives the same engine from operator-typed picks.

``map_picks`` *is* implemented (it touches no ESPN endpoint) so that, in manual
mode, picks typed for an ESPN draft still map onto projections via the shared
:func:`src.sleeper_player_map.map_picks_to_projections`.

If ESPN ever ships an official live draft API, replace ``resolve_draft`` and
``load_state`` here — the rest of the engine + ``/draft-live`` skill run unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.draft_models import DraftState, PickEvent

_UNSUPPORTED_MSG = (
    "ESPN live capture unsupported — use --manual; see "
    ".planning/phases/89-espn-draft-adapter/89-SPIKE-FINDINGS.md"
)


class EspnAdapter:
    """Gated ``DraftAdapter`` for ESPN — NO-GO stub (Phase 89 spike).

    Conforms to the :class:`~src.draft_adapter.DraftAdapter` protocol so ESPN is a
    registerable platform, but automated live capture is intentionally disabled per
    the ESPN-01 spike verdict. Use the manual-entry fallback (D-09) for ESPN drafts.
    """

    platform = "espn"

    #: Why live capture is disabled (surfaced to callers / docs).
    spike_verdict = "NO-GO"

    def resolve_draft(
        self, identifier: str, season: str, league_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolution is unsupported for ESPN; always reports no draft found.

        Returns a fail-open ``{found: False, ...}`` (never raises) so callers can
        branch to the manual fallback rather than crash.

        Args:
            identifier: A username/handle or draft id (ignored — ESPN unsupported).
            season: Draft season (ignored).
            league_id: Optional league id (ignored).

        Returns:
            ``{"found": False, "candidates": [], "platform": "espn",
            "reason": <unsupported message>}``.
        """
        return {
            "found": False,
            "candidates": [],
            "platform": self.platform,
            "reason": _UNSUPPORTED_MSG,
        }

    def load_state(self, draft_id: str) -> DraftState:
        """Live polling is unsupported for ESPN — always raises.

        Args:
            draft_id: The ESPN draft id (ignored).

        Raises:
            NotImplementedError: Always, with guidance toward ``--manual`` and the
                spike findings. Per the ESPN-01 NO-GO verdict there is no reliable
                live pick source to poll.
        """
        raise NotImplementedError(_UNSUPPORTED_MSG)

    def map_picks(
        self, picks: Sequence[PickEvent], projections_df: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], List[PickEvent]]:
        """Map normalized picks onto projection rows (network-free).

        Implemented even on the NO-GO path because mapping touches no ESPN
        endpoint: in manual mode, operator-typed ESPN picks still resolve to
        projections. Reuses the shared name/position matcher with an empty
        platform index (ESPN exposes no clean live player_id).

        Args:
            picks: Normalized pick events (e.g. from ``build_manual_state``).
            projections_df: Projection rows to match against.

        Returns:
            ``(matched, unmatched)`` — matched projection dicts and any picks that
            could not be resolved (never silently dropped).
        """
        from src.sleeper_player_map import map_picks_to_projections

        return map_picks_to_projections(picks, projections_df, player_index={})
