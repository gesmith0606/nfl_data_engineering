"""Tests for `espn_league.submit_lineup` — the no-browser ESPN lineup write.

The guards are the point. A lineup write is replayable in a way a waiver claim
is not: the same plan can be applied twice, from a stale board, or against the
wrong team, and ESPN will cheerfully accept moves that leave a slot
double-filled or a starter benched. Each test below pins one refusal.

`requests.post` is stubbed throughout: no test may reach ESPN, and the happy
path asserts on the body that *would* have been sent.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import espn_league  # noqa: E402
from espn_league import submit_lineup  # noqa: E402

LEAGUE, SEASON, TEAM, WEEK = 1493260, 2026, 1, 8
SWID = "{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}"


class _Resp:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {"id": "txn_1", "type": "ROSTER", "status": "EXECUTED"}

    def json(self):
        return self._payload


@pytest.fixture
def espn(monkeypatch):
    """Patch auth, league reads and the POST; capture what would be sent."""
    sent = {}

    monkeypatch.setattr(espn_league, "cookies_from_env", lambda: {"SWID": SWID, "espn_s2": "x"})
    monkeypatch.setattr(
        espn_league,
        "fetch_league",
        lambda *a, **k: {"teams": [{"id": TEAM, "owners": [SWID]}, {"id": 2, "owners": ["{OTHER}"]}]},
    )
    # Starter in QB(0), bench player in BN(20).
    monkeypatch.setattr(
        espn_league, "current_lineup_slots", lambda *a, **k: {111: 0, 222: 20, 333: 20}
    )

    def _post(url, json=None, **kwargs):
        sent["url"] = url
        sent["body"] = json
        return _Resp()

    monkeypatch.setattr(espn_league.requests, "post", _post)
    return sent


# ---------------------------------------------------------------------------
# The write itself
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_swap_posts_both_halves(self, espn):
        """A swap is two moves; posting one would leave a slot double-filled."""
        out = submit_lineup(LEAGUE, SEASON, TEAM, WEEK, [(111, 0, 20), (222, 20, 0)])

        assert out["status"] == 200
        assert out["transaction"]["id"] == "txn_1"
        body = espn["body"]
        assert body["type"] == "ROSTER"
        assert body["executionType"] == "EXECUTE"
        assert body["teamId"] == TEAM
        assert body["scoringPeriodId"] == WEEK
        assert body["memberId"] == SWID, "ESPN rejects a transaction without memberId"
        assert body["items"] == [
            {"playerId": 111, "type": "LINEUP", "fromLineupSlotId": 0, "toLineupSlotId": 20},
            {"playerId": 222, "type": "LINEUP", "fromLineupSlotId": 20, "toLineupSlotId": 0},
        ]

    def test_posts_to_the_write_host(self, espn):
        submit_lineup(LEAGUE, SEASON, TEAM, WEEK, [(222, 20, 0)])
        assert espn["url"].startswith("https://lm-api-writes.fantasy.espn.com/")
        assert f"/leagues/{LEAGUE}/transactions/" in espn["url"]

    def test_espn_error_is_surfaced_not_swallowed(self, espn, monkeypatch):
        monkeypatch.setattr(
            espn_league.requests,
            "post",
            lambda *a, **k: _Resp(400, {"messages": ["Lineup is locked"]}),
        )
        out = submit_lineup(LEAGUE, SEASON, TEAM, WEEK, [(222, 20, 0)])
        assert out["status"] == 400
        assert "locked" in out["errors"][0][1].lower()


# ---------------------------------------------------------------------------
# Guards — each one refuses before any POST
# ---------------------------------------------------------------------------


class TestGuards:
    def _refused(self, espn, *args):
        out = submit_lineup(*args)
        assert out["status"] == 0
        assert "body" not in espn, "a refused write must not POST"
        return out["errors"][0][1]

    def test_no_moves(self, espn):
        assert "no lineup moves" in self._refused(espn, LEAGUE, SEASON, TEAM, WEEK, [])

    def test_unknown_slot_id(self, espn):
        why = self._refused(espn, LEAGUE, SEASON, TEAM, WEEK, [(222, 20, 99)])
        assert "unknown lineup slot" in why and "99" in why

    def test_not_our_team(self, espn):
        why = self._refused(espn, LEAGUE, SEASON, 2, WEEK, [(222, 20, 0)])
        assert "does not own team 2" in why

    def test_player_not_on_roster(self, espn):
        why = self._refused(espn, LEAGUE, SEASON, TEAM, WEEK, [(999, 20, 0)])
        assert "not on team" in why

    def test_stale_plan_is_refused(self, espn):
        """The player has been moved since the board was built — don't guess."""
        why = self._refused(espn, LEAGUE, SEASON, TEAM, WEEK, [(222, 0, 20)])
        assert "is in slot BN" in why and "expected QB" in why

    def test_missing_swid(self, espn, monkeypatch):
        monkeypatch.setattr(espn_league, "cookies_from_env", lambda: {"espn_s2": "x"})
        why = self._refused(espn, LEAGUE, SEASON, TEAM, WEEK, [(222, 20, 0)])
        assert "ESPN_SWID" in why

    def test_one_bad_move_refuses_the_whole_batch(self, espn):
        """Partial application is worse than none: it benches without starting."""
        why = self._refused(
            espn, LEAGUE, SEASON, TEAM, WEEK, [(111, 0, 20), (999, 20, 0)]
        )
        assert "not on team" in why
