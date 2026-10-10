"""A dedicated Playwright browser profile logged into ESPN, Yahoo and Sleeper.

George logs in once, by hand, in a visible window::

    python scripts/league_login.py

Every later run (``scripts/submit_claims.py``, ``scripts/check_pending_claims.py``)
opens the same profile headless and reuses the saved sessions — no Chrome left
open, no cookies copied into ``.env``. Requests are same-origin ``fetch`` calls
run inside each site's own page, so the sites' cookies, Yahoo's form crumb, the
ESPN member id and the Sleeper token never pass through Python.

The profile holds live sessions: it lives OUTSIDE the repo
(``$FANTASY_BROWSER_PROFILE``, default ``~/.nfl-fantasy-browser``) and must never
be committed or shared. Playwright drives the installed Chrome
(``channel="chrome"``), so no browser download is needed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

#: Where the logged-in profile lives (never inside the repo).
DEFAULT_PROFILE = Path(
    os.environ.get("FANTASY_BROWSER_PROFILE") or Path.home() / ".nfl-fantasy-browser"
)

#: platform -> page URL template (``{lid}`` league id, ``{team}`` our team id).
SITE_URLS = {
    "espn": "https://fantasy.espn.com/football/team?leagueId={lid}&teamId={team}",
    "yahoo": "https://football.fantasysports.yahoo.com/f1/{lid}/{team}",
    "sleeper": "https://sleeper.com/leagues/{lid}",
}


class BrowserPage:
    """One site's page; ``evaluate`` runs a snippet and returns its value.

    Same interface as :class:`src.espn_draft_page.ChromeDraftPage`, so the
    snippets in :mod:`src.waiver_sites` run unchanged.
    """

    def __init__(self, page: Any) -> None:
        self._page = page

    def evaluate(
        self, expression: str, await_promise: bool = False, timeout: float = 15.0
    ) -> Any:
        """Evaluate ``expression`` in the page (promises are awaited).

        Raises:
            RuntimeError: The snippet threw (e.g. logged out, HTTP error).
        """
        try:
            from playwright.sync_api import Error as PlaywrightError
        except ImportError:  # pragma: no cover - playwright is a hard dependency here
            PlaywrightError = Exception  # type: ignore[assignment,misc]
        self._page.set_default_timeout(timeout * 1000)
        try:
            return self._page.evaluate(expression)
        except PlaywrightError as exc:
            raise RuntimeError(f"JS error: {exc}") from exc


class FantasyBrowser:
    """Context manager over the persistent, logged-in browser profile.

    Args:
        profile: Profile directory (default :data:`DEFAULT_PROFILE`).
        headless: False for the one-time login / troubleshooting.
    """

    def __init__(self, profile: Path = DEFAULT_PROFILE, headless: bool = True) -> None:
        self.profile = Path(profile)
        self.headless = headless
        self._pw: Any = None
        self.context: Any = None
        self._pages: Dict[str, BrowserPage] = {}

    def __enter__(self) -> "FantasyBrowser":
        from playwright.sync_api import sync_playwright

        self.profile.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        try:
            self.context = self._pw.chromium.launch_persistent_context(
                str(self.profile),
                channel="chrome",
                headless=self.headless,
                viewport={"width": 1280, "height": 900},
            )
        except Exception:
            self._pw.stop()
            raise
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            if self.context is not None:
                self.context.close()
        finally:
            if self._pw is not None:
                self._pw.stop()

    def page(self, platform: str, league_id: str, team_id: Optional[int] = None) -> BrowserPage:
        """The site's page (opened and loaded once per run).

        Raises:
            LookupError: The page could not be loaded.
        """
        if platform not in self._pages:
            url = SITE_URLS[platform].format(lid=league_id, team=team_id or "")
            page = self.context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            except Exception as exc:  # noqa: BLE001 — network / navigation failure
                raise LookupError(f"could not open {url}: {exc}") from exc
            self._pages[platform] = BrowserPage(page)
        return self._pages[platform]

    def new_tab(self, url: str) -> Any:
        """Open ``url`` in a new tab (used by the login helper)."""
        page = self.context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        return page
