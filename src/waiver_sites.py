"""Site I/O for waiver claims: live league state, claim submission, read-back.

ESPN and Yahoo are driven through a Chrome started with remote debugging and
logged into both sites (the ``refresh_league_pools.py`` setup)::

    chrome --remote-debugging-port=9222 --user-data-dir=<separate profile>

Every request is a same-origin ``fetch`` run inside the site's own tab, so
cookies, Yahoo's form crumb and the ESPN member id never leave the browser —
Python only sees the JSON each snippet returns. A missing tab is opened.

Sleeper is read through its public REST API only (see :mod:`src.waiver_claims`).

Never retry a submit that timed out: no site offers an idempotency key, so a
retried claim can spend FAAB twice. Callers re-read pending claims instead.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from src import sleeper_http
    from src import waiver_claims as wc
    from src.espn_draft_page import ChromeDraftPage
except ImportError:  # pragma: no cover - direct-script import path
    import sleeper_http
    import waiver_claims as wc
    from espn_draft_page import ChromeDraftPage

DEFAULT_CDP_URL = "http://127.0.0.1:9222"

#: platform -> (tab URL fragment, URL to open when no tab matches).
SITES = {
    "espn": (
        "fantasy.espn.com",
        "https://fantasy.espn.com/football/team?leagueId={lid}&teamId={team}",
    ),
    "yahoo": (
        "football.fantasysports.yahoo.com",
        "https://football.fantasysports.yahoo.com/f1/{lid}/{team}",
    ),
}

SLEEPER_TX_URL = "https://api.sleeper.app/v1/league/{lid}/transactions/{leg}"
SLEEPER_STATE_URL = "https://api.sleeper.app/v1/state/nfl"

# Each snippet is an async IIFE over one JSON argument (``__ARGS__``) that
# returns a JSON string. Keep them free of secrets in their return values.

ESPN_STATE_JS = r"""(async (A) => {
 const api = 'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/'
   + A.season;
 const base = `${api}/segments/0/leagues/${A.lid}`;
 const get = async (u, f) => {
   const headers = f ? {'x-fantasy-filter': JSON.stringify(f)} : {};
   const r = await fetch(u, {credentials: 'include', headers});
   if (!r.ok) {
     throw new Error(`ESPN HTTP ${r.status} for ${u.split('?')[0]} (logged in?)`);
   }
   return r.json();
 };
 const L = await get(base + '?view=mSettings&view=mTeam&view=mRoster&view=mStatus');
 const sp = L.scoringPeriodId;
 const acq = (L.settings || {}).acquisitionSettings || {};
 const me = (L.teams || []).find(t => t.id === A.team);
 if (!me) throw new Error(`team ${A.team} is not in ESPN league ${A.lid}`);
 const rosters = [];
 for (const t of L.teams || []) {
   const tname = (t.name || `${t.location || ''} ${t.nickname || ''}`).trim();
   for (const e of (t.roster || {}).entries || []) {
     const p = (e.playerPoolEntry || {}).player || {};
     rosters.push([t.id, tname, p.id, p.fullName]);
   }
 }
 const pool = ((await get(`${base}?scoringPeriodId=${sp}&view=kona_player_info`,
   {players: {filterStatus: {value: ['FREEAGENT', 'WAIVERS']}, limit: 2000,
              sortPercOwned: {sortPriority: 1, sortAsc: false}}})).players || [])
   .map(x => [x.player.id, x.player.fullName, x.status]);
 let tx = [];
 for (const w of [sp, sp + 1]) {
   const j = await get(`${base}?view=mTransactions2&scoringPeriodId=${w}`);
   tx = tx.concat(j.transactions || []);
 }
 // claims, their PROCESS outcomes and CANCEL rows all carry type WAIVER
 tx = tx.filter(t => t.type === 'WAIVER').map(t => ({
   id: t.id, type: t.type, status: t.status, executionType: t.executionType,
   teamId: t.teamId,
   bidAmount: t.bidAmount, relatedTransactionId: t.relatedTransactionId || null,
   proposedDate: t.proposedDate, scoringPeriodId: t.scoringPeriodId,
   items: (t.items || []).map(i => ({type: i.type, playerId: i.playerId}))}));
 const names = {};
 for (const [, , id, n] of rosters) names[id] = n;
 for (const [id, n] of pool) names[id] = n;
 const missing = [...new Set(tx.flatMap(t => t.items.map(i => i.playerId)))]
   .filter(id => id > 0 && !(id in names));
 if (missing.length) {
   const wl = `${api}/players?scoringPeriodId=0&view=players_wl`;
   for (const p of await get(wl, {filterIds: {value: missing}})) {
     names[p.id] = p.fullName;
   }
 }
 return JSON.stringify({scoring_period: sp, budget: acq.acquisitionBudget,
   spent: (me.transactionCounter || {}).acquisitionBudgetSpent || 0,
   min_bid: acq.minimumBid || 0,
   team_name: me.name || '', rosters, pool, transactions: tx, names});
})(__ARGS__)"""

ESPN_SUBMIT_JS = r"""(async (A) => {
 const refuse = why => JSON.stringify({status: 0, errors: [['not submitted', why]]});
 const sw = (document.cookie.match(/(?:^|; )SWID=([^;]*)/) || [])[1];
 if (!sw) return refuse('SWID cookie not readable in this tab');
 const member = decodeURIComponent(sw);
 const reads = 'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/'
   + `${A.season}/segments/0/leagues/${A.lid}?view=mTeam`;
 const L = await (await fetch(reads, {credentials: 'include'})).json();
 const team = (L.teams || []).find(t => t.id === A.body.teamId);
 const owners = ((team || {}).owners || []).map(o => String(o).toUpperCase());
 if (!owners.includes(member.toUpperCase())) {
   return refuse(`the logged-in ESPN account does not own team ${A.body.teamId}`);
 }
 const body = Object.assign({}, A.body, {memberId: member});
 const guid = /\{?[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}?/gi;
 const scrub = m => String(m || '').replace(guid, '{id}');
 const url = 'https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl/seasons/'
   + `${A.season}/segments/0/leagues/${A.lid}/transactions/`;
 const r = await fetch(url, {method: 'POST', credentials: 'include',
   headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
 let j = null; try { j = await r.json(); } catch (e) {}
 const out = {status: r.status};
 if (j && j.id) out.transaction = {id: j.id, type: j.type, status: j.status,
                                   bidAmount: j.bidAmount};
 if (j && (j.messages || j.details)) {
   out.errors = (j.details || []).map(d => [d.type, scrub(d.message || d.shortMessage)])
     .concat((j.messages || []).map(m => ['message', scrub(m)]));
 }
 return JSON.stringify(out);
})(__ARGS__)"""

YAHOO_STATE_JS = r"""(async (A) => {
 const P = new DOMParser();
 const page = async (u, opt) => {
   const r = await fetch(u, Object.assign({credentials: 'include'}, opt || {}));
   if (!r.ok) throw new Error(`Yahoo HTTP ${r.status} for ${u}`);
   return P.parseFromString(await r.text(), 'text/html');
 };
 const txt = n => (n ? n.textContent : '').replace(/\s+/g, ' ').trim();
 const team = await page(`/f1/${A.lid}/${A.team}`);
 const budget = (txt(team.body).match(/Waiver Budget:\s*\$(\d+)/) || [])[1];
 const box = team.getElementById('transactions');
 const content = box && (box.querySelector('.Content') || box);
 const pending = content ? [...content.children].map(el => {
   const a = el.matches('a') ? el : el.querySelector('a');
   const href = a ? a.getAttribute('href') || '' : '';
   return {path: href ? new URL(href, location.origin).pathname : '', text: txt(el)};
 }) : [];
 const search = {};
 for (const q of A.names) {
   const d = await page(`/f1/${A.lid}/playersearch`, {method: 'POST',
     headers: {'Content-Type': 'application/x-www-form-urlencoded'},
     body: 'search=' + encodeURIComponent(q)});
   const heads = [...d.querySelectorAll('table thead tr:last-child > *')].map(txt);
   const col = heads.indexOf('Roster Status');
   search[q] = [...d.querySelectorAll('table tbody tr')].map(r => {
     const a = r.querySelector('a.name, .ysf-player-name a');
     if (!a) return null;
     const tds = [...r.children];
     // DEF rows link to a team page, so the id comes from data-ys-playerid
     const idEl = r.querySelector('[data-ys-playerid]');
     return {name: txt(a), pid: idEl ? idEl.getAttribute('data-ys-playerid') : '',
             roster_status: col >= 0 && tds[col] ? txt(tds[col]) : '',
             ours: !!r.querySelector('a[href*="dropplayer"]')};
   }).filter(Boolean);
 }
 return JSON.stringify({faab_left: budget === undefined ? null : Number(budget),
   pending, search,
   logged_in: !!box || /Waiver Budget/.test(txt(team.body))});
})(__ARGS__)"""

YAHOO_FORM_JS = r"""(async (A) => {
 const P = new DOMParser();
 const txt = n => (n ? n.textContent : '').replace(/\s+/g, ' ').trim();
 const r = await fetch(`/f1/${A.lid}/addplayer?apid=${encodeURIComponent(A.apid)}`,
   {credentials: 'include'});
 const d = P.parseFromString(await r.text(), 'text/html');
 const f = d.getElementById('add-drop-players-form');
 const notes = doc => [...doc.querySelectorAll(
   '.error, .F-error, .notice, .Notice, .F-notice, [role=alert]')]
   .map(txt).filter(Boolean).slice(0, 5);
 if (!f) {
   const error = notes(d).join(' | ') || txt(d.querySelector('h1, h2'));
   return JSON.stringify({found: false, status: r.status, error});
 }
 const drops = [...f.querySelectorAll('input[name=dpid]')].map(i => {
   const row = i.closest('tr');
   return [i.value, txt(row && row.querySelector('a.name, .ysf-player-name a'))];
 });
 const submits = [...f.querySelectorAll('input[type=submit], button[type=submit]')]
   .filter(b => b.name).map(b => [b.name, b.value || txt(b)]);
 const out = {found: true, action: (f.getAttribute('action') || '').split('?')[0],
              drops, faab: !!f.querySelector('input[name=faab]'), submits};
 if (!A.submit) return JSON.stringify(out);
 const sub = submits.find(([n]) => n.includes('drop') === !!A.dpid);
 if (!sub) { out.error = 'no matching submit button'; return JSON.stringify(out); }
 if (out.action !== `/f1/${A.lid}/${A.team}/addplayer`) {
   out.error = `form posts to ${out.action}, not to our team`;
   return JSON.stringify(out);
 }
 if (A.expect_claim && !(out.faab && /claim/i.test(sub[1]))) {
   out.error = 'Yahoo no longer offers a waiver claim for this player';
   return JSON.stringify(out);
 }
 const fd = new URLSearchParams();
 for (const i of f.querySelectorAll('input[type=hidden]')) {
   fd.append(i.name, i.value);
 }
 if (A.dpid) fd.append('dpid', A.dpid);
 if (out.faab) fd.append('faab', String(A.faab));
 fd.append(sub[0], sub[1]);
 const p = await fetch(f.getAttribute('action'), {method: 'POST',
   credentials: 'include',
   headers: {'Content-Type': 'application/x-www-form-urlencoded'},
   body: fd.toString()});
 const pd = P.parseFromString(await p.text(), 'text/html');
 out.posted = {status: p.status, path: new URL(p.url).pathname,
               messages: notes(pd),
               form_again: !!pd.getElementById('add-drop-players-form')};
 return JSON.stringify(out);
})(__ARGS__)"""


def site_page(
    platform: str, league_id: str, team_id: int, cdp_url: str = DEFAULT_CDP_URL
) -> ChromeDraftPage:
    """The logged-in ESPN/Yahoo tab in the debug Chrome, opening one if absent.

    Raises:
        LookupError: No DevTools HTTP endpoint at ``cdp_url`` — including an
            everyday Chrome whose remote debugging was switched on from
            chrome://inspect, which serves only the browser websocket.
    """
    import requests

    fragment, url = SITES[platform]
    page = ChromeDraftPage(cdp_url, url_fragment=fragment)
    try:
        page.find_tab()
        return page
    except LookupError:
        pass
    try:
        resp = requests.get(f"{page.cdp_url}/json/version", timeout=5)
        resp.raise_for_status()
        resp.json()["Browser"]
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise LookupError(
            f"no Chrome DevTools endpoint at {page.cdp_url} ({exc}). Start a separate "
            "Chrome with --remote-debugging-port=<port> --user-data-dir=<profile>, "
            "log into ESPN + Yahoo there, and pass --cdp-url http://127.0.0.1:<port>"
        ) from exc
    try:
        requests.put(
            f"{page.cdp_url}/json/new?{url.format(lid=league_id, team=team_id)}",
            timeout=10,
        ).raise_for_status()
    except requests.RequestException as exc:
        raise LookupError(f"could not open a {fragment} tab: {exc}") from exc
    for _ in range(40):
        time.sleep(0.5)
        try:
            if page.evaluate("document.readyState") == "complete":
                return page
        except (LookupError, RuntimeError):
            continue
    raise LookupError(f"opened a {fragment} tab but it never finished loading")


def run_js(
    page: ChromeDraftPage, js: str, args: Mapping[str, Any], timeout: float = 60
) -> Any:
    """Evaluate a ``__ARGS__`` snippet in ``page`` and parse its JSON result."""
    raw = page.evaluate(
        js.replace("__ARGS__", json.dumps(args)), await_promise=True, timeout=timeout
    )
    return json.loads(raw) if isinstance(raw, str) else raw


def espn_state(
    page: ChromeDraftPage, season: int, league_id: str, team_id: int
) -> Dict[str, Any]:
    """Settings, rosters, free-agent pool, our waiver transactions, names."""
    return run_js(
        page, ESPN_STATE_JS, {"season": season, "lid": int(league_id), "team": team_id}
    )


def espn_submit(
    page: ChromeDraftPage, season: int, league_id: str, body: Mapping[str, Any]
) -> Dict[str, Any]:
    """POST one claim; returns ``{status, transaction?, errors?}``. Never retried."""
    return run_js(
        page,
        ESPN_SUBMIT_JS,
        {"season": season, "lid": int(league_id), "body": dict(body)},
        timeout=30,
    )


def yahoo_state(
    page: ChromeDraftPage, league_id: str, team_id: int, names: Sequence[str]
) -> Dict[str, Any]:
    """FAAB left, the Transactions box, and a player search per name."""
    return run_js(
        page,
        YAHOO_STATE_JS,
        {
            "lid": str(league_id),
            "team": int(team_id),
            "names": list(dict.fromkeys(names)),
        },
        timeout=30 + 5 * len(names),
    )


def yahoo_form(
    page: ChromeDraftPage,
    league_id: str,
    team_id: int,
    apid: str,
    drop_pid: Optional[str],
    bid: int,
    submit: bool = False,
    expect_claim: bool = True,
) -> Dict[str, Any]:
    """Read (and with ``submit=True`` post) the add/drop form for one claim.

    Before posting, the browser re-checks that the form posts to our team and,
    with ``expect_claim``, that it still files a waiver claim (FAAB box +
    "Create claim" button) — waivers clearing between the check and the submit
    must not turn a claim into an immediate add.
    """
    return run_js(
        page,
        YAHOO_FORM_JS,
        {
            "lid": str(league_id),
            "team": int(team_id),
            "apid": str(apid),
            "dpid": drop_pid or "",
            "faab": int(bid),
            "submit": submit,
            "expect_claim": expect_claim,
        },
        timeout=30,
    )


def sleeper_state(league_id: str, my_user: str, legs: Sequence[int]) -> Dict[str, Any]:
    """Sleeper league, rosters, owners and our recent transactions (public API).

    Returns:
        ``{league, rosters, owners: {roster_id: name}, my_roster_id, faab_left,
        transactions: {leg: [...]}, week}``.

    Raises:
        LookupError: League unavailable or ``my_user`` owns no roster in it.
    """
    league = sleeper_http.get_league(league_id)
    if not league:
        raise LookupError(f"Sleeper league {league_id} unavailable")
    users = {
        u.get("user_id"): u.get("display_name")
        for u in sleeper_http.get_league_users(league_id)
    }
    rosters = sleeper_http.get_league_rosters(league_id)
    owners = {
        r.get("roster_id"): users.get(r.get("owner_id"), f"roster {r.get('roster_id')}")
        for r in rosters
    }
    mine = [r for r in rosters if users.get(r.get("owner_id")) == my_user]
    if not mine:
        raise LookupError(
            f"Sleeper user {my_user!r} owns no roster in league {league_id}"
        )
    used = (mine[0].get("settings") or {}).get("waiver_budget_used") or 0
    budget = (league.get("settings") or {}).get("waiver_budget")
    txns = {
        leg: sleeper_http.fetch_sleeper_json(
            SLEEPER_TX_URL.format(lid=league_id, leg=leg)
        )
        or []
        for leg in legs
    }
    return {
        "league": league,
        "rosters": rosters,
        "owners": owners,
        "my_roster_id": mine[0].get("roster_id"),
        "faab_left": None if budget is None else int(budget) - int(used),
        "transactions": {
            leg: t if isinstance(t, list) else [] for leg, t in txns.items()
        },
    }


def sleeper_week() -> int:
    """Sleeper's current NFL week (the waiver ``leg``)."""
    state = sleeper_http.fetch_sleeper_json(SLEEPER_STATE_URL)
    return int((state or {}).get("leg") or (state or {}).get("week") or 1)


def read_claims(
    league: str,
    preset: Mapping[str, Any],
    season: int,
    cdp_url: str = DEFAULT_CDP_URL,
    registry: Optional[Mapping[str, Any]] = None,
) -> Tuple[str, List[wc.ClaimRecord]]:
    """Our claims as the site shows them right now: ``(summary line, records)``.

    ESPN: pending claims plus this period's outcomes. Yahoo: the team page's
    Transactions box. Sleeper: processed claims only (pending ones are private).

    Raises:
        LookupError: The debug Chrome / tab / league is unreachable.
        RuntimeError: A snippet failed in the page (e.g. logged out).
    """
    platform, lid = preset["platform"], str(preset["league_id"])
    if platform == "espn":
        team = int(preset["my_team_id"])
        s = espn_state(site_page("espn", lid, team, cdp_url), season, lid, team)
        records = wc.espn_claim_records(s["transactions"], team, s["names"], league)
        left = int(s["budget"] or 0) - int(s["spent"] or 0)
        return f"ESPN period {s['scoring_period']}, FAAB left ${left}", records
    if platform == "yahoo":
        team = int(preset["my_team_id"])
        s = yahoo_state(site_page("yahoo", lid, team, cdp_url), lid, team, [])
        if not s.get("logged_in"):
            raise RuntimeError("Yahoo team page has no Transactions box - logged in?")
        return f"Yahoo, FAAB left ${s.get('faab_left')}", wc.yahoo_claim_records(
            s["pending"], league
        )
    if platform == "sleeper":
        week = sleeper_week()
        s = sleeper_state(lid, preset["my_user"], legs=sorted({max(1, week - 1), week}))
        if registry is None:
            try:
                from src.sleeper_player_map import load_sleeper_players
            except ImportError:  # pragma: no cover
                from sleeper_player_map import load_sleeper_players
            registry = load_sleeper_players(max_age_days=1)
        records = wc.sleeper_claim_records(
            s["transactions"], s["my_roster_id"], registry, league
        )
        return (
            f"Sleeper week {week}, FAAB left ${s['faab_left']} - pending claims "
            "are private on Sleeper: check the app. Processed claims:",
            records,
        )
    raise LookupError(f"{league}: no claims reader for platform {platform!r}")


__all__: List[str] = [
    "DEFAULT_CDP_URL",
    "espn_state",
    "espn_submit",
    "read_claims",
    "run_js",
    "site_page",
    "sleeper_state",
    "sleeper_week",
    "yahoo_form",
    "yahoo_state",
]
