"""Unit tests for phase 67 / v7.0 refresh_rosters.py v2 behaviour.

Locks in the root-cause fix: Sleeper ``team=null`` must map to ``team='FA'``
in the output, and the change classifier must emit the correct type
(``TRADED`` vs ``RELEASED`` vs ``RECLASSIFIED`` vs ``TRADED+RECLASSIFIED``).

Also exercises the new Bronze live-roster write (``rosters_live/``) helper.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from scripts.refresh_rosters import (  # noqa: E402
    build_roster_mapping,
    log_changes,
    update_rosters,
    write_bronze_live_rosters,
)


# ---------------------------------------------------------------------------
# build_roster_mapping — FA handling (root-cause fix)
# ---------------------------------------------------------------------------


def _sleeper_entry(
    full_name: str,
    team: str | None,
    position: str,
    status: str = "Active",
) -> dict:
    """Minimal Sleeper player entry for tests."""
    return {
        "full_name": full_name,
        "team": team,
        "position": position,
        "status": status,
    }


def test_released_player_kept_as_fa_not_skipped() -> None:
    """HOTFIX root-cause: team=null must produce team='FA', not silent skip.

    This is the single most important test in phase 67 — the prior
    behaviour (silently continue) is exactly what caused the Kyler Murray
    regression in v6.0.
    """
    players = {
        "1": _sleeper_entry("Released Player", team=None, position="RB"),
        "2": _sleeper_entry("Active Player", team="KC", position="WR"),
    }
    mapping = build_roster_mapping(players)

    assert "released player" in mapping, (
        "FA players must appear in the mapping, not be skipped"
    )
    assert mapping["released player"]["team"] == "FA"
    assert mapping["active player"]["team"] == "KC"


def test_non_fantasy_positions_still_skipped() -> None:
    """DST / defensive players are still outside scope."""
    players = {
        "1": _sleeper_entry("Linebacker Lou", team="ARI", position="LB"),
        "2": _sleeper_entry("QB Pat", team="KC", position="QB"),
    }
    mapping = build_roster_mapping(players)
    assert "linebacker lou" not in mapping
    assert "qb pat" in mapping


def test_collision_prefers_active_over_fa() -> None:
    """When two entries share a name, the Active/teamed one wins."""
    # Same name — one active teamed, one inactive FA.
    players = {
        "1": _sleeper_entry("Common Name", team=None, position="RB", status="Inactive"),
        "2": _sleeper_entry("Common Name", team="KC", position="RB", status="Active"),
    }
    mapping = build_roster_mapping(players)
    # Order independence: whichever ran first, active must win.
    assert mapping["common name"]["team"] == "KC"


# ---------------------------------------------------------------------------
# update_rosters — change classification
# ---------------------------------------------------------------------------


def _proj_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["player_name", "recent_team", "position"])


def _mapping(entries: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Build a mapping dict matching build_roster_mapping's shape."""
    return {k: {**v, "status": v.get("status", "Active")} for k, v in entries.items()}


def test_released_emits_released_change_type() -> None:
    """Sleeper reports team=None → change_type='RELEASED', team='FA'."""
    df = _proj_df([{"player_name": "Kyler Murray", "recent_team": "ARI", "position": "QB"}])
    mapping = _mapping({"kyler murray": {"team": "FA", "position": "QB"}})
    _, changes = update_rosters(df, mapping)
    assert len(changes) == 1
    assert changes.iloc[0]["change_type"] == "RELEASED"
    assert changes.iloc[0]["new_team"] == "FA"


def test_traded_emits_traded_change_type() -> None:
    """Team change only → change_type='TRADED'."""
    df = _proj_df([{"player_name": "Davante Adams", "recent_team": "NYJ", "position": "WR"}])
    mapping = _mapping({"davante adams": {"team": "LAR", "position": "WR"}})
    _, changes = update_rosters(df, mapping)
    assert len(changes) == 1
    assert changes.iloc[0]["change_type"] == "TRADED"


