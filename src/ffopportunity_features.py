"""ffopportunity Expected-Points Trailing Candidate Features.

Adds trailing (lagged) candidate features on top of the already-built
ffopportunity Silver player-week table (`data/silver/ffopportunity_features/
season=YYYY/`, 2016-2025 — see `.planning/FFOPPORTUNITY_COVERAGE.md` and
`scripts/ingest_ffopportunity.py`, both built by a prior task; this module
does not re-ingest or re-aggregate any raw data). Pre-registered gate:
`.planning/EP_FEATURES_GATE.md`.

Hypothesis: ffopportunity's model-derived expected-fantasy-points and
actual-minus-expected residual are an *opportunity quality* signal that raw
box-score trailing stats miss (e.g. a WR with high expected but low actual
points over recent weeks is a positive-regression candidate).

Raw (unlagged, per-player-week) source columns consumed from Silver:
  - exp_fantasy_points_total       : model's expected fantasy points, summed
                                      across the player's passer/rusher/
                                      receiver roles that week
  - fantasy_points_over_expected   : actual - expected (the residual signal)
  - total_opportunities            : pass_attempts + targets + carries
                                      (derived here; not a Silver column)

These three RAW columns describe the week being predicted and must NEVER be
used directly as model features -- only the trailing variants below.

Exported trailing feature columns (the only columns that should flow into
`player_feature_engineering.py`'s candidate pool):
  - ffopp_{feat}_roll3  : shift(1) rolling 3-week mean within (player_id, season)
  - ffopp_{feat}_roll5  : shift(1) rolling 5-week mean within (player_id, season)
  - ffopp_{feat}_trail  : shift(1) season-to-date (expanding) mean

`FFOPPORTUNITY_EP_FEATURE_COLUMNS` (9 columns) is the production candidate
pool addition.

A second, ablation-only column family (`FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS`,
also 9 columns) is built from the SAME Silver source's raw opportunity counts
(targets/carries/pass_attempts individually, not the model's expected-points
output) using the identical lag/window mechanism. It exists ONLY to
deconfound the gate -- ffopportunity's expected points correlate heavily
with raw volume already in the model's candidate pool, so the gate compares
"pool + EP" against "pool + an equal-count raw-volume set" rather than just
"pool + EP" against "pool alone", to isolate NEW information from
feature-count inflation. It is intentionally NOT wired into
`player_feature_engineering.py` -- see `.planning/EP_FEATURES_GATE.md`.

Usage:
    from ffopportunity_features import (
        compute_ffopportunity_player_week,
        add_ffopportunity_trailing_features,
        build_ffopportunity_features_for_season,
        FFOPPORTUNITY_EP_FEATURE_COLUMNS,
        FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS,
    )
"""

import glob
import logging
import os
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature column registries
# ---------------------------------------------------------------------------

# "Opportunity quality" raw features -- the EP model's own outputs.
FFOPPORTUNITY_EP_RAW_FEATURES: List[str] = [
    "exp_fantasy_points_total",
    "fantasy_points_over_expected",
    "total_opportunities",
]

# Raw volume-only features for the ablation control set -- individual
# opportunity counts, no EP-model information.
FFOPPORTUNITY_VOLUME_RAW_FEATURES: List[str] = [
    "targets",
    "carries",
    "pass_attempts",
]

_WINDOWS = (3, 5)
_MIN_PERIODS = 2

FFOPPORTUNITY_EP_FEATURE_COLUMNS: List[str] = (
    [f"ffopp_{feat}_roll{w}" for feat in FFOPPORTUNITY_EP_RAW_FEATURES for w in _WINDOWS]
    + [f"ffopp_{feat}_trail" for feat in FFOPPORTUNITY_EP_RAW_FEATURES]
)

FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS: List[str] = (
    [
        f"ffopp_vol_{feat}_roll{w}"
        for feat in FFOPPORTUNITY_VOLUME_RAW_FEATURES
        for w in _WINDOWS
    ]
    + [f"ffopp_vol_{feat}_trail" for feat in FFOPPORTUNITY_VOLUME_RAW_FEATURES]
)

_KEY_COLS = ["player_id", "season", "week"]


# ---------------------------------------------------------------------------
# Silver reader
# ---------------------------------------------------------------------------


def _default_silver_dir() -> str:
    """Default Silver root: {project_root}/data/silver.

    Callers may override with a custom `silver_dir` that plays the same
    role — i.e. a directory directly containing `ffopportunity_features/
    season=YYYY/` (see tests, which point this at a tmp_path fixture root).
    """
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "silver")


