"""
Tests for the quantile floor/ceiling CLI wiring
(.planning/QUANTILE_REFIT_2026_08_15.md section 7 / .planning/PROPS_MULTIBOOK_2026_08_16.md).

The weekly CLI's floor/ceiling call site used to hand ``add_floor_ceiling()``
the trimmed weekly-output frame, which never carries the quantile model's
feature columns — the quantile path's ``has_features`` gate always failed,
so every call (with or without ``--conformal-bands``) silently used the
heuristic +/-mult fallback. ``attach_floor_ceiling_with_features()`` in
``scripts/generate_projections.py`` fixes this by assembling the real
feature vector and joining it in by ``player_id`` before calling
``add_floor_ceiling()``.

A second, real gap surfaces once features are wired through: some seasons'
Silver ``advanced`` join is missing columns the shipped imputer was fit on
(confirmed: 2024/2025 have zero ``qbr_*`` columns while 2022/2023 have 16).
``sklearn.SimpleImputer.transform()`` raises rather than gracefully
imputing when hit with a strict subset of its fit-time columns, so this
also verifies the any-missing-column-becomes-NaN backfill that prevents
that crash.
"""

import logging
import os
import sys

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from quantile_models import load_quantile_models  # noqa: E402

import generate_projections  # noqa: E402
from generate_projections import attach_floor_ceiling_with_features  # noqa: E402

QUANTILE_LOGGER = "projection_engine"
QUANTILE_FIRE_MSG = "Floor/ceiling set via quantile models"


def _proj_frame(n=6):
    positions = (["QB", "RB", "WR", "TE"] * n)[:n]
    return pd.DataFrame(
        {
            "player_id": [f"00-{1000 + i}" for i in range(n)],
            "position": positions,
            "projected_points": [10.0] * n,
        }
    )


def _full_feature_frame(proj, week=10):
    """Synthetic feature frame carrying every column the shipped imputer expects."""
    qdata = load_quantile_models()
    base = proj[["player_id", "position"]].copy()
    base["week"] = week
    # Deterministic, position-varying values so predictions aren't flat.
    # Built as one concat (not per-column assignment) to avoid fragmenting
    # the frame across 486 individual inserts.
    values = {
        col: [float((i + j) % 7) for j in range(len(base))]
        for i, col in enumerate(qdata["feature_cols"])
    }
    return pd.concat([base, pd.DataFrame(values, index=base.index)], axis=1)


