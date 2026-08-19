"""
Tests for scripts/bronze_depthchart_ourlads_ingestion.py

Fixtures under tests/fixtures/ourlads_buf_offense.html and
tests/fixtures/ourlads_ari_empty.html are trimmed real captures taken live
from ourlads.com/nfldepthcharts/depthchart/BUF and .../ARI on 2026-08-18
(see module docstring re: the ARZ/ARI silent-empty-table gotcha — "ARI" is
NOT Arizona's real OurLads code, but it 200s with a genuinely empty tbody,
which is exactly the failure mode this fixture reproduces).

Covers:
  - parse_player_cell: suffix stripping, name-order flip, ALL-CAPS
    normalization, already-mixed-case names left untouched, empty slot
  - parse_offense_rows: real BUF table -> correct per-position player lists,
    non-skill (OL) rows excluded
  - build_team_rows: QB1 identity, WR slot ordering across LWR/RWR/SWR,
    team code mapped via OURLADS_TO_NFLVERSE, raw_cell preserved
  - build_team_rows on the ARI-empty fixture: zero rows (the silent-failure
    mode this script must catch loudly, not swallow)
  - OURLADS_TO_NFLVERSE: exactly 32 codes, ARZ->ARI and LAR->LA fixups present
  - write_depthchart_parquet: dry run vs real write, season partition path
  - run_depthchart_capture: any single empty team -> exit 1 (fail-hard,
    not silent-partial), even though good teams still get written
  - run_depthchart_capture: zero rows overall -> exit 1
"""

