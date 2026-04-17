#!/usr/bin/env python3
"""
Refresh player team AND position assignments in Gold projections using
the Sleeper API.

Fetches the full Sleeper NFL player database, builds a name -> {team,
position} mapping, and updates the `recent_team` and `position` columns
in the latest preseason projections parquet. All changes are appended to
`roster_changes.log` for auditability (per Phase 60 D-02, D-03, D-04).

Position fixes propagate to the Gold layer only; Silver/Bronze retain the
original nfl-data-py positions for model training stability (D-05).

Usage:
    python scripts/refresh_rosters.py --season 2026
    python scripts/refresh_rosters.py --season 2026 --dry-run
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
REQUEST_TIMEOUT = 60
FANTASY_POSITIONS = {'QB', 'RB', 'WR', 'TE', 'K'}

# Sleeper uses different abbreviations for some teams.
# Map Sleeper abbreviation -> nflverse abbreviation used in Gold data.
SLEEPER_TO_NFLVERSE_TEAM: Dict[str, str] = {
    'LAR': 'LA',   # Rams
    'JAC': 'JAX',  # Jaguars (Sleeper sometimes uses JAC)
}


def fetch_sleeper_players() -> dict:
    """Fetch the full Sleeper NFL player database."""
    logger.info("Fetching Sleeper player database...")
    resp = requests.get(SLEEPER_PLAYERS_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    logger.info("Received %d player entries from Sleeper", len(data))
    return data


def build_team_mapping(players: dict) -> Dict[str, str]:
    """Build a mapping of normalized player name -> current team.

    Only includes fantasy-relevant positions with a non-null team assignment.
    Applies Sleeper-to-nflverse team abbreviation normalization.

    Returns:
        Dict mapping lowercase player name to nflverse team abbreviation.
    """
    mapping: Dict[str, str] = {}
    skipped_no_team = 0

    for player_id, info in players.items():
        if not isinstance(info, dict):
            continue

        pos = info.get('position')
        if pos not in FANTASY_POSITIONS:
            continue

        team = info.get('team')
        if not team:
            skipped_no_team += 1
            continue

        full_name = info.get('full_name') or ''
        if not full_name:
            first = info.get('first_name', '')
            last = info.get('last_name', '')
            full_name = f"{first} {last}".strip()
        if not full_name:
            continue

        # Normalize team abbreviation
        team = SLEEPER_TO_NFLVERSE_TEAM.get(team, team)

        name_key = full_name.lower().strip()
        mapping[name_key] = team

    logger.info(
        "Built team mapping: %d players with teams, %d without",
        len(mapping),
        skipped_no_team,
    )
    return mapping


def build_roster_mapping(players: dict) -> Dict[str, Dict[str, str]]:
    """Build a mapping of normalized player name -> {team, position}.

    Combines the team and position extraction in a single pass so that the
    Gold projections layer can be updated coherently (per Phase 60 D-03,
    D-04). Only fantasy-relevant positions (QB/RB/WR/TE/K) with a non-null
    team are included. LAR is normalized to LA via SLEEPER_TO_NFLVERSE_TEAM.

    Name-collision handling: Sleeper's player database includes historical
    and inactive players, producing 36 documented full_name collisions
    among fantasy positions. When two entries collide, the Active player
    wins (Pitfall 1 from 60-RESEARCH.md).

    Args:
        players: Raw Sleeper /v1/players/nfl response (player_id -> info dict).

    Returns:
        Dict mapping lowercase full_name to {'team': str, 'position': str}.
    """
    mapping: Dict[str, Dict[str, str]] = {}
    skipped_no_team = 0

    for _, info in players.items():
        if not isinstance(info, dict):
            continue

        pos = info.get('position')
        if pos not in FANTASY_POSITIONS:
            continue

        team = info.get('team')
        if not team:
            skipped_no_team += 1
            continue

        full_name = info.get('full_name') or ''
        if not full_name:
            first = info.get('first_name', '')
            last = info.get('last_name', '')
            full_name = f"{first} {last}".strip()
        if not full_name:
            continue

        team = SLEEPER_TO_NFLVERSE_TEAM.get(team, team)
        name_key = full_name.lower().strip()

        # On collision, prefer Active players (Pitfall 1 from 60-RESEARCH.md).
        if name_key in mapping and info.get('status') != 'Active':
            continue

        mapping[name_key] = {'team': team, 'position': pos}

    logger.info(
        "Built roster mapping: %d players with teams, %d without",
        len(mapping),
        skipped_no_team,
    )
    return mapping


def find_latest_parquet(projections_dir: str) -> Optional[str]:
    """Find the latest parquet file in the projections directory."""
    p = Path(projections_dir)
    if not p.exists():
        return None
    files = sorted(p.glob('*.parquet'))
    if not files:
        return None
    return str(files[-1])


def update_teams(
    df: pd.DataFrame, team_mapping: Dict[str, str]
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Update recent_team in the projections DataFrame using the Sleeper mapping.

    Args:
        df: Gold projections DataFrame with player_name and recent_team columns.
        team_mapping: Mapping of lowercase player name to current team.

    Returns:
        Tuple of (updated DataFrame, changes DataFrame showing before/after).
    """
    df = df.copy()
    changes = []

    for idx, row in df.iterrows():
        name_key = str(row['player_name']).lower().strip()
        new_team = team_mapping.get(name_key)

        if new_team is None:
            continue

        old_team = row['recent_team']
        if old_team != new_team:
            changes.append({
                'player_name': row['player_name'],
                'position': row['position'],
                'old_team': old_team,
                'new_team': new_team,
            })
            df.at[idx, 'recent_team'] = new_team

    changes_df = pd.DataFrame(changes)
    return df, changes_df


