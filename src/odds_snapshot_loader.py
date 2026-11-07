"""Loader for Bronze Odds API snapshots → per-game open-proxy and close lines.

Reads the timestamped Parquet files written by
``scripts/bronze_odds_api_ingestion.py`` and derives:

- **Open-proxy line**: the first snapshot captured for each game (earliest
  ``snapshot_ts`` before ``commence_time``).
- **Close line**: the last snapshot captured *before* kickoff.  Snapshots
  taken after ``commence_time`` are treated as in-game data and excluded.

Consensus is computed as the **median** across all bookmakers present in the
open/close snapshot to reduce single-book outlier noise.

Supported markets: ``"spreads"`` and ``"totals"``.

Typical usage
-------------
    from src.odds_snapshot_loader import load_open_close_lines

    lines_df = load_open_close_lines(
        snapshot_dir="data/bronze/odds_api/snapshots",
        season=2026,
        market="spreads",
    )
    # Returns DataFrame keyed on (home_team_nfl, away_team_nfl) with columns:
    #   home_team_nfl, away_team_nfl, commence_time,
    #   open_spread, close_spread, n_books_open, n_books_close

Notes
-----
- The function is tolerant of missing seasons / empty directories — it returns
  an empty DataFrame with the correct columns so callers can always join safely.
- Sign convention for ``home_spread`` is the SPORTSBOOK convention: *negative =
  home is the favourite* (the raw bookmaker point passed through by the
  ingestion script). WARNING: this is the OPPOSITE of nflverse
  ``spread_line``, which is the expected HOME MARGIN (positive = home
  favoured). Convert with ``margin = -home_spread`` before comparing to
  nflverse-derived predictions.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Default Bronze directory (project-relative; override in tests via argument).
_DEFAULT_BRONZE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "bronze", "odds_api", "snapshots")
)

# Schema columns guaranteed present in every Bronze snapshot file.
_SNAPSHOT_COLS = [
    "snapshot_ts",
    "game_id_ext",
    "commence_time",
    "home_team",
    "away_team",
    "home_team_nfl",
    "away_team_nfl",
    "bookmaker",
    "market",
    "home_spread",
    "total_points",
    "price_home",
    "price_away",
    "season",
]

# Output column sets per market.
_SPREAD_OUTPUT_COLS = [
    "home_team_nfl",
    "away_team_nfl",
    "commence_time",
    "open_spread",
    "close_spread",
    "n_books_open",
    "n_books_close",
    "open_days_before_kickoff",
]

_TOTAL_OUTPUT_COLS = [
    "home_team_nfl",
    "away_team_nfl",
    "commence_time",
    "open_total",
    "close_total",
    "n_books_open",
    "n_books_close",
    "open_days_before_kickoff",
]


def _parse_utc(ts: str) -> datetime:
    """Parse an ISO-8601 UTC string to a timezone-aware datetime.

    Handles both ``Z``-suffix and ``+00:00``-suffix formats produced by the
    ingestion script.

    Args:
        ts: ISO-8601 UTC timestamp string.

    Returns:
        Timezone-aware UTC datetime.
    """
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def _load_season_snapshots(
    snapshot_dir: str,
    season: int,
) -> pd.DataFrame:
    """Read all Parquet snapshot files for a given season into one DataFrame.

    Args:
        snapshot_dir: Path to the Bronze snapshots root directory.
        season: NFL season year (directory name: ``season=YYYY``).

    Returns:
        Concatenated DataFrame of all snapshots for the season, or an empty
        DataFrame with schema columns if none exist.
    """
    season_dir = os.path.join(snapshot_dir, f"season={season}")
    if not os.path.isdir(season_dir):
        logger.debug("No snapshot directory found: %s", season_dir)
        return pd.DataFrame(columns=_SNAPSHOT_COLS)

    parquet_files = sorted(
        f for f in os.listdir(season_dir) if f.endswith(".parquet")
    )
    if not parquet_files:
        logger.debug("No parquet files in %s", season_dir)
        return pd.DataFrame(columns=_SNAPSHOT_COLS)

    frames: List[pd.DataFrame] = []
    for fname in parquet_files:
        path = os.path.join(season_dir, fname)
        try:
            frames.append(pd.read_parquet(path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read %s: %s", path, exc)

    if not frames:
        return pd.DataFrame(columns=_SNAPSHOT_COLS)

    combined = pd.concat(frames, ignore_index=True)
    logger.debug(
        "Loaded %d snapshot rows from season=%d (%d files)",
        len(combined),
        season,
        len(frames),
    )
    return combined


def _coerce_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Parse ``snapshot_ts`` and ``commence_time`` into UTC datetimes.

    Operates in-place on a copy; safe to call on empty DataFrames.

    Args:
        df: DataFrame with string ``snapshot_ts`` and ``commence_time`` columns.

    Returns:
        Copy of df with those columns as timezone-aware datetime64[ns, UTC].
    """
    df = df.copy()
    if df.empty:
        return df

    def _safe_parse(ts_series: pd.Series) -> pd.Series:
        """Vectorised ISO-8601 parser; returns NaT on any unparseable value.

        Compatible with pandas 1.x and 2.x.  Normalises Z-suffix and
        +00:00-suffix ISO strings before parsing.
        """
        normalized = ts_series.str.replace("Z", "+00:00", regex=False)
        return pd.to_datetime(normalized, utc=True, errors="coerce")

    df["snapshot_ts"] = _safe_parse(df["snapshot_ts"])
    df["commence_time"] = _safe_parse(df["commence_time"])
    return df


