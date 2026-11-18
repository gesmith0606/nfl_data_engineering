"""Serve-time feature-coverage guard for the residual (hybrid) models.

Why: the residual models were fitted on feature matrices where ~80-86% of the
cells were populated (2025: QB .86, RB .83, WR .82, TE .80). A live run can
hand them a matrix that is mostly empty (NGS/PFR/PBP-derived columns absent,
ingest steps are ``continue-on-error``), and the imputer then silently fills the
holes with training means. On the 2026 local data the QB matrix was 48%
populated and the QB residual made the board worse than the bare heuristic
(MAE 6.38 vs 5.97, weeks 1-9, no anchor) while every row still read
``projection_source == "hybrid"``.

The guard compares the share of non-NaN cells in the matrix about to be scored
with the share the model was trained on and, when it falls below
``min_ratio`` x the training share, skips that position's residual, labels the
rows and prints a GitHub Actions ``::warning::``.

The training share comes from ``meta["train_feature_nonnan_share"]`` when a
model's meta carries it, else from the tracked sidecar
``src/residual_feature_coverage.json`` (written by
``scripts/measure_residual_feature_coverage.py``). It lives in a sidecar rather
than in ``models/residual/*_meta.json`` so no model artifact has to be edited
or retrained.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, Optional

import numpy as np
import pandas as pd

#: Skip a position's residual when its serve-time share is below this fraction
#: of its training share. QB local 2026: .48 / .86 = .56 (skipped); RB .76,
#: WR .73, TE .80 (applied).
MIN_RATIO: float = 0.70

REFERENCE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "residual_feature_coverage.json")


def nonnan_share(X: pd.DataFrame) -> float:
    """Share of populated cells in a feature matrix (NaN for an empty one)."""
    if X is None or X.size == 0:
        return float("nan")
    return float(X.notna().to_numpy().mean())


def load_reference(path: Optional[str] = None) -> Dict[str, Any]:
    """The sidecar mapping ``position -> {"nonnan_share": float, ...}`` ({} if absent)."""
    p = path or REFERENCE_PATH
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def training_share(position: str, meta: Optional[Dict[str, Any]], reference: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """Training non-NaN share for ``position``: model meta first, then the sidecar."""
    if meta and meta.get("train_feature_nonnan_share") is not None:
        return float(meta["train_feature_nonnan_share"])
    ref = reference if reference is not None else load_reference()
    entry = ref.get(position.upper())
    return float(entry["nonnan_share"]) if entry and entry.get("nonnan_share") is not None else None


def check_coverage(
    position: str,
    X: pd.DataFrame,
    meta: Optional[Dict[str, Any]] = None,
    min_ratio: Optional[float] = MIN_RATIO,
    reference: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Decide whether the residual for ``position`` should run on ``X``.

    Returns:
        ``{"ok": bool, "serve": float, "train": float|None, "ratio": float|None,
        "reason": str}``. ``ok`` is True when the guard is off (``min_ratio``
        falsy), when no training share is known (cannot judge, so do not block),
        or when the serve share is at least ``min_ratio`` x the training share.
    """
    serve = nonnan_share(X)
    train = training_share(position, meta, reference)
    out: Dict[str, Any] = {"ok": True, "serve": serve, "train": train, "ratio": None, "reason": ""}
    if not min_ratio:
        out["reason"] = "guard off"
        return out
    if train is None or not np.isfinite(serve):
        out["reason"] = "no training share on record" if train is None else "empty matrix"
        return out
    out["ratio"] = serve / train if train > 0 else None
    if out["ratio"] is not None and out["ratio"] < min_ratio:
        out["ok"] = False
        out["reason"] = f"serve share {serve:.2f} is {out['ratio']:.0%} of training share {train:.2f} (floor {min_ratio:.0%})"
    return out


def warning_line(position: str, verdict: Dict[str, Any]) -> str:
    """The GitHub Actions annotation printed when the guard skips a residual."""
    return (
        f"::warning::{position} residual SKIPPED by the feature-coverage guard: {verdict['reason']}; "
        f"rows keep the heuristic and read projection_source='heuristic'"
    )


def measure_reference(
    positions: Iterable[str],
    features_by_position: Dict[str, Iterable[str]],
    seasons: Iterable[int],
    min_week: int = 3,
) -> Dict[str, Any]:
    """Non-NaN share of each position's model features on assembled history.

    Rows are every assembled player-week at the position from ``min_week`` on
    (the population the live board is scored on), columns are the model's own
    feature list, columns that do not exist count as NaN.
    """
    from player_feature_engineering import assemble_player_features

    frames = [assemble_player_features(s) for s in seasons]
    feats = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    out: Dict[str, Any] = {}
    for pos in positions:
        sub = feats[(feats["position"] == pos) & (feats["week"] >= min_week)]
        cols = list(features_by_position[pos])
        X = pd.DataFrame({c: sub[c].to_numpy() if c in sub.columns else np.nan for c in cols}, index=sub.index)
        out[pos] = {
            "nonnan_share": round(nonnan_share(X), 4),
            "n_rows": int(len(sub)),
            "n_features": len(cols),
            "seasons": sorted(int(s) for s in seasons),
            "min_week": min_week,
        }
    return out
