"""One-time Yahoo OAuth2 grant + a read check for the Fantasy Sports API.

Yahoo enabled read-only Fantasy Sports access for this app on 2026-10-28
(``fspt-r``: leagues, teams, rosters, players, standings, matchups, stats).
Write access — lineups, add/drop, waivers — is not offered, so this script
only ever requests the read scope.

Usage::

    python scripts/yahoo_auth.py            # run the grant, then verify
    python scripts/yahoo_auth.py --check    # verify an existing grant only

The grant is interactive and needed once: Yahoo shows an authorization code
on screen (the ``oob`` redirect), you paste it back here, and the resulting
token pair lands in ``data/yahoo_tokens.json`` (gitignored) and refreshes
itself from then on.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import LEAGUE_PRESETS  # noqa: E402
from src.yahoo_draft import fetch_yahoo_json  # noqa: E402
from src.yahoo_oauth import (  # noqa: E402
    DEFAULT_SCOPE,
    YahooAuthError,
    YahooOAuth,
)


#: Values that look like credentials to ``has_credentials()`` but are not.
#: A placeholder left in .env authenticates far enough to build an auth URL,
#: then fails at the token exchange with an opaque error -- so refuse early.
_PLACEHOLDERS = {
    "PASTE_SECRET_HERE",
    "PASTE_YOUR_SECRET_HERE",
    "CHANGEME",
    "TODO",
    "xxx",
}


def _credential_problem(oauth: YahooOAuth) -> str:
    """Return a human-readable reason the credentials are unusable, else ""."""
    if not oauth.client_id:
        return "YAHOO_CLIENT_ID is missing from .env"
    if not oauth.client_secret:
        return "YAHOO_CLIENT_SECRET is missing from .env"
    if oauth.client_secret in _PLACEHOLDERS:
        return (
            f"YAHOO_CLIENT_SECRET is still the placeholder "
            f"({oauth.client_secret!r}) -- paste the real Consumer Secret "
            f"from https://developer.yahoo.com/apps/ first"
        )
    return ""


ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)


def capture_secret(env_path: str = ENV_PATH) -> bool:
    """Prompt for the Consumer Secret and write it into ``.env``.

    Prompting here rather than in the shell keeps the value out of shell
    history and sidesteps ``read``'s bash/zsh flag differences. The value is
    never echoed and never printed back.

    Returns:
        True when the secret was captured and stored.
    """
    secret = getpass.getpass("Yahoo Consumer Secret (not echoed): ").strip()
    if not secret:
        print("Nothing entered — .env unchanged.")
        return False
    if secret in _PLACEHOLDERS:
        print("That is the placeholder text, not the secret — .env unchanged.")
        return False

    line = f"YAHOO_CLIENT_SECRET={secret}"
    try:
        with open(env_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except FileNotFoundError:
        lines = []

    replaced = False
    for i, existing in enumerate(lines):
        if existing.startswith("YAHOO_CLIENT_SECRET="):
            lines[i] = line
            replaced = True
            break
    if not replaced:
        lines.append(line)

    with open(env_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    os.environ["YAHOO_CLIENT_SECRET"] = secret
    print(f"Secret stored in {env_path} ({'replaced' if replaced else 'appended'}).")
    return True


def _leagues(oauth: YahooOAuth) -> list:
    """Return the NFL leagues the signed-in user can read, as (key, name)."""
    node = fetch_yahoo_json("/users;use_login=1/games;game_keys=nfl/leagues", oauth)
    found = []

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            if "league_key" in obj and "name" in obj:
                found.append((str(obj["league_key"]), str(obj["name"])))
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(node)
    return found


def check(oauth: YahooOAuth) -> int:
    """Print what the token can actually read. Returns a process exit code."""
    problem = _credential_problem(oauth)
    if problem:
        print(f"NOT WIRED: {problem}")
        return 1
    if not oauth.get_access_token():
        print("NO GRANT: no usable token — run this script with no arguments")
        return 1

    leagues = _leagues(oauth)
    if not leagues:
        print(
            "TOKEN OK BUT NO FANTASY DATA: the call returned nothing. Either the "
            "grant predates the scope, or access is not live for this app yet."
        )
        return 1

    print(f"READ OK — {len(leagues)} NFL league(s) visible:")
    for key, name in leagues:
        print(f"  {key}  {name}")

    preset = LEAGUE_PRESETS.get("feetball", {})
    team_key = f"nfl.l.{preset.get('league_id')}.t.{preset.get('my_team_id')}"
    roster = fetch_yahoo_json(f"/team/{team_key}/roster", oauth)
    names = []

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            full = obj.get("name")
            if isinstance(full, dict) and full.get("full"):
                names.append(str(full["full"]))
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(roster)
    if names:
        print(f"\nfeetball roster ({team_key}) — {len(names)} players:")
        for name in names:
            print(f"  {name}")
    else:
        print(f"\nfeetball roster ({team_key}): EMPTY — check my_team_id in config")
        return 1
    return 0


def grant(oauth: YahooOAuth, code: str = "") -> int:
    """Run the authorization-code grant.

    Args:
        oauth: The token manager to store the resulting tokens on.
        code: An authorization code obtained out of band. When empty the
            function prints the authorization URL and prompts for one.
    """
    problem = _credential_problem(oauth)
    if problem:
        if not oauth.client_id:
            print(f"NOT WIRED: {problem}")
            return 1
        print(f"{problem}\n")
        if not capture_secret():
            return 1
        oauth.client_secret = os.environ["YAHOO_CLIENT_SECRET"]

    url = oauth.build_authorization_url(scope=DEFAULT_SCOPE)
    if code:
        print("Exchanging the supplied authorization code...")
        if not oauth.exchange_code(code):
            print("Exchange failed — the code is single-use and expires fast.")
            print("It can also mean the Consumer Secret is wrong.")
            return 1
        print(f"\nTokens stored in {oauth.token_path}.\n")
        return check(oauth)

    print("1. Open this URL, sign in as the Yahoo account that owns feetball,")
    print("   and approve the Fantasy Sports read permission:\n")
    print(f"   {url}\n")
    if not code:
        print("2. Yahoo shows an authorization code on screen. Paste it here.")
        code = input("   Code: ").strip()
    if not code:
        print("No code entered — nothing done.")
        return 1
    if not oauth.exchange_code(code):
        print("Exchange failed. The code is single-use and expires fast; retry.")
        return 1
    print(f"\nTokens stored in {oauth.token_path}.\n")
    return check(oauth)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify an existing grant instead of creating one",
    )
    parser.add_argument(
        "--set-secret",
        action="store_true",
        help="only capture the Consumer Secret into .env, then exit",
    )
    parser.add_argument(
        "--code",
        default="",
        help="authorization code obtained out of band (skips the prompt)",
    )
    parser.add_argument(
        "--redirect-uri",
        default="oob",
        help="must match the app's registered redirect URI (default: oob)",
    )
    args = parser.parse_args()

    load_dotenv()
    if args.set_secret:
        return 0 if capture_secret() else 1

    oauth = YahooOAuth(redirect_uri=args.redirect_uri)
    try:
        return check(oauth) if args.check else grant(oauth, args.code)
    except YahooAuthError as exc:
        print(f"{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
