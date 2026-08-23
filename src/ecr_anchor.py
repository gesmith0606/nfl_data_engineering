"""WR weekly-ECR ordinal anchor lever (opt-in, two pre-registered mechanisms).

Hypothesis (``.planning/WR_ECR_ORDINAL_GATE.md``): FantasyPros' weekly
expert-consensus rank (ECR) — the crowd itself, not a proxy signal —
resolves the near-tie WR pairs identified in
``.planning/WR_ORDERING_DIAGNOSIS.md`` finding #2 more strongly than the
target-share-slope tie-break ``--wr-tiebreak`` HELD on (54.8% hit rate,
16% of gate bar). Data: ``data/silver/fp_ecr/season=YYYY/`` (DynastyProcess
FantasyPros archive, 2020-2024, PPR-only for RB/WR/TE, local-only — see
``.planning/FP_ECR_HISTORY_COVERAGE.md``).

Join key: ``gsis_id`` in the ECR archive IS this repo's ``player_id``
format (nflverse gsis convention, e.g. ``"00-0033106"`` — verified against
Bronze ``schedules.away_qb_id`` / ``players/weekly.player_id``). No
name-join anywhere in this module — the DynastyProcess crosswalk already
resolved FantasyPros names to ``gsis_id`` at ingestion time, so the
abbreviated-name trap that has bitten this repo six-plus times (see
``knowledge-vault/concepts/gated-experiment-coverage-check.md``) simply
doesn't apply here.

Thursday leakage: every scrape_date in this archive is a Friday. A player
whose own game already kicked off by the scrape date would leak that
game's outcome/injury news into "his" week's ECR. :func:`build_ecr_lookup`
enforces ``kickoff_date > scrape_date`` (strict, date-granularity — the
archive carries no time-of-day) via a team-kickoff lookup built from
Bronze ``schedules``, and reports the exclusion count for the coverage
report.

Two mechanisms (both pre-registered; the tuning-set winner is what a
caller should actually use):

- ``mode="blend"``: ``blended_rank = (1-w)*our_rank + w*ecr_pos_rank``
  for ECR-matched WR rows only; the matched subset's own point values are
  sorted descending and reassigned to players in ascending-blended-rank
  order (rearrangement-inequality-minimal reassignment — the smallest
  point-mass shuffle that exactly realizes the blended order). Unmatched
  WR rows and non-WR rows are untouched.
- ``mode="near_tie"``: reuses ``wr_tiebreak.py``'s exact adjacent-pair
  clustering mechanism and constants (``EPSILON=1.5``, ``NUDGE=0.5``),
  with ``ecr_pos_rank`` substituted for the trailing target-share slope as
  the disagreement signal.

Mirrors the ``wr_tiebreak.py`` / ``adp_prior.py`` opt-in compute/apply
pattern: additive provenance flag, never touches non-WR or unmatched rows.
"""

from __future__ import annotations

import glob
import os
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

#: WR position filter.
WR_POSITION = "WR"

#: Near-tie threshold on our OWN projected_points gap — reused unchanged
#: from ``wr_tiebreak.EPSILON`` (matches the WR_ORDERING_DIAGNOSIS near-tie
#: population).
EPSILON = 1.5

#: Points moved between a qualifying near-tie pair's two members — reused
#: unchanged from ``wr_tiebreak.NUDGE``.
NUDGE = 0.5

#: ECR scoring-variant preference (a set-membership filter, tried as a
#: whole, not a precedence tie-break — see ``_load_ecr_season``). The
#: historical archive (2020-2024, ``data/silver/fp_ecr/season<=2024``) only
#: ever contains "ppr" rows for RB/WR/TE weekly pages (see
#: FP_ECR_HISTORY_COVERAGE.md) — gated entirely on PPR because that's the
#: only scoring variant DynastyProcess's archive ever captured, an
#: archive-only limitation, not a modeling choice. The 2026+ live bridge
#: (``scripts/bridge_fp_ecr_live.py``) captures our own daily FantasyPros
#: refresh, whose honest scoring label is "half_ppr" (``refresh_external_
#: rankings.py``'s un-overridden CLI default) — seeing "ppr" is impossible
#: on a live season and vice versa, so ``isin(ECR_SCORING_PREFERENCE)`` reads
#: exactly the same historical rows the old hardcoded ``== "ppr"`` filter did
#: (proven byte-identical in
#: ``tests/test_ecr_anchor.py::TestScoringPreferenceRegression``) while also
#: reading the live half_ppr rows that filter used to silently return zero
#: of. See ``.planning/ECR_ANCHOR_FORWARD_GATE.md`` §0.2 for the discovery
#: and this amendment.
ECR_SCORING = "ppr"  # kept for backward-compat display/reference only
ECR_SCORING_PREFERENCE: Tuple[str, ...] = ("ppr", "half_ppr")

