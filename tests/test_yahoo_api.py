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
