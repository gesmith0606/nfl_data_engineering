"""Consensus anchoring for preseason projections.

The preseason heuristic is a recency-weighted per-game average of the last
two seasons scaled to 17 games.  It has no knowledge of the upcoming season's
context — coaching changes, depth-chart moves, age cliffs, sophomore leaps —
which is precisely what market consensus rankings price in.  The 2026 audit
showed the raw heuristic ranked Jayden Daniels QB14 (consensus QB4) and
Matthew Stafford QB9 (consensus QB20): Spearman vs consensus was only 0.73
for the top-24 QBs.

This module blends the model's projected season points toward the points
implied by the external consensus positional rank, the same anchor-plus-delta
philosophy that let the weekly projections beat Sleeper consensus (v4.3):

    blended = (1 - w) * model_points + w * implied_points(consensus_rank)

``implied_points`` maps a consensus positional rank onto OUR points scale by
interpolating the model's own sorted points curve at that position, so the
output stays in fantasy-points units and non-anchored players remain
comparable.

External rankings come from the ``data/external/{source}_rankings.json``
caches maintained by the weekly-external-projections workflow (Sleeper,
FantasyPros, ESPN, Draft Sharks).
"""

import json
import logging
import re
from pathlib import Path
from statistics import median
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Sources read from data/external/. Matches VALID_SOURCES in
# web/api/services/external_rankings_service.py, which owns the cache files.
CONSENSUS_SOURCES = ["sleeper", "fantasypros", "espn", "draftsharks"]

# Blend weight per position: 0 = pure model, 1 = pure consensus.
# Weights are inversely proportional to how well the raw heuristic tracked
# the market in the 2026 preseason audit (Spearman vs consensus) and to the
# model's demonstrated skill at the position:
#   QB 0.70 — worst raw alignment (0.733), no season-long alpha evidence
#   RB 0.60 — 0.827 raw; RB is also our one weekly deficit vs Sleeper
#   WR 0.60 — 0.787 raw; misses dominated by rookies and situation changes
#   TE 0.50 — 0.889 raw, and TE is our strongest position vs consensus
#   K  0.80 — kicker projections are thin (several established kickers
#             project 0.0); the market is nearly all the signal we have
DEFAULT_CONSENSUS_WEIGHTS: Dict[str, float] = {
    "QB": 0.7,
    "RB": 0.6,
    "WR": 0.6,
    "TE": 0.5,
    "K": 0.8,
}

# Rows flagged is_low_sample_projection (rookies / thin NFL sample) get at
# least this much consensus weight regardless of position: the synthesizer's
# positional baselines are explicitly not market-grade, so when the market
# ranks such a player, trust it. This is what pulls 2026 rookies like
# Jeremiyah Love (consensus RB13, raw model RB73) onto the draftable board.
LOW_SAMPLE_WEIGHT = 0.85

# A player must appear in at least this many sources to be anchored;
# single-source ranks are too noisy to pull a projection.
MIN_SOURCES = 2

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?", re.IGNORECASE)


def normalize_player_name(name: str) -> str:
    """Normalize a player name for cross-source matching.

    Lowercases, strips generational suffixes (Jr/Sr/II-V) and all
    punctuation so "Patrick Mahomes II" and "Amon-Ra St. Brown" match
    their spellings in every source.

    Args:
        name: Raw player name from any source.

    Returns:
        Normalized matching key.
    """
    n = _SUFFIX_RE.sub("", str(name).lower())
    n = n.replace("-", " ")
    n = re.sub(r"[^a-z ]", "", n)
    return re.sub(r"\s+", " ", n).strip()


