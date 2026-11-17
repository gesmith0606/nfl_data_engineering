#!/usr/bin/env python3
"""Replay the lineup tool against what actually happened, week by week.

    python scripts/replay_lineups.py                       # recorded fixture, every roster
    python scripts/replay_lineups.py --roster 6            # one roster's per-week table too
    python scripts/replay_lineups.py --collect --save out.json.gz --data-root <checkout>

This is the test bench for ``src/lineup_setter.py``. For every roster-week of a
finished Sleeper league it scores, in the league's own actual points:

    set          the lineup the manager really set
    v1 rule      the original tool's SWAPs (both sources agree by 3.0) applied to it
    v1 blend     the original tool's blended-optimal lineup
    sleeper/ours the optimal lineup under one projection source alone
    hindsight    the best lineup the roster could have fielded (not achievable)
    tool         the CURRENT tool (MUST FIX repairs + its swap rule) applied to the set lineup
    carry        last week's lineup carried over unchanged, raw / v1 / current tool

``carry`` is the stress test for dead slots: nobody touched that lineup, so every
bye and ruled-out starter is still in it. Judge a change by these actual points,
never by agreement with Sleeper (lessons in .planning/): the baselines here do not
depend on the tool, and n is printed with every table.

Inputs are frozen in a fixture (``tests/fixtures/lineup_replay``) so the replay is
reproducible and needs no network. ``--collect`` builds a fresh one from local
data plus Sleeper's public API. Caveat recorded in the fixture's ``meta``: until
``scripts/snapshot_gameday_inputs.py`` has been running, past weeks' Sleeper
projections are what the API serves TODAY, not what was known at kickoff, and
past injury tags are gone (only the official nflverse report, as of Sunday
09:00 ET, is replayed).
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import gzip
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.lineup_setter import (  # noqa: E402
    ET,
    MIN_WEEKLY_ROWS,
    SKILL_POSITIONS,
    InjuryContext,
    OfficialReport,
    apply_swaps,
    build_rows,
    full_name_map,
    kickoffs_for_week,
    lineup_deltas,
    official_reports,
    optimal_by_source,
    ours_by_sleeper_id,
    preseason_to_weekly,
    recommend,
    roster_gsis_map,
    score_ours,
    sleeper_to_gsis,
    weekly_gold_to_stats,
)
from src.roster_optimizer import _SKIP_SLOTS, optimal_lineup  # noqa: E402

FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "lineup_replay" / "mantis_2026_w1_9.json.gz"
)
THRESHOLD = 3.0
_TS = re.compile(r"(\d{8}_\d{6})")
# Current Sleeper injury tags are not the tags that existed at replay time.
_STRIP = ("injury_status", "injury_body_part", "practice_participation", "news_updated")
_KEEP_META = (
    "position",
    "team",
    "full_name",
    "first_name",
    "last_name",
    "depth_chart_order",
)


# ---------------------------------------------------------------------------
# Fixture IO
# ---------------------------------------------------------------------------


def load_fixture(path: Path = FIXTURE) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def save_fixture(data: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(data, fh, separators=(",", ":"), sort_keys=True)


# ---------------------------------------------------------------------------
# Pure replay
# ---------------------------------------------------------------------------


def _score_stats(
    stats: Mapping[str, Mapping[str, Any]], scoring: Mapping[str, Any]
) -> Dict[str, float]:
    """``{sleeper_id: league points}`` for our stat lines (the same path the CLI uses)."""
    if not stats:
        return {}
    df = pd.DataFrame.from_dict(stats, orient="index")
    return score_ours(df, dict(scoring))["projected_points"].astype(float).to_dict()


def _injury_ctx(week: int, inj: Mapping[str, Any]) -> InjuryContext:
    """Fixture injury block -> InjuryContext. Sleeper ids stand in for gsis ids."""
    reports = {
        sid: OfficialReport(
            r.get("game_status"),
            r.get("injury"),
            tuple(r.get("practice") or ()),
            dt.datetime.fromisoformat(r["as_of"]) if r.get("as_of") else None,
        )
        for sid, r in (inj.get("reports") or {}).items()
    }
    played = inj.get("played_prev")
    return InjuryContext(
        week=week,
        reports=reports,
        teams_reported=set(inj.get("teams_reported") or ()),
        played_prev=None if played is None else set(played),
        gsis_by_sleeper={sid: sid for sid in (inj.get("sids") or ())},
    )


def _score(ids: Iterable[str], pts: Mapping[str, float]) -> float:
    return round(sum(pts.get(i, 0.0) for i in ids if i and i != "0"), 2)


def _hindsight(slots: Sequence[str], players: Sequence[str], pts, positions) -> float:
    from scripts import backtest_lineups as bl

    return round(
        bl.optimal_points(list(slots), list(players), dict(pts), dict(positions)), 2
    )


def replay_roster_week(
    data: Mapping[str, Any],
    week: int,
    matchup: Mapping[str, Any],
    prev: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Every lineup variant for one roster-week, in actual points, plus diagnostics."""
    wk = data["weeks"][str(week)]
    league = data["league"]
    rp, scoring = league["roster_positions"], league["scoring_settings"]
    registry = data["registry"]
    if wk.get(
        "status"
    ):  # Sleeper tags as saved before kickoff (snapshot_gameday_inputs)
        registry = {
            sid: {**m, **wk["status"].get(sid, {})} for sid, m in registry.items()
        }
    positions = {sid: str(m.get("position") or "") for sid, m in registry.items()}
    slots = [p for p in rp if p.upper() not in _SKIP_SLOTS]
    rid = matchup["roster_id"]

    pts = {
        str(k): float(v or 0) for k, v in (matchup.get("players_points") or {}).items()
    }
    starters = [str(s) for s in matchup["starters"]]
    taxi = {t for t in data["taxi"].get(str(rid), []) if t not in starters}
    players = [str(p) for p in matchup["players"] if str(p) not in taxi]

    ours_all = _score_stats(wk["ours_stats"], scoring)
    # The current tool treats a preseason-pace board as no board at all.
    ours_tool = {} if wk["ours_kind"] != "weekly" else ours_all
    sleeper = wk["sleeper_stats"]
    kick = {t: dt.datetime.fromisoformat(v) for t, v in wk["kickoffs"].items()}
    now_sun = dt.datetime.fromisoformat(wk["now_sun"])
    now_pre = dt.datetime.fromisoformat(wk["now_pre"])
    ictx = _injury_ctx(week, wk["injury"])

    def rows_at(ours, now, ids=players, st=starters):
        return build_rows(
            ids, st, rp, registry, ours, sleeper, scoring, kick, now, ictx
        )

    def row_by_id(rows):
        return {r.sleeper_id: r for r in rows}

    def dead_in(ids, rows):
        by = row_by_id(rows)
        return sum(1 for i in ids if i in by and by[i].dead)

    def zeros_in(ids):
        return sum(1 for i in ids if i and i != "0" and pts.get(i, 0.0) == 0.0)

    rec: Dict[str, Any] = dict(
        week=week, rid=rid, ours_label=wk["ours_label"], ours_kind=wk["ours_kind"],
        set=_score(starters, pts),
    )  # fmt: skip

    # --- the lineup actually set, as of Sunday 09:00 ET (Thursday games locked)
    rows_sun = rows_at(ours_all, now_sun)
    legacy = lineup_deltas(rows_sun, THRESHOLD, legacy=True)
    rec["v1_rule"] = _score(apply_swaps(starters, legacy), pts)
    rec["v1_deltas"] = [
        dict(
            v=d.verdict,
            gain=pts.get(d.in_player.sleeper_id, 0)
            - pts.get(d.out_player.sleeper_id, 0),
        )
        for d in legacy
    ]
    tool_rows = rows_at(ours_tool, now_sun)
    got = recommend(tool_rows, rp, starters, THRESHOLD)
    rec["tool"] = _score(got.starters, pts)
    rec["tool_fixes"] = len([f for f in got.must_fix if f.in_player is not None])
    rec["tool_deltas"] = [
        dict(
            v=d.verdict,
            gain=pts.get(d.in_player.sleeper_id, 0)
            - pts.get(d.out_player.sleeper_id, 0),
        )
        for d in got.deltas
    ]
    rec["dead_set"] = dead_in(starters, tool_rows)
    rec["dead_tool"] = dead_in(got.starters, tool_rows)
    rec["zero_set"], rec["zero_tool"] = zeros_in(starters), zeros_in(got.starters)
    rec["empty_tool"] = got.starters.count("0")

    # --- single-source and blended optima (nothing locked: the pre-slate view)
    rows_pre = rows_at(ours_all, now_pre)
    pool = [r.as_optimizer_dict("blend") for r in rows_pre]
    lu = optimal_lineup(pool, roster_positions=list(rp))
    rec["v1_blend"] = _score(
        [p["sleeper_id"] for ps in lu["starters"].values() for p in ps], pts
    )
    rec["sleeper_only"] = _score(optimal_by_source(rows_pre, rp, "sleeper"), pts)
    rec["ours_only"] = _score(optimal_by_source(rows_pre, rp, "ours"), pts)
    rec["hindsight"] = _hindsight(slots, players, pts, positions)
    rec["n_no_ours"] = sum(
        1 for r in rows_pre if r.ours is None and r.position in SKILL_POSITIONS
    )

    # --- last week's lineup carried over untouched (nobody fixed a bye)
    if prev is not None:
        carried = [s if s in players else "0" for s in map(str, prev["starters"])]
        rows_c = rows_at(ours_tool, now_pre, st=carried)
        rec["carry_raw"] = _score(carried, pts)
        rec["dead_carry"] = dead_in(carried, rows_c)
        rec["zero_carry"] = zeros_in(carried)
        rec["empty_carry"] = carried.count("0")
        rec["carry_tool"] = _score(
            recommend(rows_c, rp, carried, THRESHOLD).starters, pts
        )
        rec["dead_carry_tool"] = dead_in(
            recommend(rows_c, rp, carried, THRESHOLD).starters, rows_c
        )
        st = list(carried)
        for _ in range(10):  # the old tool, applied repeatedly to the carried lineup
            ds = lineup_deltas(
                rows_at(ours_all, now_pre, st=st), THRESHOLD, legacy=True
            )
            nxt = apply_swaps(st, ds)
            if nxt == st:
                break
            st = nxt
        rec["carry_v1"] = _score(st, pts)
        rec["zero_carry_tool"] = zeros_in(
            recommend(rows_c, rp, carried, THRESHOLD).starters
        )
    return rec


