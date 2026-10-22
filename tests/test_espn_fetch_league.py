"""Unit tests for waiver_sites.espn_fetch_league.

league_context's bid summary needs transactions from every scoring period —
mTransactions2 without a scoringPeriodId returns only the current period's
lineup moves. Reading that through the claims profile means league context
works without a second set of ESPN credentials in .env.
"""

from __future__ import annotations

import json

from src import waiver_sites as ws


class FakePage:
    """Captures the evaluated snippet instead of running it."""

    def __init__(self, payload):
        self.payload = payload
        self.scripts = []

    def evaluate(self, script, await_promise=False, timeout=None):
        self.scripts.append(script)
        return json.dumps(self.payload)

    @property
    def args(self):
        """The JSON argument object the last snippet was built with."""
        script = self.scripts[-1]
        start = script.index("})(") + 3
        return json.loads(script[start : script.rindex(")")])


def test_returns_decoded_payload():
    page = FakePage({"teams": [{"id": 1}], "scoringPeriodId": 7})
    out = ws.espn_fetch_league(page, 2026, "1493260", ["mSettings"])
    assert out["scoringPeriodId"] == 7


def test_args_carry_season_league_and_views():
    page = FakePage({})
    ws.espn_fetch_league(page, 2026, "1493260", ["mSettings", "mTeam"])
    a = page.args
    assert a["season"] == 2026
    assert a["lid"] == 1493260
    assert a["views"] == ["mSettings", "mTeam"]


def test_scoring_period_defaults_to_null():
    """A league read must not be pinned to a period; a transaction read must."""
    page = FakePage({})
    ws.espn_fetch_league(page, 2026, "1493260", ["mSettings"])
    assert page.args["scoring_period"] is None

    ws.espn_fetch_league(page, 2026, "1493260", ["mTransactions2"], 5)
    assert page.args["scoring_period"] == 5


def test_league_id_accepts_str_or_int():
    page = FakePage({})
    ws.espn_fetch_league(page, 2026, 1493260, ["mTeam"])
    assert page.args["lid"] == 1493260


def test_snippet_sends_cookies_and_raises_on_http_error():
    """Same-origin credentials are what make the profile's login count."""
    assert "credentials: 'include'" in ws.ESPN_FETCH_JS
    assert "ESPN HTTP" in ws.ESPN_FETCH_JS


def test_exported():
    assert "espn_fetch_league" in ws.__all__
