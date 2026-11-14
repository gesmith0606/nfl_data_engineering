#!/usr/bin/env python3
"""Waiver preflight: every prerequisite of the weekly-waivers skill, checked in one go.

    python scripts/waiver_preflight.py                # all checks
    python scripts/waiver_preflight.py --build-board  # + build a missing board
    python scripts/waiver_preflight.py --skip-browser # skip the Playwright probe

Why it exists (2026-11-10): the week-10 run spent an hour discovering, one at a
time, that the cron board was missing (3 weeks of sanity-gate failures), local
ingests failed SSL, the Playwright profile was logged out of ESPN and Yahoo, no
debug Chrome was up, and the Yahoo token predated the API approval. Each check
here prints the ROUTE the skill should take, so a dead route costs one line, not
an hour. It changes nothing on any fantasy site.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

LEDGER = REPO_ROOT / "data" / "draft" / "claims_ledger.jsonl"
GOLD = REPO_ROOT / "data" / "gold" / "projections"
YAHOO_PROBE = (
    "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/"
    "games;game_keys=nfl/leagues?format=json"
)


@dataclass(frozen=True)
class Check:
    """One preflight result line."""

    name: str
    ok: bool
    detail: str
    fix: str = ""


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def classify_yahoo(status: Optional[int], body: str) -> Tuple[bool, str, str]:
    """Yahoo API probe -> (ok, detail, fix)."""
    if status is None:
        return (
            False,
            "no token (data/yahoo_tokens.json missing or unreadable)",
            "restore YAHOO_TOKENS from Bitwarden or run scripts/yahoo_auth.py — "
            "runbook 'Yahoo API access'",
        )
    if status == 200:
        return True, "fantasy read scope OK", ""
    if status == 401 and "additional_authorization_required" in body:
        return (
            False,
            "token predates the 2026-10-28 approval (no fspt-r scope)",
            "re-grant once: scripts/yahoo_auth.py (paste the code in the terminal, "
            "never in chat); refreshing never adds a scope",
        )
    return False, f"HTTP {status}", "check YAHOO_CLIENT_ID/SECRET in .env"


def board_files(season: int, week: int) -> List[Path]:
    """Weekly Gold boards for (season, week) — both padded and unpadded dirs."""
    out: List[Path] = []
    for d in {f"week={week}", f"week={week:02d}"}:
        out += sorted(
            (GOLD / f"season={season}" / d).glob("projections_half_ppr_*.parquet")
        )
    return out


def board_build_commands(season: int, week: int) -> List[List[str]]:
    """The local Bronze -> Silver -> Gold chain the Tuesday cron would have run."""
    py = sys.executable
    cmds = [
        [
            py,
            "scripts/bronze_ingestion_simple.py",
            "--season",
            str(season),
            "--week",
            str(week),
            "--data-type",
            t,
        ]
        for t in (
            "player_weekly",
            "snap_counts",
            "injuries",
            "rosters",
            "depth_charts",
            "schedules",
        )
    ]
    cmds += [
        [py, f"scripts/{s}.py", "--seasons", str(season)]
        for s in (
            "silver_player_transformation",
            "silver_team_transformation",
            "silver_game_context_transformation",
            "silver_player_quality_transformation",
        )
    ]
    cmds.append(
        [
            py,
            "scripts/generate_projections.py",
            "--week",
            str(week),
            "--season",
            str(season),
            "--scoring",
            "half_ppr",
        ]
    )
    return cmds


#: A post that may or may not have happened: never re-file, resolve first.
UNCLEAR = ("ATTEMPT", "POSTING", "UNKNOWN")
#: Posted fine; only the waiver run's outcome is still unseen.
AWAITING = ("OK", "PENDING")


def unresolved_claims(
    lines: List[str], today: dt.date, days: int = 8
) -> Tuple[List[str], List[str]]:
    """Recent ledger claims by their LAST row: (unclear, awaiting_outcome).

    ``unclear`` = ATTEMPT (crash mid-POST, what submit_claims writes) /
    POSTING / UNKNOWN — must be resolved before any new advice. ``awaiting``
    = OK / PENDING — filed normally; just confirm whether the claim won.
    """
    last: dict = {}
    for ln in lines:
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        last[(row.get("league"), row.get("add"))] = row
    unclear: List[str] = []
    awaiting: List[str] = []
    for (league, add), row in last.items():
        try:
            when = dt.date.fromisoformat(str(row.get("ts", ""))[:10])
        except ValueError:
            continue
        if (today - when).days > days:
            continue
        line = f"{league}: {add} (${row.get('bid')}) is {row.get('verdict')}"
        if row.get("verdict") in UNCLEAR:
            unclear.append(line)
        elif row.get("verdict") in AWAITING:
            awaiting.append(line)
    return unclear, awaiting


def routes(results: dict) -> List[str]:
    """Pick the read/file route per site from the check results (True = usable)."""
    pw = results.get("playwright")
    cdp = results.get("debug_chrome")
    espn_cookie = results.get("espn_cookies")
    yahoo_api = results.get("yahoo_api")
    tab = "claude-in-chrome tab (runbook 'Chrome-tab fallback')"
    espn_read = (
        "ESPN cookies (direct)"
        if espn_cookie
        else (
            "--espn-browser"
            if pw
            else "refresh_league_pools.py (debug Chrome)" if cdp else tab
        )
    )
    espn_file = (
        "submit_claims.py --submit"
        if pw
        else "submit_claims.py --submit --espn-http" if espn_cookie else tab
    )
    yahoo_read = (
        "Yahoo API"
        if yahoo_api
        else (
            "--yahoo-browser"
            if pw
            else "refresh_league_pools.py (debug Chrome)" if cdp else tab
        )
    )
    yahoo_file = "submit_claims.py --submit" if pw else tab + " — then VERIFY pending"
    return [
        f"ESPN  read: {espn_read}",
        f"ESPN  file: {espn_file}",
        f"Yahoo read: {yahoo_read}",
        f"Yahoo file: {yahoo_file}",
        "Mantis file: George in the Sleeper app (ToS) — always",
    ]


# ---------------------------------------------------------------------------
# Live probes
# ---------------------------------------------------------------------------


def _resolve_week() -> Tuple[int, int]:
    spec = importlib.util.spec_from_file_location(
        "resolve_pipeline_week", REPO_ROOT / "scripts" / "resolve_pipeline_week.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    season, week, _ = mod.resolve_target_week(dt.date.today())
    return season, week


def check_git() -> Check:
    def git(*a: str) -> str:
        return subprocess.run(
            ["git", *a], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
        ).stdout.strip()

    git("fetch", "-q", "origin", "main")
    behind = git("rev-list", "--count", "HEAD..origin/main") or "?"
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    ok = behind == "0"
    return Check(
        "git",
        ok,
        f"{branch}, {behind} commit(s) behind origin/main",
        "" if ok else "git pull (stash data/draft/ pool files first)",
    )


def check_board(season: int, week: int) -> Check:
    files = board_files(season, week)
    if files:
        return Check("board", True, f"week {week} Gold board: {files[-1].name}")
    return Check(
        "board",
        False,
        f"no week {week} Gold board (cron failed or not run)",
        "python scripts/waiver_preflight.py --build-board",
    )


def check_yahoo() -> Check:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        from src.yahoo_oauth import YahooOAuth

        tok = YahooOAuth().get_access_token()
    except Exception:  # noqa: BLE001 - any failure here means "no usable token"
        tok = None
    if not tok:
        ok, detail, fix = classify_yahoo(None, "")
        return Check("yahoo_api", ok, detail, fix)
    req = urllib.request.Request(
        YAHOO_PROBE, headers={"Authorization": f"Bearer {tok}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, body = r.status, ""
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read().decode("utf-8", "replace")[:400]
    except OSError as e:
        return Check("yahoo_api", False, f"network: {e}", "retry")
    ok, detail, fix = classify_yahoo(status, body)
    return Check("yahoo_api", ok, detail, fix)


def check_espn_cookies(season: int) -> Check:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        from src import config
        from src.espn_league import cookies_from_env, fetch_league

        cookies = cookies_from_env()
        if not cookies:
            return Check(
                "espn_cookies",
                False,
                "ESPN_S2/ESPN_SWID not in .env",
                "optional: refresh them from DevTools (runbook)",
            )
        fetch_league(
            int(config.LEAGUE_PRESETS["la_liga"]["league_id"]),
            season,
            views=["mTeam"],
            cookies=cookies,
            timeout=20,
        )
        return Check("espn_cookies", True, ".env cookies accepted")
    except Exception as e:  # noqa: BLE001
        return Check(
            "espn_cookies",
            False,
            f"rejected ({type(e).__name__})",
            "optional: re-copy espn_s2 + SWID from DevTools into .env",
        )


def check_debug_chrome() -> Check:
    for port in (9333, 9222):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=2
            ):
                return Check("debug_chrome", True, f"CDP on {port}")
        except OSError:
            continue
    return Check(
        "debug_chrome",
        False,
        "no CDP Chrome on 9333/9222",
        "optional: start a --remote-debugging-port Chrome (pc-chrome-devtools-port)",
    )


def check_playwright(season: int) -> Check:
    try:
        r = subprocess.run(
            [sys.executable, "scripts/league_login.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=150,
        )
    except subprocess.TimeoutExpired:
        return Check(
            "playwright",
            False,
            "login probe timed out",
            "python scripts/league_login.py (George logs in once)",
        )
    bad = [ln.strip() for ln in r.stdout.splitlines() if "NOT LOGGED IN" in ln]
    if r.returncode == 0 and not bad:
        return Check("playwright", True, "ESPN + Yahoo profile logged in")
    leagues = (
        ", ".join(ln.split(":")[0].replace("NOT LOGGED IN", "").strip() for ln in bad)
        or "unknown"
    )
    return Check(
        "playwright",
        False,
        f"logged out: {leagues}",
        "python scripts/league_login.py (George types the passwords; never in chat)",
    )


def check_ledger(today: dt.date) -> Check:
    lines = LEDGER.read_text(encoding="utf-8").splitlines() if LEDGER.exists() else []
    unclear, awaiting = unresolved_claims(lines, today)
    if unclear:
        return Check(
            "last_claims",
            False,
            "; ".join(unclear),
            "resolve on the site (or check_pending_claims.py) BEFORE new advice and "
            "never re-file blind; then `tab_snippet.py record ... --verdict ...`",
        )
    if awaiting:
        return Check(
            "last_claims",
            True,
            "verify outcomes: " + "; ".join(awaiting),
            "a lost claim changes this week's needs — read the result on the site",
        )
    return Check("last_claims", True, "no recent claims in the ledger")


def build_board(season: int, week: int, run: Callable = subprocess.run) -> bool:
    for cmd in board_build_commands(season, week):
        print("  $", " ".join(Path(c).name if i == 0 else c for i, c in enumerate(cmd)))
        r = run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            print("    FAILED:", (r.stderr or r.stdout)[-400:])
            return False
    return bool(board_files(season, week))


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--build-board",
        action="store_true",
        help="build the week's Gold board locally when it is missing",
    )
    ap.add_argument(
        "--skip-browser",
        action="store_true",
        help="skip the Playwright login probe (~1 min)",
    )
    ap.add_argument("--week", type=int)
    args = ap.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "src"))
    import nfl_data_adapter  # noqa: F401 - sets the CA bundle for child ingests

    season, week = _resolve_week()
    week = args.week or week
    today = dt.date.today()
    print(f"=== waiver preflight — season {season} week {week} ({today}) ===")

    checks = [check_git(), check_board(season, week)]
    if not checks[1].ok and args.build_board:
        print("Building the board locally ...")
        checks[1] = (
            check_board(season, week) if build_board(season, week) else checks[1]
        )
    checks += [
        check_ledger(today),
        check_yahoo(),
        check_espn_cookies(season),
        check_debug_chrome(),
    ]
    if not args.skip_browser:
        checks.append(check_playwright(season))

    for c in checks:
        print(f"  {'OK  ' if c.ok else 'FAIL'} {c.name:13} {c.detail}")
        if c.fix:
            print(f"       {'':13} -> {c.fix}")
    print("\nRoutes this run:")
    for line in routes({c.name: c.ok for c in checks}):
        print("  " + line)
    blocking = [c for c in checks if not c.ok and c.name in ("board",)]
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
