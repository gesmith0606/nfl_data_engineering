"""Tests for the ESPN historical projections backfill (players endpoint).

Covers the pure parsing path (stat-id mapping + our-scoring conversion),
the weeks CLI parser, and the zero-padded Bronze partition contract that
the Silver consolidator depends on (week={WW}).
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "ingest_external_projections_espn",
    _PROJECT_ROOT / "scripts" / "ingest_external_projections_espn.py",
)
espn_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(espn_mod)


def _player_entry(
    name: str,
    pos_id: int,
    team_id: int,
    week: int,
    raw_stats: dict,
    source_id: int = 1,
    split_id: int = 1,
):
    return {
        "player": {
            "id": 12345,
            "fullName": name,
            "defaultPositionId": pos_id,
            "proTeamId": team_id,
            "stats": [
                {
                    "statSourceId": source_id,
                    "statSplitTypeId": split_id,
                    "scoringPeriodId": week,
                    "stats": raw_stats,
                }
            ],
        }
    }


class TestParseHistoricalPayload:
    def test_wr_half_ppr_scoring(self):
        # 5 rec, 80 rec yds, 1 rec TD -> 5*0.5 + 80*0.1 + 6 = 16.5 half-PPR
        payload = [
            _player_entry(
                "Test Receiver", pos_id=3, team_id=12, week=5,
                raw_stats={"53": 5.0, "42": 80.0, "43": 1.0},
            )
        ]
        df = espn_mod._parse_historical_payload(payload, season=2023, week=5, scoring="half_ppr")
        assert len(df) == 1
        row = df.iloc[0]
        assert row["position"] == "WR"
        assert row["projected_points"] == pytest.approx(16.5)
        assert row["source"] == "espn"
        assert row["season"] == 2023 and row["week"] == 5

    def test_qb_scoring_includes_ints_and_two_pt(self):
        # 250 pass yds, 2 pass TD, 1 INT, 1 pass 2pt
        # = 250*0.04 + 2*4 - 2 + 2 = 18.0
        payload = [
            _player_entry(
                "Test Quarterback", pos_id=1, team_id=2, week=3,
                raw_stats={"3": 250.0, "4": 2.0, "20": 1.0, "19": 1.0},
            )
        ]
        df = espn_mod._parse_historical_payload(payload, season=2022, week=3, scoring="half_ppr")
        assert df.iloc[0]["projected_points"] == pytest.approx(18.0)

    def test_actual_stat_entries_are_ignored(self):
        # statSourceId=0 is the ACTUAL stat line — must never leak into
        # the projection Bronze.
        payload = [
            _player_entry(
                "Actuals Only", pos_id=3, team_id=1, week=5,
                raw_stats={"42": 200.0}, source_id=0,
            )
        ]
        df = espn_mod._parse_historical_payload(payload, season=2023, week=5, scoring="half_ppr")
        assert df.empty

    def test_wrong_week_entries_are_ignored(self):
        payload = [
            _player_entry(
                "Wrong Week", pos_id=3, team_id=1, week=4,
                raw_stats={"42": 80.0},
            )
        ]
        df = espn_mod._parse_historical_payload(payload, season=2023, week=5, scoring="half_ppr")
        assert df.empty

    def test_unmapped_position_is_skipped(self):
        payload = [
            _player_entry(
                "Some Defender", pos_id=99, team_id=1, week=5,
                raw_stats={"42": 80.0},
            )
        ]
        df = espn_mod._parse_historical_payload(payload, season=2023, week=5, scoring="half_ppr")
        assert df.empty

    def test_negative_points_clamped_to_zero(self):
        # 3 INTs and nothing else would be negative — invariant clamps to 0.
        payload = [
            _player_entry(
                "Bad Day QB", pos_id=1, team_id=2, week=5,
                raw_stats={"20": 3.0},
            )
        ]
        df = espn_mod._parse_historical_payload(payload, season=2023, week=5, scoring="half_ppr")
        assert df.iloc[0]["projected_points"] == 0.0


class TestParseWeeksArg:
    def test_range(self):
        assert espn_mod._parse_weeks_arg("1-18") == list(range(1, 19))

    def test_list_and_dedupe(self):
        assert espn_mod._parse_weeks_arg("5,3,5") == [3, 5]

    def test_out_of_bounds_dropped(self):
        assert espn_mod._parse_weeks_arg("0,19,7") == [7]


class TestBronzePartitionPadding:
    def test_write_bronze_zero_pads_week(self, tmp_path):
        """The Silver consolidator reads week={WW} — unpadded dirs are
        silently invisible to it (bug found during the 2022-2024 backfill)."""
        df = pd.DataFrame(
            [{"player_name": "X", "player_id": "1", "team": "KC",
              "position": "WR", "projected_points": 1.0,
              "scoring_format": "half_ppr", "source": "espn",
              "season": 2023, "week": 5, "projected_at": "t",
              "raw_payload": "{}"}]
        )
        out = espn_mod._write_bronze(df, out_root=tmp_path, season=2023, week=5)
        assert "week=05" in str(out)
        assert out.exists()
