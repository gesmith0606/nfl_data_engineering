"""PR 3: the dispersion shrink is fitted per position.

Leave-one-week-out on faithful 2026 w1-9 replay boards (matched cons>=5 rows,
MAE vs ACTUALS): WR with no shrink beat WR at k=0.8 by 0.043 pts (n=542) and by
0.042 on weeks 6-9 alone; QB keeps 0.8 (k=1.0 was +0.052 worse); RB and TE were
small and mixed (CIs include 0) so they keep 0.8.
"""

import os
import subprocess
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dispersion_shrink import (  # noqa: E402
    SHRINK_FACTOR,
    SHRINK_FACTOR_BY_POSITION,
    apply_dispersion_shrink,
)


def _board():
    rows = []
    for pos in ("QB", "RB", "WR", "TE"):
        for i, pts in enumerate([20.0, 16.0, 12.0, 9.0, 7.0, 6.0]):
            rows.append({"player_id": f"{pos}{i}", "position": pos, "projected_points": pts})
    return pd.DataFrame(rows)


def test_shipped_per_position_defaults():
    assert SHRINK_FACTOR == 0.8
    assert SHRINK_FACTOR_BY_POSITION == {"QB": 0.8, "RB": 0.8, "WR": 1.0, "TE": 0.8}


def test_default_leaves_wr_alone_and_shrinks_the_rest():
    out, stats = apply_dispersion_shrink(_board())
    by = out.groupby("position").projected_points.apply(list).to_dict()
    assert by["WR"] == [20.0, 16.0, 12.0, 9.0, 7.0, 6.0]  # untouched
    assert by["QB"][0] < 20.0 and by["TE"][0] < 20.0 and by["RB"][-1] > 6.0
    assert {s["position"] for s in stats} == {"QB", "RB", "TE"}
    assert not out[out.position == "WR"]["dispersion_shrink_flag"].any()


def test_an_explicit_scalar_k_still_applies_to_every_position():
    """--dispersion-shrink-k keeps its meaning: one k for all positions (including WR)."""
    out, stats = apply_dispersion_shrink(_board(), k=0.8)
    assert {s["position"] for s in stats} == {"QB", "RB", "WR", "TE"}
    assert out[out.position == "WR"].projected_points.iloc[0] < 20.0


def test_a_mapping_overrides_positions_and_falls_back_to_the_defaults():
    out, stats = apply_dispersion_shrink(_board(), k={"QB": 0.5})
    st = {s["position"]: s["k"] for s in stats}
    assert st["QB"] == 0.5 and st["RB"] == 0.8 and st["TE"] == 0.8 and "WR" not in st


@pytest.mark.parametrize("bad", [0.0, 1.2, -0.1])
def test_invalid_k_is_rejected_whether_scalar_or_in_a_mapping(bad):
    with pytest.raises(ValueError):
        apply_dispersion_shrink(_board(), k=bad)
    with pytest.raises(ValueError):
        apply_dispersion_shrink(_board(), k={"WR": bad})


def test_scalar_one_is_still_an_explicit_noop():
    out, stats = apply_dispersion_shrink(_board(), k=1.0)
    assert stats == []
    pd.testing.assert_series_equal(out["projected_points"], _board()["projected_points"])


@pytest.mark.parametrize("script", ["generate_projections.py", "backtest_projections.py"])
def test_cli_help_renders_with_the_per_position_default(script):
    out = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "..", "scripts", script), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-400:]
    assert "--dispersion-shrink-k" in out.stdout
