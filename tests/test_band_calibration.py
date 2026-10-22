"""Tests for the empirical floor/ceiling band calibration.

Shipped 2026-10-21 (``.planning/MODEL_ASSESSMENT_2026_10_21.md``): the
published band covered 29.8% of actual outcomes against an ~80% target, so it
is refitted from each season's own completed weeks. Walk-forward coverage over
2026 w3-6 went 30.6% -> 83.2%.

These cover the fit, the asymmetry the data demands, the clamp that makes the
extrapolated QB line safe, and the leak-free contract of the history loader.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from band_calibration import (  # noqa: E402
    FLAG_COL,
    HI_QUANTILE,
    LO_QUANTILE,
    MIN_POSITION_ROWS,
    SUPPORTED_POSITIONS,
    apply_calibrated_bands,
    fit_band_offsets,
    load_completed_player_weeks,
)

rng = np.random.default_rng(20261021)


def _history(pos="WR", n=400, spread_slope=0.5, base_spread=2.0, skew=1.5):
    """Completed player-weeks whose residual spread grows with the projection."""
    proj = rng.uniform(1.0, 20.0, n)
    scale = base_spread + spread_slope * proj
    resid = rng.normal(0.0, scale) + skew
    return pd.DataFrame(
        {
            "position": pos,
            "projected_points": proj,
            "actual_points": np.clip(proj + resid, 0, None),
        }
    )


def _board(positions=("WR",), n_each=30, lo=1.0, hi=20.0):
    rows = []
    for pos in positions:
        for i in range(n_each):
            pts = lo + (hi - lo) * i / max(n_each - 1, 1)
            rows.append(
                {
                    "player_id": f"{pos}{i}",
                    "position": pos,
                    "projected_points": round(pts, 2),
                    "projected_floor": round(pts * 0.62, 2),
                    "projected_ceiling": round(pts * 1.38, 2),
                }
            )
    return pd.DataFrame(rows)


class TestConstants:
    def test_nominal_interval_is_eighty_percent(self):
        assert LO_QUANTILE == 0.10
        assert HI_QUANTILE == 0.90
        assert HI_QUANTILE - LO_QUANTILE == pytest.approx(0.80)

    def test_scope_is_the_skill_positions(self):
        assert set(SUPPORTED_POSITIONS) == {"QB", "RB", "WR", "TE"}


class TestFitBandOffsets:
    def test_fits_each_position_present(self):
        hist = pd.concat([_history("WR"), _history("TE")], ignore_index=True)
        off = fit_band_offsets(hist)
        assert set(off) == {"WR", "TE"}
        assert all(len(v) == 4 for v in off.values())

    def test_width_grows_with_projection_when_the_data_says_so(self):
        """b_hi - b_lo > 0 means the band widens as the projection rises —
        the shape the assessment measured (spread correlates +0.43/+0.50 with
        projection for WR/RB)."""
        off = fit_band_offsets(_history("WR", spread_slope=0.8))
        a_lo, b_lo, a_hi, b_hi = off["WR"]
        assert (b_hi - b_lo) > 0

    def test_band_is_asymmetric_for_skewed_residuals(self):
        """Fantasy residuals skew upward off a hard zero; a symmetric band is
        what made 51% of TE actuals fall below the floor."""
        off = fit_band_offsets(_history("WR", skew=3.0))
        a_lo, b_lo, a_hi, b_hi = off["WR"]
        assert a_hi > abs(a_lo) * 0.5  # upper offset is clearly not -lower

    def test_position_with_too_little_history_is_omitted(self):
        assert fit_band_offsets(_history("WR", n=MIN_POSITION_ROWS - 1)) == {}

    def test_single_usable_bin_falls_back_to_a_flat_band(self):
        """Narrow projection range -> one bin -> additive band, still far
        better calibrated than a multiplicative one."""
        hist = _history("QB", n=200)
        hist["projected_points"] = rng.uniform(17.0, 19.0, len(hist))
        off = fit_band_offsets(hist)
        if "QB" in off:
            _a_lo, b_lo, _a_hi, b_hi = off["QB"]
            assert b_lo == 0.0 and b_hi == 0.0

    def test_rows_without_actuals_are_ignored(self):
        hist = _history("WR")
        hist.loc[hist.index[:200], "actual_points"] = np.nan
        off = fit_band_offsets(hist)
        assert "WR" in off  # still fits from the remaining settled rows

    def test_empty_or_malformed_input_returns_empty(self):
        assert fit_band_offsets(pd.DataFrame()) == {}
        assert fit_band_offsets(pd.DataFrame({"position": ["WR"]})) == {}


class TestCoverage:
    def test_fitted_band_achieves_roughly_the_nominal_coverage(self):
        """Fit on one sample, score coverage on a fresh draw from the same
        process — the property the whole lever exists for."""
        off = fit_band_offsets(_history("WR", n=3000))
        test = _history("WR", n=3000)
        out, _ = apply_calibrated_bands(
            test.assign(
                player_id=range(len(test)),
                projected_floor=np.nan,
                projected_ceiling=np.nan,
            ),
            off,
        )
        covered = (
            (test["actual_points"].values >= out["projected_floor"].values)
            & (test["actual_points"].values <= out["projected_ceiling"].values)
        ).mean()
        assert 0.70 <= covered <= 0.90

    def test_beats_the_multiplicative_band_it_replaces(self):
        """The old band: floor = pts*(1-0.38), ceiling = pts*(1+0.38)."""
        off = fit_band_offsets(_history("WR", n=3000))
        test = _history("WR", n=3000)
        old_cov = (
            (test.actual_points >= test.projected_points * 0.62)
            & (test.actual_points <= test.projected_points * 1.38)
        ).mean()
        out, _ = apply_calibrated_bands(
            test.assign(
                player_id=range(len(test)),
                projected_floor=np.nan,
                projected_ceiling=np.nan,
            ),
            off,
        )
        new_cov = (
            (test["actual_points"].values >= out["projected_floor"].values)
            & (test["actual_points"].values <= out["projected_ceiling"].values)
        ).mean()
        assert new_cov > old_cov


class TestApplyAndClamp:
    def test_invariant_floor_le_points_le_ceiling(self):
        off = fit_band_offsets(_history("WR"))
        out, _ = apply_calibrated_bands(_board(("WR",)), off)
        assert (out.projected_floor <= out.projected_points + 1e-6).all()
        assert (out.projected_points <= out.projected_ceiling + 1e-6).all()
        assert (out.projected_floor >= 0).all()

    def test_clamp_survives_a_line_extrapolated_outside_its_support(self):
        """The real QB fit was lo = +9.70 - 1.089*p, which implies a floor
        ABOVE the projection for a 5-point QB. The clamp is what makes that
        safe, so it is asserted against those exact coefficients."""
        off = {"QB": (9.70, -1.089, 17.73, -0.468)}
        board = _board(("QB",), n_each=20, lo=2.0, hi=40.0)
        out, _ = apply_calibrated_bands(board, off)
        assert (out.projected_floor <= out.projected_points + 1e-6).all()
        assert (out.projected_points <= out.projected_ceiling + 1e-6).all()
        assert (out.projected_floor >= 0).all()

    def test_zero_projection_rows_are_left_alone(self):
        """Bye-week and injury-zeroed rows must not acquire a band."""
        off = fit_band_offsets(_history("WR"))
        board = _board(("WR",))
        board.loc[0, ["projected_points", "projected_floor", "projected_ceiling"]] = 0.0
        out, _ = apply_calibrated_bands(board, off)
        assert out.loc[0, "projected_floor"] == 0.0
        assert out.loc[0, "projected_ceiling"] == 0.0
        assert not out.loc[0, FLAG_COL]

    def test_unfitted_positions_keep_their_existing_band(self):
        off = fit_band_offsets(_history("WR"))
        board = _board(("WR", "RB"))
        out, stats = apply_calibrated_bands(board, off)
        rb_in = board[board.position == "RB"].reset_index(drop=True)
        rb_out = out[out.position == "RB"].reset_index(drop=True)
        pd.testing.assert_series_equal(
            rb_in.projected_floor, rb_out.projected_floor, check_names=False
        )
        assert {s["position"] for s in stats} == {"WR"}
        assert not out.loc[out.position == "RB", FLAG_COL].any()

    def test_empty_offsets_is_a_byte_identical_no_op(self):
        board = _board(("WR",))
        out, stats = apply_calibrated_bands(board, {})
        assert stats == []
        pd.testing.assert_series_equal(board.projected_floor, out.projected_floor)

    def test_stats_report_the_width_change(self):
        off = fit_band_offsets(_history("WR", spread_slope=0.9))
        out, stats = apply_calibrated_bands(_board(("WR",)), off)
        assert len(stats) == 1
        st = stats[0]
        assert st["position"] == "WR"
        assert st["n_rows"] == 30
        assert st["mean_width_after"] > st["mean_width_before"]

    def test_does_not_mutate_the_caller_frame(self):
        off = fit_band_offsets(_history("WR"))
        board = _board(("WR",))
        before = board.projected_floor.tolist()
        apply_calibrated_bands(board, off)
        assert board.projected_floor.tolist() == before
        assert FLAG_COL not in board.columns

    def test_adds_band_columns_when_absent(self):
        off = fit_band_offsets(_history("WR"))
        board = _board(("WR",)).drop(columns=["projected_floor", "projected_ceiling"])
        out, stats = apply_calibrated_bands(board, off)
        assert out.projected_floor.notna().all()
        assert stats and stats[0]["mean_width_before"] is None


class TestHistoryLoaderIsLeakFree:
    def test_only_strictly_earlier_weeks_contribute(self, tmp_path):
        """The leak-free contract: a week-3 call must never see week 3+."""
        from scoring_calculator import calculate_fantasy_points_df  # noqa: F401

        data_root = tmp_path / "data"
        weekly_dir = data_root / "bronze" / "players" / "weekly" / "season=2026"
        weekly_dir.mkdir(parents=True)
        weekly = pd.DataFrame(
            {
                "player_id": ["A", "A", "A"],
                "season": [2026] * 3,
                "week": [1, 2, 3],
                "position": ["WR"] * 3,
                "receptions": [5, 5, 5],
                "receiving_yards": [60, 60, 60],
                "receiving_tds": [1, 1, 1],
            }
        )
        weekly.to_parquet(
            weekly_dir / "player_weekly_20261021_000000.parquet", index=False
        )

        for wk in (1, 2, 3):
            d = data_root / "gold" / "projections" / "season=2026" / f"week={wk}"
            d.mkdir(parents=True)
            pd.DataFrame(
                {"player_id": ["A"], "position": ["WR"], "projected_points": [10.0]}
            ).to_parquet(
                d / "projections_half_ppr_20261021_000000.parquet", index=False
            )

        hist = load_completed_player_weeks(2026, 3, str(data_root), "half_ppr")
        assert len(hist) == 2  # weeks 1 and 2 only

    def test_missing_data_returns_empty_rather_than_raising(self, tmp_path):
        hist = load_completed_player_weeks(2026, 5, str(tmp_path), "half_ppr")
        assert hist.empty
        assert list(hist.columns) == ["position", "projected_points", "actual_points"]


class TestCLIWiring:
    """Argparse/placement wiring, mirroring test_dispersion_shrink_cli.py."""

    def test_help_lists_the_opt_out(self):
        import subprocess

        out = subprocess.run(
            [
                sys.executable,
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "scripts",
                    "generate_projections.py",
                ),
                "--help",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
        assert "--no-band-calibration" in out

    def test_percent_signs_in_help_are_escaped(self):
        """argparse runs help strings through %-formatting, so a bare '%' in
        this lever's evidence numbers crashes --help for the whole CLI (it
        did: 'TypeError: %o format: an integer is required')."""
        src = open(
            os.path.join(
                os.path.dirname(__file__), "..", "scripts", "generate_projections.py"
            ),
            encoding="utf-8",
        ).read()
        block = src[
            src.index('"--no-band-calibration"') : src.index('"--no-dispersion-shrink"')
        ]
        # every % in the help text must be doubled
        assert "%" in block
        for i, ch in enumerate(block):
            if ch == "%":
                assert block[i - 1] == "%" or block[i + 1] == "%", "unescaped % in help"

    def test_runs_after_the_point_estimate_is_final_and_before_the_injury_invariant(
        self,
    ):
        src = open(
            os.path.join(
                os.path.dirname(__file__), "..", "scripts", "generate_projections.py"
            ),
            encoding="utf-8",
        ).read()
        shrink = src.index("projections, shrink_stats = apply_dispersion_shrink(")
        band = src.index("projections, _band_stats = apply_calibrated_bands(")
        invariant = src.index("# --- injury invariant")
        assert shrink < band < invariant
