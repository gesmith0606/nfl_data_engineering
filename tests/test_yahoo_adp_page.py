"""Offline tests for the Yahoo Draft Analysis page parser (src/yahoo_adp_page.py)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from src.adp_sources import ADP_COLUMNS
from src.yahoo_adp_page import parse_yahoo_draft_analysis

_TEXT = """Draft Analysis
Player
Avg Pick
Avg Round
% Drafted
Bijan Robinson
Atl - RB
2.3
1.1
99%
Ja'Marr Chase
Cin - WR
3.1
1.2
99%
Christian McCaffrey
Q
SF - RB
6.8
1.5
98%
James Cook III
Buf - RB
12.9
2.0
97%
Texans
Hou - DEF
101.2
9.1
60%
"""


@pytest.mark.unit
def test_parses_rows_with_status_tags_and_defense():
    df = parse_yahoo_draft_analysis(_TEXT)
    assert list(df.columns) == ADP_COLUMNS
    assert df["player_name"].tolist() == [
        "Bijan Robinson", "Ja'Marr Chase", "Christian McCaffrey", "James Cook III", "Texans"
    ]
    assert df["adp"].tolist() == [2.3, 3.1, 6.8, 12.9, 101.2]
    mccaffrey = df.set_index("player_name").loc["Christian McCaffrey"]
    assert mccaffrey["team"] == "SF" and mccaffrey["position"] == "RB"
    assert df.set_index("player_name").loc["Texans", "position"] == "DST"
    assert (df["source"] == "yahoo").all()
    assert df.set_index("player_name").loc["James Cook III", "name_key"] == "james cook"


@pytest.mark.unit
def test_unrecognised_layout_yields_empty_frame():
    assert parse_yahoo_draft_analysis("Nothing\nto\nsee\n1.0\n").empty
    assert parse_yahoo_draft_analysis("").empty
