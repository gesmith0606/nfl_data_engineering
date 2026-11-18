"""PR 2: the board says what happened (labels by outcome) and a serve-time
feature-coverage guard skips a residual fed a mostly-empty feature matrix."""

import json
import os
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import residual_coverage as rc  # noqa: E402
from hybrid_projection import (  # noqa: E402
    RESIDUAL_APPLIED_COL,
    RESIDUAL_SKIP_REASON_COL,
    apply_residual_correction,
    label_projection_source,
)

FEATS = ["f1", "f2", "f3", "f4"]


def _model_dir(tmp_path, position="WR", constant_pred=2.0, extra_meta=None):
    import joblib
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline

    X = pd.DataFrame({f: [0.0, 0.0] for f in FEATS})
    pipe = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", Ridge(alpha=1.0))])
    pipe.fit(X, pd.Series([constant_pred, constant_pred]))
    d = tmp_path / "residual"
    d.mkdir()
    joblib.dump(pipe, d / f"{position.lower()}_residual.joblib")
    meta = {"position": position, "model_type": "ridge", "features": FEATS, "graph_features_added": 0}
    meta.update(extra_meta or {})
    (d / f"{position.lower()}_residual_meta.json").write_text(json.dumps(meta))
    return str(d)


def _heur(n=2):
    return pd.DataFrame(
        {"player_id": [f"p{i}" for i in range(n)], "position": "WR", "projected_points": [10.0 + i for i in range(n)]}
    )


def _feats(rows):
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- labels by outcome
def test_label_projection_source_follows_the_applied_flag():
    df = pd.DataFrame({RESIDUAL_APPLIED_COL: [True, False, True]})
    assert list(label_projection_source(df)) == ["hybrid", "heuristic", "hybrid"]


def test_label_without_the_flag_is_never_hybrid():
    assert list(label_projection_source(pd.DataFrame({"projected_points": [1.0, 2.0]}))) == ["heuristic", "heuristic"]


def test_stamp_is_per_row_not_per_position(tmp_path):
    d = _model_dir(tmp_path)
    feats = _feats([{"player_id": "p0", "f1": 1.0, "f2": 1.0, "f3": 1.0, "f4": 1.0}, {"player_id": "p1"}])
    out = apply_residual_correction(_heur(), feats, "WR", model_dir=d)
    by = out.set_index("player_id")
    assert bool(by.loc["p0", RESIDUAL_APPLIED_COL]) is True and by.loc["p0", RESIDUAL_SKIP_REASON_COL] == ""
    assert bool(by.loc["p1", RESIDUAL_APPLIED_COL]) is False and by.loc["p1", RESIDUAL_SKIP_REASON_COL] == "no_features"
    assert by.loc["p0", "projected_points"] == pytest.approx(12.0, abs=0.05)
    assert by.loc["p1", "projected_points"] == 11.0  # untouched


def test_no_model_is_labelled_with_a_reason(tmp_path):
    out = apply_residual_correction(_heur(), _feats([{"player_id": "p0", "f1": 1.0}]), "WR", model_dir=str(tmp_path / "nope"))
    assert not out[RESIDUAL_APPLIED_COL].any()
    assert (out[RESIDUAL_SKIP_REASON_COL] == "no_model").all()


# ---------------------------------------------------------------- coverage guard
def _sparse_feats():
    # 1 of 4 features populated => serve share 0.25
    return _feats([{"player_id": "p0", "f1": 1.0}, {"player_id": "p1", "f1": 2.0}])


def test_guard_skips_a_mostly_empty_matrix_and_warns(tmp_path, capsys):
    d = _model_dir(tmp_path, extra_meta={"train_feature_nonnan_share": 0.9})
    out = apply_residual_correction(_heur(), _sparse_feats(), "WR", model_dir=d, coverage_min_ratio=0.7)
    assert not out[RESIDUAL_APPLIED_COL].any()
    assert (out[RESIDUAL_SKIP_REASON_COL] == "coverage_guard").all()
    assert list(out["projected_points"]) == [10.0, 11.0]  # heuristic untouched
    printed = capsys.readouterr().out
    # a real workflow command: must START the line (a logging prefix would defeat it)
    assert any(line.startswith("::warning::WR residual SKIPPED") for line in printed.splitlines())


