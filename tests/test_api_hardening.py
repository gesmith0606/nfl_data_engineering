"""Audit hardening: CORS credentials, Yahoo owner gate, ESPN env cookies."""

import importlib

import pytest
from fastapi.testclient import TestClient

EVIL = "https://evil.example"


def _reload():
    import web.api.config as config
    import web.api.main as main

    importlib.reload(config)
    importlib.reload(main)
    return main


def _client(monkeypatch, origins, api_key=""):
    monkeypatch.setenv("CORS_ORIGINS", origins)
    monkeypatch.setenv("API_KEY", api_key)
    return TestClient(_reload().app)


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    yield
    monkeypatch.undo()
    _reload()


def test_cors_wildcard_has_no_credentials(monkeypatch):
    c = _client(monkeypatch, "*")
    r = c.get("/api/health", headers={"Origin": EVIL})
    assert "access-control-allow-credentials" not in r.headers


def test_cors_explicit_list_never_sends_credentials(monkeypatch):
    # The HF proxy adds its own reflected allow-origin, so ours must never
    # contribute allow-credentials, allowed origin or not.
    c = _client(monkeypatch, "https://ok.example")
    r = c.get("/api/health", headers={"Origin": "https://ok.example"})
    assert r.headers.get("access-control-allow-origin") == "https://ok.example"
    assert "access-control-allow-credentials" not in r.headers
    r = c.get("/api/health", headers={"Origin": EVIL})
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-credentials" not in r.headers


def test_yahoo_anonymous_leagues_forbidden(monkeypatch):
    c = _client(monkeypatch, "*")
    assert c.get("/api/yahoo/leagues").status_code == 403


def test_yahoo_anonymous_connect_forbidden_and_writes_nothing(monkeypatch):
    c = _client(monkeypatch, "*")
    from web.api.routers import yahoo

    called = []
    monkeypatch.setattr(
        yahoo.YahooOAuth, "exchange_code", lambda *a, **k: called.append(1)
    )
    r = c.post("/api/yahoo/connect", json={"code": "x"})
    assert r.status_code == 403
    assert not called


def test_yahoo_key_gate(monkeypatch):
    c = _client(monkeypatch, "*", api_key="s3cret")
    assert c.get("/api/yahoo/leagues", headers={"X-API-Key": "no"}).status_code in (
        401,
        403,
    )
    # right key passes the gate (then fails later: not connected)
    r = c.get("/api/yahoo/leagues", headers={"X-API-Key": "s3cret"})
    assert r.status_code != 403


def test_yahoo_bad_league_key_rejected(monkeypatch):
    c = _client(monkeypatch, "*", api_key="s3cret")
    h = {"X-API-Key": "s3cret"}
    assert c.get("/api/yahoo/league/evil/teams", headers=h).status_code == 422
    assert c.get("/api/yahoo/league/1.l.2%3Fx/teams", headers=h).status_code == 422


def test_espn_router_never_sends_env_cookies(monkeypatch):
    c = _client(monkeypatch, "*")
    from src import espn_league

    monkeypatch.setenv("ESPN_S2", "owner-s2")
    monkeypatch.setenv("ESPN_SWID", "{OWNER}")
    seen = {}

    class Resp:
        status_code = 401

    def fake_get(url, **kw):
        seen["cookies"] = kw.get("cookies")
        return Resp()

    monkeypatch.setattr(espn_league.requests, "get", fake_get)
    r = c.post("/api/espn/import", json={"league_id": 1, "season": 2026})
    assert r.status_code == 401
    assert not seen["cookies"]
    assert ".env" not in r.text


def test_espn_cli_default_still_uses_env_cookies(monkeypatch):
    from src import espn_league

    monkeypatch.setenv("ESPN_S2", "owner-s2")
    monkeypatch.setenv("ESPN_SWID", "{OWNER}")
    seen = {}

    class Resp:
        status_code = 404

    monkeypatch.setattr(
        espn_league.requests, "get", lambda url, **kw: seen.update(kw) or Resp()
    )
    with pytest.raises(LookupError):
        espn_league.fetch_league(1, 2026)
    assert seen["cookies"]
