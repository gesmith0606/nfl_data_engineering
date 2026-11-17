"""Waiver preflight: route selection and the failure classes from 2026-11-03/10."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.waiver_preflight as pf  # noqa: E402

TODAY = dt.date(2026, 11, 10)


class TestYahooClassify:
    def test_pre_approval_token_is_named_not_generic(self):
        ok, detail, fix = pf.classify_yahoo(
            401,
            '{"error":{"description":"oauth_problem='
            '\\"additional_authorization_required\\""}}',
        )
        assert not ok
        assert "predates" in detail
        assert "never in chat" in fix

    def test_missing_token_points_at_bitwarden(self):
        ok, _, fix = pf.classify_yahoo(None, "")
        assert not ok and "YAHOO_TOKENS" in fix

    def test_200_is_ok(self):
        assert pf.classify_yahoo(200, "")[0]


class TestRoutes:
    def test_everything_dead_falls_back_to_the_chrome_tab_and_says_verify(self):
        r = "\n".join(pf.routes({}))
        assert "ESPN  file: claude-in-chrome" in r
        assert "Yahoo file: claude-in-chrome" in r and "VERIFY" in r
        assert "Mantis file: George in the Sleeper app" in r

    def test_playwright_up_uses_the_scripts(self):
        r = "\n".join(pf.routes({"playwright": True}))
        assert "ESPN  file: submit_claims.py --submit" in r
        assert "Yahoo read: --yahoo-browser" in r

    def test_yahoo_api_beats_the_browser_for_reads(self):
        r = "\n".join(pf.routes({"playwright": True, "yahoo_api": True}))
        assert "Yahoo read: Yahoo API" in r

    def test_espn_cookies_enable_http_filing_without_a_browser(self):
        r = "\n".join(pf.routes({"espn_cookies": True}))
        assert "--espn-http" in r


class TestLedger:
    def _row(self, verdict, ts="2026-11-10T21:00:00", add="Tyler Shough"):
        return json.dumps(
            {"ts": ts, "league": "feetball", "add": add, "bid": 2, "verdict": verdict}
        )

    def test_unknown_outcome_is_unclear(self):
        unclear, awaiting = pf.unresolved_claims(
            [self._row("POSTING"), self._row("UNKNOWN")], TODAY
        )
        assert unclear == ["feetball: Tyler Shough ($2) is UNKNOWN"]
        assert awaiting == []

    def test_submit_claims_attempt_row_is_unclear(self):
        # submit_claims.py writes ATTEMPT before a POST; a crash leaves it last.
        unclear, _ = pf.unresolved_claims([self._row("ATTEMPT")], TODAY)
        assert unclear

    def test_pending_is_a_verify_note_not_a_failure(self):
        # Review: counting PENDING as a failure would FAIL every Tuesday.
        unclear, awaiting = pf.unresolved_claims([self._row("PENDING")], TODAY)
        assert unclear == [] and awaiting

    def test_resolved_claim_is_quiet(self):
        out = pf.unresolved_claims(
            [self._row("PENDING"), self._row("CONFIRMED")], TODAY
        )
        assert out == ([], [])

    def test_old_rows_age_out(self):
        out = pf.unresolved_claims(
            [self._row("UNKNOWN", ts="2026-10-01T09:00:00")], TODAY
        )
        assert out == ([], [])

    def test_garbage_lines_are_ignored(self):
        assert pf.unresolved_claims(["not json", ""], TODAY) == ([], [])


class TestBoard:
    def test_build_chain_ends_with_the_gold_board(self):
        cmds = pf.board_build_commands(2026, 10)
        assert any("player_weekly" in c for c in cmds[0])
        assert cmds[-1][1] == "scripts/generate_projections.py"
        assert cmds[-1][cmds[-1].index("--week") + 1] == "10"

    def test_build_stops_at_the_first_failure(self, monkeypatch):
        calls = []

        def fake_run(cmd, **_):
            calls.append(cmd)
            return SimpleNamespace(returncode=1, stderr="boom", stdout="")

        monkeypatch.setattr(pf, "board_files", lambda s, w: [])
        assert pf.build_board(2026, 10, run=fake_run) is False
        assert len(calls) == 1

    def test_board_files_reads_padded_and_unpadded_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pf, "GOLD", tmp_path)
        for d in ("week=9", "week=09"):
            p = tmp_path / "season=2026" / d
            p.mkdir(parents=True)
            (p / f"projections_half_ppr_2026110{len(d)}_000000.parquet").write_text("x")
        assert len(pf.board_files(2026, 9)) == 2
