"""What it takes to win a waiver claim, not what winners paid.

The old bid model was tuned to **winning** bids (``scripts/backtest_bid_model.py``
scores it by distance to the price that won). That is the wrong target twice
over. A winning bid is whatever the winner chose to pay: in Mantis 73% of the
league's winning bids had no rival claim at all, so the "price" was a bidder
bidding against himself. And it hides the quantity that matters, which is how
little would have been enough. George's 8 winning in-season bids cost $475;
the runner-up's bid + 1 would have won every one for $19 (see
``data/waivers/scorecard/mantis_2026.md``).

What decides a claim is the **top rival bid**, ``R``: you win iff you bid more
than ``R`` (a tie loses), and when nobody else claims the player ``R`` does not
exist and the league minimum wins. So the model has two parts:

* ``q``  — the probability somebody else claims him at all, by *tier* (position
  and whether the board ranks him among the top three free agents at it);
* ``R | contested`` — the distribution of the top rival bid, from the league's
  own claims. Failed claims are in Sleeper's log with their bids, so a loser's
  bid is as visible as a winner's.

From those, ``p_win(b) = (1 - q) + q * P(R < b)``, and the recommended bid is
the one that maximises ``p_win(b) * (value - b)`` — cheap when the claim is
probably uncontested, higher only when contest is likely *and* he is worth it.

Both parts are shrunk toward a prior built from published FAAB data (600k+
adds: winning bids are typically 1-1.4% of budget, skill-position medians
2-3%, and fewer than 5% of dynasty adds go for 10%+), so a tier the league has
barely produced data for does not get a confident number out of three
observations.

Pure functions over plain values; the replay that fits and scores it lives in
``scripts/backtest_clearing_price.py``.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

#: Position rank (by blend, among the week's free agents) that counts as "top".
TOP_RANK = 3
#: Published-data prior for the top rival bid, as shares of the season budget.
PRIOR_SHARES = (0.01, 0.02, 0.03, 0.05, 0.10)
#: Pseudo-observations the prior is worth, for contest rate and for bid size.
PRIOR_RATE = 0.15
PRIOR_N = 4.0
POOL_WEIGHT = 3.0
#: Probability that a contested claim meets a bid above anything we planned for.
TAIL = 0.05
#: Free replacement level: the blend of the rank-N free agent at the position.
REPLACEMENT_RANK = 12
#: Never plan to put more than this share of what is left on one claim.
CAP_SHARE = 0.25


def tier_of(pos: str, rank: Optional[int]) -> str:
    """``QB-top`` etc. A player the board does not rank counts as deep."""
    return f"{pos}-{'top' if rank is not None and rank <= TOP_RANK else 'deep'}"


@dataclass(frozen=True)
class Obs:
    """One player-week we could have bid on, and what the rivals did."""

    week: int
    tier: str
    #: Bids by every other roster that claimed him; empty = uncontested.
    rivals: Tuple[int, ...] = ()

    @property
    def top(self) -> int:
        return max(self.rivals) if self.rivals else 0


@dataclass(frozen=True)
class Advice:
    """The numbers the report prints for one target."""

    floor: int
    bid: int
    p_win: float
    p_win_floor: float
    ceiling: int
    p_contested: float
    price_for_half: Optional[int]
    reason: str


def value_ceiling(
    marginal_weekly_points: float,
    dyn_value: float = 0.0,
    weeks: int = 4,
    usd_per_point: float = 2.0,
    usd_per_dyn: float = 0.02,
) -> int:
    """What the claim is worth to us in FAAB dollars.

    ``usd_per_point`` and ``usd_per_dyn`` are decisions, not fits: there is no
    league history of what a point is worth to *us*, only of what the room pays.
    They are printed beside every ceiling so George can move them, and
    ``scripts/backtest_clearing_price.py`` reports spend at other settings.
    """
    pts = max(0.0, marginal_weekly_points) * weeks
    return int(round(usd_per_point * pts + usd_per_dyn * max(0.0, dyn_value)))


class ClearingModel:
    """Contest rate and top-rival-bid distribution per tier."""

    def __init__(
        self, obs: Sequence[Obs], budget: int = 1000, min_bid: int = 1
    ) -> None:
        self.budget = budget
        self.min_bid = min_bid
        self._cdf_memo: Dict[str, Tuple[List[int], List[float]]] = {}
        self._by: Dict[str, List[Obs]] = defaultdict(list)
        for o in obs:
            self._by[o.tier].append(o)
        n = len(obs)
        hit = sum(1 for o in obs if o.rivals)
        self.base_rate = (hit + PRIOR_N * PRIOR_RATE) / (n + PRIOR_N)
        pooled = [o.top for o in obs if o.rivals]
        prior = [max(min_bid, round(budget * s)) for s in PRIOR_SHARES]
        # The prior is worth PRIOR_N pseudo-observations however big the league
        # sample gets; data takes over as it accumulates.
        self._pool: List[Tuple[int, float]] = [(v, 1.0) for v in pooled] + [
            (v, PRIOR_N / len(prior)) for v in prior
        ]

    def p_contested(self, tier: str) -> float:
        """Shrunk share of this tier's names that drew a rival claim."""
        rows = self._by.get(tier, [])
        hit = sum(1 for o in rows if o.rivals)
        return (hit + PRIOR_N * self.base_rate) / (len(rows) + PRIOR_N)

    def _cdf(self, tier: str) -> Tuple[List[int], List[float]]:
        if tier not in self._cdf_memo:
            self._cdf_memo[tier] = self._build_cdf(tier)
        return self._cdf_memo[tier]

    def _build_cdf(self, tier: str) -> Tuple[List[int], List[float]]:
        own = [(o.top, 1.0) for o in self._by.get(tier, []) if o.rivals]
        total_pool = sum(w for _v, w in self._pool)
        pooled = [(v, POOL_WEIGHT * w / total_pool) for v, w in self._pool]
        pts = sorted(own + pooled)
        values = [v for v, _w in pts]
        cum, run = [], 0.0
        total = sum(w for _v, w in pts)
        for _v, w in pts:
            run += w / total
            cum.append(run)
        return values, cum

    def p_win(self, bid: int, tier: str) -> float:
        """Chance a bid of ``bid`` beats every rival (a tie loses)."""
        q = self.p_contested(tier)
        values, cum = self._cdf(tier)
        i = bisect.bisect_left(values, bid)  # values strictly below the bid
        below = cum[i - 1] if i else 0.0
        return (1.0 - q) + q * below * (1.0 - TAIL)

    def price_for(self, p: float, tier: str, hi: Optional[int] = None) -> Optional[int]:
        """Smallest bid that wins with probability ``p``, if one can."""
        for b in range(self.min_bid, (hi or self.budget) + 1):
            if self.p_win(b, tier) >= p:
                return b
        return None

    def recommend(self, tier: str, value: float, budget_left: int) -> Advice:
        """The bid maximising ``p_win * (value - bid)``, within the cap."""
        cap = max(self.min_bid, min(budget_left, int(budget_left * CAP_SHARE)))
        hi = max(self.min_bid, min(cap, int(value)))
        best, best_u = self.min_bid, float("-inf")
        for b in range(self.min_bid, hi + 1):
            u = self.p_win(b, tier) * (value - b)
            if u > best_u + 1e-9:
                best, best_u = b, u
        q = self.p_contested(tier)
        pw = self.p_win(best, tier)
        half = self.price_for(0.5, tier, cap)
        if value <= self.min_bid:
            why = f"worth about ${int(value)} to us — the minimum or skip"
        elif q < 0.25:
            why = (
                f"only {q:.0%} of {tier} names draw a rival claim, so a few "
                "dollars usually wins"
            )
        elif half is None or half > value:
            why = (
                f"{q:.0%} of {tier} names draw a rival and clearing usually "
                f"exceeds what he is worth (${int(value)}) — a lottery ticket"
            )
        else:
            why = (
                f"{q:.0%} of {tier} names draw a rival claim; ${half} wins at "
                "least half the time"
            )
        return Advice(
            floor=self.min_bid,
            bid=best,
            p_win=pw,
            p_win_floor=self.p_win(self.min_bid, tier),
            ceiling=int(value),
            p_contested=q,
            price_for_half=half,
            reason=why,
        )


