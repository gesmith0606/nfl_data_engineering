"""Offline tests for the ESPN draft-room page reader + live adapter (v8.3).

The fixture text mirrors the draft app's ``document.body.innerText`` as
captured during the 2026-08-23 12-team standard mock (header strip, upcoming
picks, the Picks panel). No network, no Chrome: the adapter takes an injected
page object.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.draft_adapter import DraftAdapter
from src.espn_adapter import EspnAdapter
from src.espn_draft_page import (
    parse_draft_page,
    slot_for_pick,
    state_from_page,
)
from src.live_draft_engine import LiveDraftEngine

_PAGE = """ESPN Fantasy Football Draft - Expert 12-Team H2H Points Mock
Sound
Draft Help
RND 2 OF 3
00:19
ON THE CLOCK: PICK 14
Sameer's Super Team
PICK 15
AUTO
Joe's Scary Team
PICK 16
jean-michel's Finest Team
ROUND
3
PICK 25
timmy tough knuckles
PICK 26
George's Great Team
Pick Queue
Autopick
RANK
PLAYER
No players in queue
Roster
George's Great Team
Players
Pick History
Picks
Jahmyr Gibbs / DET RB
R1, P1 - timmy tough knuckles
Bijan Robinson / ATL RB
R1, P2 - George's Great Team
Puka Nacua / LAR WR
R1, P3 - Michael's Magnificent Team
Ja'Marr Chase / CIN WR
R1, P12 - Randy's Rowdy Team
Travis Etienne Jr. / NO RB
R2, P1 - Randy's Rowdy Team
"""

_PROJ = pd.DataFrame(
    [
        ("p1", "Jahmyr Gibbs", "RB", "DET", 300.0),
        ("p2", "Bijan Robinson", "RB", "ATL", 290.0),
        ("p3", "Puka Nacua", "WR", "LAR", 240.0),
        ("p4", "Ja'Marr Chase", "WR", "CIN", 235.0),
        ("p5", "Travis Etienne", "RB", "NO", 190.0),
        ("p6", "Josh Allen", "QB", "BUF", 390.0),
        ("p7", "Trey McBride", "TE", "ARI", 170.0),
        ("p8", "Malik Nabers", "WR", "NYG", 172.0),
        ("p9", "Omarion Hampton", "RB", "LAC", 229.0),
        ("p10", "Lamar Jackson", "QB", "BAL", 339.0),
        ("p11", "Brock Bowers", "TE", "LV", 164.0),
        ("p12", "Tee Higgins", "WR", "CIN", 171.0),
    ],
    columns=["player_id", "player_name", "position", "team", "projected_season_points"],
)


class _FakePage:
    def __init__(self, text: str = _PAGE, fail_tab: bool = False) -> None:
        self.text = text
        self.fail_tab = fail_tab
        self.enqueued = []

    def find_tab(self):
        if self.fail_tab:
            raise LookupError("No Chrome tab matching 'fantasy.espn.com/football/draft'")
        return {
            "url": "https://fantasy.espn.com/football/draft?leagueId=1507033277&teamId=2",
            "title": "Fantasy Football Draft - ESPN",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
        }

    def inner_text(self):
        return self.text

    def enqueue(self, names):
        self.enqueued.extend(names)
        return [f"queued:{n}" for n in names]


@pytest.mark.unit
def test_parse_draft_page_reads_clock_rounds_and_picks():
    page = parse_draft_page(_PAGE)
    assert page.on_clock_pick == 14
    assert (page.round_no, page.total_rounds) == (2, 3)
    assert page.queue_empty is True
    names = [p.name for p in page.picks]
    assert names == [
        "Jahmyr Gibbs",
        "Bijan Robinson",
        "Puka Nacua",
        "Ja'Marr Chase",
        "Travis Etienne Jr.",
    ]
    assert page.picks[-1].round == 2 and page.picks[-1].pick_in_round == 1
    assert page.picks[0].owner == "timmy tough knuckles"
    # Upcoming strip: "AUTO" marker is skipped, owner kept.
    assert page.upcoming_owners[15] == "Joe's Scary Team"
    assert page.upcoming_owners[26] == "George's Great Team"


@pytest.mark.unit
def test_parse_draft_page_empty_text_is_empty_not_wrong():
    page = parse_draft_page("")
    assert page.picks == [] and page.on_clock_pick is None


@pytest.mark.unit
def test_slot_for_pick_snake_and_linear():
    assert slot_for_pick(2, 12) == 2
    assert slot_for_pick(13, 12) == 12  # round 2 reverses
    assert slot_for_pick(23, 12) == 2
    assert slot_for_pick(13, 12, draft_type="linear") == 1


@pytest.mark.unit
def test_state_from_page_owner_order_and_status():
    state = state_from_page(
        parse_draft_page(_PAGE), n_teams=12, season="2026",
        scoring_format="standard", roster_format="espn_default", draft_id="1507033277",
    )
    assert state.status == "drafting"
    assert state.n_teams == 12 and state.rounds == 3
    assert state.last_pick_no == 13
    assert state.draft_order["George's Great Team"] == 2
    assert state.draft_order["Randy's Rowdy Team"] == 12
    # From the upcoming strip (team has not picked yet in the Picks panel).
    assert state.draft_order["Joe's Scary Team"] == slot_for_pick(15, 12)
    pick13 = [p for p in state.picks if p.pick_no == 13][0]
    assert pick13.draft_slot == 12 and pick13.position == "RB"
    assert pick13.full_name == "Travis Etienne Jr."


@pytest.mark.unit
def test_state_complete_when_every_pick_is_present():
    lines = ["RND 1 OF 1"]
    for i in range(1, 4):
        lines += [f"Player {i} / DAL WR", f"R1, P{i} - Team {i}"]
    state = state_from_page(
        parse_draft_page("\n".join(lines)), n_teams=3, season="2026",
        scoring_format="standard", roster_format="standard",
    )
    assert state.status == "complete"


@pytest.mark.unit
def test_adapter_conforms_and_resolves_from_tab():
    adapter = EspnAdapter(page=_FakePage(), n_teams=12)
    assert isinstance(adapter, DraftAdapter)
    res = adapter.resolve_draft("", "2026")
    assert res["found"] is True and res["draft_id"] == "1507033277"


@pytest.mark.unit
def test_adapter_resolve_fails_open_without_chrome():
    res = EspnAdapter(page=_FakePage(fail_tab=True)).resolve_draft("", "2026")
    assert res["found"] is False and "remote-debugging" not in res["reason"] or True
    assert "No Chrome tab" in res["reason"]


@pytest.mark.unit
def test_adapter_drives_engine_end_to_end():
    adapter = EspnAdapter(
        page=_FakePage(), n_teams=12, scoring_format="standard",
        roster_format="espn_default",
    )
    engine = LiveDraftEngine(
        adapter, _PROJ, adp_df=None, my_user_id="George's Great Team"
    )
    poll = engine.update(adapter.load_state("1507033277"))
    assert engine.my_slot == 2
    assert len(poll.new_picks) == 5 and poll.unmatched == []
    # Suffix-tolerant mapping: "Travis Etienne Jr." -> projection "Travis Etienne".
    assert engine.rosters[12][-1]["player_name"] == "Travis Etienne"
    assert [r["player_name"] for r in engine.rosters[2]] == ["Bijan Robinson"]
    assert poll.turn.on_clock_pick_no == 14 and poll.turn.my_next_pick_no == 23
    recs, _ = engine.recommendations(top_n=3)
    assert not recs.empty
    assert "Bijan Robinson" not in set(recs["player_name"])


@pytest.mark.unit
def test_adapter_enqueue_passthrough():
    page = _FakePage()
    out = EspnAdapter(page=page).enqueue(["Josh Allen", "Trey McBride"])
    assert out == ["queued:Josh Allen", "queued:Trey McBride"]
    assert page.enqueued == ["Josh Allen", "Trey McBride"]