def test_guard_lets_a_healthy_matrix_through(tmp_path, capsys):
    d = _model_dir(tmp_path, extra_meta={"train_feature_nonnan_share": 0.9})
    full = _feats([{"player_id": "p0", "f1": 1, "f2": 1, "f3": 1, "f4": 1}, {"player_id": "p1", "f1": 1, "f2": 1, "f3": 1, "f4": 1}])
    out = apply_residual_correction(_heur(), full, "WR", model_dir=d, coverage_min_ratio=0.7)
    assert out[RESIDUAL_APPLIED_COL].all()
    assert "::warning::" not in capsys.readouterr().out


def test_guard_is_off_unless_asked_for(tmp_path):
    """Library default must not change backtests: no ratio passed -> residual runs."""
    d = _model_dir(tmp_path, extra_meta={"train_feature_nonnan_share": 0.9})
    out = apply_residual_correction(_heur(), _sparse_feats(), "WR", model_dir=d)
    assert out[RESIDUAL_APPLIED_COL].all()


def test_guard_does_not_block_when_no_training_share_is_known(tmp_path):
    d = _model_dir(tmp_path)  # no share in meta
    with patch.object(rc, "load_reference", return_value={}):
        out = apply_residual_correction(_heur(), _sparse_feats(), "WR", model_dir=d, coverage_min_ratio=0.7)
    assert out[RESIDUAL_APPLIED_COL].all()


# ---------------------------------------------------------------- residual_coverage helpers
def test_training_share_prefers_meta_over_sidecar():
    ref = {"WR": {"nonnan_share": 0.8}}
    assert rc.training_share("WR", {"train_feature_nonnan_share": 0.9}, ref) == 0.9
    assert rc.training_share("WR", {}, ref) == 0.8
    assert rc.training_share("QB", {}, ref) is None


def test_check_coverage_ratio_and_message():
    X = pd.DataFrame({"a": [1.0, np.nan], "b": [np.nan, np.nan]})  # 0.25
    v = rc.check_coverage("QB", X, {"train_feature_nonnan_share": 0.86}, 0.7)
    assert v["ok"] is False and v["ratio"] == pytest.approx(0.25 / 0.86)
    assert "QB" in rc.warning_line("QB", v) and rc.warning_line("QB", v).startswith("::warning::")
    assert rc.check_coverage("QB", X, {"train_feature_nonnan_share": 0.86}, 0.0)["ok"] is True


def test_committed_reference_covers_all_four_positions():
    ref = rc.load_reference()
    assert set(ref) >= {"QB", "RB", "WR", "TE"}
    assert all(0.3 < ref[p]["nonnan_share"] <= 1.0 for p in ("QB", "RB", "WR", "TE"))


# ---------------------------------------------------------------- router stamps by outcome
@patch("ml_projection_router.generate_weekly_projections")
@patch("ml_projection_router._load_ship_gate")
def test_router_labels_hybrid_rows_by_outcome(mock_gate, mock_heur):
    import ml_projection_router as router

    mock_gate.return_value = {"WR": "HYBRID", "QB": "SKIP", "RB": "SKIP", "TE": "SKIP"}
    heur = pd.DataFrame(
        {
            "player_id": ["w1", "w2", "q1"],
            "player_name": ["A", "B", "C"],
            "position": ["WR", "WR", "QB"],
            "recent_team": ["X", "Y", "Z"],
            "projected_points": [10.0, 9.0, 18.0],
            "projected_floor": [5.0, 4.0, 9.0],
            "projected_ceiling": [15.0, 14.0, 27.0],
            "position_rank": [1, 2, 1],
        }
    )
    mock_heur.return_value = heur
    silver = pd.DataFrame(
        [{"player_id": p, "season": 2026, "week": 5, "position": "WR", "f1": 1.0} for p in ("w1", "w2")]
    )

    def fake_apply(df, feats, position, model_dir=None, **kw):
        out = df.copy()
        out[RESIDUAL_APPLIED_COL] = [True, False]  # w1 corrected, w2 not
        out[RESIDUAL_SKIP_REASON_COL] = ["", "no_features"]
        return out

    with patch("hybrid_projection.apply_residual_correction", side_effect=fake_apply):
        out = router.generate_ml_projections(silver, pd.DataFrame(), season=2026, week=5, model_dir="models/player")
    src = out.set_index("player_id")["projection_source"]
    assert src["w1"] == "hybrid" and src["w2"] == "heuristic" and src["q1"] == "heuristic"


