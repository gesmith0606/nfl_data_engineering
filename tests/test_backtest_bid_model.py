"""Unit tests for scripts/backtest_bid_model.py.

The model's accuracy was a number in a commit message until this script
existed. Making it reproducible is what lets the floor be swept on evidence
(the no-rival floor moved from a third of the room median to a fifth after
measuring wasted FAAB) rather than argued about.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "backtest_bid_model",
    Path(__file__).resolve().parent.parent / "scripts" / "backtest_bid_model.py",
)
backtest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(backtest)

score = backtest.score
winning_adds = backtest.winning_adds


def _tx(leg, bid, adds=None):
    return {"_leg": leg, "settings": {"waiver_bid": bid}, "adds": adds or {}}


def test_only_paid_waiver_adds_count():
    rows = [
        _tx(3, 40, {"111": 1}),
        _tx(4, 0, {"222": 2}),
        _tx(5, None, {"333": 3}),
        _tx(6, 12, {}),
    ]
    assert winning_adds(rows) == [(3, "111", 40)]


def test_a_multi_player_claim_yields_one_row_each():
    rows = [_tx(2, 25, {"111": 1, "222": 1})]
    got = sorted(winning_adds(rows))
    assert got == [(2, "111", 25), (2, "222", 25)]


def test_score_reports_median_mean_and_hit_rate():
    s = score([0, 1, 2, 30])
    assert s["n"] == 4
    assert s["median"] == 1.5
    assert s["mean"] == 8.25
    assert s["within_5"] == 75.0


def test_score_of_nothing_is_zeroed_not_an_error():
    assert score([])["n"] == 0


def test_within_5_counts_the_boundary():
    assert score([5, 6])["within_5"] == 50.0


# --- drift detection ---------------------------------------------------------


def test_run_signature_accepts_a_median_error_bound():
    """The bound is what turns a one-off measurement into a standing check."""
    import inspect

    params = inspect.signature(backtest.run).parameters
    assert "max_median_error" in params
    assert params["max_median_error"].default == 0


def test_cli_exposes_the_bound():
    import inspect

    src = inspect.getsource(backtest.main)
    assert "--max-median-error" in src


# --- the decision view -------------------------------------------------------


def test_the_decision_view_is_reported_before_the_verdict():
    """Absolute error conflates misjudging a player with refusing to overpay."""
    import inspect

    src = inspect.getsource(backtest.run)
    assert "decision view" in src
    assert "overpaid" in src and "lost_prices" in src
    assert src.index("decision view") < src.index("model_median =")


def test_a_win_is_counted_by_overpay_and_a_loss_by_its_price():
    import inspect

    src = inspect.getsource(backtest.run)
    assert "if suggested >= won:" in src
    assert "overpaid.append(suggested - won)" in src
    assert "lost_prices.append(won)" in src


def test_the_docstring_tells_you_to_read_the_decision_view_first():
    assert "Read the DECISION view first" in backtest.__doc__
