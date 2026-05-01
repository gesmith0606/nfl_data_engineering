"""
Tests for the lineup builder module.

Covers starter identification from depth charts, snap count integration,
projection joining, field position assignment, and the API endpoint schema.
"""

import os
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from lineup_builder import (
    DEFENSE_STARTER_SLOTS,
    OFFENSE_STARTER_SLOTS,
    _assign_field_position,
    _canonical_team,
    _compute_starter_confidence,
    _normalize_depth_chart_schema,
    _resolve_position_group,
    get_team_lineup_with_projections,
    get_team_starters,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_depth_chart(
    teams=None,
    week=1.0,
    include_defense=True,
):
    """Build a minimal depth chart DataFrame for testing."""
    if teams is None:
        teams = ["KC"]
    rows = []
    for team in teams:
        # Offense starters (depth_team=1)
        offense_starters = [
            ("QB", "QB", "Patrick Mahomes", "00-0001"),
            ("RB", "RB", "Isiah Pacheco", "00-0002"),
            ("RB", "RB", "Clyde Edwards", "00-0003"),
            ("WR", "WR", "Rashee Rice", "00-0004"),
            ("WR", "WR", "Xavier Worthy", "00-0005"),
            ("WR", "WR", "Hollywood Brown", "00-0006"),
            ("TE", "TE", "Travis Kelce", "00-0007"),
            ("K", "K", "Harrison Butker", "00-0008"),
            # Return specialist should be filtered out
            ("WR", "PR", "Mecole Hardman", "00-0009"),
        ]
        for pos, dp, name, gsis in offense_starters:
            rows.append(
                {
                    "season": 2024,
                    "club_code": team,
                    "week": week,
                    "game_type": "REG",
                    "depth_team": "1",
                    "full_name": name,
                    "gsis_id": gsis,
                    "position": pos,
                    "depth_position": dp,
                    "first_name": name.split()[0],
                    "last_name": name.split()[-1],
                    "football_name": name.split()[0],
                    "formation": "",
                    "elias_id": "",
                    "jersey_number": 0,
                }
            )

        # Backups (depth_team=2)
        backups = [
            ("QB", "QB", "Blaine Gabbert", "00-0010"),
            ("RB", "RB", "Jerick McKinnon", "00-0011"),
        ]
        for pos, dp, name, gsis in backups:
            rows.append(
                {
                    "season": 2024,
                    "club_code": team,
                    "week": week,
                    "game_type": "REG",
                    "depth_team": "2",
                    "full_name": name,
                    "gsis_id": gsis,
                    "position": pos,
                    "depth_position": dp,
                    "first_name": name.split()[0],
                    "last_name": name.split()[-1],
                    "football_name": name.split()[0],
                    "formation": "",
                    "elias_id": "",
                    "jersey_number": 0,
                }
            )

        if include_defense:
            defense_starters = [
                ("DE", "LDE", "George Karlaftis", "00-0020"),
                ("DE", "RDE", "Chris Jones", "00-0021"),
                ("DT", "LDT", "Derrick Nnadi", "00-0022"),
                ("DT", "RDT", "Tershawn Wharton", "00-0023"),
                ("LB", "MIKE", "Nick Bolton", "00-0024"),
                ("LB", "WILL", "Willie Gay", "00-0025"),
                ("LB", "SAM", "Drue Tranquill", "00-0026"),
                ("CB", "LCB", "Trent McDuffie", "00-0027"),
                ("CB", "RCB", "Jaylen Watson", "00-0028"),
                ("S", "FS", "Justin Reid", "00-0029"),
                ("S", "SS", "Bryan Cook", "00-0030"),
            ]
            for pos, dp, name, gsis in defense_starters:
                rows.append(
                    {
                        "season": 2024,
                        "club_code": team,
                        "week": week,
                        "game_type": "REG",
                        "depth_team": "1",
                        "full_name": name,
                        "gsis_id": gsis,
                        "position": pos,
                        "depth_position": dp,
                        "first_name": name.split()[0],
                        "last_name": name.split()[-1],
                        "football_name": name.split()[0],
                        "formation": "",
                        "elias_id": "",
                        "jersey_number": 0,
                    }
                )

    return pd.DataFrame(rows)


def _make_snap_counts(team="KC", week=1):
    """Build snap count data matching the depth chart fixture."""
    return pd.DataFrame(
        [
            {
                "team": team,
                "player": "Patrick Mahomes",
                "offense_pct": 100.0,
                "week": week,
            },
            {
                "team": team,
                "player": "Isiah Pacheco",
                "offense_pct": 65.0,
                "week": week,
            },
            {
                "team": team,
                "player": "Clyde Edwards",
                "offense_pct": 30.0,
                "week": week,
            },
            {"team": team, "player": "Rashee Rice", "offense_pct": 88.0, "week": week},
            {
                "team": team,
                "player": "Xavier Worthy",
                "offense_pct": 75.0,
                "week": week,
            },
            {
                "team": team,
                "player": "Hollywood Brown",
                "offense_pct": 60.0,
                "week": week,
            },
            {"team": team, "player": "Travis Kelce", "offense_pct": 82.0, "week": week},
            {
                "team": team,
                "player": "Harrison Butker",
                "offense_pct": 0.0,
                "week": week,
            },
        ]
    )


def _make_projections(team="KC", week=1):
    """Build Gold projections matching the depth chart fixture."""
    return pd.DataFrame(
        [
            {
                "player_id": "00-0001",
                "player_name": "Patrick Mahomes",
                "recent_team": team,
                "position": "QB",
                "projected_points": 22.4,
                "projected_floor": 18.1,
                "projected_ceiling": 28.7,
                "season": 2024,
                "week": week,
            },
            {
                "player_id": "00-0002",
                "player_name": "Isiah Pacheco",
                "recent_team": team,
                "position": "RB",
                "projected_points": 12.8,
                "projected_floor": 8.2,
                "projected_ceiling": 18.4,
                "season": 2024,
                "week": week,
            },
            {
                "player_id": "00-0004",
                "player_name": "Rashee Rice",
                "recent_team": team,
                "position": "WR",
                "projected_points": 14.2,
                "projected_floor": 9.1,
                "projected_ceiling": 20.3,
                "season": 2024,
                "week": week,
            },
            {
                "player_id": "00-0007",
                "player_name": "Travis Kelce",
                "recent_team": team,
                "position": "TE",
                "projected_points": 13.1,
                "projected_floor": 8.8,
                "projected_ceiling": 18.4,
                "season": 2024,
                "week": week,
            },
        ]
    )


# ---------------------------------------------------------------------------
# Test: Position group resolution
# ---------------------------------------------------------------------------


class TestResolvePositionGroup(unittest.TestCase):
    """Test _resolve_position_group mapping."""

    def test_standard_positions(self):
        self.assertEqual(_resolve_position_group("QB", "QB"), "QB")
        self.assertEqual(_resolve_position_group("WR", "WR"), "WR")
        self.assertEqual(_resolve_position_group("K", "K"), "K")

    def test_defensive_granular_positions(self):
        self.assertEqual(_resolve_position_group("LDE", "DE"), "DE")
        self.assertEqual(_resolve_position_group("RDE", "DE"), "DE")
        self.assertEqual(_resolve_position_group("LCB", "CB"), "CB")
        self.assertEqual(_resolve_position_group("MIKE", "LB"), "LB")
        self.assertEqual(_resolve_position_group("FS", "S"), "S")
        self.assertEqual(_resolve_position_group("NT", "DT"), "DT")

    def test_return_specialist_maps_to_wr(self):
        self.assertEqual(_resolve_position_group("PR", "WR"), "WR")
        self.assertEqual(_resolve_position_group("KR", "WR"), "WR")

    def test_fallback_to_position(self):
        self.assertEqual(_resolve_position_group("UNKNOWN", "QB"), "QB")

    def test_unrecognized_returns_raw(self):
        self.assertEqual(_resolve_position_group("UNKNOWN", "UNKNOWN"), "UNKNOWN")


# ---------------------------------------------------------------------------
# Test: Field position assignment
# ---------------------------------------------------------------------------


class TestAssignFieldPosition(unittest.TestCase):
    """Test _assign_field_position layout labels."""

    def test_qb(self):
        self.assertEqual(_assign_field_position("QB", 1), "qb")

    def test_wr_slots(self):
        self.assertEqual(_assign_field_position("WR", 1), "wr_left")
        self.assertEqual(_assign_field_position("WR", 2), "wr_right")
        self.assertEqual(_assign_field_position("WR", 3), "wr_slot")

    def test_rb(self):
        self.assertEqual(_assign_field_position("RB", 1), "rb")
        self.assertEqual(_assign_field_position("RB", 2), "rb_2")

    def test_defense(self):
        self.assertEqual(_assign_field_position("DE", 1), "edge_left")
        self.assertEqual(_assign_field_position("DE", 2), "edge_right")
        self.assertEqual(_assign_field_position("CB", 1), "cb_left")
        self.assertEqual(_assign_field_position("CB", 2), "cb_right")
        self.assertEqual(_assign_field_position("S", 1), "s_left")
        self.assertEqual(_assign_field_position("LB", 2), "lb_mid")

    def test_te_and_k(self):
        self.assertEqual(_assign_field_position("TE", 1), "te")
        self.assertEqual(_assign_field_position("K", 1), "k")


# ---------------------------------------------------------------------------
# Test: Starter confidence scoring
# ---------------------------------------------------------------------------


class TestStarterConfidence(unittest.TestCase):
    """Test _compute_starter_confidence heuristic."""

    def test_depth_starter_with_high_snaps(self):
        conf = _compute_starter_confidence(True, 90.0)
        self.assertGreater(conf, 0.85)
        self.assertLessEqual(conf, 1.0)

    def test_depth_starter_no_snaps(self):
        conf = _compute_starter_confidence(True, None)
        self.assertAlmostEqual(conf, 0.70)

    def test_not_starter_high_snaps(self):
        conf = _compute_starter_confidence(False, 80.0)
        self.assertAlmostEqual(conf, 0.65)

    def test_not_starter_no_snaps(self):
        conf = _compute_starter_confidence(False, None)
        self.assertAlmostEqual(conf, 0.40)

    def test_depth_starter_borderline_snaps(self):
        conf = _compute_starter_confidence(True, 50.0)
        self.assertGreaterEqual(conf, 0.85)


# ---------------------------------------------------------------------------
# Test: get_team_starters
# ---------------------------------------------------------------------------


class TestGetTeamStarters(unittest.TestCase):
    """Test starter identification from depth charts."""

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_identifies_offensive_starters(self, mock_dc, mock_sc):
        mock_dc.return_value = _make_depth_chart(include_defense=False)
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2024, 1, team="KC")

        self.assertFalse(result.empty)
        self.assertTrue(all(result["is_starter"]))
        self.assertTrue(all(result["team"] == "KC"))

        # Should have QB, 2 RB, 3 WR (excl PR), 1 TE, 1 K = 8
        self.assertEqual(len(result), 8)

        pos_groups = result["position_group"].value_counts()
        self.assertEqual(pos_groups.get("QB", 0), 1)
        self.assertEqual(pos_groups.get("RB", 0), 2)
        self.assertEqual(pos_groups.get("WR", 0), 3)
        self.assertEqual(pos_groups.get("TE", 0), 1)
        self.assertEqual(pos_groups.get("K", 0), 1)

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_filters_return_specialists(self, mock_dc, mock_sc):
        mock_dc.return_value = _make_depth_chart(include_defense=False)
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2024, 1, team="KC")

        # Mecole Hardman (PR) should be excluded
        names = result["player_name"].tolist()
        self.assertNotIn("Mecole Hardman", names)

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_includes_defense(self, mock_dc, mock_sc):
        mock_dc.return_value = _make_depth_chart(include_defense=True)
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2024, 1, team="KC")

        offense = result[result["side"] == "offense"]
        defense = result[result["side"] == "defense"]
        self.assertEqual(len(offense), 8)
        self.assertEqual(len(defense), 11)

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_snap_counts_integrated(self, mock_dc, mock_sc):
        mock_dc.return_value = _make_depth_chart(include_defense=False)
        mock_sc.return_value = _make_snap_counts()

        result = get_team_starters(2024, 1, team="KC")

        # Mahomes should have snap_pct = 100
        qb = result[result["position_group"] == "QB"]
        self.assertEqual(len(qb), 1)
        self.assertAlmostEqual(qb.iloc[0]["snap_pct"], 100.0)

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_all_teams(self, mock_dc, mock_sc):
        mock_dc.return_value = _make_depth_chart(
            teams=["KC", "BUF"], include_defense=False
        )
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2024, 1)

        teams = sorted(result["team"].unique())
        self.assertEqual(teams, ["BUF", "KC"])

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_empty_depth_chart(self, mock_dc, mock_sc):
        mock_dc.return_value = pd.DataFrame()
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2024, 1)

        self.assertTrue(result.empty)

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_field_positions_assigned(self, mock_dc, mock_sc):
        mock_dc.return_value = _make_depth_chart(include_defense=False)
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2024, 1, team="KC")

        self.assertIn("field_position", result.columns)
        qb_fp = result[result["position_group"] == "QB"]["field_position"].iloc[0]
        self.assertEqual(qb_fp, "qb")

        wr_fps = sorted(
            result[result["position_group"] == "WR"]["field_position"].tolist()
        )
        self.assertTrue(set(wr_fps).issubset({"wr_left", "wr_right", "wr_slot"}))

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_uses_latest_week(self, mock_dc, mock_sc):
        """Depth chart from week 3 should be used when asking for week 5."""
        dc_w1 = _make_depth_chart(week=1.0, include_defense=False)
        dc_w3 = _make_depth_chart(week=3.0, include_defense=False)
        # Change QB in week 3
        dc_w3.loc[dc_w3["position"] == "QB", "full_name"] = "Backup QB"
        combined = pd.concat([dc_w1, dc_w3], ignore_index=True)
        mock_dc.return_value = combined
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2024, 5, team="KC")

        qb = result[result["position_group"] == "QB"]
        self.assertEqual(qb.iloc[0]["player_name"], "Backup QB")

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_backups_excluded(self, mock_dc, mock_sc):
        mock_dc.return_value = _make_depth_chart(include_defense=False)
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2024, 1, team="KC")

        names = result["player_name"].tolist()
        self.assertNotIn("Blaine Gabbert", names)
        self.assertNotIn("Jerick McKinnon", names)


