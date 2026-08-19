"""Tests for scripts/ingest_adp_history.py — historical ADP snapshot schema.

No live network access: fetch_ffc_adp/fetch_mfl_adp are monkeypatched.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import ingest_adp_history as hist  # noqa: E402
from src.adp_sources import ADP_COLUMNS  # noqa: E402


def _fake_raw_df(source: str, scoring: str, ffc_meta=None):
    df = pd.DataFrame(
        [
            {
                "player_name": "Christian McCaffrey",
                "position": "RB",
                "team": "CAR",
                "adp": 1.4,
                "high": 1.0,
                "low": 5.0,
                "stdev": 0.5,
                "times_drafted": 500.0,
                "source": source,
                "scoring_format": scoring,
                "fetched_at": "2026-08-18T00:00:00+00:00",
                "name_key": "christian mccaffrey",
            }
        ],
        columns=ADP_COLUMNS,
    )
    if ffc_meta is not None:
        df.attrs["ffc_meta"] = ffc_meta
    return df


class TestHistoryColumns:
    def test_unified_schema_columns(self):
        assert hist.HISTORY_COLUMNS == [
            "season", "snapshot_date", "source", "format", "player_name",
            "team", "position", "adp", "high", "low", "stdev", "times_drafted",
        ]

    def test_to_history_df_reshapes_and_fills_metadata(self):
        raw = _fake_raw_df("ffc", "ppr")
        out = hist._to_history_df(raw, season=2021, snapshot_date="2021-09-01", source="ffc", fmt="ppr")

        assert list(out.columns) == hist.HISTORY_COLUMNS
        row = out.iloc[0]
        assert row["season"] == 2021
        assert row["snapshot_date"] == "2021-09-01"
        assert row["source"] == "ffc"
        assert row["format"] == "ppr"
        assert row["player_name"] == "Christian McCaffrey"
        assert row["adp"] == pytest.approx(1.4)
        assert row["high"] == pytest.approx(1.0)
        assert row["low"] == pytest.approx(5.0)

    def test_to_history_df_empty_input_returns_empty_with_schema(self):
        empty = pd.DataFrame(columns=ADP_COLUMNS)
        out = hist._to_history_df(empty, season=2021, snapshot_date="2021-09-01", source="ffc", fmt="ppr")
        assert out.empty
        assert list(out.columns) == hist.HISTORY_COLUMNS


class TestIngestFfc:
    def test_snapshot_date_from_ffc_meta_end_date(self, tmp_path):
        raw = _fake_raw_df("ffc", "ppr", ffc_meta={"start_date": "2021-08-31", "end_date": "2021-09-01"})
        with patch.object(hist, "fetch_ffc_adp", return_value=raw), patch.object(hist.time, "sleep"):
            written = hist.ingest_ffc([2021], str(tmp_path))

        assert len(written) == 3  # ppr, half_ppr, standard
        path, n = written[0]
        assert n == 1
        df = pd.read_csv(path)
        assert df.iloc[0]["snapshot_date"] == "2021-09-01"
        assert df.iloc[0]["source"] == "ffc"

    def test_empty_fetch_is_skipped_not_written(self, tmp_path):
        empty = pd.DataFrame(columns=ADP_COLUMNS)
        with patch.object(hist, "fetch_ffc_adp", return_value=empty), patch.object(hist.time, "sleep"):
            written = hist.ingest_ffc([2021], str(tmp_path))

        assert written == []


class TestIngestMfl:
    def test_format_labeled_season_aggregate(self, tmp_path):
        raw = _fake_raw_df("mfl", "half_ppr")
        with patch.object(hist, "fetch_mfl_adp", return_value=raw), patch.object(hist.time, "sleep"):
            written = hist.ingest_mfl([2021], str(tmp_path))

        assert len(written) == 1
        path, n = written[0]
        assert "adp_mfl_season_aggregate_2021.csv" in path
        df = pd.read_csv(path)
        assert df.iloc[0]["format"] == "season_aggregate"
        assert df.iloc[0]["source"] == "mfl"
