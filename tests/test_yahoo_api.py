"""Smoke tests for /api/yahoo router (deferred-items sprint).

No network: all tests run credential-less and assert the fail-closed
behavior of each endpoint.
"""

from fastapi.testclient import TestClient

from web.api.main import app

client = TestClient(app)


def test_status_reports_disconnected(monkeypatch):
    monkeypatch.delenv("YAHOO_CLIENT_ID", raising=False)
    monkeypatch.delenv("YAHOO_CLIENT_SECRET", raising=False)
    resp = client.get("/api/yahoo/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_credentials"] is False
    assert body["connected"] is False
    assert body["redirect_mode"] in ("oob", "callback")


def test_auth_url_503_without_credentials(monkeypatch):
    monkeypatch.delenv("YAHOO_CLIENT_ID", raising=False)
    monkeypatch.delenv("YAHOO_CLIENT_SECRET", raising=False)
    assert client.get("/api/yahoo/auth-url").status_code == 503


def test_auth_url_with_credentials(monkeypatch):
    monkeypatch.setenv("YAHOO_CLIENT_ID", "cid")
    monkeypatch.setenv("YAHOO_CLIENT_SECRET", "sec")
    monkeypatch.setenv(
        "YAHOO_REDIRECT_URI", "https://api.example.com/api/yahoo/callback"
    )
    resp = client.get("/api/yahoo/auth-url")
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"].startswith("https://api.login.yahoo.com/oauth2/request_auth")
    assert "client_id=cid" in body["url"]
    assert body["redirect_mode"] == "callback"


def test_callback_requires_code():
    assert client.get("/api/yahoo/callback").status_code == 400


def test_leagues_401_when_disconnected(monkeypatch):
    monkeypatch.delenv("YAHOO_CLIENT_ID", raising=False)
    monkeypatch.delenv("YAHOO_CLIENT_SECRET", raising=False)
    assert client.get("/api/yahoo/leagues").status_code == 401


def test_teams_401_when_disconnected(monkeypatch):
    monkeypatch.delenv("YAHOO_CLIENT_ID", raising=False)
    monkeypatch.delenv("YAHOO_CLIENT_SECRET", raising=False)
    assert client.get("/api/yahoo/league/nfl.l.123/teams").status_code == 401


class TestAuthorizationScope:
    """Since 2026 the Fantasy API is approval-gated and scope is not optional.

    A token granted without a fantasy scope authenticates fine and then 401s on
    every fantasysports call, which looks like a broken client rather than
    missing access. Requesting the scope explicitly makes the grant itself say
    whether the app is approved.
    """

    def _oauth(self):
        from yahoo_oauth import YahooOAuth

        return YahooOAuth(client_id="cid", client_secret="sec")

    def test_read_scope_is_the_default(self):
        assert "scope=fspt-r" in self._oauth().build_authorization_url()

    def test_write_scope_can_be_requested(self):
        """fspt-w is what a lineup write needs, and a higher access tier."""
        assert "scope=fspt-w" in self._oauth().build_authorization_url(scope="fspt-w")

    def test_scope_can_be_omitted_for_the_pre_2026_flow(self):
        url = self._oauth().build_authorization_url(scope=None)
        assert "scope=" not in url

    def test_state_still_round_trips_alongside_scope(self):
        url = self._oauth().build_authorization_url(state="xyz", scope="fspt-r")
        assert "state=xyz" in url and "scope=fspt-r" in url
