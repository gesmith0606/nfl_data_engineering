#!/usr/bin/env python3
"""
Bridge — live FantasyPros rankings capture -> Silver FP-ECR (2026+).

``--ecr-anchor`` (``src/ecr_anchor.py``, HOLD-pending-forward-gate, see
``.planning/WR_ECR_ORDINAL_GATE.md``) reads its weekly WR consensus signal
from ``data/silver/fp_ecr/season=YYYY/``. That archive
(``scripts/ingest_fp_ecr_history.py``, DynastyProcess/FantasyPros, GPL-3.0 +
FantasyPros ToS, local-only) stops at 2024 -- there is no sealed 2025 and no
2026 data in it at all. This script is the bridge: it turns OUR OWN daily
FantasyPros rankings capture (``data/external/fantasypros_rankings.json`` +
dated gzip archive under ``data/external/archive/YYYY-MM-DD/``, refreshed by
``scripts/refresh_external_rankings.py`` via the daily-sentiment cron) into
rows matching the historical Silver schema column-for-column, so the 2026
in-season forward gate (``.planning/ECR_ANCHOR_FORWARD_GATE.md``) has
*something* to read starting week 1.

READ THIS BEFORE TRUSTING THE OUTPUT (2026-08-21 bridge session findings)
--------------------------------------------------------------------------
1. **SOURCE MISMATCH (the big one).** ``refresh_external_rankings.py
   ::fetch_fantasypros`` always calls FantasyPros' partners
   ``consensus-rankings.php`` with ``week=0&type=draft`` -- the perpetual
   SEASON-LONG REDRAFT/overall board -- with no code path that switches to a
   weekly per-position page once the season starts. The historical archive
   ``--ecr-anchor`` was gated against came from FantasyPros' *weekly-position*
   pages (``ppr-wr.php`` etc, re-scraped each week, reacting to that week's
   matchups/injuries -- see ``ingest_fp_ecr_history.py``'s own docstring).
   Our live capture is a much slower-moving, week-agnostic signal. This
   bridge maps it honestly (below) but a forward gate built on top of it is
   testing "does anchoring toward FantasyPros' OVERALL draft consensus help
   WR ordering," which is a materially weaker/different hypothesis than the
   one ``WR_ECR_ORDINAL_GATE.md`` actually validated on 2022-2024 weekly
   data. Flagged loudly here and in ``ECR_ANCHOR_FORWARD_GATE.md`` -- not
   silently assumed equivalent.
2. **SCHEMA.** Our capture is ``{player_name, position, team, rank,
   external_rank}`` only (see ``refresh_external_rankings.py::
   _parse_fp_partners_players`` / ``save_rankings``'s envelope). No
   per-expert dispersion (``sd``/``best``/``worst`` -> always null), no float
   ECR average (only an integer overall-board rank -- ``ecr`` is left null
   rather than faked as a float we don't have), and no FantasyPros numeric
   player id (``fantasypros_id`` -> always null; the historical ingestion's
   DynastyProcess id-crosswalk join has nothing to join against here). Id
   resolution instead goes through ``src.player_name_resolver
   .PlayerNameResolver`` (fuzzy name match against Bronze rosters/depth
   charts), reported loudly, hard-failing under 90% WR match (see
   ``resolve_gsis_ids``).
3. **SCORING.** The daily cron (``.github/workflows/daily-sentiment.yml``)
   calls ``refresh_external_rankings.py`` with no ``--scoring`` flag, so it
   uses that script's own default, ``"half_ppr"``. ``src/ecr_anchor.py``
   hardcodes ``ECR_SCORING = "ppr"`` (the only weekly-position scoring
   variant that ever existed in the historical archive). This bridge writes
   the HONEST scoring label (``"half_ppr"``) for these rows rather than
   mislabeling them ``"ppr"`` to force a match through that filter -- see
   ``ECR_ANCHOR_FORWARD_GATE.md`` for the exact consequence (zero rows read
   by ``build_ecr_lookup`` until that filter is generalized) and why fixing
   it is out of this script's ownership.
4. **PRESEASON WEEK MAPPING.** Every capture date so far
   (2026-07-09 .. today) is well before the 2026 week-1 window (kickoff
   2026-09-09) closes, so the reused
   ``ingest_fp_ecr_history.map_scrape_date_to_week()`` maps ALL of them to
   ``week=1`` -- the exact same "smallest week not yet concluded" rule the
   historical ingestion applies, run unchanged against 2026 dates. That
   collapses 40+ distinct daily snapshots onto one (season=2026, week=1)
   partition. Rows are written sorted by ``scrape_date`` DESCENDING
   specifically because ``src/ecr_anchor.py::build_ecr_lookup`` ends with a
   naive ``drop_duplicates("player_id", keep="first")`` and has no
   scrape_date tie-break of its own -- writing newest-first makes the
   freshest (closest-to-kickoff, most-informed) capture win that dedup.
5. **Position scope.** Historical Silver rows only ever covered
   QB/RB/WR/TE (``ingest_fp_ecr_history.WEEKLY_PAGE_TYPES``); our capture
   also includes K, which this bridge drops to keep the schema's position
   domain identical.

Idempotency: re-running for a date that's already in the season parquet
REPLACES that date's rows (matched on exact ``scrape_date``); it never
duplicates. Safe to re-run for the same day, or backfill every archived day,
as often as needed.

Usage
-----
::

    # Bridge every available capture (all archive dates + the current live
    # snapshot) -- the normal invocation.
    python scripts/bridge_fp_ecr_live.py

    # Bridge one specific archived date only.
    python scripts/bridge_fp_ecr_live.py --date 2026-08-18

    # Point at a different capture root (tests).
    python scripts/bridge_fp_ecr_live.py --external-dir /tmp/fixture_external
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import ingest_fp_ecr_history as fpecr_ingest  # noqa: E402 -- reuse the season/week mapper, don't reimplement it
from src.player_name_resolver import PlayerNameResolver  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

EXTERNAL_DIR = os.path.join(_PROJECT_ROOT, "data", "external")
ARCHIVE_DIR = os.path.join(EXTERNAL_DIR, "archive")
LIVE_FILE = os.path.join(EXTERNAL_DIR, "fantasypros_rankings.json")
SILVER_OUT_DIR = fpecr_ingest.SILVER_OUT_DIR  # data/silver/fp_ecr -- same root the historical ingestion writes

# Historical Silver schema, column-for-column (reused, not re-declared, so
# the two scripts can never drift apart on column order/names).
SILVER_COLUMNS = fpecr_ingest.SILVER_COLUMNS

# Only these positions ever existed in the historical archive
# (ingest_fp_ecr_history.WEEKLY_PAGE_TYPES == weekly-{qb,rb,wr,te}).
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}

# True scoring label of our daily capture (refresh_external_rankings.py's
# own CLI default, which the daily-sentiment cron never overrides). See
# module docstring finding #3 -- this deliberately does NOT match
# src/ecr_anchor.py's hardcoded ECR_SCORING="ppr" filter.
LIVE_SCORING = "half_ppr"

# The source label recorded on our own captures (refresh_external_rankings
# .save_rankings envelope's "source" field for FantasyPros).
LIVE_SOURCE_NAME = "fantasypros"

# FantasyPros team codes that don't match nflverse convention used by
# PlayerNameResolver's Bronze index (only affects the team/position
# tiebreaker among same-named players -- primary name match is unaffected).
_TEAM_CODE_FIX = {"JAC": "JAX"}

#: Hard gate -- resolving fewer than this fraction of WR rows to a gsis_id
#: means something is badly wrong (stale roster snapshot, capture schema
#: change, etc.) and the run should fail loud rather than silently ship a
#: mostly-empty lookup.
MIN_WR_MATCH_RATE = 0.90


# ---------------------------------------------------------------------------
# Loading captures
# ---------------------------------------------------------------------------


@dataclass
class Capture:
    """One day's FantasyPros capture: its true scrape date + player rows."""

    scrape_date: date
    players: List[Dict]


