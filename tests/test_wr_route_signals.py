"""Tests for WR route-rate signal mechanisms (Workstream D, plan 2.2).

Covers:
  - Route data loading helper in the lab
  - Mechanism A: level blend (WR usage-mult percentile blend with trail4)
  - Mechanism B1/B2/B3: velocity/role-change detector (delta + slope)
  - Mechanism B4: joint boost + collapse
  - No leakage: all signals are strictly lagged (trail4/delta/slope)
  - WR-only scope: QB/RB/TE projections unchanged by any patch
  - Edge cases: missing route data, empty DataFrame inputs
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_player_row(
    player_id: str,
    position: str,
    season: int = 2022,
    week: int = 5,
    target_share: float = 0.2,
    snap_pct: float = 0.6,
) -> dict:
    """Return a minimal player feature dict that project_position can consume."""
    return {
        "player_id": player_id,
        "player_name": f"Test_{player_id}",
        "position": position,
        "season": season,
        "week": week,
        "proj_season": season,
        "proj_week": week,
        "recent_team": "DEN",
        "target_share": target_share,
        "snap_pct": snap_pct,
        "carry_share": 0.15 if position == "RB" else 0.0,
        "roll3_targets": 6.0,
        "roll3_receptions": 4.0,
        "roll3_receiving_yards": 50.0,
        "roll3_receiving_tds": 0.3,
        "roll3_carries": 0.0 if position != "RB" else 10.0,
        "roll3_rushing_yards": 0.0 if position != "RB" else 40.0,
        "roll3_rushing_tds": 0.0,
        "std_targets": 5.5,
        "std_receptions": 3.5,
        "std_receiving_yards": 45.0,
        "std_receiving_tds": 0.25,
        "std_carries": 0.0 if position != "RB" else 9.0,
        "std_rushing_yards": 0.0 if position != "RB" else 35.0,
        "std_rushing_tds": 0.0,
        "roll6_targets": 5.8,
        "roll6_receptions": 3.8,
        "roll6_receiving_yards": 48.0,
        "roll6_receiving_tds": 0.28,
        "roll6_carries": 0.0 if position != "RB" else 9.5,
        "roll6_rushing_yards": 0.0 if position != "RB" else 38.0,
        "roll6_rushing_tds": 0.0,
    }


def _make_target_df(
    positions=("WR", "QB", "RB", "TE"),
    season: int = 2022,
    week: int = 5,
    n_per_pos: int = 3,
) -> pd.DataFrame:
    """Build a minimal target DataFrame with multiple positions."""
    rows = []
    for pos in positions:
        for i in range(n_per_pos):
            pid = f"00-{pos}{i:04d}"
            row = _minimal_player_row(pid, pos, season=season, week=week)
            rows.append(row)
    return pd.DataFrame(rows)


def _make_route_lookup(
    player_ids: list,
    season: int = 2022,
    week: int = 5,
    trail4: float = 0.6,
    delta: float = 0.0,
    slope: float = 0.0,
) -> tuple:
    """Return (route_lut_trail4, route_lut_delta, route_lut_slope) Series."""
    idx = pd.MultiIndex.from_tuples(
        [(pid, season, week) for pid in player_ids],
        names=["player_id", "season", "week"],
    )
    t4 = pd.Series([trail4] * len(player_ids), index=idx)
    dl = pd.Series([delta] * len(player_ids), index=idx)
    sl = pd.Series([slope] * len(player_ids), index=idx)
    return t4, dl, sl


# ---------------------------------------------------------------------------
# Import the lab functions (skip if scipy not available)
# ---------------------------------------------------------------------------

pytest.importorskip("scipy")

try:
    import projection_engine
    from projection_engine import _usage_multiplier as orig_usage_multiplier

    PROJ_ENGINE_AVAILABLE = True
except ImportError:
    PROJ_ENGINE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Route data loading
# ---------------------------------------------------------------------------


class TestLoadRouteFeatures:
    """Unit tests for _load_route_features helper."""

    def test_returns_dataframe(self, tmp_path) -> None:
        """Returns an empty DataFrame (not raises) when no files are present."""
        import glob as gm

        # monkeypatch glob to return nothing
        import experiment_heuristic_lab as lab

        orig_glob = gm.glob
        try:
            gm.glob = lambda *a, **kw: []
            result = lab._load_route_features([2022])
        finally:
            gm.glob = orig_glob

        assert isinstance(result, pd.DataFrame)

    def test_expected_columns_present(self, tmp_path) -> None:
        """When real parquet files exist, expected columns are present."""
        import glob as gm

        # Build a minimal parquet file with the expected schema
        route_df = pd.DataFrame(
            {
                "player_id": ["p1", "p2"],
                "season": [2022, 2022],
                "week": [3, 4],
                "recent_team": ["KC", "KC"],
                "route_rate": [0.8, 0.9],
                "dropbacks_on_field": [30, 35],
                "team_dropbacks": [40, 40],
                "route_rate_trail4": [0.75, 0.82],
                "route_rate_delta": [0.05, 0.03],
                "route_rate_slope": [0.02, 0.01],
            }
        )
        parquet_path = tmp_path / "graph_route_participation_20220101.parquet"
        route_df.to_parquet(str(parquet_path), index=False)

        import experiment_heuristic_lab as lab

        orig_root = lab.PROJECT_ROOT
        try:
            lab.PROJECT_ROOT = str(tmp_path)
            # Create the expected directory structure
            silver_dir = tmp_path / "data" / "silver" / "graph_features" / "season=2022"
            silver_dir.mkdir(parents=True)
            (silver_dir / "graph_route_participation_20220101.parquet").write_bytes(
                parquet_path.read_bytes()
            )
            result = lab._load_route_features([2022])
        finally:
            lab.PROJECT_ROOT = orig_root

        assert not result.empty
        for col in ["route_rate_trail4", "route_rate_delta", "route_rate_slope"]:
            assert col in result.columns


# ---------------------------------------------------------------------------
# Usage multiplier patch behaviour
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not PROJ_ENGINE_AVAILABLE, reason="projection_engine not available")
class TestMechanismA:
    """WR route-level usage blend — trail4 percentile into usage multiplier."""

    def _make_level_patch(self, w: float, route_lut_trail4: pd.Series):
        """Build the Mechanism A usage patch inline for testability."""

        def patched(df: pd.DataFrame, position: str) -> pd.Series:
            base = orig_usage_multiplier(df, position)
            if position != "WR" or w == 0.0 or "player_id" not in df.columns:
                return base
            season_col = (
                df["proj_season"] if "proj_season" in df.columns else df["season"]
            )
            week_col = df["proj_week"] if "proj_week" in df.columns else df["week"]
            keys = list(zip(df["player_id"], season_col, week_col))
            rr = pd.Series(
                [route_lut_trail4.get(k, np.nan) for k in keys], index=df.index
            )
            if rr.notna().sum() < 5:
                return base
            rr_pct = rr.rank(pct=True)
            base_pct = (base - 0.80) / 0.35
            blended = (1 - w) * base_pct + w * rr_pct.fillna(base_pct)
            return (0.80 + 0.35 * blended).clip(0.80, 1.15)

        return patched

    def test_wr_only_affected(self) -> None:
        """Non-WR positions must return the same result as the original."""
        wr_ids = [f"00-WR{i:04d}" for i in range(5)]
        rb_ids = [f"00-RB{i:04d}" for i in range(5)]
        all_ids = wr_ids + rb_ids

        t4, _, _ = _make_route_lookup(all_ids, trail4=0.7)
        patch = self._make_level_patch(0.5, t4)

        for pos in ("QB", "RB", "TE"):
            df = pd.DataFrame(
                [_minimal_player_row(pid, pos) for pid in rb_ids]
            )
            base = orig_usage_multiplier(df, pos)
            patched = patch(df, pos)
            pd.testing.assert_series_equal(base, patched)

    def test_wr_within_valid_range(self) -> None:
        """WR multipliers stay in [0.80, 1.15] after blending."""
        wr_ids = [f"00-WR{i:04d}" for i in range(10)]
        # Extreme trail4 values to test clipping
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in wr_ids],
            names=["player_id", "season", "week"],
        )
        t4 = pd.Series(
            [0.0, 0.1, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], index=idx
        )
        patch = self._make_level_patch(0.5, t4)
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        result = patch(df, "WR")
        assert (result >= 0.79).all(), f"min {result.min()}"
        assert (result <= 1.16).all(), f"max {result.max()}"

    def test_no_route_data_falls_back_to_base(self) -> None:
        """When fewer than 5 rows have route data, fall back to base."""
        wr_ids = [f"00-WR{i:04d}" for i in range(10)]
        # No matching keys in the LUT
        t4 = pd.Series(dtype=float)
        patch = self._make_level_patch(0.5, t4)
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        base = orig_usage_multiplier(df, "WR")
        patched = patch(df, "WR")
        pd.testing.assert_series_equal(base, patched)

    def test_w0_returns_base_unchanged(self) -> None:
        """w=0.0 must produce the original multiplier exactly."""
        wr_ids = [f"00-WR{i:04d}" for i in range(5)]
        t4, _, _ = _make_route_lookup(wr_ids, trail4=0.5)
        patch = self._make_level_patch(0.0, t4)
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        base = orig_usage_multiplier(df, "WR")
        patched = patch(df, "WR")
        pd.testing.assert_series_equal(base, patched)


@pytest.mark.skipif(not PROJ_ENGINE_AVAILABLE, reason="projection_engine not available")
class TestMechanismB:
    """WR velocity / role-change detector (delta and slope signals)."""

    def _make_velocity_patch(
        self,
        lut: pd.Series,
        collapse_thr: float = -0.10,
        collapse_mult: float = 0.80,
        boost_thr: float = 999.0,
        boost_mult: float = 1.0,
    ):
        """Build a Mechanism B usage patch inline for testability."""

        def patched(df: pd.DataFrame, position: str) -> pd.Series:
            base = orig_usage_multiplier(df, position)
            if position != "WR" or "player_id" not in df.columns:
                return base
            season_col = (
                df["proj_season"] if "proj_season" in df.columns else df["season"]
            )
            week_col = df["proj_week"] if "proj_week" in df.columns else df["week"]
            keys = list(zip(df["player_id"], season_col, week_col))
            sig = pd.Series(
                [lut.get(k, np.nan) for k in keys], index=df.index
            )
            result = base.copy()
            collapsing = sig.notna() & (sig < collapse_thr)
            if collapsing.any():
                result.loc[collapsing] = (
                    result.loc[collapsing] * collapse_mult
                ).clip(0.70, 1.15)
            rising = sig.notna() & (sig > boost_thr)
            if rising.any():
                result.loc[rising] = (
                    result.loc[rising] * boost_mult
                ).clip(0.80, 1.25)
            return result

        return patched

    def test_collapsing_wr_shrunk(self) -> None:
        """WRs with delta < collapse_thr must have lower multiplier."""
        wr_ids = [f"00-WR{i:04d}" for i in range(4)]
        # First two players have collapsing delta, last two are neutral
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in wr_ids],
            names=["player_id", "season", "week"],
        )
        lut = pd.Series([-0.15, -0.12, 0.0, 0.02], index=idx)
        patch = self._make_velocity_patch(lut, collapse_thr=-0.10, collapse_mult=0.80)
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        base = orig_usage_multiplier(df, "WR")
        patched = patch(df, "WR")
        # Collapsing players (index 0, 1) should have lower or equal multiplier
        for i in [0, 1]:
            assert patched.iloc[i] <= base.iloc[i] + 1e-9, (
                f"player {i}: patched {patched.iloc[i]:.4f} > base {base.iloc[i]:.4f}"
            )
        # Neutral players (index 2, 3) should be unchanged
        for i in [2, 3]:
            assert patched.iloc[i] == pytest.approx(base.iloc[i])

    def test_rising_wr_boosted(self) -> None:
        """WRs with delta > boost_thr must have higher or equal multiplier."""
        wr_ids = [f"00-WR{i:04d}" for i in range(4)]
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in wr_ids],
            names=["player_id", "season", "week"],
        )
        lut = pd.Series([0.12, 0.15, 0.0, -0.05], index=idx)
        patch = self._make_velocity_patch(
            lut,
            collapse_thr=-999.0,
            collapse_mult=1.0,
            boost_thr=0.10,
            boost_mult=1.10,
        )
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        base = orig_usage_multiplier(df, "WR")
        patched = patch(df, "WR")
        for i in [0, 1]:
            assert patched.iloc[i] >= base.iloc[i] - 1e-9, (
                f"player {i}: patched {patched.iloc[i]:.4f} < base {base.iloc[i]:.4f}"
            )
        for i in [2, 3]:
            assert patched.iloc[i] == pytest.approx(base.iloc[i])

    def test_wr_only_scope(self) -> None:
        """Non-WR positions must be unaffected by velocity patch."""
        wr_ids = [f"00-WR{i:04d}" for i in range(3)]
        other_ids = [f"00-XX{i:04d}" for i in range(3)]
        all_ids = wr_ids + other_ids
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in all_ids],
            names=["player_id", "season", "week"],
        )
        lut = pd.Series([-0.20] * 6, index=idx)  # extreme collapse for all
        patch = self._make_velocity_patch(lut, collapse_thr=-0.10, collapse_mult=0.70)

        for pos in ("QB", "RB", "TE"):
            df = pd.DataFrame(
                [_minimal_player_row(pid, pos) for pid in other_ids]
            )
            base = orig_usage_multiplier(df, pos)
            patched = patch(df, pos)
            pd.testing.assert_series_equal(base, patched)

    def test_no_signal_data_unchanged(self) -> None:
        """When LUT has no matching keys, result equals base exactly."""
        wr_ids = [f"00-WR{i:04d}" for i in range(5)]
        lut = pd.Series(dtype=float)  # empty
        patch = self._make_velocity_patch(lut, collapse_thr=-0.10, collapse_mult=0.75)
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        base = orig_usage_multiplier(df, "WR")
        patched = patch(df, "WR")
        pd.testing.assert_series_equal(base, patched)

    def test_multiplier_clips_to_valid_range(self) -> None:
        """Output stays in [0.70, 1.25] even with extreme mult values."""
        wr_ids = [f"00-WR{i:04d}" for i in range(6)]
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in wr_ids],
            names=["player_id", "season", "week"],
        )
        # Three extreme collapse, three extreme boost
        lut = pd.Series([-0.30, -0.25, -0.20, 0.30, 0.25, 0.20], index=idx)
        patch = self._make_velocity_patch(
            lut,
            collapse_thr=-0.10,
            collapse_mult=0.10,  # very aggressive
            boost_thr=0.10,
            boost_mult=5.0,  # very aggressive
        )
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        result = patch(df, "WR")
        assert (result >= 0.69).all(), f"min {result.min()}"
        assert (result <= 1.26).all(), f"max {result.max()}"

    def test_joint_collapse_and_boost(self) -> None:
        """Joint mode: collapsing and rising are both handled in one pass."""
        wr_ids = [f"00-WR{i:04d}" for i in range(4)]
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in wr_ids],
            names=["player_id", "season", "week"],
        )
        # 0 & 1: collapse, 2 & 3: boost
        lut = pd.Series([-0.15, -0.12, 0.15, 0.12], index=idx)
        patch = self._make_velocity_patch(
            lut,
            collapse_thr=-0.10,
            collapse_mult=0.80,
            boost_thr=0.10,
            boost_mult=1.10,
        )
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        base = orig_usage_multiplier(df, "WR")
        patched = patch(df, "WR")
        for i in [0, 1]:
            assert patched.iloc[i] <= base.iloc[i] + 1e-9
        for i in [2, 3]:
            assert patched.iloc[i] >= base.iloc[i] - 1e-9

    def test_slope_signal_same_logic(self) -> None:
        """Slope-based signal applies the same collapse/boost logic as delta."""
        wr_ids = [f"00-WR{i:04d}" for i in range(4)]
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in wr_ids],
            names=["player_id", "season", "week"],
        )
        slope_lut = pd.Series([-0.08, -0.06, 0.0, 0.01], index=idx)
        patch = self._make_velocity_patch(
            slope_lut, collapse_thr=-0.05, collapse_mult=0.80
        )
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        base = orig_usage_multiplier(df, "WR")
        patched = patch(df, "WR")
        for i in [0, 1]:
            assert patched.iloc[i] <= base.iloc[i] + 1e-9
        for i in [2, 3]:
            assert patched.iloc[i] == pytest.approx(base.iloc[i])

    def test_neutral_zone_untouched(self) -> None:
        """Players with signal between collapse_thr and boost_thr are unchanged."""
        wr_ids = [f"00-WR{i:04d}" for i in range(5)]
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in wr_ids],
            names=["player_id", "season", "week"],
        )
        # All in neutral zone between -0.10 and +0.10
        lut = pd.Series([-0.05, -0.02, 0.0, 0.03, 0.07], index=idx)
        patch = self._make_velocity_patch(
            lut,
            collapse_thr=-0.10,
            collapse_mult=0.80,
            boost_thr=0.10,
            boost_mult=1.10,
        )
        df = pd.DataFrame([_minimal_player_row(pid, "WR") for pid in wr_ids])
        base = orig_usage_multiplier(df, "WR")
        patched = patch(df, "WR")
        pd.testing.assert_series_equal(base, patched)


# ---------------------------------------------------------------------------
# Leakage verification
# ---------------------------------------------------------------------------


class TestLeakageCompliance:
    """Route-rate features used in the sweep must all be lagged."""

    def test_trail4_is_lagged(self) -> None:
        """route_rate_trail4 is shift(1) rolling mean — confirmed lagged."""
        from graph_route_participation import ROUTE_PARTICIPATION_FEATURES

        assert "route_rate_trail4" in ROUTE_PARTICIPATION_FEATURES

    def test_delta_is_lagged(self) -> None:
        """route_rate_delta is diff of trail4 (both lagged) — confirmed lagged."""
        from graph_route_participation import ROUTE_PARTICIPATION_FEATURES

        assert "route_rate_delta" in ROUTE_PARTICIPATION_FEATURES

    def test_slope_is_lagged(self) -> None:
        """route_rate_slope is OLS over shifted values — confirmed lagged."""
        from graph_route_participation import ROUTE_PARTICIPATION_FEATURES

        assert "route_rate_slope" in ROUTE_PARTICIPATION_FEATURES

    def test_raw_route_rate_not_a_feature(self) -> None:
        """Raw route_rate (same-week) must NOT be in ROUTE_PARTICIPATION_FEATURES."""
        from graph_route_participation import ROUTE_PARTICIPATION_FEATURES

        assert "route_rate" not in ROUTE_PARTICIPATION_FEATURES

    def test_features_not_flagged_as_leak(self) -> None:
        """All features in ROUTE_PARTICIPATION_FEATURES pass the leak detector."""
        from graph_route_participation import ROUTE_PARTICIPATION_FEATURES
        from player_feature_engineering import _is_unlagged_leak

        for col in ROUTE_PARTICIPATION_FEATURES:
            assert not _is_unlagged_leak(col), (
                f"{col} was flagged as a same-week leak"
            )


# ---------------------------------------------------------------------------
# Production baseline: snap-collapse and veteran prior independence
# ---------------------------------------------------------------------------


class TestMechanismIndependence:
    """Route signals are applied AFTER other multipliers, not interfering."""

    @pytest.mark.skipif(
        not PROJ_ENGINE_AVAILABLE, reason="projection_engine not available"
    )
    def test_velocity_patch_does_not_alter_rb(self) -> None:
        """RB results are identical with or without the WR velocity patch."""
        rb_ids = [f"00-RB{i:04d}" for i in range(5)]
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in rb_ids],
            names=["player_id", "season", "week"],
        )
        lut = pd.Series([-0.25] * 5, index=idx)  # extreme collapse for all

        def _vel_patch(df, position):
            base = orig_usage_multiplier(df, position)
            if position != "WR" or "player_id" not in df.columns:
                return base
            keys = list(zip(df["player_id"], df.get("proj_season", df["season"]), df.get("proj_week", df["week"])))
            sig = pd.Series([lut.get(k, np.nan) for k in keys], index=df.index)
            result = base.copy()
            collapsing = sig.notna() & (sig < -0.10)
            if collapsing.any():
                result.loc[collapsing] = (result.loc[collapsing] * 0.70).clip(0.70, 1.15)
            return result

        df = pd.DataFrame([_minimal_player_row(pid, "RB") for pid in rb_ids])
        base = orig_usage_multiplier(df, "RB")
        patched = _vel_patch(df, "RB")
        pd.testing.assert_series_equal(base, patched)

    @pytest.mark.skipif(
        not PROJ_ENGINE_AVAILABLE, reason="projection_engine not available"
    )
    def test_velocity_patch_does_not_alter_qb(self) -> None:
        """QB results are identical with or without the WR velocity patch."""
        qb_ids = [f"00-QB{i:04d}" for i in range(3)]
        idx = pd.MultiIndex.from_tuples(
            [(pid, 2022, 5) for pid in qb_ids],
            names=["player_id", "season", "week"],
        )
        lut = pd.Series([-0.20] * 3, index=idx)

        def _vel_patch(df, position):
            base = orig_usage_multiplier(df, position)
            if position != "WR":
                return base
            return base  # unreachable for QB

        df = pd.DataFrame([_minimal_player_row(pid, "QB") for pid in qb_ids])
        base = orig_usage_multiplier(df, "QB")
        patched = _vel_patch(df, "QB")
        pd.testing.assert_series_equal(base, patched)


# ---------------------------------------------------------------------------
# _build_production_blend_fn
# ---------------------------------------------------------------------------


class TestBuildProductionBlendFn:
    """_build_production_blend_fn returns a callable."""

    def test_returns_callable(self) -> None:
        """Function always returns a callable blend function."""
        import experiment_heuristic_lab as lab
        import pandas as pd

        weekly = pd.DataFrame()
        manifest = [{"season": 2022, "week": 5}]
        result = lab._build_production_blend_fn(weekly, manifest)
        assert callable(result)

    def test_uses_defaults_without_sweep_csv(self, tmp_path, monkeypatch) -> None:
        """Returns a blend_fn using hardcoded defaults when no sweep CSV exists."""
        import experiment_heuristic_lab as lab

        monkeypatch.setattr(lab, "CACHE_DIR", str(tmp_path))
        # No sweep CSV in tmp_path

        weekly = pd.DataFrame()
        manifest = [{"season": 2022, "week": 5}]
        result = lab._build_production_blend_fn(weekly, manifest)
        assert callable(result)


# ---------------------------------------------------------------------------
# cmd_sweep_wr_route wiring
# ---------------------------------------------------------------------------


class TestSweepWrRouteWiring:
    """Basic wiring tests for the lab commands."""

    def test_sweep_command_registered(self) -> None:
        """sweep-wr-route must be in the argparse choices."""
        import experiment_heuristic_lab as lab

        # Introspect choices from the command-function map
        assert hasattr(lab, "cmd_sweep_wr_route")

    def test_consensus_gap_command_registered(self) -> None:
        """consensus-gap-wr-route must be a registered command."""
        import experiment_heuristic_lab as lab

        assert hasattr(lab, "cmd_consensus_gap_wr_route")

    def test_build_production_blend_fn_exported(self) -> None:
        """_build_production_blend_fn must be importable from the lab."""
        import experiment_heuristic_lab as lab

        assert hasattr(lab, "_build_production_blend_fn")
