"""Tests for src/adp_sources.py — real ADP fetchers (FFC + ESPN + MFL).

All HTTP calls are mocked; no live network access. Every fetcher must be
fail-open (D-06): network/HTTP/JSON errors return an empty, correctly
columned DataFrame rather than raising.
"""

import json
import os
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest

from src.adp_sources import ADP_COLUMNS, fetch_espn_adp, fetch_ffc_adp

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "mfl_adp")


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
        assert row["high"] == pytest.approx(1)
        assert row["low"] == pytest.approx(4)
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


# ---------------------------------------------------------------------------
# fetch_mfl_adp — fixture-based (trimmed from live-verified probe JSON:
# tests/fixtures/mfl_adp/{adp,players}_2021_sample.json, 3 real players)
# ---------------------------------------------------------------------------


def _load_fixture(name: str):
    with open(os.path.join(_FIXTURES_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


class TestFetchMflAdp:
    def setup_method(self):
        # The players crosswalk is memoized per-year at module scope —
        # clear it so each test starts from a clean cache.
        from src import adp_sources

        adp_sources._MFL_PLAYERS_CACHE.clear()

    def _urlopen_side_effect(self, adp_payload=None, players_payload=None):
        """Route the mocked urlopen by URL: TYPE=adp vs TYPE=players."""
        adp_payload = adp_payload if adp_payload is not None else _load_fixture("adp_2021_sample.json")
        players_payload = (
            players_payload if players_payload is not None else _load_fixture("players_2021_sample.json")
        )

        def _side_effect(request, timeout=15):
            url = request.full_url
            if "TYPE=players" in url:
                return _mock_urlopen_returning(json.dumps(players_payload).encode("utf-8"))
            return _mock_urlopen_returning(json.dumps(adp_payload).encode("utf-8"))

        return _side_effect

    def test_happy_path_parses_and_maps_fields(self):
        from src.adp_sources import fetch_mfl_adp

        with patch("src.adp_sources.urlopen", side_effect=self._urlopen_side_effect()):
            df = fetch_mfl_adp(2021, scoring="half_ppr")

        assert list(df.columns) == ADP_COLUMNS
        assert len(df) == 3
        row = df[df["player_name"] == "Christian McCaffrey"].iloc[0]
        assert row["position"] == "RB"
        assert row["team"] == "CAR"
        assert row["adp"] == pytest.approx(1.42)
        # Per SCOUT mapping: adp<-averagePick, high<-minPick, low<-maxPick,
        # times_drafted<-draftsSelectedIn.
        assert row["high"] == pytest.approx(1)
        assert row["low"] == pytest.approx(143)
        assert row["times_drafted"] == pytest.approx(8165)
        assert pd.isna(row["stdev"])  # not exposed by MFL
        assert row["source"] == "mfl"
        assert row["scoring_format"] == "half_ppr"
        assert row["name_key"] == "christian mccaffrey"
        # Top pick sanity (matches the FFC fixture's #1 too).
        assert df.sort_values("adp").iloc[0]["player_name"] == "Christian McCaffrey"

    def test_name_flip_last_first_to_first_last(self):
        from src.adp_sources import _flip_mfl_name

        assert _flip_mfl_name("McCaffrey, Christian") == "Christian McCaffrey"
        assert _flip_mfl_name("Bills, Buffalo") == "Buffalo Bills"  # DST rows
        assert _flip_mfl_name("NoComma") == "NoComma"
        assert _flip_mfl_name("") == ""
        assert _flip_mfl_name(None) == ""

    def test_period_all_is_required_in_url(self):
        """PERIOD=RECENT returns totalDrafts=0 for closed seasons (verified
        live) -- the fetcher must always request PERIOD=ALL."""
        from src.adp_sources import fetch_mfl_adp

        with patch(
            "src.adp_sources.urlopen", side_effect=self._urlopen_side_effect()
        ) as mock_urlopen:
            fetch_mfl_adp(2021, scoring="ppr")

        adp_call_urls = [
            c.args[0].full_url for c in mock_urlopen.call_args_list if "TYPE=adp" in c.args[0].full_url
        ]
        assert adp_call_urls, "expected at least one TYPE=adp request"
        assert all("PERIOD=ALL" in u for u in adp_call_urls)
        assert all("PERIOD=RECENT" not in u for u in adp_call_urls)

    def test_players_crosswalk_memoized_per_year(self):
        """A second fetch_mfl_adp call for the same year must not re-fetch
        the players crosswalk (only the adp export is fetched again)."""
        from src.adp_sources import fetch_mfl_adp

        with patch(
            "src.adp_sources.urlopen", side_effect=self._urlopen_side_effect()
        ) as mock_urlopen:
            fetch_mfl_adp(2021, scoring="ppr")
            first_call_count = mock_urlopen.call_count
            fetch_mfl_adp(2021, scoring="standard")
            second_round_calls = mock_urlopen.call_count - first_call_count

        # First call: 1 adp + 1 players fetch. Second call: adp only.
        assert first_call_count == 2
        assert second_round_calls == 1

    def test_unknown_scoring_fails_open_without_network_call(self):
        from src.adp_sources import fetch_mfl_adp

        with patch("src.adp_sources.urlopen") as mock_urlopen:
            df = fetch_mfl_adp(2021, scoring="bogus_format")

        mock_urlopen.assert_not_called()
        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_empty_adp_players_fails_open(self):
        from src.adp_sources import fetch_mfl_adp

        empty_adp = {"adp": {"player": []}}
        with patch(
            "src.adp_sources.urlopen",
            side_effect=self._urlopen_side_effect(adp_payload=empty_adp),
        ):
            df = fetch_mfl_adp(2021)

        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_missing_crosswalk_fails_open(self):
        from src.adp_sources import fetch_mfl_adp

        empty_players = {"players": {"player": []}}
        with patch(
            "src.adp_sources.urlopen",
            side_effect=self._urlopen_side_effect(players_payload=empty_players),
        ):
            df = fetch_mfl_adp(2021)

        assert df.empty
        assert list(df.columns) == ADP_COLUMNS

    def test_unmatched_id_skipped_not_raised(self):
        """An adp entry whose id has no crosswalk match is dropped, not a
        crash — MFL's adp/players exports can drift out of sync."""
        from src.adp_sources import fetch_mfl_adp

        adp_payload = {"adp": {"player": [
            {"id": "99999999", "averagePick": "5.0", "minPick": "1", "maxPick": "10", "draftsSelectedIn": "100"},
        ]}}
        with patch(
            "src.adp_sources.urlopen",
            side_effect=self._urlopen_side_effect(adp_payload=adp_payload),
        ):
            df = fetch_mfl_adp(2021)

        assert df.empty
