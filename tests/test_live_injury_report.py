"""Unit tests for projection_engine.live_injury_report.

The NFL's official report for week N lands on the Wednesday of that week, so a
Tuesday projection run sees no Bronze rows for its own week. Before this
fallback existed the run treated that gap as "everyone Active": the 2026 week-7
board carried all 376 rows at injury_multiplier 1.0, projecting Lamar Jackson
(out since week 4) and Tyler Huntley, his replacement, as simultaneous QB1s.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection_engine import (  # noqa: E402
    apply_injury_adjustments,
    live_injury_report,
)


def _p(gsis, status):
    return {"gsis_id": gsis, "injury_status": status}


REGISTRY = {
    "1": _p("00-0034796", "Out"),
    "2": _p("00-0035710", "IR"),
    "3": _p("00-0036355", "PUP"),
    "4": _p("00-0037013", "Doubtful"),
    "5": _p("00-0038122", "Questionable"),
    "6": _p("00-0039001", None),
    "7": _p(None, "Out"),
    "8": _p("00-0039500", "Sus"),
}


def test_blocking_statuses_map_to_out():
    df = live_injury_report(REGISTRY).set_index("gsis_id")["report_status"]
    for gsis in ("00-0034796", "00-0035710", "00-0036355", "00-0039500"):
        assert df[gsis] == "Out"


def test_softer_statuses_keep_their_own_grade():
    df = live_injury_report(REGISTRY).set_index("gsis_id")["report_status"]
    assert df["00-0037013"] == "Doubtful"
    assert df["00-0038122"] == "Questionable"


def test_healthy_and_idless_players_are_dropped():
    df = live_injury_report(REGISTRY)
    assert "00-0039001" not in set(df.gsis_id)
    assert df.gsis_id.notna().all()
    assert len(df) == 6


def test_empty_registry_yields_empty_frame_with_schema():
    df = live_injury_report({})
    assert df.empty
    assert list(df.columns) == ["gsis_id", "report_status"]


def test_junk_entries_are_skipped():
    assert live_injury_report({"a": None, "b": "junk", "c": 7}).empty


def test_output_feeds_apply_injury_adjustments():
    """The frame is shaped for the consumer that needed it."""
    proj = pd.DataFrame(
        {
            "player_id": ["00-0034796", "00-0038122", "00-0039001"],
            "player_name": ["Out Guy", "Q Guy", "Healthy Guy"],
            "position": ["QB", "RB", "WR"],
            "projected_points": [20.0, 10.0, 12.0],
        }
    )
    live = live_injury_report(REGISTRY)
    out = apply_injury_adjustments(proj, live)
    by_name = out.set_index("player_name")
    assert by_name.loc["Out Guy", "projected_points"] == 0.0
    assert by_name.loc["Out Guy", "injury_multiplier"] == 0.0
    assert by_name.loc["Healthy Guy", "injury_multiplier"] == 1.0
    assert by_name.loc["Healthy Guy", "projected_points"] == 12.0
    # A Questionable player is discounted, not zeroed.
    assert 0.0 < by_name.loc["Q Guy", "injury_multiplier"] <= 1.0
