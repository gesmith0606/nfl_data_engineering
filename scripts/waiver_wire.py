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
import glob
import subprocess
import time
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, league_context, sleeper_http  # noqa: E402
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
from src.sleeper_player_map import load_sleeper_players, normalize_name  # noqa: E402
from src.waiver_verdicts import (  # noqa: E402
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
            for pid in (t.get(f"{kind}s") or {}) or {}:
                out.setdefault(str(pid), []).append(
                    {"leg": leg, "bid": bid, "kind": kind}
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


def espn_player_moves(
    league_id: str,
    season: int,
    team_id: int,
    through_period: int,
    registry: Mapping[str, Any],
    by_name: Mapping[Any, str],
) -> PlayerMoves:
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
        ``sleeper_player_id -> [{"leg", "bid", "kind"}]``, oldest first.
    """
    try:
        from src import waiver_sites as ws
        from src.fantasy_browser import FantasyBrowser

        browser = FantasyBrowser()
        page = ws.site_page(browser, "espn", str(league_id), team_id)
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
    except Exception as exc:  # noqa: BLE001 — the column is an aid, not a gate
        print(f"WARN: ESPN demand history unavailable ({exc})")
        return {}

    return moves_from_tx(tx, by_name)


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
) -> bool:
    """Does this team lack a usable surplus at ``position``?

    Counts rostered players at the position who are not on IR/taxi and not
    carrying a blocking injury status.
    """
    reserve = {str(p) for p in (roster.get("reserve") or [])}
    taxi = {str(p) for p in (roster.get("taxi") or [])}
    healthy = 0
    for pid in roster.get("players") or []:
        sid = str(pid)
        if sid in reserve or sid in taxi:
            continue
        meta = registry.get(sid) or {}
        if meta.get("position") != position:
            continue
        if str(meta.get("injury_status") or "").upper() in BLOCKING_STATUSES:
            continue
        healthy += 1
    return healthy <= required


def suggest_bid(
    moves: Optional[List[Dict[str, Any]]],
    rival_bids: Sequence[int],
    room_median: int,
    my_faab: int,
    current_leg: int,
    room_max: int = 0,
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
    if moves and moves[-1]["kind"] == "drop":
        cut_and_free = max(0, current_leg - moves[-1]["leg"])
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
        return min(max(1, room_median // 5), cap), (
            "no rival is both thin here and able to spend"
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


def yahoo_transactions_text(league_id: str, pages: int = 4) -> str:
    """Transactions page text through the logged-in claims profile.

    Returns an empty string on any failure, so a Yahoo login that has lapsed
    costs the demand column rather than the whole report.
    """
    try:
        from src import waiver_sites as ws
        from src.fantasy_browser import FantasyBrowser

        browser = FantasyBrowser()
        page = ws.site_page(browser, "yahoo", str(league_id), 0)
        return ws.yahoo_transactions(page, str(league_id), pages)
    except Exception as exc:  # noqa: BLE001 — the column is an aid, not a gate
        print(f"WARN: Yahoo transactions unavailable ({exc})")
        return ""


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


def demand_note(moves: Optional[List[Dict[str, Any]]], current_leg: int) -> str:
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
    return f"cut wk{last['leg']} (was {paid}), free {free_for}wk"


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
        "--transactions-file",
        type=Path,
        help="Yahoo: the league Transactions page saved as text, for the demand "
        "column and bid model (Yahoo's API has no read scope)",
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
    ap.add_argument("--top", type=int, default=6, help="free agents shown per position")
    args = ap.parse_args(argv)

    preset = config.LEAGUE_PRESETS.get(args.league)
    if preset is None:
        sys.exit(
            f"Unknown league '{args.league}'. Presets: {sorted(config.LEAGUE_PRESETS)}"
        )
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
        if not args.roster_file:
            sys.exit(
                f"{args.league} is on {platform}: pass --roster-file with your roster"
            )
        mine = sorted(roster_ids_from_file(args.roster_file, by_name))
        rostered = set(mine)
        if args.rostered_file:
            rostered |= roster_ids_from_file(args.rostered_file, by_name)
        mechanics = []
        title = f"{args.league} ({platform}, my roster from {args.roster_file.name})"
    available: Optional[Set[str]] = (
        roster_ids_from_file(args.available_file, by_name)
        if args.available_file
        else None
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
    room_median = 0
    room_max = 0
    my_faab = 0
    if platform == "sleeper":
        tx_rows = fetch_league_transactions(str(preset["league_id"]), week)
        bid_stats = team_bid_stats(tx_rows)
        moves = league_player_moves(str(preset["league_id"]), week, tx_rows)
        my_rid = str(my.get("roster_id"))
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
        for r in all_rosters:
            rid = str(r.get("roster_id"))
            if rid == my_rid:
                continue
            st = bid_stats.get(rid)
            left = budget_total - int(
                (r.get("settings") or {}).get("waiver_budget_used") or 0
            )
            # Credible = thin at the spot, has money, and has shown he spends.
            if not st or left < room_median:
                continue
            for pos in SKILL_POSITIONS:
                if thin_at(r, registry, pos, need.get(pos, 0)):
                    rivals_by_pos.setdefault(pos, []).append(st["median"])
    elif platform == "espn" and args.espn_browser:
        moves = espn_player_moves(
            str(preset["league_id"]),
            season,
            int(preset.get("my_team_id") or 1),
            week,
            registry,
            by_name,
        )
    elif platform == "yahoo" and args.yahoo_browser:
        moves = moves_from_yahoo(
            yahoo_transactions_text(str(preset["league_id"])), by_name, season
        )
    elif platform == "yahoo" and args.transactions_file:
        moves = moves_from_yahoo(
            args.transactions_file.read_text(encoding="utf-8"), by_name, season
        )
    else:
        moves = {}
    ours = ours_by_sleeper_id(
        score_ours(ours_df, scoring), registry, gsis_map=gsis_map, full_names=names
    )
    slpr_raw = set_lineups.load_sleeper_projections(season, week)
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
    news = set_lineups.news_by_sleeper(
        set_lineups.sentiment_flags(season, week), registry, gsis_map
    )
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
            "age": meta.get("age"),
            "ir": str(meta.get("injury_status") or "").upper() in ("IR", "PUP", "NFI"),
            # Out/Doubtful: no bar for "weakest bench". Bye: same, and never a drop.
            "out": str(meta.get("injury_status") or "").upper() in ("OUT", "DOUBTFUL"),
            "bye": bool(kickoffs) and meta.get("team") not in playing,
            # Same-position team-mates who cannot play: the candidate's role
            # may be on loan from them (see RENTAL in the report legend).
            # What the room has paid for him before: price a claim off this,
            # not the league-wide median (see demand_note).
            "demand": demand_note(moves.get(sid), week) if moves else "",
            "bid": (
                suggest_bid(
                    moves.get(sid),
                    rivals_by_pos.get(pos, []),
                    room_median,
                    my_faab,
                    week,
                    room_max,
                )
                if moves and my_faab
                else None
            ),
            "blocked_by": [
                f"{n}({news[bsid]})" if news.get(bsid) else n
                for rank, n, bsid in blocked_map.get((str(meta.get("team")), pos), [])
                if n != (meta.get("full_name") or "") and rank < own_rank(meta)
            ],
            # A team-mate the week's news says is RETURNING ends the rental:
            # the candidate is about to lose the role, not grow into it.
            "blocked_returning": any(
                "returning" in (news.get(bsid) or "")
                or "activated" in (news.get(bsid) or "")
                for rank, n, bsid in blocked_map.get((str(meta.get("team")), pos), [])
                if n != (meta.get("full_name") or "") and rank < own_rank(meta)
            ),
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
            + (f" dyn{r['dyn']:5d} age{r['age'] or '-':>3}" if dyn else "")
            + (f" {r['verdict']:7}" if r.get("verdict") else "")
            + (f" BID ${r['bid'][0]}" if r.get("bid") else "")
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
        print(stale)
    print(f"\n=== {title} — {season} week {week} waivers ===")
    print(
        f"OURS = {ours_label}; SLPR = Sleeper week {week}; LAST = week {week - 1} actuals"
    )
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
    for r in fas:
        r["verdict"] = waiver_verdict(r["pos"], r["blend"], baseline)
    print(
        "FIT = vs MY roster: STARTS (beats a starter he can replace), BENCH+ (beats my "
        "weakest non-keeper bench at his position), depth (pure add), no help. "
        "RENTAL<-NAME = a same-position team-mate cannot play, so the role may "
        "revert when he returns — check before paying up; ENDING<- means the "
        "week's news says that team-mate is RETURNING, so the role is going "
        "away now, not later. ADDS counts adds "
        "across ALL of Sleeper, not this league — never price a claim off it. "
        "[brackets] = what THIS room has paid for him (unclaimed / held $N / "
        "cut wkN, free Nwk): that is the first bid anchor, and "
        "league_context.py's median/p75 only the fallback."
    )
    for pos in ("QB", "RB", "WR", "TE"):
        print(f"\n-- {pos} free agents --")
        for r in sorted((r for r in fas if r["pos"] == pos), key=lambda r: -r["blend"])[
            : args.top
        ]:
            print(line(r))
    hot = sorted((r for r in fas if r["adds"] >= 100_000), key=lambda r: -r["adds"])[
        :10
    ]
    if hot:
        print("\n-- Most added on Sleeper (48h) still available --")
        for r in hot:
            print(line(r))

    if dyn:
        print(
            "\n-- Dynasty targets: unrostered by market value "
            "(youth + a path to a role beat one week's points) --"
        )
        for r in sorted(fas, key=lambda r: -r["dyn"])[: args.top * 2]:
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
    for r in sorted(my_rows, key=lambda r: r["dyn"] if dyn else r["blend"]):
        if normalize_name(r["name"]) in keepers:
            tag = "KEEP"
        elif r["sid"] in (starters or baseline["starters"]):
            tag = "START"
        else:
            tag = "bench"
        print(line(r, tag))
    drops = drop_order(my_rows, baseline, keepers, key="dyn" if dyn else "blend")
    print(
        "\n  Drop candidates (bench, keepers excluded, weakest first): "
        + (", ".join(r["name"] for r in drops[:4]) or "none")
    )
    if keepers:
        print(
            f"  Keepers protected: {len(keepers)} (from {args.league}_{season}_keepers.txt)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