def update_rosters(
    df: pd.DataFrame, roster_mapping: Dict[str, Dict[str, str]]
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Update recent_team AND position in Gold projections (per D-03, D-05).

    Extends the `update_teams` behavior to also correct the `position`
    column using Sleeper as the canonical source (D-04). Position fixes
    propagate to the Gold layer only -- Silver/Bronze retain their original
    nfl-data-py positions for model training stability (D-05).

    Args:
        df: Gold projections DataFrame with at least player_name, recent_team,
            and position columns.
        roster_mapping: Output of build_roster_mapping -- lowercase name ->
            {'team': str, 'position': str}.

    Returns:
        Tuple of (updated DataFrame, changes DataFrame). The changes DataFrame
        contains one row per corrected player with columns:
            player_name, position (new), old_team, new_team
        and, when position changed:
            old_position, new_position
    """
    df = df.copy()
    changes = []

    for idx, row in df.iterrows():
        name_key = str(row['player_name']).lower().strip()
        mapping = roster_mapping.get(name_key)
        if mapping is None:
            continue

        old_team = row['recent_team']
        new_team = mapping['team']
        old_pos = row['position']
        new_pos = mapping['position']

        if old_team == new_team and old_pos == new_pos:
            continue

        change: Dict[str, object] = {
            'player_name': row['player_name'],
            'position': new_pos,
            'old_team': old_team,
            'new_team': new_team,
        }
        if old_pos != new_pos:
            change['old_position'] = old_pos
            change['new_position'] = new_pos

        changes.append(change)
        df.at[idx, 'recent_team'] = new_team
        df.at[idx, 'position'] = new_pos  # D-05: Gold layer only

    changes_df = pd.DataFrame(changes)
    return df, changes_df


def log_changes(
    changes_df: pd.DataFrame, log_path: str = 'roster_changes.log'
) -> None:
    """Append roster changes to a persistent, timestamped log file (per D-02).

    Writes a section header with the current timestamp, then one line per
    change showing the player, position, and team/position deltas. An empty
    changes DataFrame still produces a header line plus "No changes detected."
    so that absence of changes is also captured in the audit trail.

    Args:
        changes_df: Output DataFrame from update_rosters(). May be empty.
        log_path: File path to append to. Defaults to 'roster_changes.log'
            in the current working directory.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_path, 'a') as f:
        f.write(f'\n--- Roster Refresh: {timestamp} ---\n')
        if changes_df is None or changes_df.empty:
            f.write('No changes detected.\n')
            return

        for _, row in changes_df.iterrows():
            old_team = row.get('old_team', '?')
            new_team = row.get('new_team', '?')
            pos = row.get('position', '?')
            f.write(
                f"  {row['player_name']} ({pos}): "
                f"{old_team} -> {new_team}"
            )
            old_pos = row.get('old_position') if 'old_position' in row else None
            new_pos = row.get('new_position') if 'new_position' in row else None
            if old_pos is not None and pd.notna(old_pos) and new_pos is not None:
                f.write(f", pos: {old_pos} -> {new_pos}")
            f.write('\n')


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Refresh player team assignments from Sleeper API'
    )
    parser.add_argument(
        '--season', type=int, default=2026, help='Target season (default: 2026)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show changes without writing a new parquet file',
    )
    args = parser.parse_args()

    print(f"\nRoster Refresh Pipeline")
    print(f"Season: {args.season}")
    print('=' * 60)

    # 1. Fetch Sleeper data -- build combined team+position mapping (D-03).
    players = fetch_sleeper_players()
    roster_mapping = build_roster_mapping(players)

    # 2. Load latest Gold projections
    proj_dir = os.path.join(
        'data', 'gold', 'projections', 'preseason', f'season={args.season}'
    )
    latest_file = find_latest_parquet(proj_dir)
    if not latest_file:
        print(f"ERROR: No parquet files found in {proj_dir}")
        return 1

    print(f"\nLoading: {latest_file}")
    df = pd.read_parquet(latest_file)
    print(f"Players loaded: {len(df)}")

    # 3. Update team AND position in a single pass (D-03, D-04, D-05).
    updated_df, changes_df = update_rosters(df, roster_mapping)

    # 4. Report
    if changes_df.empty:
        print("\nNo roster changes detected — all assignments are current.")
        # Still log the no-op run for audit continuity (D-02).
        log_changes(changes_df)
        return 0

    print(f"\nRoster changes found: {len(changes_df)}")
    print('-' * 60)
    print(
        changes_df.sort_values('player_name')
        .to_string(index=False)
    )
    print('-' * 60)

    # Position breakdown of changes
    pos_counts = changes_df['position'].value_counts()
    print("\nChanges by (new) position:")
    for pos, count in pos_counts.items():
        print(f"  {pos}: {count}")

    # Dedicated breakdown of position reclassifications (D-04).
    if 'old_position' in changes_df.columns:
        pos_reclass = changes_df.dropna(subset=['old_position'])
        if not pos_reclass.empty:
            print(f"\nPosition reclassifications: {len(pos_reclass)}")
            for _, row in pos_reclass.iterrows():
                print(
                    f"  {row['player_name']}: "
                    f"{row['old_position']} -> {row['new_position']}"
                )

    # 5. Save
    if args.dry_run:
        print("\n[DRY RUN] No file written.")
        # Still log the dry-run changes for audit visibility (D-02).
        log_changes(changes_df)
        return 0

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(proj_dir, f'season_proj_{timestamp}.parquet')
    updated_df.to_parquet(output_file, index=False)
    print(f"\nSaved: {output_file}")

    # Persist the change record for audit review (D-02).
    log_changes(changes_df)
    print("Logged changes to roster_changes.log")

    # Verify key players
    print("\nVerification (key players):")
    verify_names = ['Kyler Murray', 'Davante Adams', 'Russell Wilson', 'Saquon Barkley']
    for name in verify_names:
        row = updated_df[
            updated_df['player_name'].str.contains(name, case=False, na=False)
        ]
        if not row.empty:
            team = row.iloc[0]['recent_team']
            print(f"  {name}: {team}")
        else:
            print(f"  {name}: NOT IN PROJECTIONS")

    return 0


if __name__ == "__main__":
    sys.exit(main())
