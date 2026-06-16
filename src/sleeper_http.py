"""Single source of truth for Sleeper public-API HTTP calls (D-01 LOCKED).

This module owns every outbound HTTP call to ``https://api.sleeper.app``.  All
scripts and services that need Sleeper data — sentiment ingestion, external
projections ingestion, future MCP-replacement utilities — MUST import the
helpers below rather than calling ``requests.get`` / ``urllib.request.urlopen``
directly.

Why centralised?
----------------
Sleeper's API is rate-limited, has occasional 5xx blips, and emits inconsistent
JSON when overloaded.  Centralising the fetch lets us:

* tune timeouts and retries in one place,
* swap to a future MCP/SDK transport without grep-replacing every caller, and
* enforce the project-wide D-06 fail-open contract: any error returns an empty
  ``{}`` (or ``[]``) rather than raising — callers detect the empty payload
  and skip the run gracefully.

Public API
----------
``fetch_sleeper_json(url, timeout=15) -> Any``
    GET ``url`` and return the parsed JSON value.  Returns ``{}`` on any
    network or parse error and logs a WARNING.  The dict default keeps the
    return type usable for the most common Sleeper endpoints (registry,
    projections); endpoints that return lists should ``isinstance`` check
    before iterating.

Draft + user read helpers (typed, fail-open) — v8.0 Live Draft Co-Pilot
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``get_user(username) -> dict``
``get_user_drafts(user_id, season) -> list``
``get_drafts_for_league(league_id) -> list``
``get_draft(draft_id) -> dict``
``get_draft_picks(draft_id) -> list``
``get_traded_picks(draft_id) -> list``
    Thin wrappers over ``fetch_sleeper_json`` that build the Sleeper v1 URL and
    normalize the fail-open default so list endpoints always return ``[]`` and
    object endpoints always return ``{}`` (never the wrong container type).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT_S: int = 15
_USER_AGENT: str = "NFLDataEngineering/1.0 (sleeper-http-helper)"


def fetch_sleeper_json(url: str, timeout: int = _DEFAULT_TIMEOUT_S) -> Any:
    """Fetch a Sleeper public-API URL and return the parsed JSON value.

    Honours the project-wide D-06 fail-open contract.  Any HTTP error,
    network error, or JSON parse error is logged at WARNING level and the
    function returns ``{}`` (an empty dict).  Callers should treat an empty
    return as "skip this run" rather than retrying.

    Uses ``urllib.request`` (stdlib) deliberately so this helper has zero
    third-party dependencies — important for environments where ``requests``
    is intentionally not vendored (e.g. lambdas, minimal CI runners).

    Args:
        url: Fully-qualified Sleeper API URL.
        timeout: Socket timeout in seconds (default 15).

    Returns:
        The parsed JSON value (typically ``dict`` or ``list``) on success;
        ``{}`` on any error.
    """
    if not url:
        logger.warning("fetch_sleeper_json: empty URL provided")
        return {}

    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except HTTPError as exc:
        logger.warning("Sleeper HTTP %d for %s — fail-open returning {}", exc.code, url)
        return {}
    except URLError as exc:
        logger.warning(
            "Sleeper network error for %s: %s — fail-open returning {}",
            url,
            exc.reason,
        )
        return {}
    except (TimeoutError, OSError) as exc:
        logger.warning(
            "Sleeper transport error for %s: %s — fail-open returning {}",
            url,
            exc,
        )
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Sleeper invalid JSON from %s: %s — fail-open returning {}", url, exc
        )
        return {}


# ---------------------------------------------------------------------------
# Draft + user read helpers (v8.0 Live Draft Co-Pilot)
# ---------------------------------------------------------------------------

_BASE_URL: str = "https://api.sleeper.app/v1"


def _as_list(value: Any) -> list:
    """Normalize a fail-open / unexpected payload to a list.

    ``fetch_sleeper_json`` returns ``{}`` on error; Sleeper list endpoints must
    therefore coerce a non-list result to ``[]`` so callers can always iterate.
    """
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    """Normalize a fail-open / unexpected payload to a dict."""
    return value if isinstance(value, dict) else {}


def get_user(username: str, timeout: int = _DEFAULT_TIMEOUT_S) -> dict:
    """Fetch a Sleeper user object by username (or user_id).

    Args:
        username: Sleeper display username or numeric user_id.
        timeout: Socket timeout in seconds.

    Returns:
        The user dict (``user_id``, ``username``, ...) or ``{}`` on any error
        or empty input.
    """
    if not username:
        logger.warning("get_user: empty username provided")
        return {}
    return _as_dict(fetch_sleeper_json(f"{_BASE_URL}/user/{username}", timeout=timeout))


def get_user_drafts(
    user_id: str, season: str, timeout: int = _DEFAULT_TIMEOUT_S
) -> list:
    """Fetch all NFL drafts a user participates in for a season.

    Args:
        user_id: Sleeper numeric user_id.
        season: Four-digit season string (e.g. ``"2026"``).
        timeout: Socket timeout in seconds.

    Returns:
        List of draft dicts (possibly empty); ``[]`` on any error or empty input.
    """
    if not user_id or not season:
        logger.warning("get_user_drafts: empty user_id or season provided")
        return []
    return _as_list(
        fetch_sleeper_json(
            f"{_BASE_URL}/user/{user_id}/drafts/nfl/{season}", timeout=timeout
        )
    )


def get_drafts_for_league(league_id: str, timeout: int = _DEFAULT_TIMEOUT_S) -> list:
    """Fetch all drafts associated with a league.

    Args:
        league_id: Sleeper league_id.
        timeout: Socket timeout in seconds.

    Returns:
        List of draft dicts (possibly empty); ``[]`` on any error or empty input.
    """
    if not league_id:
        logger.warning("get_drafts_for_league: empty league_id provided")
        return []
    return _as_list(
        fetch_sleeper_json(f"{_BASE_URL}/league/{league_id}/drafts", timeout=timeout)
    )


def get_draft(draft_id: str, timeout: int = _DEFAULT_TIMEOUT_S) -> dict:
    """Fetch a single draft's metadata (status, type, settings, draft_order).

    Args:
        draft_id: Sleeper draft_id.
        timeout: Socket timeout in seconds.

    Returns:
        The draft dict or ``{}`` on any error or empty input.
    """
    if not draft_id:
        logger.warning("get_draft: empty draft_id provided")
        return {}
    return _as_dict(
        fetch_sleeper_json(f"{_BASE_URL}/draft/{draft_id}", timeout=timeout)
    )


def get_draft_picks(draft_id: str, timeout: int = _DEFAULT_TIMEOUT_S) -> list:
    """Fetch all picks made so far in a draft (works mid-draft).

    Args:
        draft_id: Sleeper draft_id.
        timeout: Socket timeout in seconds.

    Returns:
        List of pick dicts (possibly empty); ``[]`` on any error or empty input.
    """
    if not draft_id:
        logger.warning("get_draft_picks: empty draft_id provided")
        return []
    return _as_list(
        fetch_sleeper_json(f"{_BASE_URL}/draft/{draft_id}/picks", timeout=timeout)
    )


def get_traded_picks(draft_id: str, timeout: int = _DEFAULT_TIMEOUT_S) -> list:
    """Fetch traded picks for a draft.

    Args:
        draft_id: Sleeper draft_id.
        timeout: Socket timeout in seconds.

    Returns:
        List of traded-pick dicts (possibly empty); ``[]`` on any error or
        empty input.
    """
    if not draft_id:
        logger.warning("get_traded_picks: empty draft_id provided")
        return []
    return _as_list(
        fetch_sleeper_json(
            f"{_BASE_URL}/draft/{draft_id}/traded_picks", timeout=timeout
        )
    )


def get_league(league_id: str, timeout: int = _DEFAULT_TIMEOUT_S) -> dict:
    """Fetch a league object (settings, ``scoring_settings``, ``roster_positions``).

    Used to apply a league's custom scoring + exact starting slots to advice.

    Args:
        league_id: Sleeper league_id.
        timeout: Socket timeout in seconds.

    Returns:
        The league dict or ``{}`` on any error or empty input.
    """
    if not league_id:
        logger.warning("get_league: empty league_id provided")
        return {}
    return _as_dict(
        fetch_sleeper_json(f"{_BASE_URL}/league/{league_id}", timeout=timeout)
    )


def get_league_rosters(league_id: str, timeout: int = _DEFAULT_TIMEOUT_S) -> list:
    """Fetch all rosters in a league (owner_id + kept player_ids per team).

    In a keeper league this is the pre-draft source of truth for who is already
    rostered — used to compute the true draftable pool.

    Args:
        league_id: Sleeper league_id.
        timeout: Socket timeout in seconds.

    Returns:
        List of roster dicts (``roster_id``, ``owner_id``, ``players``, ...);
        ``[]`` on any error or empty input.
    """
    if not league_id:
        logger.warning("get_league_rosters: empty league_id provided")
        return []
    return _as_list(
        fetch_sleeper_json(f"{_BASE_URL}/league/{league_id}/rosters", timeout=timeout)
    )
