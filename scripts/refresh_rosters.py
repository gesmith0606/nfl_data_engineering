#!/usr/bin/env python3
"""
Refresh player team assignments in Gold projections using the Sleeper API.

Fetches the full Sleeper NFL player database, builds a name-to-team mapping,
and updates the `recent_team` column in the latest preseason projections parquet.

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

    # 1. Fetch Sleeper data
    players = fetch_sleeper_players()
    team_mapping = build_team_mapping(players)

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

    # 3. Update teams
    updated_df, changes_df = update_teams(df, team_mapping)

    # 4. Report
    if changes_df.empty:
        print("\nNo team changes detected — all assignments are current.")
        return 0

    print(f"\nTeam changes found: {len(changes_df)}")
    print('-' * 60)
    print(
        changes_df.sort_values('player_name')
        .to_string(index=False)
    )
    print('-' * 60)

    # Position breakdown of changes
    pos_counts = changes_df['position'].value_counts()
    print("\nChanges by position:")
    for pos, count in pos_counts.items():
        print(f"  {pos}: {count}")

    # 5. Save
    if args.dry_run:
        print("\n[DRY RUN] No file written.")
        return 0

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(proj_dir, f'season_proj_{timestamp}.parquet')
    updated_df.to_parquet(output_file, index=False)
    print(f"\nSaved: {output_file}")

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