def _parse_envelope(raw_text: str) -> Optional[Dict]:
    """Parse a rankings JSON envelope, tolerating the legacy bare-list format."""
    data = json.loads(raw_text)
    if isinstance(data, dict) and "players" in data:
        return data
    return None  # legacy bare-list caches predate FantasyPros captures we care about


def load_archive_captures(archive_dir: str = ARCHIVE_DIR) -> List[Capture]:
    """Load every archived FantasyPros snapshot, scrape_date from the folder name.

    The folder name (``YYYY-MM-DD``) is the ground-truth capture date -- it's
    written by ``refresh_external_rankings.archive_rankings_snapshot`` at the
    moment that day's content changed, which is exactly the leakage boundary
    this bridge needs (see module docstring finding #4).
    """
    captures: List[Capture] = []
    if not os.path.isdir(archive_dir):
        return captures
    for day_name in sorted(os.listdir(archive_dir)):
        try:
            scrape_date = datetime.strptime(day_name, "%Y-%m-%d").date()
        except ValueError:
            continue
        gz_path = os.path.join(archive_dir, day_name, f"{LIVE_SOURCE_NAME}_rankings.json.gz")
        if not os.path.isfile(gz_path):
            continue
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            envelope = _parse_envelope(f.read())
        if not envelope:
            continue
        captures.append(Capture(scrape_date=scrape_date, players=envelope.get("players", [])))
    return captures