def test_position_only_change_emits_reclassified() -> None:
    """Position changed but team stable → change_type='RECLASSIFIED'."""
    df = _proj_df([{"player_name": "Taysom Hill", "recent_team": "NO", "position": "QB"}])
    mapping = _mapping({"taysom hill": {"team": "NO", "position": "TE"}})
    _, changes = update_rosters(df, mapping)
    assert len(changes) == 1
    assert changes.iloc[0]["change_type"] == "RECLASSIFIED"


def test_team_and_position_changed_emits_combined_type() -> None:
    """Both team and position changed → change_type='TRADED+RECLASSIFIED'."""
    df = _proj_df([{"player_name": "Cordarrelle Patterson", "recent_team": "ATL", "position": "RB"}])
    mapping = _mapping({"cordarrelle patterson": {"team": "PIT", "position": "WR"}})
    _, changes = update_rosters(df, mapping)
    assert len(changes) == 1
    assert changes.iloc[0]["change_type"] == "TRADED+RECLASSIFIED"


def test_unchanged_player_produces_no_change_row() -> None:
    """Sleeper agrees with Gold → no change row emitted."""
    df = _proj_df([{"player_name": "Patrick Mahomes", "recent_team": "KC", "position": "QB"}])
    mapping = _mapping({"patrick mahomes": {"team": "KC", "position": "QB"}})
    updated_df, changes = update_rosters(df, mapping)
    assert changes.empty
    assert updated_df.iloc[0]["recent_team"] == "KC"


# ---------------------------------------------------------------------------
# log_changes — typed prefixes
# ---------------------------------------------------------------------------


def test_log_changes_prefixes_with_change_type(tmp_path: Path) -> None:
    """Audit log lines carry the TRADED/RELEASED/etc prefix."""
    log_path = tmp_path / "roster_changes.log"
    changes = pd.DataFrame([
        {
            "player_name": "Kyler Murray",
            "position": "QB",
            "old_team": "ARI",
            "new_team": "FA",
            "change_type": "RELEASED",
        },
        {
            "player_name": "Davante Adams",
            "position": "WR",
            "old_team": "NYJ",
            "new_team": "LAR",
            "change_type": "TRADED",
        },
    ])
    log_changes(changes, log_path=str(log_path))
    text = log_path.read_text()
    assert "RELEASED: Kyler Murray (QB): ARI -> FA" in text
    assert "TRADED: Davante Adams (WR): NYJ -> LAR" in text


# ---------------------------------------------------------------------------
# write_bronze_live_rosters — new Bronze tree
# ---------------------------------------------------------------------------


def test_bronze_live_write_creates_timestamped_parquet(tmp_path: Path) -> None:
    """Live roster writer partitions by season and timestamps the filename."""
    mapping = _mapping({
        "kyler murray": {"team": "FA", "position": "QB"},
        "patrick mahomes": {"team": "KC", "position": "QB"},
    })
    out = write_bronze_live_rosters(mapping, season=2026, bronze_root=str(tmp_path))
    assert out is not None
    out_path = Path(out)
    assert out_path.exists()
    assert out_path.parent.name == "season=2026"
    assert out_path.name.startswith("sleeper_rosters_")
    assert out_path.suffix == ".parquet"

    df = pd.read_parquet(out_path)
    assert set(df["team"]) == {"FA", "KC"}
    assert df[df["team"] == "FA"]["is_free_agent"].iloc[0] is True or df[df["team"] == "FA"]["is_free_agent"].iloc[0] == True  # noqa: E712


def test_bronze_live_write_empty_mapping_returns_none(tmp_path: Path) -> None:
    """Empty mapping → None, no parquet written (defensive)."""
    out = write_bronze_live_rosters({}, season=2026, bronze_root=str(tmp_path))
    assert out is None
