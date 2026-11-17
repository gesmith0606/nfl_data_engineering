"""The clearing-price model against Mantis' own claims, pinned.

``data/waivers/scorecard/mantis_2026_clearing.json`` is written by
``python scripts/backtest_clearing_price.py --league mantis --out ...`` and
``data/waivers/clearing_fit/mantis_2026.json`` is the fit ``waiver_wire.py``
loads. The acceptance bar from the waiver plan: replaying George's eight winning
in-season bids, recommended spend at most $60 while still winning at least
seven of them.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from src import clearing_model as cm

REPO = Path(__file__).resolve().parent.parent
REPLAY = REPO / "data" / "waivers" / "scorecard" / "mantis_2026_clearing.json"
FIT = REPO / "data" / "waivers" / "clearing_fit" / "mantis_2026.json"

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", REPO / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)


@pytest.mark.skipif(not REPLAY.exists(), reason="replay not generated")
class TestReplayOfOurWins:
    @pytest.fixture(scope="class")
    def replay(self):
        return json.loads(REPLAY.read_text(encoding="utf-8"))

    def test_eight_wins_for_at_most_60_dollars_winning_at_least_seven(self, replay):
        w = replay["our_wins"]
        assert w["claims_won"] == 8 and w["paid"] == 475
        assert w["model_won"] >= 7
        assert w["model_spend"] <= 60

    def test_the_model_never_bids_above_what_the_claim_is_worth(self, replay):
        for c in replay["our_claims"]:
            assert c["model_bid"] <= max(1, c["ceiling"]), c

    def test_a_name_that_cleared_far_above_his_value_is_not_chased(self, replay):
        allen = next(c for c in replay["our_claims"] if c["name"] == "Braelon Allen")
        assert allen["clearing"] == 451 and allen["worth_chasing"] is False
        assert allen["model_bid"] <= 5  # a lottery ticket, not the $160 we filed

    def test_held_out_weeks_spend_is_a_fraction_of_the_old_rules(self, replay):
        p = replay["policies"]
        assert p["clearing model"]["spend"] < p["old model (no rivals)"]["spend"] / 2
        assert p["clearing model"]["spend"] < p["room median so far"]["spend"] / 10
        # and it does not pay for wins it could have had for the minimum
        assert p["clearing model"]["overpay"] < 0.25 * p["clearing model"]["spend"]


@pytest.mark.skipif(not FIT.exists(), reason="fit not generated")
def test_the_committed_fit_loads_and_prices_a_tier():
    model, note = waiver_wire.load_clearing_model("mantis", 2026, 1000)
    assert "fit on" in note and "NO LEAGUE FIT" not in note
    assert model.fit_through >= 9  # the report flags a fit that stops short of the week
    adv = model.recommend("RB-top", value=40, budget_left=800)
    assert 1 <= adv.bid <= 200 and 0 < adv.p_win <= 1


def test_a_league_without_a_fit_says_it_is_the_prior_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(waiver_wire, "CLEARING_FIT_DIR", tmp_path)
    model, note = waiver_wire.load_clearing_model("la_liga", 2026, 100)
    assert "NO LEAGUE FIT" in note and model.fit_through is None
    # prior only: published-data shares of a $100 budget, so a few dollars at most
    assert model.recommend("WR-top", value=30, budget_left=90).bid <= 10


def test_the_fit_round_trips_into_the_report_model(tmp_path, monkeypatch):
    obs = [cm.Obs(3, "QB-top", (11,)), cm.Obs(4, "RB-deep", ())]
    (tmp_path / "x_2026.json").write_text(
        json.dumps({"through_week": 4, "obs": cm.obs_to_json(obs)})
    )
    monkeypatch.setattr(waiver_wire, "CLEARING_FIT_DIR", tmp_path)
    model, note = waiver_wire.load_clearing_model("x", 2026, 1000)
    assert "2 name-weeks through week 4" in note
    assert model.p_contested("QB-top") > model.p_contested("RB-deep")
