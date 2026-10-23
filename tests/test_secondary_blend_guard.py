"""Guard tests for the secondary residual-model blend.

Diagnosis 2026-10-22 (``.planning/WR_SECONDARY_BLEND_2026_10_22.md``):
``apply_residual_correction`` returns the UNTOUCHED heuristic when it cannot
run (no artifact, or no matching features). The WR secondary-model blend fed
that return value straight into::

    final = (1 - w) * primary_corrected + w * secondary

so when the secondary could not run, ``w`` of every WR row silently reverted
to the *uncorrected* heuristic — and the logs announced a successful blend.
That is exactly what shipped: ``models/residual_wr_secondary/`` holds
``wr_residual.joblib`` but its meta JSON was never committed, and
``load_residual_model`` tolerates a missing meta (returns ``{}``), so
``features`` was ``[]``.

These tests pin the guard that distinguishes "the secondary corrected these
rows" from "the secondary fell back", which the return value alone cannot
express.
"""

import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from hybrid_projection import (  # noqa: E402
    GRAPH_FEATURE_SET,
    _secondary_blend_is_usable,
)

FEATURES = ["receiving_yards_std", "implied_team_total", "ngs_avg_separation_std"]


def _write_secondary(tmp_path, features=None, meta_extra=None, write_meta=True):
    """A minimal on-disk secondary model, optionally without its meta."""
    d = tmp_path / "residual_wr_secondary"
    d.mkdir(parents=True, exist_ok=True)
    feats = FEATURES if features is None else features
    pipe = Pipeline([("imputer", SimpleImputer()), ("model", Ridge())])
    x = pd.DataFrame(
        np.random.default_rng(0).normal(size=(40, len(feats))), columns=feats
    )
    pipe.fit(x, np.random.default_rng(1).normal(size=40))
    joblib.dump(pipe, d / "wr_residual.joblib")
    if write_meta:
        meta = {"model_type": "ridge", "features": feats}
        meta.update(meta_extra or {})
        with open(d / "wr_residual_meta.json", "w") as fh:
            json.dump(meta, fh)
    return str(d)


def _features_frame(cols=None):
    cols = FEATURES if cols is None else cols
    return pd.DataFrame({c: [1.0, 2.0, 3.0] for c in cols})


class TestTheShippedFailureIsCaught:
    def test_missing_meta_is_not_usable(self, tmp_path):
        """The exact shipped state: artifact present, meta never committed."""
        blend_dir = _write_secondary(tmp_path, write_meta=False)
        usable, reason = _secondary_blend_is_usable("WR", blend_dir, _features_frame())
        assert usable is False
        assert "metadata" in reason

    def test_meta_without_a_feature_list_is_not_usable(self, tmp_path):
        blend_dir = _write_secondary(tmp_path)
        with open(os.path.join(blend_dir, "wr_residual_meta.json"), "w") as fh:
            json.dump({"model_type": "ridge"}, fh)
        usable, reason = _secondary_blend_is_usable("WR", blend_dir, _features_frame())
        assert usable is False
        assert "feature list" in reason

    def test_absent_artifact_is_not_usable(self, tmp_path):
        usable, reason = _secondary_blend_is_usable(
            "WR", str(tmp_path / "nope"), _features_frame()
        )
        assert usable is False
        assert "no model artifact" in reason


class TestUsableSecondary:
    def test_complete_secondary_is_usable(self, tmp_path):
        blend_dir = _write_secondary(tmp_path)
        usable, reason = _secondary_blend_is_usable("WR", blend_dir, _features_frame())
        assert usable is True
        assert reason == ""

    def test_graph_features_count_as_satisfiable_when_the_meta_asks_for_them(
        self, tmp_path
    ):
        """The primary path enriches graph columns at inference; the guard must
        judge the secondary on the same terms or it would reject a model that
        would in fact run."""
        graph_feat = sorted(GRAPH_FEATURE_SET)[0]
        blend_dir = _write_secondary(
            tmp_path,
            features=[graph_feat],
            meta_extra={"graph_features_added": 5},
        )
        usable, reason = _secondary_blend_is_usable(
            "WR", blend_dir, _features_frame(["something_else"])
        )
        assert usable is True, reason

    def test_graph_features_do_not_count_when_the_meta_does_not_ask(self, tmp_path):
        graph_feat = sorted(GRAPH_FEATURE_SET)[0]
        blend_dir = _write_secondary(
            tmp_path,
            features=[graph_feat],
            meta_extra={"graph_features_added": 0},
        )
        usable, _reason = _secondary_blend_is_usable(
            "WR", blend_dir, _features_frame(["something_else"])
        )
        assert usable is False