def replay(
    data: Mapping[str, Any], weeks: Optional[Iterable[int]] = None
) -> List[Dict[str, Any]]:
    """Replay every roster-week; ``weeks`` defaults to every week in the fixture."""
    out: List[Dict[str, Any]] = []
    have = sorted(int(w) for w in data["weeks"])
    for w in weeks or have:
        wk = data["weeks"][str(w)]
        prev = (
            {m["roster_id"]: m for m in data["weeks"][str(w - 1)]["matchups"]}
            if str(w - 1) in data["weeks"]
            else {}
        )
        for m in wk["matchups"]:
            out.append(replay_roster_week(data, w, m, prev.get(m["roster_id"])))
    return out


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

_COLS = ["set", "v1_rule", "v1_blend", "sleeper_only", "ours_only", "hindsight", "tool"]
_CARRY = ["carry_raw", "carry_v1", "carry_tool"]


def totals(recs: Sequence[Mapping[str, Any]], cols: Sequence[str]) -> Dict[str, float]:
    return {c: round(sum(r.get(c) or 0.0 for r in recs), 1) for c in cols}


def verdict_stats(recs: Sequence[Mapping[str, Any]], key: str) -> pd.DataFrame:
    rows = [d for r in recs for d in r.get(key, [])]
    if not rows:
        return pd.DataFrame(columns=["n", "hit", "mean", "total"])
    df = pd.DataFrame(rows)
    return (
        df.groupby("v")["gain"]
        .agg(n="count", hit=lambda x: (x > 0).mean(), mean="mean", total="sum")
        .round(2)
    )


