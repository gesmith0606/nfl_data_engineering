"""Normalized Sleeper draft data layer (v8.0 Live Draft Co-Pilot, Phase 85).

This module turns raw Sleeper draft JSON (fetched via :mod:`src.sleeper_http`)
into typed, normalized state the live-draft engine (Phase 86) consumes:

* :class:`PickEvent` — one draft pick, with the Sleeper player_id plus the
  metadata identity (name/pos/team) so downstream mapping has a fallback.
* :class:`DraftState` — a full draft snapshot: status, type, league settings
  mapped onto our :data:`SCORING_CONFIGS` / :data:`ROSTER_CONFIGS` keys, draft
  order, and the ordered pick list.

Network access is confined to :func:`load_draft_state` and
:func:`resolve_active_draft`; the model constructors operate purely on
already-fetched dicts so they are trivially unit-testable offline.

Everything honours the project-wide D-06 fail-open contract — bad/missing input
yields empty defaults, never an exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src import sleeper_http
from src.config import ROSTER_CONFIGS, SCORING_CONFIGS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce ``value`` to int, returning ``default`` on any failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _scoring_format_from_draft(draft: Dict[str, Any]) -> str:
    """Map a Sleeper draft's scoring onto a SCORING_CONFIGS key.

    Tries, in order: the draft ``metadata.scoring_type`` label, then the league
    ``settings`` reception value, then the project default ``half_ppr``.
    """
    meta = draft.get("metadata") or {}
    label = str(meta.get("scoring_type", "")).lower()
    if "half" in label:
        return "half_ppr"
    if "ppr" in label:  # plain "ppr" / "dynasty_ppr" etc. (half already caught)
        return "ppr"
    if "std" in label or "standard" in label:
        return "standard"

    settings = draft.get("settings") or {}
    rec = settings.get("rec")
    if rec is not None:
        try:
            rec_val = float(rec)
        except (TypeError, ValueError):
            rec_val = None
        if rec_val is not None:
            if rec_val >= 1.0:
                return "ppr"
            if rec_val <= 0.0:
                return "standard"
            return "half_ppr"

    return "half_ppr"


def _roster_format_from_draft(draft: Dict[str, Any]) -> str:
    """Best-effort map of a Sleeper draft's roster slots onto a ROSTER_CONFIGS key."""
    settings = draft.get("settings") or {}
    if _safe_int(settings.get("slots_super_flex")) > 0:
        return "superflex"
    if _safe_int(settings.get("slots_qb")) >= 2:
        return "2qb"
    return "standard"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PickEvent:
    """A single drafted player, normalized from a Sleeper pick object."""

    pick_no: int
    round: int
    draft_slot: int
    roster_id: Optional[int]
    picked_by: str
    sleeper_player_id: str
    first_name: str
    last_name: str
    position: str
    team: str
    is_keeper: bool

    @property
    def full_name(self) -> str:
        """``"First Last"`` with surrounding whitespace collapsed."""
        return f"{self.first_name} {self.last_name}".strip()

    @classmethod
    def from_sleeper_pick(cls, raw: Dict[str, Any]) -> "PickEvent":
        """Build a PickEvent from a raw Sleeper pick dict, defensively.

        Missing keys default to ``""`` / ``0`` / ``False`` — never raises, so a
        malformed or empty pick yields a zero-value PickEvent rather than an
        error.
        """
        raw = raw if isinstance(raw, dict) else {}
        meta = raw.get("metadata") or {}
        roster_id_raw = raw.get("roster_id")
        return cls(
            pick_no=_safe_int(raw.get("pick_no")),
            round=_safe_int(raw.get("round")),
            draft_slot=_safe_int(raw.get("draft_slot")),
            roster_id=None if roster_id_raw is None else _safe_int(roster_id_raw),
            picked_by=str(raw.get("picked_by") or ""),
            sleeper_player_id=str(raw.get("player_id") or ""),
            first_name=str(meta.get("first_name") or ""),
            last_name=str(meta.get("last_name") or ""),
            position=str(meta.get("position") or "").upper(),
            team=str(meta.get("team") or "").upper(),
            is_keeper=bool(raw.get("is_keeper") or False),
        )


