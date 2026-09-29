"""Unit tests for src/league_context.py — league FAAB/bid/dynasty context."""

from __future__ import annotations

import json
import os
import time

import pandas as pd
import requests

from src import league_context as lc

REGISTRY = {
    "100": {
        "full_name": "Braelon Allen",
        "position": "RB",
        "team": "NYJ",
        "age": 22,
        "years_exp": 2,
        "espn_id": 5001,
    },
    "200": {
        "full_name": "Drew Lock",
        "position": "QB",
        "team": "SEA",
        "age": 29,
        "years_exp": 7,
        "espn_id": 5002,
    },
    "300": {
        "full_name": "Puka Nacua",
        "position": "WR",
        "team": "LAR",
        "age": 25,
        "years_exp": 3,
    },
}
FC_ROWS = [
    {
        "player": {"sleeperId": "100"},
        "value": 1257,
        "overallRank": 173,
        "trend30Day": 13,
    },
    {
        "player": {"sleeperId": "300"},
        "value": 7433,
        "overallRank": 7,
        "trend30Day": -738,
    },
    {"player": {"sleeperId": None}, "value": 50},  # pick / unmapped: skipped
]


def test_parse_fantasycalc_keys_by_sleeper_id() -> None:
    v = lc.parse_fantasycalc(FC_ROWS)
    assert set(v) == {"100", "300"}
    assert v["300"] == {"value": 7433, "rank": 7, "trend30": -738}


def test_fetch_dynasty_values_uses_fresh_cache_without_network(
    tmp_path, monkeypatch
) -> None:
    cache = tmp_path / "values_2qb_10t_1ppr.json"
    cache.write_text(json.dumps(FC_ROWS))

    def boom(*a, **k):  # network must not be touched
        raise AssertionError("fetched despite fresh cache")

    monkeypatch.setattr(lc.requests, "get", boom)
    assert (
        lc.fetch_dynasty_values(2, 10, 1.0, cache_dir=tmp_path)["100"]["value"] == 1257
    )


