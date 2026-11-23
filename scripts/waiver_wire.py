#!/usr/bin/env python3
"""Weekly waiver-wire report: free agents on two projection sources + last week's actuals.

    python scripts/waiver_wire.py --league mantis
    python scripts/waiver_wire.py --league la_liga --roster-file data/draft/la_liga_2026_roster.txt

Sleeper leagues: every roster in the league is pulled live, so the free-agent pool is
exact and both sources are scored under the league's own ``scoring_settings``.
ESPN/Yahoo leagues have no roster reader yet: pass ``--roster-file`` (one name per
line) for YOUR roster. Other teams' rosters are unknown, so each candidate carries the
room ADP rank and an ``FA?`` guess (undrafted by ADP) that you must verify on the site.

Columns: OURS = our weekly Gold projection, SLPR = Sleeper's weekly projection,
BLEND = mean of the two, LAST = last week's actual under the same scoring,
ADDS = Sleeper trending adds (48h, thousands), NEWS = Gold sentiment flags,
then the injury status: the official NFL report for the week when posted
(game status + practice trail), else Sleeper's tag labelled with where it came
from (``from wk2 game, not a wk3 ruling``) and how old Sleeper's news is.
Drop candidates are the lowest-BLEND bench players (K/DEF are not scored here).
Dynasty presets (``"dynasty": True``, e.g. Mantis) add DYN = FantasyCalc market value
and AGE, a "dynasty targets" list, and sort my roster by value instead of BLEND.
Run ``scripts/league_context.py --league <key>`` first (FAAB, bid levels, our churn).
"""

from __future__ import annotations

import argparse
import builtins
import datetime as dt
import glob
import re
import subprocess
import time
import importlib.util
import json
import sys
from pathlib import Path
from typing import (
    AbstractSet,
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import (  # noqa: E402
    clearing_model,
    config,
    league_context,
    sleeper_http,
    waiver_rank,
    waiver_record,
)
from src.espn_league import PRO_TEAM_MAP  # noqa: E402
from src.lineup_setter import (  # noqa: E402
    SKILL_POSITIONS,
    build_id_maps,
    full_name_map,
    ours_by_sleeper_id,
    resolve_injury_status,
    roster_gsis_map,
    score_ours,
    score_sleeper_stats,
)
from src.sleeper_player_map import (  # noqa: E402
    _CACHE_PATH as _PLAYERS_CACHE,
    load_sleeper_players,
    normalize_name,
)
from src.waiver_verdicts import (  # noqa: E402
    NO_HELP,
    STARTS,
    BENCH_UP,
    DEPTH,
    drop_order,
    load_keepers,
    roster_baseline,
)
from src.waiver_verdicts import verdict as waiver_verdict  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "set_lineups", REPO_ROOT / "scripts" / "set_lineups.py"
)
set_lineups = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(set_lineups)  # type: ignore[union-attr]

GOLD = REPO_ROOT / "data" / "gold"
BRONZE = REPO_ROOT / "data" / "bronze"
ADP_FILES = {
    "espn": "adp_espn_half_ppr.csv",
    "yahoo": "adp_yahoo_feetball_half_ppr.csv",
}
TRENDING_URL = (
    "https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=48&limit=200"
)

# SCORING_CONFIGS vocabulary -> Sleeper scoring_settings vocabulary (ESPN/Yahoo leagues).
_TO_SLEEPER_KEYS = {
    "reception": "rec",
    "rush_yd": "rush_yd",
    "rec_yd": "rec_yd",
    "rush_td": "rush_td",
    "rec_td": "rec_td",
    "pass_yd": "pass_yd",
    "pass_td": "pass_td",
    "interception": "pass_int",
    "fumble_lost": "fum_lost",
}
_ACTUAL_COLS = {
    "passing_yards": "passing_yards",
    "passing_tds": "passing_tds",
    "interceptions": "interceptions",
    "rushing_yards": "rushing_yards",
    "rushing_tds": "rushing_tds",
    "receptions": "receptions",
    "receiving_yards": "receiving_yards",
    "receiving_tds": "receiving_tds",
}


def scoring_for(
    preset: Dict[str, Any], league: Optional[Dict[str, Any]]
) -> Dict[str, float]:
    if league and league.get("scoring_settings"):
        return league["scoring_settings"]
    base = config.SCORING_CONFIGS[preset["scoring_format"]]
    return {_TO_SLEEPER_KEYS[k]: v for k, v in base.items() if k in _TO_SLEEPER_KEYS}


def last_week_actuals(
    season: int, week: int, scoring: Dict[str, float]
) -> pd.DataFrame:
    files = sorted(
        glob.glob(str(BRONZE / "players" / "weekly" / f"season={season}" / "*.parquet"))
    )
    if not files:
        return pd.DataFrame()
    df = pd.read_parquet(files[-1])
    df = df[(df["week"] == week) & df["position"].isin(SKILL_POSITIONS)]
    if "player_display_name" in df.columns:
        df = df.rename(columns={"player_display_name": "player_name"})
    keep = ["player_id", "player_name", "position", "recent_team"] + list(_ACTUAL_COLS)
    return score_ours(df[[c for c in keep if c in df.columns]].copy(), scoring)


#: A practice trail that ENDS in full or limited participation after a DNP is
#: a player on his way back. Structured, published by the team, and available
#: every week -- unlike the news keyword "returning", which is produced by
#: pattern-matching article text and is only as good as the extractor.
_RECOVERING_TRAIL = ("LP", "FP")


def returning_from_practice(sleeper_id: Optional[str], ctx: Any) -> bool:
    """Is this player trending back INTO the lineup, per the official report?

    The ENDING tag -- "the role you are buying is about to vanish" -- used to
    rest entirely on a news flag. That flag comes from keyword extraction,
    which this session found to be running on rules while claiming to be
    Claude, so the most consequential signal on the board had the weakest
    provenance behind it.

    The same conclusion is available from structured data the report already
    loads: nflverse publishes a DNP/LP/FP practice status per day, collapsed
    into a trail. A trail that starts at DNP and ends at LP or FP is a player
    returning, stated by his own team. No API key, no language model.

    Returns False when there is no report line, which keeps the news path as
    the fallback rather than replacing it.
    """
    if not sleeper_id or ctx is None:
        return False
    gsis = (getattr(ctx, "gsis_by_sleeper", None) or {}).get(str(sleeper_id))
    if not gsis:
        return False
    report = (getattr(ctx, "reports", None) or {}).get(str(gsis))
    trail = tuple(getattr(report, "practice", ()) or ())
    if len(trail) < 2 or trail[-1] not in _RECOVERING_TRAIL:
        return False
    # Improving, not merely present: DNP -> LP -> FP counts, FP -> FP does not,
    # and LP -> DNP is going the wrong way.
    order = {"DNP": 0, "LP": 1, "FP": 2}
    return order.get(trail[-1], 0) > order.get(trail[0], 0)


def snap_trend(
    season: int, week: int, by_name: Mapping[Any, str]
) -> Dict[str, Tuple[int, int]]:
    """``sleeper_id -> (latest snap %, change vs the week before)``.

    The one question the report could not answer was the one George asked
    first -- "isn't he a backup?". Projections and trending adds both say a
    player is interesting; neither says he is on the field. A rising snap
    share is the difference between a role and a rumour, and it is also the
    signal the young-drop rule leans on.

    Reads the committed Bronze snap counts, which key on ``player`` (a name,
    not an id) and carry ``offense_pct`` -- not ``snap_pct``. Returns ``{}``
    when the files are absent so the column simply does not render.
    """
    out: Dict[str, Tuple[int, int]] = {}
    pct: Dict[int, Dict[str, float]] = {}
    for wk in (week - 1, week - 2):
        if wk < 1:
            continue
        files = sorted(
            glob.glob(
                str(
                    BRONZE
                    / "players"
                    / "snaps"
                    / f"season={season}"
                    / f"week={wk}"
                    / "*.parquet"
                )
            )
        )
        if not files:
            continue
        df = pd.read_parquet(files[-1])
        if "offense_pct" not in df.columns or "player" not in df.columns:
            continue
        pct[wk] = {
            normalize_name(str(n)): float(v)
            for n, v in zip(df["player"], df["offense_pct"])
            if pd.notna(v)
        }
    latest = pct.get(week - 1) or {}
    prior = pct.get(week - 2) or {}
    for (norm, _pos), sid in by_name.items():
        if norm in latest:
            now = round(latest[norm] * 100)
            was = round(prior.get(norm, latest[norm]) * 100)
            out[sid] = (now, now - was)
    return out


def adp_rank_map(platform: str) -> Dict[str, int]:
    path = REPO_ROOT / "data" / "adp" / ADP_FILES.get(platform, "")
    if not path.is_file():
        return {}
    df = pd.read_csv(path)
    return {
        normalize_name(str(n)): int(r)
        for n, r in zip(df["player_name"], df["adp_rank"])
    }


def roster_ids_from_file(path: Path, by_name: Dict[Any, str]) -> Set[str]:
    ids: Set[str] = set()
    for line in path.read_text().splitlines():
        name = line.split("#", 1)[0].strip()
        if not name:
            continue
        norm = normalize_name(name)
        hit = next((sid for (n, _p), sid in by_name.items() if n == norm), None)
        if hit is None:
            print(f"WARN: roster name not in Sleeper registry: {name}")
        else:
            ids.add(hit)
    return ids


#: One league's completed waiver/free-agent moves, keyed by Sleeper player id.
PlayerMoves = Dict[str, List[Dict[str, Any]]]


def fetch_league_transactions(league_id: str, through_leg: int) -> List[Dict[str, Any]]:
    """Every completed transaction in the league, legs 1..``through_leg``.

    Legs that fail to load are skipped: a thin history still prices most
    claims, and a waiver report that dies on one bad HTTP call is useless.
    """
    rows: List[Dict[str, Any]] = []
    for leg in range(1, max(1, through_leg) + 1):
        try:
            got = sleeper_http.fetch_sleeper_json(
                f"https://api.sleeper.app/v1/league/{league_id}/transactions/{leg}"
            )
        except Exception:  # noqa: BLE001 — a missing leg is not a failure
            continue
        for t in got or []:
            if isinstance(t, dict) and t.get("status") == "complete":
                t = dict(t)
                t["_leg"] = leg
                rows.append(t)
    return rows