def render_summary(
    recs: Sequence[Mapping[str, Any]], roster: Optional[int] = None
) -> str:
    out: List[str] = []
    n = len(recs)
    weeks = sorted({r["week"] for r in recs})
    out.append(f"League-wide: {n} roster-weeks, weeks {weeks[0]}-{weeks[-1]}")
    t = totals(recs, _COLS)
    out.append("  " + "  ".join(f"{c}={t[c]:.1f}" for c in _COLS))
    out.append(
        "  vs set, per roster-week: "
        + "  ".join(f"{c}={(t[c] - t['set']) / n:+.2f}" for c in _COLS[1:])
    )
    carry = [r for r in recs if "carry_raw" in r]
    if carry:
        tc = totals(carry, _CARRY)
        out.append(
            f"Carried-over lineups: n={len(carry)} roster-weeks (week {min(r['week'] for r in carry)}+)"
        )
        out.append("  " + "  ".join(f"{c}={tc[c]:.1f}" for c in _CARRY))
        out.append(
            "  starters who cannot play (bye/Out/IR/Doubtful/no team): "
            f"carried {sum(r['dead_carry'] for r in carry)}  after tool {sum(r['dead_carry_tool'] for r in carry)}"
            f"   | starters who scored exactly 0: carried {sum(r['zero_carry'] for r in carry)}"
            f"  after tool {sum(r['zero_carry_tool'] for r in carry)}   | empty slots carried {sum(r['empty_carry'] for r in carry)}"
        )
    out.append(
        f"Set lineups: dead starters set {sum(r['dead_set'] for r in recs)} -> tool {sum(r['dead_tool'] for r in recs)}"
        f";  zero-point starters set {sum(r['zero_set'] for r in recs)} -> tool {sum(r['zero_tool'] for r in recs)}"
        f";  MUST FIX replacements {sum(r['tool_fixes'] for r in recs)}"
    )
    for label, key in (
        ("v1 rule verdicts on set lineups", "v1_deltas"),
        ("current tool verdicts on set lineups", "tool_deltas"),
    ):
        out += [
            f"{label} (gain = actual points of bench minus starter):",
            verdict_stats(recs, key).to_string(),
        ]
    if roster is not None:
        mine = [r for r in recs if r["rid"] == roster]
        cols = _COLS + [c for c in _CARRY if any(c in r for r in mine)]
        out.append(f"\nRoster {roster}, n={len(mine)} weeks")
        out.append("wk " + " ".join(f"{c[:11]:>11}" for c in cols))
        for r in mine:
            out.append(
                f"{r['week']:<2} "
                + " ".join(f"{r.get(c, float('nan')):11.2f}" for c in cols)
                + f"   [{r['ours_kind']}]"
            )
        tm = totals(mine, cols)
        out.append("TOT" + " ".join(f"{tm[c]:11.1f}" for c in cols))
        out.append("vs " + " ".join(f"{tm[c] - tm['set']:+11.1f}" for c in cols))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Collector: build a fixture from local data + Sleeper's public API