_DEFAULT_SILVER_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "silver", "fp_ecr"
)


def _load_ecr_season(
    season: int,
    silver_dir: str = _DEFAULT_SILVER_DIR,
    scoring_preference: Tuple[str, ...] = ECR_SCORING_PREFERENCE,
) -> pd.DataFrame:
    """Load one season's Silver FP-ECR parquet, WR rows matching ``scoring_preference``.

    ``scoring_preference`` is a set-membership filter (``scoring.isin(...)``),
    not a precedence tie-break: no season in practice carries more than one
    scoring label under a single ``gsis_id``/week (historical seasons are
    100% "ppr", the 2026+ live bridge is 100% "half_ppr" — see
    ``ECR_SCORING_PREFERENCE``'s docstring), so simple membership is
    sufficient and keeps this byte-identical to the old hardcoded
    ``scoring == "ppr"`` filter for every season that filter used to read.
    If a season ever legitimately carries both labels for the same
    player/week, ``build_ecr_lookup``'s unguarded
    ``drop_duplicates("player_id", keep="first")`` would need an explicit
    scoring tie-break too — not silently handled here, flagged for whoever
    hits it.
    """
    path = os.path.join(silver_dir, f"season={season}", f"fp_ecr_{season}.parquet")
    if not os.path.exists(path):
        return pd.DataFrame(columns=["season", "week", "scrape_date", "position", "gsis_id", "pos_rank"])
    df = pd.read_parquet(path)
    df = df[(df["position"] == WR_POSITION) & (df["scoring"].isin(scoring_preference))].copy()
    return df


