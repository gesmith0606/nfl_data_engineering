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

import logging
import os
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
_ROOKIE_DRAFT_MAX_ROUNDS = 5  # <= this many rounds → rookie draft (no ADP moments)
_TIER_POSITIONS = ("QB", "RB", "WR", "TE")  # positions tiered / deep-round scoped
_TIER_CLIFF_MAX_LEFT = 2  # alert when <= this many remain in the best live tier


def _load_vacated_board(season: int) -> pd.DataFrame:
    """Load the UC1 vacated-opportunity sleeper board (scripts/sleeper_board.py).

    Reuses ``build_sleeper_board`` — the exact shot list the 2026-08-28 mock
    proved out — rather than duplicating its computation. scripts/ is not a
    package, so the module is loaded by file path (the repo's test-side
    convention for scripts).

    Args:
        season: Target season for the N-1 -> N vacancy transition.

    Returns:
        The sleeper-board DataFrame (may be empty). Raises on load failure —
        the engine's caller handles fail-soft.
    """
    import importlib.util

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "sleeper_board.py",
    )
    spec = importlib.util.spec_from_file_location("_uc1_sleeper_board", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # top=60 leaves headroom: the live filter removes drafted names each cycle.
    return module.build_sleeper_board(season=season, top=60)


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
        roster_config: Optional[Dict[str, int]] = None,
        adp_moments: Optional[bool] = None,
    ) -> None:
        self.adapter = adapter
        self.enriched = compute_value_scores(projections_df, adp_df)
        self.my_user_id = my_user_id
        self.my_slot = my_slot
        self.roster_config = roster_config
        # ADP-based key moments (steal/reach) and vorp-par pick grades use
        # overall REDRAFT rank — meaningless in rookie/dynasty drafts, where
        # they graded every chalk rookie pick a D (2026-07-11 MANTIS lesson).
        # None = auto: disabled when the draft is short enough to be a rookie
        # draft (rounds <= _ROOKIE_DRAFT_MAX_ROUNDS), enabled otherwise.
        self.adp_moments = adp_moments
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
        # Lazy one-time caches (both must NOT recompute per 2-second poll cycle):
        # positional tiers from the INITIAL board (tier structure is a property
        # of the pre-draft pool — recomputing on the shrinking availability
        # shifts boundaries mid-draft), and the UC1 vacated-opportunity sleeper
        # board for the deep-round lens. None = not yet built/attempted.
        self._tier_pool: Optional[pd.DataFrame] = None
        self._vacated_shots: Optional[pd.DataFrame] = None
        # UC3 correlation edges for stack-aware recommendations. Optional —
        # a missing/broken Gold parquet must never break the draft co-pilot.
        try:
            from src.graph_correlation import load_latest_correlations
        except ImportError:  # pragma: no cover
            from graph_correlation import load_latest_correlations
        try:
            edges = load_latest_correlations()
            self._corr_pairs = (
                edges[edges["level"] == "pair"] if not edges.empty else pd.DataFrame()
            )
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Correlation edges unavailable — stack-aware recommendations disabled"
            )
            self._corr_pairs = pd.DataFrame()

    # -- public --------------------------------------------------------------

    def update(self, state: DraftState) -> PollResult:
        """Ingest a polled DraftState and return what changed (idempotent)."""
        if self.board is None:
            self.board = DraftBoard(
                self.enriched,
                roster_format=state.roster_format or "standard",
                n_teams=state.n_teams or 12,
                roster_config=self.roster_config,
            )
            self.advisor = DraftAdvisor(self.board, scoring_format=state.scoring_format)
            if self.my_slot is None and self.my_user_id:
                slot = state.draft_order.get(self.my_user_id)
                self.my_slot = int(slot) if slot is not None else None
            if self.adp_moments is None:
                rounds = state.rounds or 15
                self.adp_moments = rounds > _ROOKIE_DRAFT_MAX_ROUNDS
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
        matched_all, unmatched_all = self.adapter.map_picks(all_kept, self.enriched)
        matched_mine, _ = self.adapter.map_picks(mine, self.enriched)
        my_ids = {m.get("player_id") for m in matched_mine}
        self.my_keepers = matched_mine
        for m in matched_all:
            pid = str(m.get("player_id") or "")
            if pid:
                self.board.draft_player(pid, by_me=(m.get("player_id") in my_ids))
        # KM-1: keepers whose projection mapping failed must STILL leave the
        # pool — otherwise they linger as phantom availability and trigger
        # false "value drop" alerts (Trey McBride, MANTIS 2026-07-11). Name
        # removal is nickname/suffix tolerant and records no pick.
        removed = self.board.remove_players(
            [pe.full_name for pe in unmatched_all if pe.full_name]
        )
        return len(matched_all) + removed

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

        Returns ``(DataFrame, reasoning)``; empty frame if the board is not
        built. When correlation edges are available (UC3), a ``stack_note``
        column flags candidates correlated with players already on your
        roster ("stacks with T.Hill (+0.60)" / "shares ceiling with ...").
        """
        if self.advisor is None:
            return pd.DataFrame(), "Draft not started."
        # Over-fetch then apply the market-belief filter so low-sample
        # artifacts never occupy a recommendation slot.
        recs, reasoning = self.advisor.recommend(top_n=top_n * 2, **self._turn_kwargs())
        if not recs.empty:
            recs = self._market_believed(recs).head(top_n)
        if not recs.empty and "player_id" in recs.columns:
            recs = recs.copy()
            recs["stack_note"] = recs["player_id"].map(self.stack_note)
        return recs, reasoning

    def _turn_kwargs(self) -> Dict[str, Any]:
        """Next-pick + picks-remaining for opportunity-cost scoring (empty if unknown)."""
        turn = self.turn_info()
        if turn is None or self.my_slot is None or self.state is None:
            return {}
        n = self.state.n_teams or 12
        start = turn.on_clock_pick_no + (1 if turn.is_my_turn else 0)
        kwargs: Dict[str, Any] = {"next_pick_no": self._my_next_pick_no(start, n)}
        total = n * (self.state.rounds or 0)
        if total:
            kwargs["my_picks_remaining"] = sum(
                1
                for p in range(turn.on_clock_pick_no, total + 1)
                if self._slot_on_clock(p, n, self.state.draft_type) == self.my_slot
            )
        return kwargs

    def stack_note(self, player_id: str) -> str:
        """Strongest correlation between a candidate and your current roster.

        Args:
            player_id: Candidate player's gsis id.

        Returns:
            Human-readable note (e.g. ``"stacks with T.Hill (+0.60)"``,
            ``"shares ceiling with S.Barkley (-0.42)"``) or ``""`` when no
            served edge connects the candidate to your roster.
        """
        if self._corr_pairs.empty:
            return ""
        roster_ids = {
            str(r.get("player_id")) for r in self.my_full_roster() if r.get("player_id")
        }
        if not roster_ids:
            return ""
        pid = str(player_id)
        pairs = self._corr_pairs
        mine = pairs[
            ((pairs["player_id_a"] == pid) & pairs["player_id_b"].isin(roster_ids))
            | ((pairs["player_id_b"] == pid) & pairs["player_id_a"].isin(roster_ids))
        ]
        if mine.empty:
            return ""
        best = mine.loc[mine["rho"].abs().idxmax()]
        other = (
            best["player_name_b"]
            if str(best["player_id_a"]) == pid
            else best["player_name_a"]
        )
        rho = float(best["rho"])
        verb = "stacks with" if rho > 0 else "shares ceiling with"
        return f"{verb} {other} ({rho:+.2f})"

    def best_available(self, positions: Optional[List[str]] = None, top_n: int = 10):
        if self.advisor is None:
            return pd.DataFrame()
        avail = self.advisor.best_available(positions=positions, top_n=top_n * 2)
        if isinstance(avail, pd.DataFrame) and not avail.empty:
            avail = self._market_believed(avail).head(top_n)
        return avail

    # -- deep rounds (UC1 vacated-opportunity shots) ---------------------------

    def is_deep_round(self, recs: Optional[pd.DataFrame]) -> bool:
        """True when every current recommendation's VORP is <= 0.

        After ~round 8 the whole rec list sits at/below replacement and VORP
        can no longer separate players (2026-08-28 ESPN mock) — the signal to
        switch the lens to vacated opportunity.

        Args:
            recs: The recommendations frame from :meth:`recommendations`.

        Returns:
            True iff the TOP recommendation's VORP is <= 0 (the primary
            trigger — the model can no longer separate its first choice from
            replacement), falling back to "all numeric VORPs <= 0" when the
            top row's VORP is NaN.
        """
        if recs is None or len(recs) == 0 or "vorp" not in getattr(recs, "columns", ()):
            return False
        vorp = pd.to_numeric(recs["vorp"], errors="coerce")
        first = vorp.iloc[0]
        if pd.notna(first):
            return float(first) <= 0.0
        rest = vorp.dropna()
        return (not rest.empty) and float(rest.max()) <= 0.0

    def deep_round_shots(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """Top still-available UC1 vacated-opportunity shots for the deep rounds.

        The sleeper board is loaded ONCE lazily (first call — never on the
        poll hot path until the deep-round condition first fires) and then
        only filtered by the drafted-name set each cycle. Fail-soft: any load
        failure logs one warning, caches an empty board, and returns [] —
        never crashes mid-draft, never retries the failing load every cycle.

        Args:
            top_n: Maximum number of shots to return.

        Returns:
            List of dicts with ``player_name``, ``position``, ``team``,
            ``absorbed_share``, ``rivals``, and a one-line ``reason``
            (vacated share + rival count), sorted by absorption score.
        """
        if self._vacated_shots is None:
            try:
                season = (
                    int(self.state.season) if self.state and self.state.season else 0
                )
            except (TypeError, ValueError):
                season = 0
            if season <= 0:
                from datetime import date

                season = date.today().year
            try:
                board = _load_vacated_board(season)
            except Exception as exc:  # noqa: BLE001 — never crash a live draft
                logging.getLogger(__name__).warning(
                    "DEEP ROUNDS lens disabled — vacated-opportunity sleeper "
                    "board unavailable (%s)",
                    exc,
                )
                board = pd.DataFrame()
            self._vacated_shots = (
                board if isinstance(board, pd.DataFrame) else pd.DataFrame()
            )
        board = self._vacated_shots
        if board.empty or "player_name" not in board.columns:
            return []

        from src.draft_optimizer import name_key

        drafted = {
            name_key(str(r.get("player_name")))
            for roster in self.rosters.values()
            for r in roster
            if r.get("player_name")
        }
        shots: List[Dict[str, Any]] = []
        for _, row in board.iterrows():
            name = str(row["player_name"])
            if name_key(name) in drafted:
                continue
            share = float(row.get("vacancy_absorbed_share") or 0.0)
            tgt_vac = float(row.get("net_target_vacancy") or 0.0)
            carry_vac = float(row.get("net_carry_vacancy") or 0.0)
            rivals = int(row.get("vacancy_competition_n") or 0)
            # The story is the vacated share he steps into ("AJ Dillon —
            # 48.7% of CAR's carries vacated", 2026-08-28 mock), quoted from
            # the dominant vacancy channel; absorbed_share is the sort score.
            vac, kind = max((carry_vac, "carries"), (tgt_vac, "targets"))
            # Contingency-depth players (RB4s etc.) arrive pre-demoted to the
            # board's bottom; if one still surfaces, say so out loud.
            depth_note = str(row.get("depth_note") or "").strip()
            shots.append(
                {
                    "player_name": name,
                    "position": str(row.get("position", "")),
                    "team": str(row.get("team", "")),
                    "absorbed_share": round(share, 3),
                    "rivals": rivals,
                    "reason": (
                        f"steps into {vac:.1%} vacated {kind} "
                        f"(absorbed {share:.1%} so far), "
                        f"{rivals} rival(s) competing"
                        + (f" — {depth_note}" if depth_note else "")
                    ),
                }
            )
            if len(shots) >= top_n:
                break
        return shots

    # -- tier cliffs (doctrine §2 / §9) ---------------------------------------

    @staticmethod
    def _pool_keys(df: pd.DataFrame) -> pd.Series:
        """Stable join keys between the tier pool and the live availability."""
        if "player_id" in df.columns and df["player_id"].notna().any():
            return df["player_id"].astype(str)
        from src.draft_optimizer import name_key

        return df["player_name"].map(lambda n: name_key(str(n)))

    def _build_tier_pool(self) -> pd.DataFrame:
        """Positional tiers computed ONCE from the initial (full) board."""
        empty = pd.DataFrame(
            columns=["_key", "player_name", "position", "tier", "_pts"]
        )
        pool = self._market_believed(self.enriched)
        if pool.empty or not {"position", "player_name"} <= set(pool.columns):
            return empty
        pts_col = (
            "projected_season_points"
            if "projected_season_points" in pool.columns
            else "projected_points"
        )
        if pts_col not in pool.columns:
            return empty
        pool = pool[pool["position"].isin(_TIER_POSITIONS)].copy()
        pool = pool[pool[pts_col].notna()]
        if pool.empty:
            return empty
        try:
            from src.draft_tiers import compute_tiers
        except ImportError:  # pragma: no cover
            from draft_tiers import compute_tiers

        pool["tier"] = compute_tiers(pool, points_col=pts_col)
        pool["_pts"] = pool[pts_col].astype(float)
        pool["_key"] = self._pool_keys(pool)
        return pool[["_key", "player_name", "position", "tier", "_pts"]].dropna(
            subset=["tier"]
        )

    def tiered_available(self) -> pd.DataFrame:
        """Initial-board tiers filtered to still-available players.

        The tier structure itself is cached from the first call (see
        ``_tier_pool``); per poll cycle this is only a set-membership filter.

        Returns:
            DataFrame with ``player_name``, ``position``, ``tier`` (1 = best)
            and ``_pts`` columns; empty before the board is built.
        """
        if self.board is None:
            return pd.DataFrame(
                columns=["_key", "player_name", "position", "tier", "_pts"]
            )
        if self._tier_pool is None:
            self._tier_pool = self._build_tier_pool()
        pool = self._tier_pool
        if pool.empty:
            return pool
        avail = self.board.available
        if avail is None or avail.empty:
            return pool.iloc[0:0]
        return pool[pool["_key"].isin(set(self._pool_keys(avail)))]

    def tier_cliff_alerts(
        self, threshold: int = _TIER_CLIFF_MAX_LEFT
    ) -> List[Dict[str, Any]]:
        """Positions whose best available tier is nearly gone (doctrine §2/§9).

        "Draft priority is 'last player in a tier at a scarce position', not
        'next-best rank'" — this is the take-him-now trigger.

        Args:
            threshold: Alert when <= this many players remain in the current
                best available tier at a position (default 2).

        Returns:
            List of dicts sorted most-urgent first: ``position``, ``tier``,
            ``remaining``, ``players`` (names left in the tier),
            ``next_player`` (who starts the next tier, or None) and
            ``drop_pts`` (projected-point drop to that next tier, or None).
        """
        live = self.tiered_available()
        if live.empty:
            return []
        alerts: List[Dict[str, Any]] = []
        for pos, sub in live.groupby("position"):
            sub = sub.sort_values("_pts", ascending=False)
            top_tier = int(sub.iloc[0]["tier"])
            current = sub[sub["tier"] == top_tier]
            if len(current) > threshold:
                continue
            nxt = sub[sub["tier"] > top_tier]
            next_player = str(nxt.iloc[0]["player_name"]) if not nxt.empty else None
            drop_pts = (
                round(float(current["_pts"].min() - nxt.iloc[0]["_pts"]), 1)
                if not nxt.empty
                else None
            )
            alerts.append(
                {
                    "position": str(pos),
                    "tier": top_tier,
                    "remaining": int(len(current)),
                    "players": [str(n) for n in current["player_name"]],
                    "next_player": next_player,
                    "drop_pts": drop_pts,
                }
            )
        return sorted(alerts, key=lambda a: a["remaining"])

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
        # A snake slot's next turn is at most 2*n_teams-1 picks away (slot 1
        # picks 1 and 2*n_teams). Platforms don't always report a round count —
        # manual/paste-sync passes rounds=0 and ESPN falls back to 0 when the
        # round header doesn't parse — and a one-round cap then hid the next
        # pick for every slot past its turn, so slots 1-3 of a 12-team league
        # silently lost the opportunity-cost scoring recommendations rank by.
        cap = start_pick + (n_teams * max(rounds, 2))
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
        # Redraft-ADP steals/reaches and vorp-par grades are noise in rookie
        # drafts (KM-2) — suppressed when adp_moments resolved False. None
        # (not yet resolved by update()) keeps the redraft default: enabled.
        if self.adp_moments is False:
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

    @staticmethod
    def _market_believed(df: pd.DataFrame) -> pd.DataFrame:
        """Drop low-sample projections the market doesn't rank.

        Delegates to :func:`src.draft_optimizer.market_believed` (shared with
        the draft assistant CLI) — hidden rows stay draftable/mappable, just
        not surfaced in recommendations, best-available, or value-drop alerts.
        """
        from src.draft_optimizer import market_believed

        return market_believed(df)

    def _value_drop_moment(self, state: DraftState) -> List[KeyMoment]:
        if self.board is None or self.board.available.empty:
            return []
        avail = self._market_believed(self.board.available)
        if (
            avail.empty
            or "vorp" not in avail.columns
            or "model_rank" not in avail.columns
        ):
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
