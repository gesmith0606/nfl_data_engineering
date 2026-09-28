"""League context for fantasy advice: FAAB, bid history, churn, dynasty values.

Waiver/lineup/trade advice must start from the league, not from one week's
projections: what every team has left to bid, what the room actually pays,
what we have already churned, and — in dynasty — what players are worth over
several seasons. (2026-09-28: by week 3 we had spent $602 of $1000 Mantis FAAB,
3x any other team, mostly on one-week backup-QB/RB streamers, and dropped two
23-year-olds to make room.)

Platform readers normalise into two frames:

    teams         team, is_me, wins, losses, faab_left, faab_spent, n_players
    transactions  week, type, team, is_me, add, drop, bid   (one row per move)

Dynasty values come from FantasyCalc's public trade-market values, keyed by
Sleeper id (the Sleeper registry carries ``espn_id`` / ``yahoo_id`` so every
platform joins through it).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
import requests

logger = logging.getLogger(__name__)

FANTASYCALC_URL = (
    "https://api.fantasycalc.com/values/current"
    "?isDynasty=true&numQbs={qbs}&numTeams={teams}&ppr={ppr}"
)
_CACHE_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "external" / "fantasycalc"
)

TEAM_COLS = ["team", "is_me", "wins", "losses", "faab_left", "faab_spent", "n_players"]
TX_COLS = ["week", "type", "team", "is_me", "add", "drop", "bid"]


# ---------------------------------------------------------------------------
# Dynasty values
# ---------------------------------------------------------------------------


def parse_fantasycalc(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """FantasyCalc ``/values/current`` rows -> ``{sleeper_id: {value, rank, trend30}}``."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sid = (r.get("player") or {}).get("sleeperId")
        if sid:
            out[str(sid)] = {
                "value": int(r.get("value") or 0),
                "rank": r.get("overallRank"),
                "trend30": r.get("trend30Day"),
            }
    return out


def fetch_dynasty_values(
    num_qbs: int = 2,
    num_teams: int = 10,
    ppr: float = 1.0,
    max_age_hours: float = 24,
    cache_dir: Path = _CACHE_DIR,
) -> Dict[str, Dict[str, Any]]:
    """Dynasty market values keyed by Sleeper id, cached on disk for a day.

    Falls back to a stale cache when the fetch fails and returns ``{}`` only
    when neither is available (callers then show no dynasty column).
    """
    cache = cache_dir / f"values_{num_qbs}qb_{num_teams}t_{ppr:g}ppr.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < max_age_hours * 3600:
        return parse_fantasycalc(json.loads(cache.read_text(encoding="utf-8")))
    try:
        resp = requests.get(
            FANTASYCALC_URL.format(qbs=num_qbs, teams=num_teams, ppr=ppr),
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        resp.raise_for_status()
        rows = resp.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows), encoding="utf-8")
        return parse_fantasycalc(rows)
    except (requests.RequestException, ValueError) as exc:
        if cache.exists():
            logger.warning("FantasyCalc fetch failed (%s) — using stale cache", exc)
            return parse_fantasycalc(json.loads(cache.read_text(encoding="utf-8")))
        logger.warning("FantasyCalc unavailable (%s) — no dynasty values", exc)
        return {}


def dynasty_values_for_preset(
    preset: Mapping[str, Any], roster_configs: Mapping[str, Mapping[str, int]]
) -> Dict[str, Dict[str, Any]]:
    """Dynasty values matched to a LEAGUE_PRESETS entry ({} unless ``dynasty``)."""
    if not preset.get("dynasty"):
        return {}
    shape = roster_configs.get(preset.get("roster", ""), {})
    return fetch_dynasty_values(
        num_qbs=2 if shape.get("SFLEX") or shape.get("QB", 1) > 1 else 1,
        num_teams=int(preset.get("teams") or 12),
        ppr={"ppr": 1.0, "half_ppr": 0.5}.get(preset.get("scoring_format"), 0.0),
    )


# ---------------------------------------------------------------------------
# Platform readers
# ---------------------------------------------------------------------------


def _label(registry: Mapping[str, Any], sid: Any) -> str:
    meta = registry.get(str(sid)) or {}
    name = meta.get("full_name") or str(sid)
    pos, age = meta.get("position"), meta.get("age")
    return f"{name} ({pos},{age})" if pos else name