@patch("ml_projection_router.generate_weekly_projections")
@patch("ml_projection_router._load_ship_gate")
def test_router_with_no_feature_rows_is_all_heuristic(mock_gate, mock_heur):
    import ml_projection_router as router

    mock_gate.return_value = {"WR": "HYBRID"}
    mock_heur.return_value = pd.DataFrame(
        {
            "player_id": ["w1"],
            "player_name": ["A"],
            "position": ["WR"],
            "recent_team": ["X"],
            "projected_points": [10.0],
            "projected_floor": [5.0],
            "projected_ceiling": [15.0],
            "position_rank": [1],
        }
    )
    silver = pd.DataFrame(columns=["player_id", "season", "week", "position"])
    out = router.generate_ml_projections(silver, pd.DataFrame(), season=2026, week=5, model_dir="models/player")
    w = out[out.position == "WR"]
    assert (w["projection_source"] == "heuristic").all()
    assert not w[RESIDUAL_APPLIED_COL].astype(bool).any()
    assert (w[RESIDUAL_SKIP_REASON_COL] == "no_feature_rows").all()


# ---------------------------------------------------------------- pbp_advanced built on demand
def test_pbp_advanced_is_built_in_memory_when_the_silver_file_is_missing(tmp_path, monkeypatch):
    """build_pbp_advanced_silver has no caller, so 2026's Silver partition never exists;
    the join must fall back to computing it from Bronze PBP instead of leaving the
    columns NaN (RB `deep_target_share_roll4` was 0% populated live)."""
    import pbp_advanced_features as paf
    import player_feature_engineering as pfe

    monkeypatch.setattr(pfe, "SILVER_DIR", str(tmp_path))  # no pbp_advanced partition on disk
    calls = {}

    def fake_compute(season, bronze_dir=None):
        calls["season"] = season
        return pd.DataFrame(
            {"player_id": ["rb1"], "season": [2026], "week": [4], "position_type": ["receiver"], "raw": [1.0]}
        )

    def fake_trailing(raw):
        out = raw.copy()
        out["deep_target_share_roll4"] = 0.25
        return out

    monkeypatch.setattr(paf, "compute_pbp_advanced_player_week", fake_compute)
    monkeypatch.setattr(paf, "add_pbp_advanced_trailing_features", fake_trailing)
    df = pd.DataFrame({"player_id": ["rb1", "rb2"], "season": 2026, "week": 4, "position": "RB"})
    out = pfe._join_pbp_advanced_features(df, 2026)
    assert calls["season"] == 2026
    by = out.set_index("player_id")
    assert by.loc["rb1", "deep_target_share_roll4"] == 0.25
    assert np.isnan(by.loc["rb2", "deep_target_share_roll4"])


def test_pbp_advanced_in_memory_build_fails_open(tmp_path, monkeypatch):
    import pbp_advanced_features as paf
    import player_feature_engineering as pfe

    monkeypatch.setattr(pfe, "SILVER_DIR", str(tmp_path))
    monkeypatch.setattr(paf, "compute_pbp_advanced_player_week", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no pbp")))
    df = pd.DataFrame({"player_id": ["rb1"], "season": 2026, "week": 4, "position": "RB"})
    out = pfe._join_pbp_advanced_features(df, 2026)
    assert "deep_target_share_roll4" in out.columns and out["deep_target_share_roll4"].isna().all()


@pytest.mark.parametrize(
    "script,flag",
    [("generate_projections.py", "--no-coverage-guard"), ("backtest_projections.py", "--residual-coverage-ratio")],
)
def test_cli_help_renders_and_lists_the_guard_flag(script, flag):
    """argparse help strings are %-formatted: a bare '48%' in one crashes --help."""
    import subprocess

    out = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "..", "scripts", script), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-400:]
    assert flag in out.stdout
