"""Does the board's ordering of waiver-tier players predict what they score?

Every other check in ``scripts/audit_waiver_skill.py`` tests machinery: that a
guard exists, that a tag is derived from something published, that the bid
model beats a naive rule on bids somebody already made. None of them can fail
because a *recommendation* was wrong. Week 8 2026 the audit read 100/100 while
four recommendations in a row had to be corrected by hand — the target share
behind a TE add, a backup quarterback who was not starting, a drop, and a bid
sized at a quarter of the budget. A score that cannot move when the advice is
wrong is not a measure of the advice.

This module scores the recommendation itself. For a week whose board was
written **before kickoff**, it takes the players the board ranks below starter
level — the population a waiver claim is drawn from — picks the top few the
way the report would, and asks what they actually scored against what the
whole tier scored. A ranking that carries information puts its top picks above
the tier average. One that does not, cannot.

Three things keep it falsifiable:

- **A null.** :func:`null_lift` ranks the same tier at random. It must come
  out at roughly zero; if a shuffled board scores as well as the real one, the
  metric is measuring something other than skill and the verdict is void. The
  repo has shipped an unfalsifiable gate before — the ELITE 2.4 line-capture
  bar that a deliberately edge-free model cleared at +2.277 — and the rule
  written down afterwards was to score a skill-free model against any bar
  before trusting it.
- **No credit for silence.** A tier player with no row in the week's actuals
  did not play and scores zero, rather than dropping out of the average. That
  is the whole Tyler Huntley case: our board had him at 16.8 because it had
  zeroed the starter ahead of him off a stale injury tag, and he was never
  going to take the field. Dropping him would hide exactly the error worth
  catching.
- **A stated minimum detectable effect.** With six usable weeks the honest
  answer to a small lift is "cannot tell", and :func:`summarise` says so
  rather than reporting a number that the sample cannot support.

**Point-in-time.** Only boards written strictly before the week's first
kickoff are eligible, which today means 2026 weeks 2-7: every 2024 and 2025
board on disk was written after the games it covers, so none of them can
answer this question. Regenerating historical boards would not fix that —
rosters, depth charts and injury reports are overwritten in place, so a board
rebuilt today sees things the engine could not have seen then.
"""

from __future__ import annotations

import glob
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLD = REPO_ROOT / "data" / "gold" / "projections"
BRONZE = REPO_ROOT / "data" / "bronze"

#: ``projections_half_ppr_20261022_221655.parquet`` -> the stamp.
STAMP_RE = re.compile(r"_(\d{8}_\d{6})\.parquet$")

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


def board_stamp(path: str) -> Optional[pd.Timestamp]:
    """When the board was written, from its filename."""
    m = STAMP_RE.search(os.path.basename(path))
    if not m:
        return None
    try:
        return pd.to_datetime(m.group(1), format="%Y%m%d_%H%M%S")
    except ValueError:
        return None


def first_kickoff(sched: pd.DataFrame, week: int) -> Optional[pd.Timestamp]:
    """The earliest gameday in ``week`` — the point-in-time cutoff."""
    g = sched[sched["week"] == week]
    if g.empty or "gameday" not in g.columns:
        return None
    return pd.to_datetime(g["gameday"].min())


def pre_kickoff_board(season: int, week: int, kickoff: pd.Timestamp) -> Optional[str]:
    """The latest board for ``week`` that predates ``kickoff``, if any.

    Latest, not earliest: the most informed board the engine could have served
    while still seeing no result from the week it projects.
    """
    best: Optional[str] = None
    best_at: Optional[pd.Timestamp] = None
    for f in glob.glob(str(GOLD / f"season={season}" / f"week={week}" / "*.parquet")):
        at = board_stamp(f)
        if at is None or at >= kickoff:
            continue
        if best_at is None or at > best_at:
            best, best_at = f, at
    return best


