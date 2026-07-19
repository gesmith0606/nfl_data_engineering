"""Draft Intel for Sleeper leagues -- manager draft tendencies from real
league-history pick data.

Walks a Sleeper league's history chain (``previous_league_id``) up to
``max_seasons`` back, pulls each season's completed draft (draft order +
picks) and the league's users, and derives per-manager tendencies from pick
data ONLY -- no historical ADP is used or needed, since the signal here is
"what does this person actually draft", not "was it a good pick".

All Sleeper reads go through ``src/sleeper_http.py`` (the D-01 single HTTP
entry point) and inherit its fail-open (D-06) contract: any network/HTTP
error returns ``{}``/``[]`` rather than raising, which this module treats as
"stop walking the chain here" -- a broken chain never raises, it just
analyzes fewer seasons.

Exports:
    build_league_draft_intel: Walk the chain and compute manager tendencies.
    get_cached_league_draft_intel: TTL-cached wrapper (draft-night polling).
    intel_to_bot_behavior: Map a manager's tendencies to a
        ``MockDraftSimulator(behavior=...)``-compatible dict.
"""

import logging
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

try:
    from sleeper_http import (
        get_draft_picks,
        get_drafts_for_league,
        get_league,
        get_league_users,
    )
except ImportError:  # pragma: no cover
    from src.sleeper_http import (
        get_draft_picks,
        get_drafts_for_league,
        get_league,
        get_league_users,
    )

logger = logging.getLogger(__name__)

# A manager taking QB/TE/K/DST in round 1 is the notable tendency -- RB/WR
# round-1 picks are the default meta and not worth flagging.
NOTABLE_FIRST_ROUND_POSITIONS = {"QB", "TE", "K", "DST"}
EARLY_ROUNDS = (1, 2, 3)

_CACHE_TTL_SECONDS = 300
_intel_cache: Dict[str, Tuple[float, dict]] = {}

_DEFAULT_BEHAVIOR: Dict[str, float] = {"run_factor": 1.5, "temperature": 3.0}


# ---------------------------------------------------------------------------
# League-history chain
# ---------------------------------------------------------------------------


def _walk_league_chain(league_id: str, max_seasons: int) -> List[dict]:
    """Follow ``previous_league_id`` up to ``max_seasons`` leagues back
    (inclusive of ``league_id`` itself). Stops (without raising) at the
    first missing/cyclic league.
    """
    chain: List[dict] = []
    current_id: Optional[str] = league_id
    seen = set()
    for _ in range(max(0, max_seasons)):
        if not current_id or current_id in seen:
            break
        seen.add(current_id)
        league = get_league(current_id)
        if not league:
            break
        chain.append(league)
        current_id = league.get("previous_league_id") or None
    return chain


def _display_name_map(league_id: str) -> Dict[str, dict]:
    users = get_league_users(league_id)
    out: Dict[str, dict] = {}
    for u in users:
        if not isinstance(u, dict):
            continue
        uid = str(u.get("user_id", ""))
        if not uid:
            continue
        out[uid] = {
            "display_name": u.get("display_name") or uid,
            "team_name": (u.get("metadata") or {}).get("team_name"),
        }
    return out


def _completed_drafts(league_id: str) -> List[dict]:
    drafts = get_drafts_for_league(league_id)
    return [d for d in drafts if isinstance(d, dict) and d.get("status") == "complete"]


def _pick_position(pick: dict) -> Optional[str]:
    meta = pick.get("metadata") or {}
    pos = meta.get("position")
    return str(pos).upper() if pos else None


def _picks_by_manager(draft_id: str) -> Dict[str, List[dict]]:
    picks = get_draft_picks(draft_id)
    by_manager: Dict[str, List[dict]] = defaultdict(list)
    for p in picks:
        if not isinstance(p, dict):
            continue
        uid = str(p.get("picked_by") or "")
        if not uid:
            continue
        by_manager[uid].append(p)
    return by_manager


# ---------------------------------------------------------------------------
# Tendency math (pick data only -- no ADP)
# ---------------------------------------------------------------------------


def _round_positions(picks: List[dict]) -> Dict[int, str]:
    """First pick of each round for one manager in one draft (round -> position)."""
    picks_sorted = sorted(
        picks, key=lambda p: p.get("pick_no", p.get("round", 0) * 1000) or 0
    )
    round_pos: Dict[int, str] = {}
    for p in picks_sorted:
        rnd, pos = p.get("round"), _pick_position(p)
        if rnd is None or pos is None:
            continue
        round_pos.setdefault(int(rnd), pos)
    return round_pos


