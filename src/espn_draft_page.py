"""ESPN draft-room page reader (v8.3, ESPN live co-pilot).

ESPN's REST surface (``mDraftDetail``) shows **no** live picks until a draft
completes (re-verified 2026-08-23 mid-draft: 121 picks on screen, 0 via REST).
The draft app's rendered page, however, exposes everything the co-pilot needs
as plain text: ``ON THE CLOCK: PICK n``, ``RND r OF R``, the upcoming-pick
strip (``PICK n`` + owner), and every pick made (``Name / TEAM POS`` followed by
``Rr, Pp - owner``).

This module has two halves:

* :func:`parse_draft_page` / :func:`state_from_page` — **pure** parsing of that
  text into the platform-neutral :class:`~src.draft_models.DraftState`. Fully
  offline-testable.
* :class:`ChromeDraftPage` — a ~40-line Chrome DevTools Protocol client that
  reads ``document.body.innerText`` from the user's own logged-in Chrome tab
  (``websocket-client`` + ``requests``, no Playwright). Chrome must be started
  with ``--remote-debugging-port=9222 --user-data-dir=<separate profile>``
  (Chrome >= 136 refuses remote debugging on the default profile).

Text parsing IS brittle to ESPN UI changes — the trade-off accepted after the
2026-08-23 mock where a human-in-the-loop scrape lost four picks to autopick.
Every regex is anchored to a labelled line, and a parse that finds no picks
degrades to an empty (not wrong) state.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from src.draft_models import DraftState, PickEvent

_PICK_LINE = re.compile(
    r"^(?P<name>.+?) / (?P<team>[A-Za-z]{2,4}) (?P<pos>QB|RB|WR|TE|K|D/ST|DST|DEF)$"
)
_SLOT_LINE = re.compile(r"^R(?P<round>\d+), P(?P<pick>\d+) - (?P<owner>.+)$")
_CLOCK = re.compile(r"ON THE CLOCK: PICK (?P<pick>\d+)")
_ROUNDS = re.compile(r"RND (?P<round>\d+) OF (?P<total>\d+)")
_UPCOMING = re.compile(r"^PICK (?P<pick>\d+)$")

_DEFAULT_CDP_URL = "http://127.0.0.1:9222"
_DRAFT_URL_FRAGMENT = "fantasy.espn.com/football/draft"


@dataclass(frozen=True)
class PagePick:
    """One drafted player as shown in the draft room's Picks panel."""

    name: str
    team: str
    position: str
    round: int
    pick_in_round: int
    owner: str


@dataclass
class ParsedDraftPage:
    """Everything :func:`parse_draft_page` could read off the page."""

    on_clock_pick: Optional[int] = None
    round_no: Optional[int] = None
    total_rounds: Optional[int] = None
    picks: List[PagePick] = field(default_factory=list)
    #: overall pick number -> owner name, from the upcoming-picks strip.
    upcoming_owners: Dict[int, str] = field(default_factory=dict)
    queue_empty: bool = True


def _normalize_position(pos: str) -> str:
    p = pos.upper()
    return "DST" if p in {"D/ST", "DEF", "DST"} else p


def parse_draft_page(text: str) -> ParsedDraftPage:
    """Parse the draft app's ``document.body.innerText`` (pure; no network).

    Args:
        text: The page's rendered text.

    Returns:
        A :class:`ParsedDraftPage`; fields the page did not expose stay ``None``
        / empty rather than guessed.
    """
    page = ParsedDraftPage()
    if not text:
        return page
    m = _CLOCK.search(text)
    if m:
        page.on_clock_pick = int(m.group("pick"))
    m = _ROUNDS.search(text)
    if m:
        page.round_no = int(m.group("round"))
        page.total_rounds = int(m.group("total"))
    page.queue_empty = "No players in queue" in text

    lines = [ln.strip() for ln in text.splitlines()]
    # Upcoming strip: "PICK n" then optional "AUTO" then the owner name.
    for i, ln in enumerate(lines):
        um = _UPCOMING.match(ln)
        if not um:
            continue
        j = i + 1
        if j < len(lines) and lines[j] == "AUTO":
            j += 1
        if j < len(lines) and lines[j] and not _UPCOMING.match(lines[j]):
            page.upcoming_owners[int(um.group("pick"))] = lines[j]

    # Picks panel: "Name / TEAM POS" immediately followed by "Rr, Pp - owner".
    for i in range(len(lines) - 1):
        pm = _PICK_LINE.match(lines[i])
        if not pm:
            continue
        sm = _SLOT_LINE.match(lines[i + 1])
        if not sm:
            continue
        page.picks.append(
            PagePick(
                name=pm.group("name").strip(),
                team=pm.group("team").upper(),
                position=_normalize_position(pm.group("pos")),
                round=int(sm.group("round")),
                pick_in_round=int(sm.group("pick")),
                owner=sm.group("owner").strip(),
            )
        )
    page.picks.sort(key=lambda p: (p.round, p.pick_in_round))
    return page