@dataclass(frozen=True)
class DraftState:
    """A normalized snapshot of a Sleeper draft."""

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

    @classmethod
    def from_sleeper(
        cls,
        draft: Dict[str, Any],
        picks: Optional[List[Dict[str, Any]]] = None,
        traded: Optional[List[Dict[str, Any]]] = None,
    ) -> "DraftState":
        """Assemble a DraftState from already-fetched Sleeper dicts/lists.

        Performs no network I/O. Maps league settings onto SCORING_CONFIGS /
        ROSTER_CONFIGS keys and normalizes every pick via
        :meth:`PickEvent.from_sleeper_pick`.
        """
        draft = draft if isinstance(draft, dict) else {}
        picks = picks if isinstance(picks, list) else []
        traded = traded if isinstance(traded, list) else []
        settings = draft.get("settings") or {}

        scoring = _scoring_format_from_draft(draft)
        roster = _roster_format_from_draft(draft)
        # Defensive: guarantee the mapped keys exist in our config dicts.
        if scoring not in SCORING_CONFIGS:
            scoring = "half_ppr"
        if roster not in ROSTER_CONFIGS:
            roster = "standard"

        pick_events = tuple(
            sorted(
                (PickEvent.from_sleeper_pick(p) for p in picks),
                key=lambda pe: pe.pick_no,
            )
        )

        return cls(
            draft_id=str(draft.get("draft_id") or ""),
            status=str(draft.get("status") or ""),
            draft_type=str(draft.get("type") or ""),
            season=str(draft.get("season") or ""),
            n_teams=_safe_int(settings.get("teams")),
            rounds=_safe_int(settings.get("rounds")),
            scoring_format=scoring,
            roster_format=roster,
            draft_order=dict(draft.get("draft_order") or {}),
            slot_to_roster_id=dict(draft.get("slot_to_roster_id") or {}),
            picks=pick_events,
            traded_picks=tuple(traded),
        )


# ---------------------------------------------------------------------------
# Network-touching assembly + resolution
# ---------------------------------------------------------------------------


def load_draft_state(draft_id: str) -> DraftState:
    """Fetch a draft + its picks + traded picks and assemble a DraftState.

    The single place in this module that performs network I/O. Fail-open: an
    unreachable Sleeper yields a DraftState with empty picks rather than raising.
    """
    draft = sleeper_http.get_draft(draft_id)
    picks = sleeper_http.get_draft_picks(draft_id)
    traded = sleeper_http.get_traded_picks(draft_id)
    return DraftState.from_sleeper(draft, picks, traded)


def _draft_recency_key(draft: Dict[str, Any]) -> int:
    """Sort key for "most recent" draft selection (higher = newer)."""
    for key in ("last_picked", "start_time", "created"):
        val = draft.get(key)
        if val:
            return _safe_int(val)
    return 0


def resolve_active_draft(
    username: str,
    season: str,
    league_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve a user's active (or most-recent) NFL draft from a username.

    No manual draft_id lookup required. Resolution path:
    ``username -> user_id -> user's drafts for the season`` (optionally filtered
    to ``league_id``). Selection rule: prefer a draft with status in
    ``{"drafting", "paused"}``; otherwise the most-recent draft.

    Args:
        username: Sleeper display username (or user_id).
        season: Four-digit season string.
        league_id: If provided, restrict candidates to this league.

    Returns:
        ``{found, draft_id, league_id, status, candidates}`` where ``candidates``
        lists every considered draft (``{draft_id, league_id, status, name}``).
        ``found`` is False with empty ``candidates`` when nothing resolves.
        Never raises (D-06 fail-open).
    """
    empty = {
        "found": False,
        "draft_id": "",
        "league_id": "",
        "status": "",
        "candidates": [],
    }

    user = sleeper_http.get_user(username)
    user_id = str(user.get("user_id") or "") if isinstance(user, dict) else ""
    if not user_id:
        return dict(empty)

    drafts = sleeper_http.get_user_drafts(user_id, season)
    if league_id:
        drafts = [d for d in drafts if str(d.get("league_id") or "") == str(league_id)]
    if not drafts:
        return dict(empty)

    candidates = [
        {
            "draft_id": str(d.get("draft_id") or ""),
            "league_id": str(d.get("league_id") or ""),
            "status": str(d.get("status") or ""),
            "name": str((d.get("metadata") or {}).get("name") or d.get("type") or ""),
        }
        for d in drafts
    ]

    active = [d for d in drafts if str(d.get("status") or "") in {"drafting", "paused"}]
    chosen = (
        max(active, key=_draft_recency_key)
        if active
        else max(drafts, key=_draft_recency_key)
    )

    return {
        "found": True,
        "draft_id": str(chosen.get("draft_id") or ""),
        "league_id": str(chosen.get("league_id") or ""),
        "status": str(chosen.get("status") or ""),
        "candidates": candidates,
    }
