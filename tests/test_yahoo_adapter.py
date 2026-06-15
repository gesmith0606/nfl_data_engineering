"""Offline unit tests for the Yahoo draft adapter (v8.0, Phase 88).

Every Yahoo network/OAuth call is monkeypatched to fixtures — no test performs
a real HTTP request, hits a real Yahoo endpoint, or needs real credentials.
All tests are marked ``@pytest.mark.unit`` (CI: no network).
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from src import yahoo_draft
from src.draft_adapter import DraftAdapter
from src.draft_models import DraftState, PickEvent
from src.sleeper_player_map import mapping_coverage
from src.yahoo_adapter import YahooAdapter
from src.yahoo_draft import (
    build_players_index,
    pick_from_yahoo,
    parse_draft_results,
    state_from_yahoo,
)
from src.yahoo_oauth import YahooAuthError, YahooOAuth

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "yahoo_draft")


def _load(name: str):
    with open(os.path.join(_FIXTURE_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def league_settings():
    return _load("league_settings.json")


@pytest.fixture
def draft_results_raw():
    return _load("draft_results.json")


@pytest.fixture
def players_raw():
    return _load("players.json")


@pytest.fixture
def projections_df():
    return pd.DataFrame(_load("projections_sample.json"))


@pytest.fixture
def players_index(players_raw):
    node = yahoo_draft._extract_subresource(players_raw, "players")
    return build_players_index(node)


@pytest.fixture
def merged_results(draft_results_raw):
    node = yahoo_draft._extract_subresource(draft_results_raw, "draft_results")
    return parse_draft_results(node)


# ---------------------------------------------------------------------------
# YH-01: OAuth token manager
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_authorization_url(tmp_path):
    mgr = YahooOAuth(
        client_id="cid",
        client_secret="secret",
        token_path=str(tmp_path / "tok.json"),
    )
    url = mgr.build_authorization_url(state="xyz")
    assert url.startswith("https://api.login.yahoo.com/oauth2/request_auth")
    assert "client_id=cid" in url
    assert "response_type=code" in url
    assert "state=xyz" in url


@pytest.mark.unit
def test_missing_credentials_raises_on_auth_steps(tmp_path):
    mgr = YahooOAuth(
        client_id="", client_secret="", token_path=str(tmp_path / "tok.json")
    )
    assert mgr.has_credentials() is False
    with pytest.raises(YahooAuthError):
        mgr.build_authorization_url()
    with pytest.raises(YahooAuthError):
        mgr.exchange_code("abc")


@pytest.mark.unit
def test_get_access_token_fails_open_without_creds(tmp_path):
    mgr = YahooOAuth(
        client_id="", client_secret="", token_path=str(tmp_path / "tok.json")
    )
    assert mgr.get_access_token() is None


@pytest.mark.unit
def test_refresh_access_token_rotation(tmp_path, monkeypatch):
    """A refresh with no new refresh_token keeps the old one and persists."""
    token_path = str(tmp_path / "tok.json")
    mgr = YahooOAuth(client_id="cid", client_secret="secret", token_path=token_path)
    mgr._tokens = {"refresh_token": "OLD_REFRESH"}

    def fake_post(payload, fallback_refresh_token=None):
        # Simulate Yahoo returning a fresh access token but no new refresh token.
        data = {
            "access_token": "NEW_ACCESS",
            "expires_in": 3600,
            "obtained_at": 10_000_000_000,
        }
        if not data.get("refresh_token") and fallback_refresh_token:
            data["refresh_token"] = fallback_refresh_token
        mgr._tokens = data
        mgr._save_tokens(data)
        return data

    monkeypatch.setattr(mgr, "_post_token", fake_post)
    result = mgr.refresh_access_token()
    assert result["access_token"] == "NEW_ACCESS"
    assert result["refresh_token"] == "OLD_REFRESH"
    # Persisted to disk.
    on_disk = json.load(open(token_path, encoding="utf-8"))
    assert on_disk["access_token"] == "NEW_ACCESS"
    assert on_disk["refresh_token"] == "OLD_REFRESH"


@pytest.mark.unit
def test_refresh_failure_clears_tokens(tmp_path, monkeypatch):
    """A failed refresh clears state so the caller re-authorizes cleanly."""
    token_path = str(tmp_path / "tok.json")
    mgr = YahooOAuth(client_id="cid", client_secret="secret", token_path=token_path)
    mgr._tokens = {"refresh_token": "OLD_REFRESH"}
    mgr._save_tokens(mgr._tokens)
    monkeypatch.setattr(mgr, "_post_token", lambda *a, **k: {})
    result = mgr.refresh_access_token()
    assert result == {}
    assert mgr._tokens == {}
    assert not os.path.exists(token_path)


@pytest.mark.unit
def test_get_access_token_refreshes_when_expired(tmp_path, monkeypatch):
    mgr = YahooOAuth(
        client_id="cid", client_secret="secret", token_path=str(tmp_path / "t.json")
    )
    # Expired access token but a usable refresh token.
    mgr._tokens = {
        "access_token": "STALE",
        "refresh_token": "R1",
        "expires_in": 3600,
        "obtained_at": 0,
    }
    monkeypatch.setattr(
        mgr,
        "refresh_access_token",
        lambda: {"access_token": "FRESH", "refresh_token": "R1"},
    )
    assert mgr.get_access_token() == "FRESH"


@pytest.mark.unit
def test_get_access_token_returns_cached_when_fresh(tmp_path):
    import time as _time

    mgr = YahooOAuth(
        client_id="cid", client_secret="secret", token_path=str(tmp_path / "t.json")
    )
    mgr._tokens = {
        "access_token": "CACHED",
        "refresh_token": "R1",
        "expires_in": 3600,
        "obtained_at": int(_time.time()),
    }
    assert mgr.get_access_token() == "CACHED"


# ---------------------------------------------------------------------------
# YH-02 / YH-03: parsing into neutral models
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_draft_results(merged_results):
    assert len(merged_results) == 6
    first = merged_results[0]
    assert first["pick"] == 1
    assert first["player_key"] == "nfl.p.30977"
    assert first["team_key"] == "nfl.l.123456.t.5"


@pytest.mark.unit
def test_build_players_index(players_index):
    assert players_index["nfl.p.30977"]["full_name"] == "Christian McCaffrey"
    assert players_index["nfl.p.30977"]["position"] == "RB"
    assert players_index["nfl.p.30977"]["team"] == "SF"
    # DEF normalized to DST.
    assert players_index["nfl.p.100007"]["position"] == "DST"


@pytest.mark.unit
def test_pick_from_yahoo(merged_results, players_index):
    pick = pick_from_yahoo(merged_results[1], players_index)
    assert isinstance(pick, PickEvent)
    assert pick.pick_no == 2
    assert pick.round == 1
    assert pick.full_name == "Ja'Marr Chase"
    assert pick.position == "WR"
    assert pick.team == "CIN"
    assert pick.sleeper_player_id == "nfl.p.31883"
    assert pick.roster_id == 3
    assert pick.draft_slot == 3


@pytest.mark.unit
def test_pick_from_yahoo_fail_open_on_garbage():
    pick = pick_from_yahoo({}, {})
    assert isinstance(pick, PickEvent)
    assert pick.pick_no == 0
    assert pick.position == ""


@pytest.mark.unit
def test_state_from_yahoo_scoring_and_roster(
    league_settings, merged_results, players_index
):
    league = yahoo_draft._extract_league(league_settings)
    state = state_from_yahoo(league, merged_results, players_index)
    assert isinstance(state, DraftState)
    assert state.scoring_format == "half_ppr"  # rec modifier 0.5
    assert state.roster_format == "standard"
    assert state.n_teams == 12
    assert state.status == "drafting"
    assert state.is_active is True
    assert len(state.picks) == 6
    assert state.last_pick_no == 6
    assert state.draft_id == "nfl.l.123456"


@pytest.mark.unit
def test_scoring_format_ppr_and_standard():
    ppr = {
        "stat_modifiers": {
            "stats": {"0": {"stat": {"stat_id": "11", "value": "1.0"}}, "count": 1}
        }
    }
    std = {
        "stat_modifiers": {
            "stats": {"0": {"stat": {"stat_id": "11", "value": "0"}}, "count": 1}
        }
    }
    assert yahoo_draft._scoring_format_from_settings(ppr) == "ppr"
    assert yahoo_draft._scoring_format_from_settings(std) == "standard"


@pytest.mark.unit
def test_roster_format_superflex_and_2qb():
    sflex = {
        "roster_positions": {
            "0": {"roster_position": {"position": "QB", "count": 1}},
            "1": {"roster_position": {"position": "Q/W/R/T", "count": 1}},
            "count": 2,
        }
    }
    two_qb = {
        "roster_positions": {
            "0": {"roster_position": {"position": "QB", "count": 2}},
            "count": 1,
        }
    }
    assert yahoo_draft._roster_format_from_settings(sflex) == "superflex"
    assert yahoo_draft._roster_format_from_settings(two_qb) == "2qb"


@pytest.mark.unit
def test_state_from_yahoo_fail_open_empty():
    state = state_from_yahoo({}, [], {})
    assert isinstance(state, DraftState)
    assert state.picks == ()
    assert state.scoring_format == "half_ppr"
    assert state.roster_format == "standard"


# ---------------------------------------------------------------------------
# YH-02: adapter conformance + network assembly
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_adapter_satisfies_protocol():
    adapter = YahooAdapter()
    assert isinstance(adapter, DraftAdapter)
    assert adapter.platform == "yahoo"


@pytest.mark.unit
def test_load_state_assembles_from_fixtures(
    monkeypatch, league_settings, draft_results_raw, players_raw
):
    """load_draft_state joins league + draft + players with no real network."""

    def fake_fetch(path, oauth, timeout=15):
        if "/settings" in path:
            return league_settings
        if "/draftresults" in path:
            return draft_results_raw
        if "/players" in path:
            return players_raw
        return {}

    monkeypatch.setattr(yahoo_draft, "fetch_yahoo_json", fake_fetch)
    adapter = YahooAdapter(oauth=YahooOAuth(client_id="c", client_secret="s"))
    state = adapter.load_state("nfl.l.123456")
    assert len(state.picks) == 6
    names = {p.full_name for p in state.picks}
    assert "Patrick Mahomes" in names
    assert state.scoring_format == "half_ppr"


@pytest.mark.unit
def test_load_state_fail_open_on_network_error(monkeypatch):
    monkeypatch.setattr(yahoo_draft, "fetch_yahoo_json", lambda *a, **k: {})
    adapter = YahooAdapter(oauth=YahooOAuth(client_id="c", client_secret="s"))
    state = adapter.load_state("nfl.l.999")
    assert isinstance(state, DraftState)
    assert state.picks == ()


@pytest.mark.unit
def test_resolve_draft_direct_league(monkeypatch, league_settings):
    monkeypatch.setattr(
        yahoo_draft, "fetch_yahoo_json", lambda *a, **k: league_settings
    )
    adapter = YahooAdapter(oauth=YahooOAuth(client_id="c", client_secret="s"))
    res = adapter.resolve_draft("123456", "2026")
    assert res["found"] is True
    assert res["draft_id"] == "nfl.l.123456"
    assert res["league_id"] == "123456"
    assert res["status"] == "drafting"


@pytest.mark.unit
def test_resolve_draft_fail_open(monkeypatch):
    monkeypatch.setattr(yahoo_draft, "fetch_yahoo_json", lambda *a, **k: {})
    adapter = YahooAdapter(oauth=YahooOAuth(client_id="c", client_secret="s"))
    res = adapter.resolve_draft("", "2026")
    assert res["found"] is False
    assert res["candidates"] == []


# ---------------------------------------------------------------------------
# YH-03: mapping coverage (>= 95% skill positions)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_map_picks_skill_coverage(
    monkeypatch, league_settings, draft_results_raw, players_raw, projections_df
):
    def fake_fetch(path, oauth, timeout=15):
        if "/settings" in path:
            return league_settings
        if "/draftresults" in path:
            return draft_results_raw
        if "/players" in path:
            return players_raw
        return {}

    monkeypatch.setattr(yahoo_draft, "fetch_yahoo_json", fake_fetch)
    adapter = YahooAdapter(oauth=YahooOAuth(client_id="c", client_secret="s"))
    state = adapter.load_state("nfl.l.123456")
    matched, unmatched = adapter.map_picks(state.picks, projections_df)
    coverage = mapping_coverage(matched, unmatched)
    assert coverage >= 0.95
    # All four skill players (MCC/Chase/Mahomes/Kelce) matched.
    matched_names = {m["player_name"] for m in matched}
    assert {
        "Christian McCaffrey",
        "Ja'Marr Chase",
        "Patrick Mahomes",
        "Travis Kelce",
    } <= matched_names


@pytest.mark.unit
def test_map_picks_empty_projections_returns_all_unmatched(
    monkeypatch, league_settings, draft_results_raw, players_raw
):
    def fake_fetch(path, oauth, timeout=15):
        if "/settings" in path:
            return league_settings
        if "/draftresults" in path:
            return draft_results_raw
        if "/players" in path:
            return players_raw
        return {}

    monkeypatch.setattr(yahoo_draft, "fetch_yahoo_json", fake_fetch)
    adapter = YahooAdapter(oauth=YahooOAuth(client_id="c", client_secret="s"))
    state = adapter.load_state("nfl.l.123456")
    matched, unmatched = adapter.map_picks(state.picks, pd.DataFrame())
    assert matched == []
    assert len(unmatched) == len(state.picks)