# ---------------------------------------------------------------------------
# Test: get_team_lineup_with_projections
# ---------------------------------------------------------------------------


class TestGetTeamLineupWithProjections(unittest.TestCase):
    """Test projection joining."""

    @patch("lineup_builder._load_projections")
    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_joins_projections(self, mock_dc, mock_sc, mock_proj):
        mock_dc.return_value = _make_depth_chart(include_defense=False)
        mock_sc.return_value = pd.DataFrame()
        mock_proj.return_value = _make_projections()

        result = get_team_lineup_with_projections(2024, 1, "KC")

        self.assertIn("projected_points", result.columns)

        qb = result[result["position_group"] == "QB"]
        self.assertAlmostEqual(qb.iloc[0]["projected_points"], 22.4)

        te = result[result["position_group"] == "TE"]
        self.assertAlmostEqual(te.iloc[0]["projected_points"], 13.1)

    @patch("lineup_builder._load_projections")
    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_missing_projection_is_nan(self, mock_dc, mock_sc, mock_proj):
        mock_dc.return_value = _make_depth_chart(include_defense=False)
        mock_sc.return_value = pd.DataFrame()
        mock_proj.return_value = _make_projections()

        result = get_team_lineup_with_projections(2024, 1, "KC")

        # Kicker has no projection in fixture
        k = result[result["position_group"] == "K"]
        self.assertTrue(pd.isna(k.iloc[0]["projected_points"]))

    @patch("lineup_builder._load_projections")
    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_no_projections_available(self, mock_dc, mock_sc, mock_proj):
        mock_dc.return_value = _make_depth_chart(include_defense=False)
        mock_sc.return_value = pd.DataFrame()
        mock_proj.return_value = pd.DataFrame()

        result = get_team_lineup_with_projections(2024, 1, "KC")

        self.assertIn("projected_points", result.columns)
        self.assertTrue(result["projected_points"].isna().all())