import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bronze_depthchart_ourlads_ingestion import (  # noqa: E402
    DEPTHCHART_SCHEMA_COLS,
    OURLADS_TO_NFLVERSE,
    build_team_rows,
    parse_offense_rows,
    parse_player_cell,
    run_depthchart_capture,
    write_depthchart_parquet,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SNAPSHOT_TS = "2026-08-18T12:00:00+00:00"
SEASON = 2026


def _load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


BUF_HTML = _load_fixture("ourlads_buf_offense.html")
ARI_EMPTY_HTML = _load_fixture("ourlads_ari_empty.html")


# ---------------------------------------------------------------------------
# parse_player_cell
# ---------------------------------------------------------------------------


class TestParsePlayerCell:
    def test_all_caps_name_order_flip(self):
        # Raw source text is genuinely ALL CAPS for this row on OurLads.
        result = parse_player_cell("ALLEN, JOSH 18/1")
        assert result["player_name"] == "Josh Allen"
        assert result["raw_cell"] == "ALLEN, JOSH 18/1"

    def test_mixed_case_left_untouched(self):
        result = parse_player_cell("Coleman, Keon 24/2")
        assert result["player_name"] == "Keon Coleman"

    def test_udfa_suffix_stripped(self):
        result = parse_player_cell("Palmer, Joshua U/LAC")
        assert result["player_name"] == "Joshua Palmer"

    def test_practice_squad_suffix_stripped(self):
        result = parse_player_cell("Shavers, Tyrell CF23")
        assert result["player_name"] == "Tyrell Shavers"

    def test_suffixed_lastname_preserved(self):
        # "Jr." lives before the comma, so it stays attached to the surname.
        result = parse_player_cell("Hardman Jr., Mecole SF25")
        assert result["player_name"] == "Mecole Hardman Jr."

    def test_empty_slot_returns_none(self):
        assert parse_player_cell("") is None
        assert parse_player_cell(None) is None

    def test_no_comma_fallback_keeps_raw(self):
        result = parse_player_cell("Some Weird Text")
        assert result["player_name"] == "Some Weird Text"


# ---------------------------------------------------------------------------
# parse_offense_rows
# ---------------------------------------------------------------------------


class TestParseOffenseRows:
    def test_real_buf_table(self):
        rows_by_pos = parse_offense_rows(BUF_HTML)
        assert rows_by_pos["QB"][0]["player_name"] == "Josh Allen"
        assert rows_by_pos["RB"][0]["player_name"] == "James Cook III"
        assert rows_by_pos["TE"][0]["player_name"] == "Dalton Kincaid"

    def test_non_skill_ol_row_excluded(self):
        # Fixture includes an "LT" row to prove OL is parsed by the table
        # walk but never surfaces in the kept OFFENSE_POSITIONS set.
        rows_by_pos = parse_offense_rows(BUF_HTML)
        assert "LT" not in rows_by_pos

    def test_wr_rows_kept_separately_pre_combine(self):
        rows_by_pos = parse_offense_rows(BUF_HTML)
        assert [p["player_name"] for p in rows_by_pos["LWR"]][:1] == ["Keon Coleman"]
        assert [p["player_name"] for p in rows_by_pos["RWR"]][:1] == ["DJ Moore"]
        assert [p["player_name"] for p in rows_by_pos["SWR"]][:1] == ["Khalil Shakir"]

    def test_ari_empty_fixture_yields_no_rows(self):
        # This is the silent-failure signature this script must catch loud.
        rows_by_pos = parse_offense_rows(ARI_EMPTY_HTML)
        assert rows_by_pos == {}


# ---------------------------------------------------------------------------
# build_team_rows
# ---------------------------------------------------------------------------


class TestBuildTeamRows:
    def test_qb1_identity(self):
        rows = build_team_rows(BUF_HTML, "BUF", SNAPSHOT_TS, SEASON)
        qb1 = [r for r in rows if r["slot"] == "QB1"][0]
        assert qb1["player_name"] == "Josh Allen"
        assert qb1["team"] == "BUF"
        assert qb1["position"] == "QB"
        assert qb1["season"] == SEASON
        assert qb1["snapshot_ts"] == SNAPSHOT_TS
        assert qb1["raw_cell"] == "ALLEN, JOSH 18/1"

    def test_wr_slot_ordering_lwr_rwr_swr(self):
        rows = build_team_rows(BUF_HTML, "BUF", SNAPSHOT_TS, SEASON)
        wr_rows = [r for r in rows if r["position"] == "WR"]
        wr_names_in_slot_order = [
            r["player_name"] for r in sorted(wr_rows, key=lambda r: int(r["slot"][2:]))
        ]
        # LWR: Coleman, Palmer, Shavers (3) -> WR1-3
        # RWR: Moore, Bell (2)             -> WR4-5
        # SWR: Shakir, Hardman Jr. (2)      -> WR6-7
        assert wr_names_in_slot_order == [
            "Keon Coleman",
            "Joshua Palmer",
            "Tyrell Shavers",
            "DJ Moore",
            "Skyler Bell",
            "Khalil Shakir",
            "Mecole Hardman Jr.",
        ]
        assert wr_rows[0]["slot"] == "WR1"

    def test_team_code_mapped_via_ourlads_to_nflverse(self):
        rows = build_team_rows(BUF_HTML, "BUF", SNAPSHOT_TS, SEASON)
        assert all(r["team"] == "BUF" for r in rows)

    def test_ari_empty_fixture_yields_zero_rows(self):
        # Fixture represents an empty-table response; exercised via the
        # real "ARZ" code (the only valid map key) since build_team_rows
        # looks up OURLADS_TO_NFLVERSE by the code actually used to fetch.
        rows = build_team_rows(ARI_EMPTY_HTML, "ARZ", SNAPSHOT_TS, SEASON)
        assert rows == []

    def test_output_columns_match_schema(self):
        rows = build_team_rows(BUF_HTML, "BUF", SNAPSHOT_TS, SEASON)
        assert set(rows[0].keys()) == set(DEPTHCHART_SCHEMA_COLS)


# ---------------------------------------------------------------------------
# OURLADS_TO_NFLVERSE
# ---------------------------------------------------------------------------


class TestOurladsToNflverseMap:
    def test_exactly_32_teams(self):
        assert len(OURLADS_TO_NFLVERSE) == 32

    def test_arizona_gotcha_fixup(self):
        # NOT "ARI" -- that code 200s with an empty table (see module docstring).
        assert "ARI" not in OURLADS_TO_NFLVERSE
        assert OURLADS_TO_NFLVERSE["ARZ"] == "ARI"

    def test_rams_fixup(self):
        assert OURLADS_TO_NFLVERSE["LAR"] == "LA"

    def test_values_are_32_distinct_nflverse_abbreviations(self):
        assert len(set(OURLADS_TO_NFLVERSE.values())) == 32


# ---------------------------------------------------------------------------
# write_depthchart_parquet
# ---------------------------------------------------------------------------


class TestWriteDepthchartParquet:
    def test_dry_run_skips_write(self, tmp_path, monkeypatch):
        import scripts.bronze_depthchart_ourlads_ingestion as mod

        monkeypatch.setattr(mod, "BRONZE_DEPTHCHART_DIR", str(tmp_path))
        df = pd.DataFrame(build_team_rows(BUF_HTML, "BUF", SNAPSHOT_TS, SEASON))
        path = write_depthchart_parquet(df, SEASON, dry_run=True)
        assert not os.path.exists(path)

    def test_real_write_season_partition_path(self, tmp_path, monkeypatch):
        import scripts.bronze_depthchart_ourlads_ingestion as mod

        monkeypatch.setattr(mod, "BRONZE_DEPTHCHART_DIR", str(tmp_path))
        df = pd.DataFrame(build_team_rows(BUF_HTML, "BUF", SNAPSHOT_TS, SEASON))
        path = write_depthchart_parquet(df, SEASON, dry_run=False)
        assert os.path.exists(path)
        assert f"season={SEASON}" in path
        assert os.path.basename(path).startswith("ourlads_")
        written = pd.read_parquet(path)
        assert len(written) == len(df)


# ---------------------------------------------------------------------------
# run_depthchart_capture
# ---------------------------------------------------------------------------


class TestRunDepthchartCapture:
    def test_one_empty_team_fails_hard(self, tmp_path, monkeypatch):
        """The ARZ/ARI silent-failure mode must exit 1, not slip through."""
        import scripts.bronze_depthchart_ourlads_ingestion as mod

        monkeypatch.setattr(mod, "BRONZE_DEPTHCHART_DIR", str(tmp_path))
        monkeypatch.setattr(mod, "OURLADS_TO_NFLVERSE", {"BUF": "BUF", "ARZ": "ARI"})
        monkeypatch.setattr(mod, "REQUEST_DELAY_S", 0)

        def fake_fetch(code):
            return BUF_HTML if code == "BUF" else ARI_EMPTY_HTML

        with patch.object(mod, "fetch_team_page", side_effect=fake_fetch):
            exit_code = run_depthchart_capture(dry_run=True)

        assert exit_code == 1

    def test_all_teams_nonzero_exits_zero(self, tmp_path, monkeypatch):
        import scripts.bronze_depthchart_ourlads_ingestion as mod

        monkeypatch.setattr(mod, "BRONZE_DEPTHCHART_DIR", str(tmp_path))
        monkeypatch.setattr(mod, "OURLADS_TO_NFLVERSE", {"BUF": "BUF"})
        monkeypatch.setattr(mod, "REQUEST_DELAY_S", 0)

        with patch.object(mod, "fetch_team_page", return_value=BUF_HTML):
            exit_code = run_depthchart_capture(dry_run=True)

        assert exit_code == 0

    def test_zero_rows_overall_exits_one(self, tmp_path, monkeypatch):
        import scripts.bronze_depthchart_ourlads_ingestion as mod

        monkeypatch.setattr(mod, "BRONZE_DEPTHCHART_DIR", str(tmp_path))
        monkeypatch.setattr(mod, "OURLADS_TO_NFLVERSE", {"ARZ": "ARI"})
        monkeypatch.setattr(mod, "REQUEST_DELAY_S", 0)

        with patch.object(mod, "fetch_team_page", return_value=ARI_EMPTY_HTML):
            exit_code = run_depthchart_capture(dry_run=True)

        assert exit_code == 1

    def test_fetch_exception_treated_as_empty_team_not_fatal(self, tmp_path, monkeypatch):
        """One team's network error must not abort the other teams' capture."""
        import scripts.bronze_depthchart_ourlads_ingestion as mod

        monkeypatch.setattr(mod, "BRONZE_DEPTHCHART_DIR", str(tmp_path))
        monkeypatch.setattr(mod, "OURLADS_TO_NFLVERSE", {"BUF": "BUF", "MIA": "MIA"})
        monkeypatch.setattr(mod, "REQUEST_DELAY_S", 0)

        def fake_fetch(code):
            if code == "MIA":
                raise RuntimeError("HTTP 500")
            return BUF_HTML

        with patch.object(mod, "fetch_team_page", side_effect=fake_fetch):
            exit_code = run_depthchart_capture(dry_run=True)

        # BUF still parsed fine; MIA failed -> overall fail-hard exit 1.
        assert exit_code == 1
