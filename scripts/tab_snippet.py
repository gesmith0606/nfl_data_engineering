#!/usr/bin/env python3
"""Print the project's claim-filing JS for a logged-in Chrome tab (claude-in-chrome).

The fallback route when the Playwright profile is logged out and no debug Chrome
is up (waiver_preflight.py says so). It reuses the SAME snippets
submit_claims.py runs — with their guards: ESPN checks the logged-in account owns
our team and the add is still at its dry-run status; Yahoo checks the form posts
to our team and still files a waiver claim — instead of hand-writing new JS.
Each `espn`/`yahoo` call also writes a POSTING row to the claims ledger; record
the outcome with `record` afterwards.

    python scripts/tab_snippet.py espn  --add "C.J. Stroud" --add-id 4432577 \
        --drop "Malik Willis" --drop-id 4242512 --bid 3 --week 10
    python scripts/tab_snippet.py yahoo --add "Tyler Shough" --add-id 41825 \
        --drop "Sam Darnold" --drop-id 30973 --bid 2 [--check-only]
    python scripts/tab_snippet.py record --league la_liga --add "C.J. Stroud" \
        --verdict PENDING --msg "ESPN 200 WAIVER PENDING"

Paste the printed JS into javascript_tool on a fantasy.espn.com / Yahoo league tab
(same origin). Run each only after George's OK on the claims table.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config  # noqa: E402
from src import waiver_claims as wc  # noqa: E402
from src import waiver_sites as ws  # noqa: E402

LEDGER = REPO_ROOT / "data" / "draft" / "claims_ledger.jsonl"
VERDICTS = ("POSTING", "PENDING", "CONFIRMED", "FAILED", "UNKNOWN", "NOT FOUND")


def ledger_row(
    league: str,
    add: str,
    add_id: str,
    drop: Optional[str],
    bid: int,
    verdict: str,
    msg: str = "",
) -> str:
    """One claims_ledger.jsonl line (same fields submit_claims.py writes)."""
    return json.dumps(
        {
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
            "league": league,
            "add": add,
            "add_id": str(add_id),
            "drop": drop,
            "bid": bid,
            "verdict": verdict,
            "msg": msg,
        }
    )


def espn_js(
    add_id: str,
    drop_id: Optional[str],
    bid: int,
    week: int,
    season: int = 2026,
    free_agent: bool = False,
) -> str:
    preset = config.LEAGUE_PRESETS["la_liga"]
    body = wc.espn_claim_body(
        int(preset["my_team_id"]), week, add_id, drop_id, bid, free_agent=free_agent
    )
    args = {
        "season": season,
        "lid": int(preset["league_id"]),
        "body": body,
        "expect": "FREEAGENT" if free_agent else "WAIVERS",
    }
    return "await " + ws.ESPN_SUBMIT_JS.replace("__ARGS__", json.dumps(args))


def yahoo_js(add_id: str, drop_id: Optional[str], bid: int, submit: bool = True) -> str:
    preset = config.LEAGUE_PRESETS["feetball"]
    args = {
        "lid": str(preset["league_id"]),
        "team": int(preset["my_team_id"]),
        "apid": str(add_id),
        "dpid": drop_id or "",
        "faab": int(bid),
        "submit": submit,
        "expect_claim": True,
    }
    return "await " + ws.YAHOO_FORM_JS.replace("__ARGS__", json.dumps(args))


LEDGER_DAYS = 6  # same window submit_claims.ledger_blocks uses


def ledger_blocks(league: str, add_id: str, now: Optional[dt.datetime] = None) -> str:
    """Why this add may not be filed again ('' when it may).

    Mirrors ``submit_claims.ledger_blocks``: the latest row for
    ``(league, add_id)`` inside the window blocks unless it is FAILED. Without
    it a re-run of this command (context compacted, a PENDING ESPN claim that
    the in-tab guard cannot see) would post the same claim twice.
    """
    if not LEDGER.exists():
        return ""
    cutoff = (now or dt.datetime.now()) - dt.timedelta(days=LEDGER_DAYS)
    last = None
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            ts = dt.datetime.fromisoformat(row["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        if row.get("league") == league and row.get("add_id") == str(add_id):
            if ts >= cutoff:
                last = row
    if not last or last.get("verdict") == "FAILED":
        return ""
    return (
        f"already filed {last['ts']} ({last['verdict']}) per {LEDGER.name} — "
        "check the site / check_pending_claims.py first; --force only if it is "
        "truly gone"
    )


def keeper_drop(league: str, drop: Optional[str]) -> bool:
    """True when ``drop`` is one of our keepers in a keeper league."""
    path = config.LEAGUE_PRESETS[league].get("keepers_file")
    if not drop or not path:
        return False
    return wc.player_key(drop) in wc.load_keepers(REPO_ROOT / path)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("espn", "yahoo"):
        p = sub.add_parser(name)
        p.add_argument("--add", required=True)
        p.add_argument("--add-id", required=True)
        p.add_argument("--drop")
        p.add_argument("--drop-id")
        p.add_argument("--bid", type=int, required=True)
        p.add_argument(
            "--force",
            action="store_true",
            help="file even though the ledger shows this add already filed",
        )
        if name == "espn":
            p.add_argument(
                "--week", type=int, required=True, help="ESPN's CURRENT scoringPeriodId"
            )
            p.add_argument("--free-agent", action="store_true")
        else:
            p.add_argument(
                "--check-only", action="store_true", help="read the form, post nothing"
            )
    r = sub.add_parser("record")
    r.add_argument("--league", required=True, choices=["la_liga", "feetball"])
    r.add_argument("--add", required=True)
    r.add_argument("--add-id", default="")
    r.add_argument("--drop")
    r.add_argument("--bid", type=int, default=0)
    r.add_argument("--verdict", required=True, choices=VERDICTS)
    r.add_argument("--msg", default="")
    a = ap.parse_args(argv)

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    if a.cmd == "record":
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(
                ledger_row(a.league, a.add, a.add_id, a.drop, a.bid, a.verdict, a.msg)
                + "\n"
            )
        print(f"ledger: {a.league} {a.add} -> {a.verdict}")
        return 0

    if a.cmd == "espn":
        js, league = (
            espn_js(a.add_id, a.drop_id, a.bid, a.week, free_agent=a.free_agent),
            "la_liga",
        )
        posting = True
    else:
        js, league = (
            yahoo_js(a.add_id, a.drop_id, a.bid, submit=not a.check_only),
            "feetball",
        )
        posting = not a.check_only
    if keeper_drop(league, a.drop):
        print(f"REFUSED: {a.drop} is one of our {league} keepers — never a drop")
        return 2
    if posting:
        why = ledger_blocks(league, a.add_id)
        if why and not a.force:
            print(f"REFUSED: {a.add} — {why}")
            return 2
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(
                ledger_row(
                    league,
                    a.add,
                    a.add_id,
                    a.drop,
                    a.bid,
                    "POSTING",
                    "via claude-in-chrome tab_snippet",
                )
                + "\n"
            )
    print(js)
    return 0


if __name__ == "__main__":
    sys.exit(main())