# ---------------------------------------------------------------------------
# Test: API response schema (unit test without running server)
# ---------------------------------------------------------------------------


class TestAPISchema(unittest.TestCase):
    """Test that the Pydantic models accept valid data."""

    def test_lineup_player_model(self):
        from web.api.models.schemas import LineupPlayer

        player = LineupPlayer(
            player_id="00-0001",
            player_name="Patrick Mahomes",
            position="QB",
            position_group="QB",
            field_position="qb",
            projected_points=22.4,
            projected_floor=18.1,
            projected_ceiling=28.7,
            snap_pct=100.0,
            depth_rank=1,
            is_starter=True,
            starter_confidence=0.95,
        )
        self.assertEqual(player.player_name, "Patrick Mahomes")
        self.assertEqual(player.field_position, "qb")

    def test_team_lineup_model(self):
        from web.api.models.schemas import LineupPlayer, TeamLineup

        player = LineupPlayer(
            player_id="00-0001",
            player_name="Patrick Mahomes",
            position="QB",
            position_group="QB",
            field_position="qb",
            depth_rank=1,
            is_starter=True,
            starter_confidence=0.95,
        )
        lineup = TeamLineup(
            team="KC",
            season=2024,
            week=1,
            offense=[player],
            defense=[],
            team_projected_total=90.7,
        )
        self.assertEqual(lineup.team, "KC")
        self.assertEqual(len(lineup.offense), 1)
        self.assertIsNone(lineup.implied_total)

    def test_lineup_player_optional_fields(self):
        from web.api.models.schemas import LineupPlayer

        player = LineupPlayer(
            player_id="00-0001",
            player_name="Test Player",
            position="K",
            position_group="K",
            field_position="k",
            depth_rank=1,
            is_starter=True,
            starter_confidence=0.70,
        )
        self.assertIsNone(player.projected_points)
        self.assertIsNone(player.snap_pct)


