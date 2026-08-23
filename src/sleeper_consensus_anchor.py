"""Historical-Sleeper weekly consensus-anchor lever (opt-in, two mechanisms).

Hypothesis (``.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md``): the ECR gate
(``src/ecr_anchor.py``, ``.planning/WR_ECR_ORDINAL_GATE.md``) proved that
blending our WR order toward an independent weekly consensus source produces
a large ordinal-accuracy effect (4.4x its gate bar on the primary metric).
Weekly historical Sleeper projections are a second, independent consensus
source we already possess as our own grading benchmark
(``data/bronze/external_projections/sleeper/season=YYYY/week=WW/``,
2022-2025, full population — not just a top-60ish subset like the FP-ECR
archive). This module ports the same rank-blend / near-tie mechanism family
to that source, generalized across QB/RB/WR/TE (the FP-ECR module was
WR-only by construction; this one takes ``position`` as a parameter so the
pre-registered WR-primary + QB/RB/TE-secondary scope can reuse one module).

**Grading-circularity note (read before interpreting any gate result):**
this lever blends OUR ranking directly toward Sleeper's own ranking. Any
metric that grades "ours" against Sleeper's own numbers (e.g. matched-MAE
vs Sleeper, or a raw rank-correlation-with-Sleeper score) mechanically
improves as the blend weight increases, independent of whether the blend
helps predict anything real — that is convergence to the benchmark, not
model improvement. The gate therefore grades the PRIMARY metric against
REALIZED outcomes only (the FantasyPros-style Accuracy Gap computed from
each source's own rank against a baseline table built purely from actual
points, i.e. ``scripts/simulate_fp_accuracy.py``'s methodology applied to
our own ranking alone) — never against Sleeper's ranking or Sleeper's own
Accuracy Gap value as the improvement target. A "vs Sleeper" delta is still
reported for context, explicitly labeled as convergence.

Join key: Bronze Sleeper rows already carry a ``player_id`` resolved to
this repo's ``gsis_id`` convention at ingestion time (via
``nfl_data_py.import_ids()`` + ``PlayerNameResolver`` fallback — see
``scripts/ingest_external_projections_sleeper.py``). Verified directly
against Bronze ``players/weekly.player_id`` (same format, e.g.
``"00-0033077"``) — no name-join anywhere in this module.

As-of / leak-safety (gate-0 check, done before any gate result — see the
gate doc's Coverage section for the full write-up): the Sleeper historical
projections endpoint omits players who were already ruled out before
kickoff rather than projecting them at ~0 — verified directly (Dak Prescott
is entirely absent from the 2022 Sleeper payload for weeks 3-6, the exact
weeks he was inactive with a thumb injury, and reappears week 7+). This is
the expected signature of a point-in-time, pre-game snapshot, not a
retroactively-revised one. No Thursday-exclusion rule is needed here (unlike
``ecr_anchor.py``'s FP-ECR archive, which is scraped on a fixed weekly
cadence after some games have already kicked off) — treated as a
documented limitation, not a proven guarantee: the exact intra-week capture
time is unknown beyond "pre-game."

Two mechanisms (mirrors ``ecr_anchor.py`` exactly, parameterized by
``position`` instead of hardcoded WR):

- ``mode="blend"``: ``blended_rank = (1-w)*our_rank + w*sleeper_pos_rank``
  for Sleeper-matched rows at ``position`` only; the matched subset's own
  point values are sorted descending and reassigned to players in
  ascending-blended-rank order (rearrangement-inequality-minimal
  reassignment). Unmatched rows and rows at other positions are untouched.
- ``mode="near_tie"``: reuses ``wr_tiebreak.py``/``ecr_anchor.py``'s exact
  adjacent-pair clustering mechanism and constants (``EPSILON=1.5``,
  ``NUDGE=0.5``), with ``sleeper_pos_rank`` substituted as the disagreement
  signal, applied within one position's pool at a time.

Mirrors the ``ecr_anchor.py`` / ``wr_tiebreak.py`` opt-in compute/apply
pattern: additive provenance flag, never touches rows outside the target
position or unmatched rows.
"""

from __future__ import annotations

import glob
import os
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

#: Positions this lever is registered for (WR primary, QB/RB/TE exploratory
#: secondaries per the gate doc's pre-registered scope).
SUPPORTED_POSITIONS = ("QB", "RB", "WR", "TE")

