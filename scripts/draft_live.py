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
import os
import sys
import time
from typing import List, Optional

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.draft_adapter import SleeperAdapter  # noqa: E402
from src.draft_models import DraftState, PickEvent  # noqa: E402
from src.live_draft_engine import LiveDraftEngine, PollResult  # noqa: E402
from src.nfl_data_integration import NFLDataFetcher  # noqa: E402
from src.projection_engine import generate_preseason_projections  # noqa: E402

_ADAPTERS = {"sleeper": SleeperAdapter}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_projections(
    season: int, scoring: str, projections_file: Optional[str]
) -> pd.DataFrame:
    """Load projections from a CSV file or generate preseason projections."""
    if projections_file and os.path.exists(projections_file):
        return pd.read_csv(projections_file)
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
            lines.append(
                f"  {str(r.get('player_name','')):<24} "
                f"{str(r.get('position','')):<3} {str(r.get('team','')):<3} "
                f"vorp={r.get('vorp','')}  tier={r.get('value_tier','')}"
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
    p.add_argument("--projections-file", help="CSV of projections (else generated)")
    p.add_argument("--adp-file", help="CSV of ADP (default data/adp_latest.csv)")
    p.add_argument("--top", type=int, default=8, help="Number of recommendations")
    p.add_argument("--watch", action="store_true", help="Poll until the draft ends")
    p.add_argument("--interval", type=float, default=3.0, help="Poll seconds")
    p.add_argument("--json", action="store_true", help="Emit JSON snapshots")
    p.add_argument("--manual", action="store_true", help="Manual pick entry (D-09)")
    p.add_argument("--teams", type=int, default=12, help="Teams (manual mode)")
    p.add_argument(
        "--add-pick",
        action="append",
        default=[],
        help="Manual pick by player name (repeatable)",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

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

    draft_id = args.draft_id
    if not draft_id:
        if not args.username:
            print("ERROR: provide --draft-id or --username.")
            return 1
        res = adapter.resolve_draft(args.username, str(args.season))
        if not res.get("found"):
            print(f"No active draft found for '{args.username}' in {args.season}.")
            return 1
        draft_id = res["draft_id"]
        if len(res.get("candidates", [])) > 1:
            print(
                f"Multiple drafts found; using {draft_id}. Candidates: "
                f"{[c['draft_id'] for c in res['candidates']]}"
            )

    engine = LiveDraftEngine(
        adapter, projections, adp_df, my_user_id=args.my_user_id, my_slot=args.my_slot
    )

    def _poll_once() -> PollResult:
        return engine.update(adapter.load_state(draft_id))

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