# ---------------------------------------------------------------------------
# Test: Starter slot counts
# ---------------------------------------------------------------------------


def _make_new_schema_depth_chart_normalized(team="KC"):
    """Build a depth chart that mirrors what `_normalize_depth_chart_schema`
    emits for the post-2025 ESPN/Sleeper Bronze parquets.

    Key difference from the legacy fixture: depth_team is a strict 1/2/3
    ordinal per pos_abb — only ONE player has depth_team=1 at WR; the
    second and third "starting" WRs sit at depth_team=2 and 3.
    """
    rows = [
        # 3 WRs at strict depth ranks 1, 2, 3 — all should be picked as starters.
        ("WR", "WR", "Rashee Rice", "00-1", 1),
        ("WR", "WR", "Xavier Worthy", "00-2", 2),
        ("WR", "WR", "Hollywood Brown", "00-3", 3),
        # 2 RBs at strict ranks 1, 2.
        ("RB", "RB", "Isiah Pacheco", "00-4", 1),
        ("RB", "RB", "Clyde Edwards", "00-5", 2),
        # Singles fill out the rest of the offense.
        ("QB", "QB", "Patrick Mahomes", "00-6", 1),
        ("TE", "TE", "Travis Kelce", "00-7", 1),
        ("K", "PK", "Harrison Butker", "00-8", 1),
        # Backup WR at rank 4 — should NOT make the cut.
        ("WR", "WR", "Justin Watson", "00-9", 4),
    ]
    return pd.DataFrame(
        [
            {
                "club_code": team,
                "full_name": name,
                "gsis_id": gsis,
                "position": pos,
                "depth_position": dp,
                "depth_team": rank,  # int, as new schema emits
                "week": 1,
            }
            for pos, dp, name, gsis, rank in rows
        ]
    )


