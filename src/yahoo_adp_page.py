"""Yahoo ADP reader — parses Yahoo's Draft Analysis page as rendered in Chrome.

Yahoo has no public ADP endpoint and the page is JS-rendered (the raw HTML
carries no player rows), so — like the ESPN draft room — we read the rendered
``document.body.innerText`` from a Chrome started with
``--remote-debugging-port`` via :class:`src.espn_draft_page.ChromeDraftPage`.
Open https://football.fantasysports.yahoo.com/f1/draftanalysis?tab=SD&pos=ALL
(Standard Draft, all positions; page through or pick "Show 100") in that
Chrome, then run ``refresh_adp.py --source yahoo --cdp-url http://127.0.0.1:<port>``.

The rendered rows read as::

    Bijan Robinson
    Atl - RB
    2.3        <- Avg Pick
    1.1        <- Avg Round
    99%        <- % Drafted

:func:`parse_yahoo_draft_analysis` is pure and tolerant (optional injury tags
such as ``Q``/``O``/``IR`` between the name and the team line are skipped); a
page whose layout changed simply yields an empty frame, never garbage.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd

from src.adp_sources import ADP_COLUMNS
from src.sleeper_player_map import normalize_name

_TEAM_POS = re.compile(r"^(?P<team>[A-Za-z]{2,3})\s*-\s*(?P<pos>QB|RB|WR|TE|K|DEF|DST)$")
_NUMBER = re.compile(r"^\d+(\.\d+)?$")
_STATUS = {"Q", "O", "D", "IR", "PUP", "SUSP", "NFI", "NA", "P"}

_YAHOO_URL_FRAGMENT = "fantasysports.yahoo.com/f1/draftanalysis"


def parse_yahoo_draft_analysis(text: str) -> pd.DataFrame:
    """Parse rendered Draft Analysis text into the shared ADP schema.

    Returns a DataFrame with :data:`src.adp_sources.ADP_COLUMNS` (``adp`` =
    Avg Pick; ``stdev``/``times_drafted`` are ``None`` — Yahoo does not expose
    them), sorted by ``adp``. Empty when no rows parse.
    """
    lines = [ln.strip() for ln in (text or "").splitlines()]
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows: List[dict] = []
    i = 0
    while i < len(lines) - 2:
        name = lines[i]
        j = i + 1
        while j < len(lines) and lines[j] in _STATUS:
            j += 1
        m = _TEAM_POS.match(lines[j]) if j < len(lines) else None
        if not name or not m or _NUMBER.match(name):
            i += 1
            continue
        # First numeric line after the team/pos line is Avg Pick.
        k = j + 1
        while k < len(lines) and k <= j + 3 and not _NUMBER.match(lines[k]):
            k += 1
        if k < len(lines) and _NUMBER.match(lines[k]):
            pos = m.group("pos").upper()
            rows.append(
                {
                    "player_name": name,
                    "position": "DST" if pos in {"DEF", "DST"} else pos,
                    "team": m.group("team").upper(),
                    "adp": float(lines[k]),
                    "stdev": None,
                    "times_drafted": None,
                    "source": "yahoo",
                    "scoring_format": "half_ppr",  # Yahoo default scoring
                    "fetched_at": fetched_at,
                    "name_key": normalize_name(name),
                }
            )
            i = k + 1
        else:
            i = j + 1
    if not rows:
        return pd.DataFrame(columns=ADP_COLUMNS)
    df = pd.DataFrame(rows).drop_duplicates("name_key").sort_values("adp").reset_index(drop=True)
    return df.reindex(columns=ADP_COLUMNS)


def fetch_yahoo_adp_from_chrome(cdp_url: str = "http://127.0.0.1:9222") -> pd.DataFrame:
    """Read the open Yahoo Draft Analysis tab over Chrome DevTools and parse it.

    Fails open to an empty frame (with a logged reason) when no such tab is open.
    """
    import logging

    from src.espn_draft_page import ChromeDraftPage

    page = ChromeDraftPage(cdp_url, url_fragment=_YAHOO_URL_FRAGMENT)
    try:
        text = page.inner_text()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("Yahoo ADP: %s", exc)
        return pd.DataFrame(columns=ADP_COLUMNS)
    df = parse_yahoo_draft_analysis(text)
    if df.empty:
        logging.getLogger(__name__).warning(
            "Yahoo ADP: no rows parsed — is the Draft Analysis table visible in the tab?"
        )
    return df


__all__ = ["parse_yahoo_draft_analysis", "fetch_yahoo_adp_from_chrome"]
