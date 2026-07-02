"""Yahoo-specific draft parsing + resolution (v8.0 Live Draft Co-Pilot, Phase 88).

Turns raw Yahoo Fantasy Sports API JSON into the platform-neutral models in
:mod:`src.draft_models` that the live engine consumes — the Yahoo analogue of
:mod:`src.sleeper_draft`:

* :func:`pick_from_yahoo`   — one Yahoo draft-result entry -> :class:`PickEvent`.
* :func:`state_from_yahoo`  — league settings + draft results + players ->
  :class:`DraftState`, mapping Yahoo settings onto :data:`SCORING_CONFIGS` /
  :data:`ROSTER_CONFIGS`.
* :func:`load_draft_state`  — the one network-touching assembler.
* :func:`resolve_active_draft` — find the user's active/most-recent league draft.

Yahoo API shape
---------------
Yahoo wraps every response in a deeply nested ``fantasy_content`` object whose
collections are JSON *objects* keyed by stringified integers plus a ``count``
field (not plain arrays). :func:`_iter_collection` flattens that shape. Player
identity (name/position/team) is NOT in ``draft_results`` — each entry carries a
``player_key`` (e.g. ``"nfl.p.31883"``) that must be resolved via the
``players`` resource. We fetch both and join in :func:`state_from_yahoo`.

* League key:  ``nfl.l.<league_id>``
* Team key:    ``nfl.l.<league_id>.t.<team_id>``
* Player key:  ``nfl.p.<player_id>``

Conservative polling
--------------------
Yahoo applies undocumented throttling and returns **HTTP 999** when a client
polls too aggressively. Callers (the live engine) MUST poll conservatively —
no faster than ~once every 5-10 seconds — and back off on any error. All fetch
helpers honour the project-wide D-06 fail-open contract: a throttle/blip yields
empty data and a stale-but-usable :class:`DraftState`, never an exception.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.config import ROSTER_CONFIGS, SCORING_CONFIGS
from src.draft_models import DraftState, PickEvent
from src.yahoo_oauth import YahooOAuth

logger = logging.getLogger(__name__)

API_BASE_URL: str = "https://fantasysports.yahooapis.com/fantasy/v2"
_DEFAULT_TIMEOUT_S: int = 15
_USER_AGENT: str = "NFLDataEngineering/1.0 (yahoo-draft-helper)"

# Yahoo position labels that are not skill positions we project for.
_DEF_POSITIONS = {"DEF", "DST", "D/ST"}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce ``value`` to int, returning ``default`` on any failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def fetch_yahoo_json(
    path: str,
    oauth: YahooOAuth,
    timeout: int = _DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """GET a Yahoo Fantasy API ``path`` as JSON, fail-open.

    Appends ``?format=json`` (or ``&format=json``), attaches the bearer token
    from ``oauth``, and returns the parsed ``dict``. Any auth/network/parse
    error — including Yahoo's throttling HTTP 999 — is logged at WARNING and
    yields ``{}`` (D-06), so a single throttle never crashes a live draft.

    Args:
        path: API path relative to :data:`API_BASE_URL`, e.g.
            ``"/league/nfl.l.123/draftresults"``.
        oauth: A :class:`~src.yahoo_oauth.YahooOAuth` providing the access token.
        timeout: Socket timeout in seconds.

    Returns:
        The parsed JSON dict, or ``{}`` on any error.
    """
    if not path:
        logger.warning("fetch_yahoo_json: empty path provided")
        return {}

    token = oauth.get_access_token()
    if not token:
        logger.warning(
            "fetch_yahoo_json: no Yahoo access token — fail-open returning {}"
        )
        return {}

    sep = "&" if "?" in path else "?"
    url = f"{API_BASE_URL}{path}{sep}format=json"
    req = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except HTTPError as exc:
        # 999 = Yahoo throttling; 401 = token died mid-session.
        logger.warning("Yahoo HTTP %d for %s — fail-open returning {}", exc.code, url)
        return {}
    except URLError as exc:
        logger.warning(
            "Yahoo network error for %s: %s — fail-open returning {}", url, exc.reason
        )
        return {}
    except (TimeoutError, OSError) as exc:
        logger.warning(
            "Yahoo transport error for %s: %s — fail-open returning {}", url, exc
        )
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Yahoo invalid JSON from %s: %s — fail-open returning {}", url, exc
        )
        return {}
    return data if isinstance(data, dict) else {}


def _iter_collection(node: Any) -> Iterable[Any]:
    """Yield member values from a Yahoo numeric-keyed collection object.

    Yahoo represents a list of N items as
    ``{"0": {...}, "1": {...}, ..., "count": N}`` rather than a JSON array.
    This yields each member (the values under the stringified-int keys), skipping
    the ``count`` bookkeeping key. Plain lists are passed through unchanged.
    """
    if isinstance(node, list):
        for item in node:
            yield item
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key == "count":
            continue
        if key.isdigit():
            yield value


def _merge_fragments(node: Any) -> Dict[str, Any]:
    """Flatten Yahoo's fragmented ``[{...}, {...}]`` records into one dict.

    Yahoo frequently splits a single logical record across a list of small
    dicts (and sometimes lists-of-dicts). This walks that structure and merges
    every dict it finds into a single flat dict (later keys win). Non-dict scraps
    are ignored. Robust to the assorted nesting Yahoo emits across resources.
    """
    merged: Dict[str, Any] = {}

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    # Keep nested collections addressable while still merging
                    # the scalar leaves they sit beside.
                    merged.setdefault(k, v)
                    _walk(v)
                else:
                    merged[k] = v
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(node)
    return merged


# ---------------------------------------------------------------------------
# Settings mapping (Yahoo -> project config keys)
# ---------------------------------------------------------------------------


def _scoring_format_from_settings(settings: Dict[str, Any]) -> str:
    """Map Yahoo league settings onto a SCORING_CONFIGS key.

    Inspects the league ``stat_modifiers`` for a reception (Rec) point value:
    >= 1.0 -> ``ppr``, <= 0.0 -> ``standard``, else ``half_ppr``. Falls back to
    the project default ``half_ppr`` when reception scoring can't be determined.
    """
    settings = settings if isinstance(settings, dict) else {}
    rec_value = _reception_points(settings)
    if rec_value is None:
        # Some payloads expose a simple scoring_type label.
        label = str(settings.get("scoring_type") or "").lower()
        if "head" in label or "point" in label:
            return "half_ppr"
        return "half_ppr"
    if rec_value >= 1.0:
        return "ppr"
    if rec_value <= 0.0:
        return "standard"
    return "half_ppr"


def _reception_points(settings: Dict[str, Any]) -> Optional[float]:
    """Extract per-reception points from Yahoo ``stat_modifiers`` if present.

    Yahoo identifies receptions with ``stat_id`` 11. Returns the modifier value,
    or ``None`` when it cannot be located.
    """
    modifiers = settings.get("stat_modifiers") or {}
    stats = modifiers.get("stats") if isinstance(modifiers, dict) else None
    for entry in _iter_collection(stats):
        stat = entry.get("stat") if isinstance(entry, dict) else None
        if not isinstance(stat, dict):
            continue
        if _safe_int(stat.get("stat_id"), -1) == 11:
            try:
                return float(stat.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def _roster_format_from_settings(settings: Dict[str, Any]) -> str:
    """Map Yahoo roster positions onto a ROSTER_CONFIGS key.

    ``superflex`` when a Q/W/R/T super-flex slot exists; ``2qb`` when two QB
    slots; otherwise ``standard``.
    """
    settings = settings if isinstance(settings, dict) else {}
    positions = settings.get("roster_positions") or {}
    qb_slots = 0
    has_superflex = False
    for entry in _iter_collection(positions):
        rp = entry.get("roster_position") if isinstance(entry, dict) else None
        if not isinstance(rp, dict):
            continue
        pos = str(rp.get("position") or "").upper()
        count = _safe_int(rp.get("count"), 0)
        if pos == "QB":
            qb_slots += count
        if pos in {"Q/W/R/T", "SUPERFLEX", "SUPER_FLEX"}:
            has_superflex = True
    if has_superflex:
        return "superflex"
    if qb_slots >= 2:
        return "2qb"
    return "standard"


# ---------------------------------------------------------------------------
# Yahoo -> neutral model construction
# ---------------------------------------------------------------------------


def _team_id_from_key(team_key: str) -> Optional[int]:
    """Extract the trailing team ordinal from a Yahoo team_key.

    ``"nfl.l.12345.t.7"`` -> ``7``. Returns ``None`` when no ``.t.<n>`` segment
    is present.
    """
    if not team_key:
        return None
    parts = str(team_key).split(".t.")
    if len(parts) != 2:
        return None
    return _safe_int(parts[1], 0) or None


def pick_from_yahoo(
    raw: Dict[str, Any],
    players_index: Optional[Dict[str, Dict[str, str]]] = None,
) -> PickEvent:
    """Build a :class:`PickEvent` from a raw Yahoo draft-result entry.

    The raw entry supplies ``pick``, ``round``, ``team_key``, ``player_key``
    (and ``cost`` for auctions). Player identity (name/position/team) is joined
    from ``players_index`` keyed by ``player_key``; when absent the identity
    fields default to empty so downstream mapping still fails open.

    The neutral model's ``sleeper_player_id`` field carries the Yahoo
    ``player_key`` (the field is named for the reference adapter; it holds the
    source platform's id).

    Args:
        raw: One draft-result dict (already merged from Yahoo fragments).
        players_index: ``player_key -> {full_name, position, team, ...}``.

    Returns:
        A :class:`PickEvent`; never raises.
    """
    raw = raw if isinstance(raw, dict) else {}
    index = players_index or {}
    player_key = str(raw.get("player_key") or "")
    team_key = str(raw.get("team_key") or "")

    identity = index.get(player_key, {})
    full_name = str(identity.get("full_name") or "").strip()
    first, _, last = full_name.partition(" ")

    return PickEvent(
        pick_no=_safe_int(raw.get("pick")),
        round=_safe_int(raw.get("round")),
        draft_slot=_team_id_from_key(team_key) or 0,
        roster_id=_team_id_from_key(team_key),
        picked_by=team_key,
        sleeper_player_id=player_key,
        first_name=first,
        last_name=last,
        position=str(identity.get("position") or "").upper(),
        team=str(identity.get("team") or "").upper(),
        is_keeper=False,
    )


def build_players_index(players_node: Any) -> Dict[str, Dict[str, str]]:
    """Build ``player_key -> identity`` from a Yahoo ``players`` collection.

    Each identity is ``{full_name, position, team}``. DST entries are kept (with
    position normalized to ``DST``) so they appear as unmatched picks rather than
    silently vanishing.

    Args:
        players_node: The collection node under ``...["players"]``.

    Returns:
        Mapping of Yahoo ``player_key`` to identity dict (possibly empty).
    """
    index: Dict[str, Dict[str, str]] = {}
    for member in _iter_collection(players_node):
        record = member.get("player") if isinstance(member, dict) else member
        flat = _merge_fragments(record)
        player_key = str(flat.get("player_key") or "")
        if not player_key:
            continue
        name_obj = flat.get("name")
        full_name = ""
        if isinstance(name_obj, dict):
            full_name = str(name_obj.get("full") or "").strip()
        position = str(
            flat.get("display_position") or flat.get("primary_position") or ""
        ).upper()
        if position in _DEF_POSITIONS:
            position = "DST"
        index[player_key] = {
            "full_name": full_name,
            "position": position,
            "team": str(flat.get("editorial_team_abbr") or "").upper(),
        }
    return index


def parse_draft_results(draft_node: Any) -> List[Dict[str, Any]]:
    """Flatten a Yahoo ``draft_results`` collection into a list of merged dicts.

    Args:
        draft_node: The collection node under ``...["draft_results"]``.

    Returns:
        A list of merged draft-result dicts (each with ``pick``, ``round``,
        ``team_key``, ``player_key``); empty on any unexpected shape.
    """
    results: List[Dict[str, Any]] = []
    for member in _iter_collection(draft_node):
        record = member.get("draft_result") if isinstance(member, dict) else member
        flat = _merge_fragments(record)
        if flat.get("player_key") or flat.get("pick"):
            results.append(flat)
    return results


def state_from_yahoo(
    league: Dict[str, Any],
    draft_results: Optional[List[Dict[str, Any]]] = None,
    players_index: Optional[Dict[str, Dict[str, str]]] = None,
) -> DraftState:
    """Assemble a :class:`DraftState` from already-fetched Yahoo data.

    Performs no network I/O. Maps Yahoo league settings onto SCORING_CONFIGS /
    ROSTER_CONFIGS keys and normalizes every draft result via
    :func:`pick_from_yahoo`.

    Args:
        league: Merged Yahoo league dict (``league_key``, ``num_teams``,
            ``draft_status``, ``season``, ``settings``...).
        draft_results: Parsed draft-result dicts (see :func:`parse_draft_results`).
        players_index: ``player_key -> identity`` for name/position resolution.

    Returns:
        A normalized :class:`DraftState`; never raises.
    """
    league = league if isinstance(league, dict) else {}
    draft_results = draft_results if isinstance(draft_results, list) else []
    players_index = players_index or {}
    settings = league.get("settings")
    if not isinstance(settings, dict):
        settings = league  # some payloads inline settings at the league level

    scoring = _scoring_format_from_settings(settings)
    roster = _roster_format_from_settings(settings)
    if scoring not in SCORING_CONFIGS:
        scoring = "half_ppr"
    if roster not in ROSTER_CONFIGS:
        roster = "standard"

    pick_events = tuple(
        sorted(
            (pick_from_yahoo(r, players_index) for r in draft_results),
            key=lambda pe: pe.pick_no,
        )
    )

    slot_to_roster_id: Dict[str, int] = {}
    for pe in pick_events:
        if pe.roster_id is not None:
            slot_to_roster_id[str(pe.draft_slot)] = pe.roster_id

    league_key = str(league.get("league_key") or "")
    league_id = league_key.split(".l.")[-1] if ".l." in league_key else league_key

    return DraftState(
        draft_id=league_key or league_id,
        status=_normalize_status(league.get("draft_status")),
        draft_type=str(settings.get("draft_type") or "snake"),
        season=str(league.get("season") or ""),
        n_teams=_safe_int(league.get("num_teams")),
        rounds=_infer_rounds(pick_events, _safe_int(league.get("num_teams"))),
        scoring_format=scoring,
        roster_format=roster,
        draft_order={},
        slot_to_roster_id=slot_to_roster_id,
        picks=pick_events,
        traded_picks=tuple(),
    )


def _normalize_status(yahoo_status: Any) -> str:
    """Map a Yahoo ``draft_status`` onto the neutral status vocabulary.

    Yahoo uses ``predraft`` / ``drafting`` / ``postdraft``. The neutral model's
    ``is_active`` treats ``drafting`` / ``paused`` as live, so ``predraft`` and
    ``postdraft`` pass through as-is (non-active).
    """
    status = str(yahoo_status or "").lower()
    if status == "drafting":
        return "drafting"
    return status


def _infer_rounds(picks: Tuple[PickEvent, ...], n_teams: int) -> int:
    """Infer the round count from picks (max round seen) or fall back to 0."""
    if picks:
        return max((p.round for p in picks), default=0)
    return 0


# ---------------------------------------------------------------------------
# Network-touching assembly + resolution
# ---------------------------------------------------------------------------


def _league_key(identifier: str) -> str:
    """Normalize a league identifier to a full Yahoo ``nfl.l.<id>`` league_key."""
    ident = str(identifier or "")
    if not ident:
        return ""
    if ident.startswith("nfl.l."):
        return ident
    return f"nfl.l.{ident}"


def load_draft_state(draft_id: str, oauth: Optional[YahooOAuth] = None) -> DraftState:
    """Fetch a league's settings + draft results + players, assemble a DraftState.

    The single place here that performs network I/O. Fail-open: an unreachable or
    throttled Yahoo yields a DraftState with empty picks rather than raising.
    Callers (the live engine) MUST poll this conservatively (~once per 5-10s) to
    avoid Yahoo's HTTP 999 throttling.

    Args:
        draft_id: Yahoo league_key (``nfl.l.<id>``) or bare league id.
        oauth: Token manager; constructed from env if omitted.

    Returns:
        A normalized :class:`DraftState`.
    """
    oauth = oauth or YahooOAuth()
    league_key = _league_key(draft_id)
    if not league_key:
        return state_from_yahoo({}, [], {})

    league_node = fetch_yahoo_json(f"/league/{league_key}/settings", oauth)
    league = _extract_league(league_node)

    draft_node = fetch_yahoo_json(f"/league/{league_key}/draftresults", oauth)
    draft_results = parse_draft_results(
        _extract_subresource(draft_node, "draft_results")
    )

    players_index: Dict[str, Dict[str, str]] = {}
    player_keys = [r.get("player_key") for r in draft_results if r.get("player_key")]
    if player_keys:
        players_node = fetch_yahoo_json(
            f"/league/{league_key}/players;player_keys={','.join(player_keys)}",
            oauth,
        )
        players_index = build_players_index(
            _extract_subresource(players_node, "players")
        )

    return state_from_yahoo(league, draft_results, players_index)


def _extract_league(node: Any) -> Dict[str, Any]:
    """Pull and merge the ``league`` record out of a fantasy_content envelope."""
    content = node.get("fantasy_content") if isinstance(node, dict) else None
    league_node = content.get("league") if isinstance(content, dict) else None
    if league_node is None:
        return {}
    return _merge_fragments(league_node)


def _extract_subresource(node: Any, name: str) -> Any:
    """Pull a named subresource (e.g. ``draft_results``) from the envelope.

    Yahoo nests it under ``fantasy_content.league[...]<name>``. Returns the raw
    collection node for :func:`_iter_collection`, or ``{}`` when absent.
    """
    content = node.get("fantasy_content") if isinstance(node, dict) else None
    league_node = content.get("league") if isinstance(content, dict) else None
    if league_node is None:
        return {}
    # league is usually [meta_dict, {<name>: {...}}]; scan for the sub-key.
    candidates = league_node if isinstance(league_node, list) else [league_node]
    for frag in candidates:
        if isinstance(frag, dict) and name in frag:
            return frag[name]
    return {}


def resolve_active_draft(
    identifier: str,
    season: str,
    league_id: Optional[str] = None,
    oauth: Optional[YahooOAuth] = None,
) -> Dict[str, Any]:
    """Resolve a Yahoo league draft from a league id/key (or the user's leagues).

    Yahoo drafts are addressed by league, so the primary path treats
    ``identifier`` (or ``league_id``) as a league id/key and inspects its
    ``draft_status``. When only a username-like identifier is given and no league
    id, this falls back to listing the authenticated user's NFL leagues for the
    season and picking the one currently ``drafting`` (else most recent).

    Returns:
        ``{found, draft_id, league_id, status, candidates}``. ``draft_id`` is the
        Yahoo league_key (what :func:`load_draft_state` expects). Never raises
        (D-06 fail-open).
    """
    empty = {
        "found": False,
        "draft_id": "",
        "league_id": "",
        "status": "",
        "candidates": [],
    }
    oauth = oauth or YahooOAuth()

    # Direct league addressing (preferred — Yahoo drafts are league-scoped).
    league_ident = league_id or identifier
    if league_ident:
        league_key = _league_key(league_ident)
        node = fetch_yahoo_json(f"/league/{league_key}/settings", oauth)
        league = _extract_league(node)
        if league.get("league_key"):
            status = _normalize_status(league.get("draft_status"))
            return {
                "found": True,
                "draft_id": str(league.get("league_key")),
                "league_id": str(league.get("league_key")).split(".l.")[-1],
                "status": status,
                "candidates": [
                    {
                        "draft_id": str(league.get("league_key")),
                        "league_id": str(league.get("league_key")).split(".l.")[-1],
                        "status": status,
                        "name": str(league.get("name") or ""),
                    }
                ],
            }

    # Fallback: enumerate the authenticated user's NFL leagues for the season.
    candidates = _user_league_candidates(season, oauth)
    if not candidates:
        return dict(empty)
    active = [c for c in candidates if c["status"] == "drafting"]
    chosen = active[0] if active else candidates[0]
    return {
        "found": True,
        "draft_id": chosen["draft_id"],
        "league_id": chosen["league_id"],
        "status": chosen["status"],
        "candidates": candidates,
    }


def _user_league_candidates(season: str, oauth: YahooOAuth) -> List[Dict[str, str]]:
    """List the authenticated user's NFL leagues for a season as candidates."""
    node = fetch_yahoo_json(
        f"/users;use_login=1/games;game_codes=nfl;seasons={season}/leagues", oauth
    )
    content = node.get("fantasy_content") if isinstance(node, dict) else None
    if not isinstance(content, dict):
        return []
    candidates: List[Dict[str, str]] = []
    # users -> user -> games -> game -> leagues -> league[...]
    for user in _iter_collection(content.get("users")):
        flat_user = user.get("user") if isinstance(user, dict) else user
        for frag in flat_user if isinstance(flat_user, list) else [flat_user]:
            if not isinstance(frag, dict) or "games" not in frag:
                continue
            for game in _iter_collection(frag["games"]):
                g = game.get("game") if isinstance(game, dict) else game
                for gf in g if isinstance(g, list) else [g]:
                    if not isinstance(gf, dict) or "leagues" not in gf:
                        continue
                    for lg in _iter_collection(gf["leagues"]):
                        league = _merge_fragments(
                            lg.get("league") if isinstance(lg, dict) else lg
                        )
                        key = str(league.get("league_key") or "")
                        if not key:
                            continue
                        candidates.append(
                            {
                                "draft_id": key,
                                "league_id": key.split(".l.")[-1],
                                "status": _normalize_status(league.get("draft_status")),
                                "name": str(league.get("name") or ""),
                            }
                        )
    return candidates
