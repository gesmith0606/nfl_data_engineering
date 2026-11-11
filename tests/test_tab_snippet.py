"""tab_snippet.py: the Chrome-tab route reuses the guarded snippets, not new JS."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.tab_snippet as ts  # noqa: E402


def _args_of(js: str) -> dict:
    return json.loads(js.rsplit("})(", 1)[1].rstrip(")"))


def test_espn_snippet_is_the_guarded_submit_with_our_team_and_waiver_body():
    js = ts.espn_js("4432577", "4242512", 3, week=10)
    assert js.startswith("await ")
    assert "does not own team" in js  # ownership guard kept
    a = _args_of(js)
    assert a["expect"] == "WAIVERS"
    body = a["body"]
    assert body["type"] == "WAIVER" and body["bidAmount"] == 3
    assert body["scoringPeriodId"] == 10
    assert [i["type"] for i in body["items"]] == ["ADD", "DROP"]
    assert "memberId" not in body  # SWID is added inside the browser only


def test_yahoo_snippet_checks_the_form_target_and_claim():
    js = ts.yahoo_js("41825", "30973", 2)
    assert "not to our team" in js and "no longer offers a waiver claim" in js
    a = _args_of(js)
    assert a == {
        "lid": a["lid"],
        "team": a["team"],
        "apid": "41825",
        "dpid": "30973",
        "faab": 2,
        "submit": True,
        "expect_claim": True,
    }


def test_check_only_never_writes_a_posting_row(tmp_path, monkeypatch, capsys):
    led = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(ts, "LEDGER", led)
    ts.main(
        [
            "yahoo",
            "--add",
            "Tyler Shough",
            "--add-id",
            "41825",
            "--bid",
            "2",
            "--check-only",
        ]
    )
    assert not led.exists() or led.read_text() == ""
    assert '"submit": false' in capsys.readouterr().out


def test_espn_print_logs_posting_then_record_logs_outcome(tmp_path, monkeypatch):
    led = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(ts, "LEDGER", led)
    ts.main(
        [
            "espn",
            "--add",
            "C.J. Stroud",
            "--add-id",
            "4432577",
            "--drop",
            "Malik Willis",
            "--drop-id",
            "4242512",
            "--bid",
            "3",
            "--week",
            "10",
        ]
    )
    ts.main(
        [
            "record",
            "--league",
            "la_liga",
            "--add",
            "C.J. Stroud",
            "--bid",
            "3",
            "--verdict",
            "PENDING",
        ]
    )
    rows = [json.loads(x) for x in led.read_text().splitlines()]
    assert [r["verdict"] for r in rows] == ["POSTING", "PENDING"]
    assert rows[0]["league"] == "la_liga" and rows[0]["bid"] == 3


def _espn(*extra):
    return [
        "espn",
        "--add",
        "C.J. Stroud",
        "--add-id",
        "4432577",
        "--drop",
        "Malik Willis",
        "--drop-id",
        "4242512",
        "--bid",
        "3",
        "--week",
        "10",
        *extra,
    ]


def test_second_filing_of_the_same_add_is_refused(tmp_path, monkeypatch, capsys):
    # Review 2026-11-10: a re-run after a PENDING ESPN claim would post a twin;
    # the in-tab guard cannot see pending claims. The ledger must stop it.
    monkeypatch.setattr(ts, "LEDGER", tmp_path / "ledger.jsonl")
    assert ts.main(_espn()) == 0
    capsys.readouterr()
    assert ts.main(_espn()) == 2
    out = capsys.readouterr().out
    assert "REFUSED" in out and "already filed" in out
    assert "await" not in out  # no JS printed to paste


def test_failed_row_does_not_block_and_force_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "LEDGER", tmp_path / "ledger.jsonl")
    ts.main(_espn())
    ts.main(
        [
            "record",
            "--league",
            "la_liga",
            "--add",
            "C.J. Stroud",
            "--add-id",
            "4432577",
            "--verdict",
            "FAILED",
        ]
    )
    assert ts.main(_espn()) == 0
    assert ts.main(_espn("--force")) == 0


def test_keeper_is_never_a_drop(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ts, "LEDGER", tmp_path / "ledger.jsonl")
    rc = ts.main(
        [
            "yahoo",
            "--add",
            "Tyler Shough",
            "--add-id",
            "41825",
            "--drop",
            "Luther Burden III",
            "--drop-id",
            "1",
            "--bid",
            "2",
        ]
    )
    assert rc == 2
    assert "keepers" in capsys.readouterr().out
    assert not (tmp_path / "ledger.jsonl").exists()