class TestAttachFloorCeilingWiring:
    def test_quantile_path_fires_with_full_features(self, monkeypatch, caplog):
        proj = _proj_frame()
        feat = _full_feature_frame(proj)
        monkeypatch.setattr(
            "player_feature_engineering.assemble_player_features",
            lambda season: feat,
        )

        with caplog.at_level(logging.INFO, logger=QUANTILE_LOGGER):
            out = attach_floor_ceiling_with_features(
                proj, season=2025, week=10, use_conformal=True, log=lambda *_: None
            )

        assert QUANTILE_FIRE_MSG in caplog.text
        assert "projected_floor" in out.columns
        assert "projected_ceiling" in out.columns
        assert (out["projected_floor"] <= out["projected_points"]).all()
        assert (out["projected_ceiling"] >= out["projected_points"]).all()
        # Not the flat heuristic pattern (10*(1-mult) is identical within a
        # position) -- quantile predictions vary per player.
        qb_floors = out.loc[out["position"] == "QB", "projected_floor"]
        if len(qb_floors) > 1:
            assert qb_floors.nunique() > 1

    def test_missing_feature_columns_backfilled_not_crashed(self, monkeypatch, caplog):
        # Simulate the real 2024/2025 QBR gap: drop a chunk of the model's
        # feature_cols from the assembled frame entirely. The wiring must
        # still reach the quantile path (via NaN backfill + imputer medians)
        # rather than silently falling back to the heuristic multipliers.
        proj = _proj_frame()
        feat = _full_feature_frame(proj)
        qdata = load_quantile_models()
        drop_cols = [c for c in qdata["feature_cols"] if "qbr" in c.lower()]
        feat = feat.drop(columns=[c for c in drop_cols if c in feat.columns])

        monkeypatch.setattr(
            "player_feature_engineering.assemble_player_features",
            lambda season: feat,
        )

        with caplog.at_level(logging.INFO, logger=QUANTILE_LOGGER):
            out = attach_floor_ceiling_with_features(
                proj, season=2025, week=10, use_conformal=True, log=lambda *_: None
            )

        assert QUANTILE_FIRE_MSG in caplog.text
        assert (out["projected_floor"] <= out["projected_points"]).all()
        assert (out["projected_ceiling"] >= out["projected_points"]).all()

    def test_empty_feature_frame_falls_back_to_heuristic(self, monkeypatch):
        proj = _proj_frame()
        monkeypatch.setattr(
            "player_feature_engineering.assemble_player_features",
            lambda season: pd.DataFrame(),
        )
        warnings = []
        out = attach_floor_ceiling_with_features(
            proj, season=2025, week=10, use_conformal=False, log=warnings.append
        )
        assert any("fall back to heuristic" in w for w in warnings)
        # Heuristic QB multiplier is 0.45: 10 * (1-0.45) / 10 * (1+0.45)
        qb_row = out[out["position"] == "QB"].iloc[0]
        assert qb_row["projected_floor"] == pytest.approx(5.5, abs=0.01)
        assert qb_row["projected_ceiling"] == pytest.approx(14.5, abs=0.01)

    def test_feature_assembly_exception_falls_back_to_heuristic(self, monkeypatch):
        proj = _proj_frame()

        def _raise(season):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "player_feature_engineering.assemble_player_features", _raise
        )
        warnings = []
        out = attach_floor_ceiling_with_features(
            proj, season=2025, week=10, use_conformal=False, log=warnings.append
        )
        assert any("boom" in w for w in warnings)
        assert "projected_floor" in out.columns
        assert "projected_ceiling" in out.columns

    def test_output_schema_unchanged_besides_floor_ceiling(self, monkeypatch):
        proj = _proj_frame()
        feat = _full_feature_frame(proj)
        monkeypatch.setattr(
            "player_feature_engineering.assemble_player_features",
            lambda season: feat,
        )
        out = attach_floor_ceiling_with_features(
            proj, season=2025, week=10, use_conformal=True, log=lambda *_: None
        )
        expected_cols = set(proj.columns) | {"projected_floor", "projected_ceiling"}
        assert set(out.columns) == expected_cols
        assert len(out) == len(proj)


@pytest.mark.skipif(
    not os.path.exists(
        os.path.join(
            os.path.dirname(__file__), "..", "data", "silver", "players", "usage", "season=2025"
        )
    ),
    reason="Real Silver data not available locally",
)
class TestRealDataQuantileFire:
    """End-to-end smoke test against real local Silver + the shipped quantile
    artifacts, no mocking -- mirrors the methodology in
    .planning/QUANTILE_REFIT_2026_08_15.md section 7's own smoke test."""

    def test_real_2025_week10_fires_quantile_path(self, caplog):
        from player_feature_engineering import assemble_player_features

        feat = assemble_player_features(season=2025)
        week_feat = feat[feat["week"] == 10]
        assert not week_feat.empty
        sample = week_feat.drop_duplicates("player_id").head(20)
        proj = pd.DataFrame(
            {
                "player_id": sample["player_id"].values,
                "position": sample["position"].values,
                "projected_points": [10.0] * len(sample),
            }
        )

        with caplog.at_level(logging.INFO, logger=QUANTILE_LOGGER):
            out = attach_floor_ceiling_with_features(
                proj, season=2025, week=10, use_conformal=True, log=lambda *_: None
            )

        assert QUANTILE_FIRE_MSG in caplog.text
        assert (out["projected_floor"] <= out["projected_points"]).all()
        assert (out["projected_ceiling"] >= out["projected_points"]).all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