def _derive_open_close(
    game_df: pd.DataFrame,
    line_col: str,
    open_within_days: Optional[float] = None,
) -> dict:
    """Compute open-proxy and close consensus for one game × one market.

    The open-proxy is the median across bookmakers of the *first* snapshot
    (by ``snapshot_ts``).  The close is the median across bookmakers of the
    *last pre-kickoff* snapshot.

    ``open_within_days`` restricts which snapshots may serve as the open to
    those within that many days of kickoff.  Without it the open is the first
    snapshot ever captured for the game, which on the 2026 capture history sits
    a **median 109 days before kickoff** — a summer futures price, not an
    opener anybody could bet in the game week.  See
    ``.planning/OPEN_PROXY_VALIDATION_2026_10_25.md``: measuring capture across
    that window carries sd 3.20 pts, versus 1.32 inside 7 days.

    Args:
        game_df: Filtered DataFrame for one game (one ``game_id_ext``), one
            market, already sorted ascending by ``snapshot_ts``.  Must have
            ``snapshot_ts``, ``commence_time``, and ``line_col`` columns.
        line_col: Column name containing the numeric line value
            (``"home_spread"`` or ``"total_points"``).
        open_within_days: When set, only snapshots at most this many days
            before kickoff may be the open.  ``None`` (default) keeps the
            historical behaviour of taking the first snapshot ever captured.

    Returns:
        Dict with keys ``open_line``, ``close_line``, ``n_books_open``,
        ``n_books_close``, ``open_days_before_kickoff``.  Values are NaN when
        data is unavailable.  The close is always derived from the full
        pre-kickoff history, so narrowing the open window never costs a close.
    """
    empty: dict = {
        "open_line": float("nan"),
        "close_line": float("nan"),
        "n_books_open": 0,
        "n_books_close": 0,
        "open_days_before_kickoff": float("nan"),
    }

    valid = game_df.dropna(subset=[line_col, "snapshot_ts", "commence_time"])
    if valid.empty:
        return empty

    commence = valid["commence_time"].iloc[0]

    # Pre-kickoff only — exclude in-game / post-game snapshots.
    pre_kick = valid[valid["snapshot_ts"] < commence]
    if pre_kick.empty:
        logger.debug(
            "No pre-kickoff snapshots for game_id_ext=%s",
            game_df["game_id_ext"].iloc[0] if "game_id_ext" in game_df.columns else "?",
        )
        return empty

    # Last snapshot timestamp (close-proxy).  Always the full history.
    last_ts = pre_kick["snapshot_ts"].max()
    close_rows = pre_kick[pre_kick["snapshot_ts"] == last_ts]
    close_line = float(close_rows[line_col].median())
    n_books_close = int(close_rows[line_col].notna().sum())

    # Open candidates, optionally restricted to the betting week.
    open_candidates = pre_kick
    if open_within_days is not None:
        cutoff = commence - pd.Timedelta(days=float(open_within_days))
        open_candidates = pre_kick[pre_kick["snapshot_ts"] >= cutoff]

    if open_candidates.empty:
        # No price inside the window.  Returning NaN excludes the game from
        # capture rather than substituting a price nobody could have bet.
        return {
            "open_line": float("nan"),
            "close_line": close_line,
            "n_books_open": 0,
            "n_books_close": n_books_close,
            "open_days_before_kickoff": float("nan"),
        }

    first_ts = open_candidates["snapshot_ts"].min()
    open_rows = open_candidates[open_candidates["snapshot_ts"] == first_ts]

    return {
        "open_line": float(open_rows[line_col].median()),
        "close_line": close_line,
        "n_books_open": int(open_rows[line_col].notna().sum()),
        "n_books_close": n_books_close,
        "open_days_before_kickoff": (commence - first_ts).total_seconds() / 86400.0,
    }