# ---------------------------------------------------------------------------


def _ts_of(path: str) -> dt.datetime:
    return dt.datetime.strptime(
        _TS.search(os.path.basename(path)).group(1), "%Y%m%d_%H%M%S"
    )


def pick_board(files: Sequence[str], cutoff_utc: dt.datetime) -> Optional[str]:
    """Newest non-derived board stamped at or before the cutoff, by FILENAME time.

    Filesystem mtime is not the board's time: a checkout or a copy rewrites it,
    which is how the live tool once picked a board that was not the newest.
    """
    ok = [
        f
        for f in files
        if "derived" not in os.path.basename(f) and _TS.search(os.path.basename(f))
    ]
    ok = [f for f in ok if _ts_of(f) <= cutoff_utc]
    return max(ok, key=_ts_of) if ok else None


def sunday_of(schedule: pd.DataFrame, week: int) -> dt.date:
    """The week's Sunday (its first Sunday gameday; first gameday if there is none)."""
    days = sorted(
        dt.date.fromisoformat(str(d))
        for d in schedule.loc[schedule["week"] == week, "gameday"].dropna()
    )
    sundays = [d for d in days if d.weekday() == 6]
    return sundays[0] if sundays else days[0]


def _fetch(cache: Path, name: str, url: str) -> Any:
    p = cache / f"{name}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    from src import sleeper_http

    got = sleeper_http.fetch_sleeper_json(url)
    if not got:
        raise RuntimeError(f"Sleeper returned nothing for {url}")
    cache.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(got), encoding="utf-8")
    return got