def compute_team_kickoff_dates(schedules_df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Per-(week, team) kickoff date for REG games in ``season``.

    Args:
        schedules_df: Bronze ``schedules`` rows (any seasons; filtered
            internally).
        season: NFL season.

    Returns:
        DataFrame with columns ``week``, ``team``, ``kickoff_date``
        (``datetime.date``). Empty (with those columns) on missing input.
    """
    empty = pd.DataFrame(columns=["week", "team", "kickoff_date"])
    required = {"season", "game_type", "week", "gameday", "home_team", "away_team"}
    if schedules_df is None or schedules_df.empty or not required.issubset(schedules_df.columns):
        return empty

    games = schedules_df[
        (schedules_df["season"] == season) & (schedules_df["game_type"] == "REG")
    ].copy()
    if games.empty:
        return empty
    games["kickoff_date"] = pd.to_datetime(games["gameday"]).dt.date

    home = games[["week", "home_team", "kickoff_date"]].rename(columns={"home_team": "team"})
    away = games[["week", "away_team", "kickoff_date"]].rename(columns={"away_team": "team"})
    return pd.concat([home, away], ignore_index=True).drop_duplicates(["week", "team"])


def build_ecr_lookup(
    proj_df: pd.DataFrame,
    season: int,
    week: int,
    schedules_df: pd.DataFrame,
    silver_dir: str = _DEFAULT_SILVER_DIR,
    scoring_preference: Tuple[str, ...] = ECR_SCORING_PREFERENCE,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Build the (player_id -> ecr_pos_rank) lookup for one (season, week), leak-free.

    Args:
        proj_df: This week's WR projections (needs ``player_id``,
            ``position``, ``recent_team``) — used only to resolve each
            player's team for the Thursday-exclusion join, not modified.
        season: NFL season.
        week: Projected week.
        schedules_df: Bronze ``schedules`` rows (any seasons; filtered
            internally to ``season``).
        silver_dir: Root of ``data/silver/fp_ecr/``.
        scoring_preference: Scoring labels to accept, see
            ``ECR_SCORING_PREFERENCE`` / ``_load_ecr_season``. Defaults to
            reading both the historical PPR archive and the live half_ppr
            bridge output.

    Returns:
        ``(lookup_df, stats)`` — ``lookup_df`` has columns ``player_id``,
        ``ecr_pos_rank`` (post Thursday-exclusion, deduplicated). ``stats``
        is a dict with ``n_ecr_wr_rows`` (raw ECR rows this week),
        ``n_team_resolved`` (had a ``recent_team`` match in ``proj_df``),
        ``n_thursday_excluded`` (team's kickoff was not strictly after the
        scrape date), ``n_final_matched`` (survived every filter),
        ``n_proj_wr_rows`` (WR rows in ``proj_df`` this week — denominator
        for the coverage report).
    """
    stats = {
        "n_ecr_wr_rows": 0,
        "n_team_resolved": 0,
        "n_thursday_excluded": 0,
        "n_final_matched": 0,
        "n_proj_wr_rows": 0,
    }
    empty = pd.DataFrame(columns=["player_id", "ecr_pos_rank"])

    if proj_df is None or proj_df.empty or "position" not in proj_df.columns:
        return empty, stats
    proj_wr = proj_df[proj_df["position"] == WR_POSITION]
    stats["n_proj_wr_rows"] = int(len(proj_wr))
    if proj_wr.empty:
        return empty, stats

    ecr_season = _load_ecr_season(season, silver_dir=silver_dir, scoring_preference=scoring_preference)
    ecr_week = ecr_season[ecr_season["week"] == week]
    ecr_week = ecr_week[ecr_week["gsis_id"].notna()]
    stats["n_ecr_wr_rows"] = int(len(ecr_week))
    if ecr_week.empty:
        return empty, stats

    if "recent_team" not in proj_wr.columns:
        return empty, stats
    team_lookup = (
        proj_wr[["player_id", "recent_team"]]
        .dropna(subset=["recent_team"])
        .drop_duplicates("player_id")
        .set_index("player_id")["recent_team"]
    )

    ecr_week = ecr_week.copy()
    ecr_week["player_id"] = ecr_week["gsis_id"].astype(str)
    ecr_week["team"] = ecr_week["player_id"].map(team_lookup)
    resolved = ecr_week[ecr_week["team"].notna()]
    stats["n_team_resolved"] = int(len(resolved))
    if resolved.empty:
        return empty, stats

    kickoffs = compute_team_kickoff_dates(schedules_df, season)
    kickoffs_wk = kickoffs[kickoffs["week"] == week].set_index("team")["kickoff_date"]

    resolved = resolved.copy()
    resolved["kickoff_date"] = resolved["team"].map(kickoffs_wk)
    resolved["scrape_date_parsed"] = pd.to_datetime(resolved["scrape_date"]).dt.date

    # Rows with no kickoff-date match (unresolvable schedule join) cannot
    # be proven leak-free -- treated as excluded, same as a Thursday game,
    # rather than silently defaulting to "safe."
    has_kickoff = resolved["kickoff_date"].notna()
    leak_free = has_kickoff & (resolved["kickoff_date"] > resolved["scrape_date_parsed"])
    stats["n_thursday_excluded"] = int((~leak_free).sum())

    final = resolved[leak_free]
    stats["n_final_matched"] = int(len(final))
    if final.empty:
        return empty, stats

    lookup = (
        final[["player_id", "pos_rank"]]
        .rename(columns={"pos_rank": "ecr_pos_rank"})
        .drop_duplicates("player_id")
        .reset_index(drop=True)
    )
    return lookup, stats


def apply_ecr_anchor_blend(
    proj_df: pd.DataFrame,
    lookup_df: pd.DataFrame,
    weight: float,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Mechanism (a): rank-blend, minimal-reassignment.

    See module docstring for the mechanism. No-op (byte-identical) when
    ``lookup_df`` is empty, ``weight <= 0``, or fewer than 2 WR rows match.
    """
    proj = proj_df.copy()
    if "ecr_anchor_flag" not in proj.columns:
        proj["ecr_anchor_flag"] = False

    if (
        proj.empty
        or lookup_df is None
        or lookup_df.empty
        or weight <= 0
        or "position" not in proj.columns
        or "player_id" not in proj.columns
    ):
        return proj

    is_wr = proj["position"] == WR_POSITION
    if is_wr.sum() < 2:
        return proj

    wr = proj.loc[is_wr].copy()
    wr["_our_rank"] = wr[points_col].rank(ascending=False, method="first")

    lookup = lookup_df.drop_duplicates("player_id").set_index("player_id")["ecr_pos_rank"]
    ecr_rank = wr["player_id"].astype(str).map(lookup)
    matched = ecr_rank.notna()
    if matched.sum() < 2:
        return proj

    matched_idx = wr.index[matched]
    blended_rank = (1.0 - weight) * wr.loc[matched_idx, "_our_rank"] + weight * ecr_rank[matched_idx]

    # Rearrangement-inequality-minimal reassignment: sort the matched
    # subset's own original point values descending, sort the target order
    # (blended_rank) ascending, pair position-by-position.
    original_values = wr.loc[matched_idx, points_col].sort_values(ascending=False).to_numpy()
    target_order_idx = blended_rank.sort_values(ascending=True).index

    proj.loc[target_order_idx, points_col] = np.round(original_values, 2)
    proj.loc[matched_idx, "ecr_anchor_flag"] = True
    return proj


def apply_ecr_anchor_near_tie(
    proj_df: pd.DataFrame,
    lookup_df: pd.DataFrame,
    epsilon: float = EPSILON,
    nudge: float = NUDGE,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Mechanism (b): near-tie-only variant (reuses wr_tiebreak's clustering).

    For every adjacent pair (sorted by ``points_col`` descending) whose gap
    is ``<= epsilon``, if both members are ECR-matched and the ECR order
    disagrees with ours (the lower-projected member has the numerically
    LOWER, i.e. better, ``ecr_pos_rank``), nudge apart by ``nudge`` each.
    """
    proj = proj_df.copy()
    if "ecr_anchor_flag" not in proj.columns:
        proj["ecr_anchor_flag"] = False

    if (
        proj.empty
        or lookup_df is None
        or lookup_df.empty
        or "position" not in proj.columns
        or "player_id" not in proj.columns
    ):
        return proj

    is_wr = proj["position"] == WR_POSITION
    if is_wr.sum() < 2:
        return proj

    lookup = lookup_df.drop_duplicates("player_id").set_index("player_id")["ecr_pos_rank"]

    wr_sorted = proj.loc[is_wr].sort_values(points_col, ascending=False)
    ids = wr_sorted["player_id"].astype(str).to_numpy()
    pts = wr_sorted[points_col].to_numpy(dtype=float)
    row_idx = wr_sorted.index.to_numpy()

    deltas = pd.Series(0.0, index=proj.index)
    fired: set = set()

    for k in range(len(wr_sorted) - 1):
        diff = pts[k] - pts[k + 1]
        if diff > epsilon:
            continue
        ecr_hi = lookup.get(ids[k], np.nan)
        ecr_lo = lookup.get(ids[k + 1], np.nan)
        if pd.isna(ecr_hi) or pd.isna(ecr_lo):
            continue
        if ecr_lo < ecr_hi:
            # ECR disagrees with our order: the lower-projected player has
            # the numerically better (lower) ECR rank. Nudge apart.
            deltas.loc[row_idx[k]] -= nudge
            deltas.loc[row_idx[k + 1]] += nudge
            fired.add(row_idx[k])
            fired.add(row_idx[k + 1])

    if fired:
        fired_idx = list(fired)
        proj.loc[fired_idx, points_col] = (
            proj.loc[fired_idx, points_col] + deltas.loc[fired_idx]
        ).clip(lower=0).round(2)
        proj.loc[fired_idx, "ecr_anchor_flag"] = True

    return proj


def apply_ecr_anchor(
    proj_df: pd.DataFrame,
    lookup_df: pd.DataFrame,
    mode: str = "near_tie",
    weight: Optional[float] = None,
    epsilon: float = EPSILON,
    nudge: float = NUDGE,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Dispatch to :func:`apply_ecr_anchor_blend` or :func:`apply_ecr_anchor_near_tie`.

    Args:
        mode: ``"blend"`` (mechanism a) or ``"near_tie"`` (mechanism b,
            default).
        weight: Required for ``mode="blend"`` (grid-tuned on 2022-2023,
            see ``.planning/WR_ECR_ORDINAL_GATE.md``).
    """
    if mode == "blend":
        return apply_ecr_anchor_blend(
            proj_df, lookup_df, weight=weight if weight is not None else 0.0, points_col=points_col
        )
    if mode == "near_tie":
        return apply_ecr_anchor_near_tie(
            proj_df, lookup_df, epsilon=epsilon, nudge=nudge, points_col=points_col
        )
    raise ValueError(f"Unknown ecr_anchor mode: {mode!r} (expected 'blend' or 'near_tie')")
