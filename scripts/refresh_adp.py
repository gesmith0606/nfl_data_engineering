#!/usr/bin/env python3
"""
Refresh ADP (Average Draft Position) data.

Default source is Fantasy Football Calculator (real ADP). ``--source sleeper``
keeps the legacy Sleeper ``search_rank`` popularity-index path — NOT real
ADP — for backward compatibility; its output is labeled ``sleeper_rank`` so
downstream consumers are never fooled into treating it as a draft position.

Usage:
    python scripts/refresh_adp.py                                  # FFC, half_ppr, 12-team (default)
    python scripts/refresh_adp.py --source espn --season 2026
    python scripts/refresh_adp.py --source ffc --scoring ppr --teams 10
    python scripts/refresh_adp.py --source sleeper --top 300
"""

import sys
import os
import argparse
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
# Also add the repo root so `from src.adp_sources import ...` resolves
# (adp_sources.py imports sleeper_player_map via the `src.` package path).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.sleeper_player_map import normalize_name  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
SLEEPER_PROJECTIONS_URL = "https://api.sleeper.app/v1/projections/nfl/regular/{season}/{week}"
FANTASY_POSITIONS = {'QB', 'RB', 'WR', 'TE', 'K', 'DEF'}
REQUEST_TIMEOUT = 60

# Legacy adp_latest.csv columns (unchanged, so existing consumers never break)
# plus the new real-ADP columns appended at the end.
_LEGACY_COLS = ['adp_rank', 'player_name', 'position', 'team', 'sleeper_id', 'age', 'years_exp']
_NEW_COLS = ['source', 'scoring_format', 'adp', 'stdev', 'times_drafted', 'fetched_at', 'name_key']
OUTPUT_COLUMNS = _LEGACY_COLS + _NEW_COLS

# The one (source, scoring) combo that also refreshes the legacy adp_latest.csv
# pointer, so a bare `python scripts/refresh_adp.py` (cron default) keeps
# existing consumers (web API, draft_optimizer) working without a flag change.
_DEFAULT_SOURCE = 'ffc'
_DEFAULT_SCORING = 'half_ppr'


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


def build_adp_from_sleeper_rank(players: dict, top_n: int, scoring: str) -> pd.DataFrame:
    """Legacy Sleeper ``search_rank`` path, reindexed to ``OUTPUT_COLUMNS``.

    ``search_rank`` is Sleeper's popularity index, NOT real ADP — the
    ``source`` column is explicitly labeled ``sleeper_rank`` (never
    ``sleeper``) so no downstream consumer mistakes it for a draft position.
    """
    df = build_adp_dataframe(players, top_n=top_n)
    if df.empty:
        return df

    df = df.copy()
    df['source'] = 'sleeper_rank'
    df['scoring_format'] = scoring
    df['adp'] = pd.NA
    df['stdev'] = pd.NA
    df['times_drafted'] = pd.NA
    df['fetched_at'] = datetime.now(timezone.utc).isoformat()
    df['name_key'] = df['player_name'].map(normalize_name)
    return df[OUTPUT_COLUMNS]


def build_adp_from_real_source(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a normalized real-ADP DataFrame (``src.adp_sources`` output)
    into the legacy ``adp_latest.csv`` schema, ranked by real ADP ascending.

    ``sleeper_id``/``age``/``years_exp`` are unavailable from FFC/ESPN and
    are left null — existing consumers only read ``adp_rank``/``player_name``/
    ``position``/``team`` from this file, so this is compatible.
    """
    if df.empty:
        return df

    out = df.sort_values('adp', na_position='last').reset_index(drop=True)
    out['adp_rank'] = range(1, len(out) + 1)
    out['sleeper_id'] = pd.NA
    out['age'] = pd.NA
    out['years_exp'] = pd.NA
    return out[OUTPUT_COLUMNS]


def main():
    parser = argparse.ArgumentParser(description='Refresh ADP (Average Draft Position) data')
    parser.add_argument('--season', type=int, default=2026, help='Target season (default: 2026)')
    parser.add_argument('--top', type=int, default=500, help='Number of players to include (default: 500)')
    parser.add_argument('--output-dir', default='data', help='Output directory (default: data)')
    parser.add_argument(
        '--source', choices=['ffc', 'espn', 'sleeper', 'sleeper_rank'], default=_DEFAULT_SOURCE,
        help=(
            'ADP source: ffc/espn/sleeper are real ADP '
            '(sleeper = crowd ADP from the Sleeper projections feed); '
            'sleeper_rank is the legacy search_rank popularity index (default: ffc)'
        ),
    )
    parser.add_argument(
        '--scoring', choices=['ppr', 'half_ppr', 'standard'], default=_DEFAULT_SCORING,
        help='Scoring format for FFC ADP / labeling (default: half_ppr)',
    )
    parser.add_argument('--teams', type=int, default=12, help='League size for FFC ADP (default: 12)')
    args = parser.parse_args()

    print(f"\nADP Refresh — source={args.source} scoring={args.scoring}")
    print(f"Season: {args.season} | Top {args.top} players")
    print('=' * 50)

    if args.source == 'sleeper_rank':
        players = fetch_sleeper_players()
        adp_df = build_adp_from_sleeper_rank(players, top_n=args.top, scoring=args.scoring)
    else:
        from src.adp_sources import fetch_espn_adp, fetch_ffc_adp, fetch_sleeper_adp

        if args.source == 'ffc':
            raw_df = fetch_ffc_adp(args.scoring, args.season, teams=args.teams)
        elif args.source == 'sleeper':
            raw_df = fetch_sleeper_adp(args.scoring, args.season)
        else:
            raw_df = fetch_espn_adp(args.season)
        adp_df = build_adp_from_real_source(raw_df).head(args.top)

    if adp_df.empty:
        print(f"ERROR: No ADP data returned from source '{args.source}'")
        return 1

    print(f"\nADP data built: {len(adp_df)} players")

    # Position breakdown
    pos_counts = adp_df['position'].value_counts()
    for pos, count in pos_counts.items():
        print(f"  {pos}: {count}")

    # Save per-source dated + "latest" file under data/adp/
    adp_dir = os.path.join(args.output_dir, 'adp')
    os.makedirs(adp_dir, exist_ok=True)
    date_str = datetime.now().strftime('%Y%m%d')

    dated_path = os.path.join(adp_dir, f"adp_{args.source}_{args.scoring}_{date_str}.csv")
    source_latest_path = os.path.join(adp_dir, f"adp_{args.source}_{args.scoring}.csv")
    adp_df.to_csv(dated_path, index=False)
    adp_df.to_csv(source_latest_path, index=False)
    print(f"\nSaved: {dated_path}")
    print(f"Saved: {source_latest_path}")

    # The legacy data/adp_latest.csv pointer is only refreshed for the
    # default (ffc, half_ppr) combo, so existing consumers (web API,
    # draft_optimizer, the CLI draft assistant) keep working unmodified.
    if args.source == _DEFAULT_SOURCE and args.scoring == _DEFAULT_SCORING:
        os.makedirs(args.output_dir, exist_ok=True)
        latest_path = os.path.join(args.output_dir, "adp_latest.csv")
        adp_df.to_csv(latest_path, index=False)
        print(f"Saved: {latest_path}")

    # Show top 20
    print(f"\nTop 20 by ADP:")
    print(adp_df.head(20).to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