def load_live_capture(live_file: str = LIVE_FILE) -> Optional[Capture]:
    """Load the current (not-yet-archived) FantasyPros snapshot.

    ``save_rankings()`` only rewrites ``fetched_at`` when the content
    actually changed (see ``refresh_external_rankings.py``), so this is a
    trustworthy "true last-changed date" even on days the archive step
    didn't run or skipped an unchanged write.
    """
    if not os.path.isfile(live_file):
        return None
    with open(live_file, "r", encoding="utf-8") as f:
        envelope = _parse_envelope(f.read())
    if not envelope or envelope.get("source") != LIVE_SOURCE_NAME:
        return None
    fetched_at = envelope.get("fetched_at")
    if not fetched_at:
        return None
    scrape_date = datetime.fromisoformat(fetched_at).date()
    return Capture(scrape_date=scrape_date, players=envelope.get("players", []))


def load_all_captures(
    archive_dir: str = ARCHIVE_DIR, live_file: str = LIVE_FILE
) -> List[Capture]:
    """Archive dates plus the live snapshot, deduplicated by scrape_date."""
    captures = load_archive_captures(archive_dir)
    seen_dates = {c.scrape_date for c in captures}
    live = load_live_capture(live_file)
    if live and live.scrape_date not in seen_dates:
        captures.append(live)
    return captures


# ---------------------------------------------------------------------------
# Shaping a capture into positional rows
# ---------------------------------------------------------------------------


