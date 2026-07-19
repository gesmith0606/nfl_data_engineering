"""Tests for src/adp_sources.py — real ADP fetchers (FFC + ESPN).

All HTTP calls are mocked; no live network access. Every fetcher must be
fail-open (D-06): network/HTTP/JSON errors return an empty, correctly
columned DataFrame rather than raising.
"""

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest

from src.adp_sources import ADP_COLUMNS, fetch_espn_adp, fetch_ffc_adp


def _mock_urlopen_returning(payload_bytes: bytes):
    """Build a context-manager mock whose ``.read()`` returns *payload_bytes*."""
    cm = MagicMock()
    cm.__enter__.return_value = cm
    cm.read.return_value = payload_bytes
    return cm


# ---------------------------------------------------------------------------
# fetch_ffc_adp
# ---------------------------------------------------------------------------


class TestFetchFfcAdp:
    def _ffc_payload(self):
        return {
            "players": [
                {
                    "player_id": 1,
                    "name": "Christian McCaffrey",
                    "position": "RB",
                    "team": "SF",
                    "adp": 1.2,
                    "adp_formatted": "1.02",
                    "times_drafted": 500,
                    "high": 1,
                    "low": 4,
                    "stdev": 0.8,
                    "bye": 9,
                },
                {
                    "player_id": 2,
                    "name": "San Francisco",
                    "position": "DEF",
                    "team": "SF",
                    "adp": 145.3,
                    "times_drafted": 480,
                    "stdev": 12.1,
                },
                {
                    "player_id": 3,
                    "name": "Justin Tucker",
                    "position": "PK",
                    "team": "BAL",
                    "adp": 160.0,
                    "times_drafted": 400,
                    "stdev": 10.0,
                },
            ]
        }

    def test_happy_path_columns_and_values(self):
        raw = json.dumps(self._ffc_payload()).encode("utf-8")
        with patch("src.adp_sources.urlopen", return_value=_mock_urlopen_returning(raw)):
            df = fetch_ffc_adp("half_ppr", 2026, teams=12)

        assert list(df.columns) == ADP_COLUMNS
        assert len(df) == 3
        row = df[df["player_name"] == "Christian McCaffrey"].iloc[0]
        assert row["position"] == "RB"
        assert row["team"] == "SF"
        assert row["adp"] == pytest.approx(1.2)
        assert row["stdev"] == pytest.approx(0.8)
        assert row["times_drafted"] == pytest.approx(500)
        assert row["source"] == "ffc"
        assert row["scoring_format"] == "half_ppr"
        assert row["name_key"] == "christian mccaffrey"

    def test_position_normalization_def_to_dst_and_pk_to_k(self):
        raw = json.dumps(self._ffc_payload()).encode("utf-8")
        with patch("src.adp_sources.urlopen", return_value=_mock_urlopen_returning(raw)):
            df = fetch_ffc_adp("ppr", 2026)

        positions = dict(zip(df["player_name"], df["position"]))
        assert positions["San Francisco"] == "DST"
        assert positions["Justin Tucker"] == "K"

    def test_scoring_format_maps_to_ffc_url_path(self):
        raw = json.dumps(self._ffc_payload()).encode("utf-8")
        with patch(
            "src.adp_sources.urlopen", return_value=_mock_urlopen_returning(raw)
        ) as mock_urlopen:
            fetch_ffc_adp("half_ppr", 2026, teams=10)

        called_url = mock_urlopen.call_args[0][0].full_url
        assert "/api/v1/adp/half-ppr" in called_url
        assert "teams=10" in called_url
        assert "year=2026" in called_url

    def test_unknown_scoring_format_fails_open_without_network_call(self):
        with patch("src.adp_sources.urlopen") as mock_urlopen:
            df = fetch_ffc_adp("bogus_format", 2026)

        mock_urlopen.assert_not_called()
        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_malformed_json_fails_open(self):
        with patch(
            "src.adp_sources.urlopen",
            return_value=_mock_urlopen_returning(b"{not valid json"),
        ):
            df = fetch_ffc_adp("ppr", 2026)

        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_http_error_fails_open(self):
        with patch(
            "src.adp_sources.urlopen",
            side_effect=HTTPError("url", 503, "Service Unavailable", {}, None),
        ):
            df = fetch_ffc_adp("ppr", 2026)

        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_network_error_fails_open(self):
        with patch(
            "src.adp_sources.urlopen", side_effect=URLError("no route to host")
        ):
            df = fetch_ffc_adp("ppr", 2026)

        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_empty_players_list_fails_open(self):
        raw = json.dumps({"players": []}).encode("utf-8")
        with patch("src.adp_sources.urlopen", return_value=_mock_urlopen_returning(raw)):
            df = fetch_ffc_adp("ppr", 2026)

        assert df.empty
        assert list(df.columns) == ADP_COLUMNS


# ---------------------------------------------------------------------------
# fetch_espn_adp
# ---------------------------------------------------------------------------


