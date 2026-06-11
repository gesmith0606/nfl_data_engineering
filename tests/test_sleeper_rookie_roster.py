"""Tests for src/sleeper_rookie_roster.py (2026 rookie roster supplement).

All tests mock the Sleeper API fetch — no live network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from sleeper_rookie_roster import build_sleeper_rookie_supplement  # noqa: E402


def _sleeper_payload() -> Dict[str, Dict[str, Any]]:
    """Minimal Sleeper /v1/players/nfl payload with edge cases."""
    return {
        "1001": {
            "full_name": "Jeremiyah Love",
            "first_name": "Jeremiyah",
            "last_name": "Love",
            "position": "RB",
            "team": "ARI",
            "years_exp": 0,
            "status": "Active",
            "number": 4,
            "age": 21,
        },
        "1002": {
            "full_name": "Veteran Back",
            "position": "RB",
            "team": "KC",
            "years_exp": 3,  # not a rookie — excluded
            "status": "Active",
        },
        "1003": {
            "full_name": "Unsigned Udfa",
            "position": "WR",
            "team": None,  # no team — excluded
            "years_exp": 0,
            "status": "Active",
        },
        "1004": {
            "full_name": "Practice Squadder",
            "position": "WR",
            "team": "SEA",
            "years_exp": 0,
            "status": "PracticeSquad",  # coerces to ACT by design
        },
        "1005": {
            "full_name": "Already Rostered",
            "position": "TE",
            "team": "DAL",
            "years_exp": 0,
            "status": "Active",
        },
    }


def _draft_picks() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "pfr_player_name": "Jeremiyah Love",
                "gsis_id": "LOV121782",
                "pick": 23,
            }
        ]
    )


@pytest.fixture
def mock_fetch():
    with patch(
        "sleeper_rookie_roster._fetch_sleeper_players",
        return_value=_sleeper_payload(),
    ) as m:
        yield m


def test_basic_supplement_includes_rookies(mock_fetch):
    df = build_sleeper_rookie_supplement(2026, existing_player_ids=set())
    names = set(df["player_name"])
    assert "Jeremiyah Love" in names
    assert "Practice Squadder" in names  # PS rookies kept, status=ACT
    assert "Veteran Back" not in names  # years_exp != 0
    assert "Unsigned Udfa" not in names  # no team
    assert (df["years_exp"] == 0).all()
    assert (df["season"] == 2026).all()


def test_gsis_id_and_pick_from_draft_picks(mock_fetch):
    df = build_sleeper_rookie_supplement(
        2026, existing_player_ids=set(), draft_picks_df=_draft_picks()
    )
    love = df[df["player_name"] == "Jeremiyah Love"].iloc[0]
    assert love["player_id"] == "LOV121782"
    assert love["draft_number"] == 23.0
    # Players absent from draft_picks fall back to SLP- ids
    ps = df[df["player_name"] == "Practice Squadder"].iloc[0]
    assert str(ps["player_id"]).startswith("SLP-")


def test_dedup_by_player_id(mock_fetch):
    df = build_sleeper_rookie_supplement(
        2026,
        existing_player_ids={"LOV121782"},
        draft_picks_df=_draft_picks(),
    )
    assert "Jeremiyah Love" not in set(df["player_name"])


def test_dedup_by_name_and_position(mock_fetch):
    """The id-format-mismatch guard: same human under a canonical nflverse id.

    Once nfl-data-py ingests the draft class, Jeremiyah Love exists in
    roster_df under 00-0XXXXXX — disjoint from the supplement's short id, so
    only the name+position key can catch the duplicate.
    """
    df = build_sleeper_rookie_supplement(
        2026,
        existing_player_ids={"00-0039420"},  # Love's future canonical id
        draft_picks_df=_draft_picks(),
        existing_player_names={"jeremiyah love|RB"},
    )
    assert "Jeremiyah Love" not in set(df["player_name"])
    # Different position with same name would NOT be skipped
    assert "Practice Squadder" in set(df["player_name"])


def test_practice_squad_status_coerced_to_act(mock_fetch):
    df = build_sleeper_rookie_supplement(2026, existing_player_ids=set())
    ps = df[df["player_name"] == "Practice Squadder"].iloc[0]
    assert ps["status"] == "ACT"


def test_headshot_url_is_sleeper_cdn(mock_fetch):
    df = build_sleeper_rookie_supplement(2026, existing_player_ids=set())
    love = df[df["player_name"] == "Jeremiyah Love"].iloc[0]
    assert love["headshot_url"] == (
        "https://sleepercdn.com/content/nfl/players/thumb/1001.jpg"
    )


def test_fail_open_on_network_error():
    with patch(
        "sleeper_rookie_roster._fetch_sleeper_players",
        side_effect=ConnectionError("simulated outage"),
    ):
        df = build_sleeper_rookie_supplement(2026, existing_player_ids=set())
    assert df.empty