class TestNewSchemaStarterSelection(unittest.TestCase):
    """Verify starter selection under the strict-rank schema (2025+ Bronze)."""

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_picks_top3_wrs_across_ranks_1_2_3(self, mock_dc, mock_sc):
        # New schema: 3 WRs at depth_team={1,2,3}, plus a depth=4 backup.
        mock_dc.return_value = _make_new_schema_depth_chart_normalized()
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2026, 1, team="KC")
        wrs = result[result["position_group"] == "WR"]
        self.assertEqual(len(wrs), 3)
        names = set(wrs["player_name"])
        self.assertEqual(
            names, {"Rashee Rice", "Xavier Worthy", "Hollywood Brown"}
        )
        self.assertNotIn("Justin Watson", names)  # rank-4 excluded

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_picks_top2_rbs_across_ranks_1_2(self, mock_dc, mock_sc):
        mock_dc.return_value = _make_new_schema_depth_chart_normalized()
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2026, 1, team="KC")
        rbs = result[result["position_group"] == "RB"]
        self.assertEqual(len(rbs), 2)
        # Field positions assigned in order — first picked = rb, second = rb_2.
        self.assertEqual(set(rbs["field_position"]), {"rb", "rb_2"})


class TestCommitteeAtDepthOne(unittest.TestCase):
    """Legacy schema: when more players carry depth_team=1 than max_slots,
    snap_pct breaks the tie."""

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_picks_top_two_by_snap_pct_when_three_at_depth_one(
        self, mock_dc, mock_sc
    ):
        # 3 RBs all at depth_team=1; max_slots=2. Snap counts decide.
        rows = []
        for name, gsis, snap_pct in [
            ("Workhorse Walker", "00-A", 78.0),
            ("Committee Carter", "00-B", 55.0),
            ("Third Wheel Tyler", "00-C", 22.0),
        ]:
            rows.append(
                {
                    "club_code": "KC",
                    "full_name": name,
                    "gsis_id": gsis,
                    "position": "RB",
                    "depth_position": "RB",
                    "depth_team": "1",
                    "week": 1.0,
                }
            )
        # Round out the rest of the lineup so the function returns a frame.
        rows.append(
            {
                "club_code": "KC",
                "full_name": "Patrick Mahomes",
                "gsis_id": "00-Q",
                "position": "QB",
                "depth_position": "QB",
                "depth_team": "1",
                "week": 1.0,
            }
        )
        mock_dc.return_value = pd.DataFrame(rows)
        mock_sc.return_value = pd.DataFrame(
            [
                {
                    "team": "KC",
                    "player": "Workhorse Walker",
                    "offense_pct": 78.0,
                    "week": 1,
                },
                {
                    "team": "KC",
                    "player": "Committee Carter",
                    "offense_pct": 55.0,
                    "week": 1,
                },
                {
                    "team": "KC",
                    "player": "Third Wheel Tyler",
                    "offense_pct": 22.0,
                    "week": 1,
                },
            ]
        )

        result = get_team_starters(2024, 1, team="KC")
        rbs = result[result["position_group"] == "RB"]
        self.assertEqual(len(rbs), 2)
        names = list(rbs["player_name"])
        # Highest snap_pct picked first → Workhorse, then Committee.
        self.assertEqual(names[0], "Workhorse Walker")
        self.assertEqual(names[1], "Committee Carter")
        self.assertNotIn("Third Wheel Tyler", names)


