"""Tests for the live2026 block built from the season scorecard CSV."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest

from generate_frontend_metrics import build_live_section, format_weeks

HEADER = "week,position,n_matched,mae_ours,mae_sleeper,mae_t3,gap,rho_ours,rho_sleeper,band_coverage\n"
ROWS = [
    "1,QB,10,6.0,5.0,7.0,1.0,0.1,0.2,0.5",
    "2,QB,10,6.0,5.0,7.0,1.0,0.1,0.2,0.5",
    "4,QB,10,6.0,5.0,7.0,1.0,0.1,0.2,0.5",  # week 3 has no board
    "ALL,QB,30,6.0,5.0,7.0,1.0,0.1,0.2,0.5",
    "ALL,RB,40,5.0,5.5,6.0,-0.5,0.4,0.3,0.6",
    "ALL,WR,50,5.0,5.0,6.0,0.0,0.3,0.3,0.4",
    "ALL,TE,20,4.0,3.5,5.0,0.5,0.2,0.1,0.3",
    "ALL,ALL,140,5.1,4.9,6.1,0.2,0.3,0.25,0.45",
]


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "scorecard.csv"
    p.write_text(HEADER + "\n".join(ROWS) + "\n")
    return p


def test_frontend_metrics_format_weeks_collapses_runs():
    assert format_weeks([1, 2, 3, 4, 5, 6, 7, 9]) == "1–7, 9"
    assert format_weeks([9, 1]) == "1, 9"
    assert format_weeks([3]) == "3"


def test_frontend_metrics_live_values_and_weeks(csv_path):
    live = build_live_section(csv_path, ats={"value": 1}, updated="2026-11-16")
    assert live["weeks_covered"] == [1, 2, 4]
    assert live["weeks"] == "1–2, 4"
    assert [p["position"] for p in live["positions"]] == ["QB", "RB", "WR", "TE"]
    assert live["overall"]["n"] == 140
    # flat keys for existing consumers mirror the overall row
    assert live["ourMae"] == 5.1 and live["gap"] == 0.2 and live["trailing3Mae"] == 6.1
    rb = live["positions"][1]
    assert rb["gap"] == -0.5 and rb["rhoSleeper"] == 0.3 and rb["bandCoverage"] == 0.6
    assert live["updated"] == "2026-11-16"
    assert live["ats"] == {"value": 1}
    assert live["generated_from"]["path"] == str(csv_path)


def test_frontend_metrics_missing_pooled_row_raises(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text(HEADER + ROWS[0] + "\n")
    with pytest.raises(ValueError):
        build_live_section(p)
