"""Team-defense (DEF/DST) and kicker (K) streaming signals.

Two independent views of each weekly matchup, so a swap is only recommended when
both agree (the same rule the skill-position lineup tool uses):

- **Projection** — Sleeper's weekly DEF/K projection, plus the league platform's
  own projection when the caller supplies it (ESPN/Yahoo scoring differ from
  Sleeper's, so the platform number is the most league-accurate).
- **Vegas** — implied team totals from the live odds snapshot (current week) or the
  schedule's look-ahead lines (future weeks). A defense wants a LOW opponent
  implied total; a kicker wants a HIGH own implied total.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

# nflverse / odds-feed abbreviations that differ from Sleeper's.
TEAM_ALIAS = {"LA": "LAR", "JAC": "JAX", "WSH": "WAS", "LV": "LV"}


def _norm(team: object) -> str:
    t = str(team or "").upper().strip()
    return TEAM_ALIAS.get(t, t)


def implied_totals_from_odds(odds: pd.DataFrame) -> Dict[str, float]:
    """``team -> implied points`` from an odds snapshot (median across books).

    Expects ``home_team_nfl``, ``away_team_nfl``, ``market`` in {spreads, totals},
    ``home_spread`` (negative = home favored) and ``total_points``.
    """
    if odds is None or odds.empty:
        return {}
    out: Dict[str, float] = {}
    for (home, away), g in odds.groupby(["home_team_nfl", "away_team_nfl"]):
        spread = g.loc[g["market"] == "spreads", "home_spread"].dropna().median()
        total = g.loc[g["market"] == "totals", "total_points"].dropna().median()
        if pd.isna(spread) or pd.isna(total):
            continue
        out[_norm(home)] = total / 2 - spread / 2
        out[_norm(away)] = total / 2 + spread / 2
    return out


def implied_totals_from_schedule(sched: pd.DataFrame, week: int) -> Dict[str, float]:
    """``team -> implied points`` from nflverse schedule lines for ``week``.

    nflverse ``spread_line`` is from the HOME perspective with positive meaning
    the home team is favored (the project's 2026-06-12 audit fixed an inverted
    read of this column — keep the sign as written here).
    """
    out: Dict[str, float] = {}
    games = sched[sched["week"] == week]
    for r in games.itertuples(index=False):
        if pd.isna(r.spread_line) or pd.isna(r.total_line):
            continue
        out[_norm(r.home_team)] = r.total_line / 2 + r.spread_line / 2
        out[_norm(r.away_team)] = r.total_line / 2 - r.spread_line / 2
    return out


def scoring_form(
    sched: pd.DataFrame, before_week: int
) -> Dict[str, Tuple[float, float]]:
    """``team -> (points scored/game, points allowed/game)`` before ``before_week``.

    The look-ahead proxy for weeks the books haven't posted lines for yet.
    """
    if "home_score" not in sched.columns:
        return {}
    played = sched[(sched["week"] < before_week) & sched["home_score"].notna()]
    scored: Dict[str, List[float]] = {}
    allowed: Dict[str, List[float]] = {}
    for r in played.itertuples(index=False):
        h, a = _norm(r.home_team), _norm(r.away_team)
        hs, as_ = float(r.home_score), float(r.away_score)
        scored.setdefault(h, []).append(hs)
        allowed.setdefault(h, []).append(as_)
        scored.setdefault(a, []).append(as_)
        allowed.setdefault(a, []).append(hs)
    return {
        t: (sum(scored[t]) / len(scored[t]), sum(allowed[t]) / len(allowed[t]))
        for t in scored
    }


def _form_implied(
    form: Dict[str, Tuple[float, float]], team: str, opp: str
) -> Optional[float]:
    """Implied points for ``team`` vs ``opp``: mean(team scored/g, opp allowed/g)."""
    if team not in form or opp not in form:
        return None
    return (form[team][0] + form[opp][1]) / 2


def matchup_table(
    sched: pd.DataFrame,
    weeks: Iterable[int],
    teams: Optional[Iterable[str]] = None,
    current_week_odds: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """One row per (team, week): opponent, home/away, implied totals, bye flag.

    ``current_week_odds`` (from :func:`implied_totals_from_odds`) overrides the
    schedule's lines for the first requested week when given.
    """
    weeks = list(weeks)
    all_teams = sorted(
        {_norm(t) for t in pd.concat([sched["home_team"], sched["away_team"]])}
    )
    wanted = [_norm(t) for t in teams] if teams else all_teams
    rows: List[dict] = []
    form = scoring_form(sched, min(weeks)) if weeks else {}
    for i, w in enumerate(weeks):
        lines = implied_totals_from_schedule(sched, w)
        source = "schedule_line"
        if i == 0 and current_week_odds:
            lines = {**lines, **current_week_odds}
            source = "live_odds"
        if not lines:
            source = "scoring_form"
        games = sched[sched["week"] == w]
        opp: Dict[str, tuple] = {}
        for r in games.itertuples(index=False):
            h, a = _norm(r.home_team), _norm(r.away_team)
            opp[h] = (a, True)
            opp[a] = (h, False)
        for t in wanted:
            if t not in opp:
                rows.append({"team": t, "week": w, "bye": True})
                continue
            o, home = opp[t]
            rows.append(
                {
                    "team": t,
                    "week": w,
                    "bye": False,
                    "opp": o,
                    "home": home,
                    "own_implied": (
                        lines.get(t)
                        if source != "scoring_form"
                        else _form_implied(form, t, o)
                    ),
                    "opp_implied": (
                        lines.get(o)
                        if source != "scoring_form"
                        else _form_implied(form, o, t)
                    ),
                    "line_source": source,
                }
            )
    df = pd.DataFrame(rows)
    if "opp" not in df.columns:
        df["opp"] = None
    return df


def swap_verdict(
    proj_gain: Optional[float],
    vegas_gain: Optional[float],
    proj_min: float = 1.5,
    vegas_min: float = 2.0,
) -> str:
    """Two-source rule: SWAP only when both sources favor the candidate enough.

    ``proj_gain`` is candidate minus current projected points; ``vegas_gain`` is
    the candidate's implied-total edge (for a DEF: current opponent implied minus
    candidate opponent implied; for a K: candidate own implied minus current).
    """
    p = proj_gain or 0.0
    v = vegas_gain or 0.0
    if p >= proj_min and v >= vegas_min:
        return "SWAP"
    if p <= 0 and v <= 0:
        return "KEEP"
    if (p > 0) != (v > 0):
        return "SPLIT"
    return "COIN FLIP"