class TestSingleRbTeam(unittest.TestCase):
    """A team with exactly one rostered RB must not emit an rb_2 field row."""

    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_no_rb_2_field_position_when_only_one_rb(self, mock_dc, mock_sc):
        rows = [
            {
                "club_code": "KC",
                "full_name": "Lone Ranger",
                "gsis_id": "00-RB1",
                "position": "RB",
                "depth_position": "RB",
                "depth_team": "1",
                "week": 1.0,
            },
            {
                "club_code": "KC",
                "full_name": "Patrick Mahomes",
                "gsis_id": "00-Q",
                "position": "QB",
                "depth_position": "QB",
                "depth_team": "1",
                "week": 1.0,
            },
        ]
        mock_dc.return_value = pd.DataFrame(rows)
        mock_sc.return_value = pd.DataFrame()

        result = get_team_starters(2024, 1, team="KC")
        rbs = result[result["position_group"] == "RB"]
        self.assertEqual(len(rbs), 1)
        self.assertEqual(rbs.iloc[0]["field_position"], "rb")
        # No rb_2 anywhere in the result.
        self.assertNotIn("rb_2", set(result["field_position"]))


class TestNormalizeDepthChartSchema(unittest.TestCase):
    """Verify the post-draft ESPN/Sleeper schema is translated to nflverse."""

    def test_passes_through_legacy_schema(self):
        legacy = pd.DataFrame(
            {
                "club_code": ["KC"],
                "full_name": ["Patrick Mahomes"],
                "position": ["QB"],
                "depth_position": ["QB"],
                "depth_team": [1],
                "week": [1.0],
                "gsis_id": ["00-0001"],
            }
        )
        out = _normalize_depth_chart_schema(legacy)
        # Identity for legacy frames — no rename.
        self.assertIn("club_code", out.columns)
        self.assertIn("week", out.columns)
        self.assertEqual(len(out), 1)

    def test_renames_new_schema_columns(self):
        new = pd.DataFrame(
            {
                "dt": ["2026-04-30T09:11:25Z"],
                "team": ["KC"],
                "player_name": ["Patrick Mahomes"],
                "gsis_id": ["00-0001"],
                "pos_grp": ["3WR 1TE"],
                "pos_abb": ["QB"],
                "pos_rank": [1],
            }
        )
        out = _normalize_depth_chart_schema(new)
        self.assertIn("club_code", out.columns)
        self.assertIn("full_name", out.columns)
        self.assertIn("depth_position", out.columns)
        self.assertIn("depth_team", out.columns)
        self.assertIn("position", out.columns)
        self.assertIn("week", out.columns)
        self.assertEqual(out.iloc[0]["club_code"], "KC")
        self.assertEqual(out.iloc[0]["full_name"], "Patrick Mahomes")
        self.assertEqual(out.iloc[0]["depth_position"], "QB")
        self.assertEqual(int(out.iloc[0]["depth_team"]), 1)
        self.assertEqual(int(out.iloc[0]["week"]), 1)

    def test_partial_migration_treated_as_unrecognized(self):
        # Frame that has `club_code` (looks legacy-ish) but is missing `week`
        # and the other legacy fields — must NOT be treated as legacy and must
        # NOT be silently coerced into a malformed nflverse-shaped result.
        partial = pd.DataFrame(
            {
                "club_code": ["KC"],
                "full_name": ["Patrick Mahomes"],
                # missing: depth_position, depth_team, week
            }
        )
        out = _normalize_depth_chart_schema(partial)
        # Helper logs a warning and returns the frame untouched, leaving the
        # caller to fail loudly when it tries to read missing columns.
        self.assertNotIn("depth_position", out.columns)
        self.assertNotIn("week", out.columns)
        # Original columns preserved (no spurious renames).
        self.assertIn("club_code", out.columns)
        self.assertIn("full_name", out.columns)

    def test_collapses_repeated_snapshots(self):
        # Same player, two snapshots — keep latest dt.
        new = pd.DataFrame(
            {
                "dt": [
                    "2026-04-29T09:11:25Z",
                    "2026-04-30T09:11:25Z",
                ],
                "team": ["KC", "KC"],
                "player_name": ["Patrick Mahomes", "Patrick Mahomes"],
                "gsis_id": ["00-0001", "00-0001"],
                "pos_grp": ["3WR 1TE", "3WR 1TE"],
                "pos_abb": ["QB", "QB"],
                "pos_rank": [1, 1],
            }
        )
        out = _normalize_depth_chart_schema(new)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["dt"], "2026-04-30T09:11:25Z")