def test_fetch_dynasty_values_falls_back_to_stale_cache(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "values_2qb_10t_1ppr.json"
    cache.write_text(json.dumps(FC_ROWS))
    old = time.time() - 3 * 86400
    os.utime(cache, (old, old))

    def fail(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(lc.requests, "get", fail)
    assert "300" in lc.fetch_dynasty_values(2, 10, 1.0, cache_dir=tmp_path)
    assert (
        lc.fetch_dynasty_values(1, 12, 0.5, cache_dir=tmp_path) == {}
    )  # no cache at all


def test_dynasty_values_for_preset_only_for_dynasty(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        lc, "fetch_dynasty_values", lambda **k: calls.append(k) or {"1": {}}
    )
    shapes = {"superflex": {"QB": 1, "SFLEX": 1}, "standard": {"QB": 1}}
    assert lc.dynasty_values_for_preset({"roster": "superflex"}, shapes) == {}
    lc.dynasty_values_for_preset(
        {"dynasty": True, "roster": "superflex", "teams": 10, "scoring_format": "ppr"},
        shapes,
    )
    assert calls == [{"num_qbs": 2, "num_teams": 10, "ppr": 1.0}]


def _sleeper_fixture():
    league = {"settings": {"waiver_budget": 1000}}
    users = [
        {"user_id": "u1", "display_name": "Gforceee"},
        {"user_id": "u2", "display_name": "rival"},
    ]
    rosters = [
        {
            "roster_id": 1,
            "owner_id": "u1",
            "players": ["100", "300"],
            "settings": {"wins": 2, "losses": 2, "waiver_budget_used": 602},
        },
        {
            "roster_id": 2,
            "owner_id": "u2",
            "players": ["200"],
            "settings": {"wins": 3, "losses": 1},
        },
    ]
    txns = {
        2: [
            {
                "status": "complete",
                "type": "waiver",
                "roster_ids": [1],
                "adds": {"200": 1},
                "drops": {"100": 1},
                "settings": {"waiver_bid": 55},
            },
            {
                "status": "failed",
                "type": "waiver",
                "roster_ids": [2],
                "adds": {"100": 2},
                "settings": {"waiver_bid": 90},
            },
            {
                "status": "complete",
                "type": "free_agent",
                "roster_ids": [2],
                "adds": None,
                "drops": {"200": 2},
            },
        ]
    }
    return league, users, rosters, txns


def test_sleeper_context_faab_and_moves() -> None:
    teams, tx = lc.sleeper_context(*_sleeper_fixture(), REGISTRY, "Gforceee")
    me = teams[teams["is_me"]].iloc[0]
    assert (me["faab_left"], me["faab_spent"], me["n_players"]) == (398, 602, 2)
    assert teams.loc[~teams["is_me"], "faab_left"].iloc[0] == 1000  # missing used -> 0
    assert len(tx) == 2  # failed claim dropped
    mine = tx[tx["is_me"]].iloc[0]
    assert (
        mine["add"] == "Drew Lock (QB,29)" and mine["drop"] == "Braelon Allen (RB,22)"
    )
    assert mine["bid"] == 55


def test_espn_context_maps_players_through_registry() -> None:
    payload = {
        "settings": {"acquisitionSettings": {"acquisitionBudget": 100}},
        "teams": [
            {
                "id": 1,
                "name": "The Oracle",
                "record": {"overall": {"wins": 1, "losses": 2}},
                "transactionCounter": {"acquisitionBudgetSpent": 19},
                "roster": {"entries": [{}, {}]},
            },
            {
                "id": 2,
                "location": "Uncle",
                "nickname": "Rico",
                "transactionCounter": {},
            },
        ],
        "transactions": [
            {
                "status": "EXECUTED",
                "type": "WAIVER",
                "teamId": 1,
                "scoringPeriodId": 3,
                "bidAmount": 12,
                "items": [
                    {"type": "ADD", "playerId": 5001},
                    {"type": "DROP", "playerId": 9999},
                ],
            },
            {
                "status": "FAILED_INVALIDPLAYERSOURCE",
                "type": "WAIVER",
                "teamId": 2,
                "bidAmount": 20,
                "items": [],
            },
        ],
    }
    teams, tx = lc.espn_context(payload, 1, REGISTRY)
    assert teams.set_index("team").loc["The Oracle", "faab_left"] == 81
    assert "Uncle Rico" in set(teams["team"])
    assert len(tx) == 1
    row = tx.iloc[0]
    assert (row["add"], row["drop"], row["bid"], row["is_me"]) == (
        "Braelon Allen (RB,22)",
        "espn:9999",
        12,
        True,
    )


def test_bid_summary_ignores_zero_and_non_waiver() -> None:
    tx = pd.DataFrame(
        {
            "type": ["waiver", "waiver", "waiver", "free_agent"],
            "bid": [0, 10, 30, None],
        },
    )
    assert lc.bid_summary(tx) == {"n": 2, "median": 20.0, "p75": 25.0, "max": 30.0}
    assert lc.bid_summary(tx.iloc[:0])["n"] == 0


def test_dynasty_roster_and_render_smoke() -> None:
    values = lc.parse_fantasycalc(FC_ROWS)
    roster = lc.dynasty_roster(["100", "300", "200"], REGISTRY, values, {"100": "taxi"})
    assert list(roster["name"]) == ["Puka Nacua", "Braelon Allen", "Drew Lock"]
    assert roster.iloc[2]["value"] == 0
    teams, tx = lc.sleeper_context(*_sleeper_fixture(), REGISTRY, "Gforceee")
    text = lc.render(
        "Mantis",
        teams,
        tx,
        budget=1000,
        my_roster=roster,
        dynasty_fas=roster,
        team_values=pd.Series({"Gforceee": 8690}),
    )
    assert "we have spent $602 (rank 1/2)" in text
    assert "<- me" in text and "Best unrostered by dynasty value" in text


def test_espn_context_falls_back_to_espn_names_and_dst() -> None:
    payload = {
        "settings": {"acquisitionSettings": {"acquisitionBudget": 100}},
        "teams": [{"id": 1, "name": "The Oracle"}],
        "players": [{"id": 4569559, "fullName": "Devaughn Vele"}],
        "transactions": [
            {
                "status": "EXECUTED",
                "type": "FREEAGENT",
                "teamId": 1,
                "scoringPeriodId": 3,
                "items": [
                    {"type": "ADD", "playerId": -16019},
                    {"type": "DROP", "playerId": -16030},
                ],
            },
            {
                "status": "EXECUTED",
                "type": "WAIVER",
                "teamId": 1,
                "scoringPeriodId": 2,
                "bidAmount": 12,
                "items": [{"type": "ADD", "playerId": 4569559}],
            },
        ],
    }
    _, tx = lc.espn_context(payload, 1, REGISTRY)
    assert list(tx["add"]) == ["D/ST -16019", "Devaughn Vele"]
    assert tx.iloc[0]["drop"] == "D/ST -16030"


def test_espn_fetch_league_passes_scoring_period(monkeypatch) -> None:
    from src import espn_league

    seen = {}

    class Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {}

    def fake_get(url, params, **kwargs):
        seen["params"] = params
        return Resp()

    monkeypatch.setattr(espn_league.requests, "get", fake_get)
    espn_league.fetch_league(
        1, 2026, views=["mTransactions2"], cookies={}, scoring_period=3
    )
    assert ("scoringPeriodId", "3") in seen["params"]
    assert ("view", "mTransactions2") in seen["params"]
