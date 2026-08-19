#!/usr/bin/env python3
"""
Ingest historical ADP snapshots — FFC (2021-2025 x ppr/half_ppr/standard)
and MFL (2021-2025) — into data/adp/history/adp_{source}_{format}_{year}.csv.

Unified schema (nulls where a source lacks a field):
    season, snapshot_date, source, format, player_name, team, position,
    adp, high, low, stdev, times_drafted

FFC snapshot_date = the aggregation window's meta.end_date. For closed
seasons FFC's window is fixed to a late-Aug/early-Sept span (e.g. 2021:
2021-08-31 -> 2021-09-01) — this is "ADP at draft time".

MFL snapshot_date = fetch date (today), because PERIOD=ALL (the only mode
that returns data for closed seasons — PERIOD=RECENT gives totalDrafts=0)
aggregates the *entire* draft season for a year, not a fixed point-in-time
window like FFC's. `format` is labeled "season_aggregate" for MFL rows
rather than a real scoring format, since MFL's ADP export isn't
scoring-format-aware.

Usage:
    python scripts/ingest_adp_history.py                  # FFC + MFL, 2021-2025
    python scripts/ingest_adp_history.py --source ffc
    python scripts/ingest_adp_history.py --source mfl
    python scripts/ingest_adp_history.py --years 2021 2022
"""

import argparse
import logging
import os
import sys
import time
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.adp_sources import fetch_ffc_adp, fetch_mfl_adp  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HISTORY_YEARS = list(range(2021, 2026))
FFC_FORMATS = ['ppr', 'half_ppr', 'standard']
RATE_LIMIT_S = 1.0  # >=1s between live API calls, per project convention

HISTORY_COLUMNS = [
    'season', 'snapshot_date', 'source', 'format', 'player_name', 'team',
    'position', 'adp', 'high', 'low', 'stdev', 'times_drafted',
]


def _to_history_df(raw_df: pd.DataFrame, season: int, snapshot_date: str, source: str, fmt: str) -> pd.DataFrame:
    """Reshape a src.adp_sources fetcher's DataFrame into the unified
    history schema (adds season/snapshot_date/format; drops fetched_at/
    scoring_format/name_key, which the history schema doesn't carry)."""
    if raw_df.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    out = pd.DataFrame({
        'season': season,
        'snapshot_date': snapshot_date,
        'source': source,
        'format': fmt,
        'player_name': raw_df['player_name'],
        'team': raw_df['team'],
        'position': raw_df['position'],
        'adp': raw_df['adp'],
        'high': raw_df['high'],
        'low': raw_df['low'],
        'stdev': raw_df['stdev'],
        'times_drafted': raw_df['times_drafted'],
    })
    return out[HISTORY_COLUMNS]


def ingest_ffc(years, out_dir):
    written = []
    for year in years:
        for fmt in FFC_FORMATS:
            df = fetch_ffc_adp(fmt, year)
            time.sleep(RATE_LIMIT_S)
            if df.empty:
                logger.warning("ffc %s %s: empty — skipping", year, fmt)
                continue
            meta = df.attrs.get('ffc_meta') or {}
            snapshot_date = meta.get('end_date') or date.today().isoformat()
            hist = _to_history_df(df, year, snapshot_date, 'ffc', fmt)
            path = os.path.join(out_dir, f"adp_ffc_{fmt}_{year}.csv")
            hist.to_csv(path, index=False)
            logger.info("Wrote %s (%d rows, snapshot_date=%s)", path, len(hist), snapshot_date)
            written.append((path, len(hist)))
    return written


def ingest_mfl(years, out_dir):
    written = []
    fetch_date = date.today().isoformat()
    for year in years:
        df = fetch_mfl_adp(year)
        time.sleep(RATE_LIMIT_S)
        if df.empty:
            logger.warning("mfl %s: empty — skipping", year)
            continue
        hist = _to_history_df(df, year, fetch_date, 'mfl', 'season_aggregate')
        path = os.path.join(out_dir, f"adp_mfl_season_aggregate_{year}.csv")
        hist.to_csv(path, index=False)
        logger.info("Wrote %s (%d rows)", path, len(hist))
        written.append((path, len(hist)))
    return written


def main():
    parser = argparse.ArgumentParser(description='Ingest historical ADP snapshots (FFC + MFL)')
    parser.add_argument('--source', choices=['ffc', 'mfl', 'both'], default='both')
    parser.add_argument('--years', type=int, nargs='+', default=HISTORY_YEARS)
    parser.add_argument('--output-dir', default=os.path.join('data', 'adp', 'history'))
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    written = []
    if args.source in ('ffc', 'both'):
        written += ingest_ffc(args.years, args.output_dir)
    if args.source in ('mfl', 'both'):
        written += ingest_mfl(args.years, args.output_dir)

    if not written:
        print("ERROR: no history files written")
        return 1

    print(f"\nWrote {len(written)} history file(s):")
    for path, n in written:
        print(f"  {path}: {n} rows")
    return 0


if __name__ == '__main__':
    sys.exit(main())