def _compute_manager_tendencies(season_picks: Dict[str, List[dict]]) -> dict:
    """Tendencies for one manager across their season -> picks map.

    Returns a dict with typed fields plus a ``summary`` key (human sentences)
    that callers should pop off before handing the rest to a typed schema.
    """
    first_round_by_season: Dict[str, Optional[str]] = {}
    opens_rb_rb_seasons: List[str] = []
    wr_heavy_early_seasons: List[str] = []
    qb_by_round_seasons: Dict[str, Optional[int]] = {}
    position_counts_rounds_1_3: Counter = Counter()
    total_early_picks = 0

    for season, picks in season_picks.items():
        round_pos = _round_positions(picks)
        first_round_by_season[season] = round_pos.get(1)

        if round_pos.get(1) == "RB" and round_pos.get(2) == "RB":
            opens_rb_rb_seasons.append(season)

        early = [round_pos[r] for r in EARLY_ROUNDS if r in round_pos]
        position_counts_rounds_1_3.update(early)
        total_early_picks += len(early)
        if early.count("WR") >= 2:
            wr_heavy_early_seasons.append(season)

        qb_round = next(
            (r for r in sorted(round_pos) if round_pos[r] == "QB"), None
        )
        qb_by_round_seasons[season] = qb_round

    n_seasons = len(season_picks) or 1
    fr_values = [v for v in first_round_by_season.values() if v]
    modal_first_round_position = (
        Counter(fr_values).most_common(1)[0][0] if fr_values else None
    )

    early_position_shares = (
        {
            pos: round(count / total_early_picks, 3)
            for pos, count in position_counts_rounds_1_3.items()
        }
        if total_early_picks
        else {}
    )

    summary: List[str] = []
    if modal_first_round_position and modal_first_round_position in (
        NOTABLE_FIRST_ROUND_POSITIONS
    ):
        n_hit = sum(1 for v in fr_values if v == modal_first_round_position)
        summary.append(
            f"Takes a {modal_first_round_position} in round 1 in "
            f"{n_hit} of {n_seasons} drafts."
        )
    qb4_hits = sum(
        1 for r in qb_by_round_seasons.values() if r is not None and r <= 4
    )
    if qb4_hits:
        summary.append(f"Takes a QB by round 4 in {qb4_hits} of {n_seasons} drafts.")
    if opens_rb_rb_seasons:
        summary.append(
            f"Opens RB-RB in {len(opens_rb_rb_seasons)} of {n_seasons} drafts."
        )
    if wr_heavy_early_seasons:
        summary.append(
            "WR-heavy early (2+ WR in first 3 rounds) in "
            f"{len(wr_heavy_early_seasons)} of {n_seasons} drafts."
        )
    if not summary:
        summary.append("Not enough draft history to identify a clear tendency.")

    return {
        "first_round_by_season": first_round_by_season,
        "modal_first_round_position": modal_first_round_position,
        "opens_rb_rb_seasons": opens_rb_rb_seasons,
        "wr_heavy_early_seasons": wr_heavy_early_seasons,
        "position_counts_rounds_1_3": dict(position_counts_rounds_1_3),
        "early_position_shares": early_position_shares,
        "qb_by_round_seasons": qb_by_round_seasons,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_league_draft_intel(league_id: str, max_seasons: int = 3) -> dict:
    """Build the full draft-intel payload for a league's history chain.

    Args:
        league_id: Sleeper league_id to start the chain from.
        max_seasons: Max number of leagues (including ``league_id`` itself)
            to walk back via ``previous_league_id``.

    Returns:
        Dict with ``league_id``, ``seasons_analyzed`` (count of leagues in
        the chain that had a completed draft with picks), and ``managers``
        (list of ``{user_id, display_name, team_name, tendencies, summary}``).
        Fail-open: any missing/broken chain link yields fewer seasons
        analyzed, never a raised exception; a fully broken chain returns
        ``seasons_analyzed=0, managers=[]``.
    """
    empty = {"league_id": league_id, "seasons_analyzed": 0, "managers": []}
    if not league_id:
        return empty

    try:
        chain = _walk_league_chain(league_id, max_seasons)
    except Exception as exc:  # pragma: no cover -- defensive, D-06
        logger.warning("Draft intel: chain walk failed for %s: %s", league_id, exc)
        return empty
    if not chain:
        return empty

    try:
        display_map = _display_name_map(str(chain[0].get("league_id") or league_id))
    except Exception as exc:  # pragma: no cover -- defensive, D-06
        logger.warning("Draft intel: user lookup failed for %s: %s", league_id, exc)
        display_map = {}

    manager_season_picks: Dict[str, Dict[str, List[dict]]] = defaultdict(dict)
    seasons_analyzed = 0

    for league in chain:
        lid = league.get("league_id")
        season_label = str(league.get("season") or lid)
        if not lid:
            continue
        try:
            drafts = _completed_drafts(str(lid))
        except Exception as exc:  # pragma: no cover -- defensive, D-06
            logger.warning("Draft intel: drafts fetch failed for %s: %s", lid, exc)
            continue
        if not drafts:
            continue
        draft_id = drafts[0].get("draft_id")
        if not draft_id:
            continue
        try:
            by_manager = _picks_by_manager(str(draft_id))
        except Exception as exc:  # pragma: no cover -- defensive, D-06
            logger.warning("Draft intel: picks fetch failed for %s: %s", draft_id, exc)
            continue
        if not by_manager:
            continue
        seasons_analyzed += 1
        for uid, picks in by_manager.items():
            manager_season_picks[uid][season_label] = picks

    managers: List[dict] = []
    for uid, season_picks in manager_season_picks.items():
        tendencies = _compute_manager_tendencies(season_picks)
        summary = tendencies.pop("summary")
        meta = display_map.get(uid, {})
        managers.append(
            {
                "user_id": uid,
                "display_name": meta.get("display_name", uid),
                "team_name": meta.get("team_name"),
                "tendencies": tendencies,
                "summary": summary,
            }
        )

    return {
        "league_id": league_id,
        "seasons_analyzed": seasons_analyzed,
        "managers": managers,
    }


def get_cached_league_draft_intel(league_id: str, max_seasons: int = 3) -> dict:
    """TTL-cached wrapper over :func:`build_league_draft_intel`.

    Draft-night / draft-prep polling would otherwise re-walk the whole
    multi-season league-history chain on every request.
    """
    key = f"{league_id}:{max_seasons}"
    now = time.monotonic()
    cached = _intel_cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]
    result = build_league_draft_intel(league_id, max_seasons)
    _intel_cache[key] = (now + _CACHE_TTL_SECONDS, result)
    return result


