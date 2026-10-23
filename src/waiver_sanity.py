"""Invariants a waiver report must satisfy before anyone acts on it.

Gold projections have had a sanity gate since v7.0; waiver advice never did,
so every bad recommendation this season was caught by the user reading the
report rather than by the pipeline. Each check here is one correction the
user had to make, turned into something that fails loudly instead.

Pure functions over the rendered report text, so they can be tested against a
fixture without a league, a browser or a network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

#: A free-agent line: name, POS, TEAM, then the annotated tail.
ROW_RE = re.compile(
    r"^\s{4,}(?P<name>.+?)\s{2,}(?P<pos>QB|RB|WR|TE|K|DEF)\s(?P<team>[A-Z]{2,3})\s+"
    r"(?P<tail>.*)$"
)
BID_RE = re.compile(r"\bBID \$(?P<bid>\d+)")
BOARD_AGE_RE = re.compile(
    r"projections_\w+?_\d{8}_\d{6}\.parquet \((?P<age>\d+)h old\)"
)
SLOTS_RE = re.compile(r"active (?P<used>\d+)/(?P<cap>\d+) \((?P<open>\d+) open", re.M)
IR_ACCEPTS_RE = re.compile(r"IR accepts: (?P<accepts>.+)$", re.M)

CRITICAL = "CRITICAL"
WARN = "WARN"


@dataclass(frozen=True)
class Finding:
    """One failed invariant."""

    level: str
    check: str
    detail: str


@dataclass(frozen=True)
class Row:
    """One free agent as the report rendered him."""

    name: str
    pos: str
    team: str
    tail: str

    @property
    def bid(self) -> Optional[int]:
        m = BID_RE.search(self.tail)
        return int(m.group("bid")) if m else None

    @property
    def ending(self) -> bool:
        return "ENDING<-" in self.tail

    @property
    def verdict(self) -> str:
        for v in ("STARTS", "BENCH+", "no help", "depth"):
            if v in self.tail:
                return v
        return ""


def parse_rows(text: str) -> List[Row]:
    """Every free-agent line in the report, in order."""
    rows: List[Row] = []
    in_fa = False
    for line in text.splitlines():
        if line.startswith("-- ") and "free agents" in line:
            in_fa = True
            continue
        if line.startswith("-- "):
            in_fa = "free agents" in line or "dynasty target" in line.lower()
            continue
        if not in_fa:
            continue
        m = ROW_RE.match(line)
        if m:
            rows.append(
                Row(
                    m.group("name").strip(),
                    m.group("pos"),
                    m.group("team"),
                    m.group("tail"),
                )
            )
    return rows


def check_report(
    text: str,
    bye_teams: Sequence[str] = (),
    max_board_age_h: int = 36,
    faab_left: Optional[int] = None,
    room_max_bid: Optional[int] = None,
) -> List[Finding]:
    """Run every invariant over a rendered waiver report.

    Args:
        text: The report as printed.
        bye_teams: Teams on bye for the week being priced.
        max_board_age_h: How stale the Gold board may be before it is a warning.
        faab_left: Remaining budget, to bound any suggested bid.
        room_max_bid: The largest bid this room has ever made.

    Returns:
        Findings, most severe first. Empty means the report is safe to act on.
    """
    rows = parse_rows(text)
    out: List[Finding] = []

    if not rows:
        out.append(Finding(CRITICAL, "rows", "no free agents parsed from the report"))
        return out

    # 1. A player on bye scores zero. Recommending one is never right.
    byes = {t.upper() for t in bye_teams}
    for r in rows:
        if r.team.upper() in byes and r.verdict in ("STARTS", "BENCH+"):
            out.append(
                Finding(
                    CRITICAL,
                    "bye",
                    f"{r.name} ({r.team}) is on bye but rated {r.verdict}",
                )
            )

    # 2. A role that is ENDING must never carry a bid worth paying.
    for r in rows:
        if r.ending and (r.bid or 0) > 1:
            out.append(
                Finding(
                    CRITICAL,
                    "ending-role",
                    f"{r.name} bid ${r.bid} while his starter is returning",
                )
            )

    # 3. Never suggest more than a quarter of the budget.
    if faab_left:
        cap = max(1, faab_left // 4)
        for r in rows:
            if (r.bid or 0) > cap:
                out.append(
                    Finding(
                        CRITICAL,
                        "faab-cap",
                        f"{r.name} bid ${r.bid} exceeds 25% of ${faab_left}",
                    )
                )

    # 4. Never suggest more than this room has ever paid.
    if room_max_bid:
        for r in rows:
            if (r.bid or 0) > room_max_bid:
                out.append(
                    Finding(
                        CRITICAL,
                        "room-max",
                        f"{r.name} bid ${r.bid} tops the room record ${room_max_bid}",
                    )
                )

    # 5. A stale board is what made four starters project as healthy.
    m = BOARD_AGE_RE.search(text)
    if m and int(m.group("age")) > max_board_age_h:
        out.append(Finding(WARN, "board-age", f"Gold board is {m.group('age')}h old"))
    elif not m:
        out.append(Finding(WARN, "board-age", "no Gold board age in the report"))

    # 6. Slot accounting must be present, or a drop gets recommended blind.
    if not SLOTS_RE.search(text):
        out.append(
            Finding(WARN, "roster-mechanics", "no roster mechanics block in the report")
        )
    if not IR_ACCEPTS_RE.search(text) and "IR " in text:
        out.append(Finding(WARN, "ir-rules", "IR slots shown without what they accept"))

    # 7. A bid with no demand context is the old median-guessing failure.
    priced = [r for r in rows if r.bid is not None]
    if priced and not any("[" in r.tail for r in priced):
        out.append(
            Finding(
                CRITICAL,
                "no-demand",
                "bids suggested with no [demand] history behind them",
            )
        )

    order = {CRITICAL: 0, WARN: 1}
    return sorted(out, key=lambda f: order.get(f.level, 9))


def summarise(findings: Sequence[Finding]) -> Dict[str, Any]:
    """Counts plus a pass/fail verdict (any CRITICAL fails)."""
    crit = [f for f in findings if f.level == CRITICAL]
    return {
        "critical": len(crit),
        "warnings": len(findings) - len(crit),
        "passed": not crit,
    }