def league_player_moves(
    league_id: str, through_leg: int, rows: Optional[List[Dict[str, Any]]] = None
) -> PlayerMoves:
    """What this league has already paid for each player, from its own log.

    A room's median winning bid is the price of a *contested* player. Pricing
    a specific claim off it overpays for anyone the room does not want: in
    week 7 2026 Jalon Daniels had been bought for $1, cut the week he won the
    starting job, and left unrostered through three 13-point starts — the
    league had already priced him, and the median said $12.

    Args:
        league_id: Numeric Sleeper league id.
        through_leg: Highest leg (week) to read, inclusive.
        rows: Pre-fetched transactions, to avoid a second walk.

    Returns:
        ``sleeper_player_id -> [{"leg", "bid", "kind"}]`` oldest first, where
        ``kind`` is ``"add"`` or ``"drop"``.
    """
    if rows is None:
        rows = fetch_league_transactions(league_id, through_leg)
    out: PlayerMoves = {}
    for t in rows:
        bid = (t.get("settings") or {}).get("waiver_bid")
        leg = int(t.get("_leg") or 0)
        for kind in ("add", "drop"):
            for pid, rid in ((t.get(f"{kind}s") or {}) or {}).items():
                out.setdefault(str(pid), []).append(
                    {"leg": leg, "bid": bid, "kind": kind, "by": str(rid)}
                )
    for moves in out.values():
        moves.sort(key=lambda m: m["leg"])
    return out


