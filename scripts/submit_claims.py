#!/usr/bin/env python3
"""Check and (only with --submit) file a week's waiver claims; then read them back.

    python scripts/submit_claims.py --claims data/draft/claims_week6.yaml  # dry run
    python scripts/submit_claims.py --claims data/draft/claims_week6.yaml --submit

Claims file (``data/draft/claims_week<N>.yaml``)::

    claims:
      - {league: la_liga,  add: Commanders D/ST, drop: Bears D/ST, bid: 1, priority: 1}
      - {league: feetball, add: Bo Nix, drop: Cairo Santos, bid: 3}
      - {league: mantis,   add: Braelon Allen, drop: Emanuel Wilson, bid: 55}

Every claim is checked LIVE first (weekly-waivers Step 4b): the add must be on
waivers, the drop on our roster and not a keeper, the bid within the FAAB left,
no claim for the add already pending, no same-name player without a pinned
``add_id``/``drop_id``; Yahoo's own add/drop form must post to our team, offer
the drop, and file a "Create claim". Free agents (added immediately, no cancel)
need ``--allow-free-agent``. The table is printed either way. ``--submit`` files
nothing unless every claim passes, files ESPN/Yahoo claims in priority order,
stops at the first unclear result (never retried: no site has idempotency, a
retry can spend FAAB twice), then re-reads each league; exit 2 unless every
filed claim is CONFIRMED.

Mantis (Sleeper) is checked but never submitted: Sleeper's public API is
read-only and its Terms (2026-10-06, §11.1) ban scripted access to the private
API the app uses - enter those claims in the Sleeper app.

ESPN and Yahoo run inside a Chrome started with remote debugging and logged into
both sites (``chrome --remote-debugging-port=9333 --user-data-dir=<profile>``).
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config  # noqa: E402
from src import waiver_claims as wc  # noqa: E402
from src import waiver_sites as ws  # noqa: E402

MY_LEAGUES = ("mantis", "la_liga", "feetball")
#: Seconds to wait for a filed ESPN claim to show on the read replica (2-5 s lag).
READ_BACK_WAIT_S = (3, 4, 8)
OK, FAILED, UNKNOWN = "OK", "FAILED", "UNKNOWN"


def _keepers(preset: Mapping[str, Any]) -> Set[str]:
    """Our keepers; a configured but missing/empty keepers file is an error."""
    path = preset.get("keepers_file")
    if not path:
        return set()
    keep = wc.load_keepers(REPO_ROOT / path)
    if not keep:
        raise RuntimeError(f"keepers file {path} is missing or lists no '*' keepers")
    return keep


def check(
    league: str,
    claims: Sequence[wc.Claim],
    season: int,
    cdp_url: str,
    allow_free_agent: bool = False,
) -> Tuple[List[wc.CheckedClaim], Dict[str, Any]]:
    """Resolve + validate one league's claims against the live site.

    Returns:
        ``(checked claims, context)`` — context carries what the writer needs
        (the ESPN scoring period, the open page).
    """
    preset = config.LEAGUE_PRESETS[league]
    platform, lid = preset["platform"], str(preset["league_id"])
    keepers = _keepers(preset)
    if platform == "espn":
        team = int(preset["my_team_id"])
        page = ws.site_page("espn", lid, team, cdp_url)
        s = ws.espn_state(page, season, lid, team)
        index = wc.index_players(wc.espn_players(s["pool"], s["rosters"], team))
        left = int(s["budget"] or 0) - int(s["spent"] or 0)
        pending = wc.espn_claim_records(s["transactions"], team, s["names"], league)
        checked = wc.check_league(
            claims,
            index,
            left,
            keepers,
            int(s["min_bid"] or 0),
            pending=pending,
            allow_free_agent=allow_free_agent,
        )
        return checked, {
            "page": page,
            "scoring_period": s["scoring_period"],
            "faab_left": left,
        }
    if platform == "yahoo":
        team = int(preset["my_team_id"])
        page = ws.site_page("yahoo", lid, team, cdp_url)
        names = [c.add for c in claims] + [c.drop for c in claims if c.drop]
        s = ws.yahoo_state(page, lid, team, [wc.search_name(n) for n in names])
        if not s.get("logged_in"):
            raise RuntimeError("Yahoo team page has no Transactions box - logged in?")
        checked = wc.check_league(
            claims,
            wc.index_players(wc.yahoo_players(s["search"])),
            s.get("faab_left"),
            keepers,
            pending=wc.yahoo_claim_records(s["pending"], league),
            allow_free_agent=allow_free_agent,
        )
        for i, c in enumerate(checked):
            if c.ok:  # Yahoo's own form must agree before anything is posted
                form = ws.yahoo_form(
                    page,
                    lid,
                    team,
                    c.add.pid,
                    c.drop.pid if c.drop else None,
                    c.claim.bid,
                )
                extra = wc.yahoo_form_problems(form, c.add, c.drop, f"/f1/{lid}/{team}")
                checked[i] = dataclasses.replace(c, problems=c.problems + tuple(extra))
        return checked, {"page": page, "faab_left": s.get("faab_left")}
    if platform == "sleeper":
        from src.sleeper_player_map import load_sleeper_players

        s = ws.sleeper_state(lid, preset["my_user"], legs=[])
        registry = load_sleeper_players(max_age_days=1)
        players = wc.sleeper_players(
            registry, s["rosters"], s["owners"], s["my_roster_id"]
        )
        checked = wc.check_league(
            claims, wc.index_players(players), s["faab_left"], keepers
        )
        return checked, {"faab_left": s["faab_left"]}
    raise LookupError(f"{league}: unsupported platform {platform!r}")


def _status(res: Mapping[str, Any]) -> int:
    """HTTP status from a snippet result; -1 when missing (an unclear outcome)."""
    try:
        return int(res.get("status"))
    except (TypeError, ValueError):
        return -1


def submit_one(
    league: str, c: wc.CheckedClaim, ctx: Mapping[str, Any], season: int
) -> Tuple[str, str]:
    """File one claim.

    Returns:
        ``(OK | FAILED | UNKNOWN, message)``. FAILED = the site (or the browser
        pre-check) refused it, nothing was filed. UNKNOWN = it may or may not
        have been filed (5xx, no status, Yahoo re-served its form).
    """
    preset = config.LEAGUE_PRESETS[league]
    lid = str(preset["league_id"])
    if preset["platform"] == "espn":
        body = wc.espn_claim_body(
            int(preset["my_team_id"]),
            int(ctx["scoring_period"]),
            c.add.pid,
            c.drop.pid if c.drop else None,
            c.claim.bid,
            free_agent=c.add.status == wc.FREE_AGENT,
        )
        res = ws.espn_submit(ctx["page"], season, lid, body)
        status = _status(res)
        errors = "; ".join(f"{t}: {m}" for t, m in res.get("errors") or [])
        detail = (res.get("transaction") or {}).get("status") or errors
        if status == 0 or 400 <= status < 500:
            verdict = FAILED  # refused by the browser pre-check or by ESPN
        else:
            verdict = OK if 200 <= status < 300 else UNKNOWN
        return verdict, f"HTTP {status} {detail}".strip()
    res = ws.yahoo_form(
        ctx["page"],
        lid,
        int(preset["my_team_id"]),
        c.add.pid,
        c.drop.pid if c.drop else None,
        c.claim.bid,
        submit=True,
        expect_claim=c.add.status == wc.WAIVERS,
    )
    posted = res.get("posted")
    if not posted:  # stopped in the browser before posting
        return FAILED, f"not posted: {res.get('error') or 'no add/drop form'}"
    status = _status(posted)
    msg = f"HTTP {status} -> {posted.get('path')} " + " | ".join(
        posted.get("messages") or []
    )
    if 200 <= status < 400 and not posted.get("form_again"):
        return OK, msg.strip()
    if 400 <= status < 500:
        return FAILED, msg.strip()
    # Yahoo re-serving the form usually means a rejection, but its markup for
    # that was never captured — treat it as unclear and read back.
    return UNKNOWN, msg.strip()


def read_back(
    leagues: Sequence[str],
    filed: Mapping[str, Sequence[wc.CheckedClaim]],
    season: int,
    cdp_url: str,
) -> bool:
    """Print each league's claims as the site shows them.

    Returns:
        True when every filed waiver claim shows as pending. Free-agent adds
        execute immediately and are not tracked as claims - check the roster.
    """
    print("\n=== Read-back (check_pending_claims) ===")
    all_ok = True
    for league in leagues:
        preset = config.LEAGUE_PRESETS[league]
        want = [c for c in filed.get(league, ()) if c.add.status != wc.FREE_AGENT]
        records: List[wc.ClaimRecord] = []

        def found(c: wc.CheckedClaim) -> bool:
            return any(wc.is_pending_for(r, c.add.name) for r in records)

        for wait in READ_BACK_WAIT_S if want else (0,):
            time.sleep(wait)
            try:
                summary, records = ws.read_claims(league, preset, season, cdp_url)
            except (LookupError, RuntimeError, OSError) as exc:
                summary, records = f"UNAVAILABLE: {exc}", []
                all_ok = False
            if all(found(c) for c in want):
                break
        print(f"\n== {league} - {summary}")
        print(wc.render_records(records))
        for c in filed.get(league, ()):
            if c.add.status == wc.FREE_AGENT:
                print(
                    f"  FREE AGENT ADD: #{c.claim.priority} {c.add.name} - check roster"
                )
                continue
            seen = found(c)
            all_ok &= seen
            print(
                f"  {'CONFIRMED' if seen else 'NOT FOUND'}: "
                f"#{c.claim.priority} {c.add.name}"
            )
    return all_ok


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--claims", type=Path, required=True, help="claims YAML file")
    ap.add_argument(
        "--submit", action="store_true", help="actually file the ESPN/Yahoo claims"
    )
    ap.add_argument(
        "--allow-free-agent",
        action="store_true",
        help="also file free-agent adds (they execute immediately, no cancel)",
    )
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--cdp-url", default=ws.DEFAULT_CDP_URL)
    args = ap.parse_args(argv)

    try:
        claims = wc.load_claims(args.claims, MY_LEAGUES)
    except wc.ClaimsFileError as exc:
        sys.exit(str(exc))
    leagues = [lg for lg in MY_LEAGUES if any(c.league == lg for c in claims)]

    checked: Dict[str, List[wc.CheckedClaim]] = {}
    ctx: Dict[str, Dict[str, Any]] = {}
    unreadable = []
    for league in leagues:
        try:
            checked[league], ctx[league] = check(
                league,
                [c for c in claims if c.league == league],
                args.season,
                args.cdp_url,
                args.allow_free_agent,
            )
        except (LookupError, RuntimeError, OSError) as exc:
            unreadable.append(f"{league}: could not check - {exc}")

    print(f"Claims: {args.claims}\n")
    print(wc.render_checked([c for lg in leagues for c in checked.get(lg, [])]))
    for league in leagues:
        if league in ctx:
            print(f"  {league}: FAAB left ${ctx[league].get('faab_left')}")
    for line in unreadable:
        print(f"  x {line}")

    blocked = bool(unreadable) or any(not c.ok for cs in checked.values() for c in cs)
    manual = list(checked.get("mantis", []))
    auto = [lg for lg in leagues if lg != "mantis" and lg in checked]
    if manual:
        print("\nMantis (Sleeper) - enter in the Sleeper app (never scripted):")
        for c in manual:
            drop = f", drop {c.drop.name}" if c.drop else ""
            print(f"  {c.claim.priority}. claim {c.add.name} for ${c.claim.bid}{drop}")
    if blocked:
        print("\nBLOCKED - fix the claims file (x lines above). Nothing was submitted.")
        return 1
    queue = [(lg, c) for lg in auto for c in checked[lg]]
    if not queue:
        print("\nNo ESPN/Yahoo claims to submit.")
        return 0
    if not args.submit:
        print(
            f"\nDRY RUN - nothing submitted. To file the {len(queue)} ESPN/Yahoo "
            "claim(s) above:\n  python scripts/submit_claims.py "
            f"--claims {args.claims.as_posix()} --cdp-url {args.cdp_url} --submit"
        )
        return 0

    print("\n=== Submitting ===")
    filed: Dict[str, List[wc.CheckedClaim]] = {}
    failures = 0
    for i, (league, c) in enumerate(queue):
        tag = f"{league} #{c.claim.priority} {c.add.name}"
        try:
            verdict, msg = submit_one(league, c, ctx[league], args.season)
        except Exception as exc:  # noqa: BLE001 — unclear outcome: never retry
            verdict, msg = UNKNOWN, str(exc)
        if verdict == UNKNOWN:
            print(f"  ?? {tag}: outcome UNKNOWN ({msg})")
            print("  Stopping - not retrying (a retry can file it twice).")
            for lg, rest in queue[i + 1 :]:
                print(f"  NOT ATTEMPTED: {lg} #{rest.claim.priority} {rest.add.name}")
            filed.setdefault(league, []).append(c)
            read_back(auto, filed, args.season, args.cdp_url)
            return 2
        failures += verdict == FAILED
        if verdict == OK:
            filed.setdefault(league, []).append(c)
        print(f"  {verdict} {tag}: {msg}")
    confirmed = read_back(auto, filed, args.season, args.cdp_url)
    if manual:
        print("\nReminder: Mantis claims above still need entering in the Sleeper app.")
    return 0 if confirmed and not failures else 2


if __name__ == "__main__":
    sys.exit(main())