class TestFeatureAvailability:
    def test_no_overlapping_features_is_not_usable(self, tmp_path):
        blend_dir = _write_secondary(tmp_path)
        usable, reason = _secondary_blend_is_usable(
            "WR", blend_dir, _features_frame(["totally", "different", "columns"])
        )
        assert usable is False
        assert "features are available" in reason

    def test_partial_overlap_is_usable(self, tmp_path):
        """The primary tolerates imputing absent features, so the secondary
        should too — one available feature is enough to run."""
        blend_dir = _write_secondary(tmp_path)
        usable, reason = _secondary_blend_is_usable(
            "WR", blend_dir, _features_frame([FEATURES[0], "unrelated"])
        )
        assert usable is True, reason

    def test_empty_or_missing_features_frame_is_not_usable(self, tmp_path):
        blend_dir = _write_secondary(tmp_path)
        for frame in (pd.DataFrame(), None):
            usable, reason = _secondary_blend_is_usable("WR", blend_dir, frame)
            assert usable is False
            assert "player features" in reason


class TestBlendSkipsRatherThanDilutes:
    """The behavioural contract: an unusable secondary must leave the primary
    correction intact, never average it with the raw heuristic."""

    def test_unusable_secondary_leaves_the_primary_correction_untouched(
        self, tmp_path, monkeypatch
    ):
        import hybrid_projection as hp

        heuristic = pd.DataFrame(
            {
                "player_id": ["A", "B", "C"],
                "position": ["WR"] * 3,
                "projected_points": [10.0, 12.0, 8.0],
            }
        )
        feats = _features_frame()
        feats["player_id"] = ["A", "B", "C"]
        feats["season"] = 2026
        feats["week"] = 5

        # Primary: a usable model whose meta points at an UNUSABLE secondary.
        primary_dir = _write_secondary(tmp_path / "primary")
        bad_secondary = _write_secondary(tmp_path / "secondary", write_meta=False)
        meta_path = os.path.join(primary_dir, "wr_residual_meta.json")
        with open(meta_path) as fh:
            meta = json.load(fh)
        meta.update({"blend_secondary_dir": bad_secondary, "blend_weight": 0.4})
        with open(meta_path, "w") as fh:
            json.dump(meta, fh)

        out = hp.apply_residual_correction(
            heuristic, feats, "WR", model_dir=primary_dir
        )

        # Re-run with the blend keys removed: the two must agree exactly,
        # proving the unusable secondary contributed nothing.
        meta.pop("blend_secondary_dir")
        meta.pop("blend_weight")
        with open(meta_path, "w") as fh:
            json.dump(meta, fh)
        expected = hp.apply_residual_correction(
            heuristic, feats, "WR", model_dir=primary_dir
        )

        pd.testing.assert_series_equal(
            out["projected_points"], expected["projected_points"]
        )

    def test_the_dilution_it_prevents_would_have_been_material(self):
        """Documents the arithmetic the guard exists to stop: at w=0.4 a
        40% revert toward the uncorrected heuristic."""
        primary_corrected = pd.Series([14.0, 9.0, 20.0])
        raw_heuristic = pd.Series([10.0, 12.0, 8.0])
        w = 0.4
        diluted = primary_corrected * (1 - w) + raw_heuristic * w
        assert not np.allclose(diluted, primary_corrected)
        assert np.allclose(diluted, [12.4, 10.2, 15.2])
