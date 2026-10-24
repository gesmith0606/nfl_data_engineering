"""Tests for espn_league.submit_transaction — ESPN writes with no browser.

George, 2026-10-23: "chrome should not be the transport." Reads already went
over `requests` with the ESPN_S2/ESPN_SWID cookies; only writes went through
an in-page fetch, which was a safety choice rather than a necessity.

Every guard the in-page version enforced is tested here, because each exists
to stop a specific way of filing the WRONG claim — and a transport change that
quietly dropped one would be worse than the browser it replaces.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from src import espn_league

BODY = {
    "teamId": 1,
    "scoringPeriodId": 7,
    "items": [{"type": "ADD", "playerId": 4242}],
}
COOKIES = {"espn_s2": "s2", "SWID": "{ABC-123}"}


def _patch(monkeypatch, *, owners=("{ABC-123}",), status="WAIVERS", posted=None):
    """Stub the league read, the player re-check, and the POST."""
    monkeypatch.setattr(
        espn_league,
        "fetch_league",
        lambda *a, **k: {"teams": [{"id": 1, "owners": list(owners)}]},
    )
    monkeypatch.setattr(espn_league, "_player_status", lambda *a, **k: status)

    class Resp:
        status_code = 200
        ok = True

        def json(self) -> Dict[str, Any]:
            return {"id": "tx1", "type": "WAIVER", "status": "PENDING", "bidAmount": 7}

    def fake_post(url, **kw):
        if posted is not None:
            posted.append((url, kw.get("json")))
        return Resp()

    monkeypatch.setattr(espn_league.requests, "post", fake_post)


def test_a_successful_claim_posts_the_body_with_the_member_id(monkeypatch):
    posted: list = []
    _patch(monkeypatch, posted=posted)
    out = espn_league.submit_transaction(99, 2026, BODY, "WAIVERS", cookies=COOKIES)
    assert out["status"] == 200
    assert out["transaction"]["id"] == "tx1"
    ((url, body),) = posted
    assert url.startswith("https://lm-api-writes.fantasy.espn.com/")
    # ESPN rejects a transaction with no memberId; it comes from the SWID.
    assert body["memberId"] == "{ABC-123}"


def test_no_swid_refuses_before_any_request(monkeypatch):
    posted: list = []
    _patch(monkeypatch, posted=posted)
    out = espn_league.submit_transaction(
        99, 2026, BODY, "WAIVERS", cookies={"espn_s2": "s2"}
    )
    assert out["status"] == 0 and "ESPN_SWID" in out["errors"][0][1]
    assert posted == [], "must not POST without a member id"


def test_filing_into_a_team_we_do_not_own_is_refused(monkeypatch):
    """The worst available failure: a claim into someone else's roster."""
    posted: list = []
    _patch(monkeypatch, owners=("{SOMEONE-ELSE}",), posted=posted)
    out = espn_league.submit_transaction(99, 2026, BODY, "WAIVERS", cookies=COOKIES)
    assert out["status"] == 0
    assert "does not own team 1" in out["errors"][0][1]
    assert posted == []


def test_a_player_whose_status_changed_since_the_dry_run_is_refused(monkeypatch):
    """Someone claimed him between the table and the submit."""
    posted: list = []
    _patch(monkeypatch, status="ONTEAM", posted=posted)
    out = espn_league.submit_transaction(99, 2026, BODY, "WAIVERS", cookies=COOKIES)
    assert out["status"] == 0
    assert "is now ONTEAM, expected WAIVERS" in out["errors"][0][1]
    assert posted == []


def test_a_player_no_longer_listed_is_refused(monkeypatch):
    posted: list = []
    _patch(monkeypatch, status=None, posted=posted)
    out = espn_league.submit_transaction(99, 2026, BODY, "WAIVERS", cookies=COOKIES)
    assert out["status"] == 0
    assert "no longer available" in out["errors"][0][1]
    assert posted == []


def test_a_claim_with_no_add_item_is_refused(monkeypatch):
    posted: list = []
    _patch(monkeypatch, posted=posted)
    out = espn_league.submit_transaction(
        99,
        2026,
        {**BODY, "items": [{"type": "DROP", "playerId": 1}]},
        "WAIVERS",
        cookies=COOKIES,
    )
    assert out["status"] == 0 and "no ADD item" in out["errors"][0][1]
    assert posted == []


def test_member_guids_are_scrubbed_out_of_espn_error_text(monkeypatch):
    """ESPN echoes the member GUID back; it must not reach a log or a report."""
    _patch(monkeypatch)

    class Resp:
        status_code = 400
        ok = False

        def json(self):
            return {"messages": ["bad member {1A2B3C4D-5E6F-7A8B-9C0D-1E2F3A4B5C6D}"]}

    monkeypatch.setattr(espn_league.requests, "post", lambda url, **kw: Resp())
    out = espn_league.submit_transaction(99, 2026, BODY, "WAIVERS", cookies=COOKIES)
    assert out["status"] == 400
    assert "{id}" in out["errors"][0][1]
    assert "1A2B3C4D" not in out["errors"][0][1]


def test_a_network_failure_propagates_so_the_caller_re_reads(monkeypatch):
    """A POST that timed out may still have applied; it must never be retried."""
    import requests as rq

    _patch(monkeypatch)
    monkeypatch.setattr(
        espn_league.requests,
        "post",
        lambda url, **kw: (_ for _ in ()).throw(rq.Timeout("boom")),
    )
    with pytest.raises(rq.RequestException):
        espn_league.submit_transaction(99, 2026, BODY, "WAIVERS", cookies=COOKIES)


def test_submit_claims_can_choose_the_http_transport():
    """A function nothing calls cannot earn its promotion.

    `submit_transaction` existed with no caller, so there was no way to prove
    it on a real claim — which was the stated condition for it replacing the
    browser. `--espn-http` makes it reachable while leaving the default alone.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent / "scripts" / "submit_claims.py"
    ).read_text(encoding="utf-8")

    assert '"--espn-http"' in src, "the transport must be selectable"
    assert (
        'ctx[league]["espn_http"]' in src
    ), "and the choice must reach the submit site"
    assert 'if ctx.get("espn_http"):' in src
    assert "espn_league.submit_transaction(" in src
    # The browser remains the default: this moves money-equivalent state and
    # has only been exercised against stubs.
    assert "else:\n            res = ws.espn_submit(" in src
    # Both transports return the same shape, so nothing downstream changes.
    after = src[src.index('if ctx.get("espn_http"):') :]
    assert after.index("status = _status(res)") > 0
