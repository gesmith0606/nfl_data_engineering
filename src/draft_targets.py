"""Pre-draft target board — value flags keyed to YOUR pick slots.

The doctrine labels (VALUE / BUST / BREAKOUT / DEEP-SLEEPER) are already
computed by :mod:`src.draft_value`, but they were only ever rendered into a
flat report read hours before the draft and then thrown away. Two things were
missing on draft night (2026-08-28 ESPN mock):

* **Reachability.** A flat list of 40 flagged players does not say which of
  them can plausibly still be there when *you* pick. Snake slot 12 picks at
  12, 13, 36, 37, 60, 61 ... and a VALUE tag on a player with ADP 20 is
  useless at pick 36.
* **Personal judgment.** The model is news-blind by construction — Sleeper's
  roster status carries no "Suspended", so a pending legal or holdout
  situation is invisible (see ``draft_value.load_roster_status``). A hand
  maintained watchlist is the only place that knowledge can live.

This module supplies both, and is imported by the live co-pilot so the flags
show up while you are on the clock rather than in a document you read earlier.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

MY_GUYS_PATH = os.path.join("data", "draft", "my_guys.txt")

# How far past a pick an ADP can sit and still be "reachable" there. A player
# going ~a round early is the normal noise in any room; beyond that, planning
# around him is wishful.
DEFAULT_REACH_WINDOW = 12


def _name_key(name) -> str:
    """Suffix/punctuation-blind key, mirroring ``draft_optimizer.name_key``.

    Duplicated deliberately: this module must import cleanly with no pandas
    board or config loaded, so the CLI can lint a watchlist on its own.
    """
    cleaned = re.sub(r"[^a-z0-9\s]", "", str(name or "").lower())
    return " ".join(
        t for t in cleaned.split() if t not in {"jr", "sr", "ii", "iii", "iv", "v"}
    )


def load_my_guys(path: str = MY_GUYS_PATH) -> List[str]:
    """Target names from the watchlist (see :func:`load_watchlist`)."""
    return load_watchlist(path)["targets"]


def load_watchlist(path: str = MY_GUYS_PATH) -> Dict[str, List[str]]:
    """Read the personal watchlist: one player per line, ``#`` comments.

    A leading ``-`` marks a FADE rather than a target. Both matter live and
    they must not render the same way — a fade shown as "MY GUY" reads as a
    recommendation, which is the opposite of the intent.

    Missing file is not an error: most leagues will not have one, and a draft
    must never fail because a convenience list is absent.

    Args:
        path: Watchlist file. Defaults to ``data/draft/my_guys.txt``.

    Returns:
        ``{"targets": [...], "fades": [...]}`` of suffix-blind name keys,
        de-duplicated, in file order.
    """
    out: Dict[str, List[str]] = {"targets": [], "fades": []}
    if not os.path.exists(path):
        logger.info("no watchlist at %s — MY GUY / AVOID tagging disabled", path)
        return out
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            bucket = "targets"
            if line.startswith("-"):
                bucket, line = "fades", line[1:].strip()
            key = _name_key(line)
            if key and key not in out[bucket]:
                out[bucket].append(key)
    return out


def my_pick_numbers(
    slot: int, n_teams: int, rounds: int, draft_type: str = "snake"
) -> List[int]:
    """Overall pick numbers belonging to ``slot``.

    Args:
        slot: 1-indexed draft slot.
        n_teams: Teams in the league.
        rounds: Rounds in the draft.
        draft_type: ``"snake"`` (default) or ``"linear"``.

    Returns:
        Ascending overall pick numbers, e.g. slot 12 of a 12-team snake ->
        ``[12, 13, 36, 37, 60, 61, ...]``.
    """
    if slot < 1 or n_teams < 1 or rounds < 1 or slot > n_teams:
        return []
    picks = []
    for rnd in range(1, rounds + 1):
        if draft_type == "linear" or rnd % 2 == 1:
            picks.append((rnd - 1) * n_teams + slot)
        else:
            picks.append((rnd - 1) * n_teams + (n_teams - slot + 1))
    return sorted(picks)


def _labels_for(
    row: pd.Series, my_guys: Sequence[str], fades: Sequence[str] = ()
) -> List[str]:
    """Short tags for one board row, most decision-relevant first."""
    tags = []
    key = _name_key(row.get("player_name"))
    if key in fades:
        tags.append("AVOID")  # a veto: never shown alongside MY GUY
    elif key in my_guys:
        tags.append("MY GUY")
    # ADVISORY keyword news (draft_value.load_news_risk): "NEWS:suspension" —
    # verify before drafting, but it never suppresses the other tags.
    news = row.get("news_risk")
    if news is not None and not pd.isna(news) and str(news):
        tags.append(f"NEWS:{str(news).split()[0]}")
    if bool(row.get("flag_bust")):
        tags.append("BUST")
    if bool(row.get("flag_value")):
        tags.append("VALUE")
    if bool(row.get("flag_breakout")):
        tags.append("BREAKOUT")
    if bool(row.get("flag_deep_sleeper")):
        tags.append("SLEEPER")
    return tags


def tag_players(
    board: pd.DataFrame,
    my_guys: Optional[Sequence[str]] = None,
    fades: Optional[Sequence[str]] = None,
) -> Dict[str, List[str]]:
    """Map name key -> flag tags, for O(1) lookup during a live draft.

    Args:
        board: Labeled board from ``draft_value.label_board``.
        my_guys: Watchlist keys; loaded from disk when omitted.

    Returns:
        ``{name_key: ["MY GUY", "VALUE", ...]}``, omitting untagged players.
    """
    wl = (
        load_watchlist()
        if my_guys is None and fades is None
        else {"targets": [], "fades": []}
    )
    guys = list(my_guys) if my_guys is not None else wl["targets"]
    fades = list(fades) if fades is not None else wl["fades"]
    out: Dict[str, List[str]] = {}
    if board is None or board.empty:
        # A watchlist must still tag even with no labeled board available.
        out = {g: ["MY GUY"] for g in guys}
        for f in fades:
            out.setdefault(f, []).insert(0, "AVOID")
        return out
    for _, row in board.iterrows():
        tags = _labels_for(row, guys, fades)
        if tags:
            out[_name_key(row.get("player_name"))] = tags
    for g in guys:
        if g not in fades:
            out.setdefault(g, ["MY GUY"])
    for f in fades:
        out.setdefault(f, ["AVOID"])
    return out


def reachable_at(
    board: pd.DataFrame, pick_no: int, window: int = DEFAULT_REACH_WINDOW
) -> pd.DataFrame:
    """Flagged players whose ADP puts them plausibly at ``pick_no``.

    A player is reachable when his ADP has not already passed by more than
    ``window`` (he may fall) and is not so far ahead that he would be a
    reach — bounded on both sides so each pick gets a distinct shortlist
    rather than the same top names repeated every round.

    Args:
        board: Labeled board with an ``adp_rank`` column.
        pick_no: Overall pick number.
        window: Tolerance in picks either side.

    Returns:
        Reachable rows, ADP order.
    """
    if board is None or board.empty or "adp_rank" not in board.columns:
        return pd.DataFrame()
    adp = pd.to_numeric(board["adp_rank"], errors="coerce")
    lo, hi = pick_no - window, pick_no + (window * 2)
    return (
        board[adp.between(lo, hi)]
        .assign(_adp=adp)
        .sort_values("_adp")
        .drop(columns="_adp")
    )


def build_target_sheet(
    board: pd.DataFrame,
    slot: int,
    n_teams: int,
    rounds: int,
    draft_type: str = "snake",
    my_guys: Optional[Sequence[str]] = None,
    fades: Optional[Sequence[str]] = None,
    window: int = DEFAULT_REACH_WINDOW,
    per_pick: int = 6,
) -> List[Dict]:
    """Per-pick shortlists of flagged players for one draft slot.

    Args:
        board: Labeled board from ``draft_value.label_board``.
        slot: Your 1-indexed draft slot.
        n_teams: League size.
        rounds: Draft rounds.
        draft_type: ``"snake"`` or ``"linear"``.
        my_guys: Watchlist keys; loaded from disk when omitted.
        window: Reachability tolerance, in picks.
        per_pick: Max players listed per pick.

    Returns:
        ``[{"pick": int, "round": int, "players": [{...}]}]`` in pick order.
    """
    wl = (
        load_watchlist()
        if my_guys is None and fades is None
        else {"targets": [], "fades": []}
    )
    guys = list(my_guys) if my_guys is not None else wl["targets"]
    fade_keys = list(fades) if fades is not None else wl["fades"]
    sheet = []
    for pick in my_pick_numbers(slot, n_teams, rounds, draft_type):
        rows = reachable_at(board, pick, window)
        players = []
        for _, row in rows.iterrows():
            tags = _labels_for(row, guys, fade_keys)
            if not tags:
                continue
            players.append(
                {
                    "player_name": row.get("player_name"),
                    "position": row.get("position"),
                    "team": row.get("recent_team", row.get("team")),
                    "adp_rank": row.get("adp_rank"),
                    "tags": tags,
                    "reasons": row.get("reasons", ""),
                }
            )
            if len(players) >= per_pick:
                break
        sheet.append(
            {"pick": pick, "round": ((pick - 1) // n_teams) + 1, "players": players}
        )
    return sheet


__all__ = [
    "MY_GUYS_PATH",
    "DEFAULT_REACH_WINDOW",
    "load_my_guys",
    "load_watchlist",
    "my_pick_numbers",
    "tag_players",
    "reachable_at",
    "build_target_sheet",
]