class TestStaleProjectionGuard(unittest.TestCase):
    """When the depth chart's team disagrees with the projection's team for
    a given player_id, the projection is treated as stale (e.g. player was
    traded post-write) and zeroed out so the UI shows '--' instead of a
    misleading number rooted in the prior team's role."""

    @patch("lineup_builder._load_projections")
    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_drops_projection_when_team_mismatches(
        self, mock_dc, mock_sc, mock_proj
    ):
        # Depth chart: Willis listed at MIA.
        dc = pd.DataFrame(
            [
                {
                    "club_code": "MIA",
                    "full_name": "Malik Willis",
                    "gsis_id": "00-X",
                    "position": "QB",
                    "depth_position": "QB",
                    "depth_team": "1",
                    "week": 1.0,
                }
            ]
        )
        mock_dc.return_value = dc
        mock_sc.return_value = pd.DataFrame()

        # Projection still has Willis on GB — this is the stale row.
        mock_proj.return_value = pd.DataFrame(
            [
                {
                    "player_id": "00-X",
                    "player_name": "Malik Willis",
                    "team": "GB",
                    "projected_points": 53.8,
                    "projected_floor": 29.6,
                    "projected_ceiling": 78.0,
                }
            ]
        )

        result = get_team_lineup_with_projections(
            season=2026, week=1, team="MIA", scoring_format="half_ppr"
        )
        # Projection columns should be NaN (stale dropped); player still
        # appears in the lineup so the UI doesn't lose the slot.
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["player_name"], "Malik Willis")
        self.assertTrue(pd.isna(result.iloc[0]["projected_points"]))
        self.assertTrue(pd.isna(result.iloc[0]["projected_floor"]))
        self.assertTrue(pd.isna(result.iloc[0]["projected_ceiling"]))
        # The internal `_proj_team` helper column must not leak through.
        self.assertNotIn("_proj_team", result.columns)

    @patch("lineup_builder._load_projections")
    @patch("lineup_builder._load_snap_counts")
    @patch("lineup_builder._load_depth_charts")
    def test_alias_does_not_false_positive(self, mock_dc, mock_sc, mock_proj):
        # Depth chart says KC; projection file has him as KAN — same team,
        # alias drift only. Projection must survive.
        dc = pd.DataFrame(
            [
                {
                    "club_code": "KC",
                    "full_name": "Emmett Johnson",
                    "gsis_id": "00-EJ",
                    "position": "RB",
                    "depth_position": "RB",
                    "depth_team": "1",
                    "week": 1.0,
                }
            ]
        )
        mock_dc.return_value = dc
        mock_sc.return_value = pd.DataFrame()
        mock_proj.return_value = pd.DataFrame(
            [
                {
                    "player_id": "00-EJ",
                    "player_name": "Emmett Johnson",
                    "team": "KAN",  # alias of KC
                    "projected_points": 83.0,
                    "projected_floor": 49.8,
                    "projected_ceiling": 116.2,
                }
            ]
        )

        result = get_team_lineup_with_projections(
            season=2026, week=1, team="KC", scoring_format="half_ppr"
        )
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result.iloc[0]["projected_points"], 83.0)