def slot_for_pick(pick_no: int, n_teams: int, draft_type: str = "snake") -> int:
    """Draft slot (1-based) that owns overall ``pick_no``."""
    if n_teams <= 0 or pick_no <= 0:
        return 0
    idx = (pick_no - 1) % n_teams
    rnd = (pick_no - 1) // n_teams + 1
    if draft_type == "snake" and rnd % 2 == 0:
        return n_teams - idx
    return idx + 1


def state_from_page(
    page: ParsedDraftPage,
    n_teams: int,
    season: str,
    scoring_format: str,
    roster_format: str,
    draft_id: str = "espn",
    draft_type: str = "snake",
) -> DraftState:
    """Build a platform-neutral :class:`DraftState` from a parsed page.

    ``draft_order`` maps **owner display name -> slot** (from both made picks
    and the upcoming strip), so ``LiveDraftEngine(my_user_id=<team name>)``
    derives the user's slot exactly as it does for Sleeper user ids.
    """
    picks: List[PickEvent] = []
    order: Dict[str, int] = {}
    for p in page.picks:
        pick_no = (p.round - 1) * n_teams + p.pick_in_round
        slot = slot_for_pick(pick_no, n_teams, draft_type)
        order.setdefault(p.owner, slot)
        first, _, last = p.name.partition(" ")
        picks.append(
            PickEvent(
                pick_no=pick_no,
                round=p.round,
                draft_slot=slot,
                roster_id=slot,
                picked_by=p.owner,
                sleeper_player_id="",
                first_name=first,
                last_name=last,
                position=p.position,
                team=p.team,
                is_keeper=False,
            )
        )
    for pick_no, owner in page.upcoming_owners.items():
        order.setdefault(owner, slot_for_pick(pick_no, n_teams, draft_type))

    total = (page.total_rounds or 0) * n_teams
    if total and len(picks) >= total:
        status = "complete"
    elif page.on_clock_pick or picks:
        status = "drafting"
    else:
        status = "pre_draft"
    return DraftState(
        draft_id=draft_id,
        status=status,
        draft_type=draft_type,
        season=str(season),
        n_teams=n_teams,
        rounds=page.total_rounds or 0,
        scoring_format=scoring_format,
        roster_format=roster_format,
        draft_order=order,
        slot_to_roster_id={str(s): s for s in order.values()},
        picks=tuple(picks),
    )


# ---------------------------------------------------------------------------
# Chrome DevTools Protocol page source
# ---------------------------------------------------------------------------

# Fills ESPN's Pick Queue: type each name into the players search box, click the
# row's QUEUE button, then clear the search. Returns a per-name status list.

_QUEUE_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def queue_match_spec(name: str) -> Dict[str, Any]:
    """Search string + row-match tokens for one ESPN Pick Queue entry.

    ESPN's players list is a FixedDataTable of divs, so a queued row is found
    by text. The original predicate used the name's last whitespace token,
    which for the 33 suffixed players in the 2026 pool ("Brian Thomas Jr.",
    "Kenneth Walker III") is the SUFFIX — it matched whichever suffixed player
    the filter happened to show and queued the wrong one silently, or reported
    notfound. Requiring every non-suffix token instead makes the match specific
    to the player, and the suffix is dropped from the query because ESPN's
    filter is literal and "Jr." can zero the result set.

    Args:
        name: Player name as our board spells it.

    Returns:
        ``{"search": str, "tokens": list[str]}`` — type ``search`` into the
        filter, then accept a row whose normalized text contains all ``tokens``.
    """
    cleaned = re.sub(r"[^a-z0-9\s]", "", str(name or "").lower())
    tokens = [t for t in cleaned.split() if t not in _QUEUE_NAME_SUFFIXES]
    raw = [w for w in str(name or "").split() if re.sub(r"[^a-z0-9]", "", w.lower())
           not in _QUEUE_NAME_SUFFIXES]
    return {"search": " ".join(raw), "tokens": tokens}


_ENQUEUE_JS = """
(async () => {
  const specs = %s;
  const out = [];
  const inp = document.querySelector('input[placeholder*="Player"]');
  if (!inp) return ['error:no search input'];
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const type = (v) => { setter.call(inp, v); inp.dispatchEvent(new Event('input', {bubbles: true})); };
  // Same normalization as queue_match_spec() on the Python side.
  // Must match queue_match_spec(): strip punctuation to NOTHING (not to a
  // space), else "A.J."->"a j" never contains the token "aj" and every
  // apostrophe/period/hyphen name (Ja'Marr, De'Von, Amon-Ra) reports notfound.
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, ' ');
  for (const spec of specs) {
    type(spec.search); await sleep(%d);
    // The players list is a FixedDataTable (divs, not <table>); rows wrap cells.
    // Require EVERY token, so a suffix can never match a different player.
    const findRow = () => [...document.querySelectorAll('.fixedDataTableRowWrapper, .fixedDataTableRowLayout_rowWrapper')]
      .find((r) => { const t = norm(r.innerText); return spec.tokens.every((tok) => t.includes(tok)); });
    let row = findRow();
    if (!row) { await sleep(900); row = findRow(); }  // filter still settling
    if (!row) { out.push('notfound:' + spec.search); continue; }
    const btn = [...row.querySelectorAll('button')].find((b) => /queue/i.test(b.innerText));
    if (btn) { btn.click(); await sleep(300); out.push('queued:' + spec.search); }
    // Row present but no queue button = ESPN already has him queued/drafted.
    else out.push('already:' + spec.search);
  }
  type(''); await sleep(300);
  return out;
})()
"""


