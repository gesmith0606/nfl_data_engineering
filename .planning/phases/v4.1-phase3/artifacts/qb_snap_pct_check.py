#!/usr/bin/env python3
"""Confirm the QB heuristic zeroing bug is caused by snap_pct being all-NaN."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import PLAYER_DATA_SEASONS  # noqa: E402
from player_feature_engineering import assemble_multiyear_player_features  # noqa: E402
from projection_engine import _usage_multiplier, _weighted_baseline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log = logging.getLogger("snap_check")

log.info("Loading…")
ALL = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)

# Check snap_pct for QB, RB, WR, TE
for pos in ["QB", "RB", "WR", "TE"]:
    sub = ALL[ALL["position"] == pos]
    if "snap_pct" in sub.columns:
        log.info(
            "%s snap_pct: nan_rate=%.3f mean=%.3f median=%.3f nonzero=%.3f",
            pos,
            sub["snap_pct"].isna().mean(),
            sub["snap_pct"].mean(),
            sub["snap_pct"].median(),
            (sub["snap_pct"] > 0).mean(),
        )
    else:
        log.info("%s snap_pct: COLUMN MISSING", pos)

    if "target_share" in sub.columns:
        log.info(
            "%s target_share: nan_rate=%.3f mean=%.3f",
            pos,
            sub["target_share"].isna().mean(),
            sub["target_share"].mean(),
        )

    if "carry_share" in sub.columns:
        log.info(
            "%s carry_share: nan_rate=%.3f mean=%.3f",
            pos,
            sub["carry_share"].isna().mean(),
            sub["carry_share"].mean(),
        )

    # The usage multiplier function:
    umult = _usage_multiplier(sub, pos)
    log.info(
        "%s usage_multiplier: nan_rate=%.3f mean=%.3f min=%.3f max=%.3f",
        pos,
        umult.isna().mean(),
        umult.mean(),
        umult.min(),
        umult.max(),
    )
    log.info("")

# Confirm what columns in the QB slice might look like snap_pct-ish
qb = ALL[ALL["position"] == "QB"]
snap_like = [c for c in qb.columns if "snap" in c.lower()]
log.info("Snap-like columns in QB data: %s", snap_like)
for c in snap_like:
    log.info("  %s: nan_rate=%.3f mean=%s",
             c, qb[c].isna().mean(), qb[c].mean())

# Check also: offense_pct, offense_snaps, etc.
off_like = [c for c in qb.columns if c.startswith("offense") or "offense_pct" in c.lower()]
log.info("offense-like columns: %s", off_like)
for c in off_like[:10]:
    if c in qb.columns:
        log.info("  %s: nan_rate=%.3f mean=%s",
                 c, qb[c].isna().mean(), qb[c].mean())
