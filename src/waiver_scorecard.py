"""Scorecard for the waiver advice: what the claims scored, what they cost.

``audit_waiver_skill.py`` checks that the machinery exists and
``recommendation_backtest.py`` asks whether the board's ranking beats a
shuffle. Neither answers the question George asked on 2026-11-15: *did the
claims we filed pay off, and did we pay the price it took?* This does, from the
league's own transaction log and the week's actual box scores, so it needs no
opinion about the model:

* **Claims.** For each add we filed, points over the next 1, 2 and 4 weeks
  against (a) the player we dropped for him, (b) the board's own #1 at that
  position, (c) the best free agent at that position in hindsight.
* **Listed names.** Same windows for everyone the report printed, by listing
  method, so a ranking change is judged by what the names went on to score.
* **Bids.** Price paid against the clearing price: the runner-up's bid + 1, or
  $1 when nobody else bid. A claim is lost only if a rival bids above you, so
  everything over that was spent for nothing.

Pure functions over plain dicts (Sleeper's own transaction shape); the file and
network reads live in ``scripts/waiver_scorecard.py``.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS
#: Next 1, 2 and 4 weeks, the windows the plan is judged on.
WINDOWS = (1, 2, 4)
#: Waivers run Wednesday morning; the report is read Tuesday evening. 22h after
#: a Tuesday-00:00-ET week start is Tuesday 18:00 ET (17:00 in standard time).
CUTOFF_HOURS = 22
#: A rival claim within this of ours is a claim for the same processing run.
CONTEST_MS = 2 * DAY_MS

Pts = Callable[[str, int], float]


# ---------------------------------------------------------------------- points


def league_points(stats: Mapping[str, Any], scoring: Mapping[str, float]) -> float:
    """A Sleeper stat line under the league's own ``scoring_settings``.

    ``bonus_rec_te`` is already a per-reception stat key in the stats feed, so
    this is a plain dot product (unlike the projection feed, which needs the
    position to apply it).
    """
    return sum(
        float(v) * scoring[k]
        for k, v in stats.items()
        if k in scoring and isinstance(v, (int, float))
    )


def window(pts: Pts, pid: str, week: int, n: int, last_week: int) -> Tuple[float, int]:
    """Points over weeks ``week .. week+n-1`` clipped to the last complete week.

    Returns ``(points, weeks_counted)`` so a truncated window is visible
    instead of looking like a bad player.
    """
    weeks = [w for w in range(week, week + n) if w <= last_week]
    return sum(pts(pid, w) for w in weeks), len(weeks)


def attach_windows(
    rows: Iterable[Mapping[str, Any]], week: int, pts: Pts, last_week: int
) -> List[Dict[str, Any]]:
    """Copy ``rows`` with ``p1/p2/p4`` = the next 1/2/4 weeks from ``week``."""
    out = []
    for r in rows:
        d = dict(r)
        for n in WINDOWS:
            d[f"p{n}"] = window(pts, str(r["sid"]), week, n, last_week)[0]
        out.append(d)
    return out


# ------------------------------------------------------------------ time / pool


def nfl_week(ts_ms: int, week1_start: int) -> int:
    """The NFL week a move belongs to; preseason moves count as week 1."""
    return max(1, int((ts_ms - week1_start) // WEEK_MS) + 1)


def week_cutoff(week: int, week1_start: int) -> int:
    """Tuesday evening of ``week``: what the report could have seen."""
    return week1_start + (week - 1) * WEEK_MS + CUTOFF_HOURS * 3_600_000


def rostered_at(
    rosters_now: Mapping[Any, Iterable[str]],
    txs: Sequence[Mapping[str, Any]],
    when_ms: int,
) -> Set[str]:
    """Who was on a roster at ``when_ms``, by undoing every later move.

    Sleeper only serves today's rosters; the completed transactions after
    ``when_ms`` are reversed (adds removed, drops restored) to get back.
    """
    cur = {rid: {str(p) for p in ps} for rid, ps in rosters_now.items()}
    for t in sorted(txs, key=lambda t: t["status_updated"], reverse=True):
        if t.get("status") != "complete":
            continue
        if t["status_updated"] <= when_ms:
            break
        for pid, rid in (t.get("adds") or {}).items():
            cur.setdefault(rid, set()).discard(str(pid))
        for pid, rid in (t.get("drops") or {}).items():
            cur.setdefault(rid, set()).add(str(pid))
    return set().union(*cur.values()) if cur else set()


# ------------------------------------------------------------------ the ledger


def _bid(t: Mapping[str, Any]) -> int:
    return int((t.get("settings") or {}).get("waiver_bid") or 0)


def filed_adds(
    txs: Sequence[Mapping[str, Any]], roster_id: int, week1_start: int
) -> List[Dict[str, Any]]:
    """The in-season adds ``roster_id`` completed, each with the drop made for it."""
    out: List[Dict[str, Any]] = []
    for t in sorted(txs, key=lambda t: t["status_updated"]):
        if t.get("status") != "complete" or t.get("type") == "trade":
            continue
        if roster_id not in (t.get("roster_ids") or []):
            continue
        if t["status_updated"] < week1_start:
            continue
        adds = [p for p, r in (t.get("adds") or {}).items() if r == roster_id]
        drops = [p for p, r in (t.get("drops") or {}).items() if r == roster_id]
        for i, pid in enumerate(adds):
            out.append(
                {
                    "add": str(pid),
                    "drop": str(drops[i]) if i < len(drops) else None,
                    "bid": _bid(t),
                    "week": nfl_week(t["status_updated"], week1_start),
                    "ts": t["status_updated"],
                    "type": t.get("type"),
                }
            )
    return out


def _claims_for(
    win: Mapping[str, Any], txs: Sequence[Mapping[str, Any]], pid: str, status: str
) -> List[Mapping[str, Any]]:
    """Other rosters' claims on ``pid`` in the same processing run as ``win``."""
    mine = set(win.get("roster_ids") or [])
    return [
        x
        for x in txs
        if x.get("status") == status
        and pid in (x.get("adds") or {})
        and abs(x["status_updated"] - win["status_updated"]) < CONTEST_MS
        and not mine & set(x.get("roster_ids") or [])
    ]