# ---------------------------------------------------------------------------
# MockDraftSimulator behavior mapping
# ---------------------------------------------------------------------------


def intel_to_bot_behavior(tendencies: Optional[dict]) -> Dict[str, float]:
    """Map one manager's tendencies to a ``MockDraftSimulator(behavior=...)``
    -compatible dict (``run_factor``/``temperature`` -- see
    ``src.draft_optimizer.MockDraftSimulator.__init__``).

    A manager with a highly consistent opening (opens RB-RB every season on
    record) drafts predictably -- lower ``temperature`` pulls the simulated
    bot's picks closer to strict ADP order. A manager who has repeatedly
    piled onto WR runs early amplifies ``run_factor``, mirroring a real
    "run chaser". Falls back to :class:`MockDraftSimulator`'s own defaults
    when there isn't enough history to say anything (empty/None input).
    """
    if not tendencies:
        return dict(_DEFAULT_BEHAVIOR)

    first_round_by_season = tendencies.get("first_round_by_season") or {}
    n_seasons = len(first_round_by_season) or 1

    opens_rb_rb = tendencies.get("opens_rb_rb_seasons") or []
    wr_heavy = tendencies.get("wr_heavy_early_seasons") or []

    consistency = len(opens_rb_rb) / n_seasons
    run_share = len(wr_heavy) / n_seasons

    return {
        "temperature": round(max(1.0, 3.0 - 2.0 * consistency), 2),
        "run_factor": round(1.5 + 1.0 * run_share, 2),
    }


__all__ = [
    "NOTABLE_FIRST_ROUND_POSITIONS",
    "EARLY_ROUNDS",
    "build_league_draft_intel",
    "get_cached_league_draft_intel",
    "intel_to_bot_behavior",
]
