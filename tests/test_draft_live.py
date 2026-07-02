"""Offline tests for the live draft co-pilot entrypoint (Phase 87).

Exercises the manual-entry fallback (D-09 / SKILL-04) and rendering without any
network or real ADP file.
"""

from __future__ import annotations

import importlib.util
import json
import os

import pandas as pd
import pytest

# Load scripts/draft_live.py as a module (scripts/ is not a package).
_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "draft_live.py")
_spec = importlib.util.spec_from_file_location("draft_live", _SCRIPT)
draft_live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(draft_live)

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sleeper_draft")


@pytest.fixture
def projections_df():
    with open(
        os.path.join(_FIXTURE_DIR, "projections_sample.json"), encoding="utf-8"
    ) as fh:
        return pd.DataFrame(json.load(fh))


@pytest.fixture
def proj_csv(tmp_path, projections_df):
    path = tmp_path / "proj.csv"
    projections_df.to_csv(path, index=False)
    return str(path)


@pytest.mark.unit
def test_build_manual_state_resolves_positions(projections_df):
    state = draft_live.build_manual_state(
        ["Ja'Marr Chase", "Bijan Robinson"],
        projections_df,
        n_teams=3,
        draft_type="snake",
        scoring="half_ppr",
        roster="standard",
        season="2026",
    )
    assert len(state.picks) == 2
    chase = state.picks[0]
    assert chase.position == "WR"
    assert chase.draft_slot == 1  # pick 1, round 1
    assert state.picks[1].draft_slot == 2


@pytest.mark.unit
def test_build_manual_state_keeps_unknown_names(projections_df):
    state = draft_live.build_manual_state(
        ["Totally Unknown Guy"], projections_df, 12, "snake", "ppr", "standard", "2026"
    )
    assert len(state.picks) == 1  # unknown name still produces a pick
    assert state.picks[0].full_name == "Totally Unknown Guy"


@pytest.mark.unit
def test_main_manual_json_returns_zero(proj_csv, capsys):
    rc = draft_live.main(
        [
            "--manual",
            "--teams",
            "3",
            "--my-slot",
            "3",
            "--projections-file",
            proj_csv,
            "--adp-file",
            "/tmp/does_not_exist_adp.csv",
            "--add-pick",
            "Patrick Mahomes",
            "--add-pick",
            "Christian McCaffrey",
            "--add-pick",
            "Ja'Marr Chase",
            "--json",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["is_my_turn"] is True  # slot 3 on the clock at pick 4 (3-team snake)
    assert out["on_clock_pick"] == 4
    assert "Ja'Marr Chase" in [r["player_name"] for r in out["my_roster"]]
    # Drafted players are off the recommendation board.
    assert "Ja'Marr Chase" not in [r["player_name"] for r in out["recommendations"]]