def clearing_price(win: Mapping[str, Any], txs: Sequence[Mapping[str, Any]]) -> int:
    """What it took to win: the best losing rival bid + 1, never below $1."""
    pid = next(iter(win.get("adds") or {}), None)
    if pid is None:
        return 1
    top = max((_bid(x) for x in _claims_for(win, txs, str(pid), "failed")), default=0)
    return max(1, top + 1)


def score_bids(
    txs: Sequence[Mapping[str, Any]], roster_id: Optional[int], week1_start: int
) -> Dict[str, Any]:
    """Price paid vs clearing price for every waiver claim ``roster_id`` won.

    ``roster_id=None`` scores the whole room, which is the base rate for how
    often a claim is contested at all.
    """
    rows: List[Dict[str, Any]] = []
    for t in sorted(txs, key=lambda t: t["status_updated"]):
        if t.get("status") != "complete" or t.get("type") != "waiver":
            continue
        if roster_id is not None and roster_id not in (t.get("roster_ids") or []):
            continue
        if t["status_updated"] < week1_start or not t.get("adds"):
            continue
        pid = str(next(iter(t["adds"])))
        rivals = sorted(
            (_bid(x) for x in _claims_for(t, txs, pid, "failed")), reverse=True
        )
        rows.append(
            {
                "add": pid,
                "week": nfl_week(t["status_updated"], week1_start),
                "paid": _bid(t),
                "clearing": max(1, (rivals[0] if rivals else 0) + 1),
                "rivals": len(rivals),
                "rival_bids": rivals,
            }
        )
    return {
        "rows": rows,
        "n": len(rows),
        "paid": sum(r["paid"] for r in rows),
        "clearing": sum(r["clearing"] for r in rows),
        "overpaid": sum(max(0, r["paid"] - r["clearing"]) for r in rows),
        "uncontested": sum(1 for r in rows if r["rivals"] == 0),
    }


def lost_bids(
    txs: Sequence[Mapping[str, Any]], roster_id: int, week1_start: int
) -> List[Dict[str, Any]]:
    """Claims ``roster_id`` lost, with what the winner paid (None if nobody did)."""
    out: List[Dict[str, Any]] = []
    for t in sorted(txs, key=lambda t: t["status_updated"]):
        if t.get("status") != "failed" or roster_id not in (t.get("roster_ids") or []):
            continue
        if not _bid(t) or not t.get("adds") or t["status_updated"] < week1_start:
            continue
        pid = str(next(iter(t["adds"])))
        won = _claims_for(t, txs, pid, "complete")
        out.append(
            {
                "add": pid,
                "week": nfl_week(t["status_updated"], week1_start),
                "bid": _bid(t),
                "winner_bid": _bid(won[0]) if won else None,
            }
        )
    return out


