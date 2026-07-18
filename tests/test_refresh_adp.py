"""Tests for scripts/refresh_adp.py — multi-source ADP refresh CLI.

Covers the new --source/--scoring plumbing: FFC/ESPN real-ADP normalization,
the legacy Sleeper search_rank path (relabeled ``sleeper_rank`` — never
mistaken for real ADP), and the adp_latest.csv backward-compat write gate.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import refresh_adp  # noqa: E402
from src.adp_sources import ADP_COLUMNS  # noqa: E402


def _fake_real_adp_df():
    return pd.DataFrame(
        [
            {
                "player_name": "Bijan Robinson",
                "position": "RB",
                "team": "ATL",
                "adp": 1.5,
                "stdev": 0.4,
                "times_drafted": 300,
                "source": "ffc",
                "scoring_format": "half_ppr",
                "fetched_at": "2026-07-18T00:00:00+00:00",
                "name_key": "bijan robinson",
            },
            {
                "player_name": "Ja'Marr Chase",
                "position": "WR",
                "team": "CIN",
                "adp": 2.1,
                "stdev": 0.6,
                "times_drafted": 295,
                "source": "ffc",
                "scoring_format": "half_ppr",
                "fetched_at": "2026-07-18T00:00:00+00:00",
                "name_key": "jamarr chase",
            },
        ],
        columns=ADP_COLUMNS,
    )


def _fake_sleeper_players():
    return {
        "4034": {
            "full_name": "Bijan Robinson",
            "position": "RB",
            "team": "ATL",
            "search_rank": 3,
            "age": 24,
            "years_exp": 3,
            "status": "Active",
        },
        "5000": {
            "full_name": "Some Guy",
            "position": "WR",
            "team": "NYJ",
            "search_rank": 900,
            "age": 27,
            "years_exp": 5,
            "status": "Active",
        },
    }


class TestBuildAdpFromRealSource:
    def test_ranks_by_adp_ascending_and_fills_legacy_nulls(self):
        out = refresh_adp.build_adp_from_real_source(_fake_real_adp_df())
        assert list(out.columns) == refresh_adp.OUTPUT_COLUMNS
        assert out.iloc[0]["player_name"] == "Bijan Robinson"
        assert out.iloc[0]["adp_rank"] == 1
        assert out.iloc[1]["adp_rank"] == 2
        assert pd.isna(out.iloc[0]["sleeper_id"])
        assert pd.isna(out.iloc[0]["age"])
        assert pd.isna(out.iloc[0]["years_exp"])

    def test_empty_input_returns_empty(self):
        empty = pd.DataFrame(columns=ADP_COLUMNS)
        out = refresh_adp.build_adp_from_real_source(empty)
        assert out.empty


class TestBuildAdpFromSleeperRank:
    def test_labels_source_as_sleeper_rank_not_sleeper(self):
        out = refresh_adp.build_adp_from_sleeper_rank(
            _fake_sleeper_players(), top_n=500, scoring="half_ppr"
        )
        assert list(out.columns) == refresh_adp.OUTPUT_COLUMNS
        assert set(out["source"]) == {"sleeper_rank"}
        assert set(out["scoring_format"]) == {"half_ppr"}
        # Real-ADP fields are unavailable from this legacy path.
        assert out["adp"].isna().all()

    def test_still_ranked_by_search_rank(self):
        out = refresh_adp.build_adp_from_sleeper_rank(
            _fake_sleeper_players(), top_n=500, scoring="half_ppr"
        )
        assert out.iloc[0]["player_name"] == "Bijan Robinson"
        assert out.iloc[0]["adp_rank"] == 1


class TestMainCli:
    """End-to-end CLI runs with the network fully mocked."""

    def test_ffc_default_invocation_writes_latest_pointer(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "data"
        monkeypatch.setattr(
            sys,
            "argv",
            ["refresh_adp.py", "--output-dir", str(out_dir), "--season", "2026"],
        )
        with patch(
            "src.adp_sources.fetch_ffc_adp", return_value=_fake_real_adp_df()
        ):
            rc = refresh_adp.main()

        assert rc == 0
        assert (out_dir / "adp" / "adp_ffc_half_ppr.csv").exists()
        assert (out_dir / "adp_latest.csv").exists()

        latest = pd.read_csv(out_dir / "adp_latest.csv")
        assert set(refresh_adp.OUTPUT_COLUMNS) <= set(latest.columns)
        assert latest.iloc[0]["player_name"] == "Bijan Robinson"

    def test_espn_source_does_not_touch_adp_latest(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "data"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "refresh_adp.py",
                "--source",
                "espn",
                "--output-dir",
                str(out_dir),
                "--season",
                "2026",
            ],
        )
        with patch(
            "src.adp_sources.fetch_espn_adp", return_value=_fake_real_adp_df()
        ):
            rc = refresh_adp.main()

        assert rc == 0
        assert (out_dir / "adp" / "adp_espn_half_ppr.csv").exists()
        assert not (out_dir / "adp_latest.csv").exists()

    def test_sleeper_source_labels_legacy_and_skips_latest(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "data"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "refresh_adp.py",
                "--source",
                "sleeper",
                "--output-dir",
                str(out_dir),
            ],
        )
        with patch.object(
            refresh_adp, "fetch_sleeper_players", return_value=_fake_sleeper_players()
        ):
            rc = refresh_adp.main()

        assert rc == 0
        source_csv = out_dir / "adp" / "adp_sleeper_half_ppr.csv"
        assert source_csv.exists()
        df = pd.read_csv(source_csv)
        assert set(df["source"]) == {"sleeper_rank"}
        assert not (out_dir / "adp_latest.csv").exists()

    def test_empty_fetch_returns_error_code(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "data"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "refresh_adp.py",
                "--source",
                "ffc",
                "--output-dir",
                str(out_dir),
            ],
        )
        empty = pd.DataFrame(columns=ADP_COLUMNS)
        with patch("src.adp_sources.fetch_ffc_adp", return_value=empty):
            rc = refresh_adp.main()

        assert rc == 1
