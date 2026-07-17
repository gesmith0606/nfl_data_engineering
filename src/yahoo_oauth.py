"""Minimal Yahoo OAuth2 token manager (v8.0 Live Draft Co-Pilot, Phase 88, YH-01).

Yahoo's Fantasy Sports API uses a 3-legged OAuth2 flow with short-lived access
tokens (~60 minutes) and rotating refresh tokens. This module owns that flow with
**stdlib only** (``urllib`` + ``json``) to match the project's zero-dependency
HTTP ethos (see :mod:`src.sleeper_http`) — no ``requests``, no ``yfpy`` runtime
requirement.

Responsibilities
----------------
* Read ``YAHOO_CLIENT_ID`` / ``YAHOO_CLIENT_SECRET`` from the environment only —
  never hardcode secrets.
* Build the authorization URL a user visits once to grant access.
* Exchange an authorization ``code`` for an initial access + refresh token pair.
* Refresh the access token using the stored refresh token (handling Yahoo's
  refresh-token rotation: a refresh response may return a *new* refresh token).
* Persist/load tokens to/from a JSON file (default under ``data/``), so a draft
  session can resume without re-authorizing.

Fail-open contract (D-06)
-------------------------
Network/parse failures return ``{}`` and log a WARNING rather than raising, so a
flaky Yahoo endpoint never crashes a live draft. Missing credentials raise a
clear :class:`YahooAuthError` *only* on the explicit auth-initiating calls
(``exchange_code`` / ``refresh_access_token``) where proceeding is impossible;
``get_access_token`` degrades to ``None`` so the adapter can fail open.

Three-legged flow (one-time, by the user)
-----------------------------------------
1. ``url = mgr.build_authorization_url()`` — open in a browser, sign in, approve.
2. Yahoo redirects to the configured redirect URI with ``?code=...`` (or, for the
   ``oob`` redirect, shows the code on screen).
3. ``mgr.exchange_code(code)`` — stores tokens to the token file.
4. Thereafter ``mgr.get_access_token()`` returns a valid token, refreshing
   transparently when the cached one is within the expiry skew window.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUTH_BASE_URL: str = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL: str = "https://api.login.yahoo.com/oauth2/get_token"

# Yahoo's "out of band" redirect shows the auth code on screen instead of
# redirecting — convenient for a CLI co-pilot with no web server.
DEFAULT_REDIRECT_URI: str = "oob"

_DEFAULT_TOKEN_PATH: str = os.path.join("data", "yahoo_tokens.json")
_DEFAULT_TIMEOUT_S: int = 15
_USER_AGENT: str = "NFLDataEngineering/1.0 (yahoo-oauth-helper)"

# Refresh slightly early so a token never expires mid-request. Yahoo access
# tokens live ~3600s; refresh once under 5 minutes remain.
_EXPIRY_SKEW_S: int = 300


class YahooAuthError(RuntimeError):
    """Raised when an auth step cannot proceed (e.g. missing credentials)."""


class YahooOAuth:
    """Stateful Yahoo OAuth2 token manager backed by a JSON token file.

    Credentials are read from the environment at construction time. Tokens are
    loaded from ``token_path`` if present so an existing grant survives process
    restarts.

    Args:
        client_id: Yahoo app client id. Defaults to ``$YAHOO_CLIENT_ID``.
        client_secret: Yahoo app client secret. Defaults to
            ``$YAHOO_CLIENT_SECRET``.
        redirect_uri: OAuth redirect URI registered with the Yahoo app. Defaults
            to ``"oob"`` (show code on screen — ideal for a CLI).
        token_path: Where to persist/load the token JSON. Defaults to
            ``data/yahoo_tokens.json``.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: str = DEFAULT_REDIRECT_URI,
        token_path: str = _DEFAULT_TOKEN_PATH,
    ) -> None:
        self.client_id = client_id or os.environ.get("YAHOO_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("YAHOO_CLIENT_SECRET", "")
        self.redirect_uri = redirect_uri or DEFAULT_REDIRECT_URI
        self.token_path = token_path
        self._tokens: Dict[str, Any] = self._load_tokens()

    # ------------------------------------------------------------------
    # Credential / state helpers
    # ------------------------------------------------------------------

    def has_credentials(self) -> bool:
        """True when both client id and secret are present."""
        return bool(self.client_id and self.client_secret)

    def _require_credentials(self) -> None:
        if not self.has_credentials():
            raise YahooAuthError(
                "Yahoo credentials missing — set YAHOO_CLIENT_ID and "
                "YAHOO_CLIENT_SECRET in the environment (never hardcode them)."
            )

    # ------------------------------------------------------------------
    # Authorization URL
    # ------------------------------------------------------------------

    def build_authorization_url(self, state: Optional[str] = None) -> str:
        """Build the URL a user visits once to grant access.

        Args:
            state: Optional opaque value echoed back by Yahoo for CSRF defense.

        Returns:
            The fully-qualified authorization URL.

        Raises:
            YahooAuthError: If credentials are missing.
        """
        self._require_credentials()
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
        }
        if state:
            params["state"] = state
        return f"{AUTH_BASE_URL}?{urlencode(params)}"

    # ------------------------------------------------------------------
    # Token endpoint calls
    # ------------------------------------------------------------------

    def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange an authorization ``code`` for an access + refresh token pair.

        On success the tokens are stored to ``token_path`` and returned.

        Args:
            code: The authorization code from the redirect (or ``oob`` screen).

        Returns:
            The stored token dict on success, or ``{}`` on a network/parse error.

        Raises:
            YahooAuthError: If credentials are missing or ``code`` is empty.
        """
        self._require_credentials()
        if not code:
            raise YahooAuthError("exchange_code: empty authorization code")
        payload = {
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "code": code,
        }
        return self._post_token(payload)

    def refresh_access_token(self) -> Dict[str, Any]:
        """Refresh the access token using the stored refresh token.

        Handles Yahoo's refresh-token rotation: if the response includes a new
        ``refresh_token`` it replaces the old one. On a failed refresh the local
        tokens are cleared so the caller can prompt a clean re-authorization.

        Returns:
            The refreshed token dict on success, or ``{}`` on failure.

        Raises:
            YahooAuthError: If credentials or a stored refresh token are missing.
        """
        self._require_credentials()
        refresh_token = str(self._tokens.get("refresh_token") or "")
        if not refresh_token:
            raise YahooAuthError(
                "refresh_access_token: no stored refresh_token — run the "
                "authorization flow first (build_authorization_url + "
                "exchange_code)."
            )
        payload = {
            "grant_type": "refresh_token",
            "redirect_uri": self.redirect_uri,
            "refresh_token": refresh_token,
        }
        result = self._post_token(payload, fallback_refresh_token=refresh_token)
        if not result:
            # Refresh failed — clear state so the caller re-auths cleanly (YH-01).
            logger.warning(
                "Yahoo refresh failed — clearing stored tokens; re-auth required."
            )
            self.clear_tokens()
        return result

    def get_access_token(self) -> Optional[str]:
        """Return a valid access token, refreshing transparently if near expiry.

        Fail-open: returns ``None`` (never raises) when no usable token can be
        obtained, so the adapter can skip gracefully rather than crash a draft.

        Returns:
            A non-empty access-token string, or ``None``.
        """
        if not self.has_credentials():
            logger.warning("get_access_token: Yahoo credentials missing")
            return None

        token = str(self._tokens.get("access_token") or "")
        if token and not self._is_expired():
            return token

        if not self._tokens.get("refresh_token"):
            logger.warning("get_access_token: no refresh_token — re-auth required")
            return None

        try:
            refreshed = self.refresh_access_token()
        except YahooAuthError as exc:
            logger.warning("get_access_token: %s", exc)
            return None
        new_token = str(refreshed.get("access_token") or "")
        return new_token or None

    # ------------------------------------------------------------------
    # Internal HTTP + persistence
    # ------------------------------------------------------------------

    def _post_token(
        self,
        payload: Dict[str, str],
        fallback_refresh_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST to the Yahoo token endpoint and persist the result.

        Args:
            payload: Form fields for the grant (sans client credentials, which
                are added here).
            fallback_refresh_token: Reused when the response omits a new
                ``refresh_token`` (Yahoo sometimes returns the same one).

        Returns:
            The stored token dict on success; ``{}`` on any error.
        """
        body = dict(payload)
        body["client_id"] = self.client_id
        body["client_secret"] = self.client_secret
        encoded = urlencode(body).encode("utf-8")
        req = Request(
            TOKEN_URL,
            data=encoded,
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=_DEFAULT_TIMEOUT_S) as resp:
                raw = resp.read()
        except HTTPError as exc:
            logger.warning("Yahoo token HTTP %d — fail-open returning {}", exc.code)
            return {}
        except URLError as exc:
            logger.warning(
                "Yahoo token network error: %s — fail-open returning {}",
                exc.reason,
            )
            return {}
        except (TimeoutError, OSError) as exc:
            logger.warning(
                "Yahoo token transport error: %s — fail-open returning {}", exc
            )
            return {}

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Yahoo token invalid JSON: %s — fail-open returning {}", exc)
            return {}
        if not isinstance(data, dict) or not data.get("access_token"):
            logger.warning("Yahoo token response missing access_token — fail-open")
            return {}

        # Refresh-token rotation: keep the previous one if Yahoo omits it.
        if not data.get("refresh_token") and fallback_refresh_token:
            data["refresh_token"] = fallback_refresh_token

        data["obtained_at"] = int(time.time())
        self._tokens = data
        self._save_tokens(data)
        return data

    def _is_expired(self) -> bool:
        """True when the cached access token is missing or within the skew window."""
        obtained = self._tokens.get("obtained_at")
        expires_in = self._tokens.get("expires_in")
        if obtained is None or expires_in is None:
            return True
        try:
            deadline = int(obtained) + int(expires_in) - _EXPIRY_SKEW_S
        except (TypeError, ValueError):
            return True
        return time.time() >= deadline

    def _load_tokens(self) -> Dict[str, Any]:
        if not os.path.exists(self.token_path):
            return self._seed_from_env()
        try:
            with open(self.token_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else self._seed_from_env()
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Could not read Yahoo token file %s: %s", self.token_path, exc
            )
            return self._seed_from_env()

    @staticmethod
    def _seed_from_env() -> Dict[str, Any]:
        """Bootstrap from ``$YAHOO_REFRESH_TOKEN`` when no token file exists.

        Deployed backends (HF Spaces) have no interactive browser and no
        persisted ``data/yahoo_tokens.json`` — a refresh token minted once
        locally and set as an env secret is enough: ``get_access_token``
        treats the seeded state as expired and refreshes on first use.
        """
        refresh = os.environ.get("YAHOO_REFRESH_TOKEN", "").strip()
        if not refresh:
            return {}
        logger.info("Seeding Yahoo tokens from YAHOO_REFRESH_TOKEN env")
        return {"refresh_token": refresh}

    def _save_tokens(self, tokens: Dict[str, Any]) -> None:
        try:
            directory = os.path.dirname(self.token_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.token_path, "w", encoding="utf-8") as fh:
                json.dump(tokens, fh)
        except OSError as exc:
            logger.warning(
                "Could not write Yahoo token file %s: %s", self.token_path, exc
            )

    def clear_tokens(self) -> None:
        """Drop cached tokens (memory + disk) to force a clean re-authorization."""
        self._tokens = {}
        try:
            if os.path.exists(self.token_path):
                os.remove(self.token_path)
        except OSError as exc:
            logger.warning(
                "Could not remove Yahoo token file %s: %s", self.token_path, exc
            )
