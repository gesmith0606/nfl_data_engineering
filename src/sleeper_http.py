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
