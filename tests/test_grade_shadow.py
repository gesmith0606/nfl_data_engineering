"""Tests for the early-season-prior SHADOW run plumbing.

1. ``scripts/grade_shadow.py`` — matched-population join, per-source
   MAE/bias/Spearman, promotion verdict, and fail-open multi-week grading.
2. ``scripts/generate_projections.py --shadow-tag`` — the shadow board key
   never lands under ``projections/`` (the prod serving path), and bad
   usage is rejected at argparse time.

Synthetic in-memory / tmp-dir data only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "src", _ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import grade_shadow as gs  # noqa: E402
import generate_projections as gp  # noqa: E402

POSITIONS = ["QB", "RB", "WR", "TE"]


def _boards(n_per_pos: int = 12, shadow_shift: float = 0.0, seed: int = 0):
    """prod / shadow / sleeper / actuals frames for one week."""
    rng = np.random.default_rng(seed)
    rows = []
    for pos in POSITIONS:
        for i in range(n_per_pos):
            rows.append(
                {
                    "player_id": f"00-{pos}{i:03d}",
                    "player_name": f"{pos} {i}",
                    "position": pos,
                    "actual": float(rng.uniform(0, 30)),
                }
            )
    base = pd.DataFrame(rows)
    prod = base[["player_id", "player_name", "position"]].copy()
    prod["projected_points"] = base["actual"] + 3.0  # MAE exactly 3
    shadow = prod.copy()
    shadow["projected_points"] = prod["projected_points"] + shadow_shift
    sleeper = base[["player_id"]].copy()
    sleeper["consensus_proj"] = base["actual"] - 2.0  # MAE exactly 2
    actuals = base[["player_id", "player_name", "position"]].copy()
    actuals["actual_points"] = base["actual"]
    return prod, shadow, sleeper, actuals


class TestBuildGradingFrame:
    def test_matched_population_and_columns(self):
        prod, shadow, sleeper, actuals = _boards()
        frame = gs.build_grading_frame(prod, shadow, sleeper, actuals, 2026, 3)
        assert {"production", "shadow", "sleeper", "actual", "week"} <= set(frame)
        assert (frame["week"] == 3).all()
        # relevance: max(source) >= 5 — actual+3 >= 5 drops actual < 2 rows only
        assert (frame[["production", "shadow", "sleeper"]].max(axis=1) >= 5).all()

    def test_sleeper_restricts_to_matched_rows(self):
        prod, shadow, sleeper, actuals = _boards()
        sleeper = sleeper.iloc[:10]
        frame = gs.build_grading_frame(prod, shadow, sleeper, actuals, 2026, 3)
        assert len(frame) <= 10
        assert frame["sleeper"].notna().all()

    def test_no_sleeper_keeps_rows_with_nan_sleeper(self):
        prod, shadow, _, actuals = _boards()
        frame = gs.build_grading_frame(prod, shadow, pd.DataFrame(), actuals, 2026, 3)
        assert not frame.empty
        assert frame["sleeper"].isna().all()

    def test_player_ids_normalised_and_deduped(self):
        prod, shadow, sleeper, actuals = _boards()
        prod = pd.concat([prod, prod.iloc[:3]], ignore_index=True)
        actuals["player_id"] = actuals["player_id"] + " "
        frame = gs.build_grading_frame(prod, shadow, sleeper, actuals, 2026, 3)
        assert frame["player_id"].is_unique
        assert not frame.empty

    @pytest.mark.parametrize("empty", ["prod", "shadow", "actuals"])
    def test_empty_required_input_returns_empty(self, empty):
        boards = dict(zip(["prod", "shadow", "sleeper", "actuals"], _boards()))
        boards[empty] = pd.DataFrame()
        frame = gs.build_grading_frame(
            boards["prod"],
            boards["shadow"],
            boards["sleeper"],
            boards["actuals"],
            2026,
            3,
        )
        assert frame.empty

    def test_non_skill_positions_dropped(self):
        prod, shadow, sleeper, actuals = _boards()
        prod.loc[0, "position"] = "K"
        frame = gs.build_grading_frame(prod, shadow, sleeper, actuals, 2026, 3)
        assert "K" not in set(frame["position"])


class TestGradeFrame:
    def test_mae_bias_and_delta(self):
        prod, shadow, sleeper, actuals = _boards(shadow_shift=-1.0)
        frame = gs.build_grading_frame(prod, shadow, sleeper, actuals, 2026, 3)
        rows = {r["position"]: r for r in gs.grade_frame(frame)}
        overall = rows["ALL"]
        assert overall["production_mae"] == pytest.approx(3.0)
        assert overall["production_bias"] == pytest.approx(3.0)
        assert overall["shadow_mae"] == pytest.approx(2.0)
        assert overall["sleeper_mae"] == pytest.approx(2.0)
        assert overall["sleeper_bias"] == pytest.approx(-2.0)
        assert overall["shadow_minus_prod_mae"] == pytest.approx(-1.0)
        assert set(rows) == set(POSITIONS) | {"ALL"}
        # projections are a monotone shift of actuals -> perfect rank order
        assert overall["production_spearman"] == pytest.approx(1.0)

    def test_sleeper_columns_absent_when_unavailable(self):
        prod, shadow, _, actuals = _boards()
        frame = gs.build_grading_frame(prod, shadow, pd.DataFrame(), actuals, 2026, 3)
        row = gs.grade_frame(frame)[0]
        assert "sleeper_mae" not in row
        assert "shadow_mae" in row

    def test_empty_frame(self):
        assert gs.grade_frame(pd.DataFrame()) == []


class TestPromotionVerdict:
    @staticmethod
    def _pooled(overall: float, per_pos: float = 0.0):
        rows = [{"position": p, "shadow_minus_prod_mae": per_pos} for p in POSITIONS]
        return rows + [{"position": "ALL", "shadow_minus_prod_mae": overall}]

    def test_ship_when_bar_cleared_all_weeks(self):
        v = gs.promotion_verdict(self._pooled(-0.12, -0.05), [3, 4, 5, 6])
        assert v["verdict"] == "SHIP"

    def test_hold_when_improvement_short_of_bar(self):
        v = gs.promotion_verdict(self._pooled(-0.05), [3, 4, 5, 6])
        assert v["verdict"] == "HOLD"
        assert not v["would_pass_on_current_data"]

    def test_hold_when_a_position_regresses(self):
        pooled = self._pooled(-0.20, -0.1)
        pooled[0]["shadow_minus_prod_mae"] = 0.06  # QB worse than tolerance
        v = gs.promotion_verdict(pooled, [3, 4, 5, 6])
        assert v["verdict"] == "HOLD"
        assert v["positions_worse_than_tolerance"] == ["QB"]

    def test_interim_until_all_weeks_graded(self):
        v = gs.promotion_verdict(self._pooled(-0.3), [3, 4])
        assert v["verdict"] == "INTERIM"
        assert v["would_pass_on_current_data"]
        assert v["weeks_still_missing"] == [5, 6]

    def test_no_data(self):
        assert gs.promotion_verdict([], [])["verdict"] == "NO DATA"


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


class TestGradeWeeksFailOpen:
    def test_grades_available_week_and_skips_missing(self, tmp_path):
        prod, shadow, sleeper, actuals = _boards(shadow_shift=-0.5)
        gold = tmp_path / "gold"
        for wk in (3, 4):
            _write(
                prod,
                gold
                / "projections"
                / "season=2026"
                / f"week={wk}"
                / "projections_half_ppr_20260922_000000.parquet",
            )
        # shadow only for week 3 -> week 4 must be skipped, not crash
        _write(
            shadow,
            gold
            / "projections_shadow"
            / "early_season_prior"
            / "season=2026"
            / "week=3"
            / "projections_half_ppr_20260922_000001.parquet",
        )
        weekly = actuals.rename(columns={"actual_points": "receiving_yards"})
        weekly["receiving_yards"] = weekly["receiving_yards"] * 10  # 0.1 pt/yd
        weekly["season"] = 2026
        weekly = pd.concat(
            [weekly.assign(week=3), weekly.assign(week=4)], ignore_index=True
        )
        _write(
            weekly,
            tmp_path
            / "bronze"
            / "players"
            / "weekly"
            / "season=2026"
            / "player_weekly_x.parquet",
        )
        slp = sleeper.merge(prod[["player_id", "player_name", "position"]])
        slp = slp.rename(columns={"consensus_proj": "projected_points"})
        slp["source"] = "sleeper"
        slp["scoring_format"] = "half_ppr"
        _write(
            slp,
            tmp_path
            / "silver"
            / "external_projections"
            / "season=2026"
            / "week=03"
            / "external_projections_x.parquet",
        )

        report = gs.grade_weeks(2026, [3, 4], data_root=str(tmp_path))
        assert report["weeks_graded"] == [3]
        assert report["missing_weeks"] == {4: "no shadow board"}
        overall = next(r for r in report["pooled"] if r["position"] == "ALL")
        assert overall["shadow_minus_prod_mae"] == pytest.approx(-0.5, abs=1e-6)
        assert "sleeper_mae" in overall
        assert report["promotion"]["verdict"] == "INTERIM"
        md = gs.render_markdown(report)
        assert "Promotion verdict: INTERIM" in md
        assert "week 4: no shadow board" in md

    def test_nothing_available(self, tmp_path):
        report = gs.grade_weeks(2026, [3], data_root=str(tmp_path))
        assert report["weeks_graded"] == []
        assert report["promotion"]["verdict"] == "NO DATA"
        assert "_no data_" in gs.render_markdown(report)


class TestShadowProjectionKey:
    def test_prod_key_unchanged(self):
        assert gp.weekly_projection_key(2026, 3, "half_ppr", "TS") == (
            "projections/season=2026/week=3/projections_half_ppr_TS.parquet"
        )

    def test_shadow_key_is_sibling_of_prod_path(self):
        key = gp.weekly_projection_key(
            2026, 3, "half_ppr", "TS", shadow_tag="early_season_prior"
        )
        assert key == (
            "projections_shadow/early_season_prior/season=2026/week=3/"
            "projections_half_ppr_TS.parquet"
        )
        assert not key.startswith("projections/")

    @pytest.mark.parametrize("tag", ["../prod", "Early", "a/b", "", "x y"])
    def test_unsafe_tag_rejected(self, tag):
        with pytest.raises(ValueError):
            gp.weekly_projection_key(2026, 3, "half_ppr", "TS", shadow_tag=tag)

    @pytest.mark.parametrize(
        "argv",
        [
            ["--preseason", "--shadow-tag", "early_season_prior"],
            ["--week", "3", "--shadow-tag", "../projections"],
        ],
    )
    def test_cli_rejects_bad_shadow_usage(self, monkeypatch, argv):
        monkeypatch.setattr(sys, "argv", ["generate_projections.py", *argv])
        with pytest.raises(SystemExit) as exc:
            gp.main()
        assert exc.value.code == 2
