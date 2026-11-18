"""The committed Mantis scorecard still says what the 2026-11-15 diagnosis found.

``data/waivers/scorecard/mantis_2026.json`` is the backfill of weeks 2-7 and 9
(``python scripts/waiver_scorecard.py --league mantis --weeks 2-7 9``). These are
the numbers the waiver plan is judged against, so they are pinned here: a
regeneration that moves them has either found a bug in the scorecard or changed
what "the advice" means, and either deserves a human looking at it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CARD = REPO / "data" / "waivers" / "scorecard" / "mantis_2026.json"

pytestmark = pytest.mark.skipif(not CARD.exists(), reason="scorecard not generated")


@pytest.fixture(scope="module")
def card():
    return json.loads(CARD.read_text(encoding="utf-8"))


def test_filed_adds_scored_against_drops_board_top_and_hindsight(card):
    t = card["claims"]["totals"]
    assert card["claims"]["n"] == 8
    # next four weeks, summed over the 8 adds filed in weeks 2-7
    assert t["add"][2] == pytest.approx(157, abs=0.5)
    assert t["drop"][2] == pytest.approx(42, abs=0.6)
    assert t["board_top"][2] == pytest.approx(282, abs=0.5)
    assert t["best_at_pos"][2] == pytest.approx(431, abs=0.6)
    # and the shorter windows, which the plan also reads
    assert t["add"][0] == pytest.approx(54, abs=0.5)
    assert t["add"][1] == pytest.approx(108, abs=0.5)


def test_bids_cost_475_where_19_would_have_won(card):
    mine = card["bids"]["mine"]
    assert (mine["n"], mine["paid"], mine["clearing"]) == (8, 475, 19)
    assert mine["uncontested"] == 7


def test_most_of_the_room_is_uncontested(card):
    room = card["bids"]["room"]
    assert room["n"] == 49 and room["uncontested"] == 36  # 73%


def test_listed_names_baselines_for_weeks_2_6(card):
    m = card["listed"]["methods"]
    assert m["tool_blend"]["weeks_2_6"]["n"] == 120
    assert m["tool_blend"]["weeks_2_6"]["p4"] == pytest.approx(25.3, abs=0.05)
    assert m["sleeper_only"]["weeks_2_6"]["p4"] == pytest.approx(25.7, abs=0.05)
    assert m["last_week_points"]["weeks_2_6"]["p4"] == pytest.approx(19.4, abs=0.1)
    assert m["hindsight_best"]["weeks_2_6"]["p4"] == pytest.approx(40.3, abs=0.05)


def test_waiver_wire_writes_its_record_on_both_exits():
    """``--no-gate`` and the gated path must both freeze the run.

    An early ``return`` that skips ``save_record`` would silently stop
    recording exactly the runs people take shortcuts on.
    """
    tree = ast.parse((REPO / "scripts" / "waiver_wire.py").read_text(encoding="utf-8"))
    main = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"
    )
    calls = [
        n
        for n in ast.walk(main)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "save_record"
    ]
    assert len(calls) >= 2
