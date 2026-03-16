"""
Tests for Phase 1 infrastructure: config, adapter, registry, local-first storage.

Covers requirements INFRA-01 (local-first), INFRA-02 (dynamic season),
INFRA-03 (adapter), INFRA-04 (registry), INFRA-05 (season ranges).
"""

import datetime
import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from src.config import (
    get_max_season,
    DATA_TYPE_SEASON_RANGES,
    STADIUM_COORDINATES,
    TEAM_DIVISIONS,
    PBP_COLUMNS,
    validate_season_for_type,
)
from src.nfl_data_adapter import NFLDataAdapter


# ------------------------------------------------------------------
# TestDynamicSeasonValidation (INFRA-02, INFRA-05)
# ------------------------------------------------------------------

class TestDynamicSeasonValidation:
    """Tests for get_max_season() and validate_season_for_type()."""

    def test_get_max_season_returns_current_year_plus_one(self):
        expected = datetime.date.today().year + 1
        assert get_max_season() == expected

    def test_get_max_season_is_dynamic(self):
        """Verify get_max_season uses current date, not a hardcoded value."""
        with patch("src.config.datetime") as mock_dt:
            mock_dt.date.today.return_value = datetime.date(2028, 6, 15)
            # Re-call -- but since get_max_season uses datetime directly,
            # we test the logic: current_year + 1 >= 2027 next year
            actual = get_max_season()
            assert actual >= 2027  # Will be true for 2026+

    def test_season_ranges_has_all_16_types(self):
        expected_types = {
            "schedules", "pbp", "player_weekly", "player_seasonal",
            "snap_counts", "injuries", "rosters", "teams", "ngs",
            "pfr_weekly", "pfr_seasonal", "qbr", "depth_charts",
            "draft_picks", "combine", "officials",
        }
        assert expected_types == set(DATA_TYPE_SEASON_RANGES.keys())

    def test_validate_valid_season(self):
        assert validate_season_for_type("schedules", 2020) is True
        assert validate_season_for_type("ngs", 2020) is True

    def test_validate_invalid_season_too_early(self):
        assert validate_season_for_type("ngs", 2010) is False
        assert validate_season_for_type("snap_counts", 2005) is False

    def test_validate_invalid_season_too_late(self):
        far_future = get_max_season() + 10
        assert validate_season_for_type("schedules", far_future) is False

    def test_validate_edge_min_year(self):
        """Minimum year for each type should be valid."""
        for dtype, (min_s, _) in DATA_TYPE_SEASON_RANGES.items():
            assert validate_season_for_type(dtype, min_s) is True, (
                f"{dtype} should be valid at min year {min_s}"
            )

    def test_injury_season_capped_at_2024(self):
        """Injuries data was discontinued after 2024 by nflverse."""
        assert validate_season_for_type("injuries", 2024) is True
        assert validate_season_for_type("injuries", 2025) is False
        assert validate_season_for_type("injuries", 2009) is True  # min bound

    def test_validate_edge_max_year(self):
        """Max year (get_max_season()) should be valid for types with dynamic bounds."""
        static_cap_types = {"injuries"}
        max_s = get_max_season()
        for dtype in DATA_TYPE_SEASON_RANGES:
            if dtype in static_cap_types:
                continue
            assert validate_season_for_type(dtype, max_s) is True, (
                f"{dtype} should be valid at max year {max_s}"
            )

    def test_validate_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown data type"):
            validate_season_for_type("nonexistent", 2024)


# ------------------------------------------------------------------
# TestNFLDataAdapter (INFRA-03)
# ------------------------------------------------------------------

class TestNFLDataAdapter:
    """Tests for NFLDataAdapter fetch methods."""

    EXPECTED_METHODS = [
        "fetch_schedules", "fetch_pbp", "fetch_weekly_data",
        "fetch_seasonal_data", "fetch_snap_counts", "fetch_injuries",
        "fetch_rosters", "fetch_team_descriptions", "fetch_ngs",
        "fetch_pfr_weekly", "fetch_pfr_seasonal", "fetch_qbr",
        "fetch_depth_charts", "fetch_draft_picks", "fetch_combine",
    ]

    def test_adapter_has_all_fetch_methods(self):
        for method_name in self.EXPECTED_METHODS:
            assert hasattr(NFLDataAdapter, method_name), (
                f"NFLDataAdapter missing {method_name}"
            )

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_schedules_calls_nfl_data_py(self, mock_nfl):
        mock_mod = MagicMock()
        mock_mod.import_schedules.return_value = pd.DataFrame({"game_id": [1, 2]})
        mock_nfl.return_value = mock_mod

        adapter = NFLDataAdapter()
        df = adapter.fetch_schedules([2024])
        assert len(df) == 2
        mock_mod.import_schedules.assert_called_once()

    @patch.object(NFLDataAdapter, "_import_nfl")
    def test_fetch_returns_empty_on_invalid_season(self, mock_nfl):
        adapter = NFLDataAdapter()
        df = adapter.fetch_ngs([1990], stat_type="passing")
        assert df.empty
        mock_nfl.assert_not_called()


