"""Sleeper-sourced supplement for rookies missing from nfl-data-py rosters.

Problem
-------
nfl-data-py's ``import_seasonal_rosters(2026)`` does not yet include the 2026
NFL draft class because the nflverse pipeline typically lags several weeks
after the draft before newly-signed players appear in the seasonal-rosters
release tag.  The ``project_low_sample_players`` synthesizer in
``src/rookie_projection.py`` requires these rookies to be present in
``roster_df`` to generate projections for them.

Solution
--------
This module fetches the Sleeper ``/v1/players/nfl`` endpoint (which is updated
within hours of signings) and builds a roster-supplement DataFrame whose
schema is compatible with the ``project_low_sample_players`` contract:

    player_id, player_name, position, team, status, years_exp,
    depth_chart_position, jersey_number, draft_number (optional)

The ``player_id`` column is set to the **draft_picks gsis_id** (short format,
e.g. ``LOV121782``) when available — this matches the ``gsis_id`` column in the
``depth_charts`` bronze, allowing ``_role_from_depth_charts`` to validate and
assign starter/backup roles for newly-drafted players.

If no draft_picks DataFrame is provided the Sleeper ``sleeper_id`` is used as
the player_id fallback (still unique, just won't match depth_charts gsis_ids
for role assignment — role will fall back to roster-ordering heuristic).

Usage
-----
Called by ``scripts/generate_projections.py`` in preseason mode to supplement
the nfl-data-py roster_df before passing it to ``generate_preseason_projections``.

Example::

    from sleeper_rookie_roster import build_sleeper_rookie_supplement

    supplement = build_sleeper_rookie_supplement(
        target_season=2026,
        existing_player_ids=set(roster_df["player_id"].dropna().astype(str)),
        draft_picks_df=draft_picks_df,  # Bronze draft_picks parquet
    )
    if not supplement.empty:
        roster_df = pd.concat([roster_df, supplement], ignore_index=True)
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
REQUEST_TIMEOUT = 60

_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K"}

# Sleeper team abbreviations that differ from nflverse conventions.
_SLEEPER_TO_NFLVERSE_TEAM: dict[str, str] = {
    "LAR": "LA",  # Rams
    "JAC": "JAX",  # Jaguars
}


def _fetch_sleeper_players() -> dict:
    """Fetch the full Sleeper NFL player database.

    Returns:
        Dict mapping Sleeper player_id -> player info dict.

    Raises:
        requests.RequestException: on network failure.
    """
    logger.info("Fetching Sleeper player database for rookie supplement...")
    resp = requests.get(SLEEPER_PLAYERS_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    logger.info("Received %d Sleeper player entries", len(data))
    return data


def _build_gsis_id_map(draft_picks_df: Optional[pd.DataFrame]) -> dict[str, str]:
    """Build a mapping of player name (lowercase) -> gsis_id from draft_picks.

    The gsis_id in draft_picks matches the short-format IDs used in the
    depth_charts bronze (e.g. ``LOV121782`` for Jeremiyah Love).  When this
    map is available, ``player_id`` in the supplement is set to the short
    gsis_id so ``_role_from_depth_charts`` can validate and assign roles.

    Args:
        draft_picks_df: Bronze draft_picks parquet (all seasons or just
            the target season).  Must contain ``pfr_player_name`` and
            ``gsis_id`` columns.  Pass ``None`` to skip.

    Returns:
        Dict mapping lowercased player name -> short gsis_id.
    """
    if draft_picks_df is None or draft_picks_df.empty:
        return {}
    needed = {"pfr_player_name", "gsis_id"}
    if not needed.issubset(draft_picks_df.columns):
        return {}

    result: dict[str, str] = {}
    for _, row in draft_picks_df.iterrows():
        gsis = row.get("gsis_id")
        name = row.get("pfr_player_name")
        if not gsis or not name or pd.isna(gsis) or pd.isna(name):
            continue
        result[str(name).lower().strip()] = str(gsis)
    return result


def _build_pick_number_map(draft_picks_df: Optional[pd.DataFrame]) -> dict[str, int]:
    """Build a mapping of player name (lowercase) -> overall pick number.

    The overall pick number is stored in the ``pick`` column of the
    draft_picks bronze (1-indexed, sequential across all rounds).  This
    feeds ``draft_number`` in the supplement row, which is used by
    ``project_low_sample_players`` to promote high-pick rookies to starter
    role when they are not yet covered by the depth_charts feed.

    Args:
        draft_picks_df: Bronze draft_picks parquet. Must contain
            ``pfr_player_name`` and ``pick`` columns.

    Returns:
        Dict mapping lowercased player name -> overall pick number.
    """
    if draft_picks_df is None or draft_picks_df.empty:
        return {}
    needed = {"pfr_player_name", "pick"}
    if not needed.issubset(draft_picks_df.columns):
        return {}

    result: dict[str, int] = {}
    for _, row in draft_picks_df.iterrows():
        pick = row.get("pick")
        name = row.get("pfr_player_name")
        if not name or pd.isna(name):
            continue
        if pd.isna(pick):
            continue
        try:
            result[str(name).lower().strip()] = int(pick)
        except (ValueError, TypeError):
            pass
    return result


def build_sleeper_rookie_supplement(
    target_season: int,
    existing_player_ids: set[str],
    draft_picks_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Build a roster-compatible supplement for 2026 rookies missing from nfl-data-py.

    Fetches the Sleeper player database, filters to fantasy-relevant positions
    with ``years_exp == 0`` (true rookies), and constructs rows whose schema
    matches the nfl-data-py seasonal-rosters format expected by
    ``project_low_sample_players``.

    Players whose ``player_id`` already appears in ``existing_player_ids`` are
    skipped to avoid duplicate rows.

    Args:
        target_season: The season being projected (e.g. 2026).  Used to
            populate the ``season`` and ``rookie_year`` columns.
        existing_player_ids: Set of player_id strings already present in the
            nfl-data-py roster_df.  Rookies whose id is in this set are
            skipped.
        draft_picks_df: Optional Bronze draft_picks parquet.  When provided,
            the supplement uses the short gsis_id from this table as
            ``player_id`` (matching depth_charts) and populates
            ``draft_number`` for the draft-capital override logic.

    Returns:
        DataFrame with columns compatible with the nfl-data-py rosters schema.
        Empty DataFrame on network failure or when no missing rookies are found.
    """
    try:
        sleeper_data = _fetch_sleeper_players()
    except Exception as exc:
        logger.warning("Could not fetch Sleeper data for rookie supplement: %s", exc)
        return pd.DataFrame()

    gsis_id_map = _build_gsis_id_map(draft_picks_df)
    pick_number_map = _build_pick_number_map(draft_picks_df)

    rows = []
    for sleeper_pid, info in sleeper_data.items():
        if not isinstance(info, dict):
            continue

        position = info.get("position")
        if position not in _FANTASY_POSITIONS:
            continue

        # True rookies only (years_exp = 0 means entering their first season).
        years_exp = info.get("years_exp")
        if years_exp != 0:
            continue

        team_raw = info.get("team")
        if not team_raw:
            # Undrafted or unsigned — skip; they won't appear in depth_charts
            # and projecting them would add noise.
            continue

        team = _SLEEPER_TO_NFLVERSE_TEAM.get(team_raw, team_raw)

        full_name = info.get("full_name") or ""
        if not full_name:
            first = info.get("first_name", "")
            last = info.get("last_name", "")
            full_name = f"{first} {last}".strip()
        if not full_name:
            continue

        name_lower = full_name.lower().strip()

        # Resolve player_id: prefer short gsis_id (matches depth_charts) from
        # draft_picks; fall back to Sleeper's own id prefixed with "SLP-" to
        # avoid collisions with existing nfl-data-py 00-0... format ids.
        gsis_id = gsis_id_map.get(name_lower)
        player_id = gsis_id if gsis_id else f"SLP-{sleeper_pid}"

        # Skip if already covered.
        if str(player_id) in existing_player_ids:
            continue

        # Also skip by Sleeper id in case the roster already has this player
        # under a different id format (belt-and-suspenders).
        if f"SLP-{sleeper_pid}" in existing_player_ids:
            continue

        draft_number = pick_number_map.get(name_lower)

        status = str(info.get("status") or "ACT")
        # Normalise Sleeper status values to the nfl-data-py vocabulary.
        status_map = {
            "Active": "ACT",
            "Inactive": "INA",
            "Reserve": "RES",
            "NonFootballInjury": "PUP",
            "PracticeSquad": "INA",
        }
        status = status_map.get(status, status)
        if status not in {"ACT", "RES", "PUP"}:
            status = "ACT"

        jersey_number = info.get("number")
        try:
            jersey_number = int(jersey_number) if jersey_number is not None else None
        except (ValueError, TypeError):
            jersey_number = None

        row: dict = {
            "season": target_season,
            "player_id": player_id,
            "player_name": full_name,
            "first_name": info.get("first_name", ""),
            "last_name": info.get("last_name", ""),
            "position": position,
            "depth_chart_position": position,
            "team": team,
            "status": status,
            "years_exp": 0,
            "entry_year": float(target_season),
            "rookie_year": float(target_season),
            "jersey_number": jersey_number,
            "draft_number": float(draft_number) if draft_number is not None else None,
            # Non-critical metadata — leave null to distinguish from nfl-data-py rows.
            "birth_date": None,
            "height": None,
            "weight": None,
            "college": None,
            "espn_id": None,
            "sportradar_id": None,
            "yahoo_id": None,
            "rotowire_id": None,
            "pff_id": None,
            "pfr_id": None,
            "fantasy_data_id": None,
            "sleeper_id": sleeper_pid,
            "headshot_url": info.get("fantasy_data_id"),
            "esb_id": None,
            "gsis_it_id": None,
            "smart_id": None,
            "draft_club": None,
            "age": info.get("age"),
        }
        rows.append(row)

    if not rows:
        logger.info(
            "Sleeper rookie supplement: no missing rookies found "
            "(all %d rookies already in roster_df or no new draft class)",
            len(existing_player_ids),
        )
        return pd.DataFrame()

    supplement = pd.DataFrame(rows)
    logger.info(
        "Sleeper rookie supplement: added %d players for season %d "
        "(%d with gsis_id matching depth_charts, %d with draft pick number)",
        len(supplement),
        target_season,
        supplement["player_id"].str.match(r"^[A-Z]{3}\d+$").sum(),
        supplement["draft_number"].notna().sum(),
    )
    return supplement