def replay_bid(bid: int, rivals: Sequence[int]) -> Tuple[bool, int]:
    """``(won, paid)`` for a bid against what the rivals actually bid."""
    won = all(bid > r for r in rivals)
    return won, bid if won else 0


# ---------------------------------------------------------------- persistence


def obs_to_json(obs: Sequence[Obs]) -> List[Dict[str, object]]:
    return [{"week": o.week, "tier": o.tier, "rivals": list(o.rivals)} for o in obs]


def obs_from_json(rows: Sequence[Dict[str, object]]) -> List[Obs]:
    return [
        Obs(int(r["week"]), str(r["tier"]), tuple(int(b) for b in r["rivals"]))
        for r in rows
    ]


# ------------------------------------------------------------------ the report


def advise_all(
    rows: Sequence[Dict[str, object]],
    model: ClearingModel,
    budget_left: int,
    usd_per_point: float = 2.0,
    usd_per_dyn: float = 0.02,
) -> None:
    """Attach ``rank``, ``tier``, ``above_free`` and ``advice`` to free-agent rows.

    ``rows`` carry ``pos``, ``blend`` and optionally ``dyn``. A name is worth
    what he scores above the free replacement at his position (the blend of the
    twelfth-ranked free agent there) over the next four weeks, plus a small
    weight on dynasty value: paying for points anyone could stream for free is
    how $300 went on a wideout who then scored zero.
    """
    by_pos: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for r in rows:
        by_pos[str(r["pos"])].append(r)
    for rs in by_pos.values():
        rs.sort(key=lambda r: -float(r["blend"]))  # type: ignore[arg-type]
        repl = (
            float(rs[REPLACEMENT_RANK - 1]["blend"])  # type: ignore[arg-type]
            if len(rs) >= REPLACEMENT_RANK
            else 0.0
        )
        for rank, r in enumerate(rs, start=1):
            r["rank"] = rank
            r["tier"] = tier_of(str(r["pos"]), rank)
            r["above_free"] = max(0.0, float(r["blend"]) - repl)  # type: ignore[arg-type]
            value = value_ceiling(
                float(r["above_free"]),  # type: ignore[arg-type]
                float(r.get("dyn") or 0),  # type: ignore[arg-type]
                usd_per_point=usd_per_point,
                usd_per_dyn=usd_per_dyn,
            )
            r["advice"] = model.recommend(str(r["tier"]), value, budget_left)


def final_bid(
    old: Optional[Tuple[int, str]],
    adv: Advice,
    *,
    role_ending: bool,
    no_help_redraft: bool,
    depth_cap: Optional[int],
) -> Tuple[int, str]:
    """The clearing-price advice, with the hazards the old model already knew.

    Three rules from the old bid stay in force because each came from a real
    mistake and none is about price: a role the week's news says is ending is
    worth the minimum, a player WE cut is re-bought at the minimum or not at
    all, and in a redraft league "no help" is a refusal. A pure depth add is
    capped at the old floor, not at what it would take to win him.
    """
    if old and (role_ending or old[1].startswith("WE cut him")):
        return old
    if no_help_redraft:
        return 1, "rated no help — minimum or nothing"
    if depth_cap is not None and adv.bid > depth_cap:
        return depth_cap, f"depth only — capped at ${depth_cap}, not ${adv.bid}"
    return adv.bid, adv.reason