#: Near-tie threshold on our OWN projected_points gap — reused unchanged
#: from ``wr_tiebreak.EPSILON`` / ``ecr_anchor.EPSILON``.
EPSILON = 1.5

#: Points moved between a qualifying near-tie pair's two members — reused
#: unchanged from ``wr_tiebreak.NUDGE`` / ``ecr_anchor.NUDGE``.
NUDGE = 0.5

#: Shipped default configuration for the weekly WR consensus anchor —
#: SHIP verdict 2026-08-22, user-approved (see
#: ``.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md`` Results section: pooled
#: tuning primary gate -0.284 vs 0.05 bar, 2025 one-shot 106.4% retained,
#: guards clean, shuffle-null p=0.0000). DEFAULT-ON in
#: ``scripts/generate_projections.py`` (weekly mode only) and the default
#: evaluation path of ``scripts/backtest_projections.py``; opt out via
#: ``--no-sleeper-anchor``.
SHIPPED_DEFAULT_SRC = "sleeper"
SHIPPED_DEFAULT_POSITION = "WR"
SHIPPED_DEFAULT_MODE = "blend"
SHIPPED_DEFAULT_WEIGHT = 0.5

#: Sleeper Bronze historical projections were backfilled half-PPR only
#: (verified: every season/week sampled 2022-2025 carries
#: ``scoring_format == "half_ppr"``) — matches this repo's grading format
#: exactly, unlike the FP-ECR archive's PPR-only limitation.
SLEEPER_SCORING = "half_ppr"


def resolve_sleeper_anchor_config(
    explicit_src: Optional[str],
    position: str,
    mode: str,
    weight: float,
    no_anchor: bool,
) -> Tuple[Optional[str], str, str, float]:
    """Resolve the effective (src, position, mode, weight) for CLI wiring.

    Shared by ``generate_projections.py`` (weekly mode) and
    ``backtest_projections.py``'s default evaluation path so both scripts
    apply identical precedence for the shipped default
    (``.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md``, SHIP verdict
    2026-08-22):

    1. ``no_anchor`` (``--no-sleeper-anchor``) wins — lever disabled
       (``src=None``), ``position``/``mode``/``weight`` passed through
       unchanged (unused when disabled).
    2. An explicit ``explicit_src`` (``--consensus-anchor-src`` passed)
       wins — the caller's own ``position``/``mode``/``weight`` are used
       verbatim (opt-in override, e.g. to exercise QB/RB/TE or a
       different mode/weight).
    3. Otherwise — the shipped default (``sleeper``, WR, blend,
       weight=0.5).

    Args:
        explicit_src: The raw ``--consensus-anchor-src`` CLI value (``None``
            if the flag was not passed).
        position: The raw ``--consensus-anchor-position`` CLI value.
        mode: The raw ``--consensus-anchor-mode`` CLI value.
        weight: The raw ``--consensus-anchor-weight`` CLI value.
        no_anchor: The raw ``--no-sleeper-anchor`` CLI flag value.

    Returns:
        ``(src, position, mode, weight)`` — ``src`` is ``None`` when the
        lever should not be applied at all.
    """
    if no_anchor:
        return None, position, mode, weight
    if explicit_src is not None:
        return explicit_src, position, mode, weight
    return (
        SHIPPED_DEFAULT_SRC,
        SHIPPED_DEFAULT_POSITION,
        SHIPPED_DEFAULT_MODE,
        SHIPPED_DEFAULT_WEIGHT,
    )

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
_DEFAULT_BRONZE_DIR = os.path.join(
    _PROJECT_ROOT, "data", "bronze", "external_projections", "sleeper"
)


def _load_sleeper_week(
    season: int,
    week: int,
    position: str,
    bronze_dir: str = _DEFAULT_BRONZE_DIR,
) -> pd.DataFrame:
    """Load one (season, week)'s Sleeper Bronze rows, filtered to ``position``.

    Returns the latest timestamped parquet in the partition (mirrors
    ``external_projections._latest_parquet``). Empty DataFrame (with the
    expected columns) if the partition is missing or has no rows for
    ``position``.
    """
    empty = pd.DataFrame(columns=["player_id", "position", "projected_points"])
    week_dir = os.path.join(bronze_dir, f"season={season}", f"week={week:02d}")
    files = sorted(glob.glob(os.path.join(week_dir, "*.parquet")))
    if not files:
        return empty
    df = pd.read_parquet(files[-1])
    if "scoring_format" in df.columns:
        df = df[df["scoring_format"] == SLEEPER_SCORING]
    if "position" not in df.columns or "player_id" not in df.columns:
        return empty
    df = df[df["position"] == position]
    if df.empty:
        return empty
    return df[["player_id", "position", "projected_points"]].copy()


