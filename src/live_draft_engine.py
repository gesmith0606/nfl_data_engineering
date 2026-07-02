"""Platform-agnostic live draft engine (v8.0, Phase 86).

Consumes a :class:`src.draft_adapter.DraftAdapter` (never a platform directly) and,
on each polled :class:`src.draft_models.DraftState`, diffs new picks, syncs the
:class:`src.draft_optimizer.DraftBoard`, reconstructs every team's roster, computes
snake/linear pick order + who is on the clock + the user's next pick, and surfaces
recommendations (on the user's turn) plus key-moment alerts.

The engine is pure given its inputs — feeding it a sequence of DraftStates replays a
draft deterministically, so it is fully unit-testable offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from src.draft_adapter import DraftAdapter
from src.draft_models import DraftState, PickEvent
from src.draft_optimizer import (
    DraftAdvisor,
    DraftBoard,
    _pick_grade,
    compute_value_scores,
)

# Tuning thresholds (picks).
_REACH_GAP = 10  # taken >= this many spots BEFORE ADP → reach
_STEAL_GAP = 10  # taken >= this many spots AFTER ADP → steal/value
_VALUE_DROP_GAP = 12  # elite player sliding this far past their model rank
_RUN_WINDOW = 4  # look-back window for a positional run
_RUN_COUNT = 3  # this many of one position within the window → run


@dataclass(frozen=True)
class KeyMoment:
    """A noteworthy draft event the co-pilot should surface."""

    kind: str  # value_drop | positional_run | reach | steal | grade
    pick_no: int
    player: str
    detail: str


@dataclass
class TurnInfo:
    """Who is on the clock and when the user picks next."""

    on_clock_slot: int
    on_clock_pick_no: int
    is_my_turn: bool
    my_slot: Optional[int]
    my_next_pick_no: Optional[int]


@dataclass
class PollResult:
    """What changed since the previous poll."""

    new_picks: List[PickEvent] = field(default_factory=list)
    unmatched: List[PickEvent] = field(default_factory=list)
    turn: Optional[TurnInfo] = None
    key_moments: List[KeyMoment] = field(default_factory=list)


class LiveDraftEngine:
    """Stateful engine driving a single live draft via a DraftAdapter."""

    def __init__(
        self,
        adapter: DraftAdapter,
        projections_df: pd.DataFrame,
        adp_df: Optional[pd.DataFrame] = None,
        my_user_id: Optional[str] = None,
        my_slot: Optional[int] = None,
    ) -> None:
        self.adapter = adapter
        self.enriched = compute_value_scores(projections_df, adp_df)
        self.my_user_id = my_user_id
        self.my_slot = my_slot
        self.board: Optional[DraftBoard] = None
        self.advisor: Optional[DraftAdvisor] = None
        self.rosters: Dict[int, List[Dict[str, Any]]] = {}
        self.my_keepers: List[Dict[str, Any]] = []
        self._seen_pick_no = 0
        self.state: Optional[DraftState] = None
        # Fast lookup: model_rank -> vorp, for pick grading / par value.
        self._vorp_by_rank = dict(
            zip(self.enriched.get("model_rank", []), self.enriched.get("vorp", []))
        )

    # -- public --------------------------------------------------------------

    def update(self, state: DraftState) -> PollResult:
        """Ingest a polled DraftState and return what changed (idempotent)."""
        if self.board is None:
            self.board = DraftBoard(
                self.enriched,
                roster_format=state.roster_format or "standard",
                n_teams=state.n_teams or 12,
            )
            self.advisor = DraftAdvisor(self.board, scoring_format=state.scoring_format)
            if self.my_slot is None and self.my_user_id:
                slot = state.draft_order.get(self.my_user_id)
                self.my_slot = int(slot) if slot is not None else None
        self.state = state

        new_picks = [p for p in state.picks if p.pick_no > self._seen_pick_no]
        matched, unmatched = self.adapter.map_picks(new_picks, self.enriched)
        matched_by_pick = {m.get("pick_no"): m for m in matched}

        moments: List[KeyMoment] = []
        for pick in new_picks:
            m = matched_by_pick.get(pick.pick_no)
            player_key = (m.get("player_id") if m else None) or pick.full_name
            is_mine = self.my_slot is not None and pick.draft_slot == self.my_slot
            self.board.draft_player(str(player_key), by_me=is_mine)
            self.rosters.setdefault(pick.draft_slot, []).append(
                m if m else {"player_name": pick.full_name, "position": pick.position}
            )
            moments.extend(self._pick_moments(pick, m))

        if new_picks:
            self._seen_pick_no = max(p.pick_no for p in new_picks)
            moments.extend(self._run_moment(state))
            moments.extend(self._value_drop_moment(state))

        return PollResult(
            new_picks=new_picks,
            unmatched=unmatched,
            turn=self.turn_info(),
            key_moments=moments,
        )

    def preload_keepers(self, keeper_info: Dict[str, List[PickEvent]]) -> int:
        """Mark already-rostered (kept) players off the board before the draft.

        For a keeper league: every kept player across the league becomes
        unavailable, so recommendations come only from the true draftable pool
        (rookies + any dropped players). The user's own keepers are marked as
        their roster so ``remaining_needs`` is correct. Call AFTER the first
        ``update()`` (the board must exist). Returns the count marked off.

        Idempotent enough for repeated calls — drafting an already-drafted player
        is a no-op on the board.
        """
        if self.board is None:
            return 0
        all_kept = keeper_info.get("all", [])
        mine = keeper_info.get("mine", [])
        matched_all, _ = self.adapter.map_picks(all_kept, self.enriched)
        matched_mine, _ = self.adapter.map_picks(mine, self.enriched)
        my_ids = {m.get("player_id") for m in matched_mine}
        self.my_keepers = matched_mine
        for m in matched_all:
            pid = str(m.get("player_id") or "")
            if pid:
                self.board.draft_player(pid, by_me=(m.get("player_id") in my_ids))
        return len(matched_all)

    def my_full_roster(self) -> List[Dict[str, Any]]:
        """Your complete roster: keepers + players you've drafted live."""
        drafted = self.rosters.get(self.my_slot, []) if self.my_slot else []
        return list(self.my_keepers) + list(drafted)

    def turn_info(self) -> Optional[TurnInfo]:
        """Compute on-the-clock slot + the user's next pick number."""
        if self.state is None:
            return None
        n = self.state.n_teams or 12
        on_clock_pick = self._seen_pick_no + 1
        on_clock_slot = self._slot_on_clock(on_clock_pick, n, self.state.draft_type)
        my_next = self._my_next_pick_no(on_clock_pick, n)
        return TurnInfo(
            on_clock_slot=on_clock_slot,
            on_clock_pick_no=on_clock_pick,
            is_my_turn=(self.my_slot is not None and on_clock_slot == self.my_slot),
            my_slot=self.my_slot,
            my_next_pick_no=my_next,
        )

    def recommendations(self, top_n: int = 5):
        """DraftAdvisor recommendations given current board state.

        Returns ``(DataFrame, reasoning)``; empty frame if the board is not built.
        """
        if self.advisor is None:
            return pd.DataFrame(), "Draft not started."
        return self.advisor.recommend(top_n=top_n)

    def best_available(self, positions: Optional[List[str]] = None, top_n: int = 10):
        if self.advisor is None:
            return pd.DataFrame()
        return self.advisor.best_available(positions=positions, top_n=top_n)

    # -- slot math -----------------------------------------------------------

    @staticmethod
    def _slot_on_clock(pick_no: int, n_teams: int, draft_type: str) -> int:
        if n_teams <= 0 or pick_no <= 0:
            return 0
        idx = (pick_no - 1) % n_teams
        rnd = (pick_no - 1) // n_teams + 1
        if draft_type == "snake" and rnd % 2 == 0:
            return n_teams - idx
        return idx + 1

    def _my_next_pick_no(self, start_pick: int, n_teams: int) -> Optional[int]:
        if self.my_slot is None or n_teams <= 0:
            return None
        rounds = self.state.rounds if self.state else 0
        cap = start_pick + (n_teams * max(rounds, 1))
        for p in range(start_pick, cap + 1):
            if self._slot_on_clock(p, n_teams, self.state.draft_type) == self.my_slot:
                return p
        return None

    # -- key moments ---------------------------------------------------------

    def _pick_moments(
        self, pick: PickEvent, matched: Optional[Dict[str, Any]]
    ) -> List[KeyMoment]:
        moments: List[KeyMoment] = []
        if not matched:
            return moments
        adp_rank = matched.get("adp_rank")
        if adp_rank is not None and pd.notna(adp_rank):
            gap = pick.pick_no - float(adp_rank)
            if gap >= _STEAL_GAP:
                moments.append(
                    KeyMoment(
                        "steal",
                        pick.pick_no,
                        pick.full_name,
                        f"Fell {int(gap)} spots past ADP {int(adp_rank)}",
                    )
                )
            elif -gap >= _REACH_GAP:
                moments.append(
                    KeyMoment(
                        "reach",
                        pick.pick_no,
                        pick.full_name,
                        f"Taken {int(-gap)} spots before ADP {int(adp_rank)}",
                    )
                )
        # Pick grade vs par value at this pick slot.
        actual_vorp = matched.get("vorp")
        expected_vorp = self._vorp_by_rank.get(pick.pick_no)
        if (
            actual_vorp is not None
            and expected_vorp is not None
            and pd.notna(actual_vorp)
        ):
            grade = _pick_grade(float(actual_vorp), float(expected_vorp))
            moments.append(
                KeyMoment("grade", pick.pick_no, pick.full_name, f"Pick grade {grade}")
            )
        return moments

    def _run_moment(self, state: DraftState) -> List[KeyMoment]:
        window = state.picks[-_RUN_WINDOW:]
        if len(window) < _RUN_COUNT:
            return []
        counts: Dict[str, int] = {}
        for p in window:
            if p.position:
                counts[p.position] = counts.get(p.position, 0) + 1
        for pos, c in counts.items():
            if c >= _RUN_COUNT:
                last = window[-1]
                return [
                    KeyMoment(
                        "positional_run",
                        last.pick_no,
                        last.full_name,
                        f"{c} {pos} taken in the last {len(window)} picks — run on {pos}",
                    )
                ]
        return []

    def _value_drop_moment(self, state: DraftState) -> List[KeyMoment]:
        if self.board is None or self.board.available.empty:
            return []
        avail = self.board.available
        if "vorp" not in avail.columns or "model_rank" not in avail.columns:
            return []
        top = avail.sort_values("vorp", ascending=False).iloc[0]
        on_clock_pick = self._seen_pick_no + 1
        if int(top["model_rank"]) + _VALUE_DROP_GAP <= on_clock_pick:
            return [
                KeyMoment(
                    "value_drop",
                    on_clock_pick,
                    str(top.get("player_name", "")),
                    f"Rank-{int(top['model_rank'])} player (VORP {top['vorp']}) still "
                    f"available at pick {on_clock_pick}",
                )
            ]
        return []
