#!/usr/bin/env python3
"""
Refresh ADP (Average Draft Position) data from Sleeper API.

Fetches the full Sleeper player database, extracts fantasy-relevant players,
and saves a ranked ADP CSV for use with the draft assistant.

Usage:
    python scripts/refresh_adp.py
    python scripts/refresh_adp.py --season 2026
    python scripts/refresh_adp.py --top 300
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from typing import Optional

import requests
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
SLEEPER_PROJECTIONS_URL = "https://api.sleeper.app/v1/projections/nfl/regular/{season}/{week}"
FANTASY_POSITIONS = {'QB', 'RB', 'WR', 'TE', 'K', 'DEF'}
REQUEST_TIMEOUT = 60


def fetch_sleeper_players() -> dict:
    """Fetch the full Sleeper NFL player database."""
    logger.info("Fetching Sleeper player database (this may take a moment)...")
    resp = requests.get(SLEEPER_PLAYERS_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    logger.info("Received %d player entries from Sleeper", len(data))
    return data


def fetch_sleeper_projections(season: int, week: int = 1) -> dict:
    """Fetch Sleeper's own projections for a given season/week."""
    url = SLEEPER_PROJECTIONS_URL.format(season=season, week=week)
    logger.info("Fetching Sleeper projections: season=%d week=%d", season, week)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("Could not fetch Sleeper projections: %s", e)
        return {}


def build_adp_dataframe(players: dict, top_n: int = 500) -> pd.DataFrame:
    """
    Build an ADP DataFrame from Sleeper player data.

    Uses search_rank as the primary ADP proxy (lower = higher drafted).
    """
    rows = []
    for player_id, info in players.items():
        if not isinstance(info, dict):
            continue
        pos = info.get('position')
        if pos not in FANTASY_POSITIONS:
            continue

        search_rank = info.get('search_rank')
        if search_rank is None or search_rank > 9999:
            continue

        full_name = info.get('full_name') or f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
        if not full_name:
            continue

        rows.append({
            'sleeper_id': player_id,
            'player_name': full_name,
            'position': pos,
            'team': info.get('team', ''),
            'search_rank': search_rank,
            'age': info.get('age'),
            'years_exp': info.get('years_exp'),
            'status': info.get('status', ''),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Filter to active/active_reserve players
    df = df[df['status'].isin(['Active', 'active', ''])].copy()

    # Rank by search_rank (lower = drafted earlier)
    df = df.sort_values('search_rank').reset_index(drop=True)
    df['adp_rank'] = range(1, len(df) + 1)

    # Keep top N
    df = df.head(top_n)

    output_cols = ['adp_rank', 'player_name', 'position', 'team', 'sleeper_id', 'age', 'years_exp']
    return df[output_cols]


def main():
    parser = argparse.ArgumentParser(description='Refresh ADP data from Sleeper API')
    parser.add_argument('--season', type=int, default=2026, help='Target season (default: 2026)')
    parser.add_argument('--top', type=int, default=500, help='Number of players to include (default: 500)')
    parser.add_argument('--output-dir', default='data', help='Output directory (default: data)')
    args = parser.parse_args()

    print(f"\nSleeper ADP Refresh")
    print(f"Season: {args.season} | Top {args.top} players")
    print('=' * 50)

    # Fetch player database
    players = fetch_sleeper_players()

    # Build ADP DataFrame
    adp_df = build_adp_dataframe(players, top_n=args.top)
    if adp_df.empty:
        print("ERROR: No fantasy-relevant players found")
        return 1

    print(f"\nADP data built: {len(adp_df)} players")

    # Position breakdown
    pos_counts = adp_df['position'].value_counts()
    for pos, count in pos_counts.items():
        print(f"  {pos}: {count}")

    # Save dated file and latest pointer
    os.makedirs(args.output_dir, exist_ok=True)
    date_str = datetime.now().strftime('%Y%m%d')

    dated_path = os.path.join(args.output_dir, f"adp_{date_str}.csv")
    latest_path = os.path.join(args.output_dir, "adp_latest.csv")

    adp_df.to_csv(dated_path, index=False)
    adp_df.to_csv(latest_path, index=False)

    print(f"\nSaved: {dated_path}")
    print(f"Saved: {latest_path}")

    # Show top 20
    print(f"\nTop 20 by ADP:")
    print(adp_df.head(20).to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