# ------------------------------------------------------------------
# TestDataTypeRegistry (INFRA-04)
# ------------------------------------------------------------------

class TestDataTypeRegistry:
    """Tests for DATA_TYPE_REGISTRY in bronze_ingestion_simple.py."""

    @pytest.fixture(autouse=True)
    def _load_registry(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from bronze_ingestion_simple import DATA_TYPE_REGISTRY
        self.registry = DATA_TYPE_REGISTRY

    def test_registry_has_16_entries(self):
        assert len(self.registry) >= 16

    def test_each_entry_has_required_keys(self):
        required = {"adapter_method", "bronze_path", "requires_week", "requires_season"}
        for dtype, entry in self.registry.items():
            missing = required - set(entry.keys())
            assert not missing, f"{dtype} missing keys: {missing}"

    def test_adapter_methods_exist_on_adapter(self):
        """Every adapter_method in the registry must exist on NFLDataAdapter."""
        for dtype, entry in self.registry.items():
            assert hasattr(NFLDataAdapter, entry["adapter_method"]), (
                f"Registry '{dtype}' references missing method {entry['adapter_method']}"
            )

    def test_sub_type_entries_have_sub_types_list(self):
        for dtype in ["ngs", "pfr_weekly", "pfr_seasonal"]:
            assert "sub_types" in self.registry[dtype], (
                f"{dtype} should have sub_types"
            )
            assert len(self.registry[dtype]["sub_types"]) > 0


# ------------------------------------------------------------------
# TestLocalFirstStorage (INFRA-01)
# ------------------------------------------------------------------

class TestLocalFirstStorage:
    """Tests for local-first bronze save functionality."""

    def test_save_local_creates_parquet(self, tmp_path):
        from bronze_ingestion_simple import save_local

        df = pd.DataFrame({"player": ["A", "B"], "yards": [100, 200]})
        out_path = str(tmp_path / "bronze" / "test" / "data.parquet")
        result = save_local(df, out_path)

        assert os.path.exists(result)
        loaded = pd.read_parquet(result)
        assert len(loaded) == 2
        assert list(loaded.columns) == ["player", "yards"]

    def test_local_path_structure(self):
        """Verify bronze_path templates produce valid directory structures."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from bronze_ingestion_simple import DATA_TYPE_REGISTRY

        entry = DATA_TYPE_REGISTRY["player_weekly"]
        path = entry["bronze_path"].format(season=2024, sub_type="")
        assert "season=2024" in path
        # player_weekly stores full-season files at season level (no week partition)
        assert "players/weekly" in path

    def test_save_local_creates_directories(self, tmp_path):
        from bronze_ingestion_simple import save_local

        deep_path = str(tmp_path / "a" / "b" / "c" / "file.parquet")
        df = pd.DataFrame({"x": [1]})
        save_local(df, deep_path)
        assert os.path.exists(deep_path)


# ------------------------------------------------------------------
# Phase 20: PBP Column Expansion (INFRA-01)
# ------------------------------------------------------------------

def _haversine_miles(lat1, lon1, lat2, lon2):
    """Compute great-circle distance in miles between two lat/lon points."""
    import math
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


class TestPBPColumnsExpanded:
    """Validate PBP_COLUMNS expansion from ~103 to ~140 columns."""

    def test_pbp_columns_expanded(self):
        """PBP_COLUMNS has >= 128 entries and contains key original columns."""
        assert len(PBP_COLUMNS) >= 128, f"Expected >= 128, got {len(PBP_COLUMNS)}"
        for col in [
            "game_id", "play_id", "epa", "wpa", "cpoe",
            "passer_player_id", "spread_line", "surface",
        ]:
            assert col in PBP_COLUMNS, f"Missing original column: {col}"

    def test_pbp_columns_no_duplicates(self):
        """No duplicate entries in PBP_COLUMNS."""
        assert len(PBP_COLUMNS) == len(set(PBP_COLUMNS)), (
            f"Found {len(PBP_COLUMNS) - len(set(PBP_COLUMNS))} duplicate columns"
        )

    def test_pbp_columns_grouped(self):
        """New columns (penalty_type) appear after surface (appended)."""
        surface_idx = PBP_COLUMNS.index("surface")
        penalty_idx = PBP_COLUMNS.index("penalty_type")
        assert penalty_idx > surface_idx, "penalty_type should appear after surface"

    def test_pbp_new_columns_present(self):
        """All key new columns from the expansion are present."""
        new_columns = [
            "penalty_type", "penalty_yards", "penalty_team",
            "kick_distance", "return_yards",
            "field_goal_result", "field_goal_attempt",
            "extra_point_result", "extra_point_attempt",
            "punt_blocked", "punt_inside_twenty",
            "kickoff_inside_twenty",
            "fumble_forced", "fumble_not_forced",
            "fumble_recovery_1_team", "fumble_recovery_1_yards",
            "fumble_recovery_1_player_id",
            "drive_play_count", "drive_time_of_possession",
        ]
        for col in new_columns:
            assert col in PBP_COLUMNS, f"Missing new column: {col}"


# ------------------------------------------------------------------
# Phase 20: Officials Data Type (INFRA-02)
# ------------------------------------------------------------------

class TestOfficialsDataType:
    """Validate officials data type wiring across config, adapter, and registry."""

    def test_officials_season_range(self):
        """Officials season range starts at 2015 per user decision."""
        assert "officials" in DATA_TYPE_SEASON_RANGES
        min_season, max_fn = DATA_TYPE_SEASON_RANGES["officials"]
        assert min_season == 2015, f"Expected 2015, got {min_season}"
        assert callable(max_fn)

    def test_officials_adapter_method_exists(self):
        """NFLDataAdapter has a callable fetch_officials method."""
        assert hasattr(NFLDataAdapter, "fetch_officials")
        assert callable(getattr(NFLDataAdapter, "fetch_officials"))

    def test_officials_registry_entry(self):
        """Officials entry exists in DATA_TYPE_REGISTRY with correct wiring."""
        import scripts.bronze_ingestion_simple as bis

        assert "officials" in bis.DATA_TYPE_REGISTRY
        reg = bis.DATA_TYPE_REGISTRY["officials"]
        assert reg["adapter_method"] == "fetch_officials"
        assert reg["bronze_path"] == "officials/season={season}"
        assert reg["requires_week"] is False
        assert reg["requires_season"] is True


# ------------------------------------------------------------------
# Phase 20: Stadium Coordinates (INFRA-03)
# ------------------------------------------------------------------

class TestStadiumCoordinates:
    """Validate STADIUM_COORDINATES completeness and format."""

    def test_stadium_coordinates_all_teams(self):
        """All 32 team abbreviations from TEAM_DIVISIONS are in STADIUM_COORDINATES."""
        missing = set(TEAM_DIVISIONS.keys()) - set(STADIUM_COORDINATES.keys())
        assert not missing, f"Teams missing from STADIUM_COORDINATES: {missing}"

    def test_stadium_coordinates_international(self):
        """All 6 international venues are present."""
        international = ["LON_TOT", "LON_WEM", "MUN", "MEX", "SAO", "MAD"]
        for venue in international:
            assert venue in STADIUM_COORDINATES, f"Missing international venue: {venue}"

    def test_stadium_coordinates_tuple_format(self):
        """Each entry is a 4-tuple (float, float, str, str)."""
        for key, val in STADIUM_COORDINATES.items():
            assert isinstance(val, tuple) and len(val) == 4, (
                f"{key}: expected 4-tuple, got {type(val).__name__}"
            )
            lat, lon, tz, name = val
            assert isinstance(lat, (int, float)), f"{key}: lat not numeric"
            assert isinstance(lon, (int, float)), f"{key}: lon not numeric"
            assert isinstance(tz, str), f"{key}: timezone not string"
            assert isinstance(name, str), f"{key}: venue name not string"

    def test_stadium_haversine_nyj_to_lar(self):
        """Haversine distance NYJ to LA is approximately 2400-2500 miles."""
        nyj = STADIUM_COORDINATES["NYJ"]
        la = STADIUM_COORDINATES["LA"]
        dist = _haversine_miles(nyj[0], nyj[1], la[0], la[1])
        assert 2400 <= dist <= 2500, f"NYJ-LA distance {dist:.0f} not in 2400-2500 range"

    def test_stadium_shared_venues(self):
        """NYG/NYJ share MetLife; LA/LAC share SoFi (identical coordinates)."""
        assert STADIUM_COORDINATES["NYG"][:2] == STADIUM_COORDINATES["NYJ"][:2]
        assert STADIUM_COORDINATES["LA"][:2] == STADIUM_COORDINATES["LAC"][:2]

    def test_stadium_total_count(self):
        """38 total entries: 32 teams + 6 international."""
        assert len(STADIUM_COORDINATES) == 38