def load_open_close_lines(
    season: int,
    market: str = "spreads",
    snapshot_dir: Optional[str] = None,
    open_within_days: Optional[float] = None,
) -> pd.DataFrame:
    """Derive per-game open-proxy and close consensus lines from Bronze snapshots.

    Reads all Parquet snapshot files for ``season`` from the Bronze directory,
    filters to the requested ``market``, and computes a consensus median across
    bookmakers for the first (open-proxy) and last pre-kickoff (close) snapshot
    of each game.

    Args:
        season: NFL season year (e.g., 2026).
        market: ``"spreads"`` or ``"totals"``.
        snapshot_dir: Path to the Bronze snapshots root directory.  Defaults to
            ``data/bronze/odds_api/snapshots`` relative to the project root.
        open_within_days: When set, the open must be a snapshot taken at most
            this many days before kickoff.  ``None`` (default) preserves the
            historical behaviour — the first snapshot EVER captured, which on
            2026 data is a median 109 days out and is therefore a futures
            price, not a betting-week opener.  Pass ``7`` for line-capture
            work; see ``.planning/OPEN_PROXY_VALIDATION_2026_10_25.md``, which
            shows every one of the 93 settled 2026 games still has a snapshot
            (median 16, 8 of 9 books) inside 7 days, so the narrower window
            costs no sample.

    Returns:
        DataFrame keyed on ``(home_team_nfl, away_team_nfl)`` with columns
        depending on market:

        Spreads market:
            - ``home_team_nfl``, ``away_team_nfl``, ``commence_time``
            - ``open_spread``: consensus open-proxy home spread.
            - ``close_spread``: consensus closing home spread.
            - ``n_books_open``, ``n_books_close``: bookmaker counts.
            - ``open_days_before_kickoff``: how far out the open was taken, so
              a stale open is visible rather than implicit.

        Totals market:
            - ``home_team_nfl``, ``away_team_nfl``, ``commence_time``
            - ``open_total``: consensus open-proxy over/under total.
            - ``close_total``: consensus closing total.
            - ``n_books_open``, ``n_books_close``: bookmaker counts.

        Returns an empty DataFrame (with correct columns) when no snapshot
        data exists for the season/market combination.

    Raises:
        ValueError: If ``market`` is not ``"spreads"`` or ``"totals"``.
    """
    if market not in ("spreads", "totals"):
        raise ValueError(f"market must be 'spreads' or 'totals', got {market!r}")

    if snapshot_dir is None:
        snapshot_dir = _DEFAULT_BRONZE_DIR

    if market == "spreads":
        line_col = "home_spread"
        open_key, close_key = "open_spread", "close_spread"
        output_cols = _SPREAD_OUTPUT_COLS
    else:
        line_col = "total_points"
        open_key, close_key = "open_total", "close_total"
        output_cols = _TOTAL_OUTPUT_COLS

    raw = _load_season_snapshots(snapshot_dir, season)
    if raw.empty:
        logger.info("No snapshot data for season=%d market=%s", season, market)
        return pd.DataFrame(columns=output_cols)

    raw = _coerce_timestamps(raw)

    # Filter to the requested market type.
    market_df = raw[raw["market"] == market].copy()
    if market_df.empty:
        logger.info(
            "No rows for market=%s in season=%d snapshots", market, season
        )
        return pd.DataFrame(columns=output_cols)

    # Sort once by snapshot time before grouping.
    market_df = market_df.sort_values("snapshot_ts")

    rows: List[dict] = []
    for game_id_ext, game_df in market_df.groupby("game_id_ext", sort=False):
        result = _derive_open_close(
            game_df, line_col, open_within_days=open_within_days
        )

        # Carry through team identity from any row in the group.
        first_row = game_df.iloc[0]
        rows.append({
            "home_team_nfl": first_row.get("home_team_nfl"),
            "away_team_nfl": first_row.get("away_team_nfl"),
            "commence_time": first_row.get("commence_time"),
            open_key: result["open_line"],
            close_key: result["close_line"],
            "n_books_open": result["n_books_open"],
            "n_books_close": result["n_books_close"],
            "open_days_before_kickoff": result["open_days_before_kickoff"],
        })

    if not rows:
        return pd.DataFrame(columns=output_cols)

    result_df = pd.DataFrame(rows, columns=output_cols)

    n_with_open = result_df[open_key].notna().sum()
    n_with_close = result_df[close_key].notna().sum()
    n_no_pre_kick = (result_df[close_key].isna() & result_df[open_key].notna()).sum()

    logger.info(
        "season=%d market=%s: %d games — %d with open-proxy, %d with close, "
        "%d missing pre-kickoff snapshots",
        season,
        market,
        len(result_df),
        n_with_open,
        n_with_close,
        n_no_pre_kick,
    )

    return result_df