def team_bid_stats(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """``roster_id -> {n, median, max}`` of that team's winning bids.

    Remaining budget is not willingness to spend. In La Liga through week 7
    2026 the three teams with the fullest budgets had spent $0, $0 and $1 all
    season — treating them as threats is what turned a $10 claim into a $22
    one. A rival's own bid history is the better read.
    """
    by_team: Dict[str, List[int]] = {}
    for t in rows:
        bid = (t.get("settings") or {}).get("waiver_bid")
        if not bid:
            continue
        for rid in t.get("roster_ids") or []:
            if (t.get("adds") or {}) and rid in set((t.get("adds") or {}).values()):
                by_team.setdefault(str(rid), []).append(int(bid))
    out: Dict[str, Dict[str, Any]] = {}
    for rid, bids in by_team.items():
        bids.sort()
        out[rid] = {
            "n": len(bids),
            "median": bids[len(bids) // 2],
            "max": bids[-1],
        }
    return out


#: One browser per run. Playwright's sync API cannot nest, so a second
#: FantasyBrowser() while the first is live raises "Sync API inside the
#: asyncio loop" -- which is exactly what happened on Yahoo: yahoo_live_pools
#: opened one, and the demand history then could never load. Every site read
#: here goes through this.
_BROWSER: Any = None


def shared_browser() -> Any:
    """The run's single FantasyBrowser, created on first use."""
    global _BROWSER
    if _BROWSER is None:
        from src.fantasy_browser import FantasyBrowser

        _BROWSER = FantasyBrowser()
    return _BROWSER


def espn_player_moves(
    league_id: str,
    season: int,
    team_id: int,
    through_period: int,
    registry: Mapping[str, Any],
    by_name: Mapping[Any, str],
) -> Tuple[PlayerMoves, int, Mapping[str, Any], "pd.DataFrame"]:
    """The same demand history as :func:`league_player_moves`, for an ESPN league.

    ESPN ids are as sparse in the Sleeper registry as gsis ids (210 of 841
    active skill players carry one), so this goes through
    ``league_context.espn_context``, which already falls back to ESPN's own
    names, and re-keys those names onto Sleeper ids.

    Reads through the logged-in claims profile, so it needs no ESPN cookies.
    Returns an empty map on any failure: the demand column is an aid, and the
    report is still worth printing without it.

    Args:
        league_id: Numeric ESPN league id.
        season: Season year.
        team_id: My ESPN team id.
        through_period: Highest ``scoringPeriodId`` to walk, inclusive.
        registry: Sleeper player registry.
        by_name: ``(normalised_name, position) -> sleeper_id`` from this report.

    Returns:
        ``(sleeper_player_id -> [{"leg", "bid", "kind"}] oldest first, our
        remaining FAAB, the raw league payload, the transaction frame)``. The
        last two let the caller build the rival model without a second fetch.
        ``({}, 0, {}, empty frame)`` on any failure.
    """
    try:
        from src import waiver_sites as ws

        page = ws.site_page(shared_browser(), "espn", str(league_id), team_id)
        payload = ws.espn_fetch_league(
            page, season, str(league_id), ["mSettings", "mTeam", "mRoster"]
        )
        payload["transactions"] = [
            t
            for wk in range(0, through_period + 1)
            for t in ws.espn_fetch_league(
                page, season, str(league_id), ["mTransactions2"], wk
            ).get("transactions")
            or []
        ]
        _teams, tx = league_context.espn_context(payload, team_id, registry)
        # mSettings + mTeam are already in this payload, so our remaining FAAB
        # costs no second page. It matters because `bid` is gated on
        # `moves and my_faab`, and my_faab was only ever filled in the Sleeper
        # branch -- the computed bid silently never ran on the two leagues we
        # can actually file claims in.
        faab = _espn_faab_left(payload, team_id)
    except Exception as exc:  # noqa: BLE001 — the column is an aid, not a gate
        print(f"WARN: ESPN demand history unavailable ({exc})")
        return {}, 0, {}, pd.DataFrame()

    return moves_from_tx(tx, by_name), faab, payload, tx


def _espn_faab_left(payload: Mapping[str, Any], team_id: int) -> int:
    """Our remaining FAAB from an ESPN league payload, 0 when unknown.

    0 leaves :func:`suggest_bid` switched off rather than pricing against a
    budget we invented.
    """
    budget = ((payload.get("settings") or {}).get("acquisitionSettings") or {}).get(
        "acquisitionBudget"
    )
    if budget is None:
        return 0
    spent = next(
        (
            (t.get("transactionCounter") or {}).get("acquisitionBudgetSpent") or 0
            for t in payload.get("teams") or []
            if int(t.get("id") or -1) == int(team_id)
        ),
        0,
    )
    return max(0, int(budget) - int(spent))


#: ESPN ``defaultPositionId`` -> our position codes. Only the skill spots
#: matter; everything else is irrelevant to a rival-thinness test.
_ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}

#: ESPN ``injuryStatus`` values that mean the player cannot be counted as
#: usable depth this week. Mirrors BLOCKING_STATUSES on the Sleeper side.
_ESPN_BLOCKED = frozenset(
    {"OUT", "DOUBTFUL", "INJURY_RESERVE", "SUSPENSION", "NON_FOOTBALL_INJURY"}
)


def espn_rivals(
    payload: Mapping[str, Any],
    my_team_id: int,
    need: Mapping[str, int],
    bids_by_team: Mapping[str, List[int]],
    room_median: int,
    playing: Optional[AbstractSet[str]] = None,
) -> Dict[str, List[int]]:
    """Which ESPN rivals cannot field a position this week AND can outbid us.

    The Sleeper branch has had this since the bid model shipped; ESPN had
    nothing, so every site-league bid fell to the room-median floor with a
    reason admitting no rival had been looked at. ESPN's own payload carries
    every team's roster, injury statuses and FAAB spent, so the same test is
    available -- it was simply never wired.

    "Credible" means the same three things it means on Sleeper: short of
    usable bodies at the position, holding at least the room's median bid,
    and having actually spent before (a team that never bids is not a threat
    however rich).

    Args:
        payload: ESPN league JSON with ``mSettings``, ``mTeam``, ``mRoster``.
        my_team_id: Our ESPN ``teamId``, excluded from the rivals.
        need: Required starters per position, from ``starters_required``.
        bids_by_team: ``team name -> winning bids``, keyed the way
            ``league_context.espn_context`` labels its transaction rows.
        room_median: The league's median winning bid.

    Returns:
        ``position -> [each credible rival's median bid]``.
    """
    budget = int(
        ((payload.get("settings") or {}).get("acquisitionSettings") or {}).get(
            "acquisitionBudget"
        )
        or 0
    )
    out: Dict[str, List[int]] = {}
    for team in payload.get("teams") or []:
        if int(team.get("id") or -1) == int(my_team_id):
            continue
        bids = sorted(bids_by_team.get(str(team.get("name") or "")) or [])
        if not bids:
            continue
        spent = int(
            (team.get("transactionCounter") or {}).get("acquisitionBudgetSpent") or 0
        )
        if budget and budget - spent < room_median:
            continue
        available: Dict[str, int] = {}
        for entry in (team.get("roster") or {}).get("entries") or []:
            player = (entry.get("playerPoolEntry") or {}).get("player") or {}
            pos = _ESPN_POS.get(int(player.get("defaultPositionId") or 0))
            status = str(
                entry.get("injuryStatus") or player.get("injuryStatus") or ""
            ).upper()
            if not pos or status in _ESPN_BLOCKED:
                continue
            if playing is not None:
                abbr = PRO_TEAM_MAP.get(player.get("proTeamId"))
                if abbr not in playing:
                    continue
            available[pos] = available.get(pos, 0) + 1
        median = bids[len(bids) // 2]
        for pos, required in need.items():
            # Nobody to start at all — see thin_at for why neither "lacks a
            # surplus" nor "short of starters" survived contact with a real
            # board.
            if required > 0 and available.get(pos, 0) == 0:
                out.setdefault(pos, []).append(median)
    return out


def moves_from_tx(tx: "pd.DataFrame", by_name: Mapping[Any, str]) -> PlayerMoves:
    """Re-key a league_context transaction frame onto Sleeper player ids.

    ``espn_context`` labels each move with a player name (falling back to
    ``espn:<id>`` when it cannot resolve one), so matching happens on the
    normalised name rather than an id. Unresolvable labels are dropped — a
    partial history still prices most claims.

    Args:
        tx: Frame with ``week``, ``add``, ``drop`` and ``bid`` columns.
        by_name: ``(normalised_name, position) -> sleeper_id``.

    Returns:
        ``sleeper_player_id -> [{"leg", "bid", "kind"}]``, oldest first.
    """

    def clean_bid(v: Any) -> Optional[int]:
        """A pandas column with any blank bid becomes float, so 40 arrives as
        40.0 and a blank as NaN. Neither belongs in "(was $40.0)"."""
        try:
            if v is None or v != v:  # NaN
                return None
            return int(round(float(v)))
        except (TypeError, ValueError):
            return None

    sid_for = {n: sid for (n, _pos), sid in by_name.items()}
    out: PlayerMoves = {}
    for row in tx.itertuples(index=False):
        for kind, label in (("add", row.add), ("drop", row.drop)):
            sid = sid_for.get(normalize_name(str(label or "")))
            if sid:
                out.setdefault(sid, []).append(
                    {"leg": int(row.week), "bid": clean_bid(row.bid), "kind": kind}
                )
    for moves in out.values():
        moves.sort(key=lambda m: m["leg"])
    return out


def starters_required(roster_positions: Sequence[str]) -> Dict[str, int]:
    """Dedicated starting slots per skill position (FLEX slots excluded).

    A team with exactly its required starters at a position is thin there:
    one injury and it is in the market. Surplus is what makes a team a
    non-bidder.
    """
    need: Dict[str, int] = {p: 0 for p in SKILL_POSITIONS}
    for slot in roster_positions:
        if slot in need:
            need[slot] += 1
    return need


def thin_at(
    roster: Mapping[str, Any],
    registry: Mapping[str, Any],
    position: str,
    required: int,
    playing: Optional[AbstractSet[str]] = None,
) -> bool:
    """Can this team not put ANYONE on the field at ``position`` this week?

    Counts rostered players at the position who can actually play: not on
    IR/taxi, not carrying a blocking injury status, and — when ``playing`` is
    given — not on a bye.

    Two definitions were tried before this one and both over-bid:

    ``healthy <= required`` ("lacks a surplus") is true of nearly every team
    in a one-QB league by construction. Week 8 2026 it reported three La Liga
    rivals thin at QB whose quarterbacks all played, and escalated the bid to
    $14 — a quarter of the budget — for a bye-week fill.

    ``available < required`` ("short of starters") then over-fired in the
    other direction on multi-slot positions: a Mantis team with two playable
    wideouts against three WR slots counted as a rival, so a week with four
    bye teams put most of the league in the market and priced *no-help*
    wideouts at $94 off the room's dynasty-sized medians.

    What survives is the case where a rival has no choice: nobody to start at
    all. That team must bid. A team one body short for one week fills from
    its flex or streams cheaply, and is not who you are bidding against.

    Args:
        playing: Teams with a game this week. Omit only when the week's
            kickoffs are unknown; a bye then counts as playable, which is the
            old, over-counting behaviour.
    """
    reserve = {str(p) for p in (roster.get("reserve") or [])}
    taxi = {str(p) for p in (roster.get("taxi") or [])}
    available = 0
    for pid in roster.get("players") or []:
        sid = str(pid)
        if sid in reserve or sid in taxi:
            continue
        meta = registry.get(sid) or {}
        if meta.get("position") != position:
            continue
        if str(meta.get("injury_status") or "").upper() in BLOCKING_STATUSES:
            continue
        if playing is not None and meta.get("team") not in playing:
            continue
        available += 1
    return required > 0 and available == 0


CLEARING_FIT_DIR = REPO_ROOT / "data" / "waivers" / "clearing_fit"


def load_clearing_model(
    league: str, season: int, budget: int
) -> Tuple[clearing_model.ClearingModel, str]:
    """The league's fitted clearing-price model, or the prior alone -- said aloud.

    The fit is the table of rival claims per tier that
    ``scripts/backtest_clearing_price.py --write-fit`` writes from the league's
    own transaction log (failed claims included). A league with no fit gets the
    published-data prior only, and the report says that is all it is.
    """
    path = CLEARING_FIT_DIR / f"{league}_{season}.json"
    if path.is_file():
        d = json.loads(path.read_text(encoding="utf-8"))
        obs = clearing_model.obs_from_json(d["obs"])
        model = clearing_model.ClearingModel(obs, budget=budget)
        model.fit_through = int(d["through_week"])
        return (
            model,
            f"fit on {len(obs)} name-weeks through week {d['through_week']}",
        )
    prior_only = clearing_model.ClearingModel([], budget=budget)
    prior_only.fit_through = None
    return (
        prior_only,
        "NO LEAGUE FIT -- published-data prior only "
        "(run scripts/backtest_clearing_price.py --write-fit)",
    )


def suggest_bid(
    moves: Optional[List[Dict[str, Any]]],
    rival_bids: Sequence[int],
    room_median: int,
    my_faab: int,
    current_leg: int,
    room_max: int = 0,
    my_roster_id: Optional[str] = None,
    rivals_modelled: bool = True,
    role_ending: bool = False,
    floor_divisor: int = 5,
) -> Tuple[int, str]:
    """A number to bid, and the one sentence that justifies it.

    Three inputs in priority order, which is the order three bids were got
    wrong in one session:

    1. **What this room paid for HIM.** A player it bought for $1 and cut is
       worth $1 (Jalon Daniels, bid $8, won at $1).
    2. **Who can actually outbid you** — rivals thin at his position who have
       both money and a history of spending it. Remaining budget alone is not
       willingness: La Liga's three fullest budgets had spent $0, $0 and $1
       (Omar Cooper, bid $22, needed $10).
    3. **The room's median**, only as the floor-setter when he has no history.

    What it deliberately does NOT model is the tail. Backtested on 51 real
    Mantis bids, escalating young high-dynasty-value players toward the room's
    big-ticket range made things worse at every threshold tried (median error
    $6 -> $14-43, mean $46.8 -> $47.5-56.8; correlation between bid and
    dynasty value is only +0.20 on n=50). Seven outliers are not a pattern.
    Instead ``room_max`` surfaces what this room HAS paid, as context for a
    deliberate override rather than a prediction dressed up as one.

    Args:
        moves: This player's history from :func:`league_player_moves`.
        rival_bids: Median winning bid of each credible rival (thin at the
            position, with budget and a bidding record).
        room_median: The league's median winning bid.
        my_faab: My remaining budget.
        current_leg: The week being priced.
        room_max: The largest winning bid this room has made all season.

    Returns:
        ``(bid, reason)``. Never above a quarter of ``my_faab``.
    """
    cap = max(1, my_faab // 4)
    cut_and_free = 0
    cut_by_us = False
    if moves and moves[-1]["kind"] == "drop":
        cut_and_free = max(0, current_leg - moves[-1]["leg"])
        cut_by_us = bool(my_roster_id) and str(moves[-1].get("by") or "") == str(
            my_roster_id
        )

    # "do not re-buy a player we just cut" (skill, Step 2). We already decided
    # he was not worth a roster spot; paying real money to undo that is the
    # churn the runbook warns about. Week 7 2026 the model wanted $55 for Drew
    # Lock, whom we had cut for $55 three weeks earlier.
    # A role the week's news says is ending is worth the minimum or nothing,
    # whatever the history says. This sits above every other rule because it
    # is the one thing that makes the rest of them irrelevant: you are not
    # buying the usage you are looking at.
    if role_ending:
        return 1, "his starter is returning — the role is ending, minimum or skip"

    if cut_by_us:
        return 1, (
            f"WE cut him in wk{moves[-1]['leg']} — re-buy at the minimum or not"
            " at all"
        )
    last_paid = next(
        (m["bid"] for m in reversed(moves or []) if m["kind"] == "add" and m["bid"]),
        None,
    )

    if not rival_bids:
        if cut_and_free >= 1:
            bid = max(1, int(last_paid or 1))
            return min(bid, cap), (
                f"this room cut him {cut_and_free}wk ago"
                f"{f' after paying ${last_paid}' if last_paid else ''}"
                " and nobody who needs the spot can outbid you"
            )
        # room_median // 5, not // 3: swept against 51 real Mantis bids, the
        # lower floor halves wasted FAAB ($96 -> $46 across 51 claims, median
        # overbid $6 -> $3) and costs one extra claim lost. Overpaying was the
        # failure mode worth fixing.
        # Only Sleeper gives us every rival's roster AND budget, so only
        # there does an empty rival list MEAN nobody can outbid us. On ESPN
        # and Yahoo it means we never looked, and saying otherwise put a
        # claim in George's hands justified by an analysis that never ran.
        return min(max(1, room_median // floor_divisor), cap), (
            "no rival is both thin here and able to spend"
            if rivals_modelled
            else f"room median ${room_median} floor; no rival model on this "
            "platform, so check who else needs the spot"
        )

    top = max(rival_bids)
    beat = top + max(1, top // 5)
    if cut_and_free >= 2 and last_paid and beat > last_paid * 3:
        beat = max(last_paid * 2, room_median)
    reason = f"{len(rival_bids)} rival(s) thin here; their top median bid is ${top}"
    bid = min(max(1, int(beat)), cap)
    if room_max and room_max >= bid * 4:
        reason += f" — but this room has gone as high as ${room_max}"
    return bid, reason


def nfl_week_for_date(stamp: str, season: int) -> Optional[int]:
    """Map a Yahoo transaction date (``Oct 21, 4:52 am``) to its NFL week.

    A move belongs to the week it was made in, which is the latest week whose
    games had already started on or before that date. Yahoo prints no year, so
    the season is supplied and a January date is read as the following
    calendar year.

    Returns:
        The week, or None when the schedule is unavailable or unparseable.
    """
    try:
        import datetime as _dt
        import glob as _glob

        files = sorted(
            _glob.glob(
                str(BRONZE / "schedules" / f"season={season}" / "**" / "*.parquet"),
                recursive=True,
            )
        )
        if not files:
            return None
        sched = pd.read_parquet(files[-1])
        sched["gameday"] = pd.to_datetime(sched["gameday"])
        starts = sched.groupby("week")["gameday"].min().sort_index()
        month_day = stamp.split(",")[0].strip()
        parsed = _dt.datetime.strptime(month_day, "%b %d")
        year = season + 1 if parsed.month < 3 else season
        when = pd.Timestamp(year=year, month=parsed.month, day=parsed.day)
        earlier = starts[starts <= when]
        return int(earlier.index[-1]) if len(earlier) else 1
    except Exception:  # noqa: BLE001 — an unmapped date just loses one row
        return None


def yahoo_transactions_text(
    league_id: str, team_id: int = 0, pages: int = 4
) -> Tuple[str, int]:
    """Transactions page text and our remaining FAAB, from one page session.

    Both come off the same logged-in page because the bid is gated on the
    demand history AND the budget: wiring only one of them (as ESPN briefly
    was) leaves every bid blank while the report looks complete. Opening a
    second browser is not an option -- Playwright's sync API cannot nest.

    Returns ``("", 0)`` on any failure, so a lapsed Yahoo login costs the
    demand column rather than the whole report.
    """
    try:
        from src import waiver_sites as ws

        page = ws.site_page(shared_browser(), "yahoo", str(league_id), team_id)
        text = ws.yahoo_transactions(page, str(league_id), pages)
        faab = 0
        try:
            state = ws.yahoo_state(page, str(league_id), team_id, [])
            faab = max(0, int(state.get("faab_left") or 0))
        except Exception as exc:  # noqa: BLE001 — bids blank, report stands
            print(f"WARN: Yahoo FAAB unavailable ({exc}) — bids will be blank")
        return text, faab
    except Exception as exc:  # noqa: BLE001 — the column is an aid, not a gate
        print(f"WARN: Yahoo transactions unavailable ({exc})")
        return "", 0


def moves_from_yahoo(text: str, by_name: Mapping[Any, str], season: int) -> PlayerMoves:
    """Demand history for a Yahoo league, from its Transactions page text.

    Yahoo's API is approval-gated (401 for read scope, no write scope for new
    apps), so the page is the only source. Without it Feetball had nothing but
    the league-wide median to price a claim on.

    Args:
        text: ``body.innerText`` of ``/f1/<league>/transactions``.
        by_name: ``(normalised_name, position) -> sleeper_id``.
        season: Season year, to resolve Yahoo's year-less dates.

    Returns:
        ``sleeper_player_id -> [{"leg", "bid", "kind"}]``, oldest first.
    """
    from src.yahoo_transactions_page import parse_yahoo_transactions

    sid_for = {n: sid for (n, _pos), sid in by_name.items()}
    out: PlayerMoves = {}
    staged: Dict[str, List[Tuple[int, int, Dict[str, Any]]]] = {}
    for idx, rec in enumerate(parse_yahoo_transactions(text)):
        leg = nfl_week_for_date(rec["when"], season)
        if leg is None:
            continue
        for kind in ("add", "drop"):
            who = rec.get(kind)
            if not who:
                continue
            sid = sid_for.get(normalize_name(who["name"]))
            if sid:
                staged.setdefault(sid, []).append(
                    (
                        leg,
                        idx,
                        {
                            "leg": leg,
                            "bid": rec["bid"] if kind == "add" else None,
                            "kind": kind,
                        },
                    )
                )
    # The page lists newest first, and several moves share one leg, so page
    # position is the only tiebreak that keeps "added then cut" in that order.
    for sid, rows in staged.items():
        rows.sort(key=lambda r: (r[0], -r[1]))
        out[sid] = [r[2] for r in rows]
    return out


def demand_note(
    moves: Optional[List[Dict[str, Any]]],
    current_leg: int,
    my_roster_id: Optional[str] = None,
) -> str:
    """One-glance summary of what this room has paid for a player, and when.

    Args:
        moves: This player's moves from :func:`league_player_moves`.
        current_leg: The leg the report is for.

    Returns:
        ``"unclaimed"`` when the room has never rostered him, else the last
        price paid plus how long he has sat free since being cut.
    """
    if not moves:
        return "unclaimed"
    last = moves[-1]
    if last["kind"] == "add":
        paid = f"${last['bid']}" if last["bid"] else "free"
        return f"held {paid} wk{last['leg']}"
    paid = next(
        (f"${m['bid']}" for m in reversed(moves) if m["kind"] == "add" and m["bid"]),
        "free",
    )
    free_for = max(0, current_leg - last["leg"])
    # "do not re-buy a player we just cut" is a rule in the skill; it is only
    # checkable if the report says who did the cutting.
    whose = (
        " by US"
        if my_roster_id and str(last.get("by") or "") == str(my_roster_id)
        else ""
    )
    return f"cut wk{last['leg']}{whose} (was {paid}), free {free_for}wk"


def checkout_age_warning(max_age_days: int = 3) -> Optional[str]:
    """Warn when HEAD is old enough that the board and tooling may be stale.

    The weekly crons commit the upcoming week's board and the day's Bronze
    snapshots, so a checkout that has not moved in days is reading last
    week's numbers and may be missing tooling entirely. A 7-week-old checkout
    once produced two confident wrong answers in one session: that the
    pipeline had died (the crons were green) and that the claim tools did not
    exist (they were on origin/main).

    Uses only the local commit date — no fetch, no network.

    Args:
        max_age_days: Age at which the warning fires.

    Returns:
        A warning line, or None when the checkout is fresh or not a git repo.
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        age_days = (time.time() - int(out.stdout.strip())) / 86400
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if age_days < max_age_days:
        return None
    return (
        f"WARN: this checkout's last commit is {age_days:.0f} days old — the "
        "weekly crons commit the board and Bronze snapshots daily. "
        "`git pull` before trusting these numbers."
    )


def fmt(v: Optional[float]) -> str:
    return f"{v:5.1f}" if v is not None else "    -"


#: Sleeper ``injury_status`` values that keep a player off the field. A
#: same-position team-mate carrying one of these is why a waiver candidate's
#: role may be borrowed rather than earned.
BLOCKING_STATUSES = frozenset({"OUT", "DOUBTFUL", "IR", "PUP", "NFI", "SUS"})


#: Sleeper ``search_rank`` for a player the registry does not rank: treated as
#: less notable than anyone who is ranked.
UNRANKED = 10**6


def injured_teammates(
    registry: Dict[str, Any],
) -> Dict[Tuple[str, str], List[Tuple[int, str, str]]]:
    """Map ``(team, position)`` to ``(search_rank, name)`` for players who cannot play.

    Built from the Sleeper registry's live ``injury_status`` rather than the
    weekly official report, because the official report is empty until
    Wednesday — exactly when waiver claims are being decided.

    ``search_rank`` rides along so callers can keep only team-mates more
    notable than the candidate; without that filter every deep reserve on an
    injured depth chart reads as a reason to discount the candidate.

    Args:
        registry: Sleeper player registry (``sleeper_player_id -> meta``).

    Returns:
        ``(team, position) -> [(search_rank, name, sleeper_id)]``, best rank
        first, for skill positions only. The id lets callers join the week's
        sentiment flags onto the team-mate — "he is out" and "he is due back
        Sunday" are opposite signals for the player filling in.
    """
    out: Dict[Tuple[str, str], List[Tuple[int, str]]] = {}
    for sid, meta in registry.items():
        if not isinstance(meta, dict):
            continue
        if str(meta.get("injury_status") or "").upper() not in BLOCKING_STATUSES:
            continue
        team, pos = meta.get("team"), meta.get("position")
        name = meta.get("full_name")
        if not team or pos not in SKILL_POSITIONS or not name:
            continue
        rank = meta.get("search_rank")
        out.setdefault((str(team), str(pos)), []).append(
            (
                int(rank) if isinstance(rank, (int, float)) else UNRANKED,
                str(name),
                str(sid),
            )
        )
    return {k: sorted(v) for k, v in out.items()}


#: Sleeper ``reserve_allow_*`` setting -> the ``injury_status`` it permits in an
#: IR slot. A slot that is free is not a slot you may use: Mantis 2026 runs
#: ``reserve_allow_out = 0``, so a player merely "Out" cannot be stashed there.
RESERVE_ALLOWS = {
    "reserve_allow_out": "Out",
    "reserve_allow_doubtful": "Doubtful",
    "reserve_allow_sus": "Sus",
    "reserve_allow_na": "NA",
    "reserve_allow_cov": "COV",
    "reserve_allow_dnr": "DNR",
}


def roster_mechanics(
    league: Mapping[str, Any],
    my_roster: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> List[str]:
    """Slot accounting a claim depends on: open spots, IR rules, who can be stashed.

    Every claim is really two questions — is he worth it, and where does he go.
    The second one went wrong twice in one session: a player was recommended
    for an IR slot the league does not allow him in, and a bench player who
    *was* IR-eligible sat unnoticed while the roster read as full.

    Args:
        league: Sleeper league object (``roster_positions``, ``settings``).
        my_roster: My roster object (``players``, ``reserve``, ``taxi``).
        registry: Sleeper player registry, for names and injury status.

    Returns:
        Printable lines; empty when the league object is unusable.
    """
    positions = league.get("roster_positions") or []
    if not positions:
        return []
    settings = league.get("settings") or {}
    players = [str(p) for p in (my_roster.get("players") or [])]
    reserve = {str(p) for p in (my_roster.get("reserve") or [])}
    taxi = {str(p) for p in (my_roster.get("taxi") or [])}
    active = [p for p in players if p not in reserve and p not in taxi]

    ir_slots = int(settings.get("reserve_slots") or 0)
    taxi_slots = int(settings.get("taxi_slots") or 0)
    allowed = ["IR"] + [
        label for key, label in RESERVE_ALLOWS.items() if settings.get(key)
    ]

    open_active = len(positions) - len(active)
    lines = [
        f"  active {len(active)}/{len(positions)}"
        f" ({open_active} open — a claim needs a drop when 0)"
        f" | IR {len(reserve)}/{ir_slots} | taxi {len(taxi)}/{taxi_slots}"
    ]
    if ir_slots:
        lines.append(f"  IR accepts: {', '.join(allowed)}")
        if ir_slots > len(reserve):
            stashable = sorted(
                (registry.get(p) or {}).get("full_name") or p
                for p in active
                if str((registry.get(p) or {}).get("injury_status") or "").upper()
                in {a.upper() for a in allowed}
            )
            lines.append(
                "  IR-eligible on your bench (move to free an active slot): "
                + (", ".join(stashable) if stashable else "none")
            )
    return lines


def yahoo_live_pools(
    league_id: str, team_id: int, teams: int, pages: int = 4
) -> Dict[str, List[str]]:
    """My roster, the league's rostered set and the free-agent pool, from Yahoo.

    Yahoo's API has no read scope, so this league used to need three
    hand-saved files while Sleeper and ESPN read themselves. Returns empty
    lists on any failure so the report degrades to the files rather than dying.

    Returns:
        ``{"mine", "rostered", "available"}`` of player names.
    """
    try:
        from src import waiver_sites as ws
        from src.yahoo_transactions_page import parse_yahoo_player_names

        page = ws.site_page(shared_browser(), "yahoo", str(league_id), team_id)
        raw = ws.yahoo_rosters(
            page, str(league_id), team_id, range(1, int(teams) + 1), pages
        )
        return {
            "mine": parse_yahoo_player_names(raw.get("mine", "")),
            "rostered": parse_yahoo_player_names(raw.get("league", "")),
            "available": parse_yahoo_player_names(raw.get("available", "")),
        }
    except Exception as exc:  # noqa: BLE001 — fall back to the files
        print(f"WARN: Yahoo live pools unavailable ({exc})")
        return {"mine": [], "rostered": [], "available": []}


def emit_claims(
    path: Path,
    league: str,
    week: int,
    fas: Sequence[Dict[str, Any]],
    drops: Sequence[Mapping[str, Any]],
    open_active: int,
    manual: bool,
    limit: int = 3,
    dynasty: bool = False,
) -> str:
    """Write a claims file for submit_claims.py from the report's own numbers.

    The bids in a hand-typed claims file are the one number in this whole
    pipeline that never came from the pipeline, which is why they were the
    thing most often wrong. Here each one is the computed ``BID $N``, each
    drop is the next name off the report's drop list, and the reason the
    model gave is written beside it. Review and edit it -- but now the
    starting point is the tool's, not a guess.

    Args:
        path: Where to write. An existing file is never overwritten.
        league: Preset key, written into every row.
        week: The week being claimed, for the header.
        fas: Scored free agents; only STARTS/BENCH+ with a bid are offered.
        drops: The report's drop candidates, weakest first.
        open_active: Open active slots -- the first N claims need no drop.
        manual: True when the platform cannot be filed by script (Sleeper).
        limit: How many claims to offer.

    Returns:
        A line for the report saying what happened.
    """
    if path.exists():
        return f"  --emit-claims: {path} already exists, left untouched"
    # Redraft: only names that help this lineup. Dynasty: a young asset reads
    # "no help" this week by design, so anything the ranking scored positive
    # is a candidate. Either way the order is the ranking's, not raw blend.
    worth_claiming = [
        r
        for r in fas
        if not r.get("bye")
        and (
            r.get("verdict") in (STARTS, BENCH_UP)
            or (dynasty and r.get("score", 0) > 0)
        )
    ]
    picks = sorted(
        (r for r in worth_claiming if r.get("bid")),
        key=lambda r: (-r.get("score", 0), -r["blend"]),
    )[:limit]
    if not picks:
        # Two very different situations used to share one message. On ESPN and
        # Yahoo the demand history -- and so the computed bid -- only exists
        # with --espn-browser / --yahoo-browser, so this said "nothing rated
        # STARTS or BENCH+" while the report listed several. Guessing a bid
        # here would defeat the whole point of generating the file, so name
        # the flag instead.
        if worth_claiming:
            return (
                f"  --emit-claims: {len(worth_claiming)} players rated "
                "STARTS/BENCH+ but none has a computed BID — re-run with "
                "--espn-browser / --yahoo-browser so the demand history "
                "loads, or write the file by hand and say why each bid"
            )
        return "  --emit-claims: nothing rated STARTS or BENCH+ to claim"
    spare, used, lines = open_active, 0, []
    for i, r in enumerate(picks, start=1):
        bid, why = r["bid"]
        if spare > 0:
            # An open slot costs no player, so the drop list does not advance.
            drop, spare = None, spare - 1
        elif used < len(drops):
            # A dynasty swap has to be an upgrade somewhere: either the claim
            # helps my lineup, or the player coming in is worth more than the
            # one going out. Without this the weakest-DYNASTY-value drop
            # (DeMario Douglas, 1,187) was offered up for a depth quarterback
            # worth 979.
            d = drops[used]
            if (
                dynasty
                and r.get("gain4", 0) <= 0
                and (r.get("dyn") or 0) <= (d.get("dyn") or 0)
            ):
                lines.append(
                    f"  # {r['name']} ${bid} -- not worth dropping {d['name']} "
                    f"(dynasty value {r.get('dyn') or 0} vs {d.get('dyn') or 0}, "
                    "no lineup gain)"
                )
                continue
            drop, used = d["name"], used + 1
        else:
            # No slot and no droppable player left: say so rather than
            # emitting a claim the site would reject.
            lines.append(f"  # {r['name']} ${bid} — no drop left to pair him with")
            continue
        lines.append(
            f"  - {{league: {league}, add: {r['name']}, "
            + (f"drop: {drop}, " if drop else "")
            + f"bid: {bid}, priority: {i}}}"
            + f"  # {r['verdict']}, "
            + (f"gain4 {r['gain4']:+.1f}, " if "gain4" in r else "")
            + why
        )
    header = [
        f"# Week {week} {league} claims — generated by scripts/waiver_wire.py.",
        "# Every bid is the report's computed BID $N and every drop comes off its",
        "# drop list. Edit freely, but state a reason when you move a bid.",
    ]
    if manual:
        header.append(
            "# Sleeper cannot be filed by script (ToS): enter these in the app."
        )
    path.write_text("\n".join(header + ["claims:"] + lines) + "\n", encoding="utf-8")
    n_claims = sum(1 for ln in lines if ln.lstrip().startswith("- {"))
    skipped = len(lines) - n_claims
    return f"  --emit-claims: wrote {n_claims} claims to {path}" + (
        f" ({skipped} candidate(s) left as comments: no drop worth making)"
        if skipped
        else ""
    )


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", required=True, help="LEAGUE_PRESETS key")
    ap.add_argument("--week", type=int, help="NFL week to project (default: upcoming)")
    ap.add_argument("--season", type=int)
    ap.add_argument(
        "--user", help="Sleeper display name (default: preset my_user / georgesmith)"
    )
    ap.add_argument(
        "--roster-file", type=Path, help="ESPN/Yahoo: my roster, one name per line"
    )
    ap.add_argument(
        "--faab",
        type=int,
        metavar="N",
        help="our remaining FAAB, when the site cannot be read live. The "
        "computed bid is gated on the demand history AND the budget, and "
        "Yahoo's login is behind bot detection — but --transactions-file "
        "already supplies the history login-free, so one typed number is all "
        "that stands between a pasted Yahoo board and a priced one",
    )
    ap.add_argument(
        "--transactions-file",
        type=Path,
        help="Yahoo: the league Transactions page saved as text, for the demand "
        "column and bid model (Yahoo's API has no read scope)",
    )
    ap.add_argument(
        "--no-gate",
        action="store_true",
        help="skip the self-check at the end of the report (it exits 1 on CRITICAL)",
    )
    ap.add_argument(
        "--yahoo-browser",
        action="store_true",
        help="Yahoo: read the league Transactions page through the logged-in "
        "claims profile instead of --transactions-file",
    )
    ap.add_argument(
        "--espn-browser",
        action="store_true",
        help="ESPN: add the demand column by reading the league's transaction log "
        "through the logged-in claims profile (scripts/league_login.py)",
    )
    ap.add_argument(
        "--rostered-file",
        type=Path,
        help="ESPN/Yahoo: every player rostered in the league (one per line) -> exact FA pool",
    )
    ap.add_argument(
        "--available-file",
        type=Path,
        help="ESPN/Yahoo: the site's own available-players list (one per line) -> exact FA pool",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=6,
        help="the ranked claim list shows 4 x this many names (6 -> 24)",
    )
    ap.add_argument(
        "--dyn-points",
        type=float,
        default=waiver_rank.DYN_POINTS_PER_UNIT,
        help="dynasty leagues: four-week points one FantasyCalc value unit is "
        "worth when ranking claims (a decision, not a fit)",
    )
    ap.add_argument(
        "--list-size",
        type=int,
        default=None,
        help="names in the ranked claim list (default: 4 x --top)",
    )
    ap.add_argument(
        "--usd-per-point",
        type=float,
        default=2.0,
        help="Sleeper bids: FAAB dollars one four-week point over the free "
        "replacement is worth (the ceiling a bid is never raised past)",
    )
    ap.add_argument(
        "--usd-per-dyn",
        type=float,
        default=0.02,
        help="Sleeper dynasty bids: FAAB dollars per FantasyCalc value unit",
    )
    ap.add_argument(
        "--emit-claims",
        type=Path,
        metavar="PATH",
        help="write a claims file for submit_claims.py using the report's own "
        "computed bids and drop list (never overwrites an existing file)",
    )
    args = ap.parse_args(argv)
    list_size = args.list_size or args.top * 4

    try:
        preset = config.our_league(args.league)
    except (KeyError, ValueError) as exc:
        sys.exit(exc.args[0])
    platform = preset.get("platform")
    if args.season and args.week:
        season, week = args.season, args.week
    else:
        season, week = set_lineups._default_week(args.season)
        week = args.week or week

    registry = load_sleeper_players(max_age_days=set_lineups.REGISTRY_MAX_AGE_DAYS)
    sched_file = set_lineups._latest(
        str(set_lineups.SCHEDULES / f"season={season}" / "*.parquet"), exclude="derived"
    )
    kickoffs = (
        set_lineups.kickoffs_for_week(pd.read_parquet(sched_file), week)
        if sched_file
        else {}
    )
    # Sleeper uses LAR/JAX-style abbreviations; nflverse schedules use LA for the Rams.
    playing = set(kickoffs) | ({"LAR"} if "LA" in kickoffs else set())
    all_teams: Set[str] = set()
    # Teams with a game in each of the next four weeks: a bye in the window
    # costs a claim a quarter of his value (src/waiver_rank.py).
    playing_by_week: Dict[int, Set[str]] = {}
    if sched_file:
        _sched = pd.read_parquet(sched_file)
        all_teams = {
            "LAR" if t == "LA" else str(t)
            for t in set(_sched["home_team"]) | set(_sched["away_team"])
        }
        for _w in range(week, week + waiver_rank.WINDOW):
            _k = set_lineups.kickoffs_for_week(_sched, _w)
            if _k:
                playing_by_week[_w] = set(_k) | ({"LAR"} if "LA" in _k else set())
    # Dynasty presets: FantasyCalc market value + age next to every row ({} otherwise).
    dyn = league_context.dynasty_values_for_preset(preset, config.ROSTER_CONFIGS)
    _, by_name = build_id_maps(registry)
    league = None
    rostered: Set[str] = set()
    mine: List[str] = []
    starters: Set[str] = set()
    if platform == "sleeper":
        league = sleeper_http.get_league(str(preset["league_id"]))
        if not league:
            sys.exit("Sleeper league unavailable")
        username = args.user or preset.get("my_user") or "georgesmith"
        all_rosters = sleeper_http.get_league_rosters(str(preset["league_id"]))
        for r in all_rosters:
            rostered.update(str(p) for p in (r.get("players") or []))
        my = set_lineups.find_my_roster(str(preset["league_id"]), username)
        mechanics = roster_mechanics(league, my, registry)
        mine = [
            str(p) for p in (my.get("players") or []) if p not in (my.get("taxi") or [])
        ]
        starters = {str(p) for p in (my.get("starters") or [])}
        title = f"{league.get('name')} — {username}"
    else:
        live = (
            yahoo_live_pools(
                str(preset["league_id"]),
                int(preset.get("my_team_id") or 1),
                int(preset.get("teams") or 10),
            )
            if platform == "yahoo" and args.yahoo_browser
            else None
        )
        if live and live["mine"]:
            to_id = {n: sid for (n, _p), sid in by_name.items()}

            def ids(names: Sequence[str]) -> Set[str]:
                return {
                    to_id[normalize_name(n)]
                    for n in names
                    if normalize_name(n) in to_id
                }

            mine = sorted(ids(live["mine"]))
            rostered = ids(live["rostered"]) | set(mine)
            live_available = ids(live["available"])
            title = f"{args.league} ({platform}, read live from the league site)"
        elif not args.roster_file:
            sys.exit(
                f"{args.league} is on {platform}: pass --roster-file with your "
                "roster, or --yahoo-browser to read it live"
            )
        else:
            mine = sorted(roster_ids_from_file(args.roster_file, by_name))
            rostered = set(mine)
            if args.rostered_file:
                rostered |= roster_ids_from_file(args.rostered_file, by_name)
            live_available = None
            title = (
                f"{args.league} ({platform}, my roster from {args.roster_file.name})"
            )
        # ESPN/Yahoo expose no settings feed here, so the slot accounting is
        # partial: active slots come from the roster shape and the names we
        # read, while IR/taxi rules need the site. Say which half is missing
        # instead of printing nothing -- the skill tells us to read this block
        # before naming a drop, and a report that omits it entirely makes that
        # rule unfollowable while the gate warned about it every single week.
        shape = config.ROSTER_CONFIGS[preset["roster"]]
        active_slots = sum(v for k, v in shape.items() if k != "BN")
        mechanics = [
            f"  active {min(len(mine), active_slots)}/{active_slots}"
            f" ({max(0, active_slots - len(mine))} open"
            f" — a claim needs a drop when 0) | roster {len(mine)}"
            f"/{sum(shape.values())} from {args.roster_file.name}",
            f"  IR accepts: unknown on {platform} — confirm on the site before "
            "using an IR slot (Step 4b)",
        ]
    available: Optional[Set[str]] = (
        roster_ids_from_file(args.available_file, by_name)
        if args.available_file
        else (live_available if platform != "sleeper" else None)
    )
    scoring = scoring_for(preset, league)

    ours_df, ours_label = set_lineups.load_ours(season, week)
    roster_files = glob.glob(
        str(BRONZE / "players" / "rosters" / "season=*" / "**" / "*.parquet"),
        recursive=True,
    )
    rosters_df = pd.concat(
        [pd.read_parquet(f) for f in roster_files], ignore_index=True
    )
    gsis_map = roster_gsis_map(rosters_df)
    weekly_files = sorted(
        glob.glob(str(BRONZE / "players" / "weekly" / f"season={season}" / "*.parquet"))
    )
    weekly_df = pd.read_parquet(weekly_files[-1]) if weekly_files else pd.DataFrame()
    names = full_name_map(rosters_df, weekly_df)
    injury_ctx = set_lineups.injury_context(season, week, registry, gsis_map, weekly_df)
    blocked_map = injured_teammates(registry)
    # What this room has already paid for each player. Sleeper only: ESPN and
    # Yahoo transaction logs need the claims browser, which this report does
    # not open (league_context.py --espn-browser has them).
    tx_rows: List[Dict[str, Any]] = []
    bid_stats: Dict[str, Dict[str, Any]] = {}
    rivals_by_pos: Dict[str, List[int]] = {}
    # True once a platform branch has actually read every rival's roster and
    # budget. An empty rivals_by_pos then MEANS nobody can outbid us; while
    # this is False it only means we never looked, and the bid's reason has to
    # say so rather than imply the field is clear.
    rivals_modelled = False
    room_median = 0
    room_max = 0
    my_faab = 0
    # The most any other roster has left to bid: above it a claim cannot lose.
    max_rival_left: Optional[int] = None
    my_roster_id: Optional[str] = None
    live_available: Optional[Set[str]] = None
    espn_payload: Optional[Mapping[str, Any]] = None
    espn_tx = pd.DataFrame()
    my_roster_id: Optional[str] = None
    if platform == "sleeper":
        tx_rows = fetch_league_transactions(str(preset["league_id"]), week)
        bid_stats = team_bid_stats(tx_rows)
        moves = league_player_moves(str(preset["league_id"]), week, tx_rows)
        my_rid = str(my.get("roster_id"))
        my_roster_id = my_rid
        budget_total = int((league.get("settings") or {}).get("waiver_budget") or 0)
        my_faab = budget_total - int(
            (my.get("settings") or {}).get("waiver_budget_used") or 0
        )
        need = starters_required(league.get("roster_positions") or [])
        all_bids = sorted(
            b for st in bid_stats.values() for b in [st["median"]] * st["n"]
        )
        room_median = all_bids[len(all_bids) // 2] if all_bids else 0
        room_max = max((st["max"] for st in bid_stats.values()), default=0)
        rivals_by_pos: Dict[str, List[int]] = {}
        rivals_modelled = True
        for r in all_rosters:
            rid = str(r.get("roster_id"))
            if rid == my_rid:
                continue
            st = bid_stats.get(rid)
            left = budget_total - int(
                (r.get("settings") or {}).get("waiver_budget_used") or 0
            )
            max_rival_left = (
                left if max_rival_left is None else max(max_rival_left, left)
            )
            # Credible = thin at the spot, has money, and has shown he spends.
            if not st or left < room_median:
                continue
            for pos in SKILL_POSITIONS:
                if thin_at(r, registry, pos, need.get(pos, 0), playing or None):
                    rivals_by_pos.setdefault(pos, []).append(st["median"])
    elif platform == "espn" and args.espn_browser:
        moves, my_faab, espn_payload, espn_tx = espn_player_moves(
            str(preset["league_id"]),
            season,
            int(preset.get("my_team_id") or 1),
            week,
            registry,
            by_name,
        )
    elif platform == "yahoo" and args.yahoo_browser:
        tx_text, my_faab = yahoo_transactions_text(
            str(preset["league_id"]), int(preset.get("my_team_id") or 0)
        )
        moves = moves_from_yahoo(tx_text, by_name, season)
    elif platform == "yahoo" and args.transactions_file:
        moves = moves_from_yahoo(
            args.transactions_file.read_text(encoding="utf-8"), by_name, season
        )
    else:
        moves = {}

    # An explicit --faab is the operator telling us a number the site would
    # not. It wins: they can read their own budget off the page, and the
    # alternative is no bid at all.
    if args.faab is not None:
        my_faab = max(0, int(args.faab))

    # Sleeper derives these from every team's transaction log; on ESPN and
    # Yahoo the same winning bids are already in `moves`, so the median and
    # the ceiling cost nothing extra. Without them every bid collapsed to the
    # $1 floor while the report looked confident about it.
    if platform != "sleeper" and moves:
        paid = sorted(
            int(m["bid"])
            for ms in moves.values()
            for m in ms
            if m.get("kind") == "add" and m.get("bid")
        )
        if paid:
            room_median = paid[len(paid) // 2]
            room_max = paid[-1]
        # ESPN can answer "who else is thin here and able to spend" from the
        # payload we already hold; only Sleeper could before, so every ESPN
        # bid fell to the room-median floor with a reason that admitted no
        # rival had been looked at.
        if platform == "espn" and espn_payload is not None and not espn_tx.empty:
            bids_by_team: Dict[str, List[int]] = {}
            for row in espn_tx.itertuples(index=False):
                bid = getattr(row, "bid", None)
                if bid and not pd.isna(bid):
                    bids_by_team.setdefault(str(row.team), []).append(int(bid))
            rivals_modelled = True
            rivals_by_pos = espn_rivals(
                espn_payload,
                int(preset.get("my_team_id") or 1),
                starters_required(
                    [
                        slot
                        for slot, n in config.ROSTER_CONFIGS[preset["roster"]].items()
                        for _ in range(n)
                    ]
                ),
                bids_by_team,
                room_median,
                playing or None,
            )

    ours = ours_by_sleeper_id(
        score_ours(ours_df, scoring), registry, gsis_map=gsis_map, full_names=names
    )
    slpr_raw = set_lineups.load_sleeper_projections(season, week)
    try:  # a name on a bye now still plays the other three weeks of the window
        slpr_next = set_lineups.load_sleeper_projections(season, week + 1)
    except SystemExit:
        slpr_next = {}
    last = ours_by_sleeper_id(
        last_week_actuals(season, week - 1, scoring),
        registry,
        gsis_map=gsis_map,
        full_names=names,
    )
    adds = {
        str(t["player_id"]): t["count"]
        for t in (sleeper_http.fetch_sleeper_json(TRENDING_URL) or [])
    }
    news_flags = set_lineups.sentiment_flags(season, week)
    news = set_lineups.news_by_sleeper(news_flags, registry, gsis_map)
    snaps = snap_trend(season, week, by_name)
    adp = adp_rank_map(platform) if platform != "sleeper" else {}
    draft_size = preset["teams"] * sum(config.ROSTER_CONFIGS[preset["roster"]].values())

    def adp_rank(sid: str, meta: Dict[str, Any]) -> Optional[int]:
        """Room ADP rank, else Sleeper's own ADP from the projection feed (1000 = undrafted)."""
        rank = adp.get(normalize_name(str(meta.get("full_name") or "")))
        if rank is None:
            dd = (slpr_raw.get(sid) or {}).get("adp_dd_ppr")
            rank = int(dd) if dd and dd < 1000 else None
        return rank

    def own_rank(meta: Dict[str, Any]) -> int:
        r = meta.get("search_rank")
        return int(r) if isinstance(r, (int, float)) else UNRANKED

    def row(sid: str) -> Optional[Dict[str, Any]]:
        meta = registry.get(sid) or {}
        pos = str(meta.get("position") or "")
        if pos not in SKILL_POSITIONS or not meta.get("team"):
            return None
        stats = slpr_raw.get(sid) or {}
        s = score_sleeper_stats(stats, scoring, pos) if stats else None
        o = ours.get(sid)
        both = [v for v in (o, s) if v is not None]
        if not both:
            return None
        # Hoisted above the dict: the bid has to SEE the ending-role signal.
        # It used to be computed as a sibling key, so suggest_bid priced a
        # vanishing role at full value and the gate caught it afterwards --
        # the gate compensating for the producer, which is the weaker half
        # of "make the right thing the only path, then fail loudly".
        blocked = [
            (rank, n, bsid)
            for rank, n, bsid in blocked_map.get((str(meta.get("team")), pos), [])
            if n != (meta.get("full_name") or "") and rank < own_rank(meta)
        ]
        # Two independent sources, either sufficient: the week's news flag
        # (keyword-grade) and the blocker's own practice trail (structured,
        # published by his team). The second exists precisely because the
        # first's provenance is weak.
        role_ending = any(
            "returning" in (news.get(bsid) or "")
            or "activated" in (news.get(bsid) or "")
            or returning_from_practice(bsid, injury_ctx)
            for _rank, _n, bsid in blocked
        )
        return {
            "sid": sid,
            "name": meta.get("full_name") or sid,
            "pos": pos,
            "team": meta.get("team"),
            "ours": o,
            "slpr": s,
            "blend": sum(both) / len(both),
            "last": last.get(sid),
            "adds": adds.get(sid, 0),
            "inj": getattr(resolve_injury_status(sid, meta, injury_ctx), "text", ""),
            "news": news.get(sid, ""),
            "adp": adp_rank(sid, meta),
            "dyn": (dyn.get(sid) or {}).get("value", 0),
            "dyn_known": sid in dyn,
            "age": meta.get("age"),
            # Is he actually on the field, and is that rising? Projections and
            # trending adds both say a player is interesting; neither says he
            # plays. "isn't he a backup?" was the first correction of all.
            "snap": snaps.get(sid),
            "ir": str(meta.get("injury_status") or "").upper() in ("IR", "PUP", "NFI"),
            # Out/Doubtful: no bar for "weakest bench". Bye: same, and never a drop.
            "out": str(meta.get("injury_status") or "").upper() in ("OUT", "DOUBTFUL"),
            "bye": bool(kickoffs) and meta.get("team") not in playing,
            # What he scores in a week he plays: this week's blend, unless he
            # is idle, then Sleeper's number for next week.
            "weekly": (
                score_sleeper_stats(slpr_next.get(sid) or {}, scoring, pos)
                if bool(kickoffs)
                and meta.get("team") not in playing
                and slpr_next.get(sid)
                else None
            ),
            # Same-position team-mates who cannot play: the candidate's role
            # may be on loan from them (see RENTAL in the report legend).
            # What the room has paid for him before: price a claim off this,
            # not the league-wide median (see demand_note).
            "demand": (
                demand_note(moves.get(sid), week, my_roster_id) if moves else ""
            ),
            "bid": (
                suggest_bid(
                    moves.get(sid),
                    rivals_by_pos.get(pos, []),
                    room_median,
                    my_faab,
                    week,
                    room_max,
                    my_roster_id,
                    rivals_modelled=rivals_modelled,
                    role_ending=role_ending,
                    floor_divisor=int(preset.get("bid_floor_divisor") or 5),
                )
                if moves and my_faab
                else None
            ),
            "blocked_by": [
                f"{n}({news[bsid]})" if news.get(bsid) else n
                for _rank, n, bsid in blocked
            ],
            # A team-mate the week's news says is RETURNING ends the rental:
            # the candidate is about to lose the role, not grow into it.
            "blocked_returning": role_ending,
        }

    def likely_fa(r: Dict[str, Any]) -> bool:
        if available is not None:
            return r["sid"] in available
        if platform == "sleeper" or args.rostered_file:
            return True
        return r["adp"] is None or r["adp"] > draft_size

    def line(r: Dict[str, Any], tag: str = "") -> str:
        fa = ""
        if platform != "sleeper":
            fa = "FA?" if likely_fa(r) else f"adp{r['adp']}"
        return (
            f"  {tag:6}{r['name'][:24]:24} {r['pos']:3}{r['team']:4}"
            f" ours{fmt(r['ours'])} slpr{fmt(r['slpr'])} blend{fmt(r['blend'])}"
            f" last{fmt(r['last'])} adds{r['adds'] / 1000:5.0f}k {fa:7}"
            + (
                f" snap{r['snap'][0]:3}%{r['snap'][1]:+3d}"
                if r.get("snap")
                else " snap   -   "
            )
            + (
                (f" dyn{r['dyn']:5d}" if r.get("dyn_known") else " dyn    ?")
                if dyn
                else ""
            )
            + (
                f" gain4 {r['gain4']:+5.1f}"
                + (f" dynpts {r['dyn_pts']:3.0f}" if r.get("dyn_pts") else "")
                if "gain4" in r
                else ""
            )
            # Age prints everywhere, not just dynasty: the gate's young-drop
            # check reads it, and Feetball is a keeper league too.
            + f" age{r['age'] or '-':>3}"
            + (f" {r['verdict']:7}" if r.get("verdict") else "")
            + (f" BID ${r['bid'][0]}" if r.get("bid") else "")
            + (
                f" (wins ~{r.get('p_win_at_bid', r['advice'].p_win):.0%}"
                + (f"; ${r['price80']} for 80%" if r.get("price80") else "")
                + f"; worth ${r['advice'].ceiling})"
                if r.get("advice") and r.get("bid")
                else ""
            )
            + (f" [{r['demand']}]" if r.get("demand") else "")
            + (
                f" {'ENDING' if r.get('blocked_returning') else 'RENTAL'}"
                f"<-{', '.join(r['blocked_by'])[:44]}"
                if r.get("blocked_by")
                else ""
            )
            + f" {r['news']}{'  ' if r['news'] and r['inj'] else ''}{r['inj']}"
        )

    stale = checkout_age_warning()
    if stale:
        # builtins.print: the local ``print`` defined below is unbound here.
        builtins.print(stale)
    # Everything from here is both printed and kept, so the report can check
    # itself at the end. A gate you have to remember to run is a gate that
    # gets skipped — that is how an hour of hand-rolled analysis happened.
    transcript: List[str] = []
    # builtins.print, not the bare name: defining ``print`` below makes it a
    # local throughout main(), so the bare name would be unbound here.
    _stdout_print = builtins.print

    def print(*parts: Any, **kw: Any) -> None:  # noqa: A001 — local shadow
        line = " ".join(str(p) for p in parts)
        transcript.append(line)
        _stdout_print(line, **kw)

    print(f"\n=== {title} — {season} week {week} waivers ===")
    print(
        f"OURS = {ours_label}; SLPR = Sleeper week {week}; LAST = week {week - 1} actuals"
    )
    # Stated, not implied. A row with no NEWS is indistinguishable from a
    # sentiment pipeline that produced nothing — and that pipeline fails OPEN
    # (the LLM layer no-ops to rule extraction while the cron stays green),
    # so "no news" has to be a number you can see and the gate can read.
    print(f"NEWS = Gold sentiment, {len(news_flags)} flags for week {week}")
    if platform != "sleeper" and not (args.rostered_file or args.available_file):
        print(
            f"Other rosters unknown: showing only players drafted beyond pick {draft_size} "
            f"({platform} ADP, Sleeper ADP fallback) — verify availability on the site"
        )

    # Verdicts are relative to MY roster: a pickup must start or beat the bench.
    my_rows = [r for r in (row(s) for s in mine) if r]
    keepers = load_keepers(
        REPO_ROOT / "data" / "draft" / f"{args.league}_{season}_keepers.txt"
    )
    baseline = roster_baseline(
        my_rows,
        roster_format=preset.get("roster"),
        roster_positions=(league or {}).get("roster_positions"),
        keepers=keepers,
    )
    fas = [
        r for r in (row(s) for s in registry if s not in rostered) if r and likely_fa(r)
    ]
    dynasty_league = bool(preset.get("dynasty"))
    clearing = None
    clearing_note = "not used on this platform (no readable rival claims)"
    if platform == "sleeper" and my_faab:
        clearing, clearing_note = load_clearing_model(args.league, season, budget_total)
        clearing_model.advise_all(
            fas,
            clearing,
            my_faab,
            args.usd_per_point,
            args.usd_per_dyn,
            rival_cap=max_rival_left,
        )
    # One list per league, ranked by the gain to MY lineup over the next four
    # weeks (byes included), plus dynasty value where the league keeps players.
    # Candidates: the top names by blend per position, by dynasty value, and
    # by market interest -- the full pool is thousands of zeroes.
    pool_ids = set()
    for _pos in ("QB", "RB", "WR", "TE"):
        by_blend = sorted(
            (r for r in fas if r["pos"] == _pos), key=lambda r: -clearing_model.level(r)
        )
        pool_ids.update(r["sid"] for r in by_blend[:25])
    pool_ids.update(r["sid"] for r in sorted(fas, key=lambda r: -r["dyn"])[:40])
    pool_ids.update(r["sid"] for r in fas if r["adds"] >= 100_000)
    ranked = waiver_rank.rank_targets(
        [r for r in fas if r["sid"] in pool_ids and not r.get("ir")],
        my_rows,
        week,
        playing_by_week,
        preset.get("roster"),
        (league or {}).get("roster_positions"),
        dynasty=dynasty_league and bool(dyn),
        dyn_points_per_unit=args.dyn_points,
    )
    for r in fas:
        r["verdict"] = waiver_verdict(r["pos"], r["blend"], baseline)
        if clearing is not None:
            adv = r["advice"]
            if "gain4" in r:
                # The ceiling is what he does for MY lineup (plus dynasty value),
                # not his points over a free agent: a second quarterback in a
                # one-quarterback league is worth nothing however well he scores.
                adv = clearing.recommend(
                    r["tier"],
                    clearing_model.value_from_gain(
                        r["gain4"],
                        r.get("dyn") if dynasty_league else 0,
                        args.usd_per_point,
                        args.usd_per_dyn,
                    ),
                    my_faab,
                    max_rival_left,
                )
                r["advice"] = adv
            r["price80"] = clearing.price_for(
                0.8, r["tier"], my_faab // 4 or 1, max_rival_left
            )
            r["bid"] = clearing_model.final_bid(
                r.get("bid"),
                adv,
                role_ending=bool(r.get("blocked_returning")),
                no_help_redraft=r["verdict"] == NO_HELP and not dynasty_league,
                depth_cap=(max(1, room_median // 5) if r["verdict"] == DEPTH else None),
            )
            # the chance at the bid actually printed, not at the model's own
            r["p_win_at_bid"] = clearing.p_win(r["bid"][0], r["tier"], max_rival_left)
            continue
        # A price on a player the report says does not help is incoherent: in
        # a redraft league "no help" is a refusal, so the only honest number
        # is the minimum. In dynasty the verdict is advisory — an asset buy is
        # supposed to read "no help" this week — so the bid stands.
        if r.get("bid") and r["verdict"] == NO_HELP and not dynasty_league:
            r["bid"] = (1, "rated no help — minimum or nothing")
        # The bid model prices CONTEST -- what it takes to beat the room. It
        # has no idea what the player is worth TO US. With no rival model that
        # was invisible, because every site-league bid fell to the floor
        # anyway; wiring rivals for ESPN immediately produced $14 (a quarter
        # of our FAAB, the hard cap) on players rated `depth`. A pure add is
        # not worth a quarter of the budget however contested it is, so the
        # verdict caps the contest price.
        elif r.get("bid") and r["verdict"] == DEPTH:
            floor = max(1, room_median // 5)
            if r["bid"][0] > floor:
                r["bid"] = (
                    floor,
                    f"depth only — capped at the ${floor} floor, not the "
                    f"${r['bid'][0]} it would take to win him",
                )
    if clearing is not None or platform == "sleeper":
        print(
            f"BID MODEL = clearing price ({clearing_note}); a claim wins by beating the "
            "top rival bid, and most claims have none: wins ~N% is the model's chance "
            "at that bid, '$X for 80%' what it would take to be fairly sure, worth $N "
            f"the ceiling (${args.usd_per_point:g}/point over the free replacement x 4 "
            f"weeks + ${args.usd_per_dyn:g}/dynasty-value unit); the most any rival "
            f"has left to bid is ${max_rival_left}"
        )
    # The same file set_lineups.sentiment_flags read: this week's, else the
    # latest of any week (so a stale file is still dated, not skipped).
    _news_files = sorted(
        glob.glob(
            str(
                set_lineups.SENTIMENT
                / f"season={season}"
                / f"week={week:02d}"
                / "*.parquet"
            )
        )
    ) or sorted(
        glob.glob(str(set_lineups.SENTIMENT / "season=*" / "week=*" / "*.parquet"))
    )
    extra_notes: List[str] = []
    if clearing is not None:
        if getattr(clearing, "fit_through", None) is None:
            extra_notes.append(
                "bid model: no league fit -- bids rest on the published-data prior alone"
            )
        elif clearing.fit_through < week - 1:
            extra_notes.append(
                f"bid model: the league fit stops at week {clearing.fit_through}, "
                f"this report is week {week}"
            )
    if not slpr_next:
        extra_notes.append(
            f"projections: Sleeper's week-{week + 1} numbers are unavailable -- a name "
            "on a bye this week is valued at 0 for the weeks he plays"
        )
    input_notes = waiver_record.fallback_notes(
        week=week,
        ours_label=ours_label,
        weekly_board=ours_label.startswith("weekly Gold"),
        guessed_pool=platform != "sleeper"
        and available is None
        and not args.rostered_file,
        draft_size=draft_size,
        dynasty_missing=dynasty_league and not dyn,
        news_flags=len(news_flags),
        official_reports=len(injury_ctx.reports),
        snap_players=len(snaps),
        have_history=bool(moves),
        have_budget=bool(my_faab),
        bronze_max_week=(
            int(weekly_df["week"].max())
            if not weekly_df.empty and "week" in weekly_df
            else 0
        ),
        recorded=[
            waiver_record.candidate_row("targets", i, r)
            for i, r in enumerate(ranked[:list_size], start=1)
        ],
        news_age_hours=waiver_record.file_freshness(
            Path(_news_files[-1]) if _news_files else None
        )["age_hours"],
        dyn_unknown=(
            sum(1 for r in ranked[:list_size] if not r.get("dyn_known"))
            if dynasty_league
            else 0
        ),
        dyn_listed=len(ranked[:list_size]),
        extra_notes=extra_notes,
    )
    print("\n" + waiver_record.status_block(input_notes))
    print(
        "FIT = vs MY roster: STARTS (beats a starter he can replace), BENCH+ (beats my "
        "weakest non-keeper bench at his position), depth (pure add), no help. "
        "SNAP = his offensive snap share last week and the change from the week "
        "before: ADDS is what the market believes, SNAP is whether he plays. "
        "When they disagree, believe SNAP — Roschon Johnson read 1,355k adds "
        "on a flat 40% share in week 7. "
        "RENTAL<-NAME = a same-position team-mate cannot play, so the role may "
        "revert when he returns — check before paying up; ENDING<- means the "
        "week's news says that team-mate is RETURNING, so the role is going "
        "away now, not later — from the week's news flag OR his own "
        "practice trail (DNP->LP->FP), either sufficient, because the news "
        "flag is keyword-grade and the trail is published by his team. "
        "ADDS counts adds "
        "across ALL of Sleeper, not this league — never price a claim off it. "
        "[brackets] = what THIS room has paid for him (unclaimed / held $N / "
        "cut wkN, free Nwk): that is the first bid anchor, and "
        "league_context.py's median/p75 only the fallback."
    )
    # What the report printed, kept for the record (src/waiver_record.py).
    listed: Dict[str, List[Dict[str, Any]]] = {}
    basis = "gain to my best lineup over the next 4 weeks, byes included" + (
        " + dynasty value in points" if dynasty_league and dyn else ""
    )
    print(f"\n-- Claim targets (free agents), ranked by {basis} --")
    listed["targets"] = ranked[:list_size]
    for i, r in enumerate(listed["targets"], start=1):
        # The rank goes inside the name column: the gate parses a free-agent
        # line by its indentation, and a tag in the margin hides the row.
        print(line({**r, "name": f"#{i} {r['name']}"}))
    hot = sorted((r for r in fas if r["adds"] >= 100_000), key=lambda r: -r["adds"])[
        :10
    ]
    listed["hot"] = hot
    if hot:
        print("\n-- Most added on Sleeper (48h) still available --")
        for r in hot:
            print(line(r))

    unscored = [
        registry.get(s, {}).get("full_name") or s for s in mine if row(s) is None
    ]
    missing = ", ".join(map(str, unscored)) or "none"
    weakest = "dynasty value" if dyn else "blend"
    print(
        (
            "\n-- Roster mechanics --\n" + "\n".join(mechanics) + "\n"
            if mechanics
            else ""
        )
        + f"\n-- My roster (weakest {weakest} first; {len(my_rows)} scored, "
        f"unscored: {missing}) --"
    )
    # Whoever we have actually started this week AND whoever the optimizer
    # would start are both off the drop list. The two sets differ, and using
    # only the optimizer's left DeMario Douglas tagged START and named a drop
    # candidate in the same week-7 report: dropping a man in the current
    # lineup is a lineup decision, not a waiver one.
    started = set(starters) | set(baseline["starters"])
    roster_out: List[Dict[str, Any]] = []
    for r in sorted(my_rows, key=lambda r: r["dyn"] if dyn else r["blend"]):
        if normalize_name(r["name"]) in keepers:
            tag = "KEEP"
        elif r["sid"] in started:
            tag = "START"
        else:
            tag = "bench"
        roster_out.append(
            {k: r.get(k) for k in ("sid", "name", "pos", "blend", "dyn", "age")}
            | {"tag": tag}
        )
        print(line(r, tag))
    drops = drop_order(
        my_rows,
        {**baseline, "starters": started},
        keepers,
        key="dyn" if dyn else "blend",
        keeps_players=dynasty_league or bool(keepers),
    )
    print(
        "\n  Drop candidates (bench, keepers excluded, weakest first): "
        + (", ".join(r["name"] for r in drops[:4]) or "none")
    )
    if keepers:
        print(
            f"  Keepers protected: {len(keepers)} (from {args.league}_{season}_keepers.txt)"
        )

    claims_msg = None
    if args.emit_claims:
        # The open-slot count lives in the mechanics block the report just
        # printed; read it back rather than recomputing the slot arithmetic
        # a second way, which is how the tag and the drop list diverged.
        slots = re.search(r"\((?P<open>\d+) open", "\n".join(mechanics))
        claims_msg = emit_claims(
            args.emit_claims,
            args.league,
            week,
            fas,
            drops,
            int(slots.group("open")) if slots else 0,
            manual=platform == "sleeper",
            dynasty=dynasty_league,
        )
        print(claims_msg)

    def save_record(sanity: Optional[Mapping[str, Any]] = None) -> None:
        """Freeze this run's listing to ``data/waivers/reports`` (never fatal)."""
        board = set_lineups._latest(
            str(
                set_lineups.GOLD
                / f"season={season}"
                / f"week={week}"
                / "projections_half_ppr_*.parquet"
            )
        )
        weekly_board = ours_label.startswith("weekly Gold")
        snap_files = sorted(
            glob.glob(
                str(set_lineups.INJURIES / f"season={season}" / "injuries_*.parquet")
            )
        )
        recorded = [
            waiver_record.candidate_row(name, i, r)
            for name, rows in listed.items()
            for i, r in enumerate(rows, start=1)
        ]
        fallbacks = input_notes
        inputs = {
            "board": {
                **waiver_record.file_freshness(board),
                "kind": "weekly" if weekly_board else "preseason_fallback",
                "label": ours_label,
            },
            "registry": waiver_record.file_freshness(Path(_PLAYERS_CACHE)),
            "sleeper_projections": {
                "rows": len(slpr_raw),
                "fetched": "live at run time",
            },
            "trending_adds": {"rows": len(adds), "fetched": "live at run time"},
            "news": {"flags": len(news_flags)},
            "injury_report": {
                "official_reports": len(injury_ctx.reports),
                "teams_reported": len(injury_ctx.teams_reported),
                "latest_snapshot": waiver_record.file_freshness(
                    Path(snap_files[-1]) if snap_files else None
                ),
            },
            "snaps": {"players": len(snaps)},
            "bronze_weekly": waiver_record.file_freshness(
                Path(weekly_files[-1]) if weekly_files else None
            ),
            "transactions": {"players_with_history": len(moves), "rows": len(tx_rows)},
            "dynasty_values": {"players": len(dyn)},
            "pool": {
                "source": (
                    "sleeper_all_rosters"
                    if platform == "sleeper"
                    else (
                        "available_file"
                        if available is not None
                        else "rostered_file" if args.rostered_file else "adp_guess"
                    )
                ),
                "free_agents_scored": len(fas),
            },
            "bidding": {
                "faab_left": my_faab,
                "room_median_bid": room_median,
                "room_max_bid": room_max,
                "rivals_modelled": rivals_modelled,
                "rivals_by_position": {p: len(v) for p, v in rivals_by_pos.items()},
            },
        }
        try:
            rec = waiver_record.build_record(
                league=args.league,
                platform=str(platform),
                season=season,
                week=week,
                title=title,
                generated_at=dt.datetime.now(dt.timezone.utc).isoformat(
                    timespec="seconds"
                ),
                inputs=inputs,
                candidates=recorded,
                fallbacks=fallbacks,
                extras={
                    "my_roster": roster_out,
                    "drop_candidates": [r["name"] for r in drops],
                    "claims_file": str(args.emit_claims) if args.emit_claims else None,
                    "claims_result": claims_msg,
                    "sanity": sanity,
                },
            )
            path = waiver_record.write_record(rec)
            _stdout_print(f"\n  record: {path.relative_to(REPO_ROOT)}")
        except OSError as exc:
            _stdout_print(
                f"\n  WARN: waiver record NOT written ({exc}) -- this run "
                "cannot be scored later"
            )

    if args.no_gate:
        save_record()
        return 0
    from src.waiver_sanity import check_report, summarise

    findings = check_report(
        "\n".join(transcript),
        bye_teams=sorted(set(all_teams) - set(playing)) if kickoffs else (),
        faab_left=my_faab or None,
        room_max_bid=room_max or None,
        dynasty=bool(preset.get("dynasty")),
        keeper=bool(keepers),
    )
    verdict = summarise(findings)
    # Printed even when clean: an absent block used to be indistinguishable
    # from a gate that never ran, which is the same silence that let three
    # CRITICALs through once a filter had trimmed the output.
    print(
        f"\n-- Sanity -- {verdict['critical']} critical, "
        f"{verdict['warnings']} warnings"
    )
    for f in findings:
        print(f"  [{f.level}] {f.check}: {f.detail}")
    save_record(
        {
            "critical": verdict["critical"],
            "warnings": verdict["warnings"],
            "passed": verdict["passed"],
            "findings": [f"[{f.level}] {f.check}: {f.detail}" for f in findings],
        }
    )
    if not verdict["passed"]:
        print(
            f"\n  SANITY FAIL: {verdict['critical']} critical — "
            "fix the cause before acting on this report"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