def build_sleeper_lookup(
    proj_df: pd.DataFrame,
    season: int,
    week: int,
    position: str,
    bronze_dir: str = _DEFAULT_BRONZE_DIR,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Build the (player_id -> sleeper_pos_rank) lookup for one (season, week, position).

    Args:
        proj_df: This week's projections (needs ``player_id``,
            ``position``) — used only to size the coverage denominator, not
            modified.
        season: NFL season.
        week: Projected week.
        position: One of :data:`SUPPORTED_POSITIONS`.
        bronze_dir: Root of ``data/bronze/external_projections/sleeper/``.

    Returns:
        ``(lookup_df, stats)`` — ``lookup_df`` has columns ``player_id``,
        ``sleeper_pos_rank`` (1-based, ascending = better, ties broken by
        ``method="first"`` on Sleeper's own ``projected_points``).
        ``stats`` has ``n_proj_pos_rows`` (denominator — rows at
        ``position`` in ``proj_df`` this week), ``n_sleeper_pos_rows`` (raw
        Sleeper rows at ``position`` this week), ``n_final_matched`` (rows
        whose ``player_id`` also appears in ``proj_df``).
    """
    stats = {"n_proj_pos_rows": 0, "n_sleeper_pos_rows": 0, "n_final_matched": 0}
    empty = pd.DataFrame(columns=["player_id", "sleeper_pos_rank"])

    if proj_df is None or proj_df.empty or "position" not in proj_df.columns or "player_id" not in proj_df.columns:
        return empty, stats
    proj_pos = proj_df[proj_df["position"] == position]
    stats["n_proj_pos_rows"] = int(len(proj_pos))
    if proj_pos.empty:
        return empty, stats

    sleeper_week = _load_sleeper_week(season, week, position, bronze_dir=bronze_dir)
    stats["n_sleeper_pos_rows"] = int(len(sleeper_week))
    if sleeper_week.empty:
        return empty, stats

    sleeper_week = sleeper_week.copy()
    sleeper_week["player_id"] = sleeper_week["player_id"].astype(str)
    sleeper_week["sleeper_pos_rank"] = sleeper_week["projected_points"].rank(
        ascending=False, method="first"
    )

    proj_ids = set(proj_pos["player_id"].astype(str))
    matched = sleeper_week[sleeper_week["player_id"].isin(proj_ids)]
    stats["n_final_matched"] = int(len(matched))
    if matched.empty:
        return empty, stats

    lookup = (
        matched[["player_id", "sleeper_pos_rank"]]
        .drop_duplicates("player_id")
        .reset_index(drop=True)
    )
    return lookup, stats


def apply_consensus_anchor_blend(
    proj_df: pd.DataFrame,
    lookup_df: pd.DataFrame,
    weight: float,
    position: str,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Mechanism (a): rank-blend, minimal-reassignment (see module docstring).

    No-op (byte-identical) when ``lookup_df`` is empty, ``weight <= 0``, or
    fewer than 2 rows at ``position`` match.
    """
    proj = proj_df.copy()
    if "sleeper_anchor_flag" not in proj.columns:
        proj["sleeper_anchor_flag"] = False

    if (
        proj.empty
        or lookup_df is None
        or lookup_df.empty
        or weight <= 0
        or "position" not in proj.columns
        or "player_id" not in proj.columns
    ):
        return proj

    is_pos = proj["position"] == position
    if is_pos.sum() < 2:
        return proj

    pool = proj.loc[is_pos].copy()
    pool["_our_rank"] = pool[points_col].rank(ascending=False, method="first")

    lookup = lookup_df.drop_duplicates("player_id").set_index("player_id")["sleeper_pos_rank"]
    sleeper_rank = pool["player_id"].astype(str).map(lookup)
    matched = sleeper_rank.notna()
    if matched.sum() < 2:
        return proj

    matched_idx = pool.index[matched]
    blended_rank = (1.0 - weight) * pool.loc[matched_idx, "_our_rank"] + weight * sleeper_rank[matched_idx]

    # Rearrangement-inequality-minimal reassignment (identical technique to
    # ecr_anchor.apply_ecr_anchor_blend): pair the matched subset's own
    # original point values (sorted desc) with the target blended order
    # (sorted asc) position-by-position.
    original_values = pool.loc[matched_idx, points_col].sort_values(ascending=False).to_numpy()
    target_order_idx = blended_rank.sort_values(ascending=True).index

    proj.loc[target_order_idx, points_col] = np.round(original_values, 2)
    proj.loc[matched_idx, "sleeper_anchor_flag"] = True
    return proj


def apply_consensus_anchor_near_tie(
    proj_df: pd.DataFrame,
    lookup_df: pd.DataFrame,
    position: str,
    epsilon: float = EPSILON,
    nudge: float = NUDGE,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Mechanism (b): near-tie-only variant (reuses wr_tiebreak's clustering).

    For every adjacent pair at ``position`` (sorted by ``points_col``
    descending) whose gap is ``<= epsilon``, if both members are
    Sleeper-matched and Sleeper's order disagrees with ours (the
    lower-projected member has the numerically LOWER, i.e. better,
    ``sleeper_pos_rank``), nudge apart by ``nudge`` each.
    """
    proj = proj_df.copy()
    if "sleeper_anchor_flag" not in proj.columns:
        proj["sleeper_anchor_flag"] = False

    if (
        proj.empty
        or lookup_df is None
        or lookup_df.empty
        or "position" not in proj.columns
        or "player_id" not in proj.columns
    ):
        return proj

    is_pos = proj["position"] == position
    if is_pos.sum() < 2:
        return proj

    lookup = lookup_df.drop_duplicates("player_id").set_index("player_id")["sleeper_pos_rank"]

    pos_sorted = proj.loc[is_pos].sort_values(points_col, ascending=False)
    ids = pos_sorted["player_id"].astype(str).to_numpy()
    pts = pos_sorted[points_col].to_numpy(dtype=float)
    row_idx = pos_sorted.index.to_numpy()

    deltas = pd.Series(0.0, index=proj.index)
    fired: set = set()

    for k in range(len(pos_sorted) - 1):
        diff = pts[k] - pts[k + 1]
        if diff > epsilon:
            continue
        rank_hi = lookup.get(ids[k], np.nan)
        rank_lo = lookup.get(ids[k + 1], np.nan)
        if pd.isna(rank_hi) or pd.isna(rank_lo):
            continue
        if rank_lo < rank_hi:
            # Sleeper disagrees with our order: the lower-projected player
            # has the numerically better (lower) Sleeper rank. Nudge apart.
            deltas.loc[row_idx[k]] -= nudge
            deltas.loc[row_idx[k + 1]] += nudge
            fired.add(row_idx[k])
            fired.add(row_idx[k + 1])

    if fired:
        fired_idx = list(fired)
        proj.loc[fired_idx, points_col] = (
            proj.loc[fired_idx, points_col] + deltas.loc[fired_idx]
        ).clip(lower=0).round(2)
        proj.loc[fired_idx, "sleeper_anchor_flag"] = True

    return proj


def apply_consensus_anchor(
    proj_df: pd.DataFrame,
    lookup_df: pd.DataFrame,
    position: str = "WR",
    mode: str = "near_tie",
    weight: Optional[float] = None,
    epsilon: float = EPSILON,
    nudge: float = NUDGE,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Dispatch to :func:`apply_consensus_anchor_blend` or `_near_tie`.

    Args:
        position: One of :data:`SUPPORTED_POSITIONS` (default ``"WR"``,
            the pre-registered primary; QB/RB/TE are exploratory
            secondaries).
        mode: ``"blend"`` (mechanism a) or ``"near_tie"`` (mechanism b,
            default).
        weight: Required for ``mode="blend"`` (grid-tuned on 2022-2024, see
            ``.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md``).
    """
    if mode == "blend":
        return apply_consensus_anchor_blend(
            proj_df,
            lookup_df,
            weight=weight if weight is not None else 0.0,
            position=position,
            points_col=points_col,
        )
    if mode == "near_tie":
        return apply_consensus_anchor_near_tie(
            proj_df, lookup_df, position=position, epsilon=epsilon, nudge=nudge, points_col=points_col
        )
    raise ValueError(f"Unknown consensus_anchor mode: {mode!r} (expected 'blend' or 'near_tie')")