def collect_inputs(
    league_id: str,
    season: int,
    weeks: Sequence[int],
    data_root: Path,
    cache: Path,
    my_roster_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Freeze everything the replay needs. Reads ``data_root`` and Sleeper only."""
    api = "https://api.sleeper.app/v1"
    league = _fetch(cache, "league", f"{api}/league/{league_id}")
    rosters_now = _fetch(cache, "rosters", f"{api}/league/{league_id}/rosters")
    registry_full = json.loads(
        (data_root / "data/bronze/players/sleeper_players.json").read_text(
            encoding="utf-8"
        )
    )
    registry_full = {k: v for k, v in registry_full.items() if isinstance(v, dict)}
    bronze_rosters = pd.concat(
        [
            pd.read_parquet(f)
            for f in sorted(
                glob.glob(
                    str(
                        data_root / "data/bronze/players/rosters/season=*/**/*.parquet"
                    ),
                    recursive=True,
                )
            )
        ],
        ignore_index=True,
    )
    weekly_files = sorted(
        glob.glob(str(data_root / "data/bronze/players/weekly/season=*/*.parquet"))
    )
    weekly = pd.read_parquet(weekly_files[-1])
    weekly = weekly[weekly["season"] == season]
    sched = pd.read_parquet(
        sorted(
            glob.glob(
                str(data_root / f"data/bronze/schedules/season={season}/*.parquet")
            )
        )[-1]
    )
    inj = pd.concat(
        [
            pd.read_parquet(f).assign(snapshot_at=_ts_of(f))
            for f in sorted(
                glob.glob(
                    str(
                        data_root
                        / f"data/bronze/players/injuries/season={season}/injuries_*.parquet"
                    )
                )
            )
        ],
        ignore_index=True,
    )
    gsis_map = roster_gsis_map(bronze_rosters)
    names = full_name_map(bronze_rosters, weekly)
    gsis_by_sleeper = sleeper_to_gsis(registry_full, gsis_map)
    scoring = league["scoring_settings"]

    out_weeks: Dict[str, Any] = {}
    sources: Dict[str, str] = {}
    gameday_root = data_root / "data" / "bronze" / "gameday_inputs"
    all_sids: set = set()
    for w in weeks:
        matchups = _fetch(
            cache, f"matchups_{w}", f"{api}/league/{league_id}/matchups/{w}"
        )
        proj_raw = _fetch(
            cache, f"proj_{w}", f"{api}/projections/nfl/regular/{season}/{w}"
        )
        sids = {str(p) for m in matchups for p in (m.get("players") or [])}
        all_sids |= sids
        sunday = sunday_of(sched, w)
        now_sun = dt.datetime(sunday.year, sunday.month, sunday.day, 9, 0, tzinfo=ET)
        cutoff = dt.datetime(sunday.year, sunday.month, sunday.day, 13, 0, tzinfo=ET)
        to_utc = lambda t: t.astimezone(dt.timezone.utc).replace(
            tzinfo=None
        )  # noqa: E731
        kick = kickoffs_for_week(sched, w)
        now_pre = min(kick.values()) - dt.timedelta(hours=1)

        # our board as it stood at Sunday 13:00 ET (the 2026 Sunday refresh runs just before)
        board = pick_board(
            glob.glob(
                str(
                    data_root
                    / f"data/gold/projections/season={season}/week={w}/projections_*.parquet"
                )
            ),
            to_utc(cutoff),
        )
        kind, label, stats = "preseason_pace", "", None
        published, fmt = None, None
        if board:
            df = pd.read_parquet(board)
            skill = df[df["position"].isin(SKILL_POSITIONS)]
            if len(skill) >= MIN_WEEKLY_ROWS:
                kind, label, stats = (
                    "weekly",
                    f"{os.path.basename(board)} ({len(skill)} skill rows)",
                    weekly_gold_to_stats(df),
                )
                # the board's own number: calibrated, in the board's scoring format
                published = df["projected_points"].to_numpy(dtype=float)
                fmt = re.search(r"projections_(.+?)_[0-9]{8}_", os.path.basename(board))
                fmt = fmt.group(1) if fmt else None
        if stats is None:
            pre = pick_board(
                glob.glob(
                    str(
                        data_root
                        / f"data/gold/projections/preseason/season={season}/season_proj_*.parquet"
                    )
                ),
                to_utc(cutoff),
            )
            label, stats = (
                f"PRESEASON PACE {os.path.basename(pre)}",
                preseason_to_weekly(pd.read_parquet(pre)),
            )
        idx = ours_by_sleeper_id(
            stats.assign(projected_points=np.arange(len(stats), dtype=float)),
            registry_full,
            gsis_map=gsis_map,
            full_names=names,
        )
        stat_cols = [
            c
            for c in stats.columns
            if c not in ("player_id", "player_name", "recent_team")
        ]
        ours_stats = {}
        for sid in sids & set(idx):
            row = stats.iloc[int(idx[sid])]
            ours_stats[sid] = {
                c: (
                    None
                    if pd.isna(row[c])
                    else (row[c] if c == "position" else float(row[c]))
                )
                for c in stat_cols
            }
            if published is not None:
                ours_stats[sid]["published"] = float(published[int(idx[sid])])

        # Prefer what was saved before kickoff; the API only serves today's values.
        from scripts import snapshot_gameday_inputs as snap

        saved = snap.read_projections(gameday_root, season, w, to_utc(cutoff))
        status = (
            snap.read_status(gameday_root, season, w, to_utc(now_sun))
            if saved is not None
            else None
        )
        sources[str(w)] = (
            "snapshot taken before kickoff"
            if saved is not None
            else "API as served on collection day"
        )
        sleeper_stats = {}
        for sid in sids:
            v = (saved or {}).get(sid) if saved is not None else proj_raw.get(sid)
            if saved is None and isinstance(v, dict):
                v = v.get("stats") or v
            if isinstance(v, dict) and v:
                sleeper_stats[sid] = v

        reports, teams = official_reports(inj[inj["snapshot_at"] <= to_utc(now_sun)], w)
        by_sid = {}
        for sid in sids:
            g = gsis_by_sleeper.get(sid)
            if g and g in reports:
                r = reports[g]
                by_sid[sid] = dict(
                    game_status=r.game_status,
                    injury=r.injury,
                    practice=list(r.practice),
                    as_of=r.as_of.isoformat() if r.as_of else None,
                )
        played = None
        if w > 1:
            prev_ids = set(weekly.loc[weekly["week"] == w - 1, "player_id"].astype(str))
            played = sorted(sid for sid in sids if gsis_by_sleeper.get(sid) in prev_ids)
        out_weeks[str(w)] = dict(
            ours_kind=kind, ours_label=label, ours_format=fmt, ours_stats=ours_stats, sleeper_stats=sleeper_stats,
            kickoffs={t: k.isoformat() for t, k in kick.items()},
            now_sun=now_sun.isoformat(), now_pre=now_pre.isoformat(),
            injury=dict(reports=by_sid, teams_reported=sorted(teams), played_prev=played, sids=sorted(sids)),
            status={sid: status[sid] for sid in sids if status and sid in status} if status else None,
            matchups=[{k: m[k] for k in ("roster_id", "players", "starters", "players_points")} for m in matchups],
        )  # fmt: skip
    return dict(
        meta=dict(
            league_id=league_id,
            season=season,
            my_roster_id=my_roster_id,
            weeks=list(weeks),
            sleeper_projection_source_by_week=sources,
            injury_source="official nflverse report as of Sunday 09:00 ET; Sleeper tags only for weeks with a status snapshot",
        ),  # fmt: skip
        league=dict(
            name=league.get("name"),
            roster_positions=league["roster_positions"],
            scoring_settings=scoring,
        ),
        registry={
            sid: {
                k: registry_full[sid].get(k)
                for k in _KEEP_META
                if registry_full[sid].get(k) is not None
            }
            for sid in sorted(all_sids)
            if sid in registry_full
        },
        taxi={
            str(r["roster_id"]): [str(t) for t in (r.get("taxi") or [])]
            for r in rosters_now
        },
        weeks=out_weeks,
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--fixture", type=Path, default=FIXTURE)
    ap.add_argument("--weeks", help="e.g. 1-5 or 6-9 (default: all in the fixture)")
    ap.add_argument(
        "--roster",
        type=int,
        help="print this roster's per-week table (default: the fixture's own)",
    )
    ap.add_argument(
        "--collect",
        action="store_true",
        help="build a fixture from local data + Sleeper's public API",
    )
    ap.add_argument("--save", type=Path, help="with --collect: write the fixture here")
    ap.add_argument(
        "--data-root",
        type=Path,
        default=REPO_ROOT,
        help="checkout holding data/ (read-only)",
    )
    ap.add_argument("--cache", type=Path, default=REPO_ROOT / "output" / "replay_cache")
    ap.add_argument("--league", default="mantis")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--my-roster", type=int, default=6)
    args = ap.parse_args(argv)

    def parse_weeks(spec: Optional[str]) -> Optional[List[int]]:
        if not spec:
            return None
        a, _, b = spec.partition("-")
        return list(range(int(a), int(b or a) + 1))

    if args.collect:
        from src import config

        weeks = parse_weeks(args.weeks) or list(range(1, 10))
        data = collect_inputs(
            str(config.our_league(args.league)["league_id"]),
            args.season,
            weeks,
            args.data_root,
            args.cache,
            args.my_roster,
        )
        if args.save:
            save_fixture(data, args.save)
            print(
                f"fixture written: {args.save} ({args.save.stat().st_size / 1024:.0f} KB)"
            )
    else:
        data = load_fixture(args.fixture)
    recs = replay(data, parse_weeks(args.weeks))
    print(
        render_summary(
            recs,
            (
                args.roster
                if args.roster is not None
                else data["meta"].get("my_roster_id")
            ),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