# ------------------------------------------------------------------ scoring


def _listing(
    rows: Sequence[Mapping[str, Any]], key: Callable[[Mapping[str, Any]], float], k: int
) -> List[Tuple[int, Mapping[str, Any]]]:
    """``(rank, row)`` for the top ``k`` of each position, best first."""
    out: List[Tuple[int, Mapping[str, Any]]] = []
    for pos in sorted({str(r["pos"]) for r in rows}):
        ranked = sorted((r for r in rows if r["pos"] == pos), key=key)[:k]
        out += [(i, r) for i, r in enumerate(ranked, start=1)]
    return out


def score_claims(
    claims: Sequence[Mapping[str, Any]],
    pool: Mapping[int, Sequence[Mapping[str, Any]]],
    pts: Pts,
    last_week: int,
    key: Callable[[Mapping[str, Any]], float] = lambda r: -r["blend"],
) -> Dict[str, Any]:
    """Each filed add against the drop, the board's #1 and hindsight's best.

    ``pool[week]`` holds that week's free agents with ``p1/p2/p4`` attached
    (see :func:`attach_windows`); ``key`` orders them the way the report did.
    """
    keys = [f"p{n}" for n in WINDOWS]
    totals = {k: [0.0, 0.0, 0.0] for k in ("add", "drop", "board_top", "best_at_pos")}
    rows: List[Dict[str, Any]] = []
    for c in claims:
        wk, pos = int(c["week"]), str(c["pos"])
        same = [r for r in pool.get(wk, ()) if r["pos"] == pos]
        add = [window(pts, c["add"], wk, n, last_week)[0] for n in WINDOWS]
        drop = (
            [window(pts, c["drop"], wk, n, last_week)[0] for n in WINDOWS]
            if c.get("drop")
            else [0.0, 0.0, 0.0]
        )
        top = sorted(same, key=key)[:1]
        board_top = [top[0][k] for k in keys] if top else [0.0, 0.0, 0.0]
        best = [max((r[k] for r in same), default=0.0) for k in keys]
        for name, v in (
            ("add", add),
            ("drop", drop),
            ("board_top", board_top),
            ("best_at_pos", best),
        ):
            totals[name] = [a + b for a, b in zip(totals[name], v)]
        rows.append(
            {
                **{k: c.get(k) for k in ("add", "drop", "bid", "week", "pos")},
                "add_pts": add,
                "drop_pts": drop,
                "board_top": top[0]["name"] if top else None,
                "board_top_pts": board_top,
                "best_at_pos_pts": best,
            }
        )
    return {
        "n": len(rows),
        "rows": rows,
        "totals": {k: [round(x, 1) for x in v] for k, v in totals.items()},
    }


def score_listed(
    pool: Mapping[int, Sequence[Mapping[str, Any]]],
    key: Callable[[Mapping[str, Any]], float],
    k: int = 6,
    weeks: Optional[Iterable[int]] = None,
) -> Dict[str, Any]:
    """Mean next-1/2/4-week points of the top ``k`` per position, by method."""
    keep = set(weeks) if weeks is not None else None
    vals: Dict[str, List[float]] = {f"p{n}": [] for n in WINDOWS}
    for wk, rows in pool.items():
        if keep is not None and wk not in keep:
            continue
        for _rank, r in _listing(rows, key, k):
            for name in vals:
                vals[name].append(float(r[name]))
    n = len(vals["p1"])
    return {
        "n": n,
        **{name: (sum(v) / n if n else 0.0) for name, v in vals.items()},
    }


def listing_rows(
    pool: Mapping[int, Sequence[Mapping[str, Any]]],
    key: Callable[[Mapping[str, Any]], float],
    k: int = 6,
) -> List[Dict[str, Any]]:
    """Every listed name as a flat row (week, position rank, windows) for the JSON."""
    out = []
    for wk in sorted(pool):
        for rank, r in _listing(pool[wk], key, k):
            out.append(
                {
                    "week": wk,
                    "rank": rank,
                    "name": r["name"],
                    "pos": r["pos"],
                    "age": r.get("age"),
                    "ours": r.get("ours"),
                    "slpr": r.get("slpr"),
                    "blend": round(float(r["blend"]), 2),
                    **{f"p{n}": round(float(r[f"p{n}"]), 1) for n in WINDOWS},
                }
            )
    return out
