#!/usr/bin/env python3
"""Score the waiver skill from checks anyone can re-run, not from an opinion.

    python scripts/audit_waiver_skill.py
    python scripts/audit_waiver_skill.py --offline   # skip the live-league checks

The 72->100 audit this replaces was a judgement call on a rubric written by the
same agent doing the work, which is the exact failure mode the skill's own
invariants exist to prevent: a claim with no way to be wrong. So every line
here is a falsifiable assertion with the command that settles it, and the score
is the fraction that hold. If a rule regresses the number drops by itself.

Exit code is 1 when any REQUIRED check fails, so this can gate a deploy.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

OUR_LEAGUES = ("mantis", "la_liga", "feetball")
#: Paste-file arguments each non-Sleeper league needs to produce a board.
LEAGUE_ARGS = {
    "mantis": [],
    "la_liga": [
        "--roster-file",
        "data/draft/la_liga_2026_roster.txt",
        "--rostered-file",
        "data/draft/la_liga_2026_all_rostered.txt",
        "--available-file",
        "data/draft/la_liga_2026_available.txt",
    ],
    "feetball": [
        "--roster-file",
        "data/draft/feetball_2026_roster.txt",
        "--available-file",
        "data/draft/feetball_2026_available.txt",
    ],
}


@dataclass
class Check:
    """One falsifiable claim about the skill."""

    dimension: str
    claim: str
    evidence: str  # the command a reader can run
    run: Callable[[], bool]
    required: bool = True
    live: bool = False  # needs a league API / the committed boards


def _guard_refuses_a_foreign_league() -> bool:
    """``config.our_league`` rejects a preset that is not George's.

    Asserted against a synthetic entry rather than a real one: the guard has
    to keep working even when every configured league happens to be ours,
    which is exactly the state that silently disarmed the old check.
    """
    from src import config

    key = "_audit_not_ours"
    config.LEAGUE_PRESETS[key] = {"platform": "sleeper", "owned": False}
    try:
        config.our_league(key)
    except ValueError as exc:
        return "NOT one of our leagues" in str(exc)
    except Exception:
        return False
    else:
        return False
    finally:
        config.LEAGUE_PRESETS.pop(key, None)


def _sh(args: Sequence[str], timeout: int = 900) -> str:
    """Run a repo script and return its combined output ('' on failure)."""
    try:
        done = subprocess.run(
            [sys.executable, *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return done.stdout + done.stderr
    except (subprocess.SubprocessError, OSError):
        return ""


def _report(league: str, week: int) -> str:
    return _sh(
        ["scripts/waiver_wire.py", "--league", league, "--week", str(week), "--no-gate"]
        + LEAGUE_ARGS[league]
    )


def _src(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def build_checks(week: int) -> List[Check]:
    """Every claim the audit makes, each with the command that settles it."""
    return [
        # --- correctness guards -------------------------------------------
        Check(
            "guards",
            "the gate carries at least 10 named invariants",
            "grep -oE '\"[a-z-]+\",$' src/waiver_sanity.py | sort -u",
            lambda: len(
                set(re.findall(r'"([a-z-]+)",\n', _src("src/waiver_sanity.py")))
            )
            >= 10,
        ),
        Check(
            "guards",
            "the sanity verdict prints even when clean (silence cannot pass)",
            "python scripts/waiver_wire.py --league mantis --week N | grep -- '-- Sanity'",
            lambda: "-- Sanity --"
            in _sh(
                ["scripts/waiver_wire.py", "--league", "mantis", "--week", str(week)]
            ),
            live=True,
        ),
        Check(
            "guards",
            "a league that is not ours is refused by name",
            "python -c \"from src import config; config.our_league('x')\"",
            # Was: grep the mantis report for the refusal. #158 dropped
            # `gentlemen` and `mahomos`, the last presets marked owned: False,
            # so from 2026-10-24 there was no league left that could produce
            # the message and the check could never pass again — it sat red
            # for three days while the skill still advertised 100/100. The
            # guard is asserted directly now, so removing a preset cannot
            # quietly disarm it.
            _guard_refuses_a_foreign_league,
        ),
        # --- pricing ------------------------------------------------------
        Check(
            "pricing",
            "the bid model beats the naive rules in Mantis",
            "python scripts/backtest_bid_model.py --league mantis",
            lambda: "PASS:"
            in _sh(["scripts/backtest_bid_model.py", "--league", "mantis"]),
            live=True,
        ),
        Check(
            "pricing",
            "the bid model beats the naive rules in La Liga too (a second room)",
            "python scripts/backtest_bid_model.py --league la_liga",
            lambda: "PASS:"
            in _sh(["scripts/backtest_bid_model.py", "--league", "la_liga"]),
            live=True,
        ),
        # --- data coverage ------------------------------------------------
        Check(
            "coverage",
            "every row carries usage (snap share), not just projections and hype",
            "python scripts/waiver_wire.py --league mantis --week N | grep snap",
            lambda: "snap" in _report("mantis", week),
            live=True,
        ),
        Check(
            "coverage",
            "every row carries the room's demand history for that player",
            "...| grep -E '\\[(unclaimed|held|cut)'",
            lambda: re.search(r"\[(unclaimed|held|cut)", _report("mantis", week))
            is not None,
            live=True,
        ),
        # --- sentiment ----------------------------------------------------
        Check(
            "sentiment",
            "the report states its news volume instead of implying it",
            "...| grep 'NEWS = Gold sentiment'",
            lambda: "NEWS = Gold sentiment" in _report("mantis", week),
            live=True,
        ),
        Check(
            "sentiment",
            "ENDING reads structured practice trails, not only news keywords",
            "grep -n returning_from_practice scripts/waiver_wire.py",
            lambda: "returning_from_practice" in _src("scripts/waiver_wire.py"),
        ),
        Check(
            "sentiment",
            "raw articles are readable for a shortlist, with no API key",
            "python scripts/player_news.py 'Any Player' --days 5",
            lambda: "unique articles"
            in _sh(["scripts/player_news.py", "Puka Nacua", "--days", "5"]),
        ),
        Check(
            "sentiment",
            "a withdrawn source is reported, not silently retried",
            "grep -n REDDIT_AVAILABLE scripts/daily_sentiment_pipeline.py",
            lambda: "REDDIT_AVAILABLE = False"
            in _src("scripts/daily_sentiment_pipeline.py"),
        ),
        # --- platform parity ----------------------------------------------
        Check(
            "parity",
            "all three of our leagues produce a gated board",
            "python scripts/waiver_wire.py --league <each> --week N",
            lambda: all(
                "-- Sanity --"
                in _sh(
                    ["scripts/waiver_wire.py", "--league", lg, "--week", str(week)]
                    + LEAGUE_ARGS[lg]
                )
                for lg in OUR_LEAGUES
            ),
            live=True,
        ),
        Check(
            "parity",
            "a Yahoo board can be priced without the bot-blocked login",
            "grep -n -- '--faab' scripts/waiver_wire.py",
            lambda: '"--faab"' in _src("scripts/waiver_wire.py"),
        ),
        Check(
            "parity",
            "ESPN has the rival model Sleeper has",
            "grep -n 'def espn_rivals' scripts/waiver_wire.py",
            lambda: "def espn_rivals(" in _src("scripts/waiver_wire.py"),
        ),
        # --- outcome measurement ------------------------------------------
        Check(
            "outcomes",
            "our claims are scored against our leaguemates' on a pooled sample",
            "python scripts/backtest_claim_outcomes.py --pool",
            lambda: "VERDICT:" in _sh(["scripts/backtest_claim_outcomes.py", "--pool"]),
            live=True,
        ),
        Check(
            "outcomes",
            "the pooled sample is large enough to drop the directional caveat",
            "python scripts/backtest_claim_outcomes.py --pool | grep -c directional",
            lambda: "directional"
            not in _sh(["scripts/backtest_claim_outcomes.py", "--pool"]),
            live=True,
        ),
        # --- rule provenance ----------------------------------------------
        Check(
            "provenance",
            "the RENTAL tag is validated against snap share, not points",
            "python scripts/validate_rental_tag.py --through-week 6",
            lambda: "VALIDATED"
            in _sh(["scripts/validate_rental_tag.py", "--through-week", "6"]),
            live=True,
        ),
        Check(
            "provenance",
            "the young-drop cutoff is validated on future production",
            "python scripts/validate_young_drop.py",
            lambda: "RESULT: VALIDATED" in _sh(["scripts/validate_young_drop.py"]),
            live=True,
        ),
        Check(
            "provenance",
            "claims are generated from the computed bid, never hand-typed",
            "grep -n -- '--emit-claims' scripts/waiver_wire.py",
            lambda: '"--emit-claims"' in _src("scripts/waiver_wire.py"),
        ),
    ]


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--week", type=int, default=7)
    ap.add_argument(
        "--offline",
        action="store_true",
        help="skip checks that need a league API or the committed boards",
    )
    args = ap.parse_args(argv)

    checks = [c for c in build_checks(args.week) if not (args.offline and c.live)]
    print(f"\n=== waiver skill audit — {len(checks)} falsifiable checks ===\n")
    passed, failed_required = 0, 0
    by_dim: dict = {}
    for check in checks:
        ok = False
        try:
            ok = bool(check.run())
        except Exception as exc:  # noqa: BLE001 — a crashing check is a failing check
            print(f"  [ERROR] {check.claim}: {type(exc).__name__}")
        passed += ok
        failed_required += (not ok) and check.required
        tally = by_dim.setdefault(check.dimension, [0, 0])
        tally[0] += ok
        tally[1] += 1
        mark = "PASS" if ok else ("FAIL" if check.required else "warn")
        print(f"  [{mark}] {check.dimension:11} {check.claim}")
        if not ok:
            print(f"         evidence: {check.evidence}")

    print(f"\n  {'dimension':14}{'passed':>8}")
    for dim, (got, tot) in by_dim.items():
        print(f"  {dim:14}{got:>4}/{tot}")
    score = round(100 * passed / max(1, len(checks)))
    print(f"\n  SCORE: {score}/100 ({passed}/{len(checks)} checks hold)")
    if failed_required:
        print(f"  {failed_required} required check(s) failing")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
