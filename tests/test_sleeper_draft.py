"""Offline unit tests for the Sleeper draft data layer (Phase 85).

All Sleeper network access is monkeypatched to fixtures — no test performs a
real HTTP call.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from src import sleeper_http, sleeper_player_map
from src.draft_models import DraftState, PickEvent
from src.sleeper_draft import (
    pick_from_sleeper,
    resolve_active_draft,
    state_from_sleeper,
)

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sleeper_draft")


def _load(name: str):
    with open(os.path.join(_FIXTURE_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def draft_raw():
    return _load("draft.json")


@pytest.fixture
def picks_raw():
    return _load("picks.json")


@pytest.fixture
def traded_raw():
    return _load("traded.json")


@pytest.fixture
def players_registry():
    return _load("sleeper_players_sample.json")


@pytest.fixture
def projections_df():
    return pd.DataFrame(_load("projections_sample.json"))


# ---------------------------------------------------------------------------
# SLPR-01: endpoint fail-open normalization
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_endpoints_normalize_failopen_to_list(monkeypatch):
    # fetch_sleeper_json fail-opens to {} — list helpers must coerce to [].
    monkeypatch.setattr(sleeper_http, "fetch_sleeper_json", lambda *a, **k: {})
    assert sleeper_http.get_draft_picks("123") == []
    assert sleeper_http.get_drafts_for_league("123") == []
    assert sleeper_http.get_traded_picks("123") == []
    assert sleeper_http.get_user_drafts("u1", "2026") == []


@pytest.mark.unit
def test_object_endpoints_normalize_failopen_to_dict(monkeypatch):
    monkeypatch.setattr(sleeper_http, "fetch_sleeper_json", lambda *a, **k: [])
    assert sleeper_http.get_draft("123") == {}
    assert sleeper_http.get_user("nobody") == {}


@pytest.mark.unit
def test_empty_ids_guarded():
    assert sleeper_http.get_draft_picks("") == []
    assert sleeper_http.get_draft("") == {}
    assert sleeper_http.get_user("") == {}


# ---------------------------------------------------------------------------
# SLPR-04: PickEvent / DraftState parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pickevent_parses_known_row(picks_raw):
    pe = pick_from_sleeper(picks_raw[0])
    assert pe.pick_no == 1
    assert pe.round == 1
    assert pe.position == "QB"
    assert pe.full_name == "Patrick Mahomes"
    assert pe.is_keeper is False


@pytest.mark.unit
def test_pickevent_defensive_on_empty_dict():
    pe = pick_from_sleeper({})
    assert pe.pick_no == 0
    assert pe.is_keeper is False
    assert pe.full_name == ""


@pytest.mark.unit
def test_draftstate_maps_scoring_and_settings(draft_raw, picks_raw, traded_raw):
    ds = state_from_sleeper(draft_raw, picks_raw, traded_raw)
    assert ds.scoring_format == "half_ppr"
    assert ds.roster_format == "standard"
    assert ds.n_teams == 12
    assert ds.rounds == 15
    assert ds.draft_type == "snake"
    # picks sorted by pick_no
    assert [p.pick_no for p in ds.picks] == list(range(1, 9))
    assert ds.last_pick_no == 8


@pytest.mark.unit
def test_draftstate_scoring_from_rec_value_when_no_label():
    ds = state_from_sleeper({"settings": {"rec": 1.0, "teams": 10}, "type": "snake"})
    assert ds.scoring_format == "ppr"
    ds2 = state_from_sleeper({"settings": {"rec": 0.0}, "type": "linear"})
    assert ds2.scoring_format == "standard"


@pytest.mark.unit
def test_load_draft_state_uses_helpers(monkeypatch, draft_raw, picks_raw, traded_raw):
    monkeypatch.setattr(sleeper_http, "get_draft", lambda d: draft_raw)
    monkeypatch.setattr(sleeper_http, "get_draft_picks", lambda d: picks_raw)
    monkeypatch.setattr(sleeper_http, "get_traded_picks", lambda d: traded_raw)
    from src.sleeper_draft import load_draft_state

    ds = load_draft_state("999000111")
    assert ds.draft_id == "999000111"
    assert len(ds.picks) == 8


# ---------------------------------------------------------------------------
# SLPR-02: active-draft resolution
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_prefers_active_draft(monkeypatch):
    monkeypatch.setattr(sleeper_http, "get_user", lambda u: {"user_id": "u1"})
    monkeypatch.setattr(
        sleeper_http,
        "get_user_drafts",
        lambda uid, season: [
            {
                "draft_id": "d_old",
                "league_id": "L1",
                "status": "complete",
                "start_time": 100,
            },
            {
                "draft_id": "d_live",
                "league_id": "L2",
                "status": "drafting",
                "start_time": 200,
            },
        ],
    )
    res = resolve_active_draft("george", "2026")
    assert res["found"] is True
    assert res["draft_id"] == "d_live"
    assert len(res["candidates"]) == 2


@pytest.mark.unit
def test_resolve_falls_back_to_most_recent(monkeypatch):
    monkeypatch.setattr(sleeper_http, "get_user", lambda u: {"user_id": "u1"})
    monkeypatch.setattr(
        sleeper_http,
        "get_user_drafts",
        lambda uid, season: [
            {
                "draft_id": "d_a",
                "league_id": "L1",
                "status": "complete",
                "start_time": 100,
            },
            {
                "draft_id": "d_b",
                "league_id": "L2",
                "status": "pre_draft",
                "start_time": 300,
            },
        ],
    )
    res = resolve_active_draft("george", "2026")
    assert res["found"] is True
    assert res["draft_id"] == "d_b"  # newest by start_time


@pytest.mark.unit
def test_resolve_empty_is_not_found(monkeypatch):
    monkeypatch.setattr(sleeper_http, "get_user", lambda u: {})
    res = resolve_active_draft("ghost", "2026")
    assert res["found"] is False
    assert res["candidates"] == []


@pytest.mark.unit
def test_resolve_filters_by_league(monkeypatch):
    monkeypatch.setattr(sleeper_http, "get_user", lambda u: {"user_id": "u1"})
    monkeypatch.setattr(
        sleeper_http,
        "get_user_drafts",
        lambda uid, season: [
            {"draft_id": "d_a", "league_id": "L1", "status": "drafting"},
            {"draft_id": "d_b", "league_id": "L2", "status": "drafting"},
        ],
    )
    res = resolve_active_draft("george", "2026", league_id="L2")
    assert res["draft_id"] == "d_b"
    assert len(res["candidates"]) == 1


# ---------------------------------------------------------------------------
# SLPR-03: player registry + mapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalize_name_strips_suffix():
    assert sleeper_player_map.normalize_name("Marvin Harrison Jr.") == "marvin harrison"
    assert sleeper_player_map.normalize_name("Michael Pittman III") == "michael pittman"


@pytest.mark.unit
def test_load_sleeper_players_caches(tmp_path, monkeypatch, players_registry):
    cache = tmp_path / "sleeper_players.json"
    monkeypatch.setattr(
        sleeper_http, "fetch_sleeper_json", lambda *a, **k: players_registry
    )
    out = sleeper_player_map.load_sleeper_players(cache_path=str(cache))
    assert cache.exists()
    assert out["4046"]["full_name"] == "Patrick Mahomes"


@pytest.mark.unit
def test_build_player_index_shape(players_registry):
    idx = sleeper_player_map.build_player_index(players_registry)
    assert idx["8112"]["normalized_name"] == "marvin harrison"
    assert idx["4046"]["position"] == "QB"


@pytest.mark.unit
def test_mapping_skill_coverage_and_unmatched(
    draft_raw, picks_raw, players_registry, projections_df
):
    ds = state_from_sleeper(draft_raw, picks_raw)
    index = sleeper_player_map.build_player_index(players_registry)
    matched, unmatched = sleeper_player_map.map_picks_to_projections(
        ds.picks, projections_df, player_index=index
    )
    coverage = sleeper_player_map.mapping_coverage(matched, unmatched)
    assert coverage >= 0.95  # all 6 skill picks map
    # DST + K have no projection row → surfaced as unmatched, never dropped
    unmatched_pos = {p.position for p in unmatched}
    assert "DEF" in unmatched_pos
    assert "K" in unmatched_pos
    assert len(matched) + len(unmatched) == len(ds.picks)


@pytest.mark.unit
def test_mapping_uses_metadata_fallback_when_no_index(
    draft_raw, picks_raw, projections_df
):
    # No registry index — mapping must fall back to the pick's embedded metadata.
    ds = state_from_sleeper(draft_raw, picks_raw)
    matched, unmatched = sleeper_player_map.map_picks_to_projections(
        ds.picks, projections_df, player_index={}
    )
    assert sleeper_player_map.mapping_coverage(matched, unmatched) >= 0.95