def starter_cutoffs(roster: Mapping[str, int], teams: int) -> Dict[str, int]:
    """Positional rank at which a league's starters run out.

    Dedicated slots plus a share of the flex ones, so the tier below is the
    population a claim is actually drawn from rather than everyone outside a
    team's first choice. FLEX is split across RB/WR/TE and a superflex slot
    goes to QB.
    """
    out = {p: float(roster.get(p, 0)) for p in SKILL_POSITIONS}
    flex = float(roster.get("FLEX", 0))
    for p in ("RB", "WR", "TE"):
        out[p] += flex / 3.0
    out["QB"] += float(roster.get("SFLEX", 0) or roster.get("SUPER_FLEX", 0))
    return {p: int(round(v * teams)) for p, v in out.items()}


def waiver_tier(
    board: pd.DataFrame, cutoffs: Mapping[str, int], bye_teams: Sequence[str] = ()
) -> pd.DataFrame:
    """Board rows ranked below starter level — what a claim chooses among.

    Bye-week rows are dropped: they score zero for a reason that has nothing to
    do with whether the ranking is any good.
    """
    byes = {str(t).upper() for t in bye_teams}
    df = board[board["position"].isin(SKILL_POSITIONS)].copy()
    if "is_bye_week" in df.columns:
        df = df[~df["is_bye_week"].fillna(False).astype(bool)]
    if "recent_team" in df.columns and byes:
        df = df[~df["recent_team"].astype(str).str.upper().isin(byes)]
    df["pos_rank"] = (
        df.groupby("position")["projected_points"]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    keep = df["position"].map(lambda p: cutoffs.get(p, 0))
    return df[df["pos_rank"] > keep].reset_index(drop=True)


def attach_actuals(tier: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Add ``actual_points``; a player with no row did not play and scores 0."""
    got = actuals[["player_id", "projected_points"]].rename(
        columns={"projected_points": "actual_points"}
    )
    out = tier.merge(got, on="player_id", how="left")
    out["actual_points"] = out["actual_points"].fillna(0.0)
    out["played"] = out["player_id"].isin(set(actuals["player_id"]))
    return out


def attach_prior(tier: pd.DataFrame, prior: pd.DataFrame) -> pd.DataFrame:
    """Add ``prior_points``: what each player scored the week before.

    The naive baseline's whole model — "pick whoever just had a big game" —
    and a demanding one. Beating a shuffle only proves the board is not noise;
    beating this proves the modelling earns its keep over a heuristic anyone
    could run off a box score with no pipeline at all.
    """
    out = tier.copy()
    if prior is None or prior.empty:
        out["prior_points"] = 0.0
        return out
    got = prior[["player_id", "projected_points"]].rename(
        columns={"projected_points": "prior_points"}
    )
    out = out.merge(got, on="player_id", how="left")
    out["prior_points"] = out["prior_points"].fillna(0.0)
    return out


def week_lift(
    tier: pd.DataFrame, top_k: int, by: str = "projected_points"
) -> Optional[Dict[str, Any]]:
    """What the board's top ``top_k`` scored, against the tier average.

    **Within position, then averaged.** Pooling the positions looks tidier and
    is worthless: quarterbacks outscore wide receivers by a dozen points a
    week whatever anyone projects, so a pooled top-5 is five quarterbacks and
    the "lift" is just that gap. Scored pooled, this read +11.7 with every top
    pick a QB — a number a coin-flipping model that only ever picked
    quarterbacks would also have earned. Per position the gap cancels and what
    is left is whether the ordering knows anything.
    """
    per_pos: Dict[str, float] = {}
    picks: List[str] = []
    n_tier = 0
    for pos, grp in tier.groupby("position"):
        if len(grp) <= top_k:
            continue
        ranked = grp.sort_values(by, ascending=False)
        chosen = ranked.head(top_k)
        per_pos[str(pos)] = float(
            chosen["actual_points"].mean() - grp["actual_points"].mean()
        )
        picks.append(f"{pos} {chosen.iloc[0]['player_name']}")
        n_tier += len(grp)
    if not per_pos:
        return None
    return {
        "n_tier": n_tier,
        "by_pos": per_pos,
        "lift": float(np.mean(list(per_pos.values()))),
        "picks": picks,
    }


def null_lift(tier: pd.DataFrame, top_k: int, seeds: int = 1500) -> float:
    """Mean lift of a ranking shuffled *within each position*.

    The control the whole verdict rests on, and it has to shuffle the same way
    the measurement slices: a null that mixed positions would come out flat
    while a pooled measurement was quietly scoring the QB-versus-WR gap, which
    is how the first version of this metric passed on nothing.

    A random pick is its position's average in expectation, so this is
    unbiased by construction and must land near zero. Anything else means the
    lift is produced by the arithmetic rather than by the board, and the
    verdict is void. ``seeds`` is high enough that its own sampling error sits
    well inside the 0.5 tolerance the verdict uses, so a noisy estimate cannot
    void a sound result.
    """
    rng = np.random.default_rng(0)
    draws: List[float] = []
    for _ in range(seeds):
        per_pos = []
        for _pos, grp in tier.groupby("position"):
            if len(grp) <= top_k:
                continue
            vals = grp["actual_points"].to_numpy()
            per_pos.append(
                float(rng.choice(vals, size=top_k, replace=False).mean() - vals.mean())
            )
        if per_pos:
            draws.append(float(np.mean(per_pos)))
    return float(np.mean(draws)) if draws else 0.0


def summarise(
    rows: Sequence[Mapping[str, Any]],
    nulls: Sequence[float],
    naive: Sequence[float] = (),
) -> Dict:
    """Pooled verdict, with the minimum effect this sample could detect.

    Weeks are the unit: player-weeks inside one week share a slate, a set of
    injuries and a weather map, so treating them as independent would shrink
    the interval to something the sample does not earn.
    """
    lifts = np.array([r["lift"] for r in rows], dtype=float)
    n = len(lifts)
    if n == 0:
        return {"n_weeks": 0, "verdict": "NO DATA"}
    mean = float(lifts.mean())
    se = float(lifts.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    # 80% power, 5% two-sided — the smallest true lift this n could separate
    # from zero. Printed next to the result so a small number is read as
    # "cannot tell" rather than "no effect".
    mde = 2.8 * se if n > 1 else float("nan")
    positive = int((lifts > 0).sum())
    null_mean = float(np.mean(nulls)) if nulls else 0.0
    naive_mean = float(np.mean(naive)) if len(naive) else float("nan")
    edge = mean - naive_mean if np.isfinite(naive_mean) else float("nan")
    if n < 2 or not np.isfinite(se):
        verdict = "TOO FEW WEEKS"
    elif abs(null_mean) > 0.5:
        verdict = "VOID — the null is not flat"
    elif mean <= 0:
        verdict = "NO VALUE — top picks do not beat the tier"
    elif mean <= mde:
        verdict = "DIRECTIONAL — lift is below what this sample can detect"
    elif np.isfinite(edge) and edge <= -mde:
        verdict = "BEATEN BY THE BOX SCORE — last week's points rank better"
    elif np.isfinite(edge) and edge <= mde:
        # A tie, said as a tie. The board clears the tier average handsomely
        # and clears the shuffle, so it is not noise; it simply has no
        # measurable edge over "take whoever just had a big game", which is a
        # heuristic with no model, no pipeline and no injury feed behind it.
        verdict = "TIED WITH THE BOX SCORE — no detectable edge over last week's points"
    else:
        verdict = "RANKING ADDS VALUE"
    return {
        "n_weeks": n,
        "mean_lift": mean,
        "se": se,
        "mde": mde,
        "weeks_positive": positive,
        "null_lift": null_mean,
        "naive_lift": naive_mean,
        "edge_over_naive": edge,
        "verdict": verdict,
    }
