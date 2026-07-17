#!/usr/bin/env python3
"""Live draft co-pilot entrypoint (v8.0, Phase 87).

Drives the platform-agnostic :class:`src.live_draft_engine.LiveDraftEngine` for a
live draft and prints a readable (or ``--json``) snapshot: draft status, who is on
the clock, the user's next pick, top recommendations, the user's roster, and
key-moment alerts. Claude Code runs this on draft night and advises from the output.

Modes
-----
* default        — print one snapshot of the current draft state.
* ``--watch``    — poll on an interval, re-printing only when new picks land.
* ``--manual``   — no platform; the operator supplies picks via ``--add-pick``
                   (repeatable). The D-09 fallback for unsupported platforms
                   (e.g. ESPN) or a mid-draft API break.

Examples
--------
    python scripts/draft_live.py --username georgesmith --my-slot 5
    python scripts/draft_live.py --draft-id 999000111 --watch
    python scripts/draft_live.py --manual --teams 12 --my-slot 5 \\
        --add-pick "Ja'Marr Chase" --add-pick "Bijan Robinson"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import List, Optional

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import sleeper_http  # noqa: E402
from src.draft_adapter import SleeperAdapter  # noqa: E402
from src.draft_models import DraftState, PickEvent  # noqa: E402
from src.draft_optimizer import (  # noqa: E402
    DraftAdvisor,
    DraftBoard,
    MockDraftSimulator,
    compute_value_scores,
    draftable_positions,
    roster_config_from_positions,
    roster_config_from_slots,
)
from src.espn_adapter import EspnAdapter  # noqa: E402
from src.league_scoring import score_with_settings, unmodeled_offense_keys  # noqa: E402
from src.live_draft_engine import LiveDraftEngine, PollResult  # noqa: E402
from src.nfl_data_integration import NFLDataFetcher  # noqa: E402
from src.projection_engine import generate_preseason_projections  # noqa: E402
from src.projection_store import load_latest_preseason  # noqa: E402
from src.roster_optimizer import drop_candidates, optimal_lineup  # noqa: E402
from src.yahoo_adapter import YahooAdapter  # noqa: E402

logging.basicConfig(level=logging.INFO)

# sleeper: live. yahoo: live (requires OAuth env + one-time grant). espn: gated
# NO-GO (no live API) — resolve/load fail loudly toward --manual (89-SPIKE-FINDINGS).
_ADAPTERS = {
    "sleeper": SleeperAdapter,
    "yahoo": YahooAdapter,
    "espn": EspnAdapter,
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _latest_preseason_parquet(season: int) -> Optional[pd.DataFrame]:
    """Thin wrapper around :func:`src.projection_store.load_latest_preseason`.

    Preserved for backward compatibility with callers and tests that reference
    this function by name.  All logic lives in the canonical loader.
    """
    return load_latest_preseason(season)


def load_projections(
    season: int, scoring: str, projections_file: Optional[str]
) -> pd.DataFrame:
    """Load projections for the draft, most-reliable source first.

    Order: an explicit ``--projections-file`` CSV, then the latest committed
    preseason projections parquet via :func:`src.projection_store.load_latest_preseason`
    (draft-day robust — upstream seasonal data is routinely unavailable
    pre-season and 404s a fresh generate), then a live generate as a last resort.
    """
    if projections_file and os.path.exists(projections_file):
        return pd.read_csv(projections_file)
    preseason = load_latest_preseason(season)
    if preseason is not None and not preseason.empty:
        return preseason
    fetcher = NFLDataFetcher()
    seasonal_df = fetcher.fetch_player_seasonal([season - 2, season - 1])
    return generate_preseason_projections(
        seasonal_df, scoring_format=scoring, target_season=season
    )


def load_adp(adp_file: Optional[str]) -> Optional[pd.DataFrame]:
    """Load ADP from a CSV file (default data/adp_latest.csv) if present."""
    path = adp_file or os.path.join("data", "adp_latest.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return None


def _empty_state(roster_format: str, scoring: str, season: str) -> DraftState:
    """A pick-less DraftState — lets a roster report build the board with no draft."""
    return DraftState(
        draft_id="",
        status="",
        draft_type="snake",
        season=season,
        n_teams=12,
        rounds=0,
        scoring_format=scoring,
        roster_format=roster_format,
        draft_order={},
        slot_to_roster_id={},
        picks=(),
    )


def _resolve_single_league(user_id: str, season: str) -> Optional[str]:
    """Return the user's league_id if they have exactly one for the season, else None."""
    url = f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{season}"
    leagues = sleeper_http.fetch_sleeper_json(url)
    if isinstance(leagues, list) and len(leagues) == 1:
        return str(leagues[0].get("league_id") or "") or None
    return None