class TestFetchEspnAdp:
    def _espn_payload(self):
        return {
            "players": [
                {
                    "player": {
                        "fullName": "Ja'Marr Chase",
                        "defaultPositionId": 3,
                        "proTeamId": 4,
                        "ownership": {"averageDraftPosition": 2.4},
                    }
                },
                {
                    "player": {
                        "fullName": "San Francisco 49ers",
                        "defaultPositionId": 16,
                        "proTeamId": 25,
                        "ownership": {"averageDraftPosition": 140.1},
                    }
                },
            ]
        }

    def test_happy_path_columns_and_position_mapping(self):
        raw = json.dumps(self._espn_payload()).encode("utf-8")
        with patch("src.adp_sources.urlopen", return_value=_mock_urlopen_returning(raw)):
            df = fetch_espn_adp(2026)

        assert list(df.columns) == ADP_COLUMNS
        assert len(df) == 2
        row = df[df["player_name"] == "Ja'Marr Chase"].iloc[0]
        assert row["position"] == "WR"
        assert row["adp"] == pytest.approx(2.4)
        assert row["source"] == "espn"
        assert pd.isna(row["stdev"])
        assert pd.isna(row["times_drafted"])
        assert row["name_key"] == "jamarr chase"

        dst_row = df[df["player_name"] == "San Francisco 49ers"].iloc[0]
        assert dst_row["position"] == "DST"

    def test_sends_fantasy_filter_header(self):
        raw = json.dumps(self._espn_payload()).encode("utf-8")
        with patch(
            "src.adp_sources.urlopen", return_value=_mock_urlopen_returning(raw)
        ) as mock_urlopen:
            fetch_espn_adp(2026)

        request_obj = mock_urlopen.call_args[0][0]
        # urllib.request.Request title-cases header keys internally
        # ("X-Fantasy-Filter" -> "X-fantasy-filter"), so compare case-insensitively.
        headers_lower = {k.lower(): v for k, v in request_obj.headers.items()}
        assert "x-fantasy-filter" in headers_lower
        filter_payload = json.loads(headers_lower["x-fantasy-filter"])
        assert filter_payload["players"]["limit"] == 400

    def test_malformed_json_fails_open(self):
        with patch(
            "src.adp_sources.urlopen",
            return_value=_mock_urlopen_returning(b"not json at all"),
        ):
            df = fetch_espn_adp(2026)

        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_http_error_fails_open(self):
        with patch(
            "src.adp_sources.urlopen",
            side_effect=HTTPError("url", 403, "Forbidden", {}, None),
        ):
            df = fetch_espn_adp(2026)

        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_unexpected_shape_fails_open(self):
        """A structural change (no 'players' key) must never raise."""
        raw = json.dumps({"unexpected": "shape"}).encode("utf-8")
        with patch("src.adp_sources.urlopen", return_value=_mock_urlopen_returning(raw)):
            df = fetch_espn_adp(2026)

        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_missing_ownership_defaults_adp_to_none(self):
        payload = {
            "players": [
                {"player": {"fullName": "No ADP Guy", "defaultPositionId": 2}}
            ]
        }
        raw = json.dumps(payload).encode("utf-8")
        with patch("src.adp_sources.urlopen", return_value=_mock_urlopen_returning(raw)):
            df = fetch_espn_adp(2026)

        assert len(df) == 1
        assert pd.isna(df.iloc[0]["adp"])
        assert df.iloc[0]["position"] == "RB"


class TestFetchSleeperAdp:
    """fetch_sleeper_adp — real crowd ADP from the Sleeper projections feed."""

    def _payload(self):
        return [
            {
                "player_id": "4866",
                "team": "ATL",
                "player": {"first_name": "Bijan", "last_name": "Robinson", "position": "RB", "team": "ATL"},
                "stats": {"adp_half_ppr": 1.5, "adp_ppr": 1.4, "adp_std": 2.1},
            },
            {
                "player_id": "9999",
                "team": "CIN",
                "player": {"first_name": "Ja'Marr", "last_name": "Chase", "position": "WR", "team": "CIN"},
                "stats": {"adp_half_ppr": 3.7},
            },
            # No ADP for the requested format -> excluded
            {
                "player_id": "1",
                "team": "FA",
                "player": {"first_name": "Practice", "last_name": "Squad", "position": "RB"},
                "stats": {"adp_ppr": 250.0},
            },
        ]

    def test_happy_path(self, monkeypatch):
        from src import adp_sources

        monkeypatch.setattr(adp_sources, "_fetch_json", lambda url, headers=None: self._payload())
        df = adp_sources.fetch_sleeper_adp("half_ppr", 2026)
        assert list(df["player_name"]) == ["Bijan Robinson", "Ja'Marr Chase"]
        assert df.iloc[0]["adp"] == 1.5
        assert (df["source"] == "sleeper").all()
        assert (df["scoring_format"] == "half_ppr").all()

    def test_unknown_scoring_fails_open(self):
        from src import adp_sources

        assert adp_sources.fetch_sleeper_adp("superflex_ppr", 2026).empty

    def test_malformed_payload_fails_open(self, monkeypatch):
        from src import adp_sources

        monkeypatch.setattr(adp_sources, "_fetch_json", lambda url, headers=None: {"error": "nope"})
        assert adp_sources.fetch_sleeper_adp("ppr", 2026).empty
