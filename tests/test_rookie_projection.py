"""Unit tests for src/rookie_projection.py.

Covers the three production fixes that closed the silent-drop bug:
  1. Per-(team, position) role resolution from depth_charts bronze
  2. Roster-validation filter that drops feed errors (e.g. ghost rows)
  3. UDFA cap that prevents undrafted rookies from inheriting starter weight
  4. Starter-conflict demote for synthesized starters when the upstream
     pipeline already covers a starter at that (team, position)
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.rookie_projection import (
    _role_from_depth_charts,
    project_low_sample_players,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _roster_row(player_id, name, team, pos, status="ACT", years_exp=0,
                draft_number=None, depth="QB", jersey=None):
    return {
        "player_id": player_id,
        "player_name": name,
        "team": team,
        "position": pos,
        "status": status,
        "years_exp": years_exp,
        "draft_number": draft_number,
        "depth_chart_position": depth,
        "jersey_number": jersey if jersey is not None else 99.0,
    }


def _depth_row(gsis_id, name, team, pos_abb, pos_rank, dt="2026-03-14T07:32:09Z"):
    return {
        "dt": dt,
        "team": team,
        "player_name": name,
        "espn_id": "0",
        "gsis_id": gsis_id,
        "pos_grp_id": "0",
        "pos_grp": "OFF",
        "pos_id": "0",
        "pos_name": pos_abb,
        "pos_abb": pos_abb,
        "pos_slot": "0",
        "pos_rank": pos_rank,
    }


# ---------------------------------------------------------------------------
# _role_from_depth_charts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_role_from_depth_charts_basic_starter_backup() -> None:
    depth = pd.DataFrame([
        _depth_row("p1", "Starter QB", "NYG", "QB", 1),
        _depth_row("p2", "Backup QB", "NYG", "QB", 2),
        _depth_row("p3", "Third QB", "NYG", "QB", 3),
    ])
    role = _role_from_depth_charts(depth)
    assert role["p1"] == "starter"
    assert role["p2"] == "backup"
    assert role["p3"] == "unknown"


@pytest.mark.unit
def test_role_from_depth_charts_filters_feed_ghost_rows() -> None:
    """Ghost rows (player listed on team they're not actually on) are filtered.

    Mirrors the real Kyler-Murray-as-MIN-QB1 incident from the 2026-03-14
    nflverse depth_charts feed.
    """
    depth = pd.DataFrame([
        # Ghost: Murray ranked QB1 of MIN but he's actually on ARI.
        _depth_row("murray-ari", "Kyler Murray", "MIN", "QB", 1),
        # Real MIN QBs.
        _depth_row("mccarthy-min", "J.J. McCarthy", "MIN", "QB", 2),
        _depth_row("brosmer-min", "Max Brosmer", "MIN", "QB", 3),
    ])
    roster = pd.DataFrame([
        _roster_row("murray-ari", "Kyler Murray", "ARI", "QB"),
        _roster_row("mccarthy-min", "J.J. McCarthy", "MIN", "QB", years_exp=1),
        _roster_row("brosmer-min", "Max Brosmer", "MIN", "QB"),
    ])
    role = _role_from_depth_charts(depth, roster_df=roster)

    # Murray's MIN row is dropped (he's on ARI per roster).
    # After dropping the ghost, McCarthy's effective rank in MIN is 1, Brosmer is 2.
    assert role["mccarthy-min"] == "starter"
    assert role["brosmer-min"] == "backup"
    # Murray himself doesn't appear in this filtered depth_charts (no ARI row).
    assert "murray-ari" not in role


@pytest.mark.unit
def test_role_from_depth_charts_uses_latest_dt() -> None:
    """Older depth_charts snapshots are ignored when a newer one exists."""
    depth = pd.DataFrame([
        _depth_row("p1", "A", "NYG", "QB", 1, dt="2026-03-12T00:00:00Z"),
        _depth_row("p2", "B", "NYG", "QB", 2, dt="2026-03-12T00:00:00Z"),
        # Newer snapshot reverses the roles.
        _depth_row("p1", "A", "NYG", "QB", 2, dt="2026-03-14T00:00:00Z"),
        _depth_row("p2", "B", "NYG", "QB", 1, dt="2026-03-14T00:00:00Z"),
    ])
    role = _role_from_depth_charts(depth)
    assert role["p2"] == "starter"
    assert role["p1"] == "backup"


@pytest.mark.unit
def test_role_from_depth_charts_handles_empty_input() -> None:
    assert _role_from_depth_charts(None) == {}
    assert _role_from_depth_charts(pd.DataFrame()) == {}


# ---------------------------------------------------------------------------
# project_low_sample_players — end-to-end with all four guards
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_synthesizer_picks_up_silently_dropped_rostered_player() -> None:
    """A rostered player not in already_projected_player_ids gets a row out."""
    roster = pd.DataFrame([
        _roster_row("dart", "Jaxson Dart", "NYG", "QB", years_exp=0, draft_number=25),
        _roster_row("winston", "Jameis Winston", "NYG", "QB", years_exp=10),
    ])
    depth = pd.DataFrame([
        _depth_row("dart", "Jaxson Dart", "NYG", "QB", 1),
        _depth_row("winston", "Jameis Winston", "NYG", "QB", 2),
    ])

    out = project_low_sample_players(
        roster_df=roster,
        weekly_df=None,
        already_projected_player_ids=set(),
        target_season=2026,
        depth_charts_df=depth,
    )
    by_id = {row["player_id"]: row for _, row in out.iterrows()}
    assert "dart" in by_id
    assert "winston" in by_id
    assert by_id["dart"]["low_sample_role"] == "starter"
    assert by_id["winston"]["low_sample_role"] == "backup"


@pytest.mark.unit
def test_synthesizer_udfa_cap_demotes_undrafted_alone_on_roster() -> None:
    """A UDFA who would inherit starter via roster-fallback gets demoted."""
    # IND has no QBs in either depth_charts or upstream — only Henigan
    # (UDFA, no draft_number) is on the roster. Without the cap, the
    # roster fallback labels him "starter" because he's alone in his
    # team-position group.
    roster = pd.DataFrame([
        _roster_row(
            "henigan-ind", "Seth Henigan", "IND", "QB",
            status="ACT", years_exp=0, draft_number=None,
        ),
    ])

    out = project_low_sample_players(
        roster_df=roster,
        weekly_df=None,
        already_projected_player_ids=set(),
        target_season=2026,
        depth_charts_df=pd.DataFrame(),  # no depth_charts → fallback path
    )
    row = out[out["player_id"] == "henigan-ind"].iloc[0]
    # UDFA cap demotes from fallback-starter to backup.
    assert row["low_sample_role"] == "backup"


@pytest.mark.unit
def test_synthesizer_starter_conflict_demote() -> None:
    """If upstream already covers a starter at (team, pos), synthesizer's
    starter is demoted to backup.

    Mirrors the Tua-vs-Ewers case: Tua is in the upstream projections at
    MIA QB; depth_charts has a feed hole that puts Ewers at MIA QB1
    (after ghost-row filtering); without this guard Ewers would mint a
    second starter at MIA.
    """
    roster = pd.DataFrame([
        _roster_row(
            "ewers-mia", "Quinn Ewers", "MIA", "QB",
            years_exp=0, draft_number=164,
        ),
    ])
    depth = pd.DataFrame([
        # Ewers is the only MIA QB in our depth_charts → he'd get starter.
        _depth_row("ewers-mia", "Quinn Ewers", "MIA", "QB", 1),
    ])

    out = project_low_sample_players(
        roster_df=roster,
        weekly_df=None,
        already_projected_player_ids=set(),
        target_season=2026,
        depth_charts_df=depth,
        team_pos_starter_already_projected={("MIA", "QB")},
    )
    row = out[out["player_id"] == "ewers-mia"].iloc[0]
    assert row["low_sample_role"] == "backup"


@pytest.mark.unit
def test_synthesizer_skips_players_already_projected() -> None:
    roster = pd.DataFrame([
        _roster_row("p1", "Already Projected", "NYG", "QB", years_exp=5),
        _roster_row("p2", "Silent Drop", "NYG", "QB", years_exp=0, draft_number=25),
    ])
    depth = pd.DataFrame([
        _depth_row("p2", "Silent Drop", "NYG", "QB", 1),
        _depth_row("p1", "Already Projected", "NYG", "QB", 2),
    ])

    out = project_low_sample_players(
        roster_df=roster,
        weekly_df=None,
        already_projected_player_ids={"p1"},  # p1 covered upstream
        target_season=2026,
        depth_charts_df=depth,
    )
    ids = set(out["player_id"])
    assert ids == {"p2"}, f"expected only p2; got {ids}"


@pytest.mark.unit
def test_synthesizer_high_pick_year1_promoted_when_no_depth_charts() -> None:
    """1st-round rookie behind a vet on roster gets promoted to starter when
    depth_charts is unavailable (the original draft-capital override path)."""
    roster = pd.DataFrame([
        _roster_row("vet", "Jameis Winston", "NYG", "QB", years_exp=10),
        _roster_row("rookie", "Jaxson Dart", "NYG", "QB",
                    years_exp=0, draft_number=25),
    ])

    out = project_low_sample_players(
        roster_df=roster,
        weekly_df=None,
        already_projected_player_ids=set(),
        target_season=2026,
        depth_charts_df=pd.DataFrame(),  # no depth_charts → fallback path
    )
    rookie = out[out["player_id"] == "rookie"].iloc[0]
    assert rookie["low_sample_role"] == "starter"