def capture_to_position_ranked_rows(players: List[Dict]) -> pd.DataFrame:
    """Derive within-position ordinal rank from the capture's overall board rank.

    Our capture has no per-position rank field -- only ``rank`` (overall,
    across all captured positions). Grouping by position and re-ranking by
    ``rank`` ascending reproduces exactly what the historical archive's
    weekly-position pages published directly (WR1, WR2, ... by consensus).

    Returns:
        DataFrame with columns ``player_name``, ``position``, ``team``,
        ``pos_rank`` (1-based, ascending = better), restricted to
        ``FANTASY_POSITIONS``. Empty (with those columns) on empty input.
    """
    cols = ["player_name", "position", "team", "pos_rank"]
    if not players:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(players)
    if df.empty or "position" not in df.columns:
        return pd.DataFrame(columns=cols)
    df = df[df["position"].isin(FANTASY_POSITIONS)].copy()
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["pos_rank"] = df.groupby("position")["rank"].rank(method="min").astype(int)
    return df[["player_name", "position", "team", "pos_rank"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Id resolution
# ---------------------------------------------------------------------------


def resolve_gsis_ids(
    df: pd.DataFrame, resolver: PlayerNameResolver, cache: Optional[Dict] = None
) -> pd.DataFrame:
    """Resolve ``player_name``/``team``/``position`` to ``gsis_id`` via fallback tiers.

    Tier 1: name + team (normalized) + position.
    Tier 2: name + position only (covers mid-season trades our team hint
        would otherwise mismatch).
    Tier 3: name only.

    Results are memoized in ``cache`` (keyed on the raw input tuple) since
    the same player recurs across dozens of daily captures.

    Args:
        df: Output of ``capture_to_position_ranked_rows`` (or equivalent).
        resolver: A ``PlayerNameResolver`` instance (reused across calls).
        cache: Optional dict shared across multiple calls for memoization.

    Returns:
        ``df`` with a new ``gsis_id`` column (``None`` where unresolved).
    """
    if cache is None:
        cache = {}
    if df.empty:
        out = df.copy()
        out["gsis_id"] = pd.Series(dtype="object")
        return out

    def _resolve_row(name: str, team: str, position: str) -> Optional[str]:
        key = (name, team, position)
        if key in cache:
            return cache[key]
        norm_team = _TEAM_CODE_FIX.get(str(team).upper(), team) if team else None
        result = (
            resolver.resolve(name, team=norm_team, position=position)
            or resolver.resolve(name, position=position)
            or resolver.resolve(name)
        )
        cache[key] = result
        return result

    out = df.copy()
    out["gsis_id"] = [
        _resolve_row(row.player_name, row.team, row.position) for row in out.itertuples()
    ]
    return out


def _report_match_rate(df: pd.DataFrame, scrape_date: date) -> float:
    """Log per-date match rates (loud, per instructions); return the WR rate."""
    if df.empty:
        logger.warning("%s: no rows to resolve", scrape_date)
        return 1.0
    overall_rate = df["gsis_id"].notna().mean()
    wr = df[df["position"] == "WR"]
    wr_rate = wr["gsis_id"].notna().mean() if not wr.empty else 1.0
    logger.info(
        "%s: gsis_id match rate overall=%.1f%% (%d rows) | WR=%.1f%% (%d rows)",
        scrape_date,
        overall_rate * 100,
        len(df),
        wr_rate * 100,
        len(wr),
    )
    return wr_rate


# ---------------------------------------------------------------------------
# Season/week assignment + Silver row assembly
# ---------------------------------------------------------------------------


def build_silver_rows(capture: Capture, resolver: PlayerNameResolver, cache: Dict) -> pd.DataFrame:
    """One capture -> Silver-schema rows (season/week resolved, gsis_id resolved).

    Returns an empty (columns-only) frame if the capture pre-dates any known
    schedule (no REG-week mapping) or has no fantasy-relevant rows.
    """
    ranked = capture_to_position_ranked_rows(capture.players)
    if ranked.empty:
        return pd.DataFrame(columns=SILVER_COLUMNS)

    season = fpecr_ingest.derive_season(capture.scrape_date)
    windows = fpecr_ingest.load_schedule_reg_windows(season)
    week = fpecr_ingest.map_scrape_date_to_week(capture.scrape_date, windows)
    if week is None:
        logger.warning(
            "%s: no REG-week mapping for season %d (no schedule, or past week 18) -- dropped",
            capture.scrape_date,
            season,
        )
        return pd.DataFrame(columns=SILVER_COLUMNS)

    resolved = resolve_gsis_ids(ranked, resolver, cache=cache)
    wr_rate = _report_match_rate(resolved, capture.scrape_date)
    if wr_rate < MIN_WR_MATCH_RATE:
        raise RuntimeError(
            f"{capture.scrape_date}: WR gsis_id match rate {wr_rate:.1%} is below the "
            f"{MIN_WR_MATCH_RATE:.0%} floor -- failing loud rather than shipping a "
            "silently degraded ECR lookup (check for a capture schema change or a "
            "stale roster/depth-chart snapshot)."
        )

    out = pd.DataFrame(
        {
            "season": season,
            "week": week,
            "scrape_date": capture.scrape_date,
            "scoring": LIVE_SCORING,
            "position": resolved["position"],
            "player_name": resolved["player_name"],
            "fantasypros_id": pd.array([pd.NA] * len(resolved), dtype="Int64"),
            "gsis_id": resolved["gsis_id"],
            "sleeper_id": pd.array([pd.NA] * len(resolved), dtype="Float64"),
            "ecr": pd.array([pd.NA] * len(resolved), dtype="Float64"),
            "pos_rank": resolved["pos_rank"].astype("int32"),
            "sd": pd.array([pd.NA] * len(resolved), dtype="Float64"),
            "best": pd.array([pd.NA] * len(resolved), dtype="Int64"),
            "worst": pd.array([pd.NA] * len(resolved), dtype="Int64"),
        }
    )
    return out[SILVER_COLUMNS]


# ---------------------------------------------------------------------------
# Idempotent write
# ---------------------------------------------------------------------------


def upsert_silver_season(
    new_rows: pd.DataFrame, season: int, silver_dir: str = SILVER_OUT_DIR
) -> str:
    """Merge ``new_rows`` into ``season``'s Silver parquet, replacing any
    existing rows for the exact ``scrape_date`` values present in ``new_rows``.

    Re-running the bridge for a date that's already on disk REPLACES that
    date's rows rather than duplicating them (idempotent per requirement).
    Rows are sorted by ``scrape_date`` DESCENDING before writing -- see
    module docstring finding #4 for why that matters to a downstream
    consumer's dedup.

    Returns:
        The path written.
    """
    season_dir = os.path.join(silver_dir, f"season={season}")
    os.makedirs(season_dir, exist_ok=True)
    out_path = os.path.join(season_dir, f"fp_ecr_{season}.parquet")

    if new_rows.empty:
        return out_path

    dates_touched = set(new_rows["scrape_date"].unique())
    if os.path.exists(out_path):
        existing = pd.read_parquet(out_path)
        existing = existing[~existing["scrape_date"].isin(dates_touched)]
        combined = pd.concat([existing, new_rows], ignore_index=True)
    else:
        combined = new_rows

    combined = combined.sort_values("scrape_date", ascending=False).reset_index(drop=True)
    combined.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows (%d dates touched) -> %s", len(combined), len(dates_touched), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_bridge(
    dates: Optional[List[date]] = None,
    external_dir: str = EXTERNAL_DIR,
    silver_dir: str = SILVER_OUT_DIR,
) -> Dict[str, int]:
    """Bridge one or more capture dates into Silver. ``dates=None`` -> all available.

    Returns a small summary dict (rows written, dates processed, per-season counts).
    """
    archive_dir = os.path.join(external_dir, "archive")
    live_file = os.path.join(external_dir, "fantasypros_rankings.json")
    all_captures = load_all_captures(archive_dir=archive_dir, live_file=live_file)
    if dates is not None:
        wanted = set(dates)
        all_captures = [c for c in all_captures if c.scrape_date in wanted]

    if not all_captures:
        logger.warning("No FantasyPros captures found to bridge (external_dir=%s)", external_dir)
        return {"rows_written": 0, "dates_processed": 0}

    resolver = PlayerNameResolver()
    cache: Dict = {}

    rows_by_season: Dict[int, List[pd.DataFrame]] = {}
    for capture in sorted(all_captures, key=lambda c: c.scrape_date):
        rows = build_silver_rows(capture, resolver, cache)
        if rows.empty:
            continue
        season = int(rows["season"].iloc[0])
        rows_by_season.setdefault(season, []).append(rows)

    total_rows = 0
    for season, frames in rows_by_season.items():
        season_rows = pd.concat(frames, ignore_index=True)
        upsert_silver_season(season_rows, season, silver_dir=silver_dir)
        total_rows += len(season_rows)

    return {"rows_written": total_rows, "dates_processed": len(all_captures)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--date", help="Single capture date to bridge (YYYY-MM-DD). Default: every available date."
    )
    parser.add_argument(
        "--external-dir", default=EXTERNAL_DIR, help="Root of data/external/ (tests override this)."
    )
    parser.add_argument(
        "--silver-dir", default=SILVER_OUT_DIR, help="Root of data/silver/fp_ecr/ (tests override this)."
    )
    args = parser.parse_args()

    dates = None
    if args.date:
        dates = [datetime.strptime(args.date, "%Y-%m-%d").date()]

    try:
        summary = run_bridge(dates=dates, external_dir=args.external_dir, silver_dir=args.silver_dir)
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1

    print(f"\nBridged {summary['dates_processed']} capture date(s), {summary['rows_written']} rows written.")
    print(
        "\nNOTE: scoring label is honest 'half_ppr' (see module docstring #3) -- "
        "src/ecr_anchor.py's hardcoded ECR_SCORING='ppr' filter will read ZERO of "
        "these rows until that mismatch is resolved. See .planning/ECR_ANCHOR_FORWARD_GATE.md."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