class TestCanonicalTeam(unittest.TestCase):
    """Verify alias normalization for known team-code variants."""

    def test_aliases_normalize(self):
        self.assertEqual(_canonical_team("KAN"), "KC")
        self.assertEqual(_canonical_team("LAR"), "LA")
        self.assertEqual(_canonical_team("LVR"), "LV")
        self.assertEqual(_canonical_team("NOR"), "NO")
        self.assertEqual(_canonical_team("NWE"), "NE")
        self.assertEqual(_canonical_team("SFO"), "SF")
        self.assertEqual(_canonical_team("TAM"), "TB")

    def test_canonical_passthrough(self):
        self.assertEqual(_canonical_team("KC"), "KC")
        self.assertEqual(_canonical_team("PHI"), "PHI")
        self.assertEqual(_canonical_team("LAC"), "LAC")  # not aliased to LA

    def test_handles_lowercase_and_whitespace(self):
        self.assertEqual(_canonical_team(" kc "), "KC")
        self.assertEqual(_canonical_team("kan"), "KC")

    def test_handles_none_and_empty(self):
        self.assertEqual(_canonical_team(None), "")
        self.assertEqual(_canonical_team(""), "")


class TestStarterSlots(unittest.TestCase):
    """Verify expected starter slot configurations."""

    def test_offense_slots(self):
        self.assertEqual(OFFENSE_STARTER_SLOTS["QB"], 1)
        self.assertEqual(OFFENSE_STARTER_SLOTS["RB"], 2)
        self.assertEqual(OFFENSE_STARTER_SLOTS["WR"], 3)
        self.assertEqual(OFFENSE_STARTER_SLOTS["TE"], 1)
        self.assertEqual(OFFENSE_STARTER_SLOTS["K"], 1)

    def test_defense_slots(self):
        self.assertEqual(DEFENSE_STARTER_SLOTS["DE"], 2)
        self.assertEqual(DEFENSE_STARTER_SLOTS["DT"], 2)
        self.assertEqual(DEFENSE_STARTER_SLOTS["LB"], 3)
        self.assertEqual(DEFENSE_STARTER_SLOTS["CB"], 2)
        self.assertEqual(DEFENSE_STARTER_SLOTS["S"], 2)


if __name__ == "__main__":
    unittest.main()