def compute_ffopportunity_player_week(
    season: int,
    silver_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Load raw (unlagged) ffopportunity Silver features for one season.

    Adds the derived `total_opportunities` column. Callers must apply
    add_ffopportunity_trailing_features() before feeding any of these
    columns into a model -- raw columns describe the week being predicted.

    Args:
        season: NFL season year.
        silver_dir: Root Silver data directory. Defaults to
            {project_root}/data.

    Returns:
        DataFrame with player_id, season, week, team, position, plus
        FFOPPORTUNITY_EP_RAW_FEATURES and FFOPPORTUNITY_VOLUME_RAW_FEATURES
        columns. Empty DataFrame if the season's Silver partition is absent.
    """
    if silver_dir is None:
        silver_dir = _default_silver_dir()

    season_dir = os.path.join(silver_dir, "ffopportunity_features", f"season={season}")
    pattern = os.path.join(season_dir, "ffopportunity_features_*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        logger.info("No ffopportunity Silver data for season %d", season)
        return pd.DataFrame()

    try:
        df = pd.read_parquet(files[-1])
    except Exception as exc:
        logger.warning("Failed to read ffopportunity Silver season %d: %s", season, exc)
        return pd.DataFrame()

    if df.empty:
        return df

    required = {"pass_attempts", "targets", "carries"}
    if not required.issubset(df.columns):
        logger.warning(
            "ffopportunity Silver season %d missing opportunity-count columns "
            "%s; cannot derive total_opportunities",
            season,
            required - set(df.columns),
        )
        return pd.DataFrame()

    df = df.copy()
    df["total_opportunities"] = (
        df["pass_attempts"].fillna(0) + df["targets"].fillna(0) + df["carries"].fillna(0)
    )
    return df


def add_ffopportunity_trailing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add shift(1)-lagged rolling and season-to-date trailing features.

    Computes, within (player_id, season), for every raw feature in
    FFOPPORTUNITY_EP_RAW_FEATURES and FFOPPORTUNITY_VOLUME_RAW_FEATURES:
      - {prefix}{feat}_roll3 : shift(1) rolling 3-week mean
      - {prefix}{feat}_roll5 : shift(1) rolling 5-week mean
      - {prefix}{feat}_trail : shift(1) season-to-date (expanding) mean

    LEAK DISCIPLINE: shift(1) is applied before any rolling/expanding
    calculation, so week W's trailing features describe performance through
    week W-1 only. min_periods=2 means a player's first two weeks of a
    season have all-NaN trailing values (fail-safe on empty/short history --
    no fabricated signal from a single shifted observation).

    Args:
        df: Player-week DataFrame containing player_id, season, week and
            the raw feature columns. Empty/missing-column input returns the
            input unchanged (or empty, if input is empty).

    Returns:
        DataFrame with FFOPPORTUNITY_EP_FEATURE_COLUMNS and
        FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS added.
    """
    if df.empty:
        return df
    if not set(_KEY_COLS).issubset(df.columns):
        logger.warning(
            "add_ffopportunity_trailing_features: missing key columns %s",
            set(_KEY_COLS) - set(df.columns),
        )
        return df

    df = df.sort_values(_KEY_COLS).copy()
    grouped = df.groupby(["player_id", "season"])

    new_cols: dict = {}

    def _add_trailing(feat: str, prefix: str) -> None:
        if feat not in df.columns:
            return
        for w in _WINDOWS:
            new_cols[f"{prefix}{feat}_roll{w}"] = grouped[feat].transform(
                lambda s, w=w: s.shift(1).rolling(w, min_periods=_MIN_PERIODS).mean()
            )
        new_cols[f"{prefix}{feat}_trail"] = grouped[feat].transform(
            lambda s: s.shift(1).expanding(min_periods=_MIN_PERIODS).mean()
        )

    for feat in FFOPPORTUNITY_EP_RAW_FEATURES:
        _add_trailing(feat, "ffopp_")
    for feat in FFOPPORTUNITY_VOLUME_RAW_FEATURES:
        _add_trailing(feat, "ffopp_vol_")

    df = df.assign(**new_cols)
    logger.info(
        "add_ffopportunity_trailing_features: added %d trailing columns", len(new_cols)
    )
    return df


def build_ffopportunity_features_for_season(
    season: int,
    silver_dir: Optional[str] = None,
    include_ablation: bool = True,
) -> pd.DataFrame:
    """Load + lag one season's ffopportunity features in one call.

    Args:
        season: NFL season year.
        silver_dir: Root Silver data directory. Defaults to data/.
        include_ablation: If False, drop the volume-ablation columns from
            the returned frame (they are never needed outside the gate
            script).

    Returns:
        DataFrame keyed by (player_id, season, week) with
        FFOPPORTUNITY_EP_FEATURE_COLUMNS (and, if requested,
        FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS). Empty DataFrame if no Silver
        data exists for the season.
    """
    raw = compute_ffopportunity_player_week(season, silver_dir=silver_dir)
    if raw.empty:
        return pd.DataFrame()

    enriched = add_ffopportunity_trailing_features(raw)

    keep = list(_KEY_COLS) + [
        c for c in FFOPPORTUNITY_EP_FEATURE_COLUMNS if c in enriched.columns
    ]
    if include_ablation:
        keep += [c for c in FFOPPORTUNITY_VOLUME_ABLATION_COLUMNS if c in enriched.columns]
    return enriched[keep].copy()