def load_consensus_ranks(
    external_dir: Path, sources: Optional[list] = None
) -> pd.DataFrame:
    """Load external ranking caches and compute consensus positional ranks.

    Each source file is the canonical cache envelope written by
    ``external_rankings_service``: ``{"source": ..., "fetched_at": ...,
    "players": [{"player_name", "position", "team", ...}, ...]}`` with
    players in overall-rank order.  The positional rank within a source is
    the player's 1-based order among same-position players.

    Args:
        external_dir: Directory holding ``{source}_rankings.json`` caches.
        sources:      Source names to read (default ``CONSENSUS_SOURCES``).

    Returns:
        DataFrame with columns ``name_key``, ``position``,
        ``consensus_pos_rank`` (median across sources) and
        ``consensus_sources`` (source count).  Empty when no caches exist.
    """
    sources = sources if sources is not None else CONSENSUS_SOURCES
    ranks: Dict[tuple, Dict[str, int]] = {}

    for source in sources:
        path = Path(external_dir) / f"{source}_rankings.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text())
            players = payload.get("players", [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable rankings cache %s: %s", path, exc)
            continue

        pos_counter: Dict[str, int] = {}
        for player in players:
            pos = str(player.get("position", "")).upper().strip()
            # Sources sometimes emit "QB1"-style position labels
            pos = re.sub(r"\d+$", "", pos)
            name = player.get("player_name")
            if not pos or not name:
                continue
            pos_counter[pos] = pos_counter.get(pos, 0) + 1
            key = (normalize_player_name(name), pos)
            ranks.setdefault(key, {})[source] = pos_counter[pos]

    rows = [
        {
            "name_key": name_key,
            "position": pos,
            "consensus_pos_rank": float(median(by_source.values())),
            "consensus_sources": len(by_source),
        }
        for (name_key, pos), by_source in ranks.items()
    ]
    return pd.DataFrame(rows)


def apply_consensus_anchor(
    proj: pd.DataFrame,
    external_dir: Path,
    weights: Optional[Dict[str, float]] = None,
    points_col: str = "projected_season_points",
    min_sources: int = MIN_SOURCES,
) -> pd.DataFrame:
    """Blend projected points toward external consensus rankings.

    For each anchored position, the model's own sorted points at that
    position define a points-vs-rank curve; a player's consensus positional
    rank is interpolated on that curve to get consensus-implied points, and
    the final projection is the weighted blend.  Players missing from the
    consensus (or below ``min_sources``) keep their model points untouched.

    Args:
        proj:         Preseason projection DataFrame.  Must contain
                      ``player_name``, ``position`` and ``points_col``.
        external_dir: Directory with ``{source}_rankings.json`` caches.
        weights:      Per-position blend weight (default
                      ``DEFAULT_CONSENSUS_WEIGHTS``).  Positions absent or
                      weighted 0 are left untouched.
        points_col:   Points column to blend in place.
        min_sources:  Minimum source count for a rank to be trusted.

    Returns:
        The projection DataFrame with ``points_col`` blended and provenance
        columns ``consensus_pos_rank``, ``consensus_sources`` and
        ``pre_anchor_points`` added for anchored rows.
    """
    weights = weights if weights is not None else DEFAULT_CONSENSUS_WEIGHTS
    active = {p: w for p, w in weights.items() if w > 0}
    if proj.empty or not active:
        return proj

    consensus = load_consensus_ranks(external_dir)
    if consensus.empty:
        logger.warning(
            "No external ranking caches found in %s — consensus anchor skipped",
            external_dir,
        )
        return proj

    consensus = consensus[consensus["consensus_sources"] >= min_sources]

    proj = proj.copy()
    proj["_name_key"] = proj["player_name"].map(normalize_player_name)
    proj = proj.merge(
        consensus.rename(columns={"name_key": "_name_key"}),
        on=["_name_key", "position"],
        how="left",
    )

    for pos, weight in active.items():
        pos_mask = proj["position"] == pos
        anchored = pos_mask & proj["consensus_pos_rank"].notna()
        if not anchored.any():
            continue

        # Model's own points curve at this position: rank r -> points of the
        # r-th best model projection. Consensus ranks beyond our list clamp
        # to the last (lowest) value via np.interp's edge handling.
        curve = (
            proj.loc[pos_mask, points_col]
            .fillna(0.0)
            .sort_values(ascending=False)
            .to_numpy()
        )
        # Enforce a strictly decreasing curve. Flat segments (e.g. dozens of
        # kickers tied at an identical synthesized value) would otherwise map
        # every consensus rank to the same implied points, collapsing the
        # blend into one big tie with arbitrary order. A 0.5-pt forced
        # descent is a no-op where the curve has real spread and creates a
        # consensus-ordered ramp where it doesn't. 0.5 survives the 1-decimal
        # rounding below at every blend weight >= 0.2.
        for i in range(1, len(curve)):
            curve[i] = min(curve[i], curve[i - 1] - 0.5)
        curve_ranks = np.arange(1, len(curve) + 1)

        implied = np.interp(
            proj.loc[anchored, "consensus_pos_rank"].to_numpy(),
            curve_ranks,
            curve,
        )
        model_pts = proj.loc[anchored, points_col].fillna(0.0).to_numpy()

        # Per-row weight: low-sample rows (rookies / thin NFL sample) lean
        # harder on the market because the model has little real signal.
        row_weight = np.full(len(model_pts), weight)
        if "is_low_sample_projection" in proj.columns:
            low_sample = (
                proj.loc[anchored, "is_low_sample_projection"]
                .eq(True)
                .to_numpy()
            )
            row_weight[low_sample] = np.maximum(
                row_weight[low_sample], LOW_SAMPLE_WEIGHT
            )

        blended = (1.0 - row_weight) * model_pts + row_weight * implied
        # DQAL invariant: projected points >= 0. The forced descent above can
        # push a long flat zero-tail slightly negative.
        blended = np.clip(blended, 0.0, None)

        # Degenerate-tie demotion: when the model assigns one identical value
        # to a large group (the kicker synthesizer hands ~40 kickers exactly
        # the same starter value), that value carries no ordering signal.
        # Un-anchored members of such a group would otherwise sit above every
        # consensus-ranked player at the position; slot them just below the
        # anchored range instead.
        raw_vals = proj.loc[pos_mask, points_col].fillna(0.0).round(1)
        tie_counts = raw_vals.value_counts()
        degenerate_vals = set(tie_counts[tie_counts >= 5].index)
        anchor_floor = float(blended.min())
        unanchored_tied = (
            pos_mask
            & ~anchored
            & proj[points_col].fillna(0.0).round(1).isin(degenerate_vals)
            & (proj[points_col].fillna(0.0) >= anchor_floor)
        )
        if unanchored_tied.any():
            n_demoted = int(unanchored_tied.sum())
            demoted = np.clip(
                anchor_floor - 0.5 * np.arange(1, n_demoted + 1), 0.0, None
            )
            proj.loc[unanchored_tied, "pre_anchor_points"] = proj.loc[
                unanchored_tied, points_col
            ]
            proj.loc[unanchored_tied, points_col] = np.round(demoted, 1)
            logger.info(
                "Demoted %d un-anchored %s rows from a degenerate tie group",
                n_demoted,
                pos,
            )

        proj.loc[anchored, "pre_anchor_points"] = model_pts
        proj.loc[anchored, points_col] = np.round(blended, 1)
        logger.info(
            "Consensus anchor applied to %d %s projections (weight %.2f)",
            int(anchored.sum()),
            pos,
            weight,
        )

    proj.drop(columns=["_name_key"], inplace=True)
    return proj