def sleeper_context(
    league: Mapping[str, Any],
    users: Iterable[Mapping[str, Any]],
    rosters: Iterable[Mapping[str, Any]],
    txns_by_week: Mapping[int, Iterable[Mapping[str, Any]]],
    registry: Mapping[str, Any],
    me: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Sleeper league/users/rosters/transactions -> (teams, transactions)."""
    budget = (league.get("settings") or {}).get("waiver_budget") or 0
    names = {u.get("user_id"): u.get("display_name") for u in users}
    by_rid: Dict[Any, str] = {}
    teams = []
    for r in rosters:
        team = names.get(r.get("owner_id")) or f"roster {r.get('roster_id')}"
        by_rid[r.get("roster_id")] = team
        st = r.get("settings") or {}
        used = st.get("waiver_budget_used") or 0
        teams.append(
            {
                "team": team,
                "is_me": team == me,
                "wins": st.get("wins", 0),
                "losses": st.get("losses", 0),
                "faab_left": budget - used,
                "faab_spent": used,
                "n_players": len(r.get("players") or []),
            }
        )
    tx = []
    for week, items in sorted(txns_by_week.items()):
        for t in items or []:
            if t.get("status") != "complete" or t.get("type") == "commissioner":
                continue
            team = ", ".join(by_rid.get(r, "?") for r in t.get("roster_ids") or [])
            tx.append(
                {
                    "week": week,
                    "type": t.get("type"),
                    "team": team,
                    "is_me": me in team.split(", "),
                    "add": "; ".join(
                        _label(registry, p) for p in (t.get("adds") or {})
                    ),
                    "drop": "; ".join(
                        _label(registry, p) for p in (t.get("drops") or {})
                    ),
                    "bid": (t.get("settings") or {}).get("waiver_bid"),
                }
            )
    return pd.DataFrame(teams, columns=TEAM_COLS), pd.DataFrame(tx, columns=TX_COLS)


def espn_context(
    payload: Mapping[str, Any], my_team_id: int, registry: Mapping[str, Any]
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """ESPN lm-api payload (views mSettings, mTeam, mRoster, mTransactions2).

    ESPN player ids map to Sleeper ids through the registry's ``espn_id``.
    NOTE: the ``transactions`` shape (type/status/items/bidAmount) is written
    from ESPN's known schema but not yet checked against a live 2026 payload.
    """
    budget = ((payload.get("settings") or {}).get("acquisitionSettings") or {}).get(
        "acquisitionBudget"
    ) or 0
    by_espn = {
        str(m.get("espn_id")): sid for sid, m in registry.items() if m.get("espn_id")
    }
    names: Dict[Any, str] = {}
    teams = []
    for t in payload.get("teams") or []:
        name = (
            t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}"
        ).strip()
        names[t.get("id")] = name
        rec = ((t.get("record") or {}).get("overall")) or {}
        spent = (t.get("transactionCounter") or {}).get("acquisitionBudgetSpent") or 0
        teams.append(
            {
                "team": name,
                "is_me": t.get("id") == my_team_id,
                "wins": rec.get("wins", 0),
                "losses": rec.get("losses", 0),
                "faab_left": budget - spent,
                "faab_spent": spent,
                "n_players": len(((t.get("roster") or {}).get("entries")) or []),
            }
        )

    def label(pid: Any) -> str:
        sid = by_espn.get(str(pid))
        return _label(registry, sid) if sid else f"espn:{pid}"

    tx = []
    for t in payload.get("transactions") or []:
        if t.get("status") != "EXECUTED" or t.get("type") not in (
            "WAIVER",
            "FREEAGENT",
        ):
            continue
        items = t.get("items") or []
        tx.append(
            {
                "week": t.get("scoringPeriodId"),
                "type": "waiver" if t.get("type") == "WAIVER" else "free_agent",
                "team": names.get(t.get("teamId"), str(t.get("teamId"))),
                "is_me": t.get("teamId") == my_team_id,
                "add": "; ".join(
                    label(i.get("playerId")) for i in items if i.get("type") == "ADD"
                ),
                "drop": "; ".join(
                    label(i.get("playerId")) for i in items if i.get("type") == "DROP"
                ),
                "bid": t.get("bidAmount"),
            }
        )
    return pd.DataFrame(teams, columns=TEAM_COLS), pd.DataFrame(tx, columns=TX_COLS)


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def bid_summary(tx: pd.DataFrame) -> Dict[str, Any]:
    """Winning waiver bids > $0: count, median, p75, max (the room's price level)."""
    bids = pd.to_numeric(
        tx.loc[tx["type"] == "waiver", "bid"], errors="coerce"
    ).dropna()
    bids = bids[bids > 0]
    if bids.empty:
        return {"n": 0, "median": None, "p75": None, "max": None}
    return {
        "n": int(len(bids)),
        "median": float(bids.median()),
        "p75": float(bids.quantile(0.75)),
        "max": float(bids.max()),
    }


def dynasty_roster(
    player_ids: Iterable[str],
    registry: Mapping[str, Any],
    values: Mapping[str, Mapping[str, Any]],
    tags: Optional[Mapping[str, str]] = None,
) -> pd.DataFrame:
    """One row per player: name/pos/team/age/exp + dynasty value, rank, 30-day trend."""
    rows = []
    for sid in player_ids:
        meta = registry.get(str(sid)) or {}
        v = values.get(str(sid)) or {}
        rows.append(
            {
                "sid": str(sid),
                "name": meta.get("full_name") or str(sid),
                "pos": meta.get("position"),
                "team": meta.get("team"),
                "age": meta.get("age"),
                "exp": meta.get("years_exp"),
                "value": v.get("value", 0),
                "rank": v.get("rank"),
                "trend30": v.get("trend30"),
                "tag": (tags or {}).get(str(sid), ""),
            }
        )
    return pd.DataFrame(rows).sort_values("value", ascending=False, ignore_index=True)


def render(
    title: str,
    teams: pd.DataFrame,
    tx: pd.DataFrame,
    budget: Optional[float] = None,
    my_roster: Optional[pd.DataFrame] = None,
    dynasty_fas: Optional[pd.DataFrame] = None,
    team_values: Optional[pd.Series] = None,
) -> str:
    """Plain-text league context report."""
    out: List[str] = [f"=== {title} ===", ""]
    t = teams.sort_values("faab_left", ascending=False)
    out.append("-- FAAB by team (most left first) --")
    for r in t.itertuples():
        me = " <- me" if r.is_me else ""
        val = (
            f"  dyn {int(team_values.get(r.team, 0)):>6}"
            if team_values is not None
            else ""
        )
        out.append(
            f"  {r.team[:24]:24} {r.wins}-{r.losses}  left ${r.faab_left:>5}  spent ${r.faab_spent:>5}{val}{me}"
        )
    if budget:
        spent = teams["faab_spent"]
        mine = teams.loc[teams["is_me"], "faab_spent"]
        if not mine.empty:
            out.append(
                f"  league median spent ${spent.median():.0f} of ${budget:.0f}; "
                f"we have spent ${int(mine.iloc[0])} (rank {int((spent > mine.iloc[0]).sum()) + 1}/{len(spent)})"
            )
    s = bid_summary(tx)
    out.append("")
    if s["n"]:
        out.append(
            f"-- Winning waiver bids > $0 (n={s['n']}): median ${s['median']:.0f}, "
            f"p75 ${s['p75']:.0f}, max ${s['max']:.0f} --"
        )
    top = tx[tx["type"] == "waiver"].assign(b=pd.to_numeric(tx["bid"], errors="coerce"))
    for r in top.nlargest(8, "b").itertuples():
        out.append(f"  wk{r.week} ${r.b:>4.0f} {r.team[:18]:18} + {r.add}  - {r.drop}")
    mine = tx[tx["is_me"] & tx["type"].isin(["waiver", "free_agent", "trade"])]
    out.append("")
    out.append(f"-- Our moves ({len(mine)}) --")
    for r in mine.itertuples():
        bid = f"${r.bid:.0f}" if pd.notna(r.bid) and r.bid else "  "
        out.append(
            f"  wk{r.week} {r.type:10} {bid:>5}  + {r.add or '-'}   - {r.drop or '-'}"
        )
    if my_roster is not None and not my_roster.empty:
        out.append("")
        out.append("-- My roster by dynasty value --")
        for r in my_roster.itertuples():
            out.append(
                f"  {r.name[:22]:22} {r.pos or '':3}{r.team or '':4} age {r.age or '-':>2}  "
                f"value {r.value:>5}  trend {r.trend30 if r.trend30 is not None else '-':>5}  {r.tag}"
            )
    if dynasty_fas is not None and not dynasty_fas.empty:
        out.append("")
        out.append("-- Best unrostered by dynasty value --")
        for r in dynasty_fas.itertuples():
            out.append(
                f"  {r.name[:22]:22} {r.pos or '':3}{r.team or '':4} age {r.age or '-':>2} exp {r.exp if r.exp is not None else '-':>2}  "
                f"value {r.value:>5}  trend {r.trend30 if r.trend30 is not None else '-':>5}"
            )
    return "\n".join(out)