# Empties ESPN's Pick Queue: click every REMOVE button in the queue panel until
# none remain (ESPN re-renders the list after each click).
_CLEAR_QUEUE_JS = """
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let removed = 0;
  for (let i = 0; i < 40; i++) {
    const btn = [...document.querySelectorAll('button')].find((b) => /^remove$/i.test(b.innerText.trim()));
    if (!btn) break;
    btn.click(); removed++; await sleep(%d);
  }
  return removed;
})()
"""


class ChromeDraftPage:
    """Read the ESPN draft tab from a Chrome started with remote debugging.

    Args:
        cdp_url: DevTools HTTP endpoint (``--remote-debugging-port``).
        url_fragment: Substring identifying the draft-room tab.
    """

    def __init__(
        self, cdp_url: str = _DEFAULT_CDP_URL, url_fragment: str = _DRAFT_URL_FRAGMENT
    ) -> None:
        self.cdp_url = cdp_url.rstrip("/")
        self.url_fragment = url_fragment

    def find_tab(self) -> Dict[str, Any]:
        """Return the DevTools target dict for the draft tab (raises if absent)."""
        import requests

        try:
            targets = requests.get(f"{self.cdp_url}/json", timeout=5).json()
        except Exception as exc:  # noqa: BLE001 — connection refused / non-JSON
            raise LookupError(
                f"Chrome DevTools not reachable at {self.cdp_url} ({exc}). Start "
                "Chrome with --remote-debugging-port=9222 --user-data-dir=<separate "
                "profile>, log into ESPN, open the draft room."
            ) from exc
        for t in targets:
            if t.get("type") == "page" and self.url_fragment in str(t.get("url", "")):
                return t
        raise LookupError(
            f"No Chrome tab matching '{self.url_fragment}' at {self.cdp_url}. "
            "Start Chrome with --remote-debugging-port=9222 "
            "--user-data-dir=<separate profile>, log into ESPN, open the draft room."
        )

    def evaluate(
        self, expression: str, await_promise: bool = False, timeout: float = 15.0
    ) -> Any:
        """Run ``expression`` in the draft tab and return its JSON value.

        ``timeout`` must exceed the JS runtime: an awaited promise that outlives
        the websocket timeout keeps running in the browser after Python gives
        up, leaving page state matching neither the error nor the caller's
        bookkeeping (review finding, 2026-08-24).
        """
        import websocket

        ws_url = self.find_tab()["webSocketDebuggerUrl"]
        # Chrome 403s DevTools websockets that carry an Origin header unless
        # launched with --remote-allow-origins; omitting the header is accepted.
        ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        try:
            ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": expression,
                            "returnByValue": True,
                            "awaitPromise": await_promise,
                        },
                    }
                )
            )
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == 1:
                    break
        finally:
            ws.close()
        if "error" in msg:
            raise RuntimeError(f"CDP error: {msg['error']}")
        result = msg.get("result", {})
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS error: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def inner_text(self) -> str:
        return str(self.evaluate("document.body.innerText") or "")

    def enqueue(self, names: Sequence[str], settle_ms: int = 900) -> List[str]:
        """Add ``names`` (in order) to ESPN's Pick Queue via the search box."""
        specs = [queue_match_spec(n) for n in names]
        js = _ENQUEUE_JS % (json.dumps(specs), int(settle_ms))
        # ~2.1 s worst case per name (settle + retry + click) + headroom.
        return list(
            self.evaluate(js, await_promise=True, timeout=15 + 2.5 * len(names)) or []
        )

    def clear_queue(self, settle_ms: int = 250) -> int:
        """Remove every player from ESPN's Pick Queue; returns the count removed."""
        return int(
            self.evaluate(_CLEAR_QUEUE_JS % int(settle_ms), await_promise=True, timeout=30)
            or 0
        )

    def set_queue(self, names: Sequence[str]) -> List[str]:
        """Replace ESPN's Pick Queue with ``names`` in this exact order.

        ESPN's queue is insertion-ordered and autopicks from the top, so order
        IS the safety net — an append-only queue left Josh Allen above the
        RBs at pick 11 in the 2026-08-23 second mock.
        """
        removed = self.clear_queue()
        return [f"cleared:{removed}"] + self.enqueue(names)


__all__ = [
    "PagePick",
    "ParsedDraftPage",
    "parse_draft_page",
    "slot_for_pick",
    "state_from_page",
    "ChromeDraftPage",
    "queue_match_spec",
]
