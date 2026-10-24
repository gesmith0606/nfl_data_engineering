#!/usr/bin/env python3
"""Weekly lineup setter: roster -> two projection sources -> league scoring -> deltas.

    python scripts/set_lineups.py --league mantis
    python scripts/set_lineups.py --league mantis --week 2 --threshold 2.5

Pulls the Sleeper roster, roster_positions and scoring_settings for a league
preset, scores OUR projections and Sleeper's weekly projections under those exact
settings (TE premium, 6-pt pass TD, first downs on the Sleeper side), and prints
only the deltas vs the lineup currently set. A swap is recommended only when both
sources agree by the threshold (default 3.0 pts); otherwise it is a coin flip.

OURS = the latest weekly Gold parquet for the week. When that board is thin
(< 150 skill rows — e.g. Week 1 of a new season, where the weekly engine has no
current-season usage yet) it falls back to preseason pace (season stats / 17) and
says so. ``*_derived`` boards are never read (see LINEUP_TOOL_ENHANCEMENT.md).

Sleeper only for now; ESPN/Yahoo need a roster reader (tracked in the doc).
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, sleeper_http  # noqa: E402
from src.league_scoring import unmodeled_offense_keys  # noqa: E402
from src.lineup_setter import (  # noqa: E402
    ET,
    _SKIP_SLOTS,
    MIN_WEEKLY_ROWS,
    SKILL_POSITIONS,
    InjuryContext,
    build_id_maps,
    build_rows,
    full_name_map,
    kickoffs_for_week,
    lineup_deltas,
    official_reports,
    ours_by_sleeper_id,
    preseason_to_weekly,
    render,
    roster_gsis_map,
    score_ours,
    sleeper_to_gsis,
    weekly_gold_to_stats,
)
from src.sleeper_player_map import (  # noqa: E402
    load_sleeper_players,
    normalize_name,
)

GOLD = REPO_ROOT / "data" / "gold" / "projections"
SCHEDULES = REPO_ROOT / "data" / "bronze" / "schedules"
ROSTERS = REPO_ROOT / "data" / "bronze" / "players" / "rosters"
INJURIES = REPO_ROOT / "data" / "bronze" / "players" / "injuries"
SENTIMENT = REPO_ROOT / "data" / "gold" / "sentiment"
# Injury tags go stale within a day in-season; the registry's default 7-day
# cache showed DJ Moore "Out" for a week after Sleeper had moved him to Q.
REGISTRY_MAX_AGE_DAYS = 0.25
_SNAP_TS = re.compile(r"(\d{8}_\d{6})")


def _latest(pattern: str, exclude: str = "derived") -> Optional[Path]:
    files = [f for f in glob.glob(pattern) if exclude not in os.path.basename(f)]
    return Path(max(files, key=os.path.getmtime)) if files else None


def _default_week(season_hint: Optional[int]) -> Tuple[int, int]:
    spec = importlib.util.spec_from_file_location(
        "resolve_pipeline_week", REPO_ROOT / "scripts" / "resolve_pipeline_week.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    season, week, _ = mod.resolve_target_week(dt.date.today())
    return (season_hint or season), week


def load_ours(season: int, week: int) -> Tuple[pd.DataFrame, str]:
    """Weekly Gold if healthy, else preseason pace. Returns (stat rows, label)."""
    weekly = _latest(
        str(GOLD / f"season={season}" / f"week={week}" / "projections_*.parquet")
    )
    if weekly is not None:
        df = pd.read_parquet(weekly)
        skill = (
            df[df["position"].isin(SKILL_POSITIONS)] if "position" in df.columns else df
        )
        if len(skill) >= MIN_WEEKLY_ROWS:
            age_h = (
                dt.datetime.now() - dt.datetime.fromtimestamp(weekly.stat().st_mtime)
            ).total_seconds() / 3600
            return (
                weekly_gold_to_stats(df),
                f"weekly Gold {weekly.name} ({age_h:.0f}h old)",
            )
        print(
            f"WARN: weekly board {weekly.name} has only {len(skill)} skill rows (< {MIN_WEEKLY_ROWS}); "
            "falling back to preseason pace"
        )
    pre = _latest(
        str(GOLD / "preseason" / f"season={season}" / "season_proj_*.parquet")
    )
    if pre is None:
        sys.exit(
            f"No usable projections for {season} week {week}. Generate one:\n"
            f"  python scripts/generate_projections.py --week {week} --season {season} --scoring ppr"
        )
    return (
        preseason_to_weekly(pd.read_parquet(pre)),
        f"preseason pace {pre.name} (season/17)",
    )


def load_injury_snapshots(season: int) -> pd.DataFrame:
    """Every Bronze nflverse injuries snapshot for *season*, with ``snapshot_at``.

    Each file is a full season-to-date pull (one practice status per
    player-week), so the daily snapshots are the only record of how a player's
    practice week went. Refreshed daily by ``daily-sentiment.yml``.
    """
    frames = []
    for f in sorted(
        glob.glob(str(INJURIES / f"season={season}" / "injuries_*.parquet"))
    ):
        m = _SNAP_TS.search(os.path.basename(f))
        if not m:
            continue
        df = pd.read_parquet(f)
        frames.append(
            df.assign(snapshot_at=dt.datetime.strptime(m.group(1), "%Y%m%d_%H%M%S"))
        )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def sentiment_flags(season: int, week: int) -> Dict[str, str]:
    """``gsis player_id -> "ruled_out,questionable"`` from the week's latest Gold
    sentiment file (falls back to the latest file of any week)."""
    files = sorted(
        glob.glob(
            str(SENTIMENT / f"season={season}" / f"week={week:02d}" / "*.parquet")
        )
    ) or sorted(glob.glob(str(SENTIMENT / "season=*" / "week=*" / "*.parquet")))
    if not files:
        return {}
    df = pd.read_parquet(files[-1])
    flags = [c for c in df.columns if c.startswith("is_")]
    out: Dict[str, str] = {}
    for row in df.itertuples(index=False):
        tags = [c[3:] for c in flags if getattr(row, c)]
        if tags:
            out[str(row.player_id)] = ",".join(tags)
    return out


def injury_context(
    season: int,
    week: int,
    registry: Dict[str, Any],
    gsis_map: Dict[str, str],
    weekly: pd.DataFrame,
) -> InjuryContext:
    """Official report for *week* + who played week-1, for resolve_injury_status."""
    snaps = load_injury_snapshots(season)
    reports, teams = official_reports(snaps, week)
    played_prev = None
    if (
        weekly is not None
        and not weekly.empty
        and {"week", "player_id"} <= set(weekly.columns)
    ):
        if (weekly["week"] == week - 1).any():
            played_prev = set(
                weekly.loc[weekly["week"] == week - 1, "player_id"].astype(str)
            )
    if snaps.empty:
        print(f"Injury report: no {season} snapshots in {INJURIES} — Sleeper tags only")
    else:
        print(
            f"Injury report: week {week} official lines for {len(reports)} players "
            f"({len(teams)} teams); latest snapshot "
            f"{snaps['snapshot_at'].max():%Y-%m-%d %H:%M}"
        )
    return InjuryContext(
        week=week,
        reports=reports,
        teams_reported=teams,
        played_prev=played_prev,
        gsis_by_sleeper=sleeper_to_gsis(registry, gsis_map),
    )


def news_by_sleeper(
    flags_by_gsis: Dict[str, str], registry: Dict[str, Any], gsis_map: Dict[str, str]
) -> Dict[str, str]:
    """Re-key gsis sentiment flags onto Sleeper ids."""
    to_sid = {g: s for s, g in sleeper_to_gsis(registry, gsis_map).items()}
    return {to_sid[g]: f for g, f in flags_by_gsis.items() if g in to_sid}


def load_sleeper_projections(season: int, week: int) -> Dict[str, Dict[str, Any]]:
    """Live Sleeper weekly projections keyed by sleeper player id."""
    url = config.SENTIMENT_CONFIG["sleeper_projections_url"].format(
        season=season, week=week
    )
    raw = sleeper_http.fetch_sleeper_json(url)
    if not raw:
        sys.exit(
            f"Sleeper projections unavailable ({url}) — refusing to recommend on one source."
        )
    if isinstance(
        raw, list
    ):  # defensive: some endpoints return a list of {player_id, stats}
        return {str(x.get("player_id")): (x.get("stats") or x) for x in raw}
    return {
        str(k): (v.get("stats") or v) for k, v in raw.items() if isinstance(v, dict)
    }


def find_my_roster(league_id: str, username: str) -> Dict[str, Any]:
    users = sleeper_http.get_league_users(league_id)
    me = next(
        (
            u
            for u in users
            if str(u.get("display_name", "")).lower() == username.lower()
        ),
        None,
    )
    if me is None:
        sys.exit(
            f"User '{username}' not in league {league_id}: {[u.get('display_name') for u in users]}"
        )
    rosters = sleeper_http.get_league_rosters(league_id)
    mine = next((r for r in rosters if r.get("owner_id") == me["user_id"]), None)
    if mine is None:
        sys.exit(f"No roster owned by {username} in league {league_id}")
    return mine


def last_week_bench_loss(
    league_id: str,
    username: str,
    season: int,
    week: int,
    registry: Mapping[str, Any],
    league: Mapping[str, Any],
) -> str:
    """One line: what last week's lineup left on the bench.

    Measured for the first time on 2026-10-23, after six weeks: a median 26.4
    points a week, of which 53% was already visible on our own board. A loss
    that size went unnoticed because nothing ever reported it, and the lineup
    tool is the one place it cannot be missed -- you are looking at it at
    exactly the moment the same decision comes round again.

    Returns "" when the previous week cannot be scored (week 1, a bye, or no
    matchup data), because an empty string is honest and a zero is not.
    """
    prior = week - 1
    if prior < 1:
        return ""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_bl", Path(__file__).resolve().parent / "backtest_lineups.py"
        )
        bl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bl)
        rosters = sleeper_http.fetch_sleeper_json(
            bl.MATCHUPS.format(lid=league_id, week=prior)
        )
        if not rosters:
            return ""
        users = {
            u["user_id"]: u.get("display_name")
            for u in sleeper_http.get_league_users(str(league_id))
        }
        mine = next(
            (
                str(r.get("roster_id"))
                for r in sleeper_http.get_league_rosters(str(league_id))
                if users.get(r.get("owner_id")) == username
            ),
            None,
        )
        roster = next((r for r in rosters if str(r.get("roster_id")) == mine), None)
        if roster is None:
            return ""
        slots = [s for s in (league.get("roster_positions") or []) if s != "BN"]
        positions = {
            sid: str((meta or {}).get("position") or "")
            for sid, meta in registry.items()
        }
        got = bl.week_regret(roster, slots, positions)
        if got is None:
            return ""
        actual, best = got
        lost = max(0.0, best - actual)
        if lost < 0.05:
            return f"\n  week {prior}: perfect lineup — nothing left on the bench."
        swaps = bl.missed_swaps(roster, slots, positions, limit=1)
        detail = ""
        if swaps:
            started, benched, gain = swaps[0]

            def name(sid: str) -> str:
                return str((registry.get(sid) or {}).get("full_name") or sid)

            detail = f" Worst: {name(started)} over {name(benched)} (-{gain:.1f})."
        return (
            f"\n  week {prior}: left {lost:.1f}pt on the bench.{detail}"
            f"\n  (room median is ~24.7pt/wk, so this is only bad if it is much"
            f" worse — scripts/backtest_lineups.py for the season view)"
        )
    except Exception as exc:  # noqa: BLE001 — a note must never break the tool
        return f"\n  (last week's bench loss unavailable: {type(exc).__name__})"


#: config.SCORING_CONFIGS keys -> the Sleeper scoring keys score_with_settings
#: understands. Same map waiver_wire.scoring_for uses; duplicated rather than
#: imported because importing one CLI from another drags its whole module in.
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

#: ROSTER_CONFIGS uses DST where Sleeper uses DEF.
_SHAPE_TO_SLEEPER_SLOT = {"DST": "DEF", "SFLEX": "SUPER_FLEX"}


def slots_from_shape(preset: Mapping[str, Any]) -> list:
    """A Sleeper-style flat slot list from a preset's ROSTER_CONFIGS shape.

    Sleeper publishes ``roster_positions`` as one entry per slot; ESPN and
    Yahoo do not publish it at all, but the shape is already in
    ``config.ROSTER_CONFIGS`` for every league we play. Bench slots are
    dropped: a lineup tool only allocates starters.
    """
    shape = config.ROSTER_CONFIGS[preset["roster"]]
    out = []
    for slot, count in shape.items():
        if slot == "BN":
            continue
        name = _SHAPE_TO_SLEEPER_SLOT.get(slot, slot)
        out.extend([name] * int(count))
    return out


def scoring_for_preset(preset: Mapping[str, Any]) -> Dict[str, float]:
    """Sleeper-keyed scoring for a league with no live settings feed.

    Mirrors ``waiver_wire.scoring_for`` for the no-league case so both tools
    price a pasted board the same way.
    """
    base = config.SCORING_CONFIGS[preset["scoring_format"]]
    return {_TO_SLEEPER_KEYS[k]: v for k, v in base.items() if k in _TO_SLEEPER_KEYS}


def roster_from_names(names: Sequence[str], registry: Mapping[str, Any]) -> list:
    """Sleeper ids for a list of player names.

    Unresolvable names are reported rather than dropped silently: a missing
    starter changes the lineup, and a D/ST or fullback that our registry has
    no entry for is a known gap, not a surprise.
    """
    _by_gsis, by_name = build_id_maps(dict(registry))
    ids, missing = [], []
    for raw in names:
        name = str(raw).split("#", 1)[0].strip()
        if not name:
            continue
        norm = normalize_name(name)
        hit = next((sid for (n, _pos), sid in by_name.items() if n == norm), None)
        if hit is None:
            missing.append(name)
        else:
            ids.append(hit)
    if missing:
        print(f"  not in the Sleeper registry (skipped): {', '.join(missing)}")
    return ids


def roster_from_file(path: Path, registry: Mapping[str, Any]) -> list:
    """Sleeper ids for the names in a pasted roster file."""
    return roster_from_names(
        Path(path).read_text(encoding="utf-8").splitlines(), registry
    )


def roster_from_espn(
    league_id: int, season: int, registry: Mapping[str, Any]
) -> Optional[list]:
    """Sleeper ids for our LIVE ESPN roster, or None when cookies are absent.

    A pasted file is a snapshot of whenever someone last pasted it. The one in
    the repo on 2026-10-24 was two days old and already wrong in six places --
    it still listed three players we had dropped and missed the three we added
    on waivers, so the lineup it produced was for a team we no longer had.
    With cookies, ESPN will just tell us.
    """
    from dotenv import load_dotenv

    load_dotenv()
    from src.espn_league import cookies_from_env, fetch_league, find_my_team_id
    from src.espn_lineup import espn_names_by_id

    cookies = cookies_from_env()
    if not cookies.get("SWID") or not cookies.get("espn_s2"):
        return None
    payload = fetch_league(
        league_id, season, views=["mRoster", "mTeam"], cookies=cookies
    )
    team_id = find_my_team_id(payload, cookies.get("SWID", ""))
    if team_id is None:
        return None
    names = list(espn_names_by_id(payload, team_id).values())
    print(f"  roster: {len(names)} players read live from ESPN")
    return roster_from_names(names, registry)


def recommended_starters(rows: Sequence[Any], roster_positions: Sequence[str]) -> list:
    """A starters list in ``roster_positions`` order, from the optimizer.

    Sleeper tells us which players are currently started, so the tool can show
    deltas against a real lineup. ESPN and Yahoo tell us nothing without a
    login, so there is no lineup to compare against — the honest output there
    is the lineup we RECOMMEND, allocated by the same optimizer, with the
    comparison left to the reader's own screen.

    ``"0"`` marks a slot the roster cannot fill (a missing D/ST, say).
    """
    from src.roster_optimizer import optimal_lineup

    pool = [r.as_optimizer_dict("blend") for r in rows]
    allocated = optimal_lineup(pool, roster_positions=list(roster_positions))
    by_slot: Dict[str, list] = {
        slot: [str(p["sleeper_id"]) for p in players]
        for slot, players in (allocated.get("starters") or {}).items()
    }
    out = []
    for slot in roster_positions:
        if str(slot).upper() in _SKIP_SLOTS:
            continue
        queue = by_slot.get(slot) or []
        out.append(queue.pop(0) if queue else "0")
    return out


def espn_write(
    preset: Mapping[str, Any],
    rows: Sequence[Any],
    starters: Sequence[str],
    roster_positions: Sequence[str],
    season: int,
    week: int,
    apply_changes: bool,
) -> int:
    """Diff our recommended lineup against ESPN's live one, and optionally file it.

    Printing is the default and applying is opt-in because this is the first
    code that can change a real roster without a human in the loop. Every
    refusal is loud: an unresolved name or an impossible slot aborts the whole
    plan rather than filing the part that happened to resolve, since a
    half-applied lineup benches a starter without starting his replacement.
    """
    from dotenv import load_dotenv

    load_dotenv()  # ESPN_S2 / ESPN_SWID live in .env, like every other script here

    from src.espn_league import (
        current_lineup_slots,
        fetch_league,
        find_my_team_id,
        cookies_from_env,
        submit_lineup,
    )
    from src.espn_lineup import (
        describe_moves,
        espn_names_by_id,
        espn_roster_index,
        plan_moves,
        resolve_players,
    )

    league_id = int(str(preset.get("league_id") or 0))
    if not league_id:
        print("ESPN write: this preset has no league_id")
        return 1

    cookies = cookies_from_env()
    if not cookies.get("SWID") or not cookies.get("espn_s2"):
        print("ESPN write: ESPN_S2 / ESPN_SWID are not set in .env")
        return 1

    payload = fetch_league(league_id, season, views=["mRoster", "mTeam"], cookies=cookies)
    team_id = find_my_team_id(payload, cookies.get("SWID", ""))
    if team_id is None:
        print("ESPN write: could not find which team this account owns")
        return 1

    index = espn_roster_index(payload, team_id)
    current = current_lineup_slots(league_id, season, team_id, week, cookies)
    names_by_sid = {str(r.sleeper_id): r.name for r in rows}
    labels = [s for s in roster_positions if str(s).upper() not in _SKIP_SLOTS]

    desired = [
        (label, names_by_sid.get(str(sid), str(sid)))
        for label, sid in zip(labels, starters)
        if str(sid) != "0"
    ]
    resolved, unresolved = resolve_players([n for _, n in desired], index)
    moves, problems = plan_moves(desired, resolved, current)

    print()
    print(f"ESPN lineup — league {league_id}, team {team_id}, week {week}")
    if unresolved:
        print("  unmatched on the ESPN roster: " + ", ".join(unresolved))
    if not moves and not problems:
        print("  already set — no moves needed")
        return 0
    names_by_pid = espn_names_by_id(payload, team_id)
    for line in describe_moves(moves, names_by_pid):
        print("  " + line)
    if problems:
        print()
        for why in problems:
            print(f"  BLOCKED: {why}")
        print("  Nothing was filed.")
        return 1
    if not apply_changes:
        print()
        print(f"  {len(moves)} move(s) — DRY RUN. Add --apply to file them.")
        return 0

    result = submit_lineup(league_id, season, team_id, week, moves, cookies)
    if result.get("status") == 0 or result.get("errors"):
        for why in result.get("errors") or [["", "refused"]]:
            print(f"  NOT FILED: {why[-1]}")
        return 1
    after = current_lineup_slots(league_id, season, team_id, week, cookies)
    landed = sum(1 for pid, _a, b in moves if after.get(pid) == b)
    print(f"  filed: HTTP {result.get('status')} — {landed}/{len(moves)} moves confirmed on read-back")
    return 0 if landed == len(moves) else 1


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", required=True, help="LEAGUE_PRESETS key (e.g. mantis)")
    ap.add_argument(
        "--week", type=int, help="NFL week (default: upcoming week per schedule)"
    )
    ap.add_argument("--season", type=int, help="Season (default: current)")
    ap.add_argument("--user", help="Sleeper display name (default: preset my_user)")
    ap.add_argument(
        "--roster-file",
        type=Path,
        help="ESPN/Yahoo: your roster, one player name per line (the same "
        "file the waiver report takes). Slots and scoring come from "
        "LEAGUE_PRESETS, so no login is needed.",
    )
    ap.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Min margin on BOTH sources for a SWAP",
    )
    ap.add_argument(
        "--espn-write",
        action="store_true",
        help="ESPN only: diff the recommended lineup against the live one and "
        "print the moves. Prints only; add --apply to file them.",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="With --espn-write, actually set the lineup on ESPN.",
    )
    args = ap.parse_args(argv)

    try:
        preset = config.our_league(args.league)
    except (KeyError, ValueError) as exc:
        sys.exit(exc.args[0])
    platform = preset.get("platform")
    if platform != "sleeper" and not args.roster_file:
        sys.exit(
            f"{args.league} is on {platform}, which publishes no roster we can read "
            "without a login. Pass --roster-file with your roster (one name per "
            "line) — the same file the waiver report takes. Slots and scoring come "
            "from LEAGUE_PRESETS, projections from our board plus Sleeper's, so "
            "nothing else is needed:\n"
            f"  python scripts/set_lineups.py --league {args.league} "
            f"--roster-file data/draft/{args.league}_2026_roster.txt"
        )
    username = args.user or preset.get("my_user") or args.league
    if platform == "sleeper" and not username:
        sys.exit("Pass --user <Sleeper display name> (preset has no my_user).")

    if args.season and args.week:
        season, week = args.season, args.week
    else:
        season, week = _default_week(args.season)
        week = args.week or week
    league_id = str(preset["league_id"])

    league = sleeper_http.get_league(league_id)
    registry = load_sleeper_players(max_age_days=REGISTRY_MAX_AGE_DAYS)
    if platform == "sleeper":
        if not league:
            sys.exit(f"Sleeper league {league_id} unavailable.")
        roster_positions = league.get("roster_positions") or []
        scoring = league.get("scoring_settings") or {}
        mine = find_my_roster(league_id, username)
    else:
        # ESPN and Yahoo expose no roster without a login, but the shape and
        # the scoring are already in LEAGUE_PRESETS and the roster is the same
        # pasted file the waiver report takes. Two of three teams had no
        # lineup tool at all purely because nobody wired this path.
        roster_positions = slots_from_shape(preset)
        scoring = scoring_for_preset(preset)
        live = (
            roster_from_espn(int(str(preset.get("league_id") or 0)), season, registry)
            if platform == "espn" and preset.get("league_id")
            else None
        )
        if live:
            # The live roster wins: a pasted file is only as fresh as the last
            # paste, and a lineup built for a team you no longer have is wrong
            # in a way no optimizer can recover from.
            mine = {"players": live}
        else:
            mine = {"players": roster_from_file(args.roster_file, registry)}

    ours_df, ours_label = load_ours(season, week)
    roster_files = sorted(
        glob.glob(str(ROSTERS / "season=*" / "**" / "*.parquet"), recursive=True)
    )
    rosters = (
        pd.concat([pd.read_parquet(f) for f in roster_files], ignore_index=True)
        if roster_files
        else pd.DataFrame()
    )
    weekly_files = sorted(
        glob.glob(str(REPO_ROOT / "data/bronze/players/weekly/season=*/*.parquet"))
    )
    weekly = pd.read_parquet(weekly_files[-1]) if weekly_files else pd.DataFrame()
    gsis_map = roster_gsis_map(rosters)
    ours = ours_by_sleeper_id(
        score_ours(ours_df, scoring),
        registry,
        gsis_map=gsis_map,
        full_names=full_name_map(rosters, weekly),
    )
    this_season_weekly = (
        weekly[weekly["season"] == season] if "season" in weekly.columns else weekly
    )
    sleeper_proj = load_sleeper_projections(season, week)

    sched_file = _latest(
        str(SCHEDULES / f"season={season}" / "*.parquet"), exclude="\0"
    )
    kickoffs = (
        kickoffs_for_week(pd.read_parquet(sched_file), week) if sched_file else {}
    )
    if not kickoffs:
        print(f"WARN: no schedule for {season} week {week}; lock/bye flags disabled")

    injury_ctx = injury_context(season, week, registry, gsis_map, this_season_weekly)
    rows = build_rows(
        player_ids=[
            p for p in mine.get("players") or [] if p not in (mine.get("taxi") or [])
        ],
        starters=mine.get("starters") or [],
        roster_positions=roster_positions,
        registry=registry,
        ours=ours,
        sleeper_proj=sleeper_proj,
        scoring_settings=scoring,
        kickoffs=kickoffs,
        now=dt.datetime.now(tz=ET),
        injury_ctx=injury_ctx,
        news=news_by_sleeper(sentiment_flags(season, week), registry, gsis_map),
    )
    if platform != "sleeper":
        # Second pass: the first had no starters to key off, so everything
        # rendered as bench. Allocate the recommendation and rebuild.
        mine["starters"] = recommended_starters(rows, roster_positions)
        rows = build_rows(
            player_ids=[p for p in mine.get("players") or []],
            starters=mine["starters"],
            roster_positions=roster_positions,
            registry=registry,
            ours=ours,
            sleeper_proj=sleeper_proj,
            scoring_settings=scoring,
            kickoffs=kickoffs,
            injury_ctx=injury_ctx,
            news=news_by_sleeper(sentiment_flags(season, week), registry, gsis_map),
        )
    deltas = lineup_deltas(rows, threshold=args.threshold)
    header = (
        f"{league.get('name', league_id)} — {username} — {season} week {week} "
        f"(threshold {args.threshold:.1f} on both sources)"
    )
    print(render(rows, deltas, header, ours_label))
    if platform != "sleeper":
        # The delta line below render() says "no bench player beats a starter",
        # which reads as "your lineup is fine". On a pasted roster there IS no
        # current lineup to compare against — the whole table is a
        # recommendation, and saying otherwise would be a claim we cannot make.
        unfilled = [
            slot
            for slot, pid in zip(
                [p for p in roster_positions if str(p).upper() not in _SKIP_SLOTS],
                mine.get("starters") or [],
            )
            if pid == "0"
        ]
        print(
            f"\n  NOTE: {platform} publishes no lineup without a login, so the SLOT"
            " column above is\n  what we RECOMMEND, not what you have set."
            " Compare it against your own screen."
        )
        if unfilled:
            print(
                f"  Could not fill: {', '.join(unfilled)} — our player registry has no"
                " D/ST or K\n  entries, so use scripts/stream_dst_k.py for those slots."
            )
    gaps = unmodeled_offense_keys(scoring)
    if gaps:
        print(f"\n  note: OURS cannot model {', '.join(gaps)} (Sleeper side does)")
    print(last_week_bench_loss(league_id, username, season, week, registry, league))

    if args.espn_write:
        if platform != "espn":
            print(f"\n--espn-write only applies to ESPN leagues ({platform} given)")
            return 1
        return espn_write(
            preset=preset,
            rows=rows,
            starters=mine.get("starters") or [],
            roster_positions=roster_positions,
            season=season,
            week=week,
            apply_changes=args.apply,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
