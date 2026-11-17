"""One ranked list per league: what a claim is worth over the next four weeks.

The report ranked each position by a **one-week** blend (the mean of our
projection and Sleeper's) and showed six of each, with the dynasty value list
as a separate block and the claims file taken from the top three by raw blend.
That answers "who is projected highest this Sunday", not "whose claim helps my
team most, for how long". Three of the things it ignored are in the data it
already had:

* **Byes.** A player's four-week points are his weekly points times the games
  he plays. A name on a bye next week loses a quarter of his window and a name
  on bye *now* has a blend of zero though he plays the other three.
* **Whose job he takes.** A claim is worth the gain to my best legal lineup,
  not his own score: a 12-point tight end is worth nothing to a team already
  starting two 14-point ones.
* **Dynasty value,** in a league that keeps players (Mantis), as an explicit
  term next to the points rather than a second list.

What this module does *not* contain, because it was tested and did not hold up
on held-out weeks (see ``.planning/WAIVER_RANKING_2026-11-16.md``): the
consensus-base rule, and every role-change boost. They are here as code with
weights of zero, so a boost is a number someone changed after a scorecard said
so, not a rule someone believed.
"""

from __future__ import annotations

from typing import (
    AbstractSet,
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from src.roster_optimizer import optimal_lineup

#: Weeks a claim is judged over.
WINDOW = 4
#: A fantasy season ends with the NFL regular season; later weeks are not played.
LAST_WEEK = 18
#: "Ours and Sleeper's disagree by 2x" -- past this they are not averaged.
RATIO = 2.0
#: Four-week points one FantasyCalc dynasty-value unit is worth in a dynasty
#: league. A decision, not a fit: values for past weeks were never archived (the
#: archive starts 2026-W43), so the weight cannot be validated on points and any
#: validation against today's values would be look-ahead.
DYN_POINTS_PER_UNIT = 0.04

#: Role-change boosts, in four-week points. Every one is 0 until a scorecard
#: shows it raising the four-week points of listed names on held-out weeks.
#: Tested 2026-11-16 on Mantis weeks 2-6 (fit) and 7, 9 (held out):
#: ``snap_jump`` LOWERED them at every weight tried; the others have no point-in-
#: time data to test on (sentiment flags start week 9, ffopportunity ends 2025,
#: trending adds are only served live). So none is kept.
FLAG_BOOSTS: Dict[str, float] = {
    "snap_jump": 0.0,
    "starter_out": 0.0,
    "xp_gap": 0.0,
    "trending": 0.0,
}


def consensus(
    ours: Optional[float], slpr: Optional[float], ratio: float = RATIO
) -> Tuple[float, str]:
    """A weekly projection from two sources, and which of them it rests on.

    Sleeper's is the consensus; ours is averaged in only while the two agree to
    within ``ratio``. Past that they are describing different players -- one of
    the two is missing a role change -- and an average represents neither
    (Tyler Huntley, ours 16.8, Sleeper 0.0, blend 8.4: a number nobody believed).
    """
    if ours is None and slpr is None:
        return 0.0, "none"
    if slpr is None:
        return float(ours), "ours_only"  # type: ignore[arg-type]
    if ours is None:
        return float(slpr), "sleeper_only"
    lo, hi = sorted((float(ours), float(slpr)))
    if lo > 0 and hi / lo <= ratio:
        return (float(ours) + float(slpr)) / 2.0, "both"
    return float(slpr), "disagree"


def games_in_window(
    team: Optional[str],
    week: int,
    playing: Mapping[int, AbstractSet[str]],
    n: int = WINDOW,
) -> int:
    """How many of weeks ``week .. week+n-1`` the team plays; unknown = all."""
    weeks = [k for k in range(week, week + n) if k <= LAST_WEEK]
    if not team or not playing:
        return len(weeks)
    return sum(1 for k in weeks if k not in playing or team in playing[k])


def _week_points(r: Mapping[str, Any], k: int, week: int, playing: Mapping) -> float:
    team = r.get("team")
    if week + k > LAST_WEEK:
        return 0.0
    if team and playing.get(week + k) and team not in playing[week + k]:
        return 0.0
    if k == 0 and (r.get("out") or r.get("ir")):
        return 0.0
    return float(r.get("weekly") if r.get("weekly") is not None else r["blend"])


def _total(
    roster: Sequence[Mapping[str, Any]],
    k: int,
    week: int,
    playing: Mapping,
    roster_format: Optional[str],
    roster_positions: Optional[Sequence[str]],
) -> float:
    pool = [
        {
            "sid": r["sid"],
            "position": r["pos"],
            "projected_points": _week_points(r, k, week, playing),
        }
        for r in roster
        if r["pos"] in ("QB", "RB", "WR", "TE") and not r.get("ir")
    ]
    lu = optimal_lineup(
        pool,
        roster_format=roster_format or "standard",
        roster_positions=[
            p
            for p in (roster_positions or [])
            if str(p).upper() not in ("K", "DEF", "DST")
        ]
        or None,
    )
    return sum(p["projected_points"] for ps in lu["starters"].values() for p in ps)


def window_gain(
    candidate: Mapping[str, Any],
    roster: Sequence[Mapping[str, Any]],
    week: int,
    playing: Mapping[int, AbstractSet[str]],
    roster_format: Optional[str] = None,
    roster_positions: Optional[Sequence[str]] = None,
    n: int = WINDOW,
) -> float:
    """Gain to my best legal lineup over the next ``n`` weeks, byes included."""
    gain = 0.0
    for k in range(n):
        base = _total(roster, k, week, playing, roster_format, roster_positions)
        withc = _total(
            [*roster, candidate], k, week, playing, roster_format, roster_positions
        )
        gain += max(0.0, withc - base)
    return gain


def rank_targets(
    candidates: Sequence[Dict[str, Any]],
    roster: Sequence[Mapping[str, Any]],
    week: int,
    playing: Mapping[int, AbstractSet[str]],
    roster_format: Optional[str],
    roster_positions: Optional[Sequence[str]],
    dynasty: bool,
    dyn_points_per_unit: float = DYN_POINTS_PER_UNIT,
) -> List[Dict[str, Any]]:
    """Attach ``gain4`` / ``dyn_pts`` / ``score`` and sort best first.

    Redraft: the score is the gain to my lineup. Dynasty: that plus the player's
    dynasty value in points, so a young tight end who does not start for me this
    month still outranks a 31-year-old who would -- which is the whole reason a
    dynasty league is not a redraft league.

    Ties (most names add nothing to a deep roster) fall back to dynasty value
    and then to the weekly blend, so the order is never arbitrary.
    """
    for c in candidates:
        c["gain4"] = window_gain(
            c, roster, week, playing, roster_format, roster_positions
        )
        c["dyn_pts"] = (
            dyn_points_per_unit * float(c.get("dyn") or 0) if dynasty else 0.0
        )
        boosts = sum(
            FLAG_BOOSTS.get(f, 0.0) for f, on in (c.get("flags") or {}).items() if on
        )
        c["score"] = c["gain4"] + c["dyn_pts"] + boosts
    return sorted(
        candidates,
        key=lambda c: (-c["score"], -float(c.get("dyn") or 0), -float(c["blend"])),
    )
