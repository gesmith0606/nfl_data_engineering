"""Tests for src/waiver_claims.py, src/waiver_sites.py glue and the two claim CLIs.

Fixtures in tests/fixtures/waiver_claims/ were recorded from the live leagues on
2026-10-09 with the same in-page snippets the tools run (read-only; nothing was
submitted). No test touches the network.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src import waiver_claims as wc
from src import waiver_sites as ws

FIX = Path(__file__).parent / "fixtures" / "waiver_claims"
REPO = Path(__file__).resolve().parent.parent
LEAGUES = ("mantis", "la_liga", "feetball")


def _fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _script(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _claims(tmp_path, text):
    path = tmp_path / "claims.yaml"
    path.write_text(text, encoding="utf-8")
    return path


ESPN = _fixture("espn_state.json")
YAHOO = _fixture("yahoo_state.json")


def _espn_index():
    return wc.index_players(wc.espn_players(ESPN["pool"], ESPN["rosters"], 1))


def _claim(add, drop=None, bid=0, priority=1, league="la_liga"):
    return wc.Claim(league, add, drop, bid, priority)


# ---------------------------------------------------------------------------
# Claims file
# ---------------------------------------------------------------------------


def test_load_claims_mapping_form_defaults_priority_per_league(tmp_path):
    path = _claims(
        tmp_path,
        "claims:\n"
        "  - {league: la_liga, add: Jaguars D/ST, drop: Commanders D/ST, bid: 1}\n"
        "  - {league: feetball, add: Bo Nix, drop: Cairo Santos, bid: 3}\n"
        "  - {league: la_liga, add: Jake Ferguson, bid: 4}\n",
    )
    claims = wc.load_claims(path, LEAGUES)
    assert [(c.league, c.priority) for c in claims] == [
        ("la_liga", 1),
        ("feetball", 1),
        ("la_liga", 2),
    ]
    assert claims[2].drop is None


def test_load_claims_list_form_and_explicit_priority(tmp_path):
    path = _claims(
        tmp_path, "- {league: mantis, add: Braelon Allen, bid: 55, priority: 3}\n"
    )
    assert wc.load_claims(path, LEAGUES) == [
        wc.Claim("mantis", "Braelon Allen", None, 55, 3)
    ]


@pytest.mark.parametrize(
    "text, msg",
    [
        ("- {league: la_liga, add: X}\n", "'bid' is required"),
        ("- {league: gentlemen, add: X, bid: 1}\n", "unknown league"),
        ("- {league: la_liga, add: X, bid: true}\n", "whole number"),
        ("- {league: la_liga, add: X, bid: 2.5}\n", "whole number"),
        ("- {league: la_liga, add: X, bid: 1, pri: 2}\n", "unknown keys"),
        ("- {league: la_liga, bid: 1}\n", "'add' is required"),
        ("[]\n", "non-empty list"),
    ],
)
def test_load_claims_rejects_bad_files(tmp_path, text, msg):
    with pytest.raises(wc.ClaimsFileError, match=msg):
        wc.load_claims(_claims(tmp_path, text), LEAGUES)


def test_keepers_file_marks_only_our_keepers():
    keep = wc.load_keepers(REPO / "data" / "draft" / "feetball_2026_keepers.txt")
    assert {"luther burden", "colston loveland"} <= keep
    assert "chase brown" not in keep  # a rival's keeper


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["Jaguars D/ST", "Jaguars", "Jaguars DEF", "jaguars d/st"]
)
def test_player_key_matches_defenses_across_sites(name):
    assert wc.player_key(name) == "jaguars"


TWINS = wc.index_players(
    [
        wc.Player("Mike Williams", "1", wc.ROSTERED, "Team A"),
        wc.Player("Mike Williams", "2", wc.WAIVERS),
    ]
)


def test_resolve_never_guesses_between_same_name_players():
    # The rostered twin may be the one George meant: claiming the waiver twin
    # instead cannot be undone, so the claim needs a pinned id.
    _, problem = wc.resolve("Mike Williams", TWINS)
    assert "matches several players" in problem and "id 1" in problem


def test_resolve_with_pinned_id_and_unknown_id():
    player, problem = wc.resolve("Mike Williams", TWINS, "2")
    assert (player.pid, player.status, problem) == ("2", wc.WAIVERS, None)
    _, problem = wc.resolve("Mike Williams", TWINS, "9")
    assert "no 'Mike Williams' with id 9" in problem


def test_resolve_requires_a_site_id():
    index = wc.index_players([wc.Player("Ghost", "", wc.WAIVERS)])
    assert "no site id" in wc.resolve("Ghost", index)[1]


def test_load_claims_reads_pinned_ids(tmp_path):
    path = _claims(
        tmp_path,
        "- {league: la_liga, add: Mike Williams, add_id: 2,\n"
        "   drop: X, drop_id: '7', bid: 1}\n",
    )
    [c] = wc.load_claims(path, LEAGUES)
    assert (c.add_id, c.drop_id) == ("2", "7")


@pytest.mark.parametrize(
    "name, query",
    [
        ("Jaguars D/ST", "Jaguars"),
        ("Jets DEF", "Jets"),
        ("Luther Burden III", "Luther Burden III"),
    ],
)
def test_search_name_strips_defense_suffixes(name, query):
    assert wc.search_name(name) == query


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------


def test_espn_claim_records_dedupe_and_join_outcomes():
    records = wc.espn_claim_records(ESPN["transactions"], 1, ESPN["names"])
    # 10 rows (period 5 + the period-6 repeat, other teams' outcomes) -> our 2 claims
    assert [(r.add, r.drop, r.status) for r in records] == [
        ("Jaguars D/ST", "Bears D/ST", "FAILED_INVALIDPLAYERSOURCE"),
        ("Commanders D/ST", "Bears D/ST", "EXECUTED"),
    ]


def test_espn_claim_is_pending_until_a_process_or_cancel_record_points_back():
    claims = [t for t in ESPN["transactions"] if t["executionType"] == "EXECUTE"]
    cancel = dict(
        claims[0],
        id="c1",
        executionType="CANCEL",
        status="CANCELED",
        relatedTransactionId="bef17292",
    )
    records = wc.espn_claim_records(claims + [cancel], 1, ESPN["names"])
    assert [r.status for r in records] == ["CANCELED", "PENDING"]


def test_espn_name_falls_back_to_team_abbr_for_defenses():
    assert wc.espn_name(-16030, {}) == "JAX D/ST"
    assert wc.espn_name(123, {}) == "espn:123"


def test_espn_claim_body_waiver_and_free_agent():
    body = wc.espn_claim_body(1, 5, "4242355", "-16003", 4)
    assert body["type"] == "WAIVER" and body["executionType"] == "EXECUTE"
    assert (
        body["bidAmount"] == 4 and body["scoringPeriodId"] == 5 and body["teamId"] == 1
    )
    assert [
        (i["type"], i["playerId"], i["fromTeamId"], i["toTeamId"])
        for i in body["items"]
    ] == [
        ("ADD", 4242355, 0, 1),
        ("DROP", -16003, 1, 0),
    ]
    assert "memberId" not in body  # added inside the browser only
    fa = wc.espn_claim_body(1, 5, "3917315", None, 9, free_agent=True)
    assert (fa["type"], fa["bidAmount"], len(fa["items"])) == ("FREEAGENT", 0, 1)


def test_check_league_espn_accepts_a_valid_waiver_claim():
    [c] = wc.check_league(
        [_claim("Jake Ferguson", "Keenan Allen", bid=4)], _espn_index(), 80
    )
    assert (
        c.ok and c.kind == "WAIVER" and (c.add.pid, c.drop.pid) == ("4242355", "15818")
    )


@pytest.mark.parametrize(
    "claim, problem",
    [
        (
            _claim("Saquon Barkley", "Keenan Allen"),
            "not available (rostered: Love, Hurts)",
        ),
        (_claim("Braelon Allen", "Keenan Allen"), "not available (mine)"),
        (_claim("Nobody Atall", "Keenan Allen"), "not found"),
        (
            _claim("Jake Ferguson", "Chase Brown"),
            "not on our roster (rostered: Love, Hurts)",
        ),
        (
            _claim("Jake Ferguson", "Keenan Allen", bid=81),
            "exceeds the FAAB left ($80)",
        ),
        (_claim("Jake Ferguson", "Keenan Allen", bid=-1), "below the league minimum"),
    ],
)
def test_check_league_espn_blocks(claim, problem):
    [c] = wc.check_league([claim], _espn_index(), 80)
    assert not c.ok and any(problem in p for p in c.problems), c.problems


def test_check_league_free_agent_needs_explicit_opt_in():
    claim = [_claim("Kyler Murray", "Keenan Allen", bid=3)]
    [c] = wc.check_league(claim, _espn_index(), 80)
    assert not c.ok and "--allow-free-agent" in c.problems[0]
    [c] = wc.check_league(claim, _espn_index(), 80, allow_free_agent=True)
    assert c.ok and c.kind == "FREE AGENT"
    assert "IMMEDIATELY" in c.warnings[0] and "$3 bid is ignored" in c.warnings[0]


def test_check_league_blocks_a_claim_already_pending_on_the_site():
    pending = [wc.ClaimRecord("la_liga", "Jake Ferguson", "Keenan Allen", 4, "PENDING")]
    claim = [_claim("Jake Ferguson", "Mike Evans", bid=5)]
    [c] = wc.check_league(claim, _espn_index(), 80, pending=pending)
    assert any("already pending" in p for p in c.problems)
    done = [dataclasses.replace(pending[0], status="FAILED_INVALIDPLAYERSOURCE")]
    assert wc.check_league(claim, _espn_index(), 80, pending=done)[0].ok


def test_check_league_warns_shared_drop_and_unknown_budget():
    claims = [
        _claim("Jake Ferguson", "Mike Evans", priority=1),
        _claim("Makai Lemon", "Mike Evans", priority=2),
    ]
    first, second = wc.check_league(claims, _espn_index(), None)
    assert first.ok and second.ok
    assert any("share the drop Mike Evans" in w for w in first.warnings)
    assert any("FAAB left unknown" in w for w in first.warnings)


def test_check_league_batch_rules():
    claims = [
        _claim("Jake Ferguson", "Keenan Allen", bid=50, priority=1),
        _claim("Jake Ferguson", "Mike Evans", bid=10, priority=2),
        _claim("Makai Lemon", "Mike Evans", bid=30, priority=2),
    ]
    checked = wc.check_league(claims, _espn_index(), 80)
    assert checked[0].ok
    assert any("claimed twice" in p for p in checked[1].problems)
    assert any("priority 2 is used twice" in p for p in checked[2].problems)
    assert any("bids total $90 > FAAB left $80" in w for w in checked[2].warnings)


def test_check_league_alternative_claims_may_share_a_drop():
    claims = [
        _claim("Jaguars D/ST", "Commanders D/ST", priority=1),
        _claim("Eagles D/ST", "Commanders D/ST", priority=2),
    ]
    index = wc.index_players(
        wc.espn_players(
            ESPN["pool"] + [[-16030, "Jaguars D/ST", "WAIVERS"]], ESPN["rosters"], 1
        )
    )
    checked = wc.check_league(claims, index, 80, allow_free_agent=True)
    assert all(c.ok for c in checked)
    assert "share the drop Commanders D/ST" in " ".join(checked[0].warnings)


# ---------------------------------------------------------------------------
# Yahoo
# ---------------------------------------------------------------------------


def _yahoo_index():
    return wc.index_players(wc.yahoo_players(YAHOO["search"]))


def test_yahoo_players_read_roster_status():
    status = {p.name: (p.status, p.owner) for p in wc.yahoo_players(YAHOO["search"])}
    assert status["Bo Nix"] == (wc.WAIVERS, "")
    assert status["Jordan Love"] == (wc.FREE_AGENT, "")
    assert status["Cairo Santos"] == (wc.MINE, "")
    assert status["Saquon Barkley"] == (wc.ROSTERED, "Josh Jacobs Gently Jabs")


def test_yahoo_keeper_is_never_a_drop():
    keep = wc.load_keepers(REPO / "data" / "draft" / "feetball_2026_keepers.txt")
    [c] = wc.check_league(
        [_claim("Bo Nix", "Luther Burden III", 3, league="feetball")],
        _yahoo_index(),
        82,
        keep,
    )
    assert any("KEEPER" in p for p in c.problems)


def test_yahoo_form_accepts_waiver_claim_form():
    [c] = wc.check_league(
        [_claim("Bo Nix", "Cairo Santos", 3, league="feetball")], _yahoo_index(), 82
    )
    assert c.ok
    assert (
        wc.yahoo_form_problems(
            _fixture("yahoo_form_waiver.json"), c.add, c.drop, "/f1/658684/10"
        )
        == []
    )


def test_yahoo_form_refuses_immediate_add_for_a_waiver_player():
    [c] = wc.check_league(
        [_claim("Bo Nix", "Cairo Santos", 3, league="feetball")], _yahoo_index(), 82
    )
    problems = wc.yahoo_form_problems(
        _fixture("yahoo_form_free_agent.json"), c.add, c.drop, "/f1/658684/10"
    )
    assert problems and "would not file a waiver claim" in problems[0]


def test_yahoo_form_needs_the_drop_among_its_options_and_a_drop_when_full():
    form = _fixture("yahoo_form_waiver.json")
    add = wc.Player("Bo Nix", "40875", wc.WAIVERS)
    assert (
        "not a drop option"
        in wc.yahoo_form_problems(
            form, add, wc.Player("X", "999", wc.MINE), "/f1/658684/10"
        )[0]
    )
    assert (
        "a drop is required"
        in wc.yahoo_form_problems(form, add, None, "/f1/658684/10")[0]
    )
    assert (
        "unavailable"
        in wc.yahoo_form_problems(
            {"found": False, "error": "x"}, add, None, "/f1/658684/10"
        )[0]
    )
    wrong_name = wc.Player("Somebody Else", "28227", wc.MINE)
    assert (
        "is 'Cairo Santos'"
        in wc.yahoo_form_problems(form, add, wrong_name, "/f1/658684/10")[0]
    )
    other_team = wc.yahoo_form_problems(form, add, None, "/f1/658684/3")
    assert any("not /f1/658684/3" in p for p in other_team)


def test_yahoo_claim_records_trade_and_best_effort_claim():
    items = YAHOO["pending"] + [
        {
            "path": "/f1/658684/10/x",
            "text": "Waiver claim: Add Bo Nix Drop Cairo Santos $3 Edit",
        }
    ]
    trade, claim = wc.yahoo_claim_records(items)
    assert trade.status == "TRADE" and "Crazy Eddie" in trade.note
    assert (claim.status, claim.add, claim.drop, claim.bid) == (
        "PENDING",
        "Bo Nix",
        "Cairo Santos",
        3,
    )
    assert wc.is_pending_for(claim, "Bo Nix")
    raw = wc.ClaimRecord(
        "feetball", "", "", None, "PENDING", note="Pending claim for Bo Nix (W)"
    )
    assert wc.is_pending_for(raw, "Bo Nix") and not wc.is_pending_for(
        raw, "Jordan Love"
    )


# ---------------------------------------------------------------------------
# Sleeper
# ---------------------------------------------------------------------------

REGISTRY = {
    "11630": {
        "full_name": "Roman Wilson",
        "position": "WR",
        "team": "PIT",
        "active": True,
    },
    "4039": {
        "full_name": "Cooper Kupp",
        "position": "WR",
        "team": "SEA",
        "active": True,
    },
    "4993": {
        "full_name": "Mike Gesicki",
        "position": "TE",
        "team": "CIN",
        "active": True,
    },
    "9999": {
        "full_name": "Braelon Allen",
        "position": "RB",
        "team": "NYJ",
        "active": True,
    },
    "1": {"full_name": "Old Namesake", "position": "RB", "team": None, "active": False},
    "2": {"full_name": "Kicker Guy", "position": "OL", "team": "NYJ", "active": True},
}
ROSTERS = [
    {"roster_id": 6, "players": ["4039"]},
    {"roster_id": 7, "players": ["11630"]},
]


def test_sleeper_players_statuses():
    players = {
        p.name: p for p in wc.sleeper_players(REGISTRY, ROSTERS, {7: "Jiddler"}, 6)
    }
    assert players["Cooper Kupp"].status == wc.MINE
    assert (players["Roman Wilson"].status, players["Roman Wilson"].owner) == (
        wc.ROSTERED,
        "Jiddler",
    )
    assert players["Braelon Allen"].status == wc.AVAILABLE
    assert "Old Namesake" not in players and "Kicker Guy" not in players
    [c] = wc.check_league(
        [_claim("Braelon Allen", "Cooper Kupp", 55, league="mantis")],
        wc.index_players(players.values()),
        398,
    )
    assert c.ok and c.kind == "WAIVER/FA"


def test_sleeper_claim_records_from_recorded_leg():
    txns = {5: _fixture("sleeper_transactions_leg5.json")}
    [r] = wc.sleeper_claim_records(txns, 7, REGISTRY)
    assert (r.add, r.drop, r.bid, r.status) == (
        "Roman Wilson",
        "Cooper Kupp",
        150,
        "COMPLETE",
    )
    failed, won = wc.sleeper_claim_records(txns, 9, REGISTRY)
    assert {failed.status, won.status} == {"FAILED", "COMPLETE"}
    assert wc.sleeper_claim_records(txns, 6, REGISTRY) == []


# ---------------------------------------------------------------------------
# Rendering + site glue
# ---------------------------------------------------------------------------


def test_render_checked_lists_problems_and_warnings():
    checked = wc.check_league(
        [
            _claim("Saquon Barkley", "Keenan Allen", priority=1),
            _claim("Kyler Murray", "Mike Evans", priority=2),
        ],
        _espn_index(),
        80,
        allow_free_agent=True,
    )
    text = wc.render_checked(checked)
    assert "BLOCKED" in text and "OK" in text
    assert "x la_liga #1:" in text and "! la_liga #2:" in text


class _FakePage:
    def __init__(self, value):
        self.value, self.calls = value, []

    def evaluate(self, expression, await_promise=False, timeout=15.0):
        self.calls.append(expression)
        return self.value


def test_run_js_substitutes_args_and_parses_json():
    page = _FakePage(json.dumps({"ok": True}))
    assert ws.run_js(page, "(async (A) => A)(__ARGS__)", {"lid": "1"}) == {"ok": True}
    assert page.calls == ['(async (A) => A)({"lid": "1"})']


def test_snippets_take_exactly_one_argument_and_form_reader_stops_before_posting():
    for js in (
        ws.ESPN_STATE_JS,
        ws.ESPN_SUBMIT_JS,
        ws.YAHOO_STATE_JS,
        ws.YAHOO_FORM_JS,
    ):
        assert js.count("__ARGS__") == 1
    form = ws.YAHOO_FORM_JS
    assert form.index("if (!A.submit) return") < form.index("method: 'POST'")
    assert "crumb" not in ws.YAHOO_STATE_JS and "memberId" not in ws.ESPN_STATE_JS


# ---------------------------------------------------------------------------
# CLIs (site I/O monkeypatched)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_sites(monkeypatch):
    calls = {"espn_submit": [], "yahoo_submit": [], "read": []}
    monkeypatch.setattr(ws, "site_page", lambda platform, *a, **k: _FakePage(platform))
    monkeypatch.setattr(ws, "espn_state", lambda *a, **k: ESPN)
    monkeypatch.setattr(ws, "yahoo_state", lambda *a, **k: YAHOO)

    def yahoo_form(page, lid, team, apid, dpid, bid, submit=False, expect_claim=True):
        if submit:
            calls["yahoo_submit"].append((team, apid, dpid, bid, expect_claim))
            return {
                **_fixture("yahoo_form_waiver.json"),
                "posted": {
                    "status": 200,
                    "path": "/f1/658684/10",
                    "messages": [],
                    "form_again": False,
                },
            }
        return _fixture("yahoo_form_waiver.json")

    def espn_submit(page, season, lid, body):
        calls["espn_submit"].append(body)
        return {"status": 200, "transaction": {"id": "new", "status": "PENDING"}}

    def read_claims(league, preset, season, cdp_url=None, registry=None):
        calls["read"].append(league)
        records = [
            wc.ClaimRecord(league, "Jake Ferguson", "Keenan Allen", 4, "PENDING")
        ]
        if league == "feetball":
            records = [
                wc.ClaimRecord(
                    league,
                    "",
                    "",
                    None,
                    "PENDING",
                    note="Add Bo Nix Drop Cairo Santos $3",
                )
            ]
        return "summary", records

    monkeypatch.setattr(ws, "yahoo_form", yahoo_form)
    monkeypatch.setattr(ws, "espn_submit", espn_submit)
    monkeypatch.setattr(ws, "read_claims", read_claims)
    sub = _script("submit_claims")
    monkeypatch.setattr(sub, "READ_BACK_WAIT_S", (0,))
    return sub, calls


VALID = (
    "claims:\n"
    "  - {league: la_liga, add: Jake Ferguson, drop: Keenan Allen, bid: 4}\n"
    "  - {league: feetball, add: Bo Nix, drop: Cairo Santos, bid: 3}\n"
)


def test_submit_claims_dry_run_submits_nothing(fake_sites, tmp_path, capsys):
    sub, calls = fake_sites
    assert sub.main(["--claims", str(_claims(tmp_path, VALID))]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "--submit" in out
    assert calls["espn_submit"] == [] and calls["yahoo_submit"] == []


def test_submit_claims_blocked_file_submits_nothing_even_with_flag(
    fake_sites, tmp_path, capsys
):
    sub, calls = fake_sites
    text = (
        VALID
        + "  - {league: feetball, add: Jordan Love, drop: Luther Burden III, bid: 0}\n"
    )
    assert sub.main(["--claims", str(_claims(tmp_path, text)), "--submit"]) == 1
    out = capsys.readouterr().out
    assert "KEEPER" in out and "BLOCKED" in out
    assert calls["espn_submit"] == [] and calls["yahoo_submit"] == []


def test_submit_claims_submit_files_and_reads_back(fake_sites, tmp_path, capsys):
    sub, calls = fake_sites
    assert sub.main(["--claims", str(_claims(tmp_path, VALID)), "--submit"]) == 0
    [body] = calls["espn_submit"]
    assert (body["type"], body["bidAmount"], body["scoringPeriodId"]) == (
        "WAIVER",
        4,
        5,
    )
    assert calls["yahoo_submit"] == [(10, "40875", "28227", 3, True)]
    out = capsys.readouterr().out
    assert out.count("CONFIRMED") == 2 and "NOT FOUND" not in out
    assert set(calls["read"]) == {"la_liga", "feetball"}


def test_submit_claims_stops_without_retry_on_unclear_outcome(
    fake_sites, monkeypatch, tmp_path, capsys
):
    sub, calls = fake_sites

    def boom(*a, **k):
        raise TimeoutError("websocket timed out")

    monkeypatch.setattr(ws, "espn_submit", boom)
    assert sub.main(["--claims", str(_claims(tmp_path, VALID)), "--submit"]) == 2
    out = capsys.readouterr().out
    assert "outcome UNKNOWN" in out and "not retrying" in out
    assert calls["yahoo_submit"] == []  # nothing after the unclear claim


def test_submit_claims_never_submits_mantis(fake_sites, monkeypatch, tmp_path, capsys):
    sub, calls = fake_sites
    monkeypatch.setattr(
        ws,
        "sleeper_state",
        lambda *a, **k: {
            "rosters": ROSTERS,
            "owners": {7: "Jiddler"},
            "my_roster_id": 6,
            "faab_left": 398,
        },
    )
    import src.sleeper_player_map as spm

    monkeypatch.setattr(spm, "load_sleeper_players", lambda **k: REGISTRY)
    text = "- {league: mantis, add: Braelon Allen, drop: Cooper Kupp, bid: 55}\n"
    assert sub.main(["--claims", str(_claims(tmp_path, text)), "--submit"]) == 0
    out = capsys.readouterr().out
    assert (
        "enter in the Sleeper app" in out
        and "claim Braelon Allen for $55, drop Cooper Kupp" in out
    )
    assert "No ESPN/Yahoo claims to submit" in out
    assert calls["espn_submit"] == [] and calls["yahoo_submit"] == []


def test_check_pending_claims_prints_each_league(fake_sites, monkeypatch, capsys):
    chk = _script("check_pending_claims")
    assert chk.main(["--league", "all"]) == 0
    out = capsys.readouterr().out
    assert "== mantis" in out and "== la_liga" in out and "== feetball" in out

    def unreachable(*a, **k):
        raise LookupError("Chrome DevTools not reachable")

    monkeypatch.setattr(ws, "read_claims", unreachable)
    assert chk.main(["--league", "la_liga"]) == 1
    assert "UNAVAILABLE: Chrome DevTools not reachable" in capsys.readouterr().out


def test_site_page_explains_a_chrome_without_devtools_http(monkeypatch):
    import requests

    class _Resp:
        status_code = 404

        def json(self):
            raise ValueError("not json")

        def raise_for_status(self):
            raise requests.HTTPError("404 Client Error: Not Found")

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
    with pytest.raises(LookupError, match="--remote-debugging-port=<port>"):
        ws.site_page("espn", "1493260", 1, "http://127.0.0.1:9222")


# ---------------------------------------------------------------------------
# Review fixes: re-runs, unclear outcomes, keepers, read-back exit code
# ---------------------------------------------------------------------------


def test_keepers_file_missing_blocks_the_league(
    fake_sites, monkeypatch, tmp_path, capsys
):
    sub, calls = fake_sites
    from src import config

    preset = dict(config.LEAGUE_PRESETS["feetball"], keepers_file="data/draft/nope.txt")
    monkeypatch.setitem(config.LEAGUE_PRESETS, "feetball", preset)
    assert sub.main(["--claims", str(_claims(tmp_path, VALID)), "--submit"]) == 1
    out = capsys.readouterr().out
    assert "keepers file data/draft/nope.txt is missing" in out
    assert calls["espn_submit"] == [] and calls["yahoo_submit"] == []


def test_unreadable_league_blocks_submit(fake_sites, monkeypatch, tmp_path, capsys):
    sub, calls = fake_sites

    def down(*a, **k):
        raise LookupError("no Chrome DevTools endpoint")

    monkeypatch.setattr(ws, "yahoo_state", down)
    assert sub.main(["--claims", str(_claims(tmp_path, VALID)), "--submit"]) == 1
    assert (
        "feetball: could not check - no Chrome DevTools endpoint"
        in capsys.readouterr().out
    )
    assert calls["espn_submit"] == []


def test_rerun_after_success_is_blocked_by_the_pending_claim(
    fake_sites, monkeypatch, tmp_path, capsys
):
    sub, calls = fake_sites
    pending = {
        "id": "new1",
        "type": "WAIVER",
        "status": "PENDING",
        "executionType": "EXECUTE",
        "teamId": 1,
        "bidAmount": 4,
        "relatedTransactionId": None,
        "proposedDate": 1,
        "scoringPeriodId": 5,
        "items": [{"type": "ADD", "playerId": 4242355}],
    }
    monkeypatch.setattr(
        ws,
        "espn_state",
        lambda *a, **k: {**ESPN, "transactions": ESPN["transactions"] + [pending]},
    )
    assert sub.main(["--claims", str(_claims(tmp_path, VALID)), "--submit"]) == 1
    assert "already pending" in capsys.readouterr().out
    assert calls["espn_submit"] == [] and calls["yahoo_submit"] == []


def test_espn_5xx_stops_the_run_and_lists_what_was_not_attempted(
    fake_sites, monkeypatch, tmp_path, capsys
):
    sub, calls = fake_sites
    monkeypatch.setattr(ws, "espn_submit", lambda *a, **k: {"status": 503})
    assert sub.main(["--claims", str(_claims(tmp_path, VALID)), "--submit"]) == 2
    out = capsys.readouterr().out
    assert "outcome UNKNOWN" in out and "NOT ATTEMPTED: feetball #1 Bo Nix" in out
    assert calls["yahoo_submit"] == []


def test_espn_refusal_is_failed_and_the_run_continues(
    fake_sites, monkeypatch, tmp_path, capsys
):
    sub, calls = fake_sites
    monkeypatch.setattr(
        ws,
        "espn_submit",
        lambda *a, **k: {
            "status": 0,
            "errors": [
                ["not submitted", "the logged-in ESPN account does not own team 1"]
            ],
        },
    )
    assert sub.main(["--claims", str(_claims(tmp_path, VALID)), "--submit"]) == 2
    out = capsys.readouterr().out
    assert "FAILED la_liga #1 Jake Ferguson: HTTP 0 not submitted" in out
    assert len(calls["yahoo_submit"]) == 1


@pytest.mark.parametrize(
    "posted, verdict",
    [
        (
            {
                "status": 200,
                "path": "/f1/658684/10",
                "messages": [],
                "form_again": True,
            },
            "UNKNOWN",
        ),
        ({"status": 500, "path": "/x", "messages": []}, "UNKNOWN"),
        ({"status": 403, "path": "/x", "messages": ["denied"]}, "FAILED"),
        (None, "FAILED"),
    ],
)
def test_yahoo_submit_outcomes(fake_sites, monkeypatch, posted, verdict):
    sub, _ = fake_sites
    monkeypatch.setattr(
        ws,
        "yahoo_form",
        lambda *a, **k: {"found": True, "posted": posted, "error": "stopped"},
    )
    c = wc.CheckedClaim(
        _claim("Bo Nix", "Cairo Santos", 3, league="feetball"),
        wc.Player("Bo Nix", "40875", wc.WAIVERS),
        wc.Player("Cairo Santos", "28227", wc.MINE),
    )
    assert sub.submit_one("feetball", c, {"page": None}, 2026)[0] == verdict


def test_read_back_not_found_exits_2(fake_sites, monkeypatch, tmp_path, capsys):
    sub, _ = fake_sites
    monkeypatch.setattr(ws, "read_claims", lambda *a, **k: ("summary", []))
    assert sub.main(["--claims", str(_claims(tmp_path, VALID)), "--submit"]) == 2
    assert capsys.readouterr().out.count("NOT FOUND") == 2


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_snippets_are_valid_javascript(tmp_path):
    args = {
        "season": 2026,
        "lid": "1",
        "team": 1,
        "names": ["A"],
        "body": {},
        "apid": "1",
        "dpid": "",
        "faab": 0,
        "submit": False,
        "expect_claim": True,
    }
    for i, js in enumerate(
        (ws.ESPN_STATE_JS, ws.ESPN_SUBMIT_JS, ws.YAHOO_STATE_JS, ws.YAHOO_FORM_JS)
    ):
        path = tmp_path / f"s{i}.js"
        path.write_text(js.replace("__ARGS__", json.dumps(args)), encoding="utf-8")
        res = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True
        )
        assert res.returncode == 0, res.stderr


def test_yahoo_form_snippet_rechecks_team_and_claim_before_posting():
    js = ws.YAHOO_FORM_JS
    post = js.index("method: 'POST'")
    assert js.index("out.action !== `/f1/${A.lid}/${A.team}/addplayer`") < post
    assert js.index("A.expect_claim && !(out.faab") < post
    submit = ws.ESPN_SUBMIT_JS
    assert submit.index("does not own team") < submit.index("method: 'POST'")
