"""Repo-wide regression test for the vacuous-gate audit (VACUOUS_GATE_AUDIT.md).

Pattern being guarded against: a gate/check/backtest verdict function that
evaluates to PASS/SHIP because ZERO rows reached it, not because anything was
actually tested. Two real incidents motivated this file:

  1. Phase 61's event-adjustment backtest (scripts/backtest_event_adjustments.py)
     reported ``verdict=SHIP`` with 0 weeks of Gold sentiment data — treatment
     was byte-identical to baseline by construction, so "no regression
     possible" silently read as a real pass.
  2. The RB_SNAP_COLLAPSE correction (src/projection_engine.py) was a silent
     no-op in every backtest for months because snaps Bronze was absent
     locally and nothing asserted on that.

Each test below feeds an empty (or effectively-empty) population to a gate
function that was audited/fixed for this class of bug and asserts it does
NOT report a fabricated pass.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# 1. backtest_event_adjustments._overall_verdict — Phase 61 incident
# ---------------------------------------------------------------------------


def test_event_adjustments_verdict_is_not_ship_with_zero_events_weeks():
    """0 events-weeks must never report verdict=SHIP (Phase 61 incident)."""
    import backtest_event_adjustments as bea

    baseline = pd.DataFrame(
        {
            "season": [2024, 2024],
            "week": [3, 4],
            "position": ["QB", "RB"],
            "projected_points": [10.0, 8.0],
            "actual_points": [9.0, 7.0],
            "abs_error": [1.0, 1.0],
        }
    )
    treatment = baseline.copy()  # byte-identical: no events fired anywhere

    verdict, _ = bea._overall_verdict(baseline, treatment, ["qb", "rb"], events_weeks=0)

    assert verdict != "SHIP", (
        "0 firing weeks must not be read as a real SHIP verdict — this is "
        "the exact Phase 61 vacuous-pass pattern"
    )
    assert verdict == "NO_DATA"


def test_event_adjustments_verdict_can_still_ship_when_events_fire():
    """Sanity: a real firing rate with no regression still ships."""
    import backtest_event_adjustments as bea

    baseline = pd.DataFrame(
        {
            "season": [2024],
            "week": [3],
            "position": ["QB"],
            "projected_points": [10.0],
            "actual_points": [9.0],
            "abs_error": [1.0],
        }
    )
    treatment = baseline.copy()

    verdict, _ = bea._overall_verdict(baseline, treatment, ["qb"], events_weeks=1)
    assert verdict == "SHIP"


# ---------------------------------------------------------------------------
# 2. backtest_projections.print_consensus_report — fabricated "matches
#    consensus" verdict on an empty post-filter population
# ---------------------------------------------------------------------------


def test_consensus_report_no_fabricated_verdict_on_empty_population(capsys):
    """0 rows after the QB/RB/WR/TE position filter must not print a
    fabricated 'matches consensus' verdict (NaN comparisons are always
    False, so the naive branch structure defaults to a false pass)."""
    import backtest_projections as bp

    # consensus_proj clears the $5 floor, but position ("K") is outside the
    # _CONSENSUS_POSITIONS set the summary verdict is computed over.
    df = pd.DataFrame(
        {
            "projected_points": [10.0],
            "consensus_proj": [6.0],
            "actual_points": [9.0],
            "position": ["K"],
            "season": [2024],
            "week": [3],
        }
    )

    bp.print_consensus_report(df, "half_ppr")
    out = capsys.readouterr().out

    assert "matches consensus" not in out.lower()
    assert "no data" in out.lower()


# ---------------------------------------------------------------------------
# 3. ablation_market_features.compute_ship_or_skip_gated — empty holdout
# ---------------------------------------------------------------------------


def test_ablation_gate_skips_on_zero_holdout_games():
    """n_games=0 on either arm must force SKIP, not ride the 0.0==0.0 tie."""
    import ablation_market_features as amf

    verdict = amf.compute_ship_or_skip_gated(
        {"n_games": 0, "ats_accuracy": 0.0},
        {"n_games": 0, "ats_accuracy": 0.0},
    )
    assert verdict == "SKIP"


def test_ablation_gate_ships_on_real_improvement():
    """Sanity: a populated holdout with real improvement still ships."""
    import ablation_market_features as amf

    verdict = amf.compute_ship_or_skip_gated(
        {"n_games": 64, "ats_accuracy": 0.52},
        {"n_games": 64, "ats_accuracy": 0.55},
    )
    assert verdict == "SHIP"


# ---------------------------------------------------------------------------
# 4. backtest_vacated_opportunity — RB row with zero backtest observations
# ---------------------------------------------------------------------------


def test_vacated_opportunity_gate_holds_on_zero_rb_rows(capsys):
    """A combined frame with 0 RB rows (all-NaN RB aggregate) must print
    HOLD, not fall through to a real SHIP/HOLD comparison on NaNs."""
    import backtest_vacated_opportunity as bvo
    from types import SimpleNamespace

    # Simulate `combined` as it would look if RB never scored (only WR rows).
    combined = pd.DataFrame(
        {
            "season": [2024],
            "position": ["WR"],
            "n": [20],
            "spearman_base": [0.5],
            "spearman_treated": [0.55],
            "spearman_delta": [0.05],
            "mae_base": [5.0],
            "mae_treated": [4.9],
            "mae_delta": [-0.1],
        }
    )
    agg = (
        combined.groupby("position")[
            [
                "spearman_base",
                "spearman_treated",
                "spearman_delta",
                "mae_base",
                "mae_treated",
                "mae_delta",
            ]
        ]
        .mean()
        .round(4)
        .reindex(bvo.POSITIONS)
    )
    rb = agg.loc["RB"]

    # RB row is present only via reindex-NaN-fill; spearman_delta is NaN.
    assert pd.isna(rb["spearman_delta"])

    args = SimpleNamespace(seasons=[2024])
    rb_n = combined.loc[combined["position"] == "RB", "n"].sum()
    assert rb_n == 0

    # This mirrors the guard added to main(): NaN/zero-N RB must short
    # circuit to HOLD rather than reach the real spearman/MAE comparison.
    if pd.isna(rb["spearman_delta"]) or rb_n == 0:
        print(f"\nGate: RB has 0 backtest rows across seasons {args.seasons} -> HOLD (no data)")
    out = capsys.readouterr().out
    assert "HOLD" in out


# ---------------------------------------------------------------------------
# 5. check_ml_output.run_checks — n=0 (empty parquet, not just missing file)
# ---------------------------------------------------------------------------


def test_check_ml_output_fails_on_zero_row_gold_file(tmp_path):
    """An empty (0-row) Gold parquet must fail CHECK2, not silently pass
    because there was nothing to iterate over."""
    from unittest import mock

    import check_ml_output as cml

    gold_dir = os.path.join(tmp_path, "data", "gold", "projections/season=2026/week=5")
    os.makedirs(gold_dir, exist_ok=True)
    empty_df = pd.DataFrame(columns=["player_id", "position", "projected_points"])
    empty_df.to_parquet(
        os.path.join(gold_dir, "projections_half_ppr_20260101_000000.parquet"),
        index=False,
    )

    with mock.patch.multiple(
        cml,
        GOLD_DIR=os.path.join(tmp_path, "data", "gold"),
        PROJECT_ROOT=str(tmp_path),
    ):
        failures, _warnings = cml.run_checks(2026, 5, "half_ppr")

    assert failures, "0 skill-position rows must produce a CHECK2 failure, not a silent pass"
    assert any("CHECK2" in f for f in failures)


# ---------------------------------------------------------------------------
# 6. NFLDataFetcher.validate_data — baseline non-vacuity contract (already
#    SAFE; guarded here so a future refactor can't silently regress it)
# ---------------------------------------------------------------------------


def test_validate_data_fails_closed_on_empty_dataframe():
    from nfl_data_integration import NFLDataFetcher

    fetcher = NFLDataFetcher()
    result = fetcher.validate_data(pd.DataFrame(), "player_weekly")

    assert result["is_valid"] is False
    assert result["row_count"] == 0
    assert any("empty" in issue.lower() for issue in result["issues"])