# ---------------------------------------------------------------------------
# Manual-entry fallback (D-09 / SKILL-04)
# ---------------------------------------------------------------------------


def build_manual_state(
    picked_names: List[str],
    projections: pd.DataFrame,
    n_teams: int,
    draft_type: str,
    scoring: str,
    roster: str,
    season: str,
) -> DraftState:
    """Build a DraftState from operator-typed player names.

    Resolves each name against the projection frame for position/team; unknown
    names still produce a pick (position/team blank) so nothing is lost.
    """
    proj = projections.copy()
    if "player_name" in proj.columns:
        proj["_norm"] = proj["player_name"].astype(str).str.lower().str.strip()
    picks = []
    for i, raw_name in enumerate(picked_names, start=1):
        name = raw_name.strip()
        pos, team = "", ""
        if "player_name" in proj.columns:
            match = proj[proj["_norm"] == name.lower()]
            if not match.empty:
                row = match.iloc[0]
                pos = str(row.get("position", "")).upper()
                team = str(row.get("team", "")).upper()
        idx = (i - 1) % n_teams
        rnd = (i - 1) // n_teams + 1
        slot = (n_teams - idx) if (draft_type == "snake" and rnd % 2 == 0) else idx + 1
        first, _, last = name.partition(" ")
        picks.append(
            PickEvent(
                pick_no=i,
                round=rnd,
                draft_slot=slot,
                roster_id=slot,
                picked_by="manual",
                sleeper_player_id="",
                first_name=first,
                last_name=last,
                position=pos,
                team=team,
                is_keeper=False,
            )
        )
    return DraftState(
        draft_id="manual",
        status="drafting",
        draft_type=draft_type,
        season=season,
        n_teams=n_teams,
        rounds=0,
        scoring_format=scoring,
        roster_format=roster,
        draft_order={},
        slot_to_roster_id={},
        picks=tuple(picks),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render(engine: LiveDraftEngine, poll: PollResult, top_n: int, as_json: bool) -> str:
    """Render a snapshot of current draft state + advice."""
    turn = poll.turn
    recs, reasoning = engine.recommendations(top_n=top_n)
    rec_cols = [
        c
        for c in [
            "player_name",
            "position",
            "team",
            "projected_points",
            "vorp",
            "value_tier",
            "adp_rank",
            "stack_note",
        ]
        if c in recs.columns
    ]
    rec_records = recs[rec_cols].to_dict("records") if not recs.empty else []
    my_roster = engine.rosters.get(turn.my_slot, []) if turn and turn.my_slot else []
    roster_view = [
        {"player_name": r.get("player_name"), "position": r.get("position")}
        for r in my_roster
    ]
    state = engine.state

    if as_json:
        return json.dumps(
            {
                "draft_id": state.draft_id if state else "",
                "status": state.status if state else "",
                "on_clock_pick": turn.on_clock_pick_no if turn else None,
                "on_clock_slot": turn.on_clock_slot if turn else None,
                "is_my_turn": turn.is_my_turn if turn else None,
                "my_slot": turn.my_slot if turn else None,
                "my_next_pick_no": turn.my_next_pick_no if turn else None,
                "new_picks": [p.full_name for p in poll.new_picks],
                "unmatched": [p.full_name for p in poll.unmatched],
                "key_moments": [
                    {
                        "kind": m.kind,
                        "pick_no": m.pick_no,
                        "player": m.player,
                        "detail": m.detail,
                    }
                    for m in poll.key_moments
                ],
                "recommendations": rec_records,
                "reasoning": reasoning,
                "my_roster": roster_view,
            },
            indent=2,
            default=str,
        )

    lines = []
    if state:
        lines.append(
            f"DRAFT {state.draft_id} [{state.status}] {state.draft_type} "
            f"{state.n_teams}-team {state.scoring_format}"
        )
    if turn:
        flag = "  <<< YOUR PICK" if turn.is_my_turn else ""
        lines.append(
            f"On the clock: pick {turn.on_clock_pick_no}, slot "
            f"{turn.on_clock_slot}{flag}"
        )
        if turn.my_slot:
            lines.append(
                f"Your slot: {turn.my_slot} | your next pick: "
                f"{turn.my_next_pick_no}"
            )
    if poll.key_moments:
        lines.append("\nKEY MOMENTS:")
        for m in poll.key_moments:
            lines.append(f"  [{m.kind}] pick {m.pick_no} {m.player}: {m.detail}")
    if rec_records:
        lines.append(f"\nTOP {len(rec_records)} RECOMMENDATIONS  ({reasoning})")
        for r in rec_records:
            stack = f"  [{r['stack_note']}]" if r.get("stack_note") else ""
            lines.append(
                f"  {str(r.get('player_name','')):<24} "
                f"{str(r.get('position','')):<3} {str(r.get('team','')):<3} "
                f"vorp={r.get('vorp','')}  tier={r.get('value_tier','')}{stack}"
            )
    if roster_view:
        lines.append("\nYOUR ROSTER:")
        for r in roster_view:
            lines.append(f"  {r['position']:<3} {r['player_name']}")
    if poll.unmatched:
        lines.append(
            f"\n(unmapped picks: {len(poll.unmatched)} — "
            f"{', '.join(p.full_name for p in poll.unmatched[:5])})"
        )
    return "\n".join(lines)


def _player_points(p: dict):
    return p.get("projected_points") or p.get("projected_season_points")


def _taxi_names(league_id: Optional[str], my_user_id: Optional[str]) -> List[str]:
    """The user's taxi-squad player names — protected from drop suggestions.

    RR-1 (MANTIS 2026-07-11): taxi players were suggested as drops. Fail-open:
    any Sleeper hiccup returns an empty list rather than blocking the report.
    """
    if not league_id or not my_user_id:
        return []
    try:
        from src.sleeper_player_map import load_sleeper_players

        rosters = sleeper_http.get_league_rosters(league_id)
        mine = next(
            (
                r
                for r in rosters
                if isinstance(r, dict) and str(r.get("owner_id")) == str(my_user_id)
            ),
            None,
        )
        taxi_ids = [str(pid) for pid in (mine or {}).get("taxi") or []]
        if not taxi_ids:
            return []
        registry = load_sleeper_players()
        names = []
        for pid in taxi_ids:
            p = registry.get(pid) or {}
            name = p.get("full_name") or (
                f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            )
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def _render_roster_report(
    engine: LiveDraftEngine,
    roster_format: str,
    as_json: bool,
    roster_positions=None,
    protected_names: Optional[List[str]] = None,
) -> str:
    """Render optimal starting lineup + drop candidates for the user's roster."""
    roster = engine.my_full_roster()
    lineup = optimal_lineup(roster, roster_format, roster_positions=roster_positions)
    drops = drop_candidates(
        roster,
        roster_format,
        top_n=5,
        roster_positions=roster_positions,
        protected_names=protected_names,
    )

    if as_json:
        return json.dumps(
            {
                "roster_size": len(roster),
                "starters": {
                    slot: [
                        {
                            "player_name": p.get("player_name"),
                            "position": p.get("position"),
                            "points": _player_points(p),
                        }
                        for p in players
                    ]
                    for slot, players in lineup["starters"].items()
                },
                "bench": [
                    {"player_name": p.get("player_name"), "position": p.get("position")}
                    for p in lineup["bench"]
                ],
                "drop_candidates": [
                    {
                        "player_name": d["player"].get("player_name"),
                        "position": d["player"].get("position"),
                        "value": d["value"],
                        "reason": d["reason"],
                    }
                    for d in drops
                ],
            },
            indent=2,
            default=str,
        )

    lines = [f"ROSTER REPORT — {len(roster)} players ({roster_format})", ""]
    if not roster:
        lines.append(
            "(no roster loaded — pass --league-id with --username/--my-user-id so "
            "your keepers load)"
        )
        return "\n".join(lines)
    lines.append("OPTIMAL STARTERS:")
    for slot, players in lineup["starters"].items():
        for p in players:
            lines.append(
                f"  {slot:<5} {str(p.get('player_name','')):<22} "
                f"{str(p.get('position','')):<3} {_player_points(p)}"
            )
    lines.append("\nDROP CANDIDATES (cut to roster a rookie):")
    for d in drops:
        pl = d["player"]
        lines.append(
            f"  {str(pl.get('player_name','')):<22} {str(pl.get('position','')):<3} "
            f"value={d['value']}  — {d['reason']}"
        )
    return "\n".join(lines)


def run_mock(
    engine: LiveDraftEngine,
    my_slot: int,
    n_teams: int,
    rounds: int,
    my_picks: List[str],
    roster_format: str,
    roster_positions,
    top_n: int = 8,
    draft_type: str = "snake",
) -> str:
    """Simulate a snake mock: opponents auto-pick by value, stop at the user's turn.

    Plays forward consuming ``my_picks`` for the user's slots; at the first user
    slot with no provided pick it stops and shows recommendations. When all the
    user's picks are provided through all rounds, it prints the final roster +
    optimal lineup.
    """
    board = engine.board
    log: List[str] = []
    my_iter = iter(my_picks)
    total = n_teams * rounds

    for p in range(1, total + 1):
        slot = LiveDraftEngine._slot_on_clock(p, n_teams, draft_type)
        rnd = (p - 1) // n_teams + 1
        if slot == my_slot:
            nxt = next(my_iter, None)
            if nxt is None:
                recs, reasoning = engine.recommendations(top_n=top_n)
                out = [
                    f"=== MOCK DRAFT — {n_teams} teams, {draft_type}, your slot "
                    f"{my_slot} ({roster_format}) ==="
                ]
                if log:
                    out.append("Recent picks:")
                    out += log[-min(len(log), n_teams) :]
                out.append(f"\n>>> PICK {p} (round {rnd}) — YOUR PICK <<<")
                out.append(f"Recommendations ({reasoning}):")
                for i, (_, r) in enumerate(recs.head(top_n).iterrows(), 1):
                    out.append(
                        f"  {i}. {str(r.get('player_name','')):<22} "
                        f"{str(r.get('position','')):<3} "
                        f"proj={round(float(r.get('projected_season_points',0) or 0),1)} "
                        f"vorp={r.get('vorp')} tier={r.get('value_tier','')}"
                    )
                roster = [pp.get("player_name") for pp in board.my_roster]
                out.append(
                    "Your roster: " + (", ".join(roster) if roster else "(empty)")
                )
                out.append(
                    "\nReply with the player to draft and I'll continue the mock."
                )
                return "\n".join(out)
            res = board.draft_player(nxt, by_me=True)
            nm = (res or {}).get("player_name", nxt)
            log.append(f"  P{p} R{rnd} slot{slot} YOU  -> {nm}")
        else:
            ba = engine.best_available(top_n=1)
            if ba is None or ba.empty:
                continue
            row = ba.iloc[0]
            key = row.get("player_id") or row.get("player_name")
            board.draft_player(str(key), by_me=False)
            log.append(
                f"  P{p} R{rnd} slot{slot} CPU  -> {row.get('player_name')} "
                f"({row.get('position')})"
            )

    roster = list(board.my_roster)
    lu = optimal_lineup(roster, roster_format, roster_positions=roster_positions)
    out = ["=== MOCK DRAFT COMPLETE ===", "", "Your optimal starting lineup:"]
    for slot, players in lu["starters"].items():
        for pp in players:
            out.append(
                f"  {slot:<6} {pp.get('player_name','')} ({pp.get('position','')})"
            )
    out.append(
        f"\nBench ({len(lu['bench'])}): "
        + ", ".join(pp.get("player_name", "") for pp in lu["bench"])
    )
    return "\n".join(out)


def run_auto_mock(
    projections: pd.DataFrame,
    adp_df: Optional[pd.DataFrame],
    n_teams: int,
    my_slot: int,
    draft_type: str,
    rounds: int,
    roster_format: str,
    roster_positions,
    scoring: str,
    league_name: Optional[str] = None,
    top_n: int = 8,
    randomness: int = 2,
) -> str:
    """Run a complete autonomous dress-rehearsal mock under the league's real rules.

    The co-pilot drafts the user's whole team itself (roster-need-aware VORP
    recommendations) while ADP-driven opponents fill the rest, honoring the
    league's draft type (snake/linear), team count, exact starting slots, and
    draftable positions. Returns a full report: every user pick with reasoning +
    runner-up alternatives, the final roster, the optimal lineup, and a grade.
    """
    rc = roster_config_from_positions(roster_positions)
    elig = draftable_positions(rc)
    enriched = compute_value_scores(projections, adp_df)
    if "position" in enriched.columns:
        enriched = enriched[enriched["position"].isin(elig)].reset_index(drop=True)
    board = DraftBoard(
        enriched, roster_format=roster_format, n_teams=n_teams, roster_config=rc
    )
    advisor = DraftAdvisor(board, scoring_format=scoring)
    sim = MockDraftSimulator(
        board,
        user_pick=my_slot,
        n_teams=n_teams,
        randomness=randomness,
        draft_type=draft_type,
    )
    result = sim.run_full_simulation(advisor, rounds=rounds)
    roster = list(board.my_roster)
    lineup = optimal_lineup(roster, roster_format, roster_positions=roster_positions)

    slot_lbl = ", ".join(str(s) for s in (roster_positions or [])) or roster_format
    out = [
        f"=== AUTONOMOUS MOCK — {league_name or 'league'} ===",
        f"{n_teams}-team {draft_type} {scoring} | {rounds} rounds | your slot {my_slot}",
        f"Starting slots: {slot_lbl}",
        f"Draftable positions: {', '.join(sorted(elig))}",
        f"Draft grade: {result['draft_grade']}  "
        f"(roster VORP {result['total_vorp']} vs ADP-baseline "
        f"{result['expected_vorp']}; {result['total_pts']} proj pts)",
        "",
        "YOUR PICKS (co-pilot reasoning):",
    ]
    for pk in result["picks"]:
        if pk["team"] != "YOU":
            continue
        alts = "; ".join(
            f"{a['player_name']} ({a['position']}, vorp {a['vorp']})"
            for a in pk.get("alternatives", [])[:3]
        )
        out.append(
            f"  R{pk['round']:<2} P{pk['pick']:<3} -> {pk['position']:<3} "
            f"{pk['player_name']:<22} vorp={pk.get('vorp')}"
        )
        if pk.get("reasoning"):
            out.append(f"        why: {pk['reasoning']}")
        if alts:
            out.append(f"        passed on: {alts}")

    out.append("\nOPTIMAL STARTING LINEUP:")
    for slot, players in lineup["starters"].items():
        for p in players:
            out.append(
                f"  {slot:<6} {str(p.get('player_name','')):<22} "
                f"{str(p.get('position','')):<3} {_player_points(p)}"
            )
    bench = lineup["bench"]
    out.append(
        f"\nBench ({len(bench)}): "
        + ", ".join(
            f"{p.get('player_name','')} ({p.get('position','')})" for p in bench
        )
    )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Live queue mode (continuously-updated draft queue)
# ---------------------------------------------------------------------------

# Per-stat Sleeper scoring for the three presets — lets a no-league mock draft be
# re-scored to its own format (a "std" draftboard must value RBs over receivers).
_FORMAT_SCORING = {
    "standard": {
        "pass_yd": 0.04,
        "pass_td": 4,
        "pass_int": -2,
        "rush_yd": 0.1,
        "rush_td": 6,
        "rec": 0.0,
        "rec_yd": 0.1,
        "rec_td": 6,
    },
    "half_ppr": {
        "pass_yd": 0.04,
        "pass_td": 4,
        "pass_int": -2,
        "rush_yd": 0.1,
        "rush_td": 6,
        "rec": 0.5,
        "rec_yd": 0.1,
        "rec_td": 6,
    },
    "ppr": {
        "pass_yd": 0.04,
        "pass_td": 4,
        "pass_int": -2,
        "rush_yd": 0.1,
        "rush_td": 6,
        "rec": 1.0,
        "rec_yd": 0.1,
        "rec_td": 6,
    },
}


def _preserve_kickers(df: pd.DataFrame) -> pd.DataFrame:
    """Restore kicker points after re-scoring (score_with_settings only sums
    offensive stats, which would zero kickers — their points are scoring-invariant)."""
    if "base_season_points" in df.columns and "position" in df.columns:
        is_k = df["position"].astype(str).str.upper() == "K"
        df.loc[is_k, "projected_season_points"] = df.loc[is_k, "base_season_points"]
        if "projected_points" in df.columns:
            df.loc[is_k, "projected_points"] = df.loc[is_k, "base_season_points"]
    return df


def _rescore_projections(
    projections: pd.DataFrame, scoring_format: str
) -> pd.DataFrame:
    """Re-score projections to a preset format (standard/half_ppr/ppr)."""
    ss = _FORMAT_SCORING.get(scoring_format)
    if not ss:
        return projections
    return _preserve_kickers(score_with_settings(projections, ss))


def _render_queue(queue: List[dict], turn, status: str) -> str:
    """Render a queue snapshot for the operator to mirror into their Sleeper queue."""
    lines = []
    if turn:
        flag = "  <<< YOUR TURN" if turn.is_my_turn else ""
        lines.append(
            f"On clock: pick {turn.on_clock_pick_no} (slot {turn.on_clock_slot})"
            f"{flag} | your next pick: {turn.my_next_pick_no}"
        )
    lines.append("QUEUE — keep your Sleeper queue matched to this (top = first):")
    for i, x in enumerate(queue, 1):
        pts = round(float(x.get("projected_season_points") or 0), 1)
        lines.append(
            f"  {i:>2}. {str(x.get('player_name','')):<22} "
            f"{str(x.get('position','')):<3} {str(x.get('team','') or ''):<3} "
            f"proj={pts} vorp={x.get('vorp')}"
        )
    return "\n".join(lines)


def run_live_queue(
    adapter,
    projections: pd.DataFrame,
    adp_df: Optional[pd.DataFrame],
    draft_id: str,
    league_id: Optional[str],
    my_user_id: Optional[str],
    my_slot: Optional[int],
    depth: int,
    interval: float,
) -> int:
    """Poll a live draft and continuously emit a need-aware queue that adapts as
    picks land — so the operator keeps their Sleeper queue synced and the platform
    auto-drafts well without per-pick reaction. Honors the draft's real scoring +
    slots (league custom settings when available, else the draftboard's format)."""
    # Defenses + obscure kickers have no projection row; their "not found" board
    # warnings are expected and would spam the live queue — silence them.
    logging.getLogger("src.draft_optimizer").setLevel(logging.ERROR)
    logging.getLogger("draft_optimizer").setLevel(logging.ERROR)
    logging.getLogger("src.sleeper_player_map").setLevel(logging.ERROR)
    draft = sleeper_http.get_draft(draft_id)
    settings = draft.get("settings") or {}
    n_teams = int(settings.get("teams") or 12)

    roster_config = None
    scored = projections
    label = ""
    if league_id:
        league = sleeper_http.get_league(league_id)
        roster_config = roster_config_from_positions(league.get("roster_positions"))
        ss = league.get("scoring_settings") or {}
        if ss:
            scored = _preserve_kickers(score_with_settings(projections, ss))
            label = f"{league.get('name', 'league')} custom"
    if roster_config is None:
        roster_config = roster_config_from_slots(settings)
    if not label:
        fmt = adapter.load_state(draft_id).scoring_format
        scored = _rescore_projections(projections, fmt)
        label = fmt

    elig = draftable_positions(roster_config)
    if "position" in scored.columns:
        scored = scored[scored["position"].isin(elig)].reset_index(drop=True)

    engine = LiveDraftEngine(
        adapter,
        scored,
        adp_df,
        my_user_id=my_user_id,
        my_slot=my_slot,
        roster_config=roster_config,
    )
    print(
        f"(live queue: {n_teams}-team {draft.get('type', '')} {label}; "
        f"slots {roster_config}; draftable {sorted(elig)})"
    )
    last_names: Optional[List[str]] = None
    try:
        while True:
            state = adapter.load_state(draft_id)
            poll = engine.update(state)
            queue = engine.advisor.build_queue(depth=depth) if engine.advisor else []
            names = [x.get("player_name") for x in queue]
            if names != last_names:
                last_names = names
                print(_render_queue(queue, poll.turn, state.status))
                print("-" * 56, flush=True)
            if state and state.status == "complete":
                print("Draft complete.")
                return 0
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Live draft co-pilot (Sleeper).")
    p.add_argument("--platform", default="sleeper", choices=sorted(_ADAPTERS))
    p.add_argument("--username", help="Sleeper username (resolves the active draft)")
    p.add_argument("--draft-id", help="Explicit draft id (skips resolution)")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument(
        "--scoring", default="half_ppr", choices=["ppr", "half_ppr", "standard"]
    )
    p.add_argument("--roster-format", default="standard")
    p.add_argument("--my-slot", type=int, help="Your draft slot (1-indexed)")
    p.add_argument("--my-user-id", help="Your Sleeper user_id (auto-derives slot)")
    p.add_argument(
        "--league-id",
        help="League id for keeper leagues — pre-marks kept players off the board",
    )
    p.add_argument(
        "--roster-report",
        action="store_true",
        help="Print optimal lineup + drop candidates for your roster (keepers + picks)",
    )
    p.add_argument("--projections-file", help="CSV of projections (else generated)")
    p.add_argument("--adp-file", help="CSV of ADP (default data/adp_latest.csv)")
    p.add_argument("--top", type=int, default=8, help="Number of recommendations")
    p.add_argument("--watch", action="store_true", help="Poll until the draft ends")
    p.add_argument(
        "--queue",
        action="store_true",
        help="Live queue mode — continuously emit a need-aware queue to mirror "
        "into your Sleeper queue (beats reacting on a 120s clock)",
    )
    p.add_argument("--queue-depth", type=int, default=12, help="Queue length")
    p.add_argument("--interval", type=float, default=3.0, help="Poll seconds")
    p.add_argument("--json", action="store_true", help="Emit JSON snapshots")
    p.add_argument("--manual", action="store_true", help="Manual pick entry (D-09)")
    p.add_argument("--teams", type=int, default=12, help="Teams (manual/mock mode)")
    p.add_argument(
        "--add-pick",
        action="append",
        default=[],
        help="Manual pick by player name (repeatable)",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="Simulated mock draft — opponents auto-pick, stops at your turn",
    )
    p.add_argument(
        "--auto",
        action="store_true",
        help="With --mock: co-pilot drafts your whole team itself (full dress "
        "rehearsal report), no interactive stops",
    )
    p.add_argument(
        "--draft-type",
        default="snake",
        choices=["snake", "linear"],
        help="Mock draft order (linear = Sleeper dynasty/rookie drafts)",
    )
    p.add_argument("--rounds", type=int, default=15, help="Mock draft rounds")
    p.add_argument(
        "--my-pick",
        action="append",
        default=[],
        help="Your mock picks so far, in order (repeatable)",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    # Quiet the per-pick "You drafted" INFO chatter during keeper preload.
    logging.getLogger("src.draft_optimizer").setLevel(logging.WARNING)
    logging.getLogger("draft_optimizer").setLevel(logging.WARNING)

    projections = load_projections(args.season, args.scoring, args.projections_file)
    if projections is None or projections.empty:
        print("ERROR: no projections. Run generate_projections.py --preseason first.")
        return 1
    adp_df = load_adp(args.adp_file)

    # Manual fallback — no adapter, operator-supplied picks.
    if args.manual:
        engine = LiveDraftEngine(
            _DummyAdapter(), projections, adp_df, my_slot=args.my_slot
        )
        state = build_manual_state(
            args.add_pick,
            projections,
            args.teams,
            "snake",
            args.scoring,
            args.roster_format,
            str(args.season),
        )
        poll = engine.update(state)
        print(render(engine, poll, args.top, args.json))
        return 0

    adapter = _ADAPTERS[args.platform]()

    # Resolve user_id (identifies YOUR keepers) from username if not given.
    my_user_id = args.my_user_id
    if not my_user_id and args.username and args.platform == "sleeper":
        my_user_id = (
            str(sleeper_http.get_user(args.username).get("user_id") or "") or None
        )

    draft_id = args.draft_id
    league_id = args.league_id

    # Resolve the draft (skipped for a roster report / mock, which only need the league).
    if not draft_id and not args.roster_report and not args.mock:
        if not args.username:
            print("ERROR: provide --draft-id or --username.")
            return 1
        res = adapter.resolve_draft(args.username, str(args.season))
        if not res.get("found"):
            print(f"No active draft found for '{args.username}' in {args.season}.")
            return 1
        draft_id = res["draft_id"]
        league_id = league_id or res.get("league_id")
        if len(res.get("candidates", [])) > 1:
            print(
                f"Multiple drafts found; using {draft_id}. Candidates: "
                f"{[c['draft_id'] for c in res['candidates']]}"
            )

    # Roster report / mock with no league id: fall back to the user's single league
    # so its custom scoring + slots + team count apply.
    if (
        (args.roster_report or args.mock)
        and not league_id
        and my_user_id
        and args.platform == "sleeper"
    ):
        league_id = _resolve_single_league(my_user_id, str(args.season))
    if args.roster_report and not league_id:
        print("ERROR: roster report needs --league-id (or a username with one league).")
        return 1

    # Live queue mode: own scoring/slot derivation + continuous queue loop.
    if args.queue:
        if not draft_id:
            print("ERROR: --queue needs --draft-id or --username with an active draft.")
            return 1
        return run_live_queue(
            adapter,
            projections,
            adp_df,
            draft_id,
            league_id,
            my_user_id,
            args.my_slot,
            args.queue_depth,
            args.interval,
        )

    # Apply the league's custom scoring + exact starting slots (Sleeper).
    roster_positions = None
    roster_format = args.roster_format
    n_teams = args.teams
    league_name = None
    scoring_label = args.scoring
    if league_id and args.platform == "sleeper":
        league = sleeper_http.get_league(league_id)
        ss = league.get("scoring_settings") or {}
        roster_positions = league.get("roster_positions") or None
        n_teams = league.get("total_rosters") or n_teams
        league_name = league.get("name")
        if "SUPER_FLEX" in (roster_positions or []):
            roster_format = "superflex"
        if ss:
            projections = score_with_settings(projections, ss)
            rec = ss.get("rec")
            if rec is not None:
                try:
                    rec = float(rec)
                    scoring_label = (
                        "full PPR (league)"
                        if rec >= 1.0
                        else "standard (league)" if rec <= 0.0 else "half-PPR (league)"
                    )
                except (TypeError, ValueError):
                    pass
            if not args.json:
                skipped = unmodeled_offense_keys(ss)
                note = f" (not modeled: {', '.join(skipped)})" if skipped else ""
                print(
                    f"(applied {league.get('name', 'league')} custom scoring + "
                    f"slots{note})"
                )

    engine = LiveDraftEngine(
        adapter,
        projections,
        adp_df,
        my_user_id=my_user_id,
        my_slot=args.my_slot,
        roster_config=roster_config_from_positions(roster_positions),
    )

    _keepers_loaded = {"done": False}

    def _poll_once() -> PollResult:
        state = (
            adapter.load_state(draft_id)
            if draft_id
            else _empty_state(roster_format, args.scoring, str(args.season))
        )
        poll = engine.update(state)
        # Keeper preload (once) — mark every league-rostered player off the board.
        if (
            not _keepers_loaded["done"]
            and league_id
            and hasattr(adapter, "get_keepers")
        ):
            n = engine.preload_keepers(adapter.get_keepers(league_id, my_user_id))
            _keepers_loaded["done"] = True
            if not args.json:
                print(f"(keeper league: marked {n} rostered players off the board)")
        return poll

    if args.mock:
        my_slot = args.my_slot or max(1, n_teams // 2)
        # --auto: co-pilot drafts your whole team and prints a full dress-rehearsal
        # report (no interactive stops), honoring the league's real draft order.
        if args.auto:
            print(
                run_auto_mock(
                    projections,
                    adp_df,
                    n_teams,
                    my_slot,
                    args.draft_type,
                    args.rounds,
                    roster_format,
                    roster_positions,
                    scoring_label,
                    league_name=league_name,
                    top_n=args.top,
                )
            )
            return 0
        # Startup-style mock: full player pool under the league's custom scoring +
        # slots (no keepers preloaded), so you see the co-pilot draft a fresh team.
        engine.update(_empty_state(roster_format, args.scoring, str(args.season)))
        print(
            run_mock(
                engine,
                my_slot,
                n_teams,
                args.rounds,
                args.my_pick,
                roster_format,
                roster_positions,
                top_n=args.top,
            )
        )
        return 0

    if args.roster_report:
        _poll_once()
        print(
            _render_roster_report(
                engine,
                roster_format,
                args.json,
                roster_positions,
                protected_names=_taxi_names(league_id, my_user_id),
            )
        )
        return 0

    if not args.watch:
        print(render(engine, _poll_once(), args.top, args.json))
        return 0

    # Watch loop — re-render only when the pick count advances.
    last_seen = -1
    try:
        while True:
            poll = _poll_once()
            state = engine.state
            if state and state.last_pick_no != last_seen:
                last_seen = state.last_pick_no
                print(render(engine, poll, args.top, args.json))
                print("-" * 60, flush=True)
            if state and state.status == "complete":
                print("Draft complete.")
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


class _DummyAdapter:
    """Minimal adapter for manual mode — maps picks but never hits a network."""

    platform = "manual"

    def resolve_draft(self, identifier, season, league_id=None):
        return {"found": False, "candidates": []}

    def load_state(self, draft_id):  # pragma: no cover - unused in manual mode
        raise NotImplementedError

    def map_picks(self, picks, projections_df):
        from src.sleeper_player_map import map_picks_to_projections

        return map_picks_to_projections(picks, projections_df, player_index={})


if __name__ == "__main__":
    raise SystemExit(main())
